import os.path
from math import ceil
from aws_cdk.aws_s3_assets import Asset
from aws_cdk import (
    core,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_ssm as ssm,
    aws_logs as logs,
    aws_route53 as dns,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_lambda as lambda_,
    aws_apigateway as api,
    aws_budgets as budget
    )

dirname = os.path.dirname(__file__)

class CdkMinecraftStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str,  **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        ######################
        #                    #
        #    EC2 SECTION     #
        #                    #
        ######################
        
        
        # We are going to create our own VPC and public subnet to stand up the server in.  
        # We are not making a nat gateway since everything is public and that would be an added unnessessary cost.
        vpc = ec2.Vpc(self, "Minecraft VPC",
                        nat_gateways = 0,
                        subnet_configuration=[ec2.SubnetConfiguration(name="public",subnet_type=ec2.SubnetType.PUBLIC)])
                        
        # Find the latest Amazon Linux 2 AMI to use for our image
        amzn_linux = ec2.MachineImage.latest_amazon_linux(
                        generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
                        edition=ec2.AmazonLinuxEdition.STANDARD,
                        virtualization=ec2.AmazonLinuxVirt.HVM,
                        storage=ec2.AmazonLinuxStorage.GENERAL_PURPOSE )
 
        # Set up our security group, this will allow access on the minecraft port, and SSH depending on what was selected
        
        minecraft_security = ec2.SecurityGroup(self, "Minecraft Security", vpc = vpc)
        minecraft_security.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(25565), 'Allow Minecraft from Anywhere')
        if self.node.try_get_context('myIpAddress'):      #Only create a rule if the personal IP is assigned
            minecraft_security.add_ingress_rule(ec2.Peer.ipv4(self.node.try_get_context('MyIPAddress')), ec2.Port.tcp(22), 'Allow SSH from my network')
        if self.node.try_get_context('useEc2InstanceConnect'):      #This can be turned on/off with the boolean in the context
            minecraft_security.add_ingress_rule(ec2.Peer.ipv4('3.16.146.0/29'), ec2.Port.tcp(22), 'Allow SSH From EC2 Instance Connect')
        minecraft_security.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8123), 'Allow Dynmap from Anywhere') # TODO: Make these extra ports adjustable from cdk.json
        
        # We are going to create a role for our server, then give it permissions to be managed by SSM, and use the cloudwatch agent.  (More permissions to come later in this file)
        role = iam.Role(self, "InstancePermissions", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"))

        # Create an EC2 Instance for our minecraft server based on the things we've already done above.
        minecraft_server =  ec2.Instance(self, "Minecraft Server",
                            instance_type=ec2.InstanceType(self.node.try_get_context("InstanceType")),
                            machine_image=amzn_linux,
                            vpc = vpc,
                            role = role,
                            key_name  = self.node.try_get_context("sshKeyName"),
                            security_group = minecraft_security
                            )
        
        # We build out an ARN of the server so that we can plug it into the policy below
        minecraft_server_arn = core.Stack.of(self).format_arn(service="ec2", resource="instance", resource_name= minecraft_server.instance_id )
        
                # This role allows this server to get the details of other instances, and change anything on itself.  This is used to read/update it's own tags
        role.attach_inline_policy(iam.Policy(self, "EC2 self access", statements = [iam.PolicyStatement(effect=iam.Effect.ALLOW,
                                                resources=[minecraft_server_arn],
                                                actions=["ec2:*"]),
                                                iam.PolicyStatement(effect=iam.Effect.ALLOW,
                                                resources=["*"],
                                                actions=["ec2:Describe*"])]))

        instanceId = core.CfnOutput(self, "instanceId", 
                            value=minecraft_server.instance_id,
                            export_name="minecraftinstanceid")
                            
  
        ######################
        #                    #
        #  TAGGING SECTION   #
        #                    #
        ######################
        
        # There is a section for tags in cdk.json.  We're going to add all those tags to the server we just created.
        for key, value in self.node.try_get_context("tags").items():
            core.Tags.of(minecraft_server).add(key, value)
        
        # We have an S3 bucket that we will be storing files in to use for setup.  We're going to add the name of that bucket as a tag so we can look it up from inside the instance.
        file_bucket = s3.Bucket.from_bucket_arn(self, "Files Bucket", bucket_arn =  ssm.StringParameter.value_for_string_parameter(self, "s3_bucket_files"))
        core.Tags.of(minecraft_server).add("s3_file_url", file_bucket.s3_url_for_object())
        file_bucket.grant_read_write(minecraft_server.role)
        
        # We want to capture the name of the bucket, and we're going to add that as a tag so the backup script can find it from inside the instance.
        backup_bucket = s3.Bucket.from_bucket_arn(self, "Backup Bucket", bucket_arn =  ssm.StringParameter.value_for_string_parameter(self, "s3_bucket_backups"))
        core.Tags.of(minecraft_server).add("s3_backup_url", backup_bucket.s3_url_for_object())  
        backup_bucket.grant_read_write(minecraft_server.role)       # Give the instance permissiont to read/write that bucket
    

        
        ######################
        #                    #
        #  DNS SECTION       #
        #                    #
        ######################


        # DNS Settings are optional.  If we have the dns zone defined, we're going to lookup the route53 zone and give our instance policy permission to update the DNS record.
        if self.node.try_get_context("tags")['dns_zone']:
            dns_zone = dns.HostedZone.from_lookup(self, "DNS Zone", domain_name = self.node.try_get_context("tags")['dns_zone'] )

            role.attach_inline_policy(iam.Policy(self, "DNS Updating Access", statements = [iam.PolicyStatement(effect=iam.Effect.ALLOW,
                                                    resources=[minecraft_server_arn],
                                                    actions=["ec2:*"]),
                                                    iam.PolicyStatement(effect=iam.Effect.ALLOW,
                                                    resources=["arn:aws:route53:::hostedzone/" + dns_zone.hosted_zone_id],
                                                    actions=["route53:ChangeResourceRecordSets"]),
                                                    iam.PolicyStatement(effect=iam.Effect.ALLOW,
                                                    resources=["*"],
                                                    actions=["route53:ListHostedZones"])
                                                    ]))

        ########################
        #                      #
        #  CLOUDWATCH SECTION  #
        #                      #
        ########################
        
        # There is a script that gets run on the server that will collect the active and max players from minecraft, and push it into cloudwatch.
        # We need to give the instance role permission to push to those custom metrics.  Also, we are optionally going to set up an alarm based 
        # on that active_players metric and shut down the server when nobody is playing.
        
        active_players_metric = cloudwatch.Metric(metric_name = "active_players", 
                                                  namespace = 'Minecraft',
                                                  dimensions_map = {"InstanceId": minecraft_server.instance_id} )
        active_players_metric.grant_put_metric_data(minecraft_server.role)
        
        max_players_metric = cloudwatch.Metric(metric_name = "max_players", 
                                               namespace = 'Minecraft',
                                               dimensions_map = {"InstanceId": minecraft_server.instance_id} )
        max_players_metric.grant_put_metric_data(minecraft_server.role)
        
        #Set up an alarm on the playercount metric
        if self.node.try_get_context("shutdownWhenIdle"):
            alarm = cloudwatch.Alarm(self, "Idle Server Alarm",
                metric=active_players_metric,
                threshold=self.node.try_get_context("shutdownWhenIdleMinimumPlayers"),
                comparison_operator = cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
                evaluation_periods=ceil(self.node.try_get_context("shutdownWhenIdleMinutes")/5),
                datapoints_to_alarm=ceil(self.node.try_get_context("shutdownWhenIdleMinutes")/5),
                statistic="max")
            alarm.add_alarm_action(cw_actions.Ec2Action(cw_actions.Ec2InstanceAction.STOP))
       
        ########################
        #                      #
        #    ASSET SECTION     #
        #                      #
        ########################
       
        # We have files included in this CDK project that we want to put into that new instance we're creating.  These next steps 
        # define what files need to be put there, give the instance permission to read them, and tell the server to run our configure.sh to finish setup.
        
        # configure.sh is the script that finishes our setup on the server.
        # NOTE: changing configure.sh and re-deploying the CDK project will not trigger a re-run of the file, you'll need to re-create the server.
        asset = Asset(self, "Asset", path=os.path.join(dirname, "configure.sh"))
        local_path = minecraft_server.user_data.add_s3_download_command(
            bucket=asset.bucket,
            bucket_key=asset.s3_object_key
        )

        # The resources directory contain other files that we'll use during configure.sh, like the minecraft startup script, user whitelist, etc.
        directory_asset = Asset(self, "Resources Directory",
          path=os.path.join(dirname, "resources")
        )
        
        local_directory = minecraft_server.user_data.add_s3_download_command(
            bucket = directory_asset.bucket,
            bucket_key = directory_asset.s3_object_key,
            local_file = "/tmp/resources.zip")
        
        directory_asset.grant_read(minecraft_server.role)
        
        
        # Userdata executes script from S3
        minecraft_server.user_data.add_execute_file_command(
            file_path=local_path
            )
        asset.grant_read(minecraft_server.role)
        
        
        ########################
        #                      #
        #  LAMBDA/API SECTION  #
        #                      #
        ########################
        if self.node.try_get_context("enableStartupUrl"):
            
            with open("minecraft_start.py", encoding="utf8") as fp:
                minecraft_start_code = fp.read()
            
            # The startup password is optional.  If it's set to false or an empty string, we will skip assigning it.
            if self.node.try_get_context("startupPassword"):
                my_lambda_env = {'INSTANCE_ID': minecraft_server.instance_id,
                                 'PASSWORD': self.node.try_get_context("startupPassword")}
            else:
                my_lambda_env = {'INSTANCE_ID': minecraft_server.instance_id}
            


            my_lambda_role = iam.Role(self, "MinecraftLambdaRole",assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"))
            
            my_lambda_policy = iam.ManagedPolicy(self, "MinecraftLambdaStartupEnabled",
                                                 description="This policy allows the lambda startup job to trigger the startup of the minecraft server" )
            
            my_lambda_policy.add_statements(iam.PolicyStatement(
                                        effect=iam.Effect.ALLOW,
                                        actions=["ec2:StartInstances"],
                                        resources=[f'arn:{self.partition}:ec2:{self.region}:{self.account}:instance/{minecraft_server.instance_id}']
                                        ))
            my_lambda_policy.add_statements(iam.PolicyStatement(
                                effect=iam.Effect.ALLOW,
                                actions=["ec2:DescribeInstances"],
                                resources=["*"]
                                ))
                                
            my_lambda_policy.attach_to_role(my_lambda_role)
            
            my_lambda = lambda_.Function(self, "MinecraftStartup",
                                            runtime=lambda_.Runtime.PYTHON_3_8,
                                            handler="index.main",
                                            code=lambda_.InlineCode(minecraft_start_code),
                                            environment=my_lambda_env,
                                            role=my_lambda_role)

            lambda_api = api.LambdaRestApi(self, "MinecraftStartupApi",
                                            handler=my_lambda
                                        )
            apiUrl = core.CfnOutput(self, "apiUrl",
                                    value=lambda_api.url,
                                    export_name="minecraftstartupurl",
                                    description="Use this URL to start the minecraft server")

        ########################
        #                      #
        #    BUDGET SECTION    #
        #                      #
        ########################
        if self.node.try_get_context("enableBudget"):
            # Create a budget data object with a dollar limit from whatever was set inside cdk.json.  We are filtering costs on the cloudformation stack.
            #   We need that defined in the billing UI (see readme.md) before this can work.
            minecraft_budget_data = budget.CfnBudget.BudgetDataProperty(
                                            budget_name="minecraft budget",
                                            budget_type="COST",
                                            budget_limit=budget.CfnBudget.SpendProperty(amount=self.node.try_get_context("budgetLimit"), unit="USD"),
                                            cost_filters={"TagKeyValue": ["aws:cloudformation:stack-name$cdk-minecraft" ]},
                                            cost_types=budget.CfnBudget.CostTypesProperty( include_credit=False, 
                                                                                        include_discount=False, 
                                                                                        include_other_subscription=True, 
                                                                                        include_recurring=True, 
                                                                                        include_refund=False, 
                                                                                        include_subscription=True, 
                                                                                        include_support=True, 
                                                                                        include_tax=True,
                                                                                        include_upfront=True, 
                                                                                        use_amortized=False, 
                                                                                        use_blended=False),
                                            time_unit = "MONTHLY")

            # Create the budget using the data we just defined
            minecraft_budget = budget.CfnBudget(self, "MinecraftBudget",
                                                budget = minecraft_budget_data)

            # We'll need to have permission to stop EC2 instances (using SSM), that's in this managed role.
            budget_role = iam.Role(self, "Budget Role", assumed_by=iam.ServicePrincipal("budgets.amazonaws.com"))
            budget_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSBudgetsActionsRolePolicyForResourceAdministrationWithSSM"))


            # We also want this budget to do something, not just sit here and look pretty, so we're going to shut down the minecraft server when we run out of money.
            #  It will also email the address defined in cdk.json when this happens.
            budget_action_shutdown = budget.CfnBudgetsAction(self, "MinecraftBudgetAction100",
                                                        action_threshold=budget.CfnBudgetsAction.ActionThresholdProperty(
                                                            type = "PERCENTAGE", 
                                                            value = 100.0),
                                                        action_type = "RUN_SSM_DOCUMENTS",
                                                        budget_name = "minecraft budget",
                                                        definition = budget.CfnBudgetsAction.DefinitionProperty(
                                                            ssm_action_definition=budget.CfnBudgetsAction.SsmActionDefinitionProperty(
                                                                instance_ids=[minecraft_server.instance_id],
                                                                region=self.region,
                                                                subtype="STOP_EC2_INSTANCES")),
                                                        execution_role_arn = budget_role.role_arn,
                                                        notification_type ="ACTUAL",
                                                        approval_model = "AUTOMATIC",
                                                        subscribers=[budget.CfnBudgetsAction.SubscriberProperty(
                                                            address=self.node.try_get_context("budgetAlertEmail"),
                                                            type="EMAIL")]
                                                        )

            if self.node.try_get_context("enableStartupUrl"):
                # If we are using the startup URL feature, we will need to lock that down when the budget runs out, because the budget stops the server but it can
                #   be started again unless we take away the permission on the lambda job as well.  We create this as a managed policy so we can leave it unattached until
                #   it is needed.  This policy is a mirror of the policy created with the lambda job, just with DENY in place of ALLOW.
                
                my_lambda_disable_policy = iam.ManagedPolicy(self, "MinecraftLambdaStartupDisabled", 
                                                             description="This job reverses what is in the default policy for the lambda job, stopping startup once the budget has run out.")
                
                my_lambda_disable_policy.add_statements(iam.PolicyStatement(
                                            effect=iam.Effect.DENY,
                                            actions=["ec2:StartInstances"],
                                            resources=[f'arn:{self.partition}:ec2:{self.region}:{self.account}:instance/{minecraft_server.instance_id}']
                                            ))

                my_lambda_disable_policy.add_statements(iam.PolicyStatement(
                                    effect=iam.Effect.DENY,
                                    actions=["ec2:DescribeInstances"],
                                    resources=["*"]
                                    ))
                
                # We also need to give our budget the permission to attach/detach role policies, otherwise this won't do anything
                budget_role.add_to_policy(iam.PolicyStatement(
                                        effect=iam.Effect.ALLOW,
                                        actions=["iam:AttachRolePolicy","iam:DetachRolePolicy"],
                                        resources=[my_lambda_role.role_arn]
                                        ))

                # This is very much like the above action for stopping EC2, but in this case we attach our deny policy to the role used by lambda.  This stops the URL
                #    from starting the server again until the policy is removed.
                budget_action_disable_lambda = budget.CfnBudgetsAction(self, "MinecraftBudgetAction100-IAM",
                                                            action_threshold=budget.CfnBudgetsAction.ActionThresholdProperty(
                                                                type = "PERCENTAGE", 
                                                                value = 100.0),
                                                            action_type = "APPLY_IAM_POLICY",
                                                            budget_name = "minecraft budget",
                                                            definition = budget.CfnBudgetsAction.DefinitionProperty(
                                                                iam_action_definition=budget.CfnBudgetsAction.IamActionDefinitionProperty(
                                                                    policy_arn=my_lambda_disable_policy.managed_policy_arn,
                                                                    roles=[my_lambda_role.role_name])),
                                                            execution_role_arn = budget_role.role_arn,
                                                            notification_type ="ACTUAL",
                                                            approval_model = "AUTOMATIC",
                                                            subscribers=[budget.CfnBudgetsAction.SubscriberProperty(
                                                                address=self.node.try_get_context("budgetAlertEmail"),
                                                                type="EMAIL")]
                                                            )

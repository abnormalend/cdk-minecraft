from aws_cdk import core
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_logs as logs

class CdkMinecraftS3Stack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # This stack defines the S3 buckets that we want to reference in the main stack, but not re-recreate when rebuilding minecraft itself
        
        minecraft_files = s3.Bucket(self, "MinecraftFiles",
                                            block_public_access = s3.BlockPublicAccess.BLOCK_ALL )
        ssm.StringParameter(self, "FileBucketURL", parameter_name = "s3_bucket_files", 
                                    string_value = minecraft_files.bucket_arn)
        
        if self.node.try_get_context("useS3Backup"):
            minecraft_backups = s3.Bucket(self, "MinecraftBackups",
                                            block_public_access = s3.BlockPublicAccess.BLOCK_ALL,
                                            lifecycle_rules = [s3.LifecycleRule(expiration = core.Duration.days(365))])
            ssm.StringParameter(self, "BackupBucketName", parameter_name = "s3_bucket_backups", 
                                    string_value = minecraft_backups.bucket_arn)                
                                    

        minecraft_log = logs.LogGroup(self, "MinecraftLog", log_group_name = "minecraft.log", retention = logs.RetentionDays.ONE_MONTH)
        messages_log = logs.LogGroup(self, "MessagesLog", log_group_name = "/var/log/messages", retention = logs.RetentionDays.ONE_MONTH)
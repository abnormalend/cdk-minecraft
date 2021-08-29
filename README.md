# cdk-minecraft
cdk-minecraft is an all-in-one minecraft server deployment that makes it easy to shut the server down when you're not using it, saving significant cost over running it 24/7.
## Installation
### Prerequisites 
It is assumed you have:

 - An AWS Account
 - Access to run the AWS CLI, with CDK installed.

The quickest way to get the second if you don't already have it is by spinning up an AWS Cloud9 instance.
### Cloud9 Environment

 1. Log into the AWS console
 2. Find the Cloud9 service (example: type cloud9 into the top search bar
 3. Press "Create Environment"
 4. Give it a name, something like "cdk-minecraft"
 5. Leave everything else as the default, selecting next at each page, until you can press "Create Environment" to complete it.
 6. Wait for your Cloud9 environment to start up
### Download from github, customize, and install
 1. You'll need to get the cdk-minecraft repository.  
` git clone https://github.com/abnormalend/cdk-minecraft.git`

 2. Look for a file on the sidebar named cdk.json.  In this file we are going to make some customizations.  Here is an excerpt from the file, focusing on the minumum required things we'll want to adjust for your installation.   You can change more things, but these are the must haves.

> **"region": "us-east-1",**
> **"awsAccount": "YOUR_ACCOUNT_NUMBER_HERE",**
> "tags": {
> "dns_hostname": "minecraft",
> **"dns_zone": "yourdomain.here.",**
		

 - Region: you probably want this to be the closest to where you live.
				 us-east-1: Virginia
				 us-east-2: Ohio
				 us-west-1: Northern California
				 us-west-2: Oregon
				 for more options, google "AWS regions"
 - AWS Account: You can find this number in the upper right of the aws console, under the username you're signed in as.
 - DNS Zone.  If you have a DNS zone, enter it here.  If you don't just delete this line.

  3. Then we need to enter the directory that was just created.
`cd cdk-minecraft`
  4. Install python modules with this command.
  `pip3 install -r requirements.txt`
   5. Finally we are ready!  For these next commands, you can swap synth where I say deploy to see what will be created without doing anything.  This first one will create the S3 buckets.  We keep it in a separate stack so we can re-create the Minecraft server without messing with these buckets.
   `cdk deploy cdk-minecraft-s3`
   Then we install the server itself with:
   `cdk deploy cdk-minecraft`

## Features
### Dynamic DNS
Update Route53 with public IP.  Avoiding use of elastic IP's for a frequently powered down system eliminates charges for an allocated but unused elastic IP.
### Dynamic JVM Memory
If you change the instance type, the JVM memory settings will automatically be updated to match the instance available memory.
### Automatic Idle Shutdown
A custom metric logs the number of logged in players (and max players).  A cloudwatch metric & alarm will power down the instance when nobody is logged in.
### Paper Updater
Get the latest version of paper minecraft server, and create tags to mark the current version.  Minecraft target version can be updated via tags, without logging into the server.
### Minecraft World Backup
Backup the minecraft world to S3, and automatically restore from S3 if a backup exists on new server creation.
### Startup via special URL
Save a bookmark or set up your alexa to start the server on demand (more details below)

## TODO
## Spot Instances
Using spot instances can save even more money while the server is running.

## Adjustable settings
cdk.json contains a set of variables that controls how cdk-minecraft is installed.  Some options (like account id) **must** be filled, others have defaults assigned.

### InstanceType
*String*

What kind of server are we running minecraft on.  T type instances are good for testing, but won't handle many players once you run out of CPU credits.  This can be adjusted at any time and a re-deploy of the project will power down the server, change the instance type, and bring it back up.  M4.large is a fairly powerful option that only costs (when writing this) $0.10 per hour.


### sshKeyName
*String*

What key to use for connecting with SSH.  This is not required if you are only going to do EC2 Instance Connect should you need to connect to your server.  
This CDK requires you to make an ssh key first, found [here](https://console.aws.amazon.com/ec2/v2/home#KeyPairs): 

### region
*String*

What region do you want to deploy the minecraft server into?  The default value is us-east-1 (Virginia).  List of regions available [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html#concepts-available-regions)

Default: us-east-1

### awsAccount
*String* 

What AWS account are we deploying this into?

*looking to remove the need for this*

### myIpAddress
*String*

If you want to allow SSH from home, put in your home IP address here (CIDR block format, 123.123.123.123/24).  If your home IP changes, updating this value and re-deploying will change the security rule to let you in again.  This is not needed if you only want to do EC2 Instance Connect.

Default: unused

### useEc2InstanceConnect
*Boolean*

Do you want to allow connecting from EC2 Instance Connect (in browser shell).  If you enable this option you can skip defining sshKeyName and myIpAddress, and just use instance connect while logged into the AWS console.  You can also do both methods, you are not limited to one or the other.

Default: True

### shutdownWhenIdle
*Boolean*

If enabled, an alarm will be created that shuts the server down when there is less than the minimum number of players connected.  

Default: True

### shutdownWhenIdleMinimumPlayers
*Integer*

Shutdown alarm triggered if there are less than this many players connected to the server.  This is only required if shutdownWhenIdle is enabled.  

Default: 1

### shutdownWhenIdleMinutes
*Integer*

How long can the server have less than the above required playercount before the shutdown is triggered.  Will round up to nearest 5 minute increment if needed (if you set this to 12, you'll get 15 minutes). 

Default: 15

### enableStartupUrl
*Boolean*

Do you want a startup URL created to easily boot the server on demand?  Highly recommended if using the above shutdown automation, as it reduces the need to log into the AWS console to start the server.  This URL can bookmarked, or even connected through Alexa.

Default: true

### startupPassword
*String*

Optional password to require on the URL in order to trigger the start.  Incorrect or missing password will return a 403.  Set this to false or an empty string to disable the password.

Default: false

### enableBudget
*Boolean*

Do you want to use an AWS budget to limit your costs?  This requires some manual setup, [see the section on enabling Budget](#Budgets) for further details.  Suggested to keep as false to start.

Default: false

### tags
These things get added as tags, but the defined ones also have some effect on the way the server behaves.  You can add other arbetrary tags to this block if desired.

### dns_hostname
if you want DNS update script to update your IP, set the target hostname here.  Combines with hosted_zone to form your FQDN.

#### dns_hosted_zone
if you want DNS update script to update your IP, set the hosted zone here.  This needs to already be configured in Route53.

#### minecraft_game_mode
Game mode to set in the server properties, survival / creative / adventure **Not Yet Implemented**

#### reserved_memory
This much memory will be reserved from going into the minecraft JVM.  If your instance has 2048M of ram and this is set to 512M, XMX setting in java will be 1536M

## S3 Buckets
The s3 stack creates 1 or 2 buckets depending on your settings.  File resources (Minecraft server jar, paper jar, plugins and mods) that can change (new releases) outside changes to this code belong in the file bucket.  If you're backing up your world to S3, then there is a different bucket for that.

## Budgets
> Written with [StackEdit](https://stackedit.io/).

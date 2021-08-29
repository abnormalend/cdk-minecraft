#!/usr/bin/env python3

from aws_cdk import core

from cdk_minecraft.cdk_minecraft_s3_stack import CdkMinecraftS3Stack
from cdk_minecraft.cdk_minecraft_stack import CdkMinecraftStack


app = core.App()
my_env = core.Environment(region=app.node.try_get_context("region"), account = app.node.try_get_context("awsAccount"))
CdkMinecraftStack(app, "cdk-minecraft", env=my_env)
CdkMinecraftS3Stack(app, "cdk-minecraft-s3", env=my_env)

app.synth()

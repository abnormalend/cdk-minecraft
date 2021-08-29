import os
import sys
import json
import boto3
import botocore

ec2 = boto3.resource('ec2')

def main(event, context):
    if "PASSWORD" in os.environ:
        if not event['path'] == "/" + os.environ.get('PASSWORD'):
            return {'statusCode': 401,
                    'body': json.dumps('Password required to access this resource')}
    
    ids = [os.environ.get('INSTANCE_ID')]
    try:
        ec2.instances.filter(InstanceIds=ids).start()
        return {'statusCode': 200,
                'body': json.dumps('Server is starting')}
    except botocore.exceptions.ClientError:
        return {'statusCode': 403,
        'body': json.dumps('Permission denied starting resource, did your budget run out?')}
    except:
        print("Unexpected error:", sys.exc_info()[0])
        raise
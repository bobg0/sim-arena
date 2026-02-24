import boto3

sts = boto3.client("sts", region_name="us-east-1")
print(sts.get_caller_identity())
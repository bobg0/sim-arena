import os
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
LT_ID = "lt-0e714d89b56d21b82"         # your template id
LT_VER = "$Latest"                    # or "1"

ec2 = boto3.client("ec2", region_name=REGION)

resp = ec2.run_instances(
    MinCount=1,
    MaxCount=1,
    LaunchTemplate={"LaunchTemplateId": LT_ID, "Version": LT_VER},
)

instance_id = resp["Instances"][0]["InstanceId"]
print("Launched:", instance_id)

# wait until it's running
ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
print("Running:", instance_id)

# optional: terminate right away for smoke test
ec2.terminate_instances(InstanceIds=[instance_id])
print("Terminated:", instance_id)
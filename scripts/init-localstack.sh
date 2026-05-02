import boto3
import json

ENDPOINT = "http://localstack:4566"
REGION   = "us-east-1"
kwargs   = dict(
    endpoint_url=ENDPOINT,
    region_name=REGION,
    aws_access_key_id="test",
    aws_secret_access_key="test",
)

s3  = boto3.client("s3",  **kwargs)
sqs = boto3.client("sqs", **kwargs)

# S3 buckets
for bucket in ("raw-images-propelhq", "processed-images-propelhq"):
    try:
        s3.create_bucket(Bucket=bucket)
        print(f"  created bucket: {bucket}")
    except Exception as e:
        print(f"  bucket already exists or error ({bucket}): {e}")

# DLQ
print("==> Creating DLQ...")
dlq_url = sqs.create_queue(QueueName="image-processing-dlq-propelhq")["QueueUrl"]
dlq_arn = sqs.get_queue_attributes(
    QueueUrl=dlq_url, AttributeNames=["QueueArn"]
)["Attributes"]["QueueArn"]
print(f"  DLQ ARN: {dlq_arn}")

# Main queue
print("==> Creating main SQS queue...")
sqs.create_queue(
    QueueName="image-processing-queue-propelhq",
    Attributes={
        "RedrivePolicy": json.dumps({
            "deadLetterTargetArn": dlq_arn,
            "maxReceiveCount": "3",
        })
    },
)
print("  created: image-processing-queue-propelhq")
print("==> All AWS resources created successfully.")
import os

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "")  # e.g. http://localstack:4566

S3_BUCKET_RAW = os.environ.get("S3_BUCKET_RAW", "raw-images-yourid")
S3_BUCKET_PROCESSED = os.environ.get("S3_BUCKET_PROCESSED", "processed-images-yourid")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "http://localstack:4566/000000000000/image-processing-queue-yourid")

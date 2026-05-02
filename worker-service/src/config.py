import os

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "")  # e.g. http://localstack:4566

S3_BUCKET_RAW = os.environ.get("S3_BUCKET_RAW", "raw-images-yourid")
S3_BUCKET_PROCESSED = os.environ.get("S3_BUCKET_PROCESSED", "processed-images-yourid")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "http://localstack:4566/000000000000/image-processing-queue-yourid")

# SQS polling config
SQS_WAIT_TIME_SECONDS = int(os.environ.get("SQS_WAIT_TIME_SECONDS", "20"))  # Long polling
SQS_MAX_MESSAGES = int(os.environ.get("SQS_MAX_MESSAGES", "5"))
SQS_VISIBILITY_TIMEOUT = int(os.environ.get("SQS_VISIBILITY_TIMEOUT", "60"))

# Retry config
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.environ.get("RETRY_BASE_DELAY", "1.0"))

# Image processing
WATERMARK_TEXT = os.environ.get("WATERMARK_TEXT", "PropelHQ")
THUMBNAIL_SIZE = (150, 150)

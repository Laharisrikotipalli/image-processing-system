#!/bin/bash
# Runs automatically inside LocalStack once it is ready (mounted at
# /etc/localstack/init/ready.d/). Creates S3 buckets and SQS queues.

set -e

ENDPOINT="http://localhost:4566"
REGION="us-east-1"

echo "==> LocalStack init script starting..."

# ── S3 Buckets ────────────────────────────────────────────────────────────────
echo "  Creating S3 bucket: raw-images-propelhq"
aws --endpoint-url=$ENDPOINT s3 mb s3://raw-images-propelhq --region $REGION || true

echo "  Creating S3 bucket: processed-images-propelhq"
aws --endpoint-url=$ENDPOINT s3 mb s3://processed-images-propelhq --region $REGION || true

# ── Dead-Letter Queue ─────────────────────────────────────────────────────────
echo "  Creating DLQ: image-processing-dlq-propelhq"
DLQ_URL=$(aws --endpoint-url=$ENDPOINT sqs create-queue \
  --queue-name image-processing-dlq-propelhq \
  --region $REGION \
  --query 'QueueUrl' --output text)

DLQ_ARN=$(aws --endpoint-url=$ENDPOINT sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)

echo "  DLQ ARN: $DLQ_ARN"

# ── Main Queue (with DLQ redrive after 3 failures) ────────────────────────────
echo "  Creating main queue: image-processing-queue-propelhq"
aws --endpoint-url=$ENDPOINT sqs create-queue \
  --queue-name image-processing-queue-propelhq \
  --region $REGION \
  --attributes "{\"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"

echo "==> All resources created successfully."
import json
import logging
import time
import io
import boto3
from botocore.exceptions import ClientError
from PIL import Image, ImageDraw, ImageFont
from config import (
    AWS_REGION,
    AWS_ENDPOINT_URL,
    S3_BUCKET_RAW,
    S3_BUCKET_PROCESSED,
    SQS_QUEUE_URL,
    SQS_WAIT_TIME_SECONDS,
    SQS_MAX_MESSAGES,
    SQS_VISIBILITY_TIMEOUT,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    WATERMARK_TEXT,
    THUMBNAIL_SIZE,
)

# Structured JSON logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        return json.dumps(log_record)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.handlers = [handler]
logger.propagate = False


def get_aws_client(service):
    kwargs = {"region_name": AWS_REGION}
    if AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = AWS_ENDPOINT_URL
    return boto3.client(service, **kwargs)


def retry_with_backoff(func, max_retries=MAX_RETRIES, base_delay=RETRY_BASE_DELAY):
    """Retry a function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except ClientError as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(json.dumps({
                "event": "retry",
                "attempt": attempt + 1,
                "delay_seconds": delay,
                "error": str(e),
            }))
            time.sleep(delay)
    return None


def download_image_from_s3(s3_client, bucket, key):
    """Download image from S3 and return as bytes."""
    def _download():
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    return retry_with_backoff(_download)


def resize_and_watermark(image_bytes, size=THUMBNAIL_SIZE, watermark_text=WATERMARK_TEXT):
    """
    Resize image to max dimensions preserving aspect ratio,
    apply watermark to bottom-right corner, return PNG bytes.
    """
    img = Image.open(io.BytesIO(image_bytes))

    # Convert to RGBA for watermark support
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGB")

    # Resize preserving aspect ratio (thumbnail does this in-place)
    img.thumbnail(size)

    # Apply watermark to bottom-right corner
    draw = ImageDraw.Draw(img)

    # Try to use a basic font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except (IOError, OSError):
        font = ImageFont.load_default()

    # Calculate text bounding box
    bbox = draw.textbbox((0, 0), watermark_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    margin = 6
    x = img.width - text_width - margin
    y = img.height - text_height - margin

    # Semi-transparent shadow for readability
    draw.text((x + 1, y + 1), watermark_text, font=font, fill=(0, 0, 0, 160))
    draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, 200))

    # Save as PNG to bytes
    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output.getvalue()


def upload_image_to_s3(s3_client, bucket, key, image_bytes):
    """Upload processed image bytes to S3."""
    def _upload():
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=image_bytes,
            ContentType="image/png",
        )

    retry_with_backoff(_upload)


def process_message(message, s3_client, sqs_client):
    """
    Process a single SQS message:
    1. Parse message body
    2. Download raw image from S3
    3. Resize + watermark
    4. Upload processed image to S3
    5. Delete message from SQS
    """
    receipt_handle = message["ReceiptHandle"]

    try:
        body = json.loads(message["Body"])
        image_id = body["image_id"]
        s3_key_raw = body["s3_key_raw"]
    except (KeyError, json.JSONDecodeError) as e:
        logger.error(json.dumps({"event": "message_parse_error", "error": str(e), "body": message.get("Body")}))
        # Don't delete — let it go to DLQ after max receives
        return False

    logger.info(json.dumps({"event": "processing_start", "image_id": image_id, "s3_key_raw": s3_key_raw}))

    try:
        # Step 1: Download raw image
        image_bytes = download_image_from_s3(s3_client, S3_BUCKET_RAW, s3_key_raw)
        logger.info(json.dumps({"event": "s3_download_success", "image_id": image_id}))

        # Step 2: Resize and watermark
        processed_bytes = resize_and_watermark(image_bytes)
        logger.info(json.dumps({"event": "image_processed", "image_id": image_id}))

        # Step 3: Upload processed image
        output_key = f"{image_id}_thumbnail.png"
        upload_image_to_s3(s3_client, S3_BUCKET_PROCESSED, output_key, processed_bytes)
        logger.info(json.dumps({"event": "s3_upload_success", "image_id": image_id, "output_key": output_key}))

        # Step 4: Delete message from SQS ONLY after successful processing
        def _delete():
            sqs_client.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)

        retry_with_backoff(_delete)
        logger.info(json.dumps({"event": "message_deleted", "image_id": image_id}))

        return True

    except ClientError as e:
        logger.error(json.dumps({"event": "aws_error", "image_id": image_id, "error": str(e)}))
        return False
    except Exception as e:
        logger.error(json.dumps({"event": "processing_error", "image_id": image_id, "error": str(e)}))
        return False


def poll_queue(s3_client, sqs_client):
    """Poll SQS queue for messages and process them."""
    logger.info(json.dumps({"event": "polling", "queue_url": SQS_QUEUE_URL}))

    try:
        def _receive():
            return sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=SQS_MAX_MESSAGES,
                WaitTimeSeconds=SQS_WAIT_TIME_SECONDS,  # Long polling — avoids busy-wait
                VisibilityTimeout=SQS_VISIBILITY_TIMEOUT,
            )

        response = retry_with_backoff(_receive)
        messages = response.get("Messages", [])

        if not messages:
            logger.info(json.dumps({"event": "queue_empty"}))
            return

        for message in messages:
            process_message(message, s3_client, sqs_client)

    except ClientError as e:
        logger.error(json.dumps({"event": "sqs_poll_error", "error": str(e)}))
        time.sleep(5)


def run():
    """Main worker loop."""
    logger.info(json.dumps({"event": "worker_started", "queue": SQS_QUEUE_URL}))

    s3_client = get_aws_client("s3")
    sqs_client = get_aws_client("sqs")

    while True:
        poll_queue(s3_client, sqs_client)


if __name__ == "__main__":
    run()

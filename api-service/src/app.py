import uuid
import logging
import json
import os
import boto3
from botocore.exceptions import ClientError
from flask import Flask, request, jsonify
from config import (
    S3_BUCKET_RAW,
    S3_BUCKET_PROCESSED,
    SQS_QUEUE_URL,
    AWS_REGION,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        })

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.handlers = [handler]
logger.propagate = False

app = Flask(__name__)

PUBLIC_HOST = os.getenv("PUBLIC_HOST", "localhost")

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

def get_s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )

def get_sqs_client():
    return boto3.client(
        "sqs",
        region_name=AWS_REGION,
        endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/images/upload", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    image_file = request.files["image"]

    if image_file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(image_file.filename):
        return jsonify({"error": "Invalid image file type"}), 400

    if image_file.mimetype not in ALLOWED_MIME_TYPES:
        return jsonify({"error": "Invalid MIME type"}), 400

    image_id = str(uuid.uuid4())
    extension = image_file.filename.rsplit(".", 1)[1].lower()
    s3_key = f"original/{image_id}.{extension}"

    try:
        s3 = get_s3_client()
        sqs = get_sqs_client()

        image_file.seek(0)

        s3.upload_fileobj(
            image_file,
            S3_BUCKET_RAW,
            s3_key,
            ExtraArgs={"ContentType": image_file.mimetype},
        )

        sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps({
                "image_id": image_id,
                "s3_key_raw": s3_key
            })
        )

        return jsonify({
            "image_id": image_id,
            "message": "Image upload initiated"
        }), 202

    except Exception as e:
        logger.error(str(e))
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500

@app.route("/images/processed/<image_id>", methods=["GET"])
def get_processed_image(image_id):
    s3_key = f"{image_id}_thumbnail.png"

    try:
        s3 = get_s3_client()

        s3.head_object(Bucket=S3_BUCKET_PROCESSED, Key=s3_key)

        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_PROCESSED, "Key": s3_key},
            ExpiresIn=3600
        )

        url = url.replace("localstack", PUBLIC_HOST)

        return jsonify({
            "image_id": image_id,
            "url": url
        }), 200

    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return jsonify({"error": "Image not found"}), 404

        return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
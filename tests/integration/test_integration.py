"""
Integration tests — run with Docker services up:
  docker-compose up -d
  docker-compose exec api pytest /app/../tests/integration/ -v   (if copied in)

Or run locally with LocalStack:
  AWS_ENDPOINT_URL=http://localhost:4566 pytest tests/integration/ -v
"""
import json
import time
import uuid
import os
import boto3
import requests
import pytest
from io import BytesIO
from PIL import Image

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:5000")
AWS_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET_RAW = os.environ.get("S3_BUCKET_RAW", "raw-images-propelhq")
S3_BUCKET_PROCESSED = os.environ.get("S3_BUCKET_PROCESSED", "processed-images-propelhq")
SQS_QUEUE_URL = os.environ.get(
    "SQS_QUEUE_URL",
    "http://localhost:4566/000000000000/image-processing-queue-propelhq"
)

def get_s3():
    return boto3.client("s3", region_name=AWS_REGION,
                        endpoint_url=AWS_ENDPOINT,
                        aws_access_key_id="test",
                        aws_secret_access_key="test")


def get_sqs():
    return boto3.client("sqs", region_name=AWS_REGION,
                        endpoint_url=AWS_ENDPOINT,
                        aws_access_key_id="test",
                        aws_secret_access_key="test")


def make_test_image(width=200, height=150):
    img = Image.new("RGB", (width, height), color=(80, 130, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


@pytest.mark.integration
class TestUploadFlow:

    def test_health_endpoint(self):
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_upload_returns_202_with_image_id(self):
        image = make_test_image()
        resp = requests.post(
            f"{API_BASE}/images/upload",
            files={"image": ("test.jpg", image, "image/jpeg")},
            timeout=10,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "image_id" in data
        assert len(data["image_id"]) == 36  # UUID format

    def test_upload_invalid_type_returns_400(self):
        resp = requests.post(
            f"{API_BASE}/images/upload",
            files={"image": ("bad.txt", BytesIO(b"hello"), "text/plain")},
            timeout=10,
        )
        assert resp.status_code == 400

    def test_upload_no_file_returns_400(self):
        resp = requests.post(f"{API_BASE}/images/upload", timeout=10)
        assert resp.status_code == 400

    def test_raw_image_stored_in_s3_after_upload(self):
        image = make_test_image()
        resp = requests.post(
            f"{API_BASE}/images/upload",
            files={"image": ("test.jpg", image, "image/jpeg")},
            timeout=10,
        )
        assert resp.status_code == 202
        image_id = resp.json()["image_id"]

        s3 = get_s3()
        # Give a moment for the upload to complete
        time.sleep(1)
        objects = s3.list_objects_v2(Bucket=S3_BUCKET_RAW, Prefix=f"original/{image_id}")
        assert objects["KeyCount"] >= 1

    def test_full_pipeline_upload_to_processed(self):
        """
        Full end-to-end: upload → worker processes → GET returns presigned URL.
        Waits up to 30 seconds for the worker to finish.
        """
        image = make_test_image()
        resp = requests.post(
            f"{API_BASE}/images/upload",
            files={"image": ("test.jpg", image, "image/jpeg")},
            timeout=10,
        )
        assert resp.status_code == 202
        image_id = resp.json()["image_id"]

        # Poll for processed image (worker needs time)
        for _ in range(15):
            time.sleep(2)
            get_resp = requests.get(f"{API_BASE}/images/processed/{image_id}", timeout=10)
            if get_resp.status_code == 200:
                data = get_resp.json()
                assert "url" in data
                assert image_id in data["image_id"]
                return  # Pass

        pytest.fail("Processed image not available after 30 seconds")

    def test_get_nonexistent_image_returns_404(self):
        fake_id = str(uuid.uuid4())
        resp = requests.get(f"{API_BASE}/images/processed/{fake_id}", timeout=10)
        assert resp.status_code == 404

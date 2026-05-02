import json
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

# ── Health check ──────────────────────────────────────────────────────────────

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

# ── Upload validation ─────────────────────────────────────────────────────────

def test_upload_no_file(client):
    resp = client.post("/images/upload")
    assert resp.status_code == 400
    assert "error" in resp.json

def test_upload_invalid_type(client):
    data = {"image": (BytesIO(b"fake content"), "file.txt")}
    resp = client.post("/images/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "Invalid image file type" in resp.json["error"]

def test_upload_empty_filename(client):
    data = {"image": (BytesIO(b""), "")}
    resp = client.post("/images/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400

# ── Successful upload ─────────────────────────────────────────────────────────

@patch("app.get_sqs_client")
@patch("app.get_s3_client")
def test_upload_success(mock_s3_factory, mock_sqs_factory, client):
    mock_s3 = MagicMock()
    mock_sqs = MagicMock()
    mock_s3_factory.return_value = mock_s3
    mock_sqs_factory.return_value = mock_sqs
    mock_sqs.send_message.return_value = {"MessageId": "test-msg-id"}

    fake_image = BytesIO(b"\xff\xd8\xff" + b"\x00" * 100)  # minimal JPEG header
    data = {"image": (fake_image, "test.jpg")}
    resp = client.post("/images/upload", data=data, content_type="multipart/form-data")

    assert resp.status_code == 202
    assert "image_id" in resp.json
    assert resp.json["message"] == "Image upload initiated"
    mock_s3.upload_fileobj.assert_called_once()
    mock_sqs.send_message.assert_called_once()

    # Verify SQS message body contains required fields
    call_kwargs = mock_sqs.send_message.call_args[1]
    body = json.loads(call_kwargs["MessageBody"])
    assert "image_id" in body
    assert "s3_key_raw" in body

@patch("app.get_sqs_client")
@patch("app.get_s3_client")
def test_upload_s3_failure_returns_500(mock_s3_factory, mock_sqs_factory, client):
    from botocore.exceptions import ClientError
    mock_s3 = MagicMock()
    mock_s3_factory.return_value = mock_s3
    mock_sqs_factory.return_value = MagicMock()
    mock_s3.upload_fileobj.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "S3 error"}}, "upload_fileobj"
    )

    fake_image = BytesIO(b"\xff\xd8\xff" + b"\x00" * 100)
    data = {"image": (fake_image, "test.jpg")}
    resp = client.post("/images/upload", data=data, content_type="multipart/form-data")

    assert resp.status_code == 500

# ── GET processed image ───────────────────────────────────────────────────────

@patch("app.get_s3_client")
def test_get_processed_success(mock_s3_factory, client):
    mock_s3 = MagicMock()
    mock_s3_factory.return_value = mock_s3
    mock_s3.head_object.return_value = {}
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned-url"

    resp = client.get("/images/processed/test-uuid-1234")
    assert resp.status_code == 200
    assert "url" in resp.json
    assert resp.json["image_id"] == "test-uuid-1234"

@patch("app.get_s3_client")
def test_get_processed_not_found(mock_s3_factory, client):
    from botocore.exceptions import ClientError
    mock_s3 = MagicMock()
    mock_s3_factory.return_value = mock_s3
    mock_s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "head_object"
    )

    resp = client.get("/images/processed/nonexistent-id")
    assert resp.status_code == 404
    assert "error" in resp.json

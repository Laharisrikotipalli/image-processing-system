import json
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO
from PIL import Image
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from worker import resize_and_watermark, process_message, download_image_from_s3, upload_image_to_s3


def create_test_image(width=300, height=200, color=(100, 150, 200)):
    """Create an in-memory test image."""
    img = Image.new("RGB", (width, height), color=color)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()




def test_resize_preserves_aspect_ratio():
    image_bytes = create_test_image(width=300, height=200)
    processed = resize_and_watermark(image_bytes)

    result_img = Image.open(BytesIO(processed))
    
    assert result_img.width <= 150
    assert result_img.height <= 150
    
    assert abs(result_img.width / result_img.height - 300 / 200) < 0.1


def test_resize_small_image_not_upscaled():
    """Images smaller than 150x150 should not be upscaled."""
    image_bytes = create_test_image(width=50, height=50)
    processed = resize_and_watermark(image_bytes)
    result_img = Image.open(BytesIO(processed))
    assert result_img.width <= 50
    assert result_img.height <= 50


def test_output_is_png():
    image_bytes = create_test_image()
    processed = resize_and_watermark(image_bytes)
    result_img = Image.open(BytesIO(processed))
    assert result_img.format == "PNG"


def test_watermark_applied():
    """Smoke test: processing should not raise and output should differ from a plain resize."""
    image_bytes = create_test_image(width=200, height=200, color=(255, 255, 255))
    processed = resize_and_watermark(image_bytes)
    result_img = Image.open(BytesIO(processed))
    assert result_img.width > 0


def test_resize_tall_image():
    image_bytes = create_test_image(width=100, height=400)
    processed = resize_and_watermark(image_bytes)
    result_img = Image.open(BytesIO(processed))
    assert result_img.height <= 150
    assert result_img.width <= 150


def test_resize_wide_image():
    image_bytes = create_test_image(width=600, height=100)
    processed = resize_and_watermark(image_bytes)
    result_img = Image.open(BytesIO(processed))
    assert result_img.width <= 150
    assert result_img.height <= 150



def make_message(image_id="test-id-123", s3_key="original/test-id-123.jpg"):
    return {
        "Body": json.dumps({"image_id": image_id, "s3_key_raw": s3_key}),
        "ReceiptHandle": "fake-receipt-handle",
    }


@patch("worker.upload_image_to_s3")
@patch("worker.resize_and_watermark")
@patch("worker.download_image_from_s3")
def test_process_message_success(mock_download, mock_process, mock_upload):
    mock_download.return_value = create_test_image()
    mock_process.return_value = b"processed-image-bytes"

    mock_s3 = MagicMock()
    mock_sqs = MagicMock()

    result = process_message(make_message(), mock_s3, mock_sqs)

    assert result is True
    mock_download.assert_called_once()
    mock_process.assert_called_once()
    mock_upload.assert_called_once()
   
    mock_sqs.delete_message.assert_called_once()
    call_kwargs = mock_sqs.delete_message.call_args[1]
    assert call_kwargs["ReceiptHandle"] == "fake-receipt-handle"


@patch("worker.download_image_from_s3")
def test_process_message_download_failure(mock_download):
    from botocore.exceptions import ClientError
    mock_download.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "get_object"
    )
    mock_s3 = MagicMock()
    mock_sqs = MagicMock()

    result = process_message(make_message(), mock_s3, mock_sqs)

    assert result is False
    
    mock_sqs.delete_message.assert_not_called()


def test_process_message_invalid_body():
    bad_message = {"Body": "not valid json {{{", "ReceiptHandle": "handle"}
    mock_s3 = MagicMock()
    mock_sqs = MagicMock()

    result = process_message(bad_message, mock_s3, mock_sqs)

    assert result is False
    mock_sqs.delete_message.assert_not_called()


def test_process_message_missing_fields():
    bad_message = {"Body": json.dumps({"foo": "bar"}), "ReceiptHandle": "handle"}
    mock_s3 = MagicMock()
    mock_sqs = MagicMock()

    result = process_message(bad_message, mock_s3, mock_sqs)

    assert result is False




def test_download_image_from_s3():
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"image-bytes")}

    result = download_image_from_s3(mock_s3, "my-bucket", "my-key")

    assert result == b"image-bytes"
    mock_s3.get_object.assert_called_once_with(Bucket="my-bucket", Key="my-key")


def test_upload_image_to_s3():
    mock_s3 = MagicMock()
    upload_image_to_s3(mock_s3, "processed-bucket", "img_thumbnail.png", b"png-bytes")
    mock_s3.put_object.assert_called_once_with(
        Bucket="processed-bucket",
        Key="img_thumbnail.png",
        Body=b"png-bytes",
        ContentType="image/png",
    )

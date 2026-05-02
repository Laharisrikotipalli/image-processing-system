# PropelHQ Image Processing Service

An event-driven image processing system built with Flask, AWS S3, AWS SQS, and Docker.

## Architecture

![Architecture Diagram](./docs/architecture.png)

```
Client → POST /images/upload → API Service → S3 (raw) + SQS message
                                                          ↓
                                              Worker polls SQS
                                              Downloads raw image
                                              Resizes to 150×150
                                              Adds "PropelHQ" watermark
                                              Uploads to S3 (processed)
                                              Deletes SQS message
Client → GET /images/processed/{id} → API Service → pre-signed URL
```

---

## Features

* Event-driven architecture using SQS
* Asynchronous image processing
* Image resizing (150×150 with aspect ratio)
* Watermarking with "PropelHQ"
* Fault-tolerant worker with retry logic
* Dead Letter Queue (DLQ) support
* Local AWS simulation using LocalStack
* Fully containerized using Docker
* Unit and integration testing

---

## Quick Start (Local — Docker)

### Prerequisites

* Docker & Docker Compose installed
* Port 5000 and 4566 free on your machine

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd propelhq-image-service

cp .env.example .env
# Edit .env if you want to change bucket/queue names (defaults work for local dev)
```

### 2. Start all services

```bash
docker-compose up --build
```

This starts:

* **LocalStack** on port 4566 (simulates S3 + SQS)
* **API Service** on port 5000
* **Worker Service** (background, polls SQS)

LocalStack auto-creates the S3 buckets and SQS queues via `init-localstack.sh`.

### 3. Test the upload flow

**Upload an image:**

```bash
curl -X POST http://localhost:5000/images/upload \
  -F "image=@/path/to/your/image.jpg" \
  -H "Accept: application/json"
```

Response:

```json
{
  "image_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Image upload initiated"
}
```

**Wait a few seconds for the worker to process it, then retrieve:**

```bash
curl http://localhost:5000/images/processed/550e8400-e29b-41d4-a716-446655440000
```

Response:

```json
{
  "image_id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "http://localhost:4566/processed-images-propelhq/550e8400...thumbnail.png?..."
}
```

---

## API Documentation

### POST /images/upload

Upload a raw image for async processing.

**Request**

* Content-Type: `multipart/form-data`
* Field: `image` — the image file (JPEG, PNG, GIF, WebP, BMP)

**Responses**

| Code | Description                                                                       |
| ---- | --------------------------------------------------------------------------------- |
| 202  | Accepted. Returns `{ "image_id": "<uuid>", "message": "Image upload initiated" }` |
| 400  | Bad request. Missing file, invalid file type.                                     |
| 500  | Internal server error.                                                            |

**Example:**

```bash
curl -X POST http://localhost:5000/images/upload \
  -F "image=@photo.jpg"
```

---

### GET /images/processed/{image_id}

Retrieve the processed (resized + watermarked) thumbnail.

**Path parameter:** `image_id` — UUID returned from the upload endpoint.

**Responses**

| Code | Description                                                                         |
| ---- | ----------------------------------------------------------------------------------- |
| 200  | Returns `{ "image_id": "...", "url": "<presigned-s3-url>" }` (URL valid for 1 hour) |
| 404  | Image not yet processed or does not exist.                                          |
| 500  | Internal server error.                                                              |

**Example:**

```bash
curl http://localhost:5000/images/processed/550e8400-e29b-41d4-a716-446655440000
```

---

### GET /health

Health check endpoint.

**Response:** `200 OK` — `{ "status": "ok" }`

---

## Running Tests

### Unit tests — API service

```bash
cd api-service
pip install -r src/requirements.txt pytest
pytest tests/ -v
```

### Unit tests — Worker service

```bash
cd worker-service
pip install -r src/requirements.txt pytest Pillow
pytest tests/ -v
```

### Integration tests (requires services running)

```bash
# Start services first
docker-compose up -d

# Run integration tests
pip install requests pytest Pillow
pytest tests/integration/ -v --integration
```

### Run all unit tests via Docker

```bash
docker-compose exec api pytest /app/../tests/ -v
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable                | Default                           | Description                                 |
| ----------------------- | --------------------------------- | ------------------------------------------- |
| `AWS_ACCESS_KEY_ID`     | `test`                            | AWS key (use `test` for LocalStack)         |
| `AWS_SECRET_ACCESS_KEY` | `test`                            | AWS secret (use `test` for LocalStack)      |
| `AWS_REGION`            | `us-east-1`                       | AWS region                                  |
| `AWS_ENDPOINT_URL`      | `http://localstack:4566`          | Override for LocalStack; empty for real AWS |
| `S3_BUCKET_RAW`         | `raw-images-propelhq`             | S3 bucket for raw uploads                   |
| `S3_BUCKET_PROCESSED`   | `processed-images-propelhq`       | S3 bucket for processed thumbnails          |
| `SQS_QUEUE_NAME`        | `image-processing-queue-propelhq` | Main processing queue name                  |
| `SQS_DLQ_NAME`          | `image-processing-dlq-propelhq`   | Dead-letter queue name                      |
| `SQS_QUEUE_URL`         | LocalStack URL                    | Full SQS queue URL                          |
| `WATERMARK_TEXT`        | `PropelHQ`                        | Text applied as watermark                   |

---

## CI/CD Pipeline

This project uses GitHub Actions for continuous integration and deployment.

Pipeline includes:

* Running API unit tests
* Running Worker unit tests
* Running integration tests using LocalStack
* Building Docker images
* Optional Docker Hub push

Workflow file:
.github/workflows/ci-cd.yml

---

## Project Structure

```
propelhq-image-service/
├── api-service/
├── worker-service/
├── tests/
│   └── integration/
├── docs/
│   └── architecture.png
├── init-localstack.sh
├── docker-compose.yml
├── .env.example
├── ARCHITECTURE.md
├── .github/workflows/ci-cd.yml
└── README.md
```


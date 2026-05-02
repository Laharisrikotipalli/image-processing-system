# PropelHQ Image Processing Service

An event-driven image processing system built with Flask, AWS S3, AWS SQS, and Docker. The system demonstrates a scalable, asynchronous microservice architecture for handling image uploads and processing.

---

## Architecture

![Architecture Diagram](./docs/architecture.png)

Client → POST /images/upload → API Service → S3 (raw) + SQS message  
→ Worker polls SQS  
→ Downloads raw image  
→ Resizes to 150×150 (preserving aspect ratio)  
→ Adds watermark  
→ Uploads to S3 (processed)  
→ Deletes SQS message  

Client → GET /images/processed/{id} → API Service → pre-signed URL

---

## Project Structure
```
propelhq-image-service/  
├── api-service/  
├── worker-service/  
├── tests/  
│   └── integration/  
├── scripts/  
│   └── init.py  
├── docs/  
│   └── architecture.png  
├── docker-compose.yml  
├── .env.example  
├── .github/workflows/  
│   └── ci-cd.yml  
└── README.md  
```
---

## Features

- Event-driven architecture using SQS  
- Asynchronous image processing pipeline  
- Image resizing (150×150 with aspect ratio preserved)  
- Optional watermark support  
- Retry handling with Dead Letter Queue (DLQ)  
- Local AWS simulation using LocalStack  
- Fully containerized with Docker  
- Unit and integration testing  

---

## Quick Start (Local Setup)

### Prerequisites

- Docker installed  
- Docker Compose available  
- Ports 5000 and 4566 available  

---

### 1. Clone the repository
```
git clone <your-repo-url>
```
```
cd propelhq-image-service
```
```
cp .env.example .env
```
---

### 2. Start services
```
docker compose up --build
```

This starts:

- LocalStack (S3 and SQS simulation)  
- API service on port 5000  
- Worker service for background processing  

---

### 3. Upload an image
```
curl -X POST http://localhost:5000/images/upload -F "image=@test.jpg"  
```
Response:
```
{
  "image_id": "uuid",
  "message": "Image upload initiated"
}
```
---

### 4. Retrieve processed image
```
curl http://localhost:5000/images/processed/<image_id>  
```
---

## API Endpoints

### POST /images/upload

Uploads an image for asynchronous processing.

- Content-Type: multipart/form-data  
- Supported formats: JPEG, PNG  

| Status | Description |
|--------|------------|
| 202    | Accepted   |
| 400    | Invalid request |
| 500    | Server error |

---

### GET /images/processed/{image_id}

Returns a pre-signed URL for the processed image.

| Status | Description |
|--------|------------|
| 200    | Success    |
| 404    | Not found  |
| 500    | Error      |

---

### GET /health
```
{ "status": "ok" }
```
---

## Running Tests

### API Unit Tests
```
cd api-service
```
```
pip install -r src/requirements.txt pytest
```
``` 
pytest tests -v
```

---

### Worker Unit Tests
```
cd worker-service
```
``` 
pip install -r src/requirements.txt pytest Pillow
```
```
pytest tests -v
```

---

### Integration Tests
```
docker compose up -d  
```
```
pip install requests pytest pillow boto3
```
```
pytest tests/integration -v --integration
```

---

## Environment Variables

| Variable | Default |
|----------|--------|
| AWS_ACCESS_KEY_ID | test |
| AWS_SECRET_ACCESS_KEY | test |
| AWS_REGION | us-east-1 |
| AWS_ENDPOINT_URL | http://localstack:4566 |
| S3_BUCKET_RAW | raw-images-propelhq |
| S3_BUCKET_PROCESSED | processed-images-propelhq |
| SQS_QUEUE_URL | LocalStack URL |
| WATERMARK_TEXT | PropelHQ |

---

## CI/CD Pipeline

The GitHub Actions pipeline includes:

- API unit tests  
- Worker unit tests  
- Integration tests using LocalStack  
- Docker image build  
```
.github/workflows/ci-cd.yml  
```
---

## Summary

This project demonstrates a production-style backend system using microservices, asynchronous processing with message queues, and cloud service simulation for local development.

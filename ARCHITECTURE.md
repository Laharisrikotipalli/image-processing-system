# Architecture Overview

## System Design

This system implements an event-driven, asynchronous image processing pipeline using AWS S3 and SQS.

```
Client
  │
  │  POST /images/upload (multipart/form-data)
  ▼
┌─────────────────┐
│   API Service   │  (Flask/Gunicorn — port 5000)
│                 │
│ 1. Validate     │
│ 2. Upload raw   │──────────► S3: raw-images
│ 3. Enqueue      │──────────► SQS: image-processing-queue
│ 4. Return 202   │
└─────────────────┘
                              │
                              │ (async)
                              ▼
                   ┌─────────────────────┐
                   │   Worker Service    │  (long-running Python process)
                   │                    │
                   │ 1. Poll SQS         │◄──── SQS queue
                   │ 2. Download raw     │◄──── S3: raw-images
                   │ 3. Resize 150x150   │
                   │ 4. Watermark        │
                   │ 5. Upload processed │────► S3: processed-images
                   │ 6. Delete message   │────► SQS (delete on success)
                   └─────────────────────┘
                              │
                   Failed messages (after 3 attempts)
                              │
                              ▼
                   ┌─────────────────────┐
                   │        DLQ          │
                   │ image-processing-   │
                   │ dlq-<yourid>        │
                   └─────────────────────┘

Client
  │
  │  GET /images/processed/{image_id}
  ▼
┌─────────────────┐
│   API Service   │
│                 │
│ 1. Check S3     │──────────► S3: processed-images
│ 2. Pre-sign URL │
│ 3. Return JSON  │
└─────────────────┘
```

## Key Design Decisions

### Event-Driven Architecture
The API never processes images synchronously. It uploads to S3, enqueues a message, and immediately returns `202 Accepted`. This keeps the API fast and responsive regardless of image processing time.

### Decoupled Services
The API and Worker communicate exclusively through SQS and S3. There are no direct network calls between them. This means:
- Either service can restart independently
- The worker can be scaled horizontally
- The queue acts as a buffer during traffic spikes

### Idempotent Worker
The worker is designed so that processing the same message twice produces the same result. SQS guarantees "at least once" delivery, so idempotency is critical. The worker:
- Uses the `image_id` as the S3 key, so re-uploading overwrites with the same result
- Only deletes the SQS message after a successful S3 upload

### Dead-Letter Queue
Messages that fail processing after 3 attempts are moved to the DLQ automatically by SQS. The DLQ allows:
- Inspection of failed messages for debugging
- Manual re-processing after fixes
- Alerting on DLQ depth (can be wired to CloudWatch)

### Exponential Backoff
All S3 and SQS operations retry with exponential backoff (1s, 2s, 4s) to handle transient AWS errors gracefully.

### Long Polling
The worker uses SQS long polling (`WaitTimeSeconds=20`) to avoid a busy-wait loop. When the queue is empty, the receive call blocks for up to 20 seconds before returning — saving CPU and API call costs.

## Local Development

Uses LocalStack to simulate S3 and SQS locally. All AWS SDK calls are redirected to `http://localstack:4566` via the `AWS_ENDPOINT_URL` environment variable.

## Structured Logging

Both services emit JSON-formatted logs for easy ingestion by log aggregation tools (CloudWatch, Datadog, etc.). Every log line includes `level`, `message`, and contextual fields like `image_id` and `event`.

# AWS S3 Storage Integration

## Purpose

S3 is used for **persistent file storage** of user-uploaded content (avatars, documents).  Files are stored in an S3 bucket and served via public or presigned URLs.

---

## Architecture Overview

```
Client → POST /users/{id}/profile/avatar (multipart upload)
           └── UserService.upload_avatar()
                   └── S3Service.upload_file(file_obj, path, content_type)
                           └── boto3 s3_client.upload_fileobj()
                                   → Returns public URL
                                   → URL saved to UserProfile.avatar_url
```

All S3 logic lives in **`app/services/s3_service.py`**.  The service is instantiated per-request so credential rotation is picked up automatically.

---

## Implementation Details

### Client Initialisation

```python
self.s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=self.region,
    config=Config(
        signature_version="s3v4",
        retries={"max_attempts": 3, "mode": "adaptive"},
    ),
)
```

Key features:
- **Signature V4** — required by all modern AWS regions
- **Adaptive retries** — boto3 automatically retries failed requests with exponential backoff (up to 3 attempts)

### Content-Type Validation

Uploads are validated against an allow-list before being sent to S3:

```python
ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf", "text/plain",
}
```

Rejected content types return an empty string and log a warning.

### Available Operations

| Method | Description |
|---|---|
| `upload_file(file_obj, path, content_type)` | Upload and return public URL |
| `generate_presigned_url(path, expiration)` | Time-limited download URL for private objects |
| `delete_file(path)` | Delete an object from the bucket |

---

## Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | `None` | IAM access key |
| `AWS_SECRET_ACCESS_KEY` | `None` | IAM secret key |
| `AWS_REGION` | `None` | AWS region (e.g. `us-east-1`) |
| `AWS_S3_BUCKET` | `None` | S3 bucket name |

When credentials are `None`, the service initialises with `s3_client = None` and all operations return empty values gracefully.

---

## Interaction with Other Systems

- **UserService** — `upload_avatar()` calls `S3Service.upload_file()` and saves the returned URL to the database
- **Database** — `UserProfile.avatar_url` stores the S3 public URL
- **Redis** — profile cache is invalidated after avatar upload

---

## Error Handling Strategy

| Error | Handling |
|---|---|
| Missing credentials | `s3_client = None`, methods return `""` / `False` with warning log |
| Invalid content type | Rejected before upload, returns `""` |
| `NoCredentialsError` | Caught, logged, returns `""` |
| `ClientError` (boto3) | Caught, logged with error details, returns `""` / `False` |
| Network errors | Handled by boto3's adaptive retry (3 attempts) |

---

## Production Considerations

- **IAM roles** — on EC2/ECS, use IAM instance roles instead of static keys.  boto3 will auto-discover them
- **Bucket policies** — restrict public access to only the `avatars/` prefix if using public URLs
- **Presigned URLs** — prefer these over public URLs for sensitive documents
- **File size limits** — enforce max upload size in the API layer (e.g. FastAPI's `UploadFile` size limits or middleware)
- **CDN** — put CloudFront in front of S3 for better latency and caching

---

## Example Flow

1. User sends `PUT /doit/v1/users/42/profile/avatar` with a JPEG file
2. `UserService.upload_avatar()` validates ownership
3. `S3Service()` is instantiated (picks up current credentials)
4. Content type `image/jpeg` passes validation
5. `upload_fileobj()` sends the file to `avatars/42/photo.jpg` in the bucket
6. Returns URL: `https://my-bucket.s3.us-east-1.amazonaws.com/avatars/42/photo.jpg`
7. URL is saved to `UserProfile.avatar_url`
8. Redis profile cache is invalidated

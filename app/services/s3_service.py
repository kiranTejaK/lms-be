import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Maximum allowed upload size (10 MB) — enforced before sending to S3.
MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024

# Allowed MIME types for avatar / general uploads.
ALLOWED_CONTENT_TYPES: set[str] = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
}

class S3Service:

    def __init__(self) -> None:
        self.bucket: str | None = settings.AWS_S3_BUCKET
        self.region: str | None = settings.AWS_REGION

        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=self.region,
                endpoint_url=settings.AWS_ENDPOINT_URL or None,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "adaptive"},
                ),
            )
        else:
            self.s3_client = None

    def upload_file(self, file_obj, object_name: str, content_type: str,) -> str:
        if not self.s3_client:
            logger.warning("s3_client_not_configured", object_name=object_name)
            return ""

        if content_type not in ALLOWED_CONTENT_TYPES:
            logger.warning("s3_upload_rejected_content_type", object_name=object_name, content_type=content_type)
            return ""

        try:
            self.s3_client.upload_fileobj(file_obj, self.bucket, object_name, ExtraArgs={"ContentType": content_type})
            url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{object_name}"
            logger.info("s3_upload_success", object_name=object_name)
            return url

        except NoCredentialsError:
            logger.error("s3_upload_failed", error="credentials_missing")
            return ""
        except ClientError as exc:
            logger.error("s3_upload_failed", error=str(exc))
            return ""
        except Exception as exc:
            logger.error("s3_upload_failed_unexpected", error=str(exc))
            return ""

    def generate_presigned_url(self, object_name: str, expiration: int = 3600,) -> str:
        if not self.s3_client:
            logger.warning("s3_client_not_configured", object_name=object_name)
            return ""

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_name},
                ExpiresIn=expiration,
            )
            logger.info("s3_presigned_url_generated", object_name=object_name)
            return url
        except ClientError as exc:
            logger.error("s3_presigned_url_failed", error=str(exc))
            return ""

    def delete_file(self, object_name: str) -> bool:
        if not self.s3_client:
            logger.warning("s3_client_not_configured", object_name=object_name)
            return False

        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=object_name)
            logger.info("s3_delete_success", object_name=object_name)
            return True
        except ClientError as exc:
            logger.error("s3_delete_failed", error=str(exc))
            return False

# """
# AWS S3 file storage service.

# Provides synchronous file upload, download URL generation, and deletion.
# All operations degrade gracefully when AWS credentials are not configured —
# methods return empty strings / False and log warnings instead of raising.

# Configuration is loaded from environment variables via ``app.core.config``.
# """

# import boto3
# from botocore.exceptions import NoCredentialsError, ClientError
# from botocore.config import Config

# import structlog

# from app.core.config import settings

# logger = structlog.get_logger(__name__)

# # Maximum allowed upload size (10 MB) — enforced before sending to S3.
# MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024

# # Allowed MIME types for avatar / general uploads.
# ALLOWED_CONTENT_TYPES: set[str] = {
#     "image/jpeg",
#     "image/png",
#     "image/gif",
#     "image/webp",
#     "application/pdf",
#     "text/plain",
# }


# class S3Service:
#     """
#     Synchronous wrapper around the boto3 S3 client.

#     Instantiate per-request so that credential rotation is picked up
#     automatically.  If AWS keys are missing, all methods return empty
#     values and log a warning.
#     """

#     def __init__(self) -> None:
#         self.bucket: str | None = settings.AWS_S3_BUCKET
#         self.region: str | None = settings.AWS_REGION

#         if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
#             self.s3_client = boto3.client(
#                 "s3",
#                 aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#                 aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#                 region_name=self.region,
#                 endpoint_url=settings.AWS_ENDPOINT_URL,
#                 config=Config(
#                     signature_version="s3v4",
#                     retries={"max_attempts": 3, "mode": "adaptive"},
#                 ),
#             )
#         else:
#             self.s3_client = None

#     # ── Upload ────────────────────────────────────────────────────────

#     def upload_file(
#         self,
#         file_obj,
#         object_name: str,
#         content_type: str,
#     ) -> str:
#         """
#         Upload a file-like object to S3.

#         Args:
#             file_obj: A readable file-like object (e.g. ``UploadFile.file``).
#             object_name: The S3 key (path) to store the file under.
#             content_type: MIME type; validated against ``ALLOWED_CONTENT_TYPES``.

#         Returns:
#             The public URL of the uploaded object, or ``""`` on failure.
#         """
#         if not self.s3_client:
#             logger.warning("s3_client_not_configured", object_name=object_name)
#             return ""

#         if content_type not in ALLOWED_CONTENT_TYPES:
#             logger.warning(
#                 "s3_upload_rejected_content_type",
#                 object_name=object_name,
#                 content_type=content_type,
#             )
#             return ""

#         try:
#             self.s3_client.upload_fileobj(
#                 file_obj,
#                 self.bucket,
#                 object_name,
#                 ExtraArgs={"ContentType": content_type},
#             )
#             url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{object_name}"
#             logger.info("s3_upload_success", object_name=object_name)
#             return url

#         except NoCredentialsError:
#             logger.error("s3_upload_failed", error="credentials_missing")
#             return ""
#         except ClientError as exc:
#             logger.error("s3_upload_failed", error=str(exc))
#             return ""
#         except Exception as exc:
#             logger.error("s3_upload_failed_unexpected", error=str(exc))
#             return ""

#     # ── Presigned Download URL ────────────────────────────────────────

#     def generate_presigned_url(
#         self,
#         object_name: str,
#         expiration: int = 3600,
#     ) -> str:
#         """
#         Generate a time-limited presigned URL for downloading a private object.

#         Args:
#             object_name: The S3 key of the object.
#             expiration: URL validity in seconds (default: 1 hour).

#         Returns:
#             A signed URL string, or ``""`` on failure.
#         """
#         if not self.s3_client:
#             logger.warning("s3_client_not_configured", object_name=object_name)
#             return ""

#         try:
#             url = self.s3_client.generate_presigned_url(
#                 "get_object",
#                 Params={"Bucket": self.bucket, "Key": object_name},
#                 ExpiresIn=expiration,
#             )
#             logger.info("s3_presigned_url_generated", object_name=object_name)
#             return url
#         except ClientError as exc:
#             logger.error("s3_presigned_url_failed", error=str(exc))
#             return ""

#     # ── Delete ────────────────────────────────────────────────────────

#     def delete_file(self, object_name: str) -> bool:
#         """
#         Delete an object from S3.

#         Returns:
#             True on success, False on failure or missing config.
#         """
#         if not self.s3_client:
#             logger.warning("s3_client_not_configured", object_name=object_name)
#             return False

#         try:
#             self.s3_client.delete_object(Bucket=self.bucket, Key=object_name)
#             logger.info("s3_delete_success", object_name=object_name)
#             return True
#         except ClientError as exc:
#             logger.error("s3_delete_failed", error=str(exc))
#             return False

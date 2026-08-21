from io import BytesIO
from pathlib import Path

from minio import Minio

from app.core.config import Settings, get_settings


class StorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = Minio(
            self.settings.minio_endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.settings.minio_bucket):
            self.client.make_bucket(self.settings.minio_bucket)

    def upload_file(self, object_key: str, path: Path, content_type: str) -> None:
        self.client.fput_object(
            self.settings.minio_bucket,
            object_key,
            str(path),
            content_type=content_type,
        )

    def download_file(self, object_key: str, path: Path) -> None:
        self.client.fget_object(self.settings.minio_bucket, object_key, str(path))

    def put_bytes(self, object_key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(
            self.settings.minio_bucket,
            object_key,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )

    def get_bytes(self, object_key: str) -> bytes:
        response = self.client.get_object(self.settings.minio_bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def check_connection(self) -> bool:
        try:
            self.client.bucket_exists(self.settings.minio_bucket)
            return True
        except Exception:
            return False

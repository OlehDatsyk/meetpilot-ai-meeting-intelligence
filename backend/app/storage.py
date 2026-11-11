"""Storage abstraction for private files (recordings and generated reports).

`local` keeps files under STORAGE_ROOT; `s3` uses any S3-compatible bucket, which must be private.
Files are only reachable through authorised API endpoints or short-lived pre-signed URLs.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from .config import Settings, get_settings

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]{0,400}$")


def _check_key(key: str) -> str:
    if not _SAFE_KEY.match(key) or ".." in key or key.startswith("/"):
        raise ValueError("Invalid storage key")
    return key


class StorageError(Exception):
    pass


class Storage(ABC):
    name: str

    @abstractmethod
    def save_file(self, key: str, src_path: str, content_type: str) -> None: ...

    @abstractmethod
    def save_bytes(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def read_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    @abstractmethod
    @contextlib.contextmanager
    def local_copy(self, key: str) -> Iterator[str]:
        """Yield a local filesystem path for processing; temporary copies are removed afterwards."""

    def local_path(self, key: str) -> str | None:
        """Direct path for streaming with range support (local storage only)."""
        return None

    def presigned_url(self, key: str, content_type: str, seconds: int = 900) -> str | None:
        return None

    def check(self) -> None:
        """Raise StorageError if the backend is unusable (used by the readiness probe)."""


class LocalStorage(Storage):
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / _check_key(key)).resolve()
        if self.root not in p.parents:
            raise ValueError("Invalid storage key")
        return p

    def save_file(self, key: str, src_path: str, content_type: str) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copyfile(src_path, tmp)
        os.replace(tmp, dest)

    def save_bytes(self, key: str, data: bytes, content_type: str) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, dest)

    def read_bytes(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as e:
            raise StorageError("File is no longer available in storage.") from e

    def delete(self, key: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path(key).unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    @contextlib.contextmanager
    def local_copy(self, key: str) -> Iterator[str]:
        p = self._path(key)
        if not p.is_file():
            raise StorageError("The recording file is no longer available in storage.")
        yield str(p)

    def local_path(self, key: str) -> str | None:
        p = self._path(key)
        return str(p) if p.is_file() else None

    def check(self) -> None:
        if not os.access(self.root, os.W_OK):
            raise StorageError("Storage directory is not writable.")


class S3Storage(Storage):
    name = "s3"

    def __init__(self, s: Settings, client=None) -> None:
        if not s.s3_bucket:
            raise StorageError("S3_BUCKET is required when STORAGE_PROVIDER=s3.")
        self.bucket = s.s3_bucket
        self.prefix = s.s3_prefix
        if client is None:
            import boto3
            client = boto3.client("s3", region_name=s.s3_region or None, endpoint_url=s.s3_endpoint_url or None,
                                  aws_access_key_id=s.s3_access_key_id or None,
                                  aws_secret_access_key=s.s3_secret_access_key or None)
        self.client = client

    def _k(self, key: str) -> str:
        return self.prefix + _check_key(key)

    def save_file(self, key: str, src_path: str, content_type: str) -> None:
        self.client.upload_file(src_path, self.bucket, self._k(key), ExtraArgs={"ContentType": content_type})

    def save_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._k(key), Body=data, ContentType=content_type)

    def read_bytes(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()
        except Exception as e:  # botocore raises many types
            raise StorageError("File is no longer available in storage.") from e

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._k(key))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except Exception:
            return False

    def size(self, key: str) -> int:
        return int(self.client.head_object(Bucket=self.bucket, Key=self._k(key))["ContentLength"])

    @contextlib.contextmanager
    def local_copy(self, key: str) -> Iterator[str]:
        suffix = Path(key).suffix
        fd, path = tempfile.mkstemp(prefix="meetpilot-", suffix=suffix)
        os.close(fd)
        try:
            try:
                self.client.download_file(self.bucket, self._k(key), path)
            except Exception as e:
                raise StorageError("The recording file could not be downloaded from storage.") from e
            yield path
        finally:
            with contextlib.suppress(OSError):
                os.remove(path)

    def presigned_url(self, key: str, content_type: str, seconds: int = 900) -> str | None:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": self._k(key), "ResponseContentType": content_type},
            ExpiresIn=seconds)

    def check(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception as e:
            raise StorageError("S3 bucket is not reachable.") from e


_override: Storage | None = None


def set_storage_override(storage: Storage | None) -> None:
    global _override
    _override = storage
    _cached_storage.cache_clear()


@lru_cache
def _cached_storage() -> Storage:
    s = get_settings()
    if s.storage_provider == "s3":
        return S3Storage(s)
    return LocalStorage(s.storage_root)


def get_storage() -> Storage:
    return _override or _cached_storage()

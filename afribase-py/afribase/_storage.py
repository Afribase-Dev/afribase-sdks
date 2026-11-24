"""AfribaseStorageClient — file uploads, downloads, and bucket management."""

from __future__ import annotations

from dataclasses import asdict
from typing import IO, Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote, urlencode

from afribase._http import HeadersMixin, handle_response, normalize_error

FileBody = Union[bytes, bytearray, str, IO[bytes]]


def _body_bytes(file: FileBody) -> bytes:
    if isinstance(file, (bytes, bytearray)):
        return bytes(file)
    if isinstance(file, str):
        return file.encode("utf-8")
    data = file.read()  # a binary file object
    return data.encode("utf-8") if isinstance(data, str) else bytes(data)


def _transform_pairs(transform: Optional[TransformOptions]) -> List[Tuple[str, str]]:
    if not transform:
        return []
    pairs: List[Tuple[str, str]] = []
    for name in ("width", "height", "resize", "quality", "format"):
        v = getattr(transform, name)
        if v:
            pairs.append((name, str(v)))
    return pairs


def _uploaded(bucket: str, path: str, data: Any) -> Dict[str, Any]:
    d = data if isinstance(data, dict) else {}
    return {"path": path, "id": d.get("id") or d.get("Key"), "fullPath": f"{bucket}/{path}"}
from afribase._types import SignedUrlOptions, TransformOptions, UploadOptions


class StorageFileApi(HeadersMixin):
    """Operations on a specific storage bucket."""

    def __init__(
        self,
        storage_url: str,
        bucket_id: str,
        api_key: str,
        get_access_token: Any,
    ) -> None:
        self._url = storage_url
        self._bucket = bucket_id
        self._api_key = api_key
        self._get_token = get_access_token

    # ─── Upload / Update ──────────────────────────────────────────────

    def upload(
        self,
        path: str,
        file: FileBody,
        options: Optional[UploadOptions] = None,
    ) -> Dict[str, Any]:
        """Upload a file (bytes, str or a binary file object)."""
        opts = options or UploadOptions()
        headers: Dict[str, str] = {
            "Content-Type": opts.content_type or "application/octet-stream",
        }
        if opts.cache_control:
            headers["Cache-Control"] = opts.cache_control
        if opts.upsert:
            headers["x-upsert"] = "true"

        body = _body_bytes(file)
        resp = self._sync(
            f"{self._url}/object/{self._bucket}/{path}",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            headers=headers,
            body=body,
        )
        result = handle_response(resp)
        if result["error"]:
            return result
        return {"data": _uploaded(self._bucket, path, result["data"]), "error": None}

    def update(
        self,
        path: str,
        file: FileBody,
        options: Optional[UploadOptions] = None,
    ) -> Dict[str, Any]:
        """Update (overwrite) a file: POST with x-upsert, like the JS SDK."""
        opts = options or UploadOptions()
        headers: Dict[str, str] = {
            "Content-Type": opts.content_type or "application/octet-stream",
            "x-upsert": "true",
        }
        if opts.cache_control:
            headers["Cache-Control"] = opts.cache_control

        body = _body_bytes(file)
        resp = self._sync(
            f"{self._url}/object/{self._bucket}/{path}",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            headers=headers,
            body=body,
        )
        result = handle_response(resp)
        if result["error"]:
            return result
        return {"data": _uploaded(self._bucket, path, result["data"]), "error": None}

    # ─── Download ─────────────────────────────────────────────────────

    def download(self, path: str, *, transform: Optional[TransformOptions] = None) -> Dict[str, Any]:
        """Download a file as bytes, optionally transformed (images)."""
        qs = urlencode(_transform_pairs(transform))
        resp = self._sync(
            f"{self._url}/object/{self._bucket}/{path}" + (f"?{qs}" if qs else ""),
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        if resp.status_code >= 400:
            return {"data": None, "error": normalize_error(resp, f"Download failed with status {resp.status_code}")}
        return {"data": resp.content, "error": None}

    # ─── List / Remove ────────────────────────────────────────────────

    def list(
        self,
        path: str = "",
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """List files in a path (limit/offset/sort only sent when given, like JS)."""
        body: Dict[str, Any] = {"prefix": path}
        if limit is not None:
            body["limit"] = limit
        if offset is not None:
            body["offset"] = offset
        if sort_by:
            body["sortBy"] = sort_by
        resp = self._sync(
            f"{self._url}/object/list/{self._bucket}",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json=body,
        )
        return handle_response(resp)

    def remove(self, paths: List[str]) -> Dict[str, Any]:
        """Delete one or more files."""
        resp = self._sync(
            f"{self._url}/object/{self._bucket}",
            method="DELETE",
            api_key=self._api_key,
            access_token=self._get_token(),
            json={"prefixes": paths},
        )
        return handle_response(resp)

    def move(self, from_path: str, to_path: str) -> Dict[str, Any]:
        """Move a file."""
        resp = self._sync(
            f"{self._url}/object/move",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json={
                "bucketId": self._bucket,
                "sourceKey": from_path,
                "destinationKey": to_path,
            },
        )
        return handle_response(resp)

    def copy(self, from_path: str, to_path: str) -> Dict[str, Any]:
        """Copy a file."""
        resp = self._sync(
            f"{self._url}/object/copy",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json={
                "bucketId": self._bucket,
                "sourceKey": from_path,
                "destinationKey": to_path,
            },
        )
        return handle_response(resp)

    # ─── Signed URLs ──────────────────────────────────────────────────

    def _absolute(self, signed: Optional[str]) -> str:
        signed = signed or ""
        return signed if signed.startswith("http") else f"{self._url}{signed}"

    def create_signed_url(
        self, path: str, expires_in: int, options: Optional[SignedUrlOptions] = None,
    ) -> Dict[str, Any]:
        """Create a signed URL for temporary access (absolute URL, path and token)."""
        body: Dict[str, Any] = {"expiresIn": expires_in}
        if options and options.download:
            body["download"] = options.download if isinstance(options.download, str) else True
        if options and options.transform:
            body["transform"] = {k: v for k, v in asdict(options.transform).items() if v is not None}
        resp = self._sync(
            f"{self._url}/object/sign/{self._bucket}/{path}",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json=body,
        )
        result = handle_response(resp)
        if result["error"]:
            return {"data": None, "error": result["error"]}
        d = result["data"] if isinstance(result["data"], dict) else {}
        signed = d.get("signedURL") or d.get("signedUrl")
        return {"data": {"signedUrl": self._absolute(signed), "path": path, "token": d.get("token") or ""}, "error": None}

    def create_signed_urls(self, paths: List[str], expires_in: int) -> Dict[str, Any]:
        """Create signed URLs for multiple files."""
        resp = self._sync(
            f"{self._url}/object/sign/{self._bucket}",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json={"expiresIn": expires_in, "paths": paths},
        )
        result = handle_response(resp)
        if result["error"]:
            return {"data": None, "error": result["error"]}
        items = result["data"] if isinstance(result["data"], list) else []
        return {
            "data": [
                {"signedUrl": self._absolute(i.get("signedURL") or i.get("signedUrl")), "path": i.get("path"),
                 "token": i.get("token") or ""}
                for i in items if isinstance(i, dict)
            ],
            "error": None,
        }

    # ─── Public URL ───────────────────────────────────────────────────

    def get_public_url(
        self,
        path: str,
        *,
        download: Union[str, bool, None] = None,
        transform: Optional[TransformOptions] = None,
    ) -> Dict[str, Any]:
        """Get the public URL for a file in a public bucket (``download`` makes it an attachment)."""
        pairs: List[Tuple[str, str]] = []
        if download:
            pairs.append(("download", download if isinstance(download, str) else ""))
        pairs += _transform_pairs(transform)
        qs = urlencode(pairs)
        base = f"{self._url}/object/public/{self._bucket}/{path}"
        return {"data": {"publicUrl": f"{base}?{qs}" if qs else base}}


class AfribaseStorageClient(HeadersMixin):
    """Manage buckets and access per-bucket file operations.

    Usage::

        storage = client.storage
        storage.create_bucket("avatars", public=True)
        storage.from_("avatars").upload("avatar.png", file_bytes)
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        get_access_token: Any,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._get_token = get_access_token

    def from_(self, bucket_id: str) -> StorageFileApi:
        """Get a reference to a specific bucket for file operations."""
        api = StorageFileApi(self._url, bucket_id, self._api_key, self._get_token)
        api._default_headers = self._default_headers
        return api

    # ─── Bucket management ────────────────────────────────────────────

    def list_buckets(self) -> Dict[str, Any]:
        resp = self._sync(
            f"{self._url}/bucket",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        return handle_response(resp)

    def get_bucket(self, id: str) -> Dict[str, Any]:
        resp = self._sync(
            f"{self._url}/bucket/{id}",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        return handle_response(resp)

    def create_bucket(
        self,
        id: str,
        *,
        public: bool = False,
        file_size_limit: Optional[int] = None,
        allowed_mime_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"id": id, "name": id, "public": public}
        if file_size_limit:
            body["file_size_limit"] = file_size_limit
        if allowed_mime_types:
            body["allowed_mime_types"] = allowed_mime_types
        resp = self._sync(
            f"{self._url}/bucket",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json=body,
        )
        return handle_response(resp)

    def update_bucket(
        self,
        id: str,
        *,
        public: Optional[bool] = None,
        file_size_limit: Optional[int] = None,
        allowed_mime_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if public is not None:
            body["public"] = public
        if file_size_limit is not None:
            body["file_size_limit"] = file_size_limit
        if allowed_mime_types is not None:
            body["allowed_mime_types"] = allowed_mime_types
        resp = self._sync(
            f"{self._url}/bucket/{id}",
            method="PUT",
            api_key=self._api_key,
            access_token=self._get_token(),
            json=body,
        )
        return handle_response(resp)

    def delete_bucket(self, id: str) -> Dict[str, Any]:
        resp = self._sync(
            f"{self._url}/bucket/{id}",
            method="DELETE",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        return handle_response(resp)

    def empty_bucket(self, id: str) -> Dict[str, Any]:
        resp = self._sync(
            f"{self._url}/bucket/{id}/empty",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        return handle_response(resp)

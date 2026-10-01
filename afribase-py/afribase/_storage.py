"""AfribaseStorageClient — file uploads, downloads, and bucket management."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote

from afribase._http import handle_response, sync_request
from afribase._types import SignedUrlOptions, TransformOptions, UploadOptions


class StorageFileApi:
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
        file: Union[bytes, str],
        options: Optional[UploadOptions] = None,
    ) -> Dict[str, Any]:
        """Upload a file."""
        opts = options or UploadOptions()
        headers: Dict[str, str] = {
            "Content-Type": opts.content_type or "application/octet-stream",
        }
        if opts.cache_control:
            headers["Cache-Control"] = opts.cache_control
        if opts.upsert:
            headers["x-upsert"] = "true"

        body = file if isinstance(file, bytes) else file.encode("utf-8")
        resp = sync_request(
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
        return {
            "data": {"path": path, "fullPath": f"{self._bucket}/{path}"},
            "error": None,
        }

    def update(
        self,
        path: str,
        file: Union[bytes, str],
        options: Optional[UploadOptions] = None,
    ) -> Dict[str, Any]:
        """Update (overwrite) a file."""
        opts = options or UploadOptions()
        headers: Dict[str, str] = {
            "Content-Type": opts.content_type or "application/octet-stream",
        }
        if opts.cache_control:
            headers["Cache-Control"] = opts.cache_control

        body = file if isinstance(file, bytes) else file.encode("utf-8")
        resp = sync_request(
            f"{self._url}/object/{self._bucket}/{path}",
            method="PUT",
            api_key=self._api_key,
            access_token=self._get_token(),
            headers=headers,
            body=body,
        )
        result = handle_response(resp)
        if result["error"]:
            return result
        return {
            "data": {"path": path, "fullPath": f"{self._bucket}/{path}"},
            "error": None,
        }

    # ─── Download ─────────────────────────────────────────────────────

    def download(self, path: str) -> Dict[str, Any]:
        """Download a file as bytes."""
        resp = sync_request(
            f"{self._url}/object/{self._bucket}/{path}",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        if resp.status_code >= 400:
            result = handle_response(resp)
            return {"data": None, "error": result["error"]}
        return {"data": resp.content, "error": None}

    # ─── List / Remove ────────────────────────────────────────────────

    def list(
        self,
        path: str = "",
        *,
        limit: int = 100,
        offset: int = 0,
        sort_by: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """List files in a path."""
        body: Dict[str, Any] = {"prefix": path, "limit": limit, "offset": offset}
        if sort_by:
            body["sortBy"] = sort_by
        resp = sync_request(
            f"{self._url}/object/list/{self._bucket}",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json=body,
        )
        return handle_response(resp)

    def remove(self, paths: List[str]) -> Dict[str, Any]:
        """Delete one or more files."""
        resp = sync_request(
            f"{self._url}/object/{self._bucket}",
            method="DELETE",
            api_key=self._api_key,
            access_token=self._get_token(),
            json={"prefixes": paths},
        )
        return handle_response(resp)

    def move(self, from_path: str, to_path: str) -> Dict[str, Any]:
        """Move a file."""
        resp = sync_request(
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
        resp = sync_request(
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

    def create_signed_url(self, path: str, expires_in: int) -> Dict[str, Any]:
        """Create a signed URL for temporary access."""
        resp = sync_request(
            f"{self._url}/object/sign/{self._bucket}/{path}",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json={"expiresIn": expires_in},
        )
        result = handle_response(resp)
        if result["error"]:
            return result
        signed = result["data"].get("signedURL", result["data"].get("signedUrl", ""))
        return {"data": {"signedUrl": signed, "path": path}, "error": None}

    def create_signed_urls(self, paths: List[str], expires_in: int) -> Dict[str, Any]:
        """Create signed URLs for multiple files."""
        resp = sync_request(
            f"{self._url}/object/sign/{self._bucket}",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json={"expiresIn": expires_in, "paths": paths},
        )
        return handle_response(resp)

    # ─── Public URL ───────────────────────────────────────────────────

    def get_public_url(
        self,
        path: str,
        *,
        transform: Optional[TransformOptions] = None,
    ) -> Dict[str, Any]:
        """Get the public URL for a file in a public bucket."""
        base = f"{self._url}/object/public/{self._bucket}/{path}"
        if transform:
            params: List[str] = []
            if transform.width:
                params.append(f"width={transform.width}")
            if transform.height:
                params.append(f"height={transform.height}")
            if transform.resize:
                params.append(f"resize={transform.resize}")
            if transform.quality:
                params.append(f"quality={transform.quality}")
            if transform.format:
                params.append(f"format={transform.format}")
            if params:
                base = f"{base}?{'&'.join(params)}"
        return {"data": {"publicUrl": base}}


class AfribaseStorageClient:
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
        return StorageFileApi(self._url, bucket_id, self._api_key, self._get_token)

    # ─── Bucket management ────────────────────────────────────────────

    def list_buckets(self) -> Dict[str, Any]:
        resp = sync_request(
            f"{self._url}/bucket",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        return handle_response(resp)

    def get_bucket(self, id: str) -> Dict[str, Any]:
        resp = sync_request(
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
        resp = sync_request(
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
        resp = sync_request(
            f"{self._url}/bucket/{id}",
            method="PUT",
            api_key=self._api_key,
            access_token=self._get_token(),
            json=body,
        )
        return handle_response(resp)

    def delete_bucket(self, id: str) -> Dict[str, Any]:
        resp = sync_request(
            f"{self._url}/bucket/{id}",
            method="DELETE",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        return handle_response(resp)

    def empty_bucket(self, id: str) -> Dict[str, Any]:
        resp = sync_request(
            f"{self._url}/bucket/{id}/empty",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        return handle_response(resp)

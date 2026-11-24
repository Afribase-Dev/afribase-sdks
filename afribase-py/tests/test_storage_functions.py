import io
from urllib.parse import parse_qsl, urlsplit

from afribase import SignedUrlOptions, TransformOptions, UploadOptions, create_client

URL = "https://proj.example.com"


def test_upload_update_id_and_file_objects(server):
    server.on("POST", "/storage/v1/object/avatars/me.png", json_body={"Key": "avatars/me.png", "id": "obj-1"})
    st = create_client(URL, "anon").storage.from_("avatars")
    r = st.upload("me.png", io.BytesIO(b"\x89PNG"), UploadOptions(content_type="image/png"))
    assert r["data"] == {"path": "me.png", "id": "obj-1", "fullPath": "avatars/me.png"}
    assert server.last.content == b"\x89PNG" and server.last.headers["content-type"] == "image/png"
    st.update("me.png", b"new")
    assert server.last.method == "POST" and server.last.headers["x-upsert"] == "true"


def test_download_transform_and_error(server):
    st = create_client(URL, "anon").storage.from_("img")
    server.on("GET", "/object/img/a.jpg", text="bytes")
    assert st.download("a.jpg", transform=TransformOptions(width=100, resize="cover"))["data"] == b"bytes"
    assert parse_qsl(urlsplit(str(server.last.url)).query) == [("width", "100"), ("resize", "cover")]
    server.on("GET", "/object/img/b.jpg", status=404, text="")
    err = st.download("b.jpg")["error"]
    assert err == {"message": "Download failed with status 404", "status": 404}


def test_signed_urls_absolute_with_token_and_options(server):
    st = create_client(URL, "anon").storage.from_("docs")
    server.on("POST", "/object/sign/docs/a.pdf", json_body={"signedURL": "/object/sign/docs/a.pdf?token=t1", "token": "t1"})
    r = st.create_signed_url("a.pdf", 60, SignedUrlOptions(download="A.pdf", transform=TransformOptions(width=50)))
    assert r["data"] == {"signedUrl": "https://proj.example.com/storage/v1/object/sign/docs/a.pdf?token=t1",
                         "path": "a.pdf", "token": "t1"}
    assert server.last_json() == {"expiresIn": 60, "download": "A.pdf", "transform": {"width": 50}}
    server.on("POST", "/object/sign/docs", json_body=[{"signedURL": "/x?token=1", "path": "a", "token": "1"},
                                                     {"signedURL": "https://cdn/y", "path": "b"}])
    many = st.create_signed_urls(["a", "b"], 60)["data"]
    assert many == [{"signedUrl": "https://proj.example.com/storage/v1/x?token=1", "path": "a", "token": "1"},
                    {"signedUrl": "https://cdn/y", "path": "b", "token": ""}]


def test_public_url_download_and_list_defaults(server):
    st = create_client(URL, "anon").storage.from_("pub")
    url = st.get_public_url("a b.png", download=True, transform=TransformOptions(height=10))["data"]["publicUrl"]
    assert url == "https://proj.example.com/storage/v1/object/public/pub/a b.png?download=&height=10"
    server.on("POST", "/object/list/pub", json_body=[])
    st.list("folder")
    assert server.last_json() == {"prefix": "folder"}


def test_functions_region_header_body_types_and_errors(server):
    fn = create_client(URL, "anon").functions
    server.on("POST", "/functions/v1/hello", json_body={"ok": True})
    assert fn.invoke("hello", body=42, region="eu-west")["data"] == {"ok": True}
    assert server.last.content == b"42" and server.last.headers["content-type"] == "application/json"
    assert server.last.headers["x-region"] == "eu-west" and "region" not in str(server.last.url)
    fn.invoke("hello", body={"a": 1}, headers={"content-type": "application/vnd.x+json"})
    assert server.last.headers.get_list("content-type") == ["application/vnd.x+json"]
    server.on("POST", "/functions/v1/bad", status=500, text="boom")
    assert fn.invoke("bad")["error"] == {"message": "boom", "status": 500}
    server.on("POST", "/functions/v1/badj", status=422, json_body={"msg": "nope"})
    assert fn.invoke("badj")["error"] == {"msg": "nope", "message": "nope", "status": 422}

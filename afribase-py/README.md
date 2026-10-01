# Afribase Python SDK

The official Python client for [Afribase](https://useafribase.app) — an open-source backend-as-a-service platform.

## Installation

```bash
pip install afribase
```

## Quick Start

```python
from afribase import create_client

client = create_client("https://your-project.useafribase.app", "your-anon-key")
```

## Authentication

```python
# Sign up
res = client.auth.sign_up(email="user@example.com", password="secret123")

# Sign in
res = client.auth.sign_in_with_password(email="user@example.com", password="secret123")

# OAuth
url = client.auth.sign_in_with_oauth(provider="google")

# OTP / Magic Link
client.auth.sign_in_with_otp(email="user@example.com")
res = client.auth.verify_otp(email="user@example.com", token="123456")

# Sign out
client.auth.sign_out()

# Delete a user permanently. Administrative: build the client with the service
# key, and only ever from your own backend — never anywhere the key is readable.
client.auth.delete_user(user_id)

# Listen for auth changes
def on_change(event, session):
    print(f"Auth event: {event}")

unsubscribe = client.auth.on_auth_state_change(on_change)
```

## Database (PostgREST Query Builder)

```python
# Select
data = client.from_("posts").select("*").eq("published", "true").execute()

# Insert
data = client.from_("posts").insert({"title": "Hello", "body": "World"}).execute()

# Update
data = client.from_("posts").update({"title": "Updated"}).eq("id", "1").execute()

# Delete
data = client.from_("posts").delete().eq("id", "1").execute()

# Filters
data = (
    client.from_("posts")
    .select("*")
    .gte("likes", "10")
    .order("created_at", desc=True)
    .limit(20)
    .execute()
)

# RPC (Postgres functions)
result = client.rpc("my_function", {"arg": "value"}).execute()
```

## Storage

```python
# Upload
client.storage.from_("avatars").upload("avatar.png", file_bytes)

# Download
data = client.storage.from_("avatars").download("avatar.png")

# Signed URL
url = client.storage.from_("avatars").create_signed_url("avatar.png", expires_in=3600)

# Public URL (with optional transforms)
url = client.storage.from_("avatars").get_public_url("avatar.png", transform={"width": 200})

# List files
files = client.storage.from_("avatars").list(path="folder/")

# Move / Copy
client.storage.from_("avatars").move("old.png", "new.png")
client.storage.from_("avatars").copy("source.png", "dest.png")

# Bucket management
buckets = client.storage.list_buckets()
client.storage.create_bucket("my-bucket", public=True)
```

## Edge Functions

```python
result = client.functions.invoke("my-function", body={"name": "world"})
```

## Realtime

```python
# Create a channel
channel = client.channel("room1")

# Listen for broadcast messages
channel.on_broadcast("message", callback=lambda payload: print(payload))

# Listen for Postgres changes
channel.on_postgres_changes(
    "INSERT",
    schema="public",
    table="messages",
    callback=lambda payload: print(payload),
)

# Presence
channel.on_presence_sync(callback=lambda state: print(state))

# Subscribe
channel.subscribe()

# Send broadcast
channel.send_broadcast("message", {"text": "Hello!"})

# Track presence
channel.track({"user": "alice", "status": "online"})
```

## Server-side usage (project API key)

Server code has no user session to carry. Pass an `afb_` project API key instead
of the anon key and the gateway exchanges it for the project's own credentials:

```python
import os
from afribase import create_client

# Server-side only. This key bypasses RLS — never ship it to a client.
afribase = create_client(
    os.environ["AFRIBASE_URL"],
    os.environ["AFRIBASE_API_KEY"],  # afb_live_...
)

with open("logo.png", "rb") as f:
    afribase.storage.from_("product-images").upload(
        f"stores/{store_id}/logo.png", f, content_type="image/png"
    )
```

Create keys in the dashboard under **API Keys**. A key belongs to one project and
is rejected against any other.

Files in a public bucket need no credentials:

```python
url = afribase.storage.from_("product-images").get_public_url("logo.png")
```

Public URLs carry a one-year immutable cache header, so give a changed image a
new path rather than overwriting it.

## Requirements

- Python 3.9+
- `httpx >= 0.25.0`
- `websockets >= 12.0`

## License

MIT

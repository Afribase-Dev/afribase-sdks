# Afribase Dart/Flutter SDK

The official Dart/Flutter client for [Afribase](https://useafribase.app) — an open-source backend-as-a-service platform.

## Installation

Add to your `pubspec.yaml`:

```yaml
dependencies:
  afribase: ^0.2.0
```

Then run:

```bash
dart pub get
# or
flutter pub get
```

## Quick Start

```dart
import 'package:afribase/afribase.dart';

final client = AfribaseClient('https://your-project.useafribase.app', 'your-anon-key');
```

## Authentication

```dart
// Sign up
final res = await client.auth.signUp(email: 'user@example.com', password: 'secret123');

// Sign in
final res = await client.auth.signInWithPassword(email: 'user@example.com', password: 'secret123');

// OAuth (returns redirect URL)
final url = await client.auth.signInWithOAuth(provider: 'google');

// OTP / Magic Link
await client.auth.signInWithOtp(email: 'user@example.com');
final res = await client.auth.verifyOtp(email: 'user@example.com', token: '123456');

// Sign out
await client.auth.signOut();

// Delete a user permanently. Administrative: needs the service key, so call it
// from your own backend — that key must never ship inside the app.
await client.auth.deleteUser(userId);

// Listen for auth changes
final unsubscribe = client.auth.onAuthStateChange((event, session) {
  print('Auth event: $event');
});
```

## Database (PostgREST Query Builder)

```dart
// Select
final data = await client.from('posts').select('*').eq('published', true).execute();

// Insert
final data = await client.from('posts').insert({'title': 'Hello', 'body': 'World'}).execute();

// Update
final data = await client.from('posts').update({'title': 'Updated'}).eq('id', 1).execute();

// Delete
final data = await client.from('posts').delete().eq('id', 1).execute();

// Filters & modifiers
final data = await client.from('posts')
    .select('*')
    .gte('likes', 10)
    .order('created_at', ascending: false)
    .limit(20)
    .execute();

// RPC (Postgres functions)
final result = await client.rpc('my_function', {'arg': 'value'}).execute();
```

## Storage

```dart
import 'dart:typed_data';

// Upload
await client.storage.from('avatars').upload('avatar.png', fileBytes);

// Download
final Uint8List data = await client.storage.from('avatars').download('avatar.png');

// Signed URL
final url = await client.storage.from('avatars').createSignedUrl('avatar.png', expiresIn: 3600);

// Public URL (with optional transforms)
final url = client.storage.from('avatars').getPublicUrl('avatar.png',
    transform: TransformOptions(width: 200));

// List files
final files = await client.storage.from('avatars').list(path: 'folder/');

// Move / Copy
await client.storage.from('avatars').move('old.png', 'new.png');
await client.storage.from('avatars').copy('source.png', 'dest.png');

// Bucket management
final buckets = await client.storage.listBuckets();
await client.storage.createBucket('my-bucket', public: true);
```

## Edge Functions

```dart
final result = await client.functions.invoke('my-function', body: {'name': 'world'});
```

## Realtime

```dart
// Create a channel
final channel = client.channel('room1');

// Listen for broadcast messages
channel.onBroadcast('message', (payload) => print(payload));

// Listen for Postgres changes
channel.onPostgresChanges(
  event: 'INSERT',
  schema: 'public',
  table: 'messages',
  callback: (payload) => print(payload),
);

// Presence
channel.onPresenceSync((state) => print(state));

// Subscribe
channel.subscribe();

// Send broadcast
channel.sendBroadcast('message', {'text': 'Hello!'});

// Track presence
channel.track({'user': 'alice', 'status': 'online'});

// Cleanup
client.dispose();
```

## Server-side usage (project API key)

Dart backends and CLI tools have no user session to carry. Pass an `afb_` project
API key instead of the anon key and the gateway exchanges it for the project's
own credentials:

```dart
// Server-side only. This key bypasses RLS — never ship it in an app binary.
final afribase = AfribaseClient(
  Platform.environment['AFRIBASE_URL']!,
  Platform.environment['AFRIBASE_API_KEY']!, // afb_live_...
);

await afribase.storage.from('product-images').upload(
  'stores/$storeId/logo.png',
  bytes,
  contentType: 'image/png',
);
```

Create keys in the dashboard under **API Keys**. A key belongs to one project and
is rejected against any other.

Files in a public bucket need no credentials:

```dart
final url = afribase.storage.from('product-images').getPublicUrl('logo.png');
```

Public URLs carry a one-year immutable cache header, so give a changed image a
new path rather than overwriting it.

## Requirements

- Dart SDK >= 3.0.0
- Flutter >= 3.10.0 (for Flutter projects)

## Dependencies

- `http` — HTTP client
- `web_socket_channel` — WebSocket support
- `meta` — Annotations

## License

MIT

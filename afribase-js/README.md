# Afribase JS SDK

The official JavaScript/TypeScript client for Afribase.

## Installation

```bash
npm install @afribase/afribase-js
```

## Usage

### Initializing the Client

```typescript
import { createClient } from '@afribase/afribase-js';

const afribase = createClient('http://your-afribase-url.com', 'your-anon-key');
```

### Authentication

```typescript
// Sign up
const { user, error } = await afribase.auth.signUp({
  email: 'hello@useafribase.app',
  password: 'password123'
});

// Sign in
const { access_token, error } = await afribase.auth.signIn({
  email: 'hello@useafribase.app',
  password: 'password123'
});

// Get current user
const user = await afribase.auth.getUser();

// Delete a user permanently. Administrative: build the client with the service
// key and call this from your own server — never from the browser.
const { error } = await afribase.auth.admin.deleteUser(userId);
```

### Working with Data

```typescript
// Fetch data
const posts = await afribase.from('posts').select();

// Insert data
const newPost = await afribase.from('posts').insert({
  title: 'Hello Afribase',
  content: 'Building faster in Africa'
});
```

## Server-side usage (project API key)

Browser code signs a user in and the SDK carries their session. Server code has
no session to carry — a backend uploading a logo on a user's behalf has only a
project API key.

Create the client with an `afb_` project API key instead of the anon key. The
gateway exchanges it for the project's own credentials, so storage, database and
functions all work without a user JWT:

```ts
import { createClient } from '@afribase/afribase-js';

// Server-side only. This key bypasses RLS — never ship it to a browser.
const afribase = createClient(
  process.env.AFRIBASE_URL!,
  process.env.AFRIBASE_API_KEY!, // afb_live_...
);

const { data, error } = await afribase.storage
  .from('product-images')
  .upload(`stores/${storeId}/logo.png`, file, { contentType: 'image/png' });
```

Create keys in the dashboard under **API Keys**. A key belongs to one project and
is rejected against any other, so a leaked key cannot reach a different tenant.

### Public files

Files in a public bucket are readable with no credentials at all:

```ts
const { data } = afribase.storage.from('product-images').getPublicUrl('logo.png');
// -> https://<project>.afribase.dev/storage/v1/object/public/product-images/logo.png
```

Those URLs are served with a one-year immutable cache header, so give a changed
image a new path rather than overwriting it.

## License

Apache-2.0

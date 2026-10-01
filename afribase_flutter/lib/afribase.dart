/// Afribase Dart/Flutter SDK
///
/// The official Dart client for Afribase — an open-source backend-as-a-service platform.
///
/// ```dart
/// import 'package:afribase/afribase.dart';
///
/// final client = AfribaseClient('https://your-project.useafribase.app', 'your-anon-key');
///
/// // Auth
/// final res = await client.auth.signUp(email: 'user@example.com', password: 'secret');
///
/// // Database (PostgREST query builder)
/// final data = await client.from('posts').select('*').eq('published', true).execute();
///
/// // Storage
/// await client.storage.from('avatars').upload('avatar.png', fileBytes);
///
/// // Edge Functions
/// final result = await client.functions.invoke('my-function', body: {'foo': 'bar'});
///
/// // Realtime
/// final channel = client.channel('room1');
/// channel.onBroadcast('message', (payload) => print(payload));
/// channel.subscribe();
/// ```
library afribase;

export 'src/types.dart';
export 'src/afribase_client.dart';
export 'src/afribase_auth_client.dart';
export 'src/afribase_email_client.dart';
export 'src/afribase_query_builder.dart';
export 'src/afribase_storage_client.dart';
export 'src/afribase_functions_client.dart';
export 'src/afribase_realtime_client.dart';
export 'src/modular.dart';

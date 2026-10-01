/// Type definitions for the Afribase Dart SDK.
library;

// ─── Auth Types ──────────────────────────────────────────────────────────────

/// Represents a user identity (OAuth, email, etc.).
class UserIdentity {
  final String id;
  final String userId;
  final String provider;
  final Map<String, dynamic> identityData;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const UserIdentity({
    required this.id,
    required this.userId,
    required this.provider,
    this.identityData = const {},
    this.createdAt,
    this.updatedAt,
  });

  factory UserIdentity.fromJson(Map<String, dynamic> json) => UserIdentity(
        id: json['id'] as String? ?? '',
        userId: json['user_id'] as String? ?? '',
        provider: json['provider'] as String? ?? '',
        identityData:
            (json['identity_data'] as Map<String, dynamic>?) ?? const {},
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
        updatedAt: json['updated_at'] != null
            ? DateTime.tryParse(json['updated_at'] as String)
            : null,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'user_id': userId,
        'provider': provider,
        'identity_data': identityData,
        'created_at': createdAt?.toIso8601String(),
        'updated_at': updatedAt?.toIso8601String(),
      };
}

/// Represents a multi-factor authentication factor.
class Factor {
  final String id;
  final String friendlyName;
  final String factorType;
  final String status;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const Factor({
    required this.id,
    this.friendlyName = '',
    this.factorType = '',
    this.status = '',
    this.createdAt,
    this.updatedAt,
  });

  factory Factor.fromJson(Map<String, dynamic> json) => Factor(
        id: json['id'] as String? ?? '',
        friendlyName: json['friendly_name'] as String? ?? '',
        factorType: json['factor_type'] as String? ?? '',
        status: json['status'] as String? ?? '',
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
        updatedAt: json['updated_at'] != null
            ? DateTime.tryParse(json['updated_at'] as String)
            : null,
      );
}

/// Represents an authenticated user.
class User {
  final String id;
  final String email;
  final String phone;
  final String role;
  final String? aud;
  final Map<String, dynamic> userMetadata;
  final Map<String, dynamic> appMetadata;
  final List<UserIdentity> identities;
  final List<Factor> factors;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? confirmedAt;
  final DateTime? emailConfirmedAt;
  final DateTime? phoneConfirmedAt;
  final DateTime? lastSignInAt;

  const User({
    required this.id,
    this.email = '',
    this.phone = '',
    this.role = '',
    this.aud,
    this.userMetadata = const {},
    this.appMetadata = const {},
    this.identities = const [],
    this.factors = const [],
    this.createdAt,
    this.updatedAt,
    this.confirmedAt,
    this.emailConfirmedAt,
    this.phoneConfirmedAt,
    this.lastSignInAt,
  });

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as String? ?? '',
        email: json['email'] as String? ?? '',
        phone: json['phone'] as String? ?? '',
        role: json['role'] as String? ?? '',
        aud: json['aud'] as String?,
        userMetadata:
            (json['user_metadata'] as Map<String, dynamic>?) ?? const {},
        appMetadata:
            (json['app_metadata'] as Map<String, dynamic>?) ?? const {},
        identities: (json['identities'] as List<dynamic>?)
                ?.map((e) =>
                    UserIdentity.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        factors: (json['factors'] as List<dynamic>?)
                ?.map((e) => Factor.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
        updatedAt: json['updated_at'] != null
            ? DateTime.tryParse(json['updated_at'] as String)
            : null,
        confirmedAt: json['confirmed_at'] != null
            ? DateTime.tryParse(json['confirmed_at'] as String)
            : null,
        emailConfirmedAt: json['email_confirmed_at'] != null
            ? DateTime.tryParse(json['email_confirmed_at'] as String)
            : null,
        phoneConfirmedAt: json['phone_confirmed_at'] != null
            ? DateTime.tryParse(json['phone_confirmed_at'] as String)
            : null,
        lastSignInAt: json['last_sign_in_at'] != null
            ? DateTime.tryParse(json['last_sign_in_at'] as String)
            : null,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'phone': phone,
        'role': role,
        'aud': aud,
        'user_metadata': userMetadata,
        'app_metadata': appMetadata,
        'identities': identities.map((e) => e.toJson()).toList(),
        'created_at': createdAt?.toIso8601String(),
        'updated_at': updatedAt?.toIso8601String(),
      };
}

/// Represents an auth session (access token, refresh token, user).
class Session {
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final int expiresIn;
  final int? expiresAt;
  final User? user;

  const Session({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType = 'bearer',
    this.expiresIn = 3600,
    this.expiresAt,
    this.user,
  });

  factory Session.fromJson(Map<String, dynamic> json) => Session(
        accessToken: json['access_token'] as String? ?? '',
        refreshToken: json['refresh_token'] as String? ?? '',
        tokenType: json['token_type'] as String? ?? 'bearer',
        expiresIn: json['expires_in'] as int? ?? 3600,
        expiresAt: json['expires_at'] as int?,
        user: json['user'] != null
            ? User.fromJson(json['user'] as Map<String, dynamic>)
            : null,
      );

  Map<String, dynamic> toJson() => {
        'access_token': accessToken,
        'refresh_token': refreshToken,
        'token_type': tokenType,
        'expires_in': expiresIn,
        'expires_at': expiresAt,
        'user': user?.toJson(),
      };
}

/// Auth state change events.
enum AuthChangeEvent {
  initialSession,
  signedIn,
  signedOut,
  tokenRefreshed,
  userUpdated,
  passwordRecovery,
  mfaChallengeVerified,
}

/// Auth response wrapping session + user.
class AuthResponse {
  final Session? session;
  final User? user;
  final String? error;

  const AuthResponse({this.session, this.user, this.error});

  bool get hasError => error != null;

  factory AuthResponse.fromJson(Map<String, dynamic> json) {
    final errorMsg = json['error_description'] as String? ??
        json['error'] as String? ??
        json['msg'] as String?;
    if (errorMsg != null) {
      return AuthResponse(error: errorMsg);
    }
    final session = json.containsKey('access_token')
        ? Session.fromJson(json)
        : null;
    final user = json['user'] != null
        ? User.fromJson(json['user'] as Map<String, dynamic>)
        : session?.user;
    return AuthResponse(session: session, user: user);
  }
}

// ─── Storage Types ───────────────────────────────────────────────────────────

/// Represents a storage bucket.
class StorageBucket {
  final String id;
  final String name;
  final bool public;
  final int? fileSizeLimit;
  final List<String>? allowedMimeTypes;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const StorageBucket({
    required this.id,
    required this.name,
    this.public = false,
    this.fileSizeLimit,
    this.allowedMimeTypes,
    this.createdAt,
    this.updatedAt,
  });

  factory StorageBucket.fromJson(Map<String, dynamic> json) => StorageBucket(
        id: json['id'] as String? ?? '',
        name: json['name'] as String? ?? '',
        public: json['public'] as bool? ?? false,
        fileSizeLimit: json['file_size_limit'] as int?,
        allowedMimeTypes: (json['allowed_mime_types'] as List<dynamic>?)
            ?.cast<String>(),
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
        updatedAt: json['updated_at'] != null
            ? DateTime.tryParse(json['updated_at'] as String)
            : null,
      );
}

/// Represents a file/object in storage.
class StorageObject {
  final String name;
  final String? id;
  final String? bucketId;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? lastAccessedAt;
  final Map<String, dynamic>? metadata;

  const StorageObject({
    required this.name,
    this.id,
    this.bucketId,
    this.createdAt,
    this.updatedAt,
    this.lastAccessedAt,
    this.metadata,
  });

  factory StorageObject.fromJson(Map<String, dynamic> json) => StorageObject(
        name: json['name'] as String? ?? '',
        id: json['id'] as String?,
        bucketId: json['bucket_id'] as String?,
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
        updatedAt: json['updated_at'] != null
            ? DateTime.tryParse(json['updated_at'] as String)
            : null,
        lastAccessedAt: json['last_accessed_at'] != null
            ? DateTime.tryParse(json['last_accessed_at'] as String)
            : null,
        metadata: json['metadata'] as Map<String, dynamic>?,
      );
}

/// Image transform options for storage downloads/URLs.
class TransformOptions {
  final int? width;
  final int? height;
  final String? resize;
  final int? quality;
  final String? format;

  const TransformOptions({
    this.width,
    this.height,
    this.resize,
    this.quality,
    this.format,
  });

  Map<String, String> toQueryParams() {
    final params = <String, String>{};
    if (width != null) params['width'] = width.toString();
    if (height != null) params['height'] = height.toString();
    if (resize != null) params['resize'] = resize!;
    if (quality != null) params['quality'] = quality.toString();
    if (format != null) params['format'] = format!;
    return params;
  }
}

// ─── Functions Types ─────────────────────────────────────────────────────────

/// Options for invoking an edge function.
class FunctionInvokeOptions {
  final Map<String, String>? headers;
  final dynamic body;
  final String method;

  const FunctionInvokeOptions({
    this.headers,
    this.body,
    this.method = 'POST',
  });
}

// ─── PostgREST Types ─────────────────────────────────────────────────────────

/// Error from the PostgREST API.
class PostgrestError {
  final String message;
  final String? code;
  final String? details;
  final String? hint;

  const PostgrestError({
    required this.message,
    this.code,
    this.details,
    this.hint,
  });

  factory PostgrestError.fromJson(Map<String, dynamic> json) => PostgrestError(
        message: json['message'] as String? ?? '',
        code: json['code'] as String?,
        details: json['details'] as String?,
        hint: json['hint'] as String?,
      );

  @override
  String toString() => 'PostgrestError($code): $message';
}

/// Response from the PostgREST API.
class PostgrestResponse<T> {
  final T? data;
  final PostgrestError? error;
  final int? count;
  final int statusCode;

  const PostgrestResponse({
    this.data,
    this.error,
    this.count,
    this.statusCode = 200,
  });

  bool get hasError => error != null;
}

// ─── Realtime Types ──────────────────────────────────────────────────────────

/// Represents a presence entry in a realtime channel.
class RealtimePresenceEntry {
  final String presenceRef;
  final Map<String, dynamic> payload;

  const RealtimePresenceEntry({
    required this.presenceRef,
    this.payload = const {},
  });

  factory RealtimePresenceEntry.fromJson(Map<String, dynamic> json) =>
      RealtimePresenceEntry(
        presenceRef: json['presence_ref'] as String? ?? '',
        payload: json,
      );
}

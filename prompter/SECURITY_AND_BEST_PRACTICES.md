# Security & Best Practices

## 🔒 Security-First Principles

### 1. NO SECRETS IN CODE (CRITICAL)

#### ❌ NEVER Do This
```dart
// NEVER hardcode API keys, passwords, tokens, or secrets
final firebaseApiKey = "AIzaSyBxxxxxxxxxxxxxxxxxxxxxxxx";
final adminPassword = "admin123";
final jwtSecret = "my_secret_key";
```

#### ✅ ALWAYS Do This
```dart
// Use environment variables or Firebase Remote Config
final firebaseApiKey = Platform.environment['FIREBASE_API_KEY'];

// Or use flutter_dotenv
import 'package:flutter_dotenv/flutter_dotenv.dart';

Future main() async {
  await dotenv.load(fileName: ".env");
  runApp(MyApp());
}

// Access secrets
final apiKey = dotenv.env['FIREBASE_API_KEY'];
```

#### .env File Structure
```bash
# .env (NEVER commit to git - add to .gitignore)
FIREBASE_API_KEY=your_api_key_here
FIREBASE_PROJECT_ID=your_project_id
FIREBASE_APP_ID=your_app_id
```

#### .gitignore (REQUIRED)
```
# Secrets
.env
.env.local
.env.production
google-services.json
GoogleService-Info.plist
firebase-credentials.json

# API Keys
**/apikeys.dart
**/secrets.dart
```

### 2. Input Validation (Security First)

#### Centralized Validator Helper
```dart
// lib/utils/validators.dart
class Validators {
  // DRY: Single source of validation logic

  static const int maxTitleLength = 200;
  static const int maxContentLength = 100000;
  static const int maxImageSize = 5 * 1024 * 1024; // 5MB

  static ValidationResult validateTitle(String title) {
    final trimmed = title.trim();

    if (trimmed.isEmpty) {
      return ValidationResult.error('Title cannot be empty');
    }

    if (trimmed.length > maxTitleLength) {
      return ValidationResult.error(
        'Title too long (max $maxTitleLength characters)',
      );
    }

    // Security: Prevent script injection
    if (_containsScriptTags(trimmed)) {
      return ValidationResult.error('Title contains invalid characters');
    }

    return ValidationResult.valid();
  }

  static ValidationResult validateContent(String content) {
    if (content.length > maxContentLength) {
      return ValidationResult.error(
        'Content too large (max ${maxContentLength ~/ 1000}KB)',
      );
    }

    return ValidationResult.valid();
  }

  static ValidationResult validateImageFile(File file, int fileSize) {
    // Check file size
    if (fileSize > maxImageSize) {
      return ValidationResult.error('Image too large (max 5MB)');
    }

    // Check file type
    final extension = file.path.split('.').last.toLowerCase();
    const allowedExtensions = ['jpg', 'jpeg', 'png', 'gif', 'webp'];

    if (!allowedExtensions.contains(extension)) {
      return ValidationResult.error(
        'Invalid image format. Allowed: ${allowedExtensions.join(", ")}',
      );
    }

    return ValidationResult.valid();
  }

  static bool _containsScriptTags(String input) {
    final scriptPattern = RegExp(
      r'<script|javascript:|onerror=|onclick=',
      caseSensitive: false,
    );
    return scriptPattern.hasMatch(input);
  }

  // Sanitize user input to prevent XSS
  static String sanitize(String input) {
    return input
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#x27;')
        .replaceAll('/', '&#x2F;');
  }
}

class ValidationResult {
  final bool isValid;
  final String? error;

  ValidationResult.valid()
      : isValid = true,
        error = null;

  ValidationResult.error(this.error) : isValid = false;
}
```

### 3. Abstraction Through Interfaces (DRY)

#### Storage Abstraction
```dart
// lib/core/interfaces/i_storage.dart
abstract class IStorage<T> {
  Future<void> init();
  Future<void> save(T item);
  Future<T?> get(String id);
  Future<List<T>> getAll({
    int? limit,
    int? offset,
    Map<String, dynamic>? filters,
  });
  Future<void> delete(String id);
  Future<void> close();
}

// Implementations
class HiveNoteStorage implements IStorage<Note> {
  // Hive-specific implementation
}

class FirestoreNoteStorage implements IStorage<Note> {
  // Firestore-specific implementation
}

// Factory pattern for abstraction
class StorageFactory {
  static IStorage<Note> createNoteStorage(StorageType type) {
    switch (type) {
      case StorageType.local:
        return HiveNoteStorage();
      case StorageType.remote:
        return FirestoreNoteStorage();
    }
  }
}
```

#### Repository Pattern (DRY + Abstraction)
```dart
// Base repository with common CRUD operations
abstract class BaseRepository<T> {
  final IStorage<T> localStorage;
  final IStorage<T>? remoteStorage;

  BaseRepository({
    required this.localStorage,
    this.remoteStorage,
  });

  // DRY: Common create logic
  Future<Result<T>> create(T item) async {
    try {
      // Validate
      final validation = validate(item);
      if (!validation.isValid) {
        return Result.failure(ValidationException(validation.error!));
      }

      // Save locally first
      await localStorage.save(item);

      // Sync to remote if available
      if (remoteStorage != null) {
        _queueRemoteSync(() => remoteStorage!.save(item));
      }

      return Result.success(item);
    } catch (e) {
      return Result.failure(_handleError(e));
    }
  }

  // DRY: Common read logic
  Future<Result<T?>> get(String id) async {
    try {
      // Try local first
      final local = await localStorage.get(id);
      if (local != null) {
        return Result.success(local);
      }

      // Fallback to remote
      if (remoteStorage != null) {
        final remote = await remoteStorage!.get(id);
        if (remote != null) {
          // Cache locally
          await localStorage.save(remote);
          return Result.success(remote);
        }
      }

      return Result.success(null);
    } catch (e) {
      return Result.failure(_handleError(e));
    }
  }

  // Abstract methods for specific validation
  ValidationResult validate(T item);

  // Helper: Error handling
  AppException _handleError(dynamic error) {
    if (error is FirebaseException) {
      return NetworkException('Network error: ${error.message}');
    } else if (error is HiveError) {
      return StorageException('Storage error: ${error.message}');
    } else {
      return AppException('Unknown error: $error');
    }
  }

  // Helper: Background sync queue
  void _queueRemoteSync(Future<void> Function() operation) {
    // Add to sync queue to handle later
    SyncQueue.instance.add(operation);
  }
}

// Specific repository
class NoteRepository extends BaseRepository<Note> {
  NoteRepository({
    required super.localStorage,
    super.remoteStorage,
  });

  @override
  ValidationResult validate(Note note) {
    final titleValidation = Validators.validateTitle(note.title);
    if (!titleValidation.isValid) return titleValidation;

    final contentValidation = Validators.validateContent(note.content);
    if (!contentValidation.isValid) return contentValidation;

    return ValidationResult.valid();
  }

  // Note-specific methods
  Future<Result<List<Note>>> searchNotes(String query) async {
    // Implementation
  }
}
```

### 4. Helper Functions Library (DRY)

```dart
// lib/utils/helpers.dart
class Helpers {
  // Date formatting helper
  static String formatDate(DateTime date, {DateFormat? format}) {
    format ??= DateFormat('MMM dd, yyyy');
    return format.format(date);
  }

  static String formatRelativeTime(DateTime date) {
    final now = DateTime.now();
    final difference = now.difference(date);

    if (difference.inDays > 365) {
      return '${difference.inDays ~/ 365}y ago';
    } else if (difference.inDays > 30) {
      return '${difference.inDays ~/ 30}mo ago';
    } else if (difference.inDays > 0) {
      return '${difference.inDays}d ago';
    } else if (difference.inHours > 0) {
      return '${difference.inHours}h ago';
    } else if (difference.inMinutes > 0) {
      return '${difference.inMinutes}m ago';
    } else {
      return 'Just now';
    }
  }

  // String helpers
  static String truncate(String text, int maxLength, {String ellipsis = '...'}) {
    if (text.length <= maxLength) return text;
    return '${text.substring(0, maxLength - ellipsis.length)}$ellipsis';
  }

  static String capitalize(String text) {
    if (text.isEmpty) return text;
    return text[0].toUpperCase() + text.substring(1);
  }

  // Color helpers
  static Color hexToColor(String hex) {
    hex = hex.replaceAll('#', '');
    if (hex.length == 6) {
      hex = 'FF$hex'; // Add alpha if not present
    }
    return Color(int.parse(hex, radix: 16));
  }

  static String colorToHex(Color color) {
    return '#${color.value.toRadixString(16).substring(2).toUpperCase()}';
  }

  // Device ID helper (security: anonymous identifier)
  static Future<String> getDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    var deviceId = prefs.getString('device_id');

    if (deviceId == null) {
      deviceId = const Uuid().v4();
      await prefs.setString('device_id', deviceId);
    }

    return deviceId;
  }

  // Connectivity helper
  static Future<bool> isOnline() async {
    final connectivityResult = await Connectivity().checkConnectivity();
    return connectivityResult != ConnectivityResult.none;
  }

  // Debounce helper (for search, autosave)
  static Timer? _debounceTimer;

  static void debounce(VoidCallback callback, {Duration delay = const Duration(milliseconds: 500)}) {
    _debounceTimer?.cancel();
    _debounceTimer = Timer(delay, callback);
  }
}
```

### 5. Constants (DRY)

```dart
// lib/core/constants/app_constants.dart
class AppConstants {
  // Private constructor to prevent instantiation
  AppConstants._();

  // App info
  static const String appName = 'Prompter';
  static const String appVersion = '1.0.0';

  // Storage limits
  static const int maxTitleLength = 200;
  static const int maxContentLength = 100000;
  static const int maxImageSize = 5 * 1024 * 1024; // 5MB
  static const int maxImagesPerNote = 10;

  // Sync settings
  static const Duration syncDebounce = Duration(seconds: 2);
  static const Duration syncTimeout = Duration(seconds: 30);
  static const int maxSyncRetries = 5;
  static const int maxQueueSize = 100;

  // Pagination
  static const int defaultPageSize = 20;
  static const int maxPageSize = 100;

  // UI
  static const Duration animationDuration = Duration(milliseconds: 300);
  static const double borderRadius = 12.0;
  static const double defaultPadding = 16.0;

  // Colors (define once, use everywhere)
  static const Color primaryColor = Color(0xFF6366F1); // Indigo
  static const Color secondaryColor = Color(0xFF8B5CF6); // Purple
  static const Color errorColor = Color(0xFFEF4444); // Red
  static const Color successColor = Color(0xFF10B981); // Green
  static const Color warningColor = Color(0xFFF59E0B); // Amber

  // Firebase collection names
  static const String notesCollection = 'notes';
  static const String foldersCollection = 'folders';
  static const String tagsCollection = 'tags';
  static const String templatesCollection = 'templates';

  // Hive box names
  static const String notesBox = 'notes';
  static const String foldersBox = 'folders';
  static const String tagsBox = 'tags';
  static const String templatesBox = 'templates';
  static const String metadataBox = 'metadata';

  // Template placeholders
  static const String datePlaceholder = '{{date}}';
  static const String timePlaceholder = '{{time}}';
  static const String namePlaceholder = '{{name}}';
}
```

### 6. Exception Handling (DRY)

```dart
// lib/core/exceptions/app_exceptions.dart
abstract class AppException implements Exception {
  final String message;
  final String? code;
  final dynamic originalError;
  final StackTrace? stackTrace;

  AppException(
    this.message, {
    this.code,
    this.originalError,
    this.stackTrace,
  });

  @override
  String toString() => 'AppException: $message (code: $code)';
}

class NetworkException extends AppException {
  NetworkException(String message, {super.originalError, super.stackTrace})
      : super(message, code: 'NETWORK_ERROR');
}

class StorageException extends AppException {
  StorageException(String message, {super.originalError, super.stackTrace})
      : super(message, code: 'STORAGE_ERROR');
}

class ValidationException extends AppException {
  ValidationException(String message)
      : super(message, code: 'VALIDATION_ERROR');
}

class SyncException extends AppException {
  SyncException(String message, {super.originalError, super.stackTrace})
      : super(message, code: 'SYNC_ERROR');
}

class AuthException extends AppException {
  AuthException(String message, {super.originalError, super.stackTrace})
      : super(message, code: 'AUTH_ERROR');
}

class ImageException extends AppException {
  ImageException(String message, {super.originalError, super.stackTrace})
      : super(message, code: 'IMAGE_ERROR');
}

// Global error handler
class ErrorHandler {
  static void handle(dynamic error, StackTrace? stackTrace) {
    // Log to console in debug mode
    if (kDebugMode) {
      print('Error: $error');
      print('Stack trace: $stackTrace');
    }

    // Report to Crashlytics in production
    if (kReleaseMode) {
      FirebaseCrashlytics.instance.recordError(error, stackTrace);
    }

    // Show user-friendly message
    _showUserMessage(error);
  }

  static void _showUserMessage(dynamic error) {
    String message;

    if (error is NetworkException) {
      message = 'Network error. Please check your connection.';
    } else if (error is StorageException) {
      message = 'Storage error. Please try again.';
    } else if (error is ValidationException) {
      message = error.message; // Show specific validation error
    } else if (error is SyncException) {
      message = 'Sync failed. Changes will sync when online.';
    } else if (error is AuthException) {
      message = 'Authentication error. Please sign in again.';
    } else {
      message = 'An unexpected error occurred.';
    }

    // Show snackbar or dialog
    // Implementation depends on navigation setup
  }
}
```

### 7. Result Pattern (DRY)

```dart
// lib/core/result.dart
class Result<T> {
  final T? data;
  final AppException? error;

  bool get isSuccess => error == null;
  bool get isFailure => error != null;

  Result.success(this.data) : error = null;
  Result.failure(this.error) : data = null;

  // Helper: Transform result
  Result<U> map<U>(U Function(T data) transform) {
    if (isSuccess) {
      return Result.success(transform(data as T));
    } else {
      return Result.failure(error!);
    }
  }

  // Helper: Handle result
  void when({
    required void Function(T data) onSuccess,
    required void Function(AppException error) onFailure,
  }) {
    if (isSuccess) {
      onSuccess(data as T);
    } else {
      onFailure(error!);
    }
  }
}
```

### 8. Security Checklist

#### Before Every Commit
- [ ] No API keys or secrets in code
- [ ] `.env` file in `.gitignore`
- [ ] All user input validated
- [ ] SQL/NoSQL injection prevented
- [ ] XSS attacks prevented (sanitize HTML)
- [ ] File upload validation (size, type)
- [ ] Firebase rules restrict to authenticated users
- [ ] HTTPS only (no HTTP)
- [ ] No sensitive data in logs
- [ ] Error messages don't leak implementation details

#### Firebase Security Rules Template
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Helper functions (DRY)
    function isAuthenticated() {
      return request.auth != null;
    }

    function isOwner(userId) {
      return isAuthenticated() && request.auth.uid == userId;
    }

    function isValidString(field, maxLength) {
      return request.resource.data[field] is string
        && request.resource.data[field].size() <= maxLength;
    }

    function isValidNote() {
      return request.resource.data.keys().hasAll([
        'id', 'userId', 'title', 'content', 'createdAt', 'updatedAt', 'version'
      ])
      && request.resource.data.userId == request.auth.uid
      && isValidString('title', 200)
      && isValidString('content', 100000)
      && request.resource.data.version is int
      && request.resource.data.version >= 1;
    }

    // Security: All reads/writes require authentication
    match /users/{userId}/{document=**} {
      allow read: if isOwner(userId);

      match /notes/{noteId} {
        allow create: if isOwner(userId) && isValidNote();
        allow update: if isOwner(userId)
                      && resource.data.userId == userId
                      && isValidNote()
                      && request.resource.data.version > resource.data.version;
        allow delete: if isOwner(userId);
      }
    }
  }
}
```

### 9. Encryption Best Practices

```dart
// lib/utils/encryption.dart
import 'package:encrypt/encrypt.dart' as encrypt;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class EncryptionService {
  static const _storage = FlutterSecureStorage();
  static const _keyName = 'hive_encryption_key';

  // Generate or retrieve encryption key
  static Future<List<int>> getEncryptionKey() async {
    String? keyString = await _storage.read(key: _keyName);

    if (keyString == null) {
      // Generate new key
      final key = Hive.generateSecureKey();
      await _storage.write(
        key: _keyName,
        value: base64Encode(key),
      );
      return key;
    }

    return base64Decode(keyString);
  }

  // Encrypt sensitive note content
  static String encryptContent(String content, List<int> key) {
    final encrypter = encrypt.Encrypter(
      encrypt.AES(encrypt.Key(Uint8List.fromList(key))),
    );

    final iv = encrypt.IV.fromLength(16);
    final encrypted = encrypter.encrypt(content, iv: iv);

    return '${iv.base64}:${encrypted.base64}';
  }

  // Decrypt sensitive note content
  static String decryptContent(String encryptedContent, List<int> key) {
    final parts = encryptedContent.split(':');
    if (parts.length != 2) throw Exception('Invalid encrypted content');

    final iv = encrypt.IV.fromBase64(parts[0]);
    final encrypted = encrypt.Encrypted.fromBase64(parts[1]);

    final encrypter = encrypt.Encrypter(
      encrypt.AES(encrypt.Key(Uint8List.fromList(key))),
    );

    return encrypter.decrypt(encrypted, iv: iv);
  }
}
```

### 10. Dependency Injection (Abstraction)

```dart
// lib/core/di/service_locator.dart
import 'package:get_it/get_it.dart';

final getIt = GetIt.instance;

Future<void> setupServiceLocator() async {
  // Storage
  getIt.registerLazySingleton<ILocalStorage>(
    () => LocalStorageFactory.create(),
  );

  // Services
  getIt.registerLazySingleton<AuthService>(
    () => AuthService(FirebaseAuth.instance),
  );

  getIt.registerLazySingleton<SyncService>(
    () => SyncService(
      localStorage: getIt<ILocalStorage>(),
      firestore: FirebaseFirestore.instance,
      connectivity: Connectivity(),
    ),
  );

  getIt.registerLazySingleton<ImageService>(
    () => ImageService(
      storage: FirebaseStorage.instance,
      localStorage: getIt<ILocalStorage>(),
    ),
  );

  // Repositories
  getIt.registerLazySingleton<NoteRepository>(
    () => NoteRepository(
      localStorage: getIt<ILocalStorage>(),
    ),
  );

  // Initialize services
  await getIt<ILocalStorage>().init();
  getIt<SyncService>().startSyncService();
}

// Usage in main.dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  await setupServiceLocator();

  runApp(MyApp());
}

// Usage in widgets
class HomeScreen extends StatelessWidget {
  final NoteRepository repository = getIt<NoteRepository>();

  // ...
}
```

## Summary of Principles Applied

| Principle | Implementation |
|-----------|---------------|
| **No Secrets** | Environment variables, .gitignore, secure storage |
| **DRY** | Base classes, helpers, constants, validators |
| **Abstraction** | Interfaces, repositories, factories |
| **Security First** | Input validation, sanitization, encryption |
| **Helper Functions** | Centralized utilities, formatters, validators |
| **Error Handling** | Custom exceptions, global handler, Result pattern |
| **Dependency Injection** | Service locator, loose coupling |

This architecture ensures:
- ✅ No secrets exposed
- ✅ Code reuse through abstraction
- ✅ Security at every layer
- ✅ Easy testing with interfaces
- ✅ Maintainable and scalable

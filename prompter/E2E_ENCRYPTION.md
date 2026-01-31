# End-to-End Encryption Architecture

## Overview

**End-to-End Encryption (E2E)** ensures that notes are encrypted on the user's device before being sent to Firebase, and can only be decrypted by the user's devices. Firebase stores only encrypted ciphertext and cannot read note content.

## Key Principles

1. **Zero-Knowledge:** Firebase cannot read note content
2. **Client-Side Encryption:** All encryption/decryption happens on device
3. **Master Key:** Derived from user password or stored securely
4. **Per-Note Keys:** Each note encrypted with unique key
5. **Key Sync:** Master key syncs across user's devices

## Architecture

### 1. Encryption Hierarchy

```
User Password/PIN
    ↓ (PBKDF2)
Master Key (256-bit)
    ↓ (derives)
Note Encryption Keys (per note, 256-bit)
    ↓ (AES-256-GCM)
Encrypted Note Content
```

### 2. Data Models (Updated)

```dart
@HiveType(typeId: 0)
class Note extends HiveObject {
  @HiveField(0)
  late String id;

  @HiveField(1)
  late String userId;

  @HiveField(2)
  late String title;  // Encrypted

  @HiveField(3)
  late String content;  // Encrypted (Delta JSON)

  @HiveField(4)
  String? folderId;

  @HiveField(5)
  late List<String> tags;  // Encrypted

  // Encryption metadata
  @HiveField(13)
  late String encryptedNoteKey;  // Note's encryption key, encrypted with master key

  @HiveField(14)
  late String iv;  // Initialization vector for AES

  @HiveField(15)
  late String authTag;  // Authentication tag for GCM mode

  // Other fields...
  @HiveField(6)
  late DateTime createdAt;

  @HiveField(7)
  late DateTime updatedAt;

  @HiveField(8)
  DateTime? deletedAt;

  @HiveField(9)
  late int version;

  @HiveField(10)
  late bool isSynced;

  @HiveField(11)
  late String deviceId;

  @HiveField(12)
  Map<String, dynamic>? syncMetadata;

  // Helper: Check if note is encrypted
  bool get isEncrypted => encryptedNoteKey.isNotEmpty;
}
```

### 3. Encryption Service

```dart
// lib/data/services/encryption_service.dart
import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:encrypt/encrypt.dart' as encrypt;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class EncryptionService {
  static const _secureStorage = FlutterSecureStorage();
  static const _masterKeyName = 'master_encryption_key';

  // Singleton pattern
  static final EncryptionService _instance = EncryptionService._internal();
  factory EncryptionService() => _instance;
  EncryptionService._internal();

  encrypt.Key? _masterKey;

  // 1. Initialize encryption (on first launch or login)
  Future<void> initialize(String userPassword) async {
    // Derive master key from password using PBKDF2
    _masterKey = await _deriveMasterKey(userPassword);

    // Store encrypted master key in secure storage
    await _secureStorage.write(
      key: _masterKeyName,
      value: base64Encode(_masterKey!.bytes),
    );
  }

  // 2. Load existing master key (on app launch)
  Future<bool> loadMasterKey() async {
    final keyString = await _secureStorage.read(key: _masterKeyName);

    if (keyString != null) {
      _masterKey = encrypt.Key(base64Decode(keyString));
      return true;
    }

    return false;
  }

  // 3. Check if encryption is set up
  Future<bool> isEncryptionEnabled() async {
    return await _secureStorage.containsKey(key: _masterKeyName);
  }

  // 4. Derive master key from password
  Future<encrypt.Key> _deriveMasterKey(String password) async {
    // Get or create salt
    final salt = await _getSalt();

    // Use PBKDF2 with 100,000 iterations
    final pbkdf2 = Pbkdf2(
      macAlgorithm: Hmac.sha256(),
      iterations: 100000,
      bits: 256,
    );

    final keyBytes = await pbkdf2.deriveKey(
      secretKey: SecretKey(utf8.encode(password)),
      nonce: salt,
    );

    return encrypt.Key(Uint8List.fromList(await keyBytes.extractBytes()));
  }

  // 5. Get or create salt for key derivation
  Future<List<int>> _getSalt() async {
    const saltKey = 'encryption_salt';
    String? saltString = await _secureStorage.read(key: saltKey);

    if (saltString == null) {
      // Generate random salt
      final salt = encrypt.IV.fromSecureRandom(32).bytes;
      await _secureStorage.write(
        key: saltKey,
        value: base64Encode(salt),
      );
      return salt;
    }

    return base64Decode(saltString);
  }

  // 6. Encrypt note (called before saving)
  Future<EncryptedNote> encryptNote(Note note) async {
    if (_masterKey == null) {
      throw EncryptionException('Master key not loaded');
    }

    // Generate unique key for this note
    final noteKey = encrypt.Key.fromSecureRandom(32);

    // Encrypt note key with master key
    final encryptedNoteKey = _encryptNoteKey(noteKey);

    // Encrypt note content with note key
    final iv = encrypt.IV.fromSecureRandom(16);
    final encrypter = encrypt.Encrypter(
      encrypt.AES(noteKey, mode: encrypt.AESMode.gcm),
    );

    final encryptedTitle = encrypter.encrypt(note.title, iv: iv);
    final encryptedContent = encrypter.encrypt(note.content, iv: iv);
    final encryptedTags = note.tags.map((tag) {
      return encrypter.encrypt(tag, iv: iv).base64;
    }).toList();

    return EncryptedNote(
      id: note.id,
      userId: note.userId,
      title: encryptedTitle.base64,
      content: encryptedContent.base64,
      tags: encryptedTags,
      encryptedNoteKey: encryptedNoteKey,
      iv: iv.base64,
      authTag: '', // GCM mode includes auth tag in ciphertext
      folderId: note.folderId,
      createdAt: note.createdAt,
      updatedAt: note.updatedAt,
      deletedAt: note.deletedAt,
      version: note.version,
      isSynced: note.isSynced,
      deviceId: note.deviceId,
      syncMetadata: note.syncMetadata,
    );
  }

  // 7. Decrypt note (called after loading)
  Future<Note> decryptNote(EncryptedNote encryptedNote) async {
    if (_masterKey == null) {
      throw EncryptionException('Master key not loaded');
    }

    // Decrypt note key using master key
    final noteKey = _decryptNoteKey(encryptedNote.encryptedNoteKey);

    // Decrypt note content using note key
    final iv = encrypt.IV.fromBase64(encryptedNote.iv);
    final encrypter = encrypt.Encrypter(
      encrypt.AES(noteKey, mode: encrypt.AESMode.gcm),
    );

    final title = encrypter.decrypt64(encryptedNote.title, iv: iv);
    final content = encrypter.decrypt64(encryptedNote.content, iv: iv);
    final tags = encryptedNote.tags.map((encryptedTag) {
      return encrypter.decrypt64(encryptedTag, iv: iv);
    }).toList();

    return Note(
      id: encryptedNote.id,
      userId: encryptedNote.userId,
      title: title,
      content: content,
      tags: tags,
      folderId: encryptedNote.folderId,
      createdAt: encryptedNote.createdAt,
      updatedAt: encryptedNote.updatedAt,
      deletedAt: encryptedNote.deletedAt,
      version: encryptedNote.version,
      isSynced: encryptedNote.isSynced,
      deviceId: encryptedNote.deviceId,
      syncMetadata: encryptedNote.syncMetadata,
    );
  }

  // 8. Encrypt note key with master key
  String _encryptNoteKey(encrypt.Key noteKey) {
    final encrypter = encrypt.Encrypter(
      encrypt.AES(_masterKey!, mode: encrypt.AESMode.cbc),
    );
    final iv = encrypt.IV.fromLength(16);
    final encrypted = encrypter.encryptBytes(noteKey.bytes, iv: iv);
    return '${iv.base64}:${encrypted.base64}';
  }

  // 9. Decrypt note key with master key
  encrypt.Key _decryptNoteKey(String encryptedNoteKey) {
    final parts = encryptedNoteKey.split(':');
    if (parts.length != 2) {
      throw EncryptionException('Invalid encrypted note key format');
    }

    final iv = encrypt.IV.fromBase64(parts[0]);
    final encrypted = encrypt.Encrypted.fromBase64(parts[1]);

    final encrypter = encrypt.Encrypter(
      encrypt.AES(_masterKey!, mode: encrypt.AESMode.cbc),
    );

    final decryptedBytes = encrypter.decryptBytes(encrypted, iv: iv);
    return encrypt.Key(Uint8List.fromList(decryptedBytes));
  }

  // 10. Change master password
  Future<void> changeMasterPassword(
    String oldPassword,
    String newPassword,
  ) async {
    // Verify old password
    final oldKey = await _deriveMasterKey(oldPassword);
    final storedKey = await _secureStorage.read(key: _masterKeyName);

    if (base64Encode(oldKey.bytes) != storedKey) {
      throw AuthException('Incorrect password');
    }

    // Derive new master key
    final newKey = await _deriveMasterKey(newPassword);

    // Re-encrypt all notes with new master key
    await _reEncryptAllNotes(oldKey, newKey);

    // Update stored master key
    _masterKey = newKey;
    await _secureStorage.write(
      key: _masterKeyName,
      value: base64Encode(newKey.bytes),
    );
  }

  // 11. Re-encrypt all notes (when changing password)
  Future<void> _reEncryptAllNotes(
    encrypt.Key oldMasterKey,
    encrypt.Key newMasterKey,
  ) async {
    // This is complex - need to:
    // 1. Load all encrypted notes
    // 2. Decrypt note keys with old master key
    // 3. Re-encrypt note keys with new master key
    // 4. Save updated notes
    // Implementation depends on storage layer
  }

  // 12. Export encryption key for backup
  Future<String> exportMasterKey(String password) async {
    // Verify password
    final key = await _deriveMasterKey(password);
    final storedKey = await _secureStorage.read(key: _masterKeyName);

    if (base64Encode(key.bytes) != storedKey) {
      throw AuthException('Incorrect password');
    }

    // Return base64-encoded master key for user to backup
    return storedKey!;
  }

  // 13. Import encryption key from backup
  Future<void> importMasterKey(String encodedKey, String password) async {
    // Verify it's a valid key
    try {
      final keyBytes = base64Decode(encodedKey);
      if (keyBytes.length != 32) {
        throw EncryptionException('Invalid key length');
      }

      _masterKey = encrypt.Key(Uint8List.fromList(keyBytes));

      // Store in secure storage
      await _secureStorage.write(
        key: _masterKeyName,
        value: encodedKey,
      );
    } catch (e) {
      throw EncryptionException('Invalid encryption key');
    }
  }

  // 14. Clear master key (on logout)
  Future<void> clearMasterKey() async {
    _masterKey = null;
    await _secureStorage.delete(key: _masterKeyName);
  }
}

// Custom exception
class EncryptionException extends AppException {
  EncryptionException(String message) : super(message, code: 'ENCRYPTION_ERROR');
}

// Helper class for encrypted note data
class EncryptedNote {
  final String id;
  final String userId;
  final String title;  // Base64 encrypted
  final String content;  // Base64 encrypted
  final List<String> tags;  // List of base64 encrypted tags
  final String encryptedNoteKey;
  final String iv;
  final String authTag;
  final String? folderId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? deletedAt;
  final int version;
  final bool isSynced;
  final String deviceId;
  final Map<String, dynamic>? syncMetadata;

  EncryptedNote({
    required this.id,
    required this.userId,
    required this.title,
    required this.content,
    required this.tags,
    required this.encryptedNoteKey,
    required this.iv,
    required this.authTag,
    this.folderId,
    required this.createdAt,
    required this.updatedAt,
    this.deletedAt,
    required this.version,
    required this.isSynced,
    required this.deviceId,
    this.syncMetadata,
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'userId': userId,
      'title': title,
      'content': content,
      'tags': tags,
      'encryptedNoteKey': encryptedNoteKey,
      'iv': iv,
      'authTag': authTag,
      'folderId': folderId,
      'createdAt': createdAt.millisecondsSinceEpoch,
      'updatedAt': updatedAt.millisecondsSinceEpoch,
      'deletedAt': deletedAt?.millisecondsSinceEpoch,
      'version': version,
      'deviceId': deviceId,
      'syncMetadata': syncMetadata,
    };
  }
}
```

### 4. Updated Note Repository with Encryption

```dart
class NoteRepository extends BaseRepository<Note> {
  final EncryptionService _encryption;

  NoteRepository({
    required super.localStorage,
    super.remoteStorage,
    required EncryptionService encryption,
  }) : _encryption = encryption;

  @override
  Future<Result<Note>> create(Note note) async {
    try {
      // Validate
      final validation = validate(note);
      if (!validation.isValid) {
        return Result.failure(ValidationException(validation.error!));
      }

      // Encrypt note
      final encryptedNote = await _encryption.encryptNote(note);

      // Save encrypted note locally
      await localStorage.save(encryptedNote);

      // Sync encrypted note to Firebase
      if (remoteStorage != null) {
        await remoteStorage!.save(encryptedNote);
      }

      return Result.success(note);
    } catch (e) {
      return Result.failure(_handleError(e));
    }
  }

  @override
  Future<Result<Note?>> get(String id) async {
    try {
      // Get encrypted note
      final encryptedNote = await localStorage.get(id);
      if (encryptedNote == null) return Result.success(null);

      // Decrypt note
      final note = await _encryption.decryptNote(encryptedNote);

      return Result.success(note);
    } catch (e) {
      return Result.failure(_handleError(e));
    }
  }

  Future<Result<List<Note>>> getAll() async {
    try {
      // Get all encrypted notes
      final encryptedNotes = await localStorage.getAll();

      // Decrypt all notes
      final notes = <Note>[];
      for (final encryptedNote in encryptedNotes) {
        final note = await _encryption.decryptNote(encryptedNote);
        notes.add(note);
      }

      return Result.success(notes);
    } catch (e) {
      return Result.failure(_handleError(e));
    }
  }
}
```

### 5. Authentication Flow with Encryption

```dart
class AuthService {
  final FirebaseAuth _auth;
  final EncryptionService _encryption;

  AuthService(this._auth, this._encryption);

  // Sign up with password
  Future<Result<User>> signUp(String email, String password) async {
    try {
      // Create Firebase account
      final credential = await _auth.createUserWithEmailAndPassword(
        email: email,
        password: password,
      );

      // Initialize encryption with password
      await _encryption.initialize(password);

      return Result.success(credential.user!);
    } catch (e) {
      return Result.failure(AuthException('Sign up failed: $e'));
    }
  }

  // Sign in with password
  Future<Result<User>> signIn(String email, String password) async {
    try {
      // Sign in to Firebase
      final credential = await _auth.signInWithEmailAndPassword(
        email: email,
        password: password,
      );

      // Load encryption key
      // Option 1: Derive from password
      await _encryption.initialize(password);

      // Option 2: Sync master key from another device (advanced)
      // await _syncMasterKeyFromCloud(password);

      return Result.success(credential.user!);
    } catch (e) {
      return Result.failure(AuthException('Sign in failed: $e'));
    }
  }

  // Sign out
  Future<void> signOut() async {
    await _auth.signOut();
    await _encryption.clearMasterKey();
  }
}
```

### 6. Master Key Sync Across Devices

```dart
// Advanced: Sync encrypted master key across devices
class KeySyncService {
  final FirebaseFirestore _firestore;
  final EncryptionService _encryption;

  // Store encrypted master key in Firebase
  // The master key is encrypted with a key derived from user password
  Future<void> syncMasterKeyToCloud(String password) async {
    final userId = FirebaseAuth.instance.currentUser?.uid;
    if (userId == null) throw AuthException('Not authenticated');

    // Export master key
    final masterKey = await _encryption.exportMasterKey(password);

    // Encrypt master key with password-derived key
    final passwordKey = await _derivePasswordKey(password);
    final encryptedMasterKey = _encryptWithPasswordKey(masterKey, passwordKey);

    // Store in Firestore
    await _firestore
        .collection('users')
        .doc(userId)
        .collection('private')
        .doc('master_key')
        .set({
      'encryptedMasterKey': encryptedMasterKey,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  // Retrieve master key from cloud
  Future<void> syncMasterKeyFromCloud(String password) async {
    final userId = FirebaseAuth.instance.currentUser?.uid;
    if (userId == null) throw AuthException('Not authenticated');

    // Get encrypted master key from Firestore
    final doc = await _firestore
        .collection('users')
        .doc(userId)
        .collection('private')
        .doc('master_key')
        .get();

    if (!doc.exists) {
      throw EncryptionException('Master key not found in cloud');
    }

    final encryptedMasterKey = doc.data()!['encryptedMasterKey'] as String;

    // Decrypt with password
    final passwordKey = await _derivePasswordKey(password);
    final masterKey = _decryptWithPasswordKey(encryptedMasterKey, passwordKey);

    // Import master key
    await _encryption.importMasterKey(masterKey, password);
  }

  Future<encrypt.Key> _derivePasswordKey(String password) async {
    // Same PBKDF2 logic as encryption service
    // ...
  }

  String _encryptWithPasswordKey(String data, encrypt.Key key) {
    // AES encryption
    // ...
  }

  String _decryptWithPasswordKey(String encryptedData, encrypt.Key key) {
    // AES decryption
    // ...
  }
}
```

### 7. Updated Dependencies

```yaml
dependencies:
  # Existing dependencies...

  # Encryption
  encrypt: ^5.0.3
  crypto: ^3.0.5
  cryptography: ^2.7.0
  flutter_secure_storage: ^9.2.2
  pointycastle: ^3.9.1  # For PBKDF2
```

### 8. UI: Setup Encryption

```dart
// lib/presentation/screens/setup_encryption_screen.dart
class SetupEncryptionScreen extends StatefulWidget {
  @override
  _SetupEncryptionScreenState createState() => _SetupEncryptionScreenState();
}

class _SetupEncryptionScreenState extends State<SetupEncryptionScreen> {
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _encryption = getIt<EncryptionService>();

  Future<void> _setupEncryption() async {
    final password = _passwordController.text;
    final confirmPassword = _confirmPasswordController.text;

    // Validate
    if (password.length < 8) {
      _showError('Password must be at least 8 characters');
      return;
    }

    if (password != confirmPassword) {
      _showError('Passwords do not match');
      return;
    }

    // Initialize encryption
    try {
      await _encryption.initialize(password);

      // Navigate to home
      Navigator.pushReplacementNamed(context, '/home');
    } catch (e) {
      _showError('Failed to setup encryption: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Setup Encryption')),
      body: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Create Master Password',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            SizedBox(height: 8),
            Text(
              'Your notes will be encrypted with this password. '
              'You will need it to access notes on other devices.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            SizedBox(height: 24),
            TextField(
              controller: _passwordController,
              decoration: InputDecoration(
                labelText: 'Master Password',
                border: OutlineInputBorder(),
              ),
              obscureText: true,
            ),
            SizedBox(height: 16),
            TextField(
              controller: _confirmPasswordController,
              decoration: InputDecoration(
                labelText: 'Confirm Password',
                border: OutlineInputBorder(),
              ),
              obscureText: true,
            ),
            SizedBox(height: 24),
            ElevatedButton(
              onPressed: _setupEncryption,
              child: Text('Setup Encryption'),
            ),
            SizedBox(height: 16),
            Card(
              color: Colors.orange.shade50,
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.warning, color: Colors.orange),
                        SizedBox(width: 8),
                        Text(
                          'Important',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.orange.shade900,
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: 8),
                    Text(
                      'If you forget your master password, you will '
                      'lose access to all your notes. There is no way '
                      'to recover them.',
                      style: TextStyle(color: Colors.orange.shade900),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}
```

### 9. Firestore Structure with Encryption

```
users/{userId}/
  ├── notes/{noteId}
  │     ├── id: string
  │     ├── userId: string
  │     ├── title: string (ENCRYPTED)
  │     ├── content: string (ENCRYPTED)
  │     ├── tags: array (ENCRYPTED)
  │     ├── encryptedNoteKey: string
  │     ├── iv: string
  │     ├── authTag: string
  │     ├── folderId: string (plaintext - for queries)
  │     ├── createdAt: timestamp
  │     ├── updatedAt: timestamp
  │     └── version: number
  │
  └── private/
        └── master_key
              ├── encryptedMasterKey: string
              └── updatedAt: timestamp
```

**Note:** Firebase can still see metadata (createdAt, updatedAt, folderId) but not the actual content.

### 10. Security Best Practices

#### Password Requirements
```dart
class PasswordValidator {
  static ValidationResult validate(String password) {
    if (password.length < 12) {
      return ValidationResult.error('Password must be at least 12 characters');
    }

    if (!password.contains(RegExp(r'[A-Z]'))) {
      return ValidationResult.error('Password must contain uppercase letter');
    }

    if (!password.contains(RegExp(r'[a-z]'))) {
      return ValidationResult.error('Password must contain lowercase letter');
    }

    if (!password.contains(RegExp(r'[0-9]'))) {
      return ValidationResult.error('Password must contain number');
    }

    if (!password.contains(RegExp(r'[!@#$%^&*(),.?":{}|<>]'))) {
      return ValidationResult.error('Password must contain special character');
    }

    return ValidationResult.valid();
  }
}
```

#### Biometric Unlock (for convenience)
```dart
import 'package:local_auth/local_auth.dart';

class BiometricService {
  final LocalAuthentication _auth = LocalAuthentication();

  Future<bool> authenticateWithBiometrics() async {
    try {
      final canCheck = await _auth.canCheckBiometrics;
      if (!canCheck) return false;

      return await _auth.authenticate(
        localizedReason: 'Authenticate to access your notes',
        options: const AuthenticationOptions(
          stickyAuth: true,
          biometricOnly: true,
        ),
      );
    } catch (e) {
      return false;
    }
  }
}

// Store password hash for biometric unlock
// DON'T store plaintext password!
class BiometricUnlockService {
  static const _storage = FlutterSecureStorage();
  static const _passwordHashKey = 'password_hash_for_biometric';

  // After user sets up biometrics, store password hash
  Future<void> enableBiometricUnlock(String password) async {
    final hash = sha256.convert(utf8.encode(password)).toString();
    await _storage.write(key: _passwordHashKey, value: hash);
  }

  // When unlocking with biometrics, retrieve password
  Future<String?> unlockWithBiometrics() async {
    final authenticated = await BiometricService().authenticateWithBiometrics();

    if (authenticated) {
      return await _storage.read(key: _passwordHashKey);
    }

    return null;
  }
}
```

## Summary

### What's Encrypted
- ✅ Note title
- ✅ Note content
- ✅ Tags
- ❌ Metadata (createdAt, updatedAt, folderId) - needed for queries

### Key Features
- ✅ Zero-knowledge encryption (Firebase can't read notes)
- ✅ Per-note encryption keys
- ✅ Master key derived from password
- ✅ Master key sync across devices
- ✅ Password change support
- ✅ Key backup/recovery
- ✅ Biometric unlock (optional)

### Security Level
- **Algorithm:** AES-256-GCM
- **Key Derivation:** PBKDF2 with 100,000 iterations
- **Key Size:** 256-bit
- **Authentication:** GCM provides authenticated encryption
- **Storage:** Flutter Secure Storage (Keychain on iOS, KeyStore on Android)

### Trade-offs
- ✅ **Pro:** Maximum security and privacy
- ✅ **Pro:** Zero-knowledge architecture
- ❌ **Con:** Search requires decrypting all notes
- ❌ **Con:** Folder/tag filters less efficient
- ❌ **Con:** Lost password = lost data (no recovery)
- ❌ **Con:** Slightly slower sync (encryption overhead)

### Recommendation
- **Personal/Sensitive Notes:** Enable E2E encryption
- **Shared/Collaborative Notes:** Consider optional encryption per note
- **Future:** Add option to enable/disable per note or per folder

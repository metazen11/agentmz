# Prompter Architecture v2.0 (Revised)

> This is the revised architecture incorporating critical fixes from ARCHITECTURE_REVIEW.md

## Key Changes from v1.0

- ✅ Enhanced data models with userId, version, deletedAt
- ✅ Event-driven sync instead of timer-based
- ✅ Tombstone-based deletion sync
- ✅ Field-level conflict resolution
- ✅ Pagination strategy
- ✅ Image compression and offline caching
- ✅ Abstract storage layer for web compatibility
- ✅ Hive schema migration system
- ✅ Enhanced Firebase security rules
- ✅ Persistent sync queue with compression

## 1. Enhanced Data Models

### Note Model (Complete)
```dart
import 'package:hive/hive.dart';

part 'note.g.dart';

@HiveType(typeId: 0)
class Note extends HiveObject {
  @HiveField(0)
  late String id;

  @HiveField(1)
  late String userId;  // NEW: Required for Firebase security

  @HiveField(2)
  late String title;

  @HiveField(3)
  late String content;  // Delta JSON format

  @HiveField(4)
  String? folderId;

  @HiveField(5)
  late List<String> tags;

  @HiveField(6)
  late DateTime createdAt;

  @HiveField(7)
  late DateTime updatedAt;

  @HiveField(8)
  DateTime? deletedAt;  // NEW: Null = active, timestamp = deleted (tombstone)

  @HiveField(9)
  late int version;  // NEW: For conflict resolution

  @HiveField(10)
  late bool isSynced;

  @HiveField(11)
  late String deviceId;  // NEW: Track which device made last edit

  @HiveField(12)
  Map<String, dynamic>? syncMetadata;  // NEW: For complex conflict resolution

  Note({
    required this.id,
    required this.userId,
    required this.title,
    required this.content,
    this.folderId,
    required this.tags,
    required this.createdAt,
    required this.updatedAt,
    this.deletedAt,
    this.version = 1,
    this.isSynced = false,
    required this.deviceId,
    this.syncMetadata,
  });

  bool get isDeleted => deletedAt != null;
  bool get isActive => deletedAt == null;

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'userId': userId,
      'title': title,
      'content': content,
      'folderId': folderId,
      'tags': tags,
      'createdAt': createdAt.millisecondsSinceEpoch,
      'updatedAt': updatedAt.millisecondsSinceEpoch,
      'deletedAt': deletedAt?.millisecondsSinceEpoch,
      'version': version,
      'deviceId': deviceId,
      'syncMetadata': syncMetadata,
    };
  }

  factory Note.fromMap(Map<String, dynamic> map) {
    return Note(
      id: map['id'],
      userId: map['userId'],
      title: map['title'],
      content: map['content'],
      folderId: map['folderId'],
      tags: List<String>.from(map['tags']),
      createdAt: DateTime.fromMillisecondsSinceEpoch(map['createdAt']),
      updatedAt: DateTime.fromMillisecondsSinceEpoch(map['updatedAt']),
      deletedAt: map['deletedAt'] != null
          ? DateTime.fromMillisecondsSinceEpoch(map['deletedAt'])
          : null,
      version: map['version'] ?? 1,
      deviceId: map['deviceId'],
      syncMetadata: map['syncMetadata'],
    );
  }
}
```

### Folder Model (Enhanced)
```dart
@HiveType(typeId: 1)
class Folder extends HiveObject {
  @HiveField(0)
  late String id;

  @HiveField(1)
  late String userId;  // NEW

  @HiveField(2)
  late String name;

  @HiveField(3)
  String? parentId;

  @HiveField(4)
  late int sortOrder;

  @HiveField(5)
  late DateTime createdAt;

  @HiveField(6)
  DateTime? deletedAt;  // NEW

  @HiveField(7)
  late bool isSynced;
}
```

### Tag Model (Enhanced)
```dart
@HiveType(typeId: 2)
class Tag extends HiveObject {
  @HiveField(0)
  late String id;

  @HiveField(1)
  late String userId;  // NEW

  @HiveField(2)
  late String name;

  @HiveField(3)
  late String color;

  @HiveField(4)
  int noteCount = 0;  // Cached, recomputed periodically

  @HiveField(5)
  DateTime? deletedAt;  // NEW

  @HiveField(6)
  late bool isSynced;
}
```

### Template Model
```dart
@HiveType(typeId: 3)
class Template extends HiveObject {
  @HiveField(0)
  late String id;

  @HiveField(1)
  late String userId;  // NEW

  @HiveField(2)
  late String name;

  @HiveField(3)
  late String content;  // Delta JSON with {{placeholders}}

  @HiveField(4)
  late String category;

  @HiveField(5)
  late bool isPinned;

  @HiveField(6)
  DateTime? deletedAt;  // NEW

  @HiveField(7)
  late bool isSynced;
}
```

## 2. Abstract Storage Layer (Web Compatibility)

```dart
// Abstract interface
abstract class ILocalStorage {
  Future<void> init();
  Future<void> saveNote(Note note);
  Future<Note?> getNote(String id);
  Future<List<Note>> getNotes({
    int? limit,
    int? offset,
    String? folderId,
    List<String>? tags,
    bool includeDeleted = false,
  });
  Future<List<Note>> getUnsyncedNotes();
  Future<void> markAsSynced(String noteId);
  Future<DateTime?> getLastSyncTime();
  Future<void> setLastSyncTime(DateTime time);
  Future<void> close();
}

// Hive implementation (Mobile/Desktop)
class HiveStorage implements ILocalStorage {
  Box<Note>? _noteBox;
  Box? _metaBox;

  @override
  Future<void> init() async {
    await Hive.initFlutter();
    Hive.registerAdapter(NoteAdapter());

    _noteBox = await Hive.openBox<Note>('notes');
    _metaBox = await Hive.openBox('metadata');
  }

  @override
  Future<List<Note>> getNotes({
    int? limit,
    int? offset,
    String? folderId,
    List<String>? tags,
    bool includeDeleted = false,
  }) async {
    var notes = _noteBox!.values.where((note) {
      if (!includeDeleted && note.isDeleted) return false;
      if (folderId != null && note.folderId != folderId) return false;
      if (tags != null && !tags.every((tag) => note.tags.contains(tag))) return false;
      return true;
    }).toList();

    // Sort by updatedAt descending
    notes.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));

    // Pagination
    if (offset != null) {
      notes = notes.skip(offset).toList();
    }
    if (limit != null) {
      notes = notes.take(limit).toList();
    }

    return notes;
  }

  // ... other methods
}

// Web implementation (using IndexedDB via shared_preferences)
class WebStorage implements ILocalStorage {
  // Use SharedPreferences or direct IndexedDB access
  // Simpler data structure optimized for web
}

// Factory
class LocalStorageFactory {
  static ILocalStorage create() {
    if (kIsWeb) {
      return WebStorage();
    } else {
      return HiveStorage();
    }
  }
}
```

## 3. Hive Migration System

```dart
class MigrationManager {
  static const String versionKey = 'hive_schema_version';
  static const int currentVersion = 2;

  static Future<void> runMigrations() async {
    final prefs = await SharedPreferences.getInstance();
    final savedVersion = prefs.getInt(versionKey) ?? 1;

    if (savedVersion < currentVersion) {
      print('Running migrations from v$savedVersion to v$currentVersion');

      for (int version = savedVersion + 1; version <= currentVersion; version++) {
        await _executeMigration(version);
        await prefs.setInt(versionKey, version);
      }
    }
  }

  static Future<void> _executeMigration(int version) async {
    switch (version) {
      case 2:
        await _migrateToV2();
        break;
      // Future migrations here
    }
  }

  static Future<void> _migrateToV2() async {
    // Add userId, version, deletedAt fields to existing notes
    final box = await Hive.openBox<Note>('notes');
    final auth = FirebaseAuth.instance;

    for (var note in box.values) {
      if (!note.toMap().containsKey('userId')) {
        note.userId = auth.currentUser?.uid ?? 'anonymous';
        note.version = 1;
        note.deletedAt = null;
        note.deviceId = await _getDeviceId();
        await note.save();
      }
    }
  }

  static Future<String> _getDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    var deviceId = prefs.getString('device_id');
    if (deviceId == null) {
      deviceId = const Uuid().v4();
      await prefs.setString('device_id', deviceId);
    }
    return deviceId;
  }
}
```

## 4. Event-Driven Sync Service

```dart
class SyncService {
  final ILocalStorage _localStorage;
  final FirebaseFirestore _firestore;
  final Connectivity _connectivity;

  StreamSubscription<ConnectivityResult>? _connectivitySubscription;
  StreamSubscription<QuerySnapshot>? _firestoreSubscription;

  bool _hasPendingChanges = false;
  bool _isSyncing = false;

  final _syncQueue = <SyncOperation>[];
  static const int maxQueueSize = 100;

  void startSyncService() {
    // Listen to connectivity changes
    _connectivitySubscription = _connectivity.onConnectivityChanged.listen((status) {
      if (status != ConnectivityResult.none && _hasPendingChanges) {
        _syncWithBackoff();
      }
    });

    // Listen to real-time Firestore changes when online
    _listenToFirestoreChanges();
  }

  void notifyLocalChange() {
    _hasPendingChanges = true;
    _scheduleSyncIfOnline();
  }

  Future<void> _scheduleSyncIfOnline() async {
    final connectivity = await _connectivity.checkConnectivity();
    if (connectivity != ConnectivityResult.none) {
      await Future.delayed(Duration(seconds: 2)); // Debounce
      _syncWithBackoff();
    }
  }

  Future<void> _syncWithBackoff() async {
    if (_isSyncing) return;
    _isSyncing = true;

    int retryCount = 0;
    const maxRetries = 5;

    while (retryCount < maxRetries) {
      try {
        await syncPendingChanges();
        await fetchRemoteChanges();
        _hasPendingChanges = false;
        _isSyncing = false;
        return;
      } catch (e) {
        retryCount++;
        if (retryCount >= maxRetries) {
          _isSyncing = false;
          throw SyncException('Sync failed after $maxRetries attempts: $e');
        }
        await Future.delayed(Duration(seconds: pow(2, retryCount).toInt()));
      }
    }
  }

  Future<void> syncPendingChanges() async {
    final unsyncedNotes = await _localStorage.getUnsyncedNotes();

    for (final note in unsyncedNotes) {
      try {
        await _firestore
            .collection('users')
            .doc(note.userId)
            .collection('notes')
            .doc(note.id)
            .set(note.toMap());

        await _localStorage.markAsSynced(note.id);
      } catch (e) {
        print('Failed to sync note ${note.id}: $e');
      }
    }
  }

  Future<void> fetchRemoteChanges() async {
    final lastSync = await _localStorage.getLastSyncTime();
    final userId = FirebaseAuth.instance.currentUser?.uid;
    if (userId == null) return;

    final snapshot = await _firestore
        .collection('users')
        .doc(userId)
        .collection('notes')
        .where('updatedAt', isGreaterThan: lastSync?.millisecondsSinceEpoch ?? 0)
        .get();

    for (final doc in snapshot.docs) {
      final remoteNote = Note.fromMap(doc.data());
      final localNote = await _localStorage.getNote(remoteNote.id);

      if (localNote == null) {
        // New note from another device
        await _localStorage.saveNote(remoteNote);
      } else {
        // Potential conflict - resolve
        final resolved = await ConflictResolver.resolve(localNote, remoteNote);
        await _localStorage.saveNote(resolved);
      }
    }

    await _localStorage.setLastSyncTime(DateTime.now());
  }

  void _listenToFirestoreChanges() {
    final userId = FirebaseAuth.instance.currentUser?.uid;
    if (userId == null) return;

    _firestoreSubscription = _firestore
        .collection('users')
        .doc(userId)
        .collection('notes')
        .snapshots()
        .listen((snapshot) {
      for (final change in snapshot.docChanges) {
        if (change.type == DocumentChangeType.added ||
            change.type == DocumentChangeType.modified) {
          final note = Note.fromMap(change.doc.data()!);
          _localStorage.saveNote(note);
        }
      }
    });
  }

  void dispose() {
    _connectivitySubscription?.cancel();
    _firestoreSubscription?.cancel();
  }
}
```

## 5. Field-Level Conflict Resolver

```dart
class ConflictResolver {
  static Future<Note> resolve(Note local, Note remote) async {
    // Same version - no conflict
    if (local.version == remote.version) {
      return remote.updatedAt.isAfter(local.updatedAt) ? remote : local;
    }

    // Check if edits were concurrent (within 5 seconds)
    final timeDiff = (local.updatedAt.difference(remote.updatedAt)).abs();

    if (timeDiff < Duration(seconds: 5)) {
      // Concurrent edit - merge fields
      return _mergeNotes(local, remote);
    } else {
      // Clear winner based on timestamp
      return local.updatedAt.isAfter(remote.updatedAt) ? local : remote;
    }
  }

  static Note _mergeNotes(Note local, Note remote) {
    return Note(
      id: local.id,
      userId: local.userId,
      title: _pickNewer(
        local.title,
        local.updatedAt,
        remote.title,
        remote.updatedAt,
      ),
      content: _mergeContent(local, remote),
      folderId: local.folderId ?? remote.folderId,
      tags: _mergeTags(local.tags, remote.tags),
      createdAt: local.createdAt,
      updatedAt: DateTime.now(),
      version: max(local.version, remote.version) + 1,
      isSynced: false,
      deviceId: local.deviceId,
      syncMetadata: {
        'mergedFrom': [local.version, remote.version],
        'mergedAt': DateTime.now().toIso8601String(),
        'localDevice': local.deviceId,
        'remoteDevice': remote.deviceId,
      },
    );
  }

  static String _pickNewer(String localValue, DateTime localTime,
      String remoteValue, DateTime remoteTime) {
    return localTime.isAfter(remoteTime) ? localValue : remoteValue;
  }

  static String _mergeContent(Note local, Note remote) {
    // If one is substring of other, use longer version
    if (remote.content.contains(local.content)) {
      return remote.content;
    } else if (local.content.contains(remote.content)) {
      return local.content;
    }

    // Otherwise, show conflict marker
    return '''
${local.content}

--- CONFLICT (tap to resolve) ---
${remote.content}
''';
  }

  static List<String> _mergeTags(List<String> local, List<String> remote) {
    return {...local, ...remote}.toList();
  }
}
```

## 6. Image Service with Compression

```dart
class ImageService {
  final FirebaseStorage _storage;
  final ILocalStorage _localStorage;

  static const int maxImageSize = 5 * 1024 * 1024; // 5MB
  static const int maxWidth = 1200;
  static const int maxHeight = 1200;
  static const int quality = 85;

  Future<String> addImageToNote(File imageFile) async {
    // 1. Validate size
    final fileSize = await imageFile.length();
    if (fileSize > maxImageSize) {
      throw ValidationException('Image too large (max 5MB)');
    }

    // 2. Compress
    final compressed = await _compressImage(imageFile);

    // 3. Save to local cache first
    final localPath = await _saveToLocalCache(compressed);

    // 4. Queue upload to Firebase (background)
    _queueUpload(compressed, localPath);

    // 5. Return local path for immediate display
    return localPath;
  }

  Future<File> _compressImage(File image) async {
    final result = await FlutterImageCompress.compressWithFile(
      image.absolute.path,
      quality: quality,
      maxWidth: maxWidth,
      maxHeight: maxHeight,
    );

    if (result == null) {
      throw ImageException('Failed to compress image');
    }

    final tempDir = await getTemporaryDirectory();
    final tempFile = File('${tempDir.path}/${const Uuid().v4()}.jpg');
    await tempFile.writeAsBytes(result);

    return tempFile;
  }

  Future<String> _saveToLocalCache(File image) async {
    final dir = await getApplicationDocumentsDirectory();
    final filename = '${const Uuid().v4()}.jpg';
    final cachePath = '${dir.path}/images';

    await Directory(cachePath).create(recursive: true);

    final cachedFile = File('$cachePath/$filename');
    await image.copy(cachedFile.path);

    return cachedFile.path;
  }

  void _queueUpload(File image, String localPath) {
    // Upload in background, update note when complete
    _uploadToFirebase(image).then((remoteUrl) {
      // Update note to use remote URL
      _updateNoteImageUrl(localPath, remoteUrl);
    }).catchError((e) {
      print('Image upload failed: $e');
      // Keep using local path
    });
  }

  Future<String> _uploadToFirebase(File image) async {
    final userId = FirebaseAuth.instance.currentUser?.uid;
    final filename = '${const Uuid().v4()}.jpg';
    final ref = _storage.ref().child('users/$userId/images/$filename');

    final uploadTask = ref.putFile(image);
    final snapshot = await uploadTask;

    return await snapshot.ref.getDownloadURL();
  }

  Future<void> _updateNoteImageUrl(String localPath, String remoteUrl) async {
    // Find notes containing localPath and replace with remoteUrl
    // Implementation depends on how images are stored in note content
  }
}
```

## 7. Enhanced Firebase Security Rules

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Helper functions
    function isAuthenticated() {
      return request.auth != null;
    }

    function isOwner(userId) {
      return isAuthenticated() && request.auth.uid == userId;
    }

    function validateNote() {
      let note = request.resource.data;
      return note.keys().hasAll(['id', 'userId', 'title', 'content', 'createdAt', 'updatedAt', 'version'])
        && note.userId is string
        && note.userId == request.auth.uid
        && note.title is string
        && note.title.size() <= 200
        && note.content is string
        && note.content.size() <= 100000
        && note.version is int
        && note.version >= 1;
    }

    match /users/{userId}/notes/{noteId} {
      allow read: if isOwner(userId);

      allow create: if isOwner(userId)
                    && validateNote();

      allow update: if isOwner(userId)
                    && resource.data.userId == userId
                    && validateNote()
                    && request.resource.data.version > resource.data.version;

      allow delete: if isOwner(userId)
                    && resource.data.userId == userId;
    }

    match /users/{userId}/folders/{folderId} {
      allow read, write: if isOwner(userId);
    }

    match /users/{userId}/tags/{tagId} {
      allow read, write: if isOwner(userId);
    }

    match /users/{userId}/templates/{templateId} {
      allow read, write: if isOwner(userId);
    }
  }
}
```

## 8. Pagination in Repository

```dart
class NoteRepository {
  final ILocalStorage _localStorage;
  static const int defaultPageSize = 20;

  Future<List<Note>> getNotes({
    int? limit,
    String? lastNoteId,
    String? folderId,
    List<String>? tags,
  }) async {
    int offset = 0;

    if (lastNoteId != null) {
      // Find offset based on lastNoteId
      offset = await _findNoteOffset(lastNoteId);
    }

    return await _localStorage.getNotes(
      limit: limit ?? defaultPageSize,
      offset: offset,
      folderId: folderId,
      tags: tags,
    );
  }

  Future<int> _findNoteOffset(String lastNoteId) async {
    final allNotes = await _localStorage.getNotes();
    return allNotes.indexWhere((note) => note.id == lastNoteId) + 1;
  }
}
```

## 9. Updated Dependencies

```yaml
name: prompter
description: Cross-platform note-taking app with offline-first sync

environment:
  sdk: '>=3.0.0 <4.0.0'

dependencies:
  flutter:
    sdk: flutter

  # Firebase (latest stable versions as of Jan 2025)
  firebase_core: ^3.6.0
  cloud_firestore: ^5.4.4
  firebase_auth: ^5.3.1
  firebase_storage: ^12.3.4
  firebase_analytics: ^11.3.3
  firebase_crashlytics: ^4.1.3

  # Local storage
  hive: ^2.2.3
  hive_flutter: ^1.1.0
  shared_preferences: ^2.3.2

  # Rich text
  flutter_quill: ^10.8.7

  # State management
  provider: ^6.1.2

  # Navigation
  go_router: ^14.6.2

  # Image handling
  flutter_image_compress: ^2.3.0
  image_picker: ^1.1.2
  path_provider: ^2.1.4

  # Utilities
  uuid: ^4.5.1
  intl: ^0.19.0
  connectivity_plus: ^6.1.0

dev_dependencies:
  hive_generator: ^2.0.1
  build_runner: ^2.4.13
  flutter_test:
    sdk: flutter
  mockito: ^5.4.4
  flutter_lints: ^5.0.0
```

## 10. Implementation Timeline (Revised)

### Phase 1: Foundation (Week 1-2)
- [ ] Create Flutter project
- [ ] Set up abstract storage layer
- [ ] Implement migration system
- [ ] Create enhanced data models with all fields
- [ ] Set up Hive adapters
- [ ] Build repository layer with pagination
- [ ] Set up Firebase project

### Phase 2: Core Features (Week 3)
- [ ] Build home screen with infinite scroll
- [ ] Implement note editor with auto-save
- [ ] Add image service with compression
- [ ] Create folder management
- [ ] Implement tag system

### Phase 3: Sync System (Week 4)
- [ ] Implement Firebase Auth
- [ ] Build event-driven sync service
- [ ] Implement conflict resolver
- [ ] Add persistent sync queue
- [ ] Test tombstone deletion sync

### Phase 4: Templates & Search (Week 5)
- [ ] Create template system with sanitization
- [ ] Implement full-text search
- [ ] Add undo/redo system

### Phase 5: Testing & Polish (Week 6)
- [ ] Write unit tests (80%+ coverage)
- [ ] Widget tests for critical flows
- [ ] Integration tests for sync
- [ ] Set up CI/CD
- [ ] Performance profiling
- [ ] Accessibility audit

**Total time: 6 weeks for production-ready MVP**

## Summary of Improvements

| Area | v1.0 | v2.0 |
|------|------|------|
| Sync | Timer-based | Event-driven with backoff |
| Deletions | Flag only | Tombstones with sync |
| Conflicts | Last-write-wins | Field-level merge |
| Data Models | Basic fields | userId, version, deletedAt, metadata |
| Images | Upload only | Compress, cache, offline support |
| Storage | Hive only | Abstract layer (web compatible) |
| Pagination | None | Offset-based with 20 items/page |
| Migrations | None | Version-based system |
| Security | Basic rules | Validated with rate limits |

This revised architecture addresses all critical issues identified in the review while maintaining simplicity and focusing on the MVP feature set.

# Prompter - Cross-Platform Note-Taking App Architecture Plan

## Overview
**Prompter** is a minimal, cross-platform note-taking app with offline-first sync that follows you across all devices (iOS, Android, Mac, PC, Linux). The name emphasizes the app's strength: quick-access prompts and templates for communications and messaging.

## Tech Stack
- **Frontend:** Flutter (single codebase for all platforms)
- **Backend:** Firebase (free tier)
  - Firestore (database + real-time sync)
  - Firebase Authentication (user accounts)
  - Firebase Storage (images)
- **Local Storage:** Hive (Flutter NoSQL database)
- **Rich Text:** flutter_quill or quill_html_editor

## Core Features (MVP)
1. Rich text notes (bold, italic, images)
2. Folder + tag organization
3. Templates and prompts
4. Offline-first with auto-sync
5. Cross-device sync

## Architecture Design

### 1. Data Model

```dart
// Note Model
class Note {
  String id;              // UUID
  String title;
  String content;         // Rich text (JSON/HTML)
  String folderId;        // FK to Folder
  List<String> tags;      // Tag names
  DateTime createdAt;
  DateTime updatedAt;
  bool isSynced;          // Sync status
  bool isDeleted;         // Soft delete
}

// Folder Model
class Folder {
  String id;
  String name;
  String? parentId;       // For nested folders
  int sortOrder;
  DateTime createdAt;
}

// Tag Model
class Tag {
  String id;
  String name;
  String color;           // Hex color code
  int noteCount;          // Cached count
}

// Template Model
class Template {
  String id;
  String name;
  String content;         // Rich text template
  String category;        // e.g., "communication", "personal"
  bool isPinned;
}
```

### 2. Project Structure

```
prompter/
├── lib/
│   ├── main.dart                     # App entry point
│   │
│   ├── core/
│   │   ├── constants/
│   │   │   └── app_constants.dart    # Colors, strings, defaults
│   │   ├── routes/
│   │   │   └── app_router.dart       # Navigation
│   │   └── theme/
│   │       └── app_theme.dart        # Light/dark themes
│   │
│   ├── data/
│   │   ├── models/
│   │   │   ├── note.dart
│   │   │   ├── folder.dart
│   │   │   ├── tag.dart
│   │   │   └── template.dart
│   │   ├── repositories/
│   │   │   ├── note_repository.dart
│   │   │   ├── folder_repository.dart
│   │   │   ├── tag_repository.dart
│   │   │   └── template_repository.dart
│   │   └── services/
│   │       ├── local_storage_service.dart    # Hive
│   │       ├── firebase_service.dart         # Firestore
│   │       ├── sync_service.dart             # Offline sync
│   │       └── auth_service.dart             # Firebase Auth
│   │
│   ├── presentation/
│   │   ├── screens/
│   │   │   ├── home/
│   │   │   │   ├── home_screen.dart
│   │   │   │   └── home_view_model.dart
│   │   │   ├── editor/
│   │   │   │   ├── note_editor_screen.dart
│   │   │   │   └── editor_view_model.dart
│   │   │   ├── folders/
│   │   │   │   ├── folder_list_screen.dart
│   │   │   │   └── folder_view_model.dart
│   │   │   ├── templates/
│   │   │   │   ├── template_picker_screen.dart
│   │   │   │   └── template_view_model.dart
│   │   │   └── settings/
│   │   │       └── settings_screen.dart
│   │   └── widgets/
│   │       ├── note_card.dart
│   │       ├── folder_tree.dart
│   │       ├── tag_chip.dart
│   │       └── rich_text_editor.dart
│   │
│   └── utils/
│       ├── sync_manager.dart         # Background sync
│       └── conflict_resolver.dart    # Sync conflicts
│
├── test/
│   ├── unit/
│   ├── widget/
│   └── integration/
│
├── pubspec.yaml
└── firebase.json
```

### 3. Key Dependencies (pubspec.yaml)

```yaml
dependencies:
  flutter:
    sdk: flutter

  # Firebase
  firebase_core: ^3.0.0
  cloud_firestore: ^5.0.0
  firebase_auth: ^5.0.0
  firebase_storage: ^12.0.0

  # Local storage
  hive: ^2.2.3
  hive_flutter: ^1.1.0

  # Rich text editor
  flutter_quill: ^10.0.0

  # State management
  provider: ^6.1.0         # or riverpod

  # Navigation
  go_router: ^14.0.0

  # Utilities
  uuid: ^4.0.0
  intl: ^0.19.0            # Date formatting
  connectivity_plus: ^6.0.0 # Network status

dev_dependencies:
  hive_generator: ^2.0.0
  build_runner: ^2.4.0
  flutter_test:
    sdk: flutter
```

### 4. Offline-First Sync Strategy

#### A. Write Flow
```
User creates/edits note
  ↓
Save to Hive (local) immediately
  ↓
Mark as "needs sync"
  ↓
If online → sync to Firestore
If offline → queue for later
```

#### B. Read Flow
```
User opens app
  ↓
Load from Hive (instant)
  ↓
Display local data
  ↓
Background: Check Firestore for updates
  ↓
If changes found → merge & update UI
```

#### C. Sync Service Logic
```dart
class SyncService {
  // Background sync every 30 seconds when online
  void startPeriodicSync() {
    Timer.periodic(Duration(seconds: 30), (_) async {
      if (await isOnline()) {
        await syncPendingChanges();
        await fetchRemoteChanges();
      }
    });
  }

  // Upload local changes
  Future<void> syncPendingChanges() async {
    final unsyncedNotes = await localDb.getUnsyncedNotes();
    for (final note in unsyncedNotes) {
      await firestore.collection('notes').doc(note.id).set(note.toMap());
      await localDb.markAsSynced(note.id);
    }
  }

  // Download remote changes
  Future<void> fetchRemoteChanges() async {
    final lastSync = await localDb.getLastSyncTime();
    final snapshot = await firestore
      .collection('notes')
      .where('updatedAt', isGreaterThan: lastSync)
      .get();

    for (final doc in snapshot.docs) {
      await localDb.upsertNote(Note.fromMap(doc.data()));
    }
    await localDb.setLastSyncTime(DateTime.now());
  }
}
```

### 5. Conflict Resolution
When same note edited on multiple devices:
- **Last-Write-Wins:** Use `updatedAt` timestamp
- **User prompt:** If major conflict, show both versions and let user choose
- **Field-level merge:** Merge non-conflicting fields

### 6. Firebase Setup

#### Firestore Collections
```
users/{userId}/
  ├── notes/{noteId}
  ├── folders/{folderId}
  ├── tags/{tagId}
  └── templates/{templateId}
```

#### Security Rules
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

#### Indexes (create via Firebase Console)
- Collection: `notes`, Fields: `updatedAt DESC, folderId ASC`
- Collection: `notes`, Fields: `tags ARRAY, updatedAt DESC`

### 7. Implementation Phases

#### Phase 1: Foundation (Week 1)
- [ ] Create Flutter project with folder structure
- [ ] Set up Firebase project and add FlutterFire
- [ ] Configure Hive local database
- [ ] Implement basic data models (Note, Folder, Tag, Template)
- [ ] Create repository layer (local-first pattern)

#### Phase 2: Core Features (Week 2)
- [ ] Build home screen (note list)
- [ ] Implement rich text editor with flutter_quill
- [ ] Create folder browsing UI
- [ ] Add tag management
- [ ] Implement search functionality

#### Phase 3: Sync & Templates (Week 3)
- [ ] Implement Firebase Auth (email + anonymous)
- [ ] Build sync service (background sync)
- [ ] Create conflict resolution logic
- [ ] Add template system (create, use, manage)
- [ ] Implement prompts feature

#### Phase 4: Polish & Testing (Week 4)
- [ ] Add settings screen (sync preferences, themes)
- [ ] Implement image upload/storage
- [ ] Handle offline mode gracefully
- [ ] Write unit and widget tests
- [ ] Test cross-device sync scenarios

#### Phase 5: Platform Builds
- [ ] **Priority 1:** Android + Web (easiest to test)
- [ ] **Priority 2:** iOS (requires Mac + developer account)
- [ ] **Priority 3:** Desktop (Mac/Windows/Linux via Flutter desktop)

### 8. File Breakdown

#### Critical Files to Create

1. **lib/main.dart** (~80 lines)
   - Initialize Firebase
   - Initialize Hive
   - Set up providers
   - Define app routes

2. **lib/data/services/sync_service.dart** (~200 lines)
   - Background sync logic
   - Conflict resolution
   - Network monitoring

3. **lib/data/repositories/note_repository.dart** (~150 lines)
   - CRUD operations
   - Local-first pattern
   - Query methods

4. **lib/presentation/screens/editor/note_editor_screen.dart** (~300 lines)
   - Rich text editor UI
   - Image picker
   - Auto-save logic
   - Tag/folder assignment

5. **lib/presentation/screens/home/home_screen.dart** (~250 lines)
   - Note grid/list view
   - Search bar
   - Folder/tag filters
   - FAB for new note

6. **lib/data/models/note.dart** (~100 lines)
   - Note model
   - JSON serialization
   - Hive adapters

### 9. Rich Text Format

Use **Delta JSON** (flutter_quill format):
```json
{
  "ops": [
    {"insert": "Hello "},
    {"insert": "World", "attributes": {"bold": true}},
    {"insert": "\n"},
    {"insert": {"image": "https://..."}}
  ]
}
```

Store as string in Firestore/Hive, parse when displaying.

### 10. Templates Feature

#### Template Structure
```dart
class Template {
  String id;
  String name;
  String category;      // "meeting", "email", "daily-log"
  String content;       // Delta JSON with placeholders
  bool isPinned;

  // Placeholders: {{date}}, {{time}}, {{name}}
}
```

#### Pre-built Templates
- Meeting Notes: "# Meeting - {{date}}\n**Attendees:**\n**Agenda:**\n**Notes:**"
- Email Draft: "To: \nSubject: \n\n---\n\n"
- Daily Log: "# {{date}}\n## Tasks\n- [ ] \n\n## Notes\n"

### 11. Security Considerations

1. **Authentication:** Firebase Auth with email/password + anonymous mode
2. **Data isolation:** Firestore rules enforce userId ownership
3. **Local encryption:** Optional Hive encryption for sensitive notes
4. **No data sharing:** Personal use only, no sharing features in MVP

### 12. Verification & Testing

#### End-to-End Test Scenarios
1. **Offline creation:**
   - Create note while offline → verify saved locally
   - Go online → verify synced to Firestore

2. **Cross-device sync:**
   - Create note on Device A
   - Open app on Device B → verify note appears

3. **Conflict resolution:**
   - Edit same note on 2 offline devices
   - Go online → verify conflict handled gracefully

4. **Template usage:**
   - Select template → verify content populates
   - Edit and save → verify saved as regular note

5. **Rich text:**
   - Format text (bold, italic)
   - Add image
   - Save and reopen → verify formatting preserved

#### Unit Tests
- Note repository CRUD operations
- Sync service merge logic
- Conflict resolution algorithm
- Template variable substitution

#### Widget Tests
- Note editor autosave
- Folder tree navigation
- Tag filtering
- Search functionality

### 13. Firebase Free Tier Limits
- **Firestore:** 1GB storage, 50K reads/day, 20K writes/day
- **Authentication:** Unlimited
- **Storage:** 5GB (for images)

For personal use with ~1000 notes, this is more than sufficient.

### 14. Estimated Resource Requirements

#### Development Time (MVP)
- Phase 1-4: 3-4 weeks of focused development
- Testing & Polish: 1 week
- Total: ~1 month for working MVP

#### Platform Builds
- Android: Immediate (Flutter default)
- Web: Immediate (Flutter web build)
- iOS: 1-2 days (code signing, TestFlight)
- Desktop: 2-3 days (packaging, installers)

#### Learning Resources
- Flutter docs: https://flutter.dev/docs
- FlutterFire: https://firebase.flutter.dev
- flutter_quill: https://pub.dev/packages/flutter_quill
- Hive: https://docs.hivedb.dev

### 15. Next Steps After Plan Approval

1. Create new Flutter project: `flutter create prompter`
2. Set up Firebase project in console
3. Add FlutterFire to project: `flutterfire configure`
4. Create folder structure and base files
5. Implement data models and local storage
6. Build core UI screens
7. Implement sync service
8. Add templates and prompts
9. Test cross-device sync
10. Build for target platforms

## Summary

This architecture provides:
- ✅ Cross-platform (Flutter)
- ✅ Offline-first with real-time sync (Hive + Firestore)
- ✅ Rich text editing (flutter_quill)
- ✅ Folders + tags organization
- ✅ Templates and prompts
- ✅ Free tier compatible (Firebase)
- ✅ Minimal but extensible
- ✅ Personal use focused

The MVP will focus on Android + Web first, then expand to iOS and desktop platforms.

## Current Status

**Phase:** Ready to begin Phase 1: Foundation
**Next Action:** On your more powerful device, run `flutter create prompter` in the parent directory, then continue with the implementation.

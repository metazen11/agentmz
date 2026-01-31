# Prompter - Implementation Roadmap

## 📚 Documentation Index

All planning documents are now complete and synced via Dropbox:

1. **ARCHITECTURE.md** - Original architecture plan
2. **ARCHITECTURE_V2.md** - Revised architecture with critical fixes
3. **ARCHITECTURE_REVIEW.md** - Critical analysis identifying problems
4. **CODING_PRINCIPLES.md** - DRY, SOLID, abstraction patterns
5. **SECURITY_AND_BEST_PRACTICES.md** - Security-first development
6. **E2E_ENCRYPTION.md** - End-to-end encryption design
7. **SETUP.md** - Quick start guide for new device
8. **THIS FILE** - Implementation roadmap

## 🎯 Project Summary

**Prompter** is a cross-platform note-taking app with:
- Offline-first architecture
- End-to-end encryption
- Real-time sync across devices
- Rich text editing
- Templates and prompts
- Folder and tag organization

**Tech Stack:** Flutter + Firebase + Hive + E2E Encryption

## 🚀 Phase-by-Phase Implementation

### Phase 0: Setup & Foundation (Week 1)

#### Day 1-2: Project Setup
```bash
# On your powerful device
cd C:\Dropbox\_CODING\agentmz
flutter create prompter
cd prompter

# Add all dependencies (see ARCHITECTURE_V2.md section 9)
# Create folder structure (see ARCHITECTURE_V2.md section 2)
```

**Checklist:**
- [ ] Create Flutter project
- [ ] Add all dependencies to pubspec.yaml
- [ ] Create folder structure (lib/core, lib/data, lib/presentation)
- [ ] Set up Firebase project in console
- [ ] Run `flutterfire configure`
- [ ] Add .gitignore (include .env, secrets)
- [ ] Create .env.example template
- [ ] Set up Git hooks (optional)

#### Day 3-4: Core Infrastructure
**Files to create:**
1. `lib/core/exceptions/app_exceptions.dart` (from SECURITY_AND_BEST_PRACTICES.md)
2. `lib/core/result.dart` (Result pattern)
3. `lib/core/constants/app_constants.dart`
4. `lib/utils/helpers.dart`
5. `lib/utils/validators.dart`
6. `lib/core/di/service_locator.dart` (dependency injection)

**Checklist:**
- [ ] Implement exception hierarchy
- [ ] Create Result wrapper class
- [ ] Define all app constants
- [ ] Create helper functions
- [ ] Set up validators
- [ ] Configure dependency injection

#### Day 5-7: Data Models & Storage
**Files to create:**
1. `lib/data/models/note.dart` (with all fields from ARCHITECTURE_V2.md)
2. `lib/data/models/folder.dart`
3. `lib/data/models/tag.dart`
4. `lib/data/models/template.dart`
5. `lib/core/interfaces/i_storage.dart` (abstract interface)
6. `lib/data/services/local_storage_service.dart` (Hive implementation)
7. `lib/data/services/migration_manager.dart`

**Checklist:**
- [ ] Create all data models with Hive annotations
- [ ] Run `flutter pub run build_runner build` to generate adapters
- [ ] Implement IStorage interface
- [ ] Create HiveStorage implementation
- [ ] Create WebStorage implementation (if targeting web)
- [ ] Implement migration system
- [ ] Write unit tests for data models

**Testing:**
```dart
// test/unit/note_model_test.dart
test('Note serialization works', () {
  final note = Note(...);
  final map = note.toMap();
  final restored = Note.fromMap(map);
  expect(restored.id, note.id);
});
```

---

### Phase 1: Repository & Basic CRUD (Week 2)

#### Day 8-10: Repository Layer
**Files to create:**
1. `lib/data/repositories/base_repository.dart`
2. `lib/data/repositories/note_repository.dart`
3. `lib/data/repositories/folder_repository.dart`
4. `lib/data/repositories/tag_repository.dart`
5. `lib/data/repositories/template_repository.dart`

**Checklist:**
- [ ] Implement BaseRepository with common CRUD
- [ ] Create NoteRepository with pagination
- [ ] Add folder management
- [ ] Add tag management
- [ ] Add template management
- [ ] Write unit tests with mocks

**Testing:**
```dart
// test/unit/note_repository_test.dart
test('Create note saves locally and queues sync', () async {
  final mockStorage = MockLocalStorage();
  final repository = NoteRepository(localStorage: mockStorage);

  final result = await repository.create(testNote);

  expect(result.isSuccess, true);
  verify(mockStorage.save(any)).called(1);
});
```

#### Day 11-14: Firebase Integration
**Files to create:**
1. `lib/data/services/firebase_service.dart`
2. `lib/data/services/auth_service.dart`
3. `lib/data/services/sync_service.dart` (event-driven)
4. `lib/utils/conflict_resolver.dart`

**Checklist:**
- [ ] Set up Firebase Auth (email + anonymous)
- [ ] Implement FirebaseService for remote storage
- [ ] Create event-driven SyncService (see ARCHITECTURE_V2.md section 4)
- [ ] Implement field-level conflict resolution
- [ ] Add connectivity monitoring
- [ ] Test sync with multiple devices
- [ ] Deploy Firebase security rules (see ARCHITECTURE_V2.md section 7)

**Firebase Rules Deployment:**
```bash
firebase deploy --only firestore:rules
```

---

### Phase 2: Encryption (Week 3)

#### Day 15-17: E2E Encryption Core
**Files to create:**
1. `lib/data/services/encryption_service.dart` (from E2E_ENCRYPTION.md)
2. `lib/data/models/encrypted_note.dart`
3. `lib/utils/password_validator.dart`

**Checklist:**
- [ ] Implement EncryptionService with PBKDF2
- [ ] Add master key management
- [ ] Create note encryption/decryption
- [ ] Add per-note key generation
- [ ] Test encryption performance
- [ ] Write encryption unit tests

**Testing:**
```dart
test('Encryption/decryption preserves data', () async {
  final encryption = EncryptionService();
  await encryption.initialize('test_password_123');

  final encrypted = await encryption.encryptNote(testNote);
  final decrypted = await encryption.decryptNote(encrypted);

  expect(decrypted.title, testNote.title);
  expect(decrypted.content, testNote.content);
});
```

#### Day 18-21: Encryption Integration
**Files to update:**
1. Update `NoteRepository` to encrypt before save
2. Update `SyncService` to sync encrypted data
3. Create `KeySyncService` for multi-device support

**Checklist:**
- [ ] Integrate encryption in repository layer
- [ ] Update sync service for encrypted notes
- [ ] Implement master key cloud sync
- [ ] Add password change functionality
- [ ] Test cross-device encryption sync
- [ ] Add key backup/export

---

### Phase 3: UI & User Experience (Week 4-5)

#### Day 22-25: Core Screens
**Files to create:**
1. `lib/presentation/screens/home/home_screen.dart`
2. `lib/presentation/screens/home/home_view_model.dart`
3. `lib/presentation/screens/editor/note_editor_screen.dart`
4. `lib/presentation/screens/editor/editor_view_model.dart`
5. `lib/presentation/widgets/note_card.dart`
6. `lib/core/theme/app_theme.dart`
7. `lib/core/routes/app_router.dart`

**Checklist:**
- [ ] Design app theme (light + dark modes)
- [ ] Set up navigation with go_router
- [ ] Build home screen with note list
- [ ] Implement infinite scroll pagination
- [ ] Create note card widget
- [ ] Build note editor with flutter_quill
- [ ] Add autosave functionality
- [ ] Add loading states

#### Day 26-28: Editor Features
**Files to create:**
1. `lib/presentation/widgets/rich_text_editor.dart`
2. `lib/data/services/image_service.dart`
3. `lib/utils/undo_redo_manager.dart`

**Checklist:**
- [ ] Integrate flutter_quill editor
- [ ] Add image picker with compression
- [ ] Implement local image caching
- [ ] Add undo/redo functionality
- [ ] Add formatting toolbar
- [ ] Test editor performance with large notes

#### Day 29-31: Folders & Tags
**Files to create:**
1. `lib/presentation/screens/folders/folder_list_screen.dart`
2. `lib/presentation/widgets/folder_tree.dart`
3. `lib/presentation/widgets/tag_chip.dart`
4. `lib/presentation/screens/search/search_screen.dart`

**Checklist:**
- [ ] Build folder management UI
- [ ] Create folder tree widget
- [ ] Add tag selection UI
- [ ] Implement tag chips
- [ ] Build search screen
- [ ] Add folder/tag filtering
- [ ] Implement full-text search

#### Day 32-35: Templates & Settings
**Files to create:**
1. `lib/presentation/screens/templates/template_picker_screen.dart`
2. `lib/presentation/screens/templates/template_editor_screen.dart`
3. `lib/presentation/screens/settings/settings_screen.dart`
4. `lib/presentation/screens/auth/setup_encryption_screen.dart`
5. `lib/presentation/screens/auth/login_screen.dart`

**Checklist:**
- [ ] Create template picker
- [ ] Build template editor with placeholders
- [ ] Add pre-built templates
- [ ] Create settings screen
- [ ] Add sync status indicator
- [ ] Build encryption setup flow
- [ ] Create login/signup screens
- [ ] Add biometric unlock (optional)

---

### Phase 4: Testing & Polish (Week 6)

#### Day 36-38: Testing
**Files to create:**
1. `test/unit/note_repository_test.dart`
2. `test/unit/sync_service_test.dart`
3. `test/unit/encryption_service_test.dart`
4. `test/widget/home_screen_test.dart`
5. `test/widget/note_editor_test.dart`
6. `test/integration/sync_flow_test.dart`

**Checklist:**
- [ ] Write unit tests for all repositories
- [ ] Test sync service thoroughly
- [ ] Test encryption/decryption
- [ ] Write widget tests for key screens
- [ ] Create integration tests for sync flows
- [ ] Test conflict resolution scenarios
- [ ] Achieve 80%+ code coverage

**Run tests:**
```bash
flutter test
flutter test --coverage
genhtml coverage/lcov.info -o coverage/html
```

#### Day 39-40: Performance Optimization
**Checklist:**
- [ ] Profile app with Flutter DevTools
- [ ] Optimize image loading
- [ ] Add caching for frequent queries
- [ ] Optimize encryption performance
- [ ] Test with 1000+ notes
- [ ] Reduce app size
- [ ] Test on low-end devices

#### Day 41-42: CI/CD & Deployment
**Files to create:**
1. `.github/workflows/flutter.yml`
2. `fastlane/Fastfile` (for iOS/Android)

**Checklist:**
- [ ] Set up GitHub Actions for automated testing
- [ ] Configure automated builds
- [ ] Set up Fastlane for deployment
- [ ] Create app icons and splash screens
- [ ] Prepare App Store/Play Store listings
- [ ] Generate release builds

---

### Phase 5: Platform Releases (Week 7)

#### Priority 1: Android + Web (Day 43-45)
```bash
# Android
flutter build apk --release
flutter build appbundle --release

# Web
flutter build web --release
firebase deploy --only hosting
```

**Checklist:**
- [ ] Build Android APK/AAB
- [ ] Test on multiple Android versions
- [ ] Deploy to Play Store (internal testing)
- [ ] Build web version
- [ ] Deploy to Firebase Hosting
- [ ] Test web version in multiple browsers

#### Priority 2: iOS (Day 46-47) - Requires Mac
```bash
flutter build ios --release
```

**Checklist:**
- [ ] Configure Xcode project
- [ ] Set up certificates and provisioning
- [ ] Build iOS app
- [ ] Test on physical iOS devices
- [ ] Upload to TestFlight
- [ ] Submit to App Store

#### Priority 3: Desktop (Day 48-49) - Optional
```bash
# Windows
flutter build windows --release

# macOS
flutter build macos --release

# Linux
flutter build linux --release
```

**Checklist:**
- [ ] Build for Windows
- [ ] Build for macOS
- [ ] Build for Linux
- [ ] Create installers/packages
- [ ] Test on each platform

---

## 📊 Progress Tracking

### Current Status
- **Phase:** 0 (Setup)
- **Days Completed:** 0/49
- **Overall Progress:** 0%

### Key Milestones
- [ ] Week 1: Foundation complete
- [ ] Week 2: CRUD and sync working
- [ ] Week 3: Encryption implemented
- [ ] Week 4-5: UI complete
- [ ] Week 6: Testing done
- [ ] Week 7: Released to production

---

## 🔄 Development Workflow

### Daily Routine
1. **Start of day:**
   - Review previous day's code
   - Check test coverage
   - Plan today's tasks

2. **During development:**
   - Write failing test first (TDD)
   - Implement feature
   - Refactor for DRY/SOLID
   - Document as you go

3. **End of day:**
   - Run all tests
   - Commit with clear message
   - Update progress tracker

### Git Commit Convention
```
feat: add note encryption
fix: resolve sync conflict bug
refactor: extract validation logic
docs: update architecture diagram
test: add unit tests for repository
chore: update dependencies
```

### Code Review Checklist (Self-Review)
- [ ] Follows DRY principle
- [ ] Uses abstractions appropriately
- [ ] No hardcoded secrets
- [ ] Input validation present
- [ ] Error handling implemented
- [ ] Unit tests written
- [ ] Documentation added
- [ ] No console warnings
- [ ] Performance verified

---

## 🎓 Learning Resources

### Flutter
- [Flutter Docs](https://flutter.dev/docs)
- [Dart Language Tour](https://dart.dev/guides/language/language-tour)
- [Flutter Cookbook](https://docs.flutter.dev/cookbook)

### Firebase
- [FlutterFire](https://firebase.flutter.dev)
- [Firestore Security Rules](https://firebase.google.com/docs/firestore/security/get-started)
- [Firebase Storage](https://firebase.google.com/docs/storage)

### Encryption
- [Flutter Encrypt Package](https://pub.dev/packages/encrypt)
- [Cryptography Best Practices](https://github.com/veorq/cryptocoding)
- [OWASP Mobile Security](https://owasp.org/www-project-mobile-top-10/)

### Architecture
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Repository Pattern](https://medium.com/@pererikbergman/repository-design-pattern-e28c0f3e4a30)
- [SOLID Principles](https://www.digitalocean.com/community/conceptual_articles/s-o-l-i-d-the-first-five-principles-of-object-oriented-design)

---

## 🆘 Troubleshooting

### Common Issues

#### Flutter Build Errors
```bash
# Clean build
flutter clean
flutter pub get
flutter pub run build_runner build --delete-conflicting-outputs
```

#### Firebase Connection Issues
```bash
# Re-run FlutterFire configuration
flutterfire configure
```

#### Hive Errors
```bash
# Delete local Hive boxes
# iOS Simulator:
rm -rf ~/Library/Developer/CoreSimulator/Devices/*/data/Containers/Data/Application/*/Documents/

# Android Emulator:
adb shell run-as com.your.package.name rm -rf /data/data/com.your.package.name/app_flutter/
```

#### Encryption Key Issues
- If you lose the master key, there's NO recovery
- Always backup encryption key after setup
- Test key import/export functionality thoroughly

---

## 📈 Success Metrics

### Technical Metrics
- [ ] 80%+ test coverage
- [ ] <2s cold start time
- [ ] <100ms sync latency
- [ ] <200KB APK size increase per version
- [ ] Zero critical security vulnerabilities
- [ ] <1% crash rate

### User Experience Metrics
- [ ] Offline-first: works without internet
- [ ] Notes sync within 5 seconds
- [ ] Search returns results instantly
- [ ] Editor has no lag
- [ ] Images load smoothly
- [ ] Encryption doesn't impact UX

---

## 🎯 Next Steps

1. **On your powerful device:**
   - Navigate to: `C:\Dropbox\_CODING\agentmz\prompter`
   - Read `SETUP.md` for quick start
   - Run: `flutter create prompter`
   - Start: `claude`

2. **Tell Claude:**
   ```
   "Start implementing Phase 0 following IMPLEMENTATION_ROADMAP.md.
   Begin with Day 1-2: Project Setup."
   ```

3. **Claude will:**
   - Create the Flutter project
   - Set up folder structure
   - Add dependencies
   - Configure Firebase
   - Create initial files

## 🎉 You're Ready!

All planning is complete. The architecture is solid. Security is prioritized. Time to build!

**Estimated Timeline:** 7 weeks to production-ready MVP
**Estimated Effort:** Full-time focused development

Good luck! 🚀

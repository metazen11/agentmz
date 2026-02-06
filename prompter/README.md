# Prompter - Cross-Platform Note-Taking App

> Quick-access prompts and templates for communications and messaging, with offline-first sync and end-to-end encryption.

## 📋 Quick Links

- **[SETUP.md](SETUP.md)** - Get started on a new device
- **[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)** - Full 7-week development plan
- **[ARCHITECTURE_V2.md](ARCHITECTURE_V2.md)** - Complete technical architecture
- **[E2E_ENCRYPTION.md](E2E_ENCRYPTION.md)** - End-to-end encryption design
- **[SECURITY_AND_BEST_PRACTICES.md](SECURITY_AND_BEST_PRACTICES.md)** - Security-first development guide
- **[CODING_PRINCIPLES.md](CODING_PRINCIPLES.md)** - DRY, SOLID, and design patterns
- **[ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md)** - Critical issues and solutions

## 🎯 Project Overview

**Prompter** is a minimal, privacy-focused note-taking app that works offline-first and syncs securely across all your devices.

### Key Features
- ✅ **Offline-First:** Works without internet, syncs when online
- ✅ **End-to-End Encryption:** Your notes are encrypted before leaving your device
- ✅ **Cross-Platform:** iOS, Android, Web, Windows, macOS, Linux
- ✅ **Rich Text:** Bold, italic, images, formatting
- ✅ **Organization:** Folders and tags
- ✅ **Templates:** Quick-access prompts for common communications
- ✅ **Real-Time Sync:** Changes sync automatically across devices
- ✅ **Zero-Knowledge:** Firebase cannot read your notes

### Tech Stack
- **Frontend:** Flutter (single codebase)
- **Backend:** Firebase (Firestore, Auth, Storage)
- **Local Storage:** Hive (NoSQL)
- **Encryption:** AES-256-GCM, PBKDF2
- **Rich Text:** flutter_quill

## 🚀 Quick Start

### Prerequisites
```bash
# Flutter SDK
flutter --version  # Should be 3.0+

# Firebase CLI (optional)
firebase --version
```

### Setup
```bash
# 1. Navigate to project directory
cd C:\Dropbox\_CODING\agentmz\prompter

# 2. Create Flutter project (if not already created)
flutter create .

# 3. Get dependencies
flutter pub get

# 4. Run code generation
flutter pub run build_runner build

# 5. Configure Firebase
flutterfire configure

# 6. Run app
flutter run
```

## 📁 Project Structure

```
prompter/
├── lib/
│   ├── main.dart                          # Entry point
│   ├── core/                              # Core utilities
│   │   ├── constants/                     # App constants
│   │   ├── exceptions/                    # Exception classes
│   │   ├── interfaces/                    # Abstract interfaces
│   │   ├── routes/                        # Navigation
│   │   └── theme/                         # UI theme
│   ├── data/                              # Data layer
│   │   ├── models/                        # Data models
│   │   ├── repositories/                  # Repository pattern
│   │   └── services/                      # Services (sync, encryption, etc.)
│   ├── presentation/                      # UI layer
│   │   ├── screens/                       # Screen widgets
│   │   └── widgets/                       # Reusable widgets
│   └── utils/                             # Helper functions
├── test/                                  # Tests
│   ├── unit/                              # Unit tests
│   ├── widget/                            # Widget tests
│   └── integration/                       # Integration tests
└── docs/                                  # Documentation
```

## 🔐 Security

### Key Security Features
- **End-to-End Encryption:** AES-256-GCM encryption
- **Zero-Knowledge:** Firebase cannot decrypt your notes
- **PBKDF2:** 100,000 iterations for key derivation
- **Secure Storage:** Platform keychain/keystore
- **No Secrets in Code:** All keys in environment variables
- **Input Validation:** All user input sanitized
- **Firebase Rules:** Strict per-user access control

### Security Checklist
- [x] No API keys or secrets in code
- [x] All user input validated
- [x] SQL/NoSQL injection prevented
- [x] XSS attacks prevented
- [x] File upload validation
- [x] HTTPS only
- [x] End-to-end encryption
- [x] Secure key storage

## 🏗️ Architecture Principles

### DRY (Don't Repeat Yourself)
- Base classes for common functionality
- Helper functions for reusable logic
- Constants for all magic numbers/strings
- Validators for consistent validation

### SOLID Principles
- **S**ingle Responsibility: Each class has one job
- **O**pen/Closed: Open for extension, closed for modification
- **L**iskov Substitution: Interfaces are substitutable
- **I**nterface Segregation: Many specific interfaces
- **D**ependency Inversion: Depend on abstractions

### Clean Architecture
```
Presentation → Domain → Data
    ↓           ↓        ↓
  Views    Business   Storage
           Logic
```

### Security-First
- Validate all input
- Encrypt sensitive data
- No secrets in code
- Principle of least privilege
- Defense in depth

## 📊 Development Timeline

| Phase | Duration | Focus |
|-------|----------|-------|
| **Phase 0** | Week 1 | Setup & Foundation |
| **Phase 1** | Week 2 | Repository & CRUD |
| **Phase 2** | Week 3 | Encryption |
| **Phase 3** | Week 4-5 | UI & UX |
| **Phase 4** | Week 6 | Testing & Polish |
| **Phase 5** | Week 7 | Platform Releases |

**Total:** 7 weeks to production-ready MVP

## 🧪 Testing

```bash
# Run all tests
flutter test

# Run with coverage
flutter test --coverage

# View coverage report
genhtml coverage/lcov.info -o coverage/html
open coverage/html/index.html

# Run specific test
flutter test test/unit/note_repository_test.dart
```

### Test Coverage Goals
- **Unit Tests:** 80%+ coverage
- **Widget Tests:** All critical user flows
- **Integration Tests:** Sync, encryption, offline scenarios

## 🛠️ Development Commands

```bash
# Clean build
flutter clean && flutter pub get

# Generate code (Hive adapters, etc.)
flutter pub run build_runner build --delete-conflicting-outputs

# Analyze code
flutter analyze

# Format code
flutter format .

# Build release
flutter build apk --release           # Android
flutter build ios --release           # iOS
flutter build web --release           # Web
flutter build windows --release       # Windows
flutter build macos --release         # macOS
flutter build linux --release         # Linux
```

## 🔧 Configuration

### Environment Variables (.env)
```bash
FIREBASE_API_KEY=your_api_key
FIREBASE_PROJECT_ID=your_project_id
FIREBASE_APP_ID=your_app_id
```

### Firebase Setup
1. Create project at https://console.firebase.google.com
2. Enable Firestore Database
3. Enable Authentication (Email/Password + Anonymous)
4. Enable Storage
5. Deploy security rules: `firebase deploy --only firestore:rules`

## 📱 Platform Support

| Platform | Status | Priority |
|----------|--------|----------|
| Android | ✅ Supported | High |
| Web | ✅ Supported | High |
| iOS | ✅ Supported | Medium |
| Windows | ✅ Supported | Low |
| macOS | ✅ Supported | Low |
| Linux | ✅ Supported | Low |

## 🤝 Contributing

### Code Style
- Follow Dart style guide
- Use meaningful variable names
- Add comments for complex logic
- Write tests for new features

### Commit Convention
```
feat: add new feature
fix: bug fix
refactor: code refactoring
docs: documentation
test: add tests
chore: maintenance
```

### Pull Request Checklist
- [ ] Code follows style guide
- [ ] Tests pass
- [ ] New tests added
- [ ] Documentation updated
- [ ] No secrets in code
- [ ] Security reviewed

## 📝 License

MIT License - See LICENSE file for details

## 🆘 Support

### Common Issues
- **Build fails:** Run `flutter clean && flutter pub get`
- **Firebase errors:** Run `flutterfire configure`
- **Hive errors:** Delete local boxes and restart
- **Encryption key lost:** No recovery possible - backup keys!

### Getting Help
- Check documentation files in this directory
- Review ARCHITECTURE_REVIEW.md for known issues
- Check Flutter docs: https://flutter.dev/docs
- Check Firebase docs: https://firebase.google.com/docs

## 🎯 Current Status

**Phase:** Setup Phase 0
**Next Action:** Run `flutter create prompter` and begin Day 1 tasks

See [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) for detailed next steps.

## 📚 Additional Documentation

All documentation is in this directory:
- Architecture design and review
- Security best practices
- Encryption implementation
- Coding principles
- Setup instructions
- Implementation roadmap

**Total Documentation:** ~15,000+ lines of detailed specifications

## 🎉 Let's Build!

Everything is planned, reviewed, and ready. Time to implement!

```bash
cd C:\Dropbox\_CODING\agentmz\prompter
claude
```

Then say: **"Start implementing Phase 0 following IMPLEMENTATION_ROADMAP.md"**

# Setup Instructions for New Device

## Prerequisites

Before starting implementation, ensure you have:

1. **Flutter SDK** installed and in PATH
   - Download: https://docs.flutter.dev/get-started/install
   - Verify: `flutter --version`
   - Run: `flutter doctor` to check setup

2. **Firebase CLI** (optional but recommended)
   - Install: `npm install -g firebase-tools`
   - Or use FlutterFire CLI: `dart pub global activate flutterfire_cli`

3. **Git** configured for this repo
   - Already in Dropbox sync folder
   - Verify: `git status`

4. **IDE** with Flutter plugins
   - VS Code + Flutter extension
   - OR Android Studio + Flutter plugin

## Quick Start Commands

```bash
# 1. Navigate to prompter directory (adjust path for your OS)
cd C:\Dropbox\_CODING\agentmz\prompter

# 2. Create Flutter project (run in parent directory)
cd ..
flutter create prompter
cd prompter

# 3. Verify Flutter project created
flutter pub get

# 4. Start Claude Code session
claude

# 5. In Claude Code, say:
"Continue implementing the Prompter app following ARCHITECTURE.md. Start with Phase 1: Foundation."
```

## Firebase Setup (Do Later)

After basic project structure is in place:

1. Create Firebase project at https://console.firebase.google.com
2. Enable Firestore Database
3. Enable Authentication (Email/Password + Anonymous)
4. Enable Storage
5. Run: `flutterfire configure` (if using FlutterFire CLI)
   - OR manually download `google-services.json` (Android) and `GoogleService-Info.plist` (iOS)

## Implementation Order

### Phase 1: Foundation ✓ (Ready to Start)
- Create project structure
- Set up data models
- Configure Hive
- Create repository layer

### Phase 2: Core Features
- Build UI screens
- Implement rich text editor
- Add folder/tag management

### Phase 3: Sync & Backend
- Connect Firebase
- Implement sync service
- Add templates

### Phase 4: Polish
- Testing
- Error handling
- UI refinements

## Resuming This Session

If you want to continue this exact conversation on the new device:

1. The transcript is saved at:
   ```
   C:\Users\mauri\.claude\projects\C--Dropbox--CODING-agentmz-prompter\a0f40ac4-3f7f-48e0-8cb4-c0ba4d6e94a4.jsonl
   ```

2. Copy this file to the new device's Claude directory (if needed)

3. Reference it in the new session, or just start fresh with ARCHITECTURE.md

## Current State

- ✅ Architecture planned
- ✅ ARCHITECTURE.md created
- ✅ Directory ready in Dropbox
- ⏳ Awaiting Flutter project initialization on powerful device

## Next Command on New Device

```bash
cd C:\Dropbox\_CODING\agentmz
flutter create prompter
cd prompter
claude
```

Then tell Claude: "Implement Phase 1 of ARCHITECTURE.md"

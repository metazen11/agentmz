# Coding Principles & Design Guidelines

## Core Principles

### 1. SOLID Principles
- **Single Responsibility:** Each class has one reason to change
  - `NoteRepository` handles note CRUD only
  - `SyncService` handles sync logic only
  - `ConflictResolver` handles conflicts only

- **Open/Closed:** Open for extension, closed for modification
  - Use abstract classes for repositories
  - Template pattern for sync strategies

- **Liskov Substitution:** Interfaces should be substitutable
  - `LocalStorageService` and `FirebaseService` implement same interface

- **Interface Segregation:** Many specific interfaces > one general
  - `Readable`, `Writable`, `Syncable` interfaces

- **Dependency Inversion:** Depend on abstractions, not concretions
  - Repositories depend on abstract storage interfaces
  - UI depends on ViewModels, not repositories directly

### 2. Clean Architecture Layers

```
Presentation Layer (UI)
    ↓ (depends on)
Domain Layer (Business Logic)
    ↓ (depends on)
Data Layer (Repositories, Services)
```

**Rules:**
- Inner layers don't know about outer layers
- Dependencies point inward only
- Data flows through well-defined boundaries

### 3. State Management Pattern

Using **Provider** with **ChangeNotifier**:

```dart
// ViewModel pattern
class HomeViewModel extends ChangeNotifier {
  final NoteRepository _repository;

  List<Note> _notes = [];
  bool _isLoading = false;
  String? _error;

  // Getters expose immutable state
  List<Note> get notes => List.unmodifiable(_notes);
  bool get isLoading => _isLoading;
  String? get error => _error;

  // Actions update state and notify listeners
  Future<void> loadNotes() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _notes = await _repository.getAllNotes();
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
```

### 4. Error Handling Strategy

#### Custom Exception Hierarchy
```dart
abstract class AppException implements Exception {
  final String message;
  final String? code;
  final dynamic originalError;

  AppException(this.message, {this.code, this.originalError});
}

class NetworkException extends AppException {
  NetworkException(String message) : super(message, code: 'NETWORK_ERROR');
}

class StorageException extends AppException {
  StorageException(String message) : super(message, code: 'STORAGE_ERROR');
}

class SyncException extends AppException {
  SyncException(String message) : super(message, code: 'SYNC_ERROR');
}

class ValidationException extends AppException {
  ValidationException(String message) : super(message, code: 'VALIDATION_ERROR');
}
```

#### Error Handling Pattern
```dart
// In repositories
Future<Result<Note>> getNote(String id) async {
  try {
    final note = await _localStorage.getNote(id);
    return Result.success(note);
  } on HiveError catch (e) {
    return Result.failure(StorageException('Failed to load note: ${e.message}'));
  } catch (e) {
    return Result.failure(AppException('Unknown error: $e'));
  }
}

// Result class
class Result<T> {
  final T? data;
  final AppException? error;

  bool get isSuccess => error == null;
  bool get isFailure => error != null;

  Result.success(this.data) : error = null;
  Result.failure(this.error) : data = null;
}
```

### 5. Code Organization

#### File Naming
- `snake_case.dart` for all files
- Suffix with type: `_repository.dart`, `_service.dart`, `_model.dart`, `_screen.dart`

#### Class Naming
- `PascalCase` for classes
- `camelCase` for methods and variables
- `SCREAMING_SNAKE_CASE` for constants

#### Folder Structure Rules
- Group by feature, not by type
- Each feature folder is self-contained
- Shared code goes in `core/`

### 6. Testing Strategy

#### Test Pyramid
```
     /\
    /E2E\      (Few - Expensive)
   /------\
  /Widget \    (Some - Medium cost)
 /----------\
/   Unit     \  (Many - Cheap)
```

#### Unit Test Pattern
```dart
// Arrange-Act-Assert
void main() {
  group('NoteRepository', () {
    late NoteRepository repository;
    late MockLocalStorage mockStorage;

    setUp(() {
      mockStorage = MockLocalStorage();
      repository = NoteRepository(mockStorage);
    });

    test('getAllNotes returns all notes', () async {
      // Arrange
      final expectedNotes = [Note(id: '1', title: 'Test')];
      when(mockStorage.getNotes()).thenAnswer((_) async => expectedNotes);

      // Act
      final result = await repository.getAllNotes();

      // Assert
      expect(result, expectedNotes);
      verify(mockStorage.getNotes()).called(1);
    });
  });
}
```

#### Mocking Strategy
- Use `mockito` for generating mocks
- Mock all external dependencies (Firebase, Hive)
- Use `fake` implementations for simple cases

### 7. Documentation Standards

#### Dart Doc Comments
```dart
/// Manages note creation, retrieval, and synchronization.
///
/// This repository provides offline-first access to notes, automatically
/// syncing with Firebase when online.
///
/// Example:
/// ```dart
/// final repository = NoteRepository(localStorage, firebaseService);
/// final note = await repository.getNote('123');
/// ```
class NoteRepository {
  /// Creates a new note and saves it locally.
  ///
  /// The note will be synced to Firebase when the device is online.
  ///
  /// Throws [ValidationException] if the note data is invalid.
  /// Throws [StorageException] if local save fails.
  Future<Note> createNote(Note note) async {
    // Implementation
  }
}
```

#### Inline Comments
- Explain **why**, not **what**
- Use comments sparingly - prefer self-documenting code
- Add TODO comments with ticket references: `// TODO(PRMPT-123): Implement pagination`

### 8. Performance Guidelines

#### Lazy Loading
```dart
// Don't load all notes at once
class HomeViewModel extends ChangeNotifier {
  static const int pageSize = 20;
  int _currentPage = 0;

  Future<void> loadMoreNotes() async {
    final notes = await _repository.getNotes(
      offset: _currentPage * pageSize,
      limit: pageSize,
    );
    _notes.addAll(notes);
    _currentPage++;
    notifyListeners();
  }
}
```

#### Image Optimization
```dart
// Compress images before upload
Future<String> uploadImage(File imageFile) async {
  final compressed = await FlutterImageCompress.compressWithFile(
    imageFile.absolute.path,
    quality: 85,
    maxWidth: 1024,
    maxHeight: 1024,
  );
  return await _firebaseStorage.upload(compressed);
}
```

#### Caching Strategy
```dart
// Cache frequently accessed data
class NoteRepository {
  final Map<String, Note> _cache = {};

  Future<Note> getNote(String id) async {
    if (_cache.containsKey(id)) {
      return _cache[id]!;
    }

    final note = await _localStorage.getNote(id);
    _cache[id] = note;
    return note;
  }
}
```

### 9. Security Best Practices

#### Input Validation
```dart
class NoteValidator {
  static ValidationResult validate(Note note) {
    if (note.title.trim().isEmpty) {
      return ValidationResult.error('Title cannot be empty');
    }

    if (note.title.length > 200) {
      return ValidationResult.error('Title too long (max 200 characters)');
    }

    if (note.content.length > 100000) {
      return ValidationResult.error('Content too long (max 100KB)');
    }

    return ValidationResult.valid();
  }
}
```

#### Sanitization
```dart
// Sanitize template placeholders to prevent injection
String renderTemplate(String template, Map<String, String> values) {
  var result = template;

  for (final entry in values.entries) {
    final sanitized = _sanitizeValue(entry.value);
    result = result.replaceAll('{{${entry.key}}}', sanitized);
  }

  return result;
}

String _sanitizeValue(String value) {
  // Remove potentially dangerous characters
  return value
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');
}
```

#### Local Encryption
```dart
// Enable Hive encryption for sensitive data
await Hive.openBox<Note>(
  'notes',
  encryptionCipher: HiveAesCipher(encryptionKey),
);
```

### 10. Accessibility Guidelines

```dart
// Always provide semantic labels
Semantics(
  label: 'Delete note',
  button: true,
  child: IconButton(
    icon: Icon(Icons.delete),
    onPressed: _deleteNote,
  ),
)

// Support screen readers
Text(
  note.title,
  semanticsLabel: 'Note title: ${note.title}',
)

// Ensure sufficient contrast ratios (WCAG AA: 4.5:1)
// Support text scaling
Text(
  note.title,
  style: TextStyle(fontSize: 16), // Will scale with user's text size setting
)
```

### 11. Responsive Design

```dart
class ResponsiveLayout extends StatelessWidget {
  final Widget mobile;
  final Widget? tablet;
  final Widget? desktop;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 600) {
          return mobile;
        } else if (constraints.maxWidth < 1200) {
          return tablet ?? mobile;
        } else {
          return desktop ?? tablet ?? mobile;
        }
      },
    );
  }
}
```

### 12. Git Workflow

#### Commit Messages
```
feat: add note editing capability
fix: resolve sync conflict crash
refactor: extract sync logic to service
docs: update API documentation
test: add unit tests for NoteRepository
chore: update dependencies
```

#### Branch Strategy
- `main` - production-ready code
- `develop` - integration branch
- `feature/feature-name` - new features
- `fix/bug-description` - bug fixes

#### Pull Request Checklist
- [ ] Code follows style guide
- [ ] All tests pass
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] No console warnings
- [ ] Performance verified
- [ ] Accessibility verified

### 13. Code Review Checklist

#### Functionality
- [ ] Does it work as expected?
- [ ] Are edge cases handled?
- [ ] Is error handling comprehensive?

#### Code Quality
- [ ] Is it readable and maintainable?
- [ ] Is it properly tested?
- [ ] Are there any code smells?
- [ ] Is it following SOLID principles?

#### Performance
- [ ] Are there any obvious performance issues?
- [ ] Is data loading efficient?
- [ ] Are images optimized?

#### Security
- [ ] Is user input validated?
- [ ] Are there any injection vulnerabilities?
- [ ] Is sensitive data protected?

### 14. Anti-Patterns to Avoid

#### ❌ Don't
```dart
// God class - does too much
class NoteManager {
  void createNote() {}
  void deleteNote() {}
  void syncNote() {}
  void validateNote() {}
  void renderNote() {}
  void exportNote() {}
}

// Tight coupling
class HomeScreen extends StatelessWidget {
  final FirebaseFirestore firestore = FirebaseFirestore.instance;
  // Directly depends on Firebase - hard to test
}

// Magic numbers
Timer.periodic(Duration(seconds: 30), (_) => sync());
```

#### ✅ Do
```dart
// Single responsibility
class NoteRepository {}
class SyncService {}
class NoteValidator {}

// Dependency injection
class HomeScreen extends StatelessWidget {
  final NoteRepository repository;
  HomeScreen({required this.repository});
}

// Named constants
class SyncConfig {
  static const Duration syncInterval = Duration(seconds: 30);
}
```

### 15. Performance Monitoring

```dart
// Add performance tracking
class PerformanceMonitor {
  static Future<T> track<T>(String operationName, Future<T> Function() operation) async {
    final stopwatch = Stopwatch()..start();

    try {
      final result = await operation();
      stopwatch.stop();

      _logPerformance(operationName, stopwatch.elapsedMilliseconds);
      return result;
    } catch (e) {
      stopwatch.stop();
      _logError(operationName, stopwatch.elapsedMilliseconds, e);
      rethrow;
    }
  }
}

// Usage
final notes = await PerformanceMonitor.track(
  'loadNotes',
  () => repository.getAllNotes(),
);
```

## Summary

These principles ensure:
- ✅ Maintainable, testable code
- ✅ Consistent architecture
- ✅ Clear separation of concerns
- ✅ Robust error handling
- ✅ Performance optimization
- ✅ Security by default
- ✅ Accessible UI
- ✅ Team collaboration standards

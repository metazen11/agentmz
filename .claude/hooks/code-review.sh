#!/usr/bin/env bash
#
# Claude Code Hook: Post-Write/Edit Code Review
#
# Validates that code written by Claude meets quality standards:
#   1. Simplest solution (no over-engineering)
#   2. Security best practices (OWASP)
#   3. Canonical naming conventions
#   4. Syntactically valid
#   5. Clear and well-documented
#
# Exit codes:
#   0 - All checks passed
#   2 - Blocking error (shown to Claude for correction)
#

set -o pipefail

# Read input from stdin
INPUT=$(cat)

# Extract file path from tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]] || [[ ! -f "$FILE_PATH" ]]; then
  exit 0  # No file to check
fi

# Determine file type
EXT="${FILE_PATH##*.}"
ISSUES=""
WARNINGS=""

add_issue() {
  ISSUES="${ISSUES}ERROR: $1\n"
}

add_warning() {
  WARNINGS="${WARNINGS}WARNING: $1\n"
}

#######################################
# 1. SIMPLICITY CHECK
#######################################
case "$EXT" in
  py)
    # Deep inheritance
    if grep -qE "class.*\(.*\(.*\(" "$FILE_PATH" 2>/dev/null; then
      add_warning "Deep class inheritance detected - consider composition over inheritance"
    fi

    # Overly complex one-liners (>100 chars with multiple operations)
    if grep -E "^.{100,}(for|if|else|and|or).*:" "$FILE_PATH" 2>/dev/null | head -1; then
      add_warning "Complex one-liner detected - consider breaking into multiple lines"
    fi
    ;;
  js|ts)
    # Deeply nested callbacks
    if grep -cE "(\{|\()" "$FILE_PATH" 2>/dev/null | awk '{if($1>50) exit 0; else exit 1}'; then
      if grep -qE "\)\s*=>\s*\{.*\)\s*=>\s*\{.*\)\s*=>\s*\{" "$FILE_PATH" 2>/dev/null; then
        add_warning "Deeply nested callbacks - consider async/await or extracting functions"
      fi
    fi
    ;;
esac

#######################################
# 2. SECURITY CHECK
#######################################
case "$EXT" in
  py)
    # SQL injection risk
    if grep -nE "(execute|raw)\s*\(.*(%s|%d|\.format|\+\s*['\"])" "$FILE_PATH" 2>/dev/null | grep -v "# nosec"; then
      add_issue "Potential SQL injection - use parameterized queries"
    fi

    # Command injection
    if grep -nE "(os\.system|subprocess\.(call|run|Popen))\s*\([^)]*\+" "$FILE_PATH" 2>/dev/null | grep -v "# nosec"; then
      add_issue "Potential command injection - avoid string concatenation in shell commands"
    fi

    # Hardcoded secrets
    if grep -niE "(password|secret|api_key|token|private_key)\s*=\s*['\"][^'\"]{8,}['\"]" "$FILE_PATH" 2>/dev/null | grep -v "# nosec\|example\|placeholder\|test"; then
      add_issue "Hardcoded secret detected - use environment variables"
    fi

    # Pickle usage (deserialization risk)
    if grep -qE "pickle\.(load|loads)" "$FILE_PATH" 2>/dev/null; then
      add_warning "Pickle usage detected - ensure trusted data source only"
    fi
    ;;

  js|ts)
    # XSS via innerHTML
    if grep -nE "innerHTML\s*=" "$FILE_PATH" 2>/dev/null; then
      add_warning "innerHTML assignment - ensure content is sanitized"
    fi

    # eval usage
    if grep -nE "\beval\s*\(" "$FILE_PATH" 2>/dev/null; then
      add_issue "eval() is a security risk - use safer alternatives"
    fi

    # Hardcoded secrets
    if grep -niE "(password|secret|api_key|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]" "$FILE_PATH" 2>/dev/null | grep -v "example\|placeholder\|test"; then
      add_issue "Hardcoded secret detected - use environment variables"
    fi
    ;;

  sh|bash)
    # Unquoted variables
    if grep -nE '\$[a-zA-Z_][a-zA-Z0-9_]*[^"'\''a-zA-Z0-9_}]' "$FILE_PATH" 2>/dev/null | grep -v "# nosec" | head -3; then
      add_warning "Unquoted variable - use \"\$VAR\" to prevent word splitting"
    fi
    ;;
esac

#######################################
# 3. NAMING CONVENTIONS
#######################################
case "$EXT" in
  py)
    # Non-snake_case functions
    if grep -nE "^def [a-z]+[A-Z]" "$FILE_PATH" 2>/dev/null; then
      add_warning "Function name should be snake_case, not camelCase"
    fi

    # Non-PascalCase classes
    if grep -nE "^class [a-z]" "$FILE_PATH" 2>/dev/null; then
      add_warning "Class name should be PascalCase"
    fi

    # Constants not UPPER_CASE (module level)
    if grep -nE "^[a-z_]+\s*=\s*['\"].*['\"]$" "$FILE_PATH" 2>/dev/null | head -3; then
      # This is a loose check - might have false positives
      :
    fi
    ;;

  js|ts)
    # Non-camelCase functions
    if grep -nE "function\s+[a-z]+_[a-z]+" "$FILE_PATH" 2>/dev/null; then
      add_warning "Function name should be camelCase, not snake_case"
    fi

    # Non-PascalCase classes/components
    if grep -nE "^(class|function)\s+[a-z]" "$FILE_PATH" 2>/dev/null | grep -v "export\|const\|let\|var"; then
      # Loose check
      :
    fi
    ;;
esac

#######################################
# 4. SYNTAX VALIDATION
#######################################
case "$EXT" in
  py)
    if command -v python3 >/dev/null 2>&1; then
      if ! python3 -m py_compile "$FILE_PATH" 2>&1; then
        add_issue "Python syntax error - code will not run"
      fi
    fi
    ;;

  js)
    if command -v node >/dev/null 2>&1; then
      if ! node --check "$FILE_PATH" 2>&1; then
        add_issue "JavaScript syntax error - code will not run"
      fi
    fi
    ;;

  sh|bash)
    if command -v bash >/dev/null 2>&1; then
      if ! bash -n "$FILE_PATH" 2>&1; then
        add_issue "Bash syntax error - script will not run"
      fi
    fi
    ;;

  json)
    if command -v jq >/dev/null 2>&1; then
      if ! jq empty "$FILE_PATH" 2>&1; then
        add_issue "Invalid JSON syntax"
      fi
    fi
    ;;
esac

#######################################
# 5. DOCUMENTATION CHECK
#######################################
case "$EXT" in
  py)
    # Count functions vs docstrings
    func_count=$(grep -cE "^\s*def " "$FILE_PATH" 2>/dev/null || echo 0)
    doc_count=$(grep -cE '^\s*"""' "$FILE_PATH" 2>/dev/null || echo 0)

    if [[ $func_count -gt 2 ]] && [[ $doc_count -lt 1 ]]; then
      add_warning "No docstrings found - add documentation for functions"
    fi
    ;;

  js|ts)
    # Check for JSDoc comments
    func_count=$(grep -cE "(function|=>)" "$FILE_PATH" 2>/dev/null || echo 0)
    jsdoc_count=$(grep -cE "/\*\*" "$FILE_PATH" 2>/dev/null || echo 0)

    if [[ $func_count -gt 3 ]] && [[ $jsdoc_count -lt 1 ]]; then
      add_warning "Consider adding JSDoc comments for complex functions"
    fi
    ;;
esac

# Check line length
long_lines=$(awk 'length > 120' "$FILE_PATH" 2>/dev/null | wc -l)
if [[ $long_lines -gt 5 ]]; then
  add_warning "$long_lines lines exceed 120 characters - consider breaking up"
fi

#######################################
# OUTPUT RESULTS
#######################################

# If there are blocking issues, exit with code 2
if [[ -n "$ISSUES" ]]; then
  echo "Code review found issues in $FILE_PATH:"
  echo ""
  echo -e "$ISSUES"
  if [[ -n "$WARNINGS" ]]; then
    echo -e "$WARNINGS"
  fi
  echo ""
  echo "Please fix these issues before proceeding."
  exit 2
fi

# If there are only warnings, show them but don't block
if [[ -n "$WARNINGS" ]]; then
  echo "Code review warnings for $FILE_PATH:"
  echo ""
  echo -e "$WARNINGS"
  # Don't exit with error - just inform
fi

exit 0

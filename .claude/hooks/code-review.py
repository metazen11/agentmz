#!/usr/bin/env python3
"""
Claude Code Hook: Post-Write/Edit Code Review

Cross-platform code quality validator for Claude Code.

Validates that code meets quality standards:
  1. Simplest solution (no over-engineering)
  2. Security best practices (OWASP)
  3. Canonical naming conventions
  4. Syntactically valid
  5. Clear and well-documented

Exit codes:
  0 - All checks passed
  2 - Blocking error (shown to Claude for correction)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def read_input():
    """Read JSON input from stdin."""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return {}


def get_file_path(input_data):
    """Extract file path from tool input."""
    tool_input = input_data.get("tool_input", {})
    return tool_input.get("file_path", "")


class CodeReview:
    def __init__(self, file_path):
        self.file_path = Path(file_path)
        self.ext = self.file_path.suffix.lstrip(".")
        self.issues = []
        self.warnings = []
        self.content = ""

        if self.file_path.exists():
            try:
                self.content = self.file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

    def add_issue(self, msg):
        self.issues.append(f"ERROR: {msg}")

    def add_warning(self, msg):
        self.warnings.append(f"WARNING: {msg}")

    def check_simplicity(self):
        """Check for over-engineering patterns."""
        if self.ext == "py":
            # Deep inheritance
            if re.search(r"class.*\(.*\(.*\(", self.content):
                self.add_warning("Deep class inheritance - consider composition")

            # Complex one-liners
            for i, line in enumerate(self.content.split("\n"), 1):
                if len(line) > 100 and re.search(r"(for|if|else|and|or).*:", line):
                    self.add_warning(f"Line {i}: Complex one-liner - consider breaking up")
                    break

        elif self.ext in ("js", "ts"):
            # Deeply nested callbacks
            if re.search(r"\)\s*=>\s*\{.*\)\s*=>\s*\{.*\)\s*=>\s*\{", self.content):
                self.add_warning("Nested callbacks - consider async/await")

    def check_security(self):
        """Check for security vulnerabilities."""
        lines = self.content.split("\n")

        if self.ext == "py":
            for i, line in enumerate(lines, 1):
                if "# nosec" in line:
                    continue

                # SQL injection detection
                if re.search(r"(execute|raw)\s*\(.*(%s|%d|\.format|\+)", line):  # nosec
                    self.add_issue(f"Line {i}: Potential SQL injection")

                # Command injection
                if re.search(r"(os\.system|subprocess\.(call|run|Popen))\s*\([^)]*\+", line):
                    self.add_issue(f"Line {i}: Potential command injection")

                # Hardcoded secrets
                if re.search(r"(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]", line, re.I):
                    if not any(x in line.lower() for x in ["example", "placeholder", "test"]):
                        self.add_issue(f"Line {i}: Hardcoded secret detected")

                # Pickle
                if "pickle.load" in line:
                    self.add_warning(f"Line {i}: Pickle usage - ensure trusted source")

        elif self.ext in ("js", "ts"):
            for i, line in enumerate(lines, 1):
                # XSS
                if "innerHTML" in line and "=" in line:
                    self.add_warning(f"Line {i}: innerHTML - ensure sanitized content")

                # eval
                if re.search(r"\beval\s*\(", line):
                    self.add_issue(f"Line {i}: eval() is a security risk")  # nosec

                # Hardcoded secrets
                if re.search(r"(password|secret|api_key|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]", line, re.I):
                    if not any(x in line.lower() for x in ["example", "placeholder", "test"]):
                        self.add_issue(f"Line {i}: Hardcoded secret detected")

        elif self.ext in ("sh", "bash"):
            for i, line in enumerate(lines, 1):
                if "# nosec" in line:
                    continue
                # Unquoted variables (simplified check)
                if re.search(r'\$[a-zA-Z_][a-zA-Z0-9_]*[^"\'\a-zA-Z0-9_}]', line):
                    self.add_warning(f"Line {i}: Unquoted variable - use \"$VAR\"")

    def check_naming(self):
        """Check naming conventions."""
        lines = self.content.split("\n")

        if self.ext == "py":
            for i, line in enumerate(lines, 1):
                # Non-snake_case functions
                if re.match(r"^\s*def [a-z]+[A-Z]", line):
                    self.add_warning(f"Line {i}: Function should be snake_case")

                # Non-PascalCase classes
                if re.match(r"^\s*class [a-z]", line):
                    self.add_warning(f"Line {i}: Class should be PascalCase")

        elif self.ext in ("js", "ts"):
            for i, line in enumerate(lines, 1):
                # Non-camelCase functions
                if re.search(r"function\s+[a-z]+_[a-z]+", line):
                    self.add_warning(f"Line {i}: Function should be camelCase")

    def check_syntax(self):
        """Validate syntax."""
        if not self.file_path.exists():
            return

        try:
            if self.ext == "py":
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(self.file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    self.add_issue(f"Python syntax error: {result.stderr.strip()}")

            elif self.ext == "js":
                result = subprocess.run(
                    ["node", "--check", str(self.file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    self.add_issue(f"JavaScript syntax error: {result.stderr.strip()}")

            elif self.ext == "json":
                json.loads(self.content)

        except subprocess.TimeoutExpired:
            pass
        except FileNotFoundError:
            pass  # Tool not available
        except json.JSONDecodeError as e:
            self.add_issue(f"Invalid JSON: {e}")

    def check_documentation(self):
        """Check for documentation."""
        lines = self.content.split("\n")

        if self.ext == "py":
            func_count = len(re.findall(r"^\s*def ", self.content, re.M))
            doc_count = self.content.count('"""')

            if func_count > 2 and doc_count < 1:
                self.add_warning("No docstrings - add documentation for functions")

        elif self.ext in ("js", "ts"):
            func_count = len(re.findall(r"(function|=>)", self.content))
            jsdoc_count = self.content.count("/**")

            if func_count > 3 and jsdoc_count < 1:
                self.add_warning("Consider adding JSDoc comments")

        # Line length
        long_lines = sum(1 for line in lines if len(line) > 120)
        if long_lines > 5:
            self.add_warning(f"{long_lines} lines exceed 120 chars")

    def run_all_checks(self):
        """Run all code review checks."""
        self.check_simplicity()
        self.check_security()
        self.check_naming()
        self.check_syntax()
        self.check_documentation()

    def report(self):
        """Generate report and exit with appropriate code."""
        if self.issues:
            print(f"Code review found issues in {self.file_path}:\n")
            for issue in self.issues:
                print(issue)
            if self.warnings:
                print()
                for warning in self.warnings:
                    print(warning)
            print("\nPlease fix these issues before proceeding.")
            sys.exit(2)

        if self.warnings:
            print(f"Code review warnings for {self.file_path}:\n")
            for warning in self.warnings:
                print(warning)

        sys.exit(0)


def main():
    input_data = read_input()
    file_path = get_file_path(input_data)

    if not file_path or not Path(file_path).exists():
        sys.exit(0)

    # Skip certain files
    skip_patterns = [".min.js", ".min.css", "node_modules", "__pycache__", ".pyc"]
    if any(p in file_path for p in skip_patterns):
        sys.exit(0)

    review = CodeReview(file_path)
    review.run_all_checks()
    review.report()


if __name__ == "__main__":
    main()

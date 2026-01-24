#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "${script_dir}/run_aider_local.sh" ]; then
  echo "run_aider_local.sh not found in ${script_dir}" >&2
  return 1 2>/dev/null || exit 1
fi

aicoder() {
  "${script_dir}/run_aider_local.sh" "$@"
}

run_aider_local() {
  "${script_dir}/run_aider_local.sh" "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  cat <<EOF
To register the 'aicoder' command in your current shell:
  source "${script_dir}/wrapper_init.sh"

To make it permanent, add this line to your ~/.bashrc or ~/.zshrc:
  source "${script_dir}/wrapper_init.sh"
EOF
fi

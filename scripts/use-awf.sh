#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf 'Source this helper instead of executing it: source scripts/use-awf.sh\n' >&2
  exit 2
fi

_awf_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_awf_invoke_repo_command() {
  local name="$1"
  shift
  local command_path="$_awf_repo_root/backend/.venv/bin/$name"
  if [[ ! -x "$command_path" ]]; then
    printf "AWF command '%s' was not found at '%s'. Run 'scripts/bootstrap.sh' from the repo root first.\n" "$name" "$command_path" >&2
    return 127
  fi
  "$command_path" "$@"
}

awf() {
  _awf_invoke_repo_command awf "$@"
}

awf-setup() {
  _awf_invoke_repo_command awf-setup "$@"
}

awf-secret() {
  _awf_invoke_repo_command awf-secret "$@"
}

awf-speech() {
  _awf_invoke_repo_command awf-speech "$@"
}

awf-gui() {
  if ! command -v npm >/dev/null 2>&1; then
    printf "npm was not found. Install Node.js/npm, then rerun 'scripts/bootstrap.sh' if frontend dependencies are missing.\n" >&2
    return 127
  fi
  (cd "$_awf_repo_root" && npm --prefix frontend run dev "$@")
}

awf-cli() {
  if ! command -v node >/dev/null 2>&1; then
    printf "node was not found. Install Node.js/npm, then rerun 'scripts/bootstrap.sh' if frontend dependencies are missing.\n" >&2
    return 127
  fi
  local entry_point="$_awf_repo_root/frontend/cli/dist/cli.js"
  if [[ ! -f "$entry_point" ]]; then
    printf "The AWF terminal UI is not built. Run 'npm --prefix frontend run build' from the repo root first.\n" >&2
    return 127
  fi
  (cd "$_awf_repo_root" && node frontend/cli/dist/cli.js "$@")
}

printf 'AWF commands loaded for this shell session: awf, awf-setup, awf-secret, awf-speech, awf-gui, awf-cli\n'

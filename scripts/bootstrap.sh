#!/usr/bin/env bash
set -euo pipefail

skip_frontend=false
skip_speech=false
for arg in "$@"; do
  case "$arg" in
    --skip-frontend) skip_frontend=true ;;
    --skip-speech) skip_speech=true ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_python="$repo_root/backend/.venv/bin/python"
venv_awf_speech="$repo_root/backend/.venv/bin/awf-speech"
venv_awf="$repo_root/backend/.venv/bin/awf"

step() {
  printf '==> %s\n' "$1"
}

cd "$repo_root"
mkdir -p "$repo_root/cache/temp"

if [[ ! -x "$venv_python" ]]; then
  step "Create backend venv"
  python3.12 -m venv "$repo_root/backend/.venv"
fi

step "Upgrade pip"
"$venv_python" -m pip install --upgrade pip

step "Install AWF base package"
"$venv_python" -m pip install -e ".[dev]"

step "Install hardware-selected backend dependencies"
"$venv_python" -m awf.setup --install --verify

step "Bootstrap local state"
"$venv_python" -m awf.setup

if [[ "$skip_speech" != true ]]; then
  step "Acquire speech models"
  "$venv_awf_speech" models sync
  step "Verify speech models"
  "$venv_awf_speech" models verify
else
  step "Skip speech setup"
  printf '    Speech is part of the normal operator path; use --skip-speech only for dependency outage triage.\n'
fi

if [[ "$skip_frontend" != true ]] && command -v npm >/dev/null 2>&1; then
  step "Install frontend dependencies"
  npm --prefix frontend install
fi

step "Doctor"
"$venv_awf" doctor

printf '\nNext command:\n'
printf 'backend/.venv/bin/awf run assistant-default@1.0.0 --objective "check the system"\n'

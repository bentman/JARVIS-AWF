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
venv_root="$repo_root/backend/.venv"
venv_awf_speech="$repo_root/backend/.venv/bin/awf-speech"
venv_awf="$repo_root/backend/.venv/bin/awf"
reports_dir="$repo_root/reports/diagnostics"
timestamp="$(date +%Y%m%d-%H%M%S)"
report_path="$reports_dir/${timestamp}-bootstrap.txt"

mkdir -p "$reports_dir"
exec > >(tee -a "$report_path") 2>&1
trap 'rc=$?; printf "\nBootstrap report: %s\n" "$report_path"; exit "$rc"' EXIT

step() {
  printf '==> %s\n' "$1"
}

cd "$repo_root"
mkdir -p "$repo_root/cache/temp"

pyvenv_cfg="$venv_root/pyvenv.cfg"
if [[ -f "$pyvenv_cfg" && -x "$venv_root/Scripts/python.exe" ]]; then
  if grep -Eq '(^home = [A-Za-z]:\\|Scripts\\python\.exe|\\)' "$pyvenv_cfg"; then
    printf 'backend/.venv was created by Windows. Remove backend/.venv and rerun scripts/bootstrap.sh from Linux/WSL.\n' >&2
    exit 1
  fi
fi

resolve_host_python() {
  local candidates=("python3" "python" "python3.14" "python3.13" "python3.12")
  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" >/dev/null 2>&1; then
      local ver
      ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
      if [[ -n "$ver" ]]; then
        local major="${ver%%.*}"
        local minor="${ver#*.}"
        if [[ "$major" -eq 3 && "$minor" -ge 12 && "$minor" -lt 15 ]]; then
          echo "$cmd"
          return 0
        fi
      fi
    fi
  done
  echo "No compatible Python executable (>=3.12,<3.15) found. Install Python 3.12, 3.13, or 3.14." >&2
  return 1
}

if [[ ! -x "$venv_python" ]]; then
  host_python="$(resolve_host_python)"
  step "Create backend venv using $host_python"
  "$host_python" -m venv "$repo_root/backend/.venv"
fi

step "Upgrade pip"
"$venv_python" -m pip install --upgrade pip

step "Install AWF base package"
"$venv_python" -m pip install -e ".[dev]"

step "Provision hardware-selected backend dependencies"
"$venv_python" -m awf.setup --provision

step "Install hardware-selected backend dependencies"
"$venv_python" -m awf.setup --install --verify

step "Profile hardware readiness"
"$venv_python" scripts/validate_backend.py profile

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

printf '\nNext commands:\n'
printf 'source scripts/use-awf.sh\n'
printf 'awf run assistant-default@1.0.0 --objective "check the system"\n'

#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_VERSION="3.12"
NODE_VERSION="20.19.0"

log() {
  printf '\n==> %s\n' "$1"
}

fail() {
  printf '\nError: %s\n' "$1" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_block_in_file() {
  local file="$1"
  local block="$2"

  mkdir -p "$(dirname "$file")"
  touch "$file"

  if grep -Fq "# >>> prox-challenge toolchain >>>" "$file"; then
    return
  fi

  {
    printf '\n'
    printf '%s\n' "$block"
  } >>"$file"
}

persist_path_setup() {
  local path_block
  path_block=$(cat <<'EOF'
# >>> prox-challenge toolchain >>>
export PATH="$HOME/.local/bin:$PATH"
export VOLTA_HOME="${VOLTA_HOME:-$HOME/.volta}"
export PATH="$VOLTA_HOME/bin:$PATH"
# <<< prox-challenge toolchain <<<
EOF
)

  ensure_block_in_file "${HOME}/.profile" "$path_block"

  case "${SHELL:-}" in
    */zsh)
      ensure_block_in_file "${HOME}/.zshrc" "$path_block"
      ;;
    */bash)
      ensure_block_in_file "${HOME}/.bashrc" "$path_block"
      ;;
  esac
}

run_remote_script() {
  local url="$1"
  if have_cmd curl; then
    curl -fsSL "$url"
  elif have_cmd wget; then
    wget -qO- "$url"
  else
    fail "Neither curl nor wget is installed. Please install one of them and rerun the setup script."
  fi
}

ensure_uv() {
  if have_cmd uv; then
    return
  fi

  log "Installing uv"
  run_remote_script "https://astral.sh/uv/install.sh" | sh
  export PATH="${HOME}/.local/bin:${PATH}"

  have_cmd uv || fail "uv was installed but is not on PATH. Add \$HOME/.local/bin to your shell PATH and rerun."
}

ensure_volta() {
  if have_cmd volta; then
    return
  fi

  log "Installing Volta"
  run_remote_script "https://get.volta.sh" | bash -s -- --skip-setup
  export VOLTA_HOME="${VOLTA_HOME:-${HOME}/.volta}"
  export PATH="${VOLTA_HOME}/bin:${PATH}"

  have_cmd volta || fail "Volta was installed but is not on PATH. Add \$HOME/.volta/bin to your shell PATH and rerun."
}

copy_env_file() {
  if [[ -f "${REPO_ROOT}/.env" ]]; then
    log ".env already exists, leaving it untouched"
    return
  fi

  if [[ ! -f "${REPO_ROOT}/.env.example" ]]; then
    fail ".env.example is missing from the repository root."
  fi

  log "Creating .env from .env.example"
  cp "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.env"
}

main() {
  log "Preparing toolchain"
  persist_path_setup
  export PATH="${HOME}/.local/bin:${PATH}"
  export VOLTA_HOME="${VOLTA_HOME:-${HOME}/.volta}"
  export PATH="${VOLTA_HOME}/bin:${PATH}"

  ensure_uv
  ensure_volta

  log "Installing Node.js ${NODE_VERSION} with Volta"
  volta install "node@${NODE_VERSION}"

  log "Installing Python ${PYTHON_VERSION} with uv"
  uv python install "${PYTHON_VERSION}"

  copy_env_file

  log "Installing backend dependencies"
  (
    cd "${REPO_ROOT}"
    uv sync --python "${PYTHON_VERSION}"
  )

  log "Installing frontend dependencies"
  (
    cd "${REPO_ROOT}/frontend"
    npm install
  )

  cat <<EOF

Setup complete.

Next steps:
1. Open ${REPO_ROOT}/.env
2. Add your API keys
3. Close this shell/terminal session completely
4. Open a fresh terminal
5. Start the backend: PYTHONPATH=src uv run uvicorn prox_agent.api:app --port 8000 --reload
6. Start the frontend: cd frontend && npm run dev

Installed versions:
- Python ${PYTHON_VERSION} via uv
- Node ${NODE_VERSION} via Volta

PATH updates were written to your shell profile so future terminals can find uv and Volta-managed Node.
Close this terminal before running the app so the new PATH entries are picked up cleanly.
EOF
}

main "$@"

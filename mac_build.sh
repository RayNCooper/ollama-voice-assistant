#!/usr/bin/env bash
#
# mac_build.sh — build the Ollama Voice Assistant desktop app (.app + .dmg) on macOS.
#
# The Tauri shell bundles a webview that loads the existing frontend and spawns
# the Python backend (ASR + LLM + TTS) as child processes at runtime. This
# script prepares the Python side, checks the Rust toolchain, and runs the
# Tauri bundler. The resulting app expects this repo (with its .venv and model
# weights) to stay in place — it is a locally built tool, not a redistributable.
#
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

TAURI_DIR="$ROOT_DIR/tauri"
BUNDLE_DIR="$TAURI_DIR/src-tauri/target/release/bundle"

step() { printf '\n\033[1;35m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\033[1;31mmac_build: %s\033[0m\n' "$*" >&2; exit 1; }

# --- 0. Platform check ------------------------------------------------------
step "Checking platform"
if [[ "$(uname -s)" != "Darwin" ]]; then
  die "this script only builds the macOS .app/.dmg and must be run on macOS.
       On Linux/CUDA use ./ova.sh (browser UI) instead."
fi
info "macOS detected ($(uname -m))."

# --- 1. uv + virtualenv -----------------------------------------------------
step "Ensuring uv and the Python virtualenv"
command -v uv >/dev/null 2>&1 || die "'uv' not found in PATH. Install it: https://docs.astral.sh/uv/"
if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  info "Creating .venv"
  uv venv
else
  info ".venv already exists — reusing it."
fi

# --- 2. Python dependencies -------------------------------------------------
step "Installing Python deps (macOS variant of the local ASR/TTS stack)"
info "torch / NeMo run on Apple Silicon via CPU/MPS. We install the same"
info "packages as the Linux '[cuda]' extra MINUS 'cuda-python': that package"
info "(and its 'cuda-bindings' dependency) publishes Linux/Windows wheels"
info "only, so '.[cuda]' is unsatisfiable on Darwin and would abort the build."
uv pip install -e "." torch torchaudio "nemo-toolkit[asr]"

# --- 3. Rust / Cargo toolchain ---------------------------------------------
step "Checking the Rust toolchain (required by Tauri)"
command -v cargo >/dev/null 2>&1 || die "'cargo' not found in PATH. Install Rust: https://rustup.rs/"
info "cargo: $(cargo --version)"

# Tauri CLI (v2). Installed as a cargo subcommand if missing.
if ! cargo tauri --version >/dev/null 2>&1; then
  step "Installing the Tauri CLI (cargo-tauri v2)"
  cargo install tauri-cli --version '^2.0.0' --locked
fi
info "tauri: $(cargo tauri --version)"

# --- 4. Icons (best-effort regeneration) -----------------------------------
step "Regenerating platform icons from icons/app-icon.png"
if cargo tauri icon "$TAURI_DIR/src-tauri/icons/app-icon.png" >/dev/null 2>&1; then
  info "Icons regenerated from the Olio brand mark."
else
  info "Skipped icon regeneration (using the committed icons)."
fi

# --- 5. Build the app -------------------------------------------------------
step "Building the desktop app (cargo tauri build)"
info "First build compiles the Rust deps and may take several minutes."
cd "$TAURI_DIR"
cargo tauri build

# --- 6. Done ----------------------------------------------------------------
step "Build complete"
info "Bundles are under:"
info "  $BUNDLE_DIR/macos/*.app"
info "  $BUNDLE_DIR/dmg/*.dmg"
echo
info "First launch downloads the ASR/TTS weights (a few minutes) unless you"
info "already ran './ova.sh install --cuda'. Set OLLAMA_API_KEY in the launch"
info "environment (or launch from a terminal) so the Ollama Cloud brain works."

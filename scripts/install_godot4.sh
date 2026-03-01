#!/usr/bin/env bash
set -euo pipefail

# Installs Godot 4 in a way that works for exptools2 subprocess experiments.
# - macOS: Homebrew cask (preferred), fallback to GitHub release zip.
# - Linux: apt/flatpak when available, fallback to GitHub release zip.

VERSION="${GODOT_VERSION:-4.2.2-stable}"
INSTALL_DIR="${GODOT_INSTALL_DIR:-$HOME/.local/opt/godot4}"
BIN_DIR="${GODOT_BIN_DIR:-$HOME/.local/bin}"

log() {
  printf '[install_godot4] %s\n' "$*"
}

ensure_bin_dir() {
  mkdir -p "$BIN_DIR"
}

install_from_github_zip_linux() {
  local arch url tmp exe_path
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) arch="x86_64" ;;
    aarch64|arm64) arch="arm64" ;;
    *)
      log "Unsupported Linux arch: $arch"
      return 1
      ;;
  esac

  url="https://github.com/godotengine/godot-builds/releases/download/${VERSION}/Godot_v${VERSION}_linux.${arch}.zip"
  tmp="$(mktemp -d)"
  log "Downloading $url"
  curl -L "$url" -o "$tmp/godot.zip"
  unzip -q "$tmp/godot.zip" -d "$tmp"

  exe_path="$(find "$tmp" -maxdepth 2 -type f -name "Godot_v*linux.*" | head -n 1)"
  if [[ -z "$exe_path" ]]; then
    log "Could not find extracted Godot binary."
    return 1
  fi

  mkdir -p "$INSTALL_DIR"
  cp "$exe_path" "$INSTALL_DIR/godot4"
  chmod +x "$INSTALL_DIR/godot4"

  ensure_bin_dir
  ln -sf "$INSTALL_DIR/godot4" "$BIN_DIR/godot4"
  log "Installed Godot at $INSTALL_DIR/godot4"
}

install_from_github_zip_macos() {
  local url tmp app_path
  url="https://github.com/godotengine/godot-builds/releases/download/${VERSION}/Godot_v${VERSION}_macos.universal.zip"
  tmp="$(mktemp -d)"
  log "Downloading $url"
  curl -L "$url" -o "$tmp/godot.zip"
  unzip -q "$tmp/godot.zip" -d "$tmp"

  app_path="$(find "$tmp" -maxdepth 3 -type d -name "Godot*.app" | head -n 1)"
  if [[ -z "$app_path" ]]; then
    log "Could not find extracted Godot app bundle."
    return 1
  fi

  mkdir -p "$INSTALL_DIR"
  rm -rf "$INSTALL_DIR/Godot.app"
  cp -R "$app_path" "$INSTALL_DIR/Godot.app"

  ensure_bin_dir
  cat > "$BIN_DIR/godot4" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/Godot.app/Contents/MacOS/Godot" "\$@"
EOF
  chmod +x "$BIN_DIR/godot4"
  log "Installed Godot app at $INSTALL_DIR/Godot.app"
}

if command -v godot4 >/dev/null 2>&1; then
  log "godot4 already available: $(command -v godot4)"
  godot4 --version || true
  exit 0
fi

OS="$(uname -s)"
case "$OS" in
  Darwin)
    if command -v brew >/dev/null 2>&1; then
      log "Installing Godot via Homebrew cask."
      brew install --cask godot
      if command -v godot4 >/dev/null 2>&1; then
        log "godot4 is available."
        godot4 --version || true
        exit 0
      fi
      ensure_bin_dir
      if [[ -x "/Applications/Godot.app/Contents/MacOS/Godot" ]]; then
        ln -sf "/Applications/Godot.app/Contents/MacOS/Godot" "$BIN_DIR/godot4"
      fi
      if command -v godot4 >/dev/null 2>&1; then
        log "godot4 is available."
        godot4 --version || true
        exit 0
      fi
    fi

    log "Falling back to direct download install."
    install_from_github_zip_macos
    ;;
  Linux)
    if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
      log "Trying apt-based install (requires sudo)."
      sudo apt-get update
      if sudo apt-get install -y godot4; then
        if command -v godot4 >/dev/null 2>&1; then
          log "godot4 is available."
          godot4 --version || true
          exit 0
        fi
      fi
    fi

    if command -v flatpak >/dev/null 2>&1; then
      log "Trying flatpak install."
      flatpak install -y flathub org.godotengine.Godot || true
      ensure_bin_dir
      cat > "$BIN_DIR/godot4" <<'EOF'
#!/usr/bin/env bash
exec flatpak run org.godotengine.Godot "$@"
EOF
      chmod +x "$BIN_DIR/godot4"
      if command -v godot4 >/dev/null 2>&1; then
        log "godot4 wrapper installed via flatpak."
        exit 0
      fi
    fi

    log "Falling back to direct download install."
    install_from_github_zip_linux
    ;;
  *)
    log "Unsupported OS: $OS"
    exit 1
    ;;
esac

if command -v godot4 >/dev/null 2>&1; then
  log "Installation complete."
  godot4 --version || true
  exit 0
fi

if [[ -x "$BIN_DIR/godot4" ]]; then
  log "Godot installed at $BIN_DIR/godot4, but this path is not on PATH."
  log "Add this to your shell profile:"
  log "  export PATH=\"$BIN_DIR:\$PATH\""
  exit 0
fi

log "Installation did not place a runnable godot4 command."
exit 1

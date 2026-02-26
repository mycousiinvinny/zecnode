#!/bin/bash
set -e
echo "================================"
echo "       ZecNode Installer"
echo "================================"

# Get actual user's home directory (not root's when running with sudo)
if [ -n "$SUDO_USER" ]; then
    ACTUAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
else
    ACTUAL_HOME="$HOME"
fi

# Ensure sudo credentials are cached for the entire install
sudo -v

PROJECT_DIR="$ACTUAL_HOME/zecnode"
GITHUB_RAW="https://raw.githubusercontent.com/mycousiinvinny/zecnode/main"

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Always clear Python cache to avoid stale bytecode issues
rm -rf "$PROJECT_DIR/__pycache__" 2>/dev/null || true

# Smart config handling - detect actual system state
CONFIG_FILE="$ACTUAL_HOME/.zecnode/config.json"
if [ -f "$CONFIG_FILE" ]; then
    # Config exists - check if it matches reality
    if ! command -v docker &> /dev/null; then
        echo "Docker not found but config exists - resetting for fresh install..."
        rm -f "$CONFIG_FILE" 2>/dev/null || true
    fi
else
    # No config - check if this is actually a fresh system or an existing setup
    if command -v docker &> /dev/null; then
        # Docker exists but no config - check for zebra data
        if [ -d "/mnt/zebra-data/zebra-cache" ] && [ "$(ls -A /mnt/zebra-data/zebra-cache 2>/dev/null)" ]; then
            echo "Existing Zebra data found - creating config..."
            mkdir -p "$ACTUAL_HOME/.zecnode"
            cat > "$CONFIG_FILE" << 'CONFIGEOF'
{
  "installed": true,
  "install_phase": "complete",
  "data_path": "/mnt/zebra-data",
  "docker_configured": true,
  "node_started": false,
  "autostart": false,
  "zebra_version": "4.0.0",
  "lightwalletd_enabled": false
}
CONFIGEOF
        fi
    fi
fi

echo "Downloading ZecNode files..."

# Download all Python files
curl -sSL -o "$PROJECT_DIR/main.py" "$GITHUB_RAW/main.py"
curl -sSL -o "$PROJECT_DIR/config.py" "$GITHUB_RAW/config.py"
curl -sSL -o "$PROJECT_DIR/node_manager.py" "$GITHUB_RAW/node_manager.py"
curl -sSL -o "$PROJECT_DIR/installer.py" "$GITHUB_RAW/installer.py"
curl -sSL -o "$PROJECT_DIR/dashboard.py" "$GITHUB_RAW/dashboard.py"

# Download icon
curl -sSL -o "$PROJECT_DIR/zecnode-icon.png" "$GITHUB_RAW/zecnode-icon.png" 2>/dev/null || true

echo "Installing dependencies..."

# Install PyQt5 - try multiple methods
install_pyqt5() {
    # Method 1: apt (most reliable on Ubuntu/Debian)
    if command -v apt &> /dev/null; then
        echo "Installing PyQt5 via apt..."
        sudo apt update -qq
        sudo apt install -y python3-pyqt5 > /dev/null 2>&1 && return 0
    fi
    
    # Method 2: pip with --break-system-packages (Python 3.11+)
    echo "Trying pip install..."
    pip3 install PyQt5 --break-system-packages 2>/dev/null && return 0
    pip install PyQt5 --break-system-packages 2>/dev/null && return 0
    
    # Method 3: pip without flag (older Python)
    pip3 install PyQt5 2>/dev/null && return 0
    pip install PyQt5 2>/dev/null && return 0
    
    return 1
}

if ! python3 -c "import PyQt5" 2>/dev/null; then
    if ! install_pyqt5; then
        echo "ERROR: Failed to install PyQt5. Please run:"
        echo "  sudo apt install python3-pyqt5"
        exit 1
    fi
fi

echo ""
echo "Launching ZecNode..."

# Launch as the actual user, not root (fixes tray icon position and window sizing)
if [ -n "$SUDO_USER" ]; then
    sudo -u "$SUDO_USER" python3 "$PROJECT_DIR/main.py"
else
    python3 main.py
fi

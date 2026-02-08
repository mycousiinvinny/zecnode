#!/bin/bash
set -e
echo "================================"
echo "       ZecNode Installer"
echo "================================"

# Ensure sudo credentials are cached for the entire install
sudo -v

PROJECT_DIR="$HOME/zecnode"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Always clear Python cache to avoid stale bytecode issues
rm -rf "$PROJECT_DIR/__pycache__" 2>/dev/null || true

# Smart config handling - detect actual system state
CONFIG_FILE="$HOME/.zecnode/config.json"
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
        if [ -d "/mnt/zebra-data/zebra-state" ] && [ "$(ls -A /mnt/zebra-data/zebra-state 2>/dev/null)" ]; then
            echo "Existing Zebra data found - creating config..."
            mkdir -p "$HOME/.zecnode"
            cat > "$CONFIG_FILE" << 'CONFIGEOF'
{
  "installed": true,
  "install_phase": "complete",
  "data_path": "/mnt/zebra-data",
  "docker_configured": true,
  "node_started": false,
  "autostart": false,
  "zebra_version": "3.1.0",
  "lightwalletd_enabled": false
}
CONFIGEOF
        fi
    fi
fi

# Download ZecNode icon
echo "Downloading icon..."
curl -sSL -o "$PROJECT_DIR/zecnode-icon.png" "https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/zecnode-icon.png" 2>/dev/null || true

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

echo "Setting up ZecNode..."

cat > main.py << 'ENDOFFILE'
#!/usr/bin/env python3
"""
ZecNode - One-Click Zcash Node Installer
Main entry point with professional styling
"""

import sys
import os
import subprocess
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from config import Config
from installer import InstallerWizard
from dashboard import DashboardWindow


# Professional dark theme with Zcash branding
STYLESHEET = """
/* Global */
QWidget {
    background-color: #0f0f14;
    color: #e8e8e8;
    font-family: 'Segoe UI', 'SF Pro Display', 'Ubuntu', sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #0f0f14;
}

/* Tooltips */
QToolTip {
    background-color: #1a1a24;
    color: #ffffff;
    border: 2px solid #4ade80;
    padding: 12px;
    border-radius: 8px;
    font-size: 13px;
}

/* Labels */
QLabel {
    color: #e8e8e8;
    background: transparent;
}

QLabel#title {
    font-size: 28px;
    font-weight: bold;
    color: #f4b728;
}

QLabel#subtitle {
    font-size: 14px;
    color: #888;
}

QLabel#success {
    color: #4ade80;
}

QLabel#warning {
    color: #f59e0b;
}

QLabel#error {
    color: #ef4444;
}

/* Buttons */
QPushButton {
    background-color: #f4b728;
    color: #0f0f14;
    border: none;
    padding: 12px 28px;
    font-weight: 600;
    font-size: 13px;
    border-radius: 8px;
    min-width: 100px;
}

QPushButton:hover {
    background-color: #ffc942;
}

QPushButton:pressed {
    background-color: #d99e1c;
}

QPushButton:disabled {
    background-color: #2a2a35;
    color: #555;
}

QPushButton#secondary {
    background-color: #1e1e28;
    color: #e8e8e8;
    border: 1px solid #333;
}

QPushButton#secondary:hover {
    background-color: #28283a;
    border-color: #444;
}

QPushButton#danger {
    background-color: #dc2626;
    color: white;
}

QPushButton#danger:hover {
    background-color: #ef4444;
}

/* Progress Bar */
QProgressBar {
    border: none;
    border-radius: 6px;
    background-color: #1e1e28;
    height: 12px;
    text-align: center;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #f4b728, stop:1 #ffc942);
    border-radius: 6px;
}

/* Combo Box */
QComboBox {
    background-color: #1e1e28;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 10px 15px;
    min-width: 200px;
    color: #e8e8e8;
}

QComboBox:hover {
    border-color: #f4b728;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox QAbstractItemView {
    background-color: #1e1e28;
    border: 1px solid #333;
    selection-background-color: #f4b728;
    selection-color: #0f0f14;
}

/* Line Edit */
QLineEdit {
    background-color: #1e1e28;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 10px 15px;
    color: #e8e8e8;
}

QLineEdit:focus {
    border-color: #f4b728;
}

/* Text Edit (Logs) */
QTextEdit {
    background-color: #0a0a0f;
    border: 1px solid #222;
    border-radius: 8px;
    padding: 10px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 11px;
    color: #4ade80;
}

/* Scroll Bar */
QScrollBar:vertical {
    background-color: #0f0f14;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: #333;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #444;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* Menu */
QMenu {
    background-color: #16161d;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 5px;
}

QMenu::item {
    padding: 8px 20px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #f4b728;
    color: #0f0f14;
}
"""


def main():
    # Kill any existing ZecNode instances (but not ourselves)
    my_pid = os.getpid()
    subprocess.run(
        ["bash", "-c", f"pgrep -f 'python.*main.py' | grep -v {my_pid} | xargs -r kill -9 2>/dev/null || true"],
        capture_output=True
    )
    
    # Small delay to let old instances fully die
    import time
    time.sleep(0.3)
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("ZecNode")
    app.setOrganizationName("ZecNode")
    app.setDesktopFileName("zecnode")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    
    config = Config()
    
    # Check if already installed
    if config.is_installed():
        window = DashboardWindow(config)
    else:
        # Check if zebra container exists OR data directories exist
        import shutil
        
        already_setup = False
        
        # Check 1: Zebra data directories exist on SSD AND have actual data
        data_path = "/mnt/zebra-data"
        cache_path = f"{data_path}/zebra-cache"
        state_path = f"{data_path}/zebra-state"
        
        # Check if directories exist and are not empty
        def has_data(path):
            if not os.path.exists(path):
                return False
            try:
                # Check if directory has more than just . and ..
                contents = os.listdir(path)
                return len(contents) > 0
            except:
                return False
        
        if has_data(cache_path) or has_data(state_path):
            # Data exists! Mark as installed and go to dashboard
            config.set("data_path", data_path)
            config.set("install_phase", Config.PHASE_COMPLETE)
            config.set("installed", True)
            config.set("docker_configured", True)
            config.save()
            already_setup = True
        
        # Check 2: Zebra container exists
        if not already_setup and shutil.which("docker"):
            try:
                result = subprocess.run(
                    ["docker", "ps", "-a", "--filter", "name=zebra", "--format", "{{.Names}}"],
                    capture_output=True, text=True, timeout=10
                )
                if "zebra" in result.stdout:
                    # Node exists! Find where it's mounted
                    mount_result = subprocess.run(
                        ["docker", "inspect", "-f", "{{range .Mounts}}{{.Source}}{{end}}", "zebra"],
                        capture_output=True, text=True, timeout=10
                    )
                    data_path = mount_result.stdout.strip() or "/mnt/zebra-data"
                    
                    # Create config and go straight to dashboard
                    config.set_data_path(data_path)
                    config.mark_installed()
                    already_setup = True
            except:
                pass
        
        if already_setup:
            window = DashboardWindow(config)
        else:
            window = InstallerWizard(config)
    
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

ENDOFFILE

cat > config.py << 'ENDOFFILE'
"""
ZecNode Configuration Management
Handles persistent settings and installation state
Supports resuming installation after reboot
"""

import json
from pathlib import Path
from typing import Optional

VERSION = "1.0.5"


class Config:
    """Manages ZecNode configuration and state"""
    
    CONFIG_DIR = Path.home() / ".zecnode"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    
    # Installation phases
    PHASE_NOT_STARTED = "not_started"
    PHASE_SYSTEM_UPDATED = "system_updated"        # After apt update/upgrade
    PHASE_DOCKER_INSTALLED = "docker_installed"    # After Docker install, needs reboot
    PHASE_REBOOT_DONE = "reboot_done"              # After reboot, ready for drive setup
    PHASE_DRIVE_READY = "drive_ready"              # After format + mount
    PHASE_DOCKER_ON_SSD = "docker_on_ssd"          # After Docker configured for SSD
    PHASE_COMPLETE = "complete"                     # Node running
    
    DEFAULTS = {
        "installed": False,
        "install_phase": PHASE_NOT_STARTED,
        "selected_drive": "",          # e.g., /dev/sda
        "selected_partition": "",      # e.g., /dev/sda1
        "data_path": "/mnt/zebra-data",
        "needs_reboot": False,
        "docker_configured": False,
        "node_started": False,
        "autostart": False,
        "zebra_version": "latest",
        "lightwalletd_enabled": False,
    }
    
    def __init__(self):
        self._ensure_config_dir()
        self._config = self._load_config()
    
    def _ensure_config_dir(self):
        """Create config directory if it doesn't exist"""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self) -> dict:
        """Load config from file or return defaults"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    saved = json.load(f)
                    # Merge with defaults for any new keys
                    return {**self.DEFAULTS, **saved}
            except (json.JSONDecodeError, IOError):
                return self.DEFAULTS.copy()
        return self.DEFAULTS.copy()
    
    def save(self):
        """Save current config to file"""
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(self._config, f, indent=2)
    
    def get(self, key: str, default=None):
        """Get a config value"""
        return self._config.get(key, default)
    
    def set(self, key: str, value):
        """Set a config value and save"""
        self._config[key] = value
        self.save()
    
    # ==================== INSTALLATION STATE ====================
    
    def get_phase(self) -> str:
        """Get current installation phase"""
        return self._config.get("install_phase", self.PHASE_NOT_STARTED)
    
    def set_phase(self, phase: str):
        """Set installation phase"""
        self.set("install_phase", phase)
    
    def is_installed(self) -> bool:
        """Check if ZecNode has been fully installed"""
        return self._config.get("installed", False)
    
    def mark_installed(self):
        """Mark installation as complete"""
        self.set("installed", True)
        self.set_phase(self.PHASE_COMPLETE)
    
    def needs_reboot(self) -> bool:
        """Check if a reboot is pending"""
        return self._config.get("needs_reboot", False)
    
    def set_needs_reboot(self, needs: bool):
        """Set reboot pending flag"""
        self.set("needs_reboot", needs)
    
    def get_selected_drive(self) -> Optional[str]:
        """Get the selected drive device path"""
        drive = self._config.get("selected_drive", "")
        return drive if drive else None
    
    def set_selected_drive(self, device: str, partition: str):
        """Save selected drive info for resume after reboot"""
        self._config["selected_drive"] = device
        self._config["selected_partition"] = partition
        self.save()
    
    def get_data_path(self) -> Path:
        """Get the configured data storage path"""
        return Path(self._config.get("data_path", "/mnt/zebra-data"))
    
    def set_data_path(self, path: str):
        """Set the data storage path"""
        self.set("data_path", str(path))
    
    def reset(self):
        """Reset config to defaults (for uninstall/reinstall)"""
        self._config = self.DEFAULTS.copy()
        self.save()
    
    def reset_installation(self):
        """Reset just the installation state (keep other settings)"""
        self.set("installed", False)
        self.set("install_phase", self.PHASE_NOT_STARTED)
        self.set("needs_reboot", False)

ENDOFFILE

cat > node_manager.py << 'ENDOFFILE'
"""
ZecNode Node Manager
Handles all Docker and Zebra node operations
"""

import subprocess
import re
import shutil
import os
import time
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DriveInfo:
    """Information about a detected drive"""
    device: str          # e.g., /dev/sdb
    size_bytes: int
    size_human: str      # e.g., "1.0 TB"
    model: str
    is_removable: bool
    mount_point: Optional[str]
    partitions: List[str]


@dataclass
class NodeStatus:
    """Current status of the Zcash node"""
    running: bool
    sync_percent: float
    current_height: int
    target_height: int
    peer_count: int
    uptime: str
    version: str


class NodeManager:
    """Manages the Zcash node (Zebra) via Docker"""
    
    CONTAINER_NAME = "zebra"
    IMAGE_NAME = "zfnd/zebra:3.1.0"
    MOUNT_PATH = "/mnt/zebra-data"
    
    # Lightwalletd
    LWD_CONTAINER_NAME = "lightwalletd"
    LWD_IMAGE_NAME = "electriccoinco/lightwalletd:latest"
    LWD_PORT = 9067
    
    # Directory structure on SSD
    # Step 6: sudo mkdir -p /mnt/zebra-data/{docker,containerd}
    DOCKER_DIR = "docker"
    CONTAINERD_DIR = "containerd"
    # Step 7: mkdir -p /mnt/zebra-data/zebra-{cache,state}
    ZEBRA_CACHE_DIR = "zebra-cache"
    ZEBRA_STATE_DIR = "zebra-state"
    
    # Zcash mainnet approximate current height
    ESTIMATED_TARGET_HEIGHT = 3_200_000
    
    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or Path(self.MOUNT_PATH)
    
    # ==================== SYSTEM CHECKS ====================
    
    def check_curl_installed(self) -> bool:
        """Check if curl is installed"""
        return shutil.which("curl") is not None
    
    def check_docker_installed(self) -> bool:
        """Check if Docker is installed"""
        return shutil.which("docker") is not None
    
    def check_docker_running(self) -> bool:
        """Check if Docker daemon is running"""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def check_user_in_docker_group(self) -> bool:
        """Check if current user is in docker group"""
        try:
            result = subprocess.run(
                ["groups"],
                capture_output=True,
                text=True
            )
            return "docker" in result.stdout
        except:
            return False
    
    def get_docker_root_dir(self) -> Optional[str]:
        """
        Get Docker's root directory.
        docker info | grep "Docker Root Dir"
        Must show: /mnt/zebra-data/docker
        """
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.DockerRootDir}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None
    
    def verify_docker_on_ssd(self) -> bool:
        """
        CRITICAL: Verify Docker is using the SSD, not the SD card.
        docker info | grep "Docker Root Dir"
        Must show: /mnt/zebra-data/docker
        If not, redo Step 6!
        """
        root_dir = self.get_docker_root_dir()
        expected = f"{self.MOUNT_PATH}/{self.DOCKER_DIR}"
        if root_dir:
            return root_dir == expected
        return False
    
    # ==================== DRIVE DETECTION ====================
    
    def detect_external_drives(self) -> List[DriveInfo]:
        """
        Detect external/removable drives suitable for Zcash data.
        lsblk (find SSD, usually sda)
        SAFETY: Excludes system drives and internal drives.
        """
        drives = []
        
        try:
            # Use lsblk to get drive info
            result = subprocess.run(
                ["lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,RM,TYPE,MOUNTPOINT"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return drives
            
            import json
            data = json.loads(result.stdout)
            
            for device in data.get("blockdevices", []):
                # Only consider whole disks, not partitions
                if device.get("type") != "disk":
                    continue
                
                name = device.get("name", "")
                size = int(device.get("size", 0))
                model = device.get("model", "").strip() if device.get("model") else "Unknown"
                removable = device.get("rm", False)
                
                # Get partitions and mount points
                partitions = []
                children = device.get("children", [])
                mount_point = None
                
                for child in children:
                    part_name = child.get("name", "")
                    partitions.append(f"/dev/{part_name}")
                    if child.get("mountpoint"):
                        mount_point = child.get("mountpoint")
                
                # SAFETY CHECKS - Skip system drives
                device_path = f"/dev/{name}"
                
                # Skip if it's the root filesystem or boot device
                if self._is_system_drive(device_path, mount_point, children):
                    continue
                
                # Skip very small drives (< 100GB) - not enough for blockchain
                if size < 100 * 1024 * 1024 * 1024:
                    continue
                
                # Skip if not removable AND no model (likely virtual/system)
                if not removable and model == "Unknown":
                    continue
                
                drives.append(DriveInfo(
                    device=device_path,
                    size_bytes=size,
                    size_human=self._format_size(size),
                    model=model,
                    is_removable=removable,
                    mount_point=mount_point,
                    partitions=partitions
                ))
            
        except Exception as e:
            print(f"Error detecting drives: {e}")
        
        return drives
    
    def _is_system_drive(self, device: str, mount_point: Optional[str], 
                         children: List[dict]) -> bool:
        """Check if a drive is a system drive (should not be formatted)"""
        
        # Critical mount points that indicate system drive
        critical_mounts = ['/', '/boot', '/home', '/var', '/usr', '/etc', '/boot/firmware']
        
        if mount_point in critical_mounts:
            return True
        
        # Check children (partitions) for critical mount points
        for child in children:
            child_mount = child.get("mountpoint", "")
            if child_mount in critical_mounts:
                return True
            for critical in critical_mounts:
                if child_mount and child_mount.startswith(critical + "/"):
                    return True
        
        # Check if it's the boot device (kernel command line)
        try:
            with open("/proc/cmdline", "r") as f:
                cmdline = f.read()
                device_name = device.replace("/dev/", "")
                if device_name in cmdline:
                    return True
                # SD card on Pi
                if "mmcblk" in device and "mmcblk" in cmdline:
                    return True
        except:
            pass
        
        return False
    
    def _format_size(self, size_bytes: int) -> str:
        """Format byte size to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
    
    # ==================== STEP 2: SYSTEM UPDATE ====================
    
    def update_system(self, progress_callback=None) -> Tuple[bool, str]:
        """
        Step:
            sudo apt update
            sudo apt upgrade -y
        Note: Reboot happens separately after this + Docker install
        """
        if progress_callback:
            progress_callback("Disabling sleep mode...")
        
        # Disable sleep/suspend so node stays online 24/7
        self._disable_sleep_mode()
        
        if progress_callback:
            progress_callback("Updating package lists...")
        
        try:
            # apt update
            result = subprocess.run(
                ["sudo", "apt", "update", "--fix-missing"],
                capture_output=True,
                text=True,
                timeout=300  # 5 min timeout
            )
            
            if result.returncode != 0:
                return False, f"apt update failed: {result.stderr}"
            
            if progress_callback:
                progress_callback("Upgrading system packages (this may take a while)...")
            
            # apt upgrade -y with fix-missing
            result = subprocess.run(
                ["sudo", "apt", "upgrade", "-y", "--fix-missing"],
                capture_output=True,
                text=True,
                timeout=1800  # 30 min timeout for upgrades
            )
            
            # If upgrade fails, try just continuing - not critical
            if result.returncode != 0:
                # Try apt-get instead which handles errors better
                result = subprocess.run(
                    ["sudo", "apt-get", "upgrade", "-y", "--fix-missing", "-o", "Dpkg::Options::=--force-confdef"],
                    capture_output=True,
                    text=True,
                    timeout=1800
                )
                if result.returncode != 0:
                    # Still continue - upgrade isn't critical for Docker install
                    pass
            
            return True, "System updated"
            
        except subprocess.TimeoutExpired:
            return False, "System update timed out"
        except Exception as e:
            return False, f"System update error: {str(e)}"
    
    def _disable_sleep_mode(self):
        """Disable sleep/suspend/hibernate so node runs 24/7"""
        try:
            # Method 1: Disable via systemctl (works on most Linux)
            sleep_targets = [
                "sleep.target",
                "suspend.target",
                "hibernate.target",
                "hybrid-sleep.target"
            ]
            for target in sleep_targets:
                subprocess.run(
                    ["sudo", "systemctl", "mask", target],
                    capture_output=True,
                    timeout=30
                )
            
            # Method 2: Create a script that runs on login to disable sleep
            # This is more reliable than trying to run gsettings as another user
            actual_user = os.environ.get('SUDO_USER', os.environ.get('USER', ''))
            if actual_user and actual_user != 'root':
                home_dir = f"/home/{actual_user}"
                autostart_dir = f"{home_dir}/.config/autostart"
                applications_dir = f"{home_dir}/.local/share/applications"
                
                # Create directories if needed
                subprocess.run(["sudo", "mkdir", "-p", autostart_dir], capture_output=True, timeout=10)
                subprocess.run(["sudo", "mkdir", "-p", applications_dir], capture_output=True, timeout=10)
                
                # Create a desktop entry that disables sleep on login
                desktop_entry = """[Desktop Entry]
Type=Application
Name=Disable Sleep for ZecNode
Exec=bash -c "gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'; gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing'; gsettings set org.gnome.desktop.session idle-delay 0"
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
"""
                desktop_file = f"{autostart_dir}/zecnode-nosleep.desktop"
                subprocess.run(
                    ["sudo", "bash", "-c", f"cat > {desktop_file} << 'EOF'\n{desktop_entry}EOF"],
                    capture_output=True,
                    timeout=10
                )
                subprocess.run(["sudo", "chown", f"{actual_user}:{actual_user}", desktop_file], capture_output=True, timeout=10)
                subprocess.run(["sudo", "chown", "-R", f"{actual_user}:{actual_user}", autostart_dir], capture_output=True, timeout=10)
                
                # Create application menu entry for ZecNode
                app_entry = f"""[Desktop Entry]
Type=Application
Name=ZecNode
Comment=Zcash Node Dashboard
Exec=bash -c "cd {home_dir}/zecnode && python3 main.py"
Icon={home_dir}/zecnode/zecnode-icon.png
Terminal=false
Categories=Utility;Network;
"""
                app_file = f"{applications_dir}/zecnode.desktop"
                subprocess.run(
                    ["sudo", "bash", "-c", f"cat > {app_file} << 'EOF'\n{app_entry}EOF"],
                    capture_output=True,
                    timeout=10
                )
                subprocess.run(["sudo", "chown", f"{actual_user}:{actual_user}", app_file], capture_output=True, timeout=10)
                subprocess.run(["sudo", "chmod", "+x", app_file], capture_output=True, timeout=10)
                
                # Also try running gsettings now via su (may work if display is available)
                gsettings_script = """
export DISPLAY=:0
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing' 2>/dev/null || true  
gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || true
"""
                subprocess.run(
                    ["sudo", "su", "-", actual_user, "-c", gsettings_script],
                    capture_output=True,
                    timeout=15
                )
            
            # Method 3: Raspberry Pi specific - disable screen blanking
            try:
                autostart_path = Path("/etc/xdg/lxsession/LXDE-pi/autostart")
                if autostart_path.exists():
                    content = autostart_path.read_text()
                    if "xset s off" not in content:
                        subprocess.run(
                            ["sudo", "bash", "-c", f'echo "@xset s off" >> {autostart_path}'],
                            capture_output=True,
                            timeout=10
                        )
                        subprocess.run(
                            ["sudo", "bash", "-c", f'echo "@xset -dpms" >> {autostart_path}'],
                            capture_output=True,
                            timeout=10
                        )
            except Exception:
                pass
                
        except Exception:
            pass  # Non-critical - continue even if this fails
    
    # ==================== STEP 3: INSTALL DOCKER ====================
    
    def install_curl(self, progress_callback=None) -> Tuple[bool, str]:
        """Install curl (needed for Docker install script)"""
        if progress_callback:
            progress_callback("Installing curl...")
        
        try:
            result = subprocess.run(
                ["sudo", "apt", "install", "-y", "curl"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                return False, f"Failed to install curl: {result.stderr}"
            
            return True, "curl installed"
            
        except subprocess.TimeoutExpired:
            return False, "curl installation timed out"
        except Exception as e:
            return False, f"curl installation error: {str(e)}"
    
    def install_docker(self, progress_callback=None) -> Tuple[bool, str]:
        """
        Step:
            sudo apt install curl -y
            curl -fsSL https://get.docker.com -o get-docker.sh
            sudo sh get-docker.sh
            sudo usermod -aG docker $USER
            sudo reboot (done separately)
        """
        # First ensure curl is installed
        if not self.check_curl_installed():
            success, msg = self.install_curl(progress_callback)
            if not success:
                return False, msg
        
        if progress_callback:
            progress_callback("Downloading Docker installer...")
        
        try:
            # Download Docker install script
            result = subprocess.run(
                ["curl", "-fsSL", "https://get.docker.com", "-o", "/tmp/get-docker.sh"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return False, f"Failed to download Docker script: {result.stderr}"
            
            if progress_callback:
                progress_callback("Installing Docker (this takes a few minutes)...")
            
            # Run Docker install script
            result = subprocess.run(
                ["sudo", "sh", "/tmp/get-docker.sh"],
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode != 0:
                return False, f"Docker installation failed: {result.stderr}"
            
            if progress_callback:
                progress_callback("Adding user to docker group...")
            
            # Add current user to docker group
            user = os.environ.get("USER", "")
            if user:
                result = subprocess.run(
                    ["sudo", "usermod", "-aG", "docker", user],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    return False, f"Failed to add user to docker group: {result.stderr}"
            
            # Clean up
            try:
                os.remove("/tmp/get-docker.sh")
            except:
                pass
            
            return True, "Docker installed (reboot required)"
            
        except subprocess.TimeoutExpired:
            return False, "Docker installation timed out"
        except Exception as e:
            return False, f"Docker installation error: {str(e)}"
    
    # ==================== STEP 4: FORMAT SSD ====================
    
    def _verify_drive_present(self, device: str) -> bool:
        """Check if drive is still connected"""
        return os.path.exists(device)
    
    def format_drive(self, device: str, progress_callback=None) -> Tuple[bool, str]:
        """
        Step:
            lsblk (find SSD, usually sda2)
            sudo umount /dev/sda2
            sudo mkfs.ext4 /dev/sda2
            sudo mkdir -p /mnt/zebra-data
        
        IMPORTANT: Unmount BEFORE format!
        
        Returns: (success, partition_path or error_message)
        """
        # Refresh sudo credentials first (in case they timed out)
        subprocess.run(["sudo", "-v"], timeout=5)
        
        # Verify drive exists before starting
        if not self._verify_drive_present(device):
            return False, f"Drive {device} not found. Is the SSD connected?"
        
        # Check for required tools
        if not shutil.which("parted"):
            if progress_callback:
                progress_callback("Installing required tools...")
            try:
                result = subprocess.run(
                    ["sudo", "apt", "install", "-y", "parted"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode != 0:
                    return False, "Failed to install 'parted'. Please run: sudo apt install parted"
            except Exception as e:
                return False, f"Failed to install 'parted': {str(e)}"
        
        if progress_callback:
            progress_callback(f"Unmounting {device}...")
        
        try:
            # Get list of partitions for this device from lsblk
            result = subprocess.run(
                ["lsblk", "-ln", "-o", "NAME", device],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Unmount each partition individually (skip the device itself)
            device_name = device.replace("/dev/", "")
            for line in result.stdout.strip().split('\n'):
                part_name = line.strip()
                if part_name and part_name != device_name:
                    subprocess.run(
                        ["sudo", "umount", "-l", f"/dev/{part_name}"],
                        capture_output=True,
                        timeout=5
                    )
            
            time.sleep(1)
            
            # Verify drive still present after unmount
            if not self._verify_drive_present(device):
                return False, "Drive disconnected during operation. Please reconnect and try again."
            
            if progress_callback:
                progress_callback(f"Creating partition table on {device}...")
            
            # Create GPT partition table
            result = subprocess.run(
                ["sudo", "parted", "-s", device, "mklabel", "gpt"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Unknown error"
                if "busy" in error_msg.lower():
                    return False, f"Drive is busy. Please close any applications using {device} and try again."
                # Check if drive was disconnected
                if not self._verify_drive_present(device):
                    return False, "Drive disconnected during formatting. Please reconnect and try again."
                return False, f"Failed to create partition table: {error_msg}"
            
            # Create single partition using 100% of disk
            result = subprocess.run(
                ["sudo", "parted", "-s", device, "mkpart", "primary", "ext4", "0%", "100%"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                if not self._verify_drive_present(device):
                    return False, "Drive disconnected during formatting. Please reconnect and try again."
                return False, f"Failed to create partition: {result.stderr}"
            
            # Determine partition name
            # /dev/sda -> /dev/sda1
            # /dev/nvme0n1 -> /dev/nvme0n1p1
            if "nvme" in device:
                partition = f"{device}p1"
            else:
                partition = f"{device}1"
            
            # Wait for partition to appear
            if progress_callback:
                progress_callback("Waiting for partition...")
            
            for _ in range(10):  # Wait up to 10 seconds
                time.sleep(1)
                if os.path.exists(partition):
                    break
                # Check if drive was disconnected while waiting
                if not self._verify_drive_present(device):
                    return False, "Drive disconnected. Please reconnect and try again."
            
            if not os.path.exists(partition):
                return False, f"Partition {partition} not found after creation. Please try again."
            
            if progress_callback:
                progress_callback(f"Formatting {partition} as ext4...")
            
            # Format as ext4)
            result = subprocess.run(
                ["sudo", "mkfs.ext4", "-F", partition],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                if not self._verify_drive_present(device):
                    return False, "Drive disconnected during formatting. Please reconnect and try again."
                return False, f"Formatting failed: {result.stderr}"
            
            # Final verification
            if not self._verify_drive_present(device):
                return False, "Drive disconnected after formatting. Please reconnect and try again."
            
            # Create mount point)
            subprocess.run(
                ["sudo", "mkdir", "-p", self.MOUNT_PATH],
                capture_output=True
            )
            
            return True, partition
            
        except subprocess.TimeoutExpired:
            return False, "Formatting timed out. The drive may be slow or unresponsive."
        except Exception as e:
            return False, f"Formatting error: {str(e)}"
    
    # ==================== STEP 5: MOUNT SSD ====================
    
    def mount_drive(self, partition: str, progress_callback=None) -> Tuple[bool, str]:
        """
        Step:
            sudo blkid /dev/sda2 (get UUID)
            sudo nano /etc/fstab
            Add: UUID=YOUR-UUID /mnt/zebra-data ext4 defaults 0 2
            sudo systemctl daemon-reload
            sudo mount -a
            sudo chown -R $USER:$USER /mnt/zebra-data
        """
        if progress_callback:
            progress_callback("Preparing mount...")
        
        try:
            # First, unmount if already mounted (from previous install)
            subprocess.run(
                ["sudo", "umount", self.MOUNT_PATH],
                capture_output=True
            )
            # Also try old mount path
            subprocess.run(
                ["sudo", "umount", "/mnt/zebra-data"],
                capture_output=True
            )
            
            # CRITICAL: Remove old fstab entries for our mount points
            # This fixes issues when reinstalling with a reformatted drive (new UUID)
            if progress_callback:
                progress_callback("Cleaning up old mount entries...")
            
            # Remove any existing entries for /mnt/zcash or /mnt/zebra-data
            subprocess.run(
                ["sudo", "bash", "-c", f"sed -i '\\|{self.MOUNT_PATH}|d' /etc/fstab"],
                capture_output=True
            )
            subprocess.run(
                ["sudo", "bash", "-c", "sed -i '\\|/mnt/zebra-data|d' /etc/fstab"],
                capture_output=True
            )
            
            if progress_callback:
                progress_callback("Getting partition UUID...")
            
            # Get UUID)
            result = subprocess.run(
                ["sudo", "blkid", "-s", "UUID", "-o", "value", partition],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                return False, "Could not get partition UUID. Is the drive connected?"
            
            uuid = result.stdout.strip()
            
            if progress_callback:
                progress_callback("Adding to /etc/fstab...")
            
            # Create mount point
            subprocess.run(
                ["sudo", "mkdir", "-p", self.MOUNT_PATH],
                capture_output=True
            )
            
            # Add new fstab entry with current UUID
            fstab_entry = f"UUID={uuid} {self.MOUNT_PATH} ext4 defaults,nofail 0 2"
            subprocess.run(
                ["sudo", "bash", "-c", f'echo "{fstab_entry}" >> /etc/fstab'],
                capture_output=True
            )
            
            if progress_callback:
                progress_callback("Mounting drive...")
            
            # Reload and mount)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
            
            result = subprocess.run(
                ["sudo", "mount", "-a"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return False, f"Mount failed: {result.stderr}"
            
            if progress_callback:
                progress_callback("Setting permissions...")
            
            # Set ownership)
            user = os.environ.get("USER", "root")
            subprocess.run(
                ["sudo", "chown", "-R", f"{user}:{user}", self.MOUNT_PATH],
                capture_output=True
            )
            
            # Verify mount worked
            if not os.path.ismount(self.MOUNT_PATH):
                return False, f"{self.MOUNT_PATH} is not mounted. Please check if the drive is connected."
            
            return True, self.MOUNT_PATH
            
        except Exception as e:
            return False, f"Mount error: {str(e)}"
    
    # ==================== STEP 6: CONFIGURE DOCKER FOR SSD ====================
    
    def configure_docker_for_ssd(self, progress_callback=None) -> Tuple[bool, str]:
        """
        CRITICAL: - Docker must store data on SSD!
        
            sudo systemctl stop docker containerd
            sudo rm -rf /var/lib/docker /var/lib/containerd
            sudo mkdir -p /mnt/zebra-data/{docker,containerd}
            sudo ln -sf /mnt/zebra-data/docker /var/lib/docker
            sudo ln -sf /mnt/zebra-data/containerd /var/lib/containerd
            sudo systemctl start containerd docker
            
        VERIFY: docker info | grep "Docker Root Dir"
        Must show: /mnt/zebra-data/docker
        If not, redo Step 6!
        """
        if progress_callback:
            progress_callback("Stopping Docker services...")
        
        try:
            # Stop Docker services
            subprocess.run(
                ["sudo", "systemctl", "stop", "docker"],
                capture_output=True,
                timeout=30
            )
            subprocess.run(
                ["sudo", "systemctl", "stop", "containerd"],
                capture_output=True,
                timeout=30
            )
            
            time.sleep(2)
            
            if progress_callback:
                progress_callback("Removing old Docker data from SD card...")
            
            # Remove existing Docker directories from SD card
            # sudo rm -rf /var/lib/docker /var/lib/containerd
            subprocess.run(
                ["sudo", "rm", "-rf", "/var/lib/docker"],
                capture_output=True
            )
            subprocess.run(
                ["sudo", "rm", "-rf", "/var/lib/containerd"],
                capture_output=True
            )
            
            if progress_callback:
                progress_callback("Creating Docker directories on SSD...")
            
            # Create directories on SSD
            # sudo mkdir -p /mnt/zebra-data/{docker,containerd}
            docker_path = f"{self.MOUNT_PATH}/{self.DOCKER_DIR}"
            containerd_path = f"{self.MOUNT_PATH}/{self.CONTAINERD_DIR}"
            
            subprocess.run(
                ["sudo", "mkdir", "-p", docker_path],
                capture_output=True
            )
            subprocess.run(
                ["sudo", "mkdir", "-p", containerd_path],
                capture_output=True
            )
            
            if progress_callback:
                progress_callback("Creating symlinks...")
            
            # Create symlinks from /var/lib to SSD
            # sudo ln -sf /mnt/zebra-data/docker /var/lib/docker
            result = subprocess.run(
                ["sudo", "ln", "-sf", docker_path, "/var/lib/docker"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return False, f"Failed to create docker symlink: {result.stderr}"
            
            result = subprocess.run(
                ["sudo", "ln", "-sf", containerd_path, "/var/lib/containerd"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return False, f"Failed to create containerd symlink: {result.stderr}"
            
            if progress_callback:
                progress_callback("Starting Docker services...")
            
            # Start services
            subprocess.run(
                ["sudo", "systemctl", "start", "containerd"],
                capture_output=True
            )
            time.sleep(2)
            
            subprocess.run(
                ["sudo", "systemctl", "start", "docker"],
                capture_output=True
            )
            time.sleep(3)
            
            # VERIFY: Docker Root Dir must be on SSD
            if progress_callback:
                progress_callback("Verifying Docker is using SSD...")
            
            if not self.verify_docker_on_ssd():
                root_dir = self.get_docker_root_dir()
                return False, f"CRITICAL: Docker not using SSD! Root dir: {root_dir}. Expected: {docker_path}"
            
            return True, "Docker configured for SSD"
            
        except subprocess.TimeoutExpired:
            return False, "Docker configuration timed out"
        except Exception as e:
            return False, f"Docker configuration error: {str(e)}"
    
    # ==================== STEP 7 & 8: ZEBRA SETUP ====================
    
    def pull_zebra_image(self, progress_callback=None) -> Tuple[bool, str]:
        """
        Step:
            docker pull zfnd/zebra:3.1.0
        """
        if progress_callback:
            progress_callback("Downloading Zebra image (this may take a while)...")
        
        try:
            result = subprocess.run(
                ["docker", "pull", self.IMAGE_NAME],
                capture_output=True,
                text=True,
                timeout=900  # 15 minute timeout
            )
            
            if result.returncode != 0:
                return False, f"Failed to pull image: {result.stderr}"
            
            return True, "Zebra image downloaded"
            
        except subprocess.TimeoutExpired:
            return False, "Image download timed out"
        except Exception as e:
            return False, f"Image download error: {str(e)}"
    
    def create_zebra_directories(self, progress_callback=None) -> Tuple[bool, str]:
        """
        Part of Step:
            mkdir -p /mnt/zebra-data/zebra-{cache,state}
        """
        if progress_callback:
            progress_callback("Creating Zebra directories...")
        
        try:
            cache_path = f"{self.MOUNT_PATH}/{self.ZEBRA_CACHE_DIR}"
            state_path = f"{self.MOUNT_PATH}/{self.ZEBRA_STATE_DIR}"
            
            # Create directories
            os.makedirs(cache_path, exist_ok=True)
            os.makedirs(state_path, exist_ok=True)
            
            # Set ownership
            user = os.environ.get("USER", "root")
            subprocess.run(
                ["sudo", "chown", "-R", f"{user}:{user}", cache_path],
                capture_output=True
            )
            subprocess.run(
                ["sudo", "chown", "-R", f"{user}:{user}", state_path],
                capture_output=True
            )
            
            return True, "Zebra directories created"
            
        except Exception as e:
            return False, f"Failed to create directories: {str(e)}"
    
    def start_node(self, progress_callback=None) -> Tuple[bool, str]:
        """
        Start the Zebra node.
        First tries to start existing container, then creates new if needed.
        """
        if progress_callback:
            progress_callback("Starting Zcash node...")
        
        # CRITICAL: Verify SSD is mounted before starting
        # This prevents writing data to the SD card if SSD is disconnected
        if not os.path.ismount(self.MOUNT_PATH):
            return False, f"SSD not mounted at {self.MOUNT_PATH}. Please reconnect the SSD and try again."
        
        # Verify the data directories exist on the SSD
        cache_path = f"{self.MOUNT_PATH}/{self.ZEBRA_CACHE_DIR}"
        state_path = f"{self.MOUNT_PATH}/{self.ZEBRA_STATE_DIR}"
        
        if not os.path.exists(cache_path) or not os.path.exists(state_path):
            return False, "Zebra data directories not found on SSD. Please run the installer again."
        
        try:
            # First, try to start existing container
            result = subprocess.run(
                ["docker", "start", self.CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True, "Node started"
            
            # Container doesn't exist, create it
            # Remove any failed container with same name
            subprocess.run(
                ["docker", "rm", "-f", self.CONTAINER_NAME],
                capture_output=True
            )
            
            # Ensure zecnode network exists
            subprocess.run(
                ["docker", "network", "create", "zecnode"],
                capture_output=True
            )
            
            # Start container with volume mounts and RPC enabled
            # Environment variables enable RPC for lightwalletd support
            result = subprocess.run([
                "docker", "run", "-d",
                "--name", self.CONTAINER_NAME,
                "--network", "zecnode",
                "-v", f"{cache_path}:/var/cache/zebrad-cache",
                "-v", f"{state_path}:/var/lib/zebrad",
                "-p", "8233:8233",
                "-e", "ZEBRA_RPC__LISTEN_ADDR=0.0.0.0:8232",
                "-e", "ZEBRA_RPC__ENABLE_COOKIE_AUTH=false",
                "--restart", "unless-stopped",
                self.IMAGE_NAME
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                return False, f"Failed to start node: {result.stderr}"
            
            return True, "Node started successfully"
            
        except Exception as e:
            return False, f"Node start error: {str(e)}"
    
    # ==================== NODE CONTROL ====================
    
    def stop_node(self) -> Tuple[bool, str]:
        """Stop the Zebra node"""
        try:
            result = subprocess.run(
                ["docker", "stop", "-t", "3", self.CONTAINER_NAME],  # 3 second graceful shutdown
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0, "Node stopped" if result.returncode == 0 else result.stderr
        except Exception as e:
            return False, str(e)
    
    def restart_node(self) -> Tuple[bool, str]:
        """Restart the Zebra node"""
        try:
            result = subprocess.run(
                ["docker", "restart", self.CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0, "Node restarted" if result.returncode == 0 else result.stderr
        except Exception as e:
            return False, str(e)
    
    def get_status(self) -> NodeStatus:
        """
        Get current node status.
        """
        status = NodeStatus(
            running=False,
            sync_percent=0.0,
            current_height=0,
            target_height=0,
            peer_count=0,
            uptime="--",
            version="--"
        )
        
        try:
            # Check if container is running
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.CONTAINER_NAME}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            status.running = bool(result.stdout.strip())
            
            if not status.running:
                return status
            
            # Get container uptime
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.StartedAt}}", self.CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                started_at = result.stdout.strip()
                status.uptime = self._calculate_uptime(started_at)
            
            # Get logs
            result = subprocess.run(
                ["docker", "logs", "--tail", "200", self.CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            logs = result.stdout + result.stderr
            
            # Find ALL matches and take the LAST one (most recent)
            sync_matches = re.findall(r'sync_percent=([0-9.]+)%?', logs)
            if sync_matches:
                status.sync_percent = float(sync_matches[-1])
            
            height_matches = re.findall(r'current_height=Height\((\d+)\)', logs)
            if height_matches:
                status.current_height = int(height_matches[-1])
            
            peer_matches = re.findall(r'cached_ip_count=(\d+)', logs)
            if peer_matches:
                status.peer_count = int(peer_matches[-1])
            
            status.version = self.IMAGE_NAME
            
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            print(f"Error getting status: {e}")
        
        return status
    
    def get_logs(self, lines: int = 100) -> str:
        """Get recent logs from the node"""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(lines), self.CONTAINER_NAME],
                capture_output=True,
                text=True
            )
            return result.stdout + result.stderr
        except Exception as e:
            return f"Error getting logs: {e}"
    
    def get_disk_usage(self) -> Tuple[str, str]:
        """
        Get disk usage for SSD and SD card.
        Commands:
            df -h /mnt/zebra-data (SSD - should grow)
            df -h / (SD - should stay ~8GB)
        """
        ssd_usage = "--"
        sd_usage = "--"
        
        try:
            # SSD usage
            result = subprocess.run(
                ["df", "-h", self.MOUNT_PATH],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 5:
                        ssd_usage = f"{parts[2]} / {parts[1]} ({parts[4]})"
            
            # SD card usage
            result = subprocess.run(
                ["df", "-h", "/"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 5:
                        sd_usage = f"{parts[2]} / {parts[1]} ({parts[4]})"
        except:
            pass
        
        return ssd_usage, sd_usage
    
    def _calculate_uptime(self, started_at: str) -> str:
        """Calculate uptime from Docker started_at timestamp"""
        try:
            started = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            now = datetime.now(started.tzinfo)
            delta = now - started
            
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
        except:
            return "--"
    
    # ==================== LIGHTWALLETD ====================
    
    def get_local_ip(self) -> str:
        """Get the local IP address of this machine"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def is_lightwalletd_running(self) -> bool:
        """Check if lightwalletd container is running"""
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.LWD_CONTAINER_NAME}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return bool(result.stdout.strip())
        except:
            return False
    
    def start_lightwalletd(self) -> Tuple[bool, str]:
        """Start lightwalletd container"""
        try:
            # Check if Zebra is running first
            status = self.get_status()
            if not status.running:
                return False, "Zebra must be running first"
            
            # Check if already running
            if self.is_lightwalletd_running():
                return True, "Lightwalletd already running"
            
            # Remove any existing stopped container
            subprocess.run(
                ["docker", "rm", "-f", self.LWD_CONTAINER_NAME],
                capture_output=True
            )
            
            # Ensure zecnode network exists
            subprocess.run(
                ["docker", "network", "create", "zecnode"],
                capture_output=True
            )
            
            # Start lightwalletd container on same network as Zebra
            # Uses container name 'zebra' for DNS resolution
            result = subprocess.run([
                "docker", "run", "-d",
                "--name", self.LWD_CONTAINER_NAME,
                "--network", "zecnode",
                "-p", f"{self.LWD_PORT}:9067",
                "--restart", "unless-stopped",
                self.LWD_IMAGE_NAME,
                "--zcash-conf-path", "/dev/null",
                "--grpc-bind-addr", "0.0.0.0:9067",
                "--no-tls-very-insecure",
                f"--zebra-rpc-address={self.CONTAINER_NAME}:8232"
            ], capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                return False, f"Failed to start lightwalletd: {result.stderr}"
            
            return True, "Lightwalletd started"
            
        except subprocess.TimeoutExpired:
            return False, "Timeout starting lightwalletd"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def stop_lightwalletd(self) -> Tuple[bool, str]:
        """Stop lightwalletd container"""
        try:
            result = subprocess.run(
                ["docker", "stop", "-t", "3", self.LWD_CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=10
            )
            # Also remove container
            subprocess.run(
                ["docker", "rm", "-f", self.LWD_CONTAINER_NAME],
                capture_output=True
            )
            return True, "Lightwalletd stopped"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def get_lightwalletd_url(self) -> str:
        """Get the lightwalletd gRPC URL"""
        return f"grpc://{self.get_local_ip()}:{self.LWD_PORT}"

ENDOFFILE

cat > installer.py << 'ENDOFFILE'
"""
ZecNode Installer Wizard
Professional UI for installing the Zcash node
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QPushButton, QComboBox, QProgressBar, QLineEdit,
    QMessageBox, QSpacerItem, QSizePolicy, QApplication, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF
from PyQt5.QtGui import QFont, QPainter, QColor, QBrush, QPainterPath

from config import Config
from node_manager import NodeManager, DriveInfo
from typing import List, Optional


class SmoothProgressBar(QWidget):
    """Custom progress bar with smooth float-based animation"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0  # Float value 0-100
        self._target = 0.0
        self.setFixedHeight(8)
        
        # Animation timer
        self._timer = QTimer()
        self._timer.timeout.connect(self._animate)
    
    def start_animation(self):
        self._timer.start(16)  # ~60 FPS
    
    def stop_animation(self):
        self._timer.stop()
    
    def set_target(self, target: float):
        """Set target value (0-100)"""
        self._target = min(100.0, max(0.0, target))
    
    def set_value(self, value: float):
        """Set value directly (0-100)"""
        self._value = min(100.0, max(0.0, value))
        self.update()
    
    def value(self):
        return self._value
    
    def _animate(self):
        """Smooth easing animation"""
        if abs(self._value - self._target) < 0.1:
            # Close enough, snap to target
            if self._value != self._target:
                self._value = self._target
                self.update()
        else:
            # Ease towards target (lerp with 0.08 factor for smoothness)
            self._value += (self._target - self._value) * 0.08
            self.update()
        
        # Slow creep when idle (not at 100%)
        if self._value >= self._target and self._target < 95:
            max_creep = min(self._target + 8, 95)
            if self._value < max_creep:
                self._target = self._value + 0.05
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 4, 4)
        painter.fillPath(bg_path, QColor("#333"))
        
        # Progress fill
        if self._value > 0:
            fill_width = (self._value / 100.0) * self.width()
            fill_path = QPainterPath()
            fill_path.addRoundedRect(QRectF(0, 0, fill_width, self.height()), 4, 4)
            painter.fillPath(fill_path, QColor("#f7931a"))
        
        painter.end()


class PreRebootWorker(QThread):
    """Worker for pre-reboot steps"""
    progress = pyqtSignal(str)
    step_complete = pyqtSignal(int, bool, str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, node_manager: NodeManager, needs_update: bool, needs_docker: bool):
        super().__init__()
        self.node_manager = node_manager
        self.needs_update = needs_update
        self.needs_docker = needs_docker
        self._cancelled = False
    
    def run(self):
        try:
            if self.needs_update:
                self.progress.emit("Updating system packages...")
                success, msg = self.node_manager.update_system(self.progress.emit)
                if not success:
                    self.step_complete.emit(0, False, msg)
                    self.finished.emit(False, msg)
                    return
                self.step_complete.emit(0, True, "System updated")
            else:
                self.step_complete.emit(0, True, "Already up to date")
            
            if self._cancelled:
                return
            
            if self.needs_docker:
                self.progress.emit("Installing Docker...")
                success, msg = self.node_manager.install_docker(self.progress.emit)
                if not success:
                    self.step_complete.emit(1, False, msg)
                    self.finished.emit(False, msg)
                    return
                self.step_complete.emit(1, True, "Docker installed")
            else:
                self.step_complete.emit(1, True, "Docker ready")
            
            self.finished.emit(True, "Ready for reboot")
        except Exception as e:
            self.finished.emit(False, str(e))
    
    def cancel(self):
        self._cancelled = True


class PostRebootWorker(QThread):
    """Worker for post-reboot steps"""
    progress = pyqtSignal(str)
    step_complete = pyqtSignal(int, bool, str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, node_manager: NodeManager, drive: DriveInfo):
        super().__init__()
        self.node_manager = node_manager
        self.drive = drive
        self._cancelled = False
    
    def run(self):
        try:
            # Format
            self.progress.emit(f"Formatting {self.drive.device}...")
            success, result = self.node_manager.format_drive(self.drive.device, self.progress.emit)
            if not success:
                self.step_complete.emit(0, False, result)
                self.finished.emit(False, result)
                return
            partition = result
            self.step_complete.emit(0, True, "Drive formatted")
            
            if self._cancelled: return
            
            # Mount
            self.progress.emit("Mounting drive...")
            success, msg = self.node_manager.mount_drive(partition, self.progress.emit)
            if not success:
                self.step_complete.emit(1, False, msg)
                self.finished.emit(False, msg)
                return
            self.step_complete.emit(1, True, "Drive mounted")
            
            if self._cancelled: return
            
            # Docker on SSD
            self.progress.emit("Configuring Docker for SSD...")
            success, msg = self.node_manager.configure_docker_for_ssd(self.progress.emit)
            if not success:
                self.step_complete.emit(2, False, msg)
                self.finished.emit(False, msg)
                return
            self.step_complete.emit(2, True, "Docker configured")
            
            if self._cancelled: return
            
            # Pull image
            self.progress.emit("Downloading Zebra...")
            success, msg = self.node_manager.pull_zebra_image(self.progress.emit)
            if not success:
                self.step_complete.emit(3, False, msg)
                self.finished.emit(False, msg)
                return
            self.step_complete.emit(3, True, "Zebra downloaded")
            
            if self._cancelled: return
            
            # Create dirs
            self.progress.emit("Creating directories...")
            success, msg = self.node_manager.create_zebra_directories(self.progress.emit)
            if not success:
                self.step_complete.emit(4, False, msg)
                self.finished.emit(False, msg)
                return
            self.step_complete.emit(4, True, "Directories ready")
            
            if self._cancelled: return
            
            # Start node
            self.progress.emit("Starting node...")
            success, msg = self.node_manager.start_node(self.progress.emit)
            if not success:
                self.step_complete.emit(5, False, msg)
                self.finished.emit(False, msg)
                return
            self.step_complete.emit(5, True, "Node started")
            
            self.finished.emit(True, "Installation complete!")
        except Exception as e:
            self.finished.emit(False, str(e))
    
    def cancel(self):
        self._cancelled = True


class InstallerWizard(QMainWindow):
    """Professional installer wizard"""
    
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.node_manager = NodeManager()
        self.selected_drive: Optional[DriveInfo] = None
        self.worker = None
        self.drives = []
        self._centered = False
        self._drag_pos = None
        
        self.setWindowTitle("ZecNode")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(700, 680)
        self.resize(700, 680)
        
        self._setup_ui()
        self._check_resume()
    
    def mousePressEvent(self, event):
        """Enable dragging the window"""
        if event.button() == Qt.LeftButton and event.pos().y() < 50:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle window dragging"""
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Stop dragging"""
        self._drag_pos = None
    
    def showEvent(self, event):
        """Center window when it's shown"""
        super().showEvent(event)
        if not self._centered:
            self._center_window()
            self._centered = True
    
    def _center_window(self):
        screen = self.screen().availableGeometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )
    
    def _check_resume(self):
        """Check if we need to resume installation from a previous phase"""
        phase = self.config.get_phase()
        
        # First, check actual system state - if Docker is installed but phase says not started,
        # skip to drive selection
        if phase == Config.PHASE_NOT_STARTED:
            if self.node_manager.check_docker_installed() and self.node_manager.check_curl_installed():
                # Docker and curl already installed, skip to drive selection
                self.config.set_phase(Config.PHASE_REBOOT_DONE)
                QTimer.singleShot(100, lambda: self._go_to_page(2))
                return
            # Fresh install, stay on welcome
            return
        
        if phase == Config.PHASE_DOCKER_INSTALLED:
            # Just rebooted after Docker install, go to drive selection
            self.config.set_phase(Config.PHASE_REBOOT_DONE)
            self.config.set_needs_reboot(False)
            QTimer.singleShot(100, lambda: self._go_to_page(2))
        
        elif phase == Config.PHASE_REBOOT_DONE:
            # Was on drive selection, go back there
            QTimer.singleShot(100, lambda: self._go_to_page(2))
        
        elif phase == Config.PHASE_SYSTEM_UPDATED:
            # System was updated but Docker not installed yet
            # This shouldn't happen normally, but handle it
            QTimer.singleShot(100, lambda: self._go_to_page(1))
    
    def _setup_ui(self):
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)
        
        # Main container with rounded corners
        self.container = QFrame(central)
        self.container.setObjectName("installerContainer")
        self.container.setStyleSheet("""
            #installerContainer {
                background-color: #0f0f14;
                border: 1px solid #333;
                border-radius: 15px;
            }
        """)
        
        # Layout for container
        container_layout = QVBoxLayout(central)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.container)
        
        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Close button in top right
        close_bar = QHBoxLayout()
        close_bar.setContentsMargins(0, 10, 15, 0)
        close_bar.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #666;
                font-size: 16px;
            }
            QPushButton:hover { color: #ff5555; }
        """)
        close_btn.clicked.connect(self.close)
        close_bar.addWidget(close_btn)
        
        main_layout.addLayout(close_bar)
        
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        main_layout.addWidget(self.stack)
        
        self.stack.addWidget(self._create_welcome())      # 0
        self.stack.addWidget(self._create_setup())        # 1
        self.stack.addWidget(self._create_drive())        # 2
        self.stack.addWidget(self._create_confirm())      # 3
        self.stack.addWidget(self._create_install())      # 4
        self.stack.addWidget(self._create_reboot())       # 5
        self.stack.addWidget(self._create_complete())     # 6
    
    def _page(self):
        """Create standard page widget"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 20, 50, 40)
        layout.setSpacing(0)
        return page, layout
    
    def _spacer(self, height=20):
        return QSpacerItem(0, height, QSizePolicy.Minimum, QSizePolicy.Fixed)
    
    # ==================== WELCOME ====================
    
    def _create_welcome(self):
        page, layout = self._page()
        
        # Logo/Icon - use HTML for guaranteed sizing
        self.lightning_icon = QLabel('<span style="font-size: 72px; color: #f4b728;">⚡</span>')
        self.lightning_icon.setTextFormat(Qt.RichText)
        self.lightning_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lightning_icon)
        
        # Pulse animation
        self.pulse_value = 0
        self.pulse_direction = 1
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self._pulse_lightning)
        self.pulse_timer.start(50)  # 50ms for smooth animation
        
        layout.addItem(self._spacer(15))
        
        # Title
        title = QLabel("ZecNode")
        title.setFont(QFont("Segoe UI", 32, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #f4b728;")
        layout.addWidget(title)
        
        subtitle = QLabel("Quick Setup Zcash Node")
        subtitle.setFont(QFont("Segoe UI", 13))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888;")
        layout.addWidget(subtitle)
        
        layout.addItem(self._spacer(30))
        
        # Requirements - left aligned in a centered container
        reqs_container = QHBoxLayout()
        reqs_container.addStretch()
        
        reqs = QLabel(
            "Requirements\n\n"
            "●  Raspberry Pi 5 or Linux PC\n\n"
            "●  SSD (500GB+, external USB or NVMe)\n\n"
            "●  Internet connection\n\n"
            "●  ~30 minutes for setup"
        )
        reqs.setFont(QFont("Segoe UI", 13))
        reqs.setStyleSheet("color: #ccc;")
        reqs.setAlignment(Qt.AlignLeft)
        reqs_container.addWidget(reqs)
        
        reqs_container.addStretch()
        layout.addLayout(reqs_container)
        
        layout.addStretch()
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        start_btn = QPushButton("Get Started")
        start_btn.setFixedSize(180, 50)
        start_btn.setStyleSheet("""
            QPushButton {
                background-color: #f4b728;
                border: none;
                border-radius: 25px;
                color: #0f0f14;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f5c040;
            }
        """)
        start_btn.clicked.connect(self._start_setup)
        btn_row.addWidget(start_btn)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        layout.addSpacing(30)
        
        return page
    
    # ==================== SETUP ====================
    
    def _create_setup(self):
        page, layout = self._page()
        
        title = QLabel("Setting Up")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        layout.addWidget(title)
        
        subtitle = QLabel("This may take 10-20 minutes")
        subtitle.setStyleSheet("color: #888;")
        layout.addWidget(subtitle)
        
        layout.addItem(self._spacer(25))
        
        # Custom smooth progress bar
        self.setup_progress = SmoothProgressBar()
        layout.addWidget(self.setup_progress)
        
        layout.addItem(self._spacer(10))
        
        self.setup_status = QLabel("Preparing...")
        self.setup_status.setStyleSheet("color: #888;")
        layout.addWidget(self.setup_status)
        
        layout.addItem(self._spacer(30))
        
        # Steps
        self.setup_steps = []
        steps = ["Update system", "Install Docker"]
        
        for step in steps:
            row = QHBoxLayout()
            row.setSpacing(12)
            
            check = QLabel("○")
            check.setFixedWidth(20)
            check.setStyleSheet("color: #444; font-size: 14px;")
            self.setup_steps.append(check)
            row.addWidget(check)
            
            label = QLabel(step)
            label.setStyleSheet("color: #888;")
            row.addWidget(label)
            row.addStretch()
            
            layout.addLayout(row)
            layout.addItem(self._spacer(8))
        
        layout.addStretch()
        return page
    
    # ==================== DRIVE SELECTION ====================
    
    def _create_drive(self):
        page, layout = self._page()
        
        title = QLabel("Select Drive")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        layout.addWidget(title)
        
        subtitle = QLabel("Choose your external SSD for blockchain storage")
        subtitle.setStyleSheet("color: #888;")
        layout.addWidget(subtitle)
        
        layout.addItem(self._spacer(30))
        
        # Drive list container
        self.drive_list_widget = QWidget()
        self.drive_list_layout = QVBoxLayout(self.drive_list_widget)
        self.drive_list_layout.setContentsMargins(0, 0, 0, 0)
        self.drive_list_layout.setSpacing(8)
        layout.addWidget(self.drive_list_widget)
        
        # Store drive buttons
        self.drive_buttons = []
        
        layout.addItem(self._spacer(15))
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedSize(120, 44)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                border: 1px solid #444;
                border-radius: 22px;
                color: #e8e8e8;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a4a; }
        """)
        self.refresh_btn.clicked.connect(self._refresh_drives)
        layout.addWidget(self.refresh_btn)
        
        layout.addStretch()
        
        # No drives message
        self.no_drives = QLabel("No external drives found.\nConnect an SSD and click Refresh.")
        self.no_drives.setStyleSheet("color: #888;")
        self.no_drives.setAlignment(Qt.AlignCenter)
        self.no_drives.setVisible(False)
        layout.addWidget(self.no_drives)
        
        layout.addStretch()
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        self.drive_next = QPushButton("Continue")
        self.drive_next.setFixedSize(160, 50)
        self.drive_next.setEnabled(False)
        self.drive_next.setStyleSheet("""
            QPushButton {
                background-color: #f4b728;
                border: none;
                border-radius: 25px;
                color: #0f0f14;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #f5c040; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.drive_next.clicked.connect(lambda: self._go_to_page(3))
        btn_row.addWidget(self.drive_next)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addSpacing(30)
        return page
    
    # ==================== CONFIRM ====================
    
    def _create_confirm(self):
        page, layout = self._page()
        
        title = QLabel("Confirm")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        layout.addWidget(title)
        
        layout.addItem(self._spacer(20))
        
        self.confirm_info = QLabel("")
        self.confirm_info.setStyleSheet("color: #ccc; font-size: 13px; line-height: 1.5;")
        self.confirm_info.setWordWrap(True)
        layout.addWidget(self.confirm_info)
        
        layout.addItem(self._spacer(25))
        
        # Warning
        warning = QLabel("⚠  All data on this drive will be erased")
        warning.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 13px;")
        layout.addWidget(warning)
        
        layout.addItem(self._spacer(20))
        
        # Confirmation input
        confirm_label = QLabel("Type the drive name to confirm:")
        confirm_label.setStyleSheet("color: #888;")
        layout.addWidget(confirm_label)
        
        layout.addItem(self._spacer(8))
        
        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText("e.g. sda")
        self.confirm_input.setFixedHeight(45)
        self.confirm_input.textChanged.connect(self._check_confirm)
        layout.addWidget(self.confirm_input)
        
        layout.addStretch()
        
        # Buttons
        btn_row = QHBoxLayout()
        
        back_btn = QPushButton("Back")
        back_btn.setFixedSize(120, 50)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                border: 1px solid #444;
                border-radius: 25px;
                color: #e8e8e8;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a4a; }
        """)
        back_btn.clicked.connect(lambda: self._go_to_page(2))
        btn_row.addWidget(back_btn)
        
        btn_row.addStretch()
        
        self.confirm_btn = QPushButton("Install")
        self.confirm_btn.setFixedSize(160, 50)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                border: none;
                border-radius: 25px;
                color: #fff;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #f87171; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.confirm_btn.clicked.connect(self._start_install)
        btn_row.addWidget(self.confirm_btn)
        
        layout.addLayout(btn_row)
        layout.addSpacing(30)
        return page
    
    # ==================== INSTALL ====================
    
    def _create_install(self):
        page, layout = self._page()
        
        title = QLabel("Installing")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        layout.addWidget(title)
        
        layout.addItem(self._spacer(25))
        
        # Custom smooth progress bar
        self.install_progress = SmoothProgressBar()
        layout.addWidget(self.install_progress)
        
        layout.addItem(self._spacer(10))
        
        self.install_status = QLabel("Preparing...")
        self.install_status.setStyleSheet("color: #888;")
        layout.addWidget(self.install_status)
        
        layout.addItem(self._spacer(30))
        
        # Steps
        self.install_steps = []
        steps = [
            "Format drive",
            "Mount drive",
            "Configure Docker",
            "Download Zebra",
            "Create directories",
            "Start node"
        ]
        
        for step in steps:
            row = QHBoxLayout()
            row.setSpacing(12)
            
            check = QLabel("○")
            check.setFixedWidth(20)
            check.setStyleSheet("color: #444; font-size: 14px;")
            self.install_steps.append(check)
            row.addWidget(check)
            
            label = QLabel(step)
            label.setStyleSheet("color: #888;")
            row.addWidget(label)
            row.addStretch()
            
            layout.addLayout(row)
            layout.addItem(self._spacer(6))
        
        layout.addStretch()
        return page
    
    # ==================== REBOOT ====================
    
    def _create_reboot(self):
        page, layout = self._page()
        
        layout.addStretch()
        
        icon = QLabel("🔄")
        icon.setFont(QFont("Segoe UI", 48))
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        
        layout.addItem(self._spacer(20))
        
        title = QLabel("Reboot Required")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        layout.addItem(self._spacer(15))
        
        info = QLabel(
            "Docker has been installed.\n\n"
            "After reboot, run ZecNode again\n"
            "to continue the installation."
        )
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #888; line-height: 1.5;")
        layout.addWidget(info)
        
        layout.addStretch()
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        later_btn = QPushButton("Later")
        later_btn.setFixedSize(120, 50)
        later_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                border: 1px solid #444;
                border-radius: 25px;
                color: #e8e8e8;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a4a; }
        """)
        later_btn.clicked.connect(self.close)
        btn_row.addWidget(later_btn)
        
        btn_row.addSpacing(15)
        
        reboot_btn = QPushButton("Reboot Now")
        reboot_btn.setFixedSize(160, 50)
        reboot_btn.setStyleSheet("""
            QPushButton {
                background-color: #f4b728;
                border: none;
                border-radius: 25px;
                color: #0f0f14;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #f5c040; }
        """)
        reboot_btn.clicked.connect(self._reboot)
        btn_row.addWidget(reboot_btn)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        layout.addSpacing(30)
        
        return page
    
    # ==================== COMPLETE ====================
    
    def _create_complete(self):
        page, layout = self._page()
        
        layout.addStretch()
        
        # Large green checkmark - use HTML for guaranteed sizing
        icon = QLabel('<span style="font-size: 80px; color: #4ade80;">✔</span>')
        icon.setTextFormat(Qt.RichText)
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        
        layout.addItem(self._spacer(30))
        
        title = QLabel('<span style="font-size: 36px; font-weight: bold; color: white;">You\'re All Set</span>')
        title.setTextFormat(Qt.RichText)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        layout.addItem(self._spacer(25))
        
        info = QLabel(
            '<div style="font-size: 15px; color: #888; text-align: center; line-height: 1.6;">'
            'Your Zcash node is running!<br><br>'
            'Initial sync takes 3-7 days.<br>'
            'The node runs in the background.'
            '</div>'
        )
        info.setTextFormat(Qt.RichText)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        layout.addStretch()
        
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        dash_btn = QPushButton("Open Dashboard")
        dash_btn.setFixedSize(200, 55)
        dash_btn.setStyleSheet("""
            QPushButton {
                background-color: #f4b728;
                border: none;
                border-radius: 27px;
                color: #0f0f14;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #f5c040; }
        """)
        dash_btn.clicked.connect(self._open_dashboard)
        btn_row.addWidget(dash_btn)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        layout.addSpacing(30)
        
        return page
    
    # ==================== LOGIC ====================
    
    def _go_to_page(self, index):
        if index == 2:
            self._refresh_drives()
        elif index == 3:
            self._update_confirm()
        self.stack.setCurrentIndex(index)
    
    def _start_setup(self):
        self._go_to_page(1)
        
        for step in self.setup_steps:
            step.setText("○")
            step.setStyleSheet("color: #444;")
        
        # Reset and start progress animation
        self.setup_progress.set_value(0)
        self.setup_progress.set_target(10)  # Start creeping towards 10%
        self.setup_progress.start_animation()
        
        needs_docker = not self.node_manager.check_docker_installed()
        
        self.worker = PreRebootWorker(self.node_manager, True, needs_docker)
        self.worker.progress.connect(lambda m: self.setup_status.setText(m))
        self.worker.step_complete.connect(self._on_setup_step)
        self.worker.finished.connect(self._on_setup_done)
        self.worker.start()
    
    def _on_setup_step(self, idx, ok, msg):
        if idx < len(self.setup_steps):
            self.setup_steps[idx].setText("✓" if ok else "✗")
            self.setup_steps[idx].setStyleSheet(f"color: {'#4ade80' if ok else '#ef4444'};")
        # Jump target forward when step completes (0-100 scale)
        self.setup_progress.set_target((idx + 1) * 50)
    
    def _on_setup_done(self, ok, msg):
        self.setup_progress.stop_animation()
        self.setup_progress.set_value(100)
        if ok:
            self.config.set_phase(Config.PHASE_DOCKER_INSTALLED)
            self.config.set_needs_reboot(True)
            self._go_to_page(5)
        else:
            QMessageBox.critical(self, "Error", msg)
            self._go_to_page(0)
    
    def _refresh_drives(self):
        """Refresh drive list while preserving selection if possible"""
        # Visual feedback
        self.refresh_btn.setText("Refreshing...")
        self.refresh_btn.setEnabled(False)
        QApplication.processEvents()
        
        # Remember current selection
        previous_device = None
        if self.selected_drive:
            previous_device = self.selected_drive.device
        
        # Clear existing buttons
        for btn in self.drive_buttons:
            btn.deleteLater()
        self.drive_buttons = []
        
        self.drives = self.node_manager.detect_external_drives()
        
        # Restore button
        self.refresh_btn.setText("Refresh")
        self.refresh_btn.setEnabled(True)
        
        if not self.drives:
            self.drive_list_widget.setVisible(False)
            self.no_drives.setVisible(True)
            self.drive_next.setEnabled(False)
            self.selected_drive = None
            return
        
        self.drive_list_widget.setVisible(True)
        self.no_drives.setVisible(False)
        
        # Create list items
        restore_index = 0
        for i, d in enumerate(self.drives):
            btn = QPushButton(f"  {d.device}  •  {d.size_human}  •  {d.model}")
            btn.setFixedHeight(50)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e1e28;
                    border: 2px solid #333;
                    border-radius: 8px;
                    color: #ccc;
                    text-align: left;
                    padding-left: 15px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    border-color: #555;
                    background-color: #252532;
                }
                QPushButton:checked {
                    border-color: #f4b728;
                    background-color: #2a2a3a;
                    color: white;
                }
            """)
            btn.clicked.connect(lambda checked, idx=i: self._on_drive_select(idx))
            self.drive_list_layout.addWidget(btn)
            self.drive_buttons.append(btn)
            
            if previous_device and d.device == previous_device:
                restore_index = i
        
        # Select drive
        self._on_drive_select(restore_index)
    
    def _on_drive_select(self, idx):
        """Handle drive selection from list"""
        # Uncheck all buttons, check selected one
        for i, btn in enumerate(self.drive_buttons):
            btn.setChecked(i == idx)
        
        if 0 <= idx < len(self.drives):
            self.selected_drive = self.drives[idx]
            self.drive_next.setEnabled(True)
        else:
            self.selected_drive = None
            self.drive_next.setEnabled(False)
    
    def _update_confirm(self):
        if self.selected_drive:
            d = self.selected_drive
            self.confirm_info.setText(
                f"Drive: {d.device}\n"
                f"Size: {d.size_human}\n"
                f"Model: {d.model}\n\n"
                f"This will format the drive, configure Docker\n"
                f"to use it, and start your Zcash node."
            )
        self.confirm_input.clear()
        self.confirm_btn.setEnabled(False)
    
    def _check_confirm(self, text):
        if self.selected_drive:
            expected = self.selected_drive.device.replace("/dev/", "")
            self.confirm_btn.setEnabled(text.strip().lower() == expected.lower())
    
    def _start_install(self):
        if not self.selected_drive:
            return
        
        self._go_to_page(4)
        
        for step in self.install_steps:
            step.setText("○")
            step.setStyleSheet("color: #444;")
        
        # Reset and start progress animation
        self.install_progress.set_value(0)
        self.install_progress.set_target(5)  # Start creeping towards 5%
        self.install_progress.start_animation()
        
        self.worker = PostRebootWorker(self.node_manager, self.selected_drive)
        self.worker.progress.connect(lambda m: self.install_status.setText(m))
        self.worker.step_complete.connect(self._on_install_step)
        self.worker.finished.connect(self._on_install_done)
        self.worker.start()
    
    def _on_install_step(self, idx, ok, msg):
        if idx < len(self.install_steps):
            self.install_steps[idx].setText("✓" if ok else "✗")
            self.install_steps[idx].setStyleSheet(f"color: {'#4ade80' if ok else '#ef4444'};")
        # Jump target forward when step completes (6 steps, 0-100 scale)
        self.install_progress.set_target(int((idx + 1) / 6 * 100))
    
    def _on_install_done(self, ok, msg):
        self.install_progress.stop_animation()
        self.install_progress.set_value(100)
        if ok:
            self.config.set_data_path("/mnt/zebra-data")
            self.config.mark_installed()
            self._go_to_page(6)
        else:
            QMessageBox.critical(self, "Error", msg)
            self._go_to_page(3)
    
    def _reboot(self):
        import subprocess
        self.close()
        subprocess.run(["sudo", "systemctl", "reboot", "-i"])
    
    def _pulse_lightning(self):
        """Animate the lightning bolt with a glow effect"""
        self.pulse_value += self.pulse_direction * 5
        if self.pulse_value >= 100:
            self.pulse_direction = -1
        elif self.pulse_value <= 0:
            self.pulse_direction = 1
        
        # Interpolate between dim orange and bright yellow
        brightness = 0.6 + (self.pulse_value / 100) * 0.4  # 0.6 to 1.0
        r = int(244 * brightness)
        g = int(183 * brightness)
        b = int(40 * brightness)
        
        # Glow intensity matches pulse
        glow_size = 10 + int((self.pulse_value / 100) * 20)  # 10px to 30px
        glow_opacity = 0.5 + (self.pulse_value / 100) * 0.5  # 0.5 to 1.0
        
        self.lightning_icon.setText(
            f'<span style="font-size: 72px; color: rgb({r},{g},{b}); '
            f'text-shadow: 0 0 {glow_size}px rgba(244,183,40,{glow_opacity}), '
            f'0 0 {glow_size*2}px rgba(244,183,40,{glow_opacity*0.5}), '
            f'0 0 {glow_size*3}px rgba(244,140,40,{glow_opacity*0.3});">⚡</span>'
        )
    
    def _open_dashboard(self):
        from dashboard import DashboardWindow
        self.dashboard = DashboardWindow(self.config)
        self.dashboard.show()
        self.close()

ENDOFFILE

cat > dashboard.py << 'ENDOFFILE'
"""
ZecNode Dashboard
Professional status display and node controls
"""

import socket
import json
import os
import urllib.request
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QSystemTrayIcon,
    QMenu, QAction, QMessageBox, QDialog, QApplication,
    QSpacerItem, QSizePolicy, QFrame, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QTextCursor

from config import Config, VERSION
from node_manager import NodeManager


def check_internet(timeout=2) -> bool:
    """Check if internet is available by trying to connect to a reliable host"""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError:
        pass
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=timeout)
        return True
    except OSError:
        return False


def fetch_zec_price():
    """Fetch ZEC price from CoinGecko API"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=zcash&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={'User-Agent': 'ZecNode/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            price = data['zcash']['usd']
            change = data['zcash']['usd_24h_change']
            return price, change
    except:
        return None, None


class PriceThread(QThread):
    """Background thread for fetching ZEC price"""
    finished = pyqtSignal(object, object)  # price, change
    
    def run(self):
        price, change = fetch_zec_price()
        self.finished.emit(price, change)


class NodeActionThread(QThread):
    """Background thread for node operations"""
    finished = pyqtSignal(bool, str)
    
    def __init__(self, action, node_manager):
        super().__init__()
        self.action = action
        self.node_manager = node_manager
    
    def run(self):
        if self.action == "start":
            ok, msg = self.node_manager.start_node()
        elif self.action == "stop":
            ok, msg = self.node_manager.stop_node()
        elif self.action == "restart":
            ok, msg = self.node_manager.restart_node()
        else:
            ok, msg = False, "Unknown action"
        self.finished.emit(ok, msg)


class RefreshThread(QThread):
    """Background thread for fetching node status without blocking UI"""
    finished = pyqtSignal(object, bool, str, str)  # status, has_internet, ssd, sd
    
    def __init__(self, node_manager):
        super().__init__()
        self.node_manager = node_manager
        self._running = True
    
    def stop(self):
        self._running = False
    
    def run(self):
        if not self._running:
            return
        
        # Check internet
        has_internet = check_internet()
        
        if not self._running:
            return
        
        # Get node status (this is the slow call)
        status = self.node_manager.get_status()
        
        if not self._running:
            return
        
        # Get disk usage
        ssd, sd = self.node_manager.get_disk_usage()
        
        if not self._running:
            return
        
        self.finished.emit(status, has_internet, ssd, sd)


class LogsDialog(QDialog):
    """Live logs viewer"""
    
    def __init__(self, parent, node_manager: NodeManager):
        super().__init__(parent)
        self.node_manager = node_manager
        
        self.setMinimumSize(750, 500)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header with status
        header = QHBoxLayout()
        header.addStretch()
        
        self.status_label = QLabel("● Live")
        self.status_label.setStyleSheet("color: #4ade80;")
        header.addWidget(self.status_label)
        
        layout.addLayout(header)
        layout.addSpacing(10)
        
        # Log area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        layout.addSpacing(15)
        
        # Buttons
        btn_row = QHBoxLayout()
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setObjectName("secondary")
        self.pause_btn.setFixedWidth(100)
        self.pause_btn.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self.pause_btn)
        
        btn_row.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        
        layout.addLayout(btn_row)
        
        # Timer
        self.paused = False
        self.timer = QTimer()
        self.timer.timeout.connect(self._refresh)
        self.timer.start(15000)  # 15 seconds
        self._refresh()
    
    def _toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.timer.stop()
            self.pause_btn.setText("Resume")
            self.status_label.setText("● Paused")
            self.status_label.setStyleSheet("color: #888;")
        else:
            self.timer.start(15000)
            self.pause_btn.setText("Pause")
            self.status_label.setText("● Live")
            self.status_label.setStyleSheet("color: #4ade80;")
    
    def _refresh(self):
        logs = self.node_manager.get_logs(300)
        
        # Filter out static startup messages that clutter the view
        filtered_lines = []
        skip_phrases = [
            "initialized disabled sentry",
            "Thank you for running",
            "You're helping to strengthen"
        ]
        for line in logs.split('\n'):
            if not any(phrase in line for phrase in skip_phrases):
                filtered_lines.append(line)
        
        self.log_text.setPlainText('\n'.join(filtered_lines))
        # Scroll to bottom to show latest logs
        self.log_text.moveCursor(QTextCursor.End)
        self.log_text.ensureCursorVisible()
    
    def closeEvent(self, event):
        self.timer.stop()
        self.timer.deleteLater()
        super().closeEvent(event)


class StatusDot(QWidget):
    """Animated status indicator - green (running), red (stopped), yellow (no internet)"""
    
    STATE_STOPPED = 0
    STATE_RUNNING = 1
    STATE_NO_INTERNET = 2
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._state = self.STATE_STOPPED
    
    def set_running(self, running: bool):
        self._state = self.STATE_RUNNING if running else self.STATE_STOPPED
        self.update()
    
    def set_state(self, state: int):
        self._state = state
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._state == self.STATE_RUNNING:
            color = QColor("#4ade80")  # Green
        elif self._state == self.STATE_NO_INTERNET:
            color = QColor("#f4b728")  # Yellow/Orange
        else:
            color = QColor("#ef4444")  # Red
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, 10, 10)


class ConfirmDialog(QDialog):
    """Custom styled confirmation dialog matching ZecNode theme"""
    
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(450, 280)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Main container
        container = QFrame(self)
        container.setGeometry(0, 0, 450, 280)
        container.setStyleSheet("""
            QFrame {
                background-color: #1a1a24;
                border: 1px solid #333;
                border-radius: 15px;
            }
        """)
        
        # Close button (X) in top right
        close_btn = QPushButton("✕", container)
        close_btn.setGeometry(405, 10, 30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #666;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #fff;
            }
        """)
        close_btn.clicked.connect(self.reject)
        
        # Title
        title_label = QLabel(title, container)
        title_label.setGeometry(0, 30, 450, 30)
        title_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title_label.setStyleSheet("color: #f4b728; border: none; background: transparent;")
        title_label.setAlignment(Qt.AlignCenter)
        
        # Message
        msg_label = QLabel(message, container)
        msg_label.setGeometry(40, 70, 370, 80)
        msg_label.setStyleSheet("color: #e8e8e8; font-size: 12px; border: none; background: transparent;")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)
        
        # Buttons container
        btn_widget = QWidget(container)
        btn_widget.setGeometry(0, 180, 450, 70)
        btn_widget.setStyleSheet("background: transparent; border: none;")
        
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(60, 0, 60, 0)
        btn_layout.setSpacing(20)
        
        self.no_btn = QPushButton("Cancel")
        self.no_btn.setMinimumHeight(50)
        self.no_btn.setMinimumWidth(140)
        self.no_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                border: 1px solid #444;
                color: #e8e8e8;
                border-radius: 25px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a4a; }
        """)
        self.no_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.no_btn)
        
        self.yes_btn = QPushButton("Update")
        self.yes_btn.setMinimumHeight(50)
        self.yes_btn.setMinimumWidth(140)
        self.yes_btn.setStyleSheet("""
            QPushButton {
                background-color: #f4b728;
                border: none;
                color: #0f0f14;
                border-radius: 25px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #f5c040; }
        """)
        self.yes_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.yes_btn)
    
    def accept(self):
        self.result = True
        super().accept()


class MessageDialog(QDialog):
    """Custom styled message dialog matching ZecNode theme"""
    
    def __init__(self, parent, title, message, is_error=False):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(320, 180)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Main container with rounded corners
        container = QFrame(self)
        container.setGeometry(0, 0, 320, 180)
        container.setStyleSheet("""
            QFrame {
                background-color: #1a1a24;
                border: 1px solid #333;
                border-radius: 15px;
            }
        """)
        
        # Close button (X) in top right
        close_btn = QPushButton("✕", container)
        close_btn.setGeometry(275, 10, 30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #666;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #fff;
            }
        """)
        close_btn.clicked.connect(self.accept)
        
        # Title
        title_label = QLabel(title, container)
        title_label.setGeometry(0, 30, 320, 30)
        title_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        color = "#ef4444" if is_error else "#4ade80"
        title_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        title_label.setAlignment(Qt.AlignCenter)
        
        # Message
        msg_label = QLabel(message, container)
        msg_label.setGeometry(20, 65, 280, 50)
        msg_label.setStyleSheet("color: #e8e8e8; font-size: 12px; border: none; background: transparent;")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)
        
        # OK Button
        ok_btn = QPushButton("OK", container)
        ok_btn.setGeometry(120, 125, 80, 40)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #f4b728;
                border: none;
                border-radius: 20px;
                color: #0f0f14;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f5c040;
            }
        """)
        ok_btn.clicked.connect(self.accept)


class UpdateDialog(QDialog):
    """Loading dialog with pulsing Zcash logo"""
    
    def __init__(self, parent, message="Updating..."):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(250, 180)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Main container with rounded corners
        container = QFrame(self)
        container.setGeometry(0, 0, 250, 180)
        container.setStyleSheet("""
            QFrame {
                background-color: #1a1a24;
                border: 1px solid #333;
                border-radius: 15px;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 25, 20, 25)
        
        # Zcash logo (will pulse)
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet("border: none; background: transparent;")
        self._opacity = 1.0
        self._fading_out = True
        
        # Load the Zcash icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zecnode-icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
        else:
            self.logo_label.setText("Ⓩ")
            self.logo_label.setStyleSheet("font-size: 48px; color: #f4b728; border: none; background: transparent;")
        
        layout.addWidget(self.logo_label)
        
        # Message
        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("color: #e8e8e8; font-size: 14px; border: none; background: transparent;")
        layout.addWidget(self.message_label)
        
        # Pulse animation timer
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self._pulse)
        self.pulse_timer.start(50)
    
    def _pulse(self):
        if self._fading_out:
            self._opacity -= 0.03
            if self._opacity <= 0.3:
                self._fading_out = False
        else:
            self._opacity += 0.03
            if self._opacity >= 1.0:
                self._fading_out = True
        
        # Use setGraphicsEffect for actual opacity
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        effect = QGraphicsOpacityEffect()
        effect.setOpacity(self._opacity)
        self.logo_label.setGraphicsEffect(effect)
    
    def set_message(self, message):
        self.message_label.setText(message)
    
    def closeEvent(self, event):
        self.pulse_timer.stop()
        super().closeEvent(event)


class UpdateThread(QThread):
    """Background thread for updates"""
    finished = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, update_type, data_path=None):
        super().__init__()
        self.update_type = update_type
        self.data_path = data_path
    
    def run(self):
        import subprocess
        import os
        try:
            if self.update_type == "zecnode":
                # Simple update - just download new main.py to zecnode folder
                home = os.path.expanduser("~")
                zecnode_dir = os.path.join(home, "zecnode")
                
                # Download new install script and extract main.py
                result = subprocess.run(
                    ["bash", "-c", f"""
                        curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install_zecnode.sh -o /tmp/zecnode_update.sh
                        # Extract just the Python code between the markers
                        sed -n '/^cat > main.py << '\\''ENDOFFILE'\\''$/,/^ENDOFFILE$/p' /tmp/zecnode_update.sh | tail -n +2 | head -n -1 > {zecnode_dir}/main.py.new
                        if [ -s {zecnode_dir}/main.py.new ]; then
                            mv {zecnode_dir}/main.py.new {zecnode_dir}/main.py
                            rm -f /tmp/zecnode_update.sh
                            echo "SUCCESS"
                        else
                            rm -f {zecnode_dir}/main.py.new /tmp/zecnode_update.sh
                            echo "FAILED: Could not extract main.py"
                            exit 1
                        fi
                    """],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0 and "SUCCESS" in result.stdout:
                    self.finished.emit(True, "RESTART_ZECNODE")
                else:
                    error = result.stderr or result.stdout or "Unknown error"
                    self.finished.emit(False, f"Update failed: {error}")
            
            elif self.update_type == "zebra":
                # Pull latest image
                result = subprocess.run(
                    ["docker", "pull", "zfnd/zebra:3.1.0"],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    self.finished.emit(False, "Failed to pull Zebra image")
                    return
                
                # Get ALL mount info from existing container BEFORE removing it
                volume_mounts = []
                port_mappings = ["8233:8233"]  # Default port
                
                try:
                    # Get volume mounts using JSON format for reliable parsing
                    mount_result = subprocess.run(
                        ["docker", "inspect", "--format", "{{json .Mounts}}", "zebra"],
                        capture_output=True, text=True, timeout=10
                    )
                    if mount_result.returncode == 0 and mount_result.stdout.strip():
                        import json
                        mounts = json.loads(mount_result.stdout.strip())
                        for mount in mounts:
                            source = mount.get('Source', '')
                            dest = mount.get('Destination', '')
                            if source and dest:
                                volume_mounts.append(f"{source}:{dest}")
                except:
                    pass
                
                # Fallback if we couldn't get mounts
                if not volume_mounts:
                    data_path = self.data_path or "/mnt/zcash"
                    volume_mounts = [
                        f"{data_path}/zebra-cache:/var/cache/zebrad-cache",
                        f"{data_path}/zebra-state:/var/lib/zebrad"
                    ]
                
                # Check if container is running
                running = subprocess.run(
                    ["docker", "ps", "-q", "-f", "name=zebra"],
                    capture_output=True, text=True
                )
                was_running = bool(running.stdout.strip())
                
                # Stop container if running
                if was_running:
                    subprocess.run(["docker", "stop", "zebra"], capture_output=True, timeout=30)
                
                # Remove old container
                subprocess.run(["docker", "rm", "zebra"], capture_output=True, timeout=10)
                
                # Build docker run command with same mounts
                docker_cmd = [
                    "docker", "run", "-d",
                    "--name", "zebra",
                    "--restart", "unless-stopped",
                ]
                
                # Add all volume mounts
                for mount in volume_mounts:
                    docker_cmd.extend(["-v", mount])
                
                # Add port mapping
                docker_cmd.extend(["-p", "8233:8233"])
                
                docker_cmd.append("zfnd/zebra:3.1.0")
                
                result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    self.finished.emit(True, "Zebra updated successfully!")
                else:
                    self.finished.emit(False, f"Failed to start Zebra: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            self.finished.emit(False, "Update timed out")
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


class StatCard(QFrame):
    """Stat display card"""
    
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setStyleSheet("""
            #statCard {
                background-color: #16161d;
                border: 1px solid #2a2a35;
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(4)
        
        self.value_label = QLabel("--")
        self.value_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.value_label.setStyleSheet("color: #fff; background: transparent; border: none;")
        layout.addWidget(self.value_label)
        
        title = QLabel(label)
        title.setStyleSheet("color: #666; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(title)
    
    def set_value(self, val: str):
        self.value_label.setText(val)


class StatusUptimeCard(QFrame):
    """Uptime card with integrated status indicator"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusUptimeCard")
        self.setStyleSheet("""
            #statusUptimeCard {
                background-color: #16161d;
                border: 1px solid #2a2a35;
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(4)
        
        # Top row with uptime value
        self.value_label = QLabel("--")
        self.value_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.value_label.setStyleSheet("color: #fff; background: transparent; border: none;")
        layout.addWidget(self.value_label)
        
        # Bottom row with status dot and text
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.setContentsMargins(0, 0, 0, 0)
        
        self.status_dot = StatusDot()
        status_row.addWidget(self.status_dot)
        
        self.status_text = QLabel("Checking...")
        self.status_text.setStyleSheet("color: #666; font-size: 11px; background: transparent; border: none;")
        status_row.addWidget(self.status_text)
        
        status_row.addStretch()
        layout.addLayout(status_row)
    
    def set_value(self, val: str):
        self.value_label.setText(val)
    
    def set_status(self, state: int, text: str):
        self.status_dot.set_state(state)
        self.status_text.setText(text)
        # Update text color based on state
        if state == StatusDot.STATE_RUNNING:
            self.status_text.setStyleSheet("color: #4ade80; font-size: 11px; background: transparent; border: none;")
        elif state == StatusDot.STATE_STOPPED:
            self.status_text.setStyleSheet("color: #f87171; font-size: 11px; background: transparent; border: none;")
        elif state == StatusDot.STATE_NO_INTERNET:
            self.status_text.setStyleSheet("color: #f4b728; font-size: 11px; background: transparent; border: none;")
        else:
            self.status_text.setStyleSheet("color: #666; font-size: 11px; background: transparent; border: none;")


class DashboardWindow(QMainWindow):
    """Professional dashboard"""
    
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.node_manager = NodeManager(config.get_data_path())
        self._centered = False
        self._drag_pos = None
        
        self.setWindowTitle("ZecNode")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(600, 550)
        self.resize(600, 550)
        
        self._setup_ui()
        self._setup_tray()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._start_refresh)
        self.timer.start(5000)  # 5 seconds - reduces thread buildup
        self._action_in_progress = False
        self._closing = False
        self.refresh_thread = None
        self._start_refresh()
        
        # Price timer - update every 30 seconds
        self.price_thread = None
        self.price_timer = QTimer()
        self.price_timer.timeout.connect(self._fetch_price)
        self.price_timer.start(30000)
        self._fetch_price()
        
        # Cleanup timer - garbage collect every hour to prevent zombie thread buildup
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._cleanup_threads)
        self.cleanup_timer.start(3600000)  # 1 hour in milliseconds
    
    def mousePressEvent(self, event):
        """Enable dragging the window"""
        if event.button() == Qt.LeftButton and event.pos().y() < 50:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle window dragging"""
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Stop dragging"""
        self._drag_pos = None
    
    def showEvent(self, event):
        """Center window when it's shown"""
        super().showEvent(event)
        if not self._centered:
            self._center_window()
            self._centered = True
    
    def _center_window(self):
        screen = self.screen().availableGeometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )
    
    def _setup_ui(self):
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)
        
        # Main container with rounded corners
        self.container = QFrame(central)
        self.container.setObjectName("mainContainer")
        self.container.setStyleSheet("""
            #mainContainer {
                background-color: #0f0f14;
                border: 1px solid #333;
                border-radius: 15px;
            }
        """)
        
        # Layout for container
        container_layout = QVBoxLayout(central)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.container)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(25, 20, 25, 25)
        layout.setSpacing(0)
        
        # Header
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        
        title_section = QVBoxLayout()
        title_section.setSpacing(0)
        
        title = QLabel("ZecNode")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet("color: #f4b728; border: none; background: transparent;")
        title_section.addWidget(title)
        
        version_label = QLabel(f"v{VERSION}")
        version_label.setStyleSheet("color: #555; font-size: 10px; border: none; background: transparent;")
        title_section.addWidget(version_label)
        
        header.addLayout(title_section)
        
        header.addSpacing(20)
        
        # Price section
        price_section = QVBoxLayout()
        price_section.setSpacing(0)
        
        self.price_label = QLabel("$--")
        self.price_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.price_label.setStyleSheet("color: #e8e8e8; border: none; background: transparent;")
        price_section.addWidget(self.price_label)
        
        self.change_label = QLabel("--%")
        self.change_label.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
        price_section.addWidget(self.change_label)
        
        header.addLayout(price_section)
        
        header.addStretch()
        
        self.status_dot = StatusDot()
        header.addWidget(self.status_dot)
        
        header.addSpacing(8)
        
        self.status_text = QLabel("Checking...")
        self.status_text.setStyleSheet("color: #888; border: none; background: transparent;")
        header.addWidget(self.status_text)
        
        layout.addLayout(header)
        layout.addSpacing(30)
        
        # Stats grid
        stats_row1 = QHBoxLayout()
        stats_row1.setSpacing(12)
        
        self.peers_card = StatCard("Peers")
        stats_row1.addWidget(self.peers_card)
        
        self.uptime_card = StatCard("Uptime")
        stats_row1.addWidget(self.uptime_card)
        
        layout.addLayout(stats_row1)
        layout.addSpacing(12)
        
        stats_row2 = QHBoxLayout()
        stats_row2.setSpacing(12)
        
        self.ssd_card = StatCard("SSD Used")
        stats_row2.addWidget(self.ssd_card)
        
        self.sd_card = StatCard("SD Card Used")
        stats_row2.addWidget(self.sd_card)
        
        layout.addLayout(stats_row2)
        layout.addSpacing(20)
        
        # Sync Progress Bar
        sync_container = QWidget()
        sync_container.setObjectName("syncContainer")
        sync_container.setStyleSheet("""
            #syncContainer {
                background-color: #1e1e28;
                border: 1px solid #2a2a35;
                border-radius: 12px;
            }
        """)
        sync_layout = QVBoxLayout(sync_container)
        sync_layout.setContentsMargins(15, 12, 15, 12)
        sync_layout.setSpacing(8)
        
        # Sync header row
        sync_header = QHBoxLayout()
        sync_label = QLabel("Sync Progress")
        sync_label.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
        sync_header.addWidget(sync_label)
        sync_header.addStretch()
        self.sync_percent_label = QLabel("0%")
        self.sync_percent_label.setStyleSheet("color: #fff; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        sync_header.addWidget(self.sync_percent_label)
        sync_layout.addLayout(sync_header)
        
        # Progress bar
        self.sync_progress = QProgressBar()
        self.sync_progress.setFixedHeight(16)
        self.sync_progress.setRange(0, 100)
        self.sync_progress.setValue(0)
        self.sync_progress.setTextVisible(False)
        self.sync_progress.setStyleSheet("""
            QProgressBar {
                background-color: #12121a;
                border: none;
                border-radius: 8px;
            }
            QProgressBar::chunk {
                border-radius: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f4b728, stop:1 #1e1e28);
            }
        """)
        sync_layout.addWidget(self.sync_progress)
        
        # Height info
        self.sync_height_label = QLabel("Block 0 / 0")
        self.sync_height_label.setStyleSheet("color: #666; font-size: 10px; border: none; background: transparent;")
        self.sync_height_label.setAlignment(Qt.AlignCenter)
        sync_layout.addWidget(self.sync_height_label)
        
        layout.addWidget(sync_container)
        
        layout.addSpacing(15)
        
        # Lightwalletd Card
        lwd_container = QWidget()
        lwd_container.setObjectName("lwdContainer")
        lwd_container.setStyleSheet("""
            #lwdContainer {
                background-color: #1a1a24;
                border: 1px solid #2a2a35;
                border-radius: 12px;
            }
        """)
        lwd_layout = QVBoxLayout(lwd_container)
        lwd_layout.setContentsMargins(15, 12, 15, 12)
        lwd_layout.setSpacing(8)
        
        # Top row: Title and Toggle
        lwd_top = QHBoxLayout()
        lwd_title = QLabel("Lightwalletd")
        lwd_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lwd_title.setStyleSheet("color: #e8e8e8; border: none; background: transparent;")
        lwd_top.addWidget(lwd_title)
        
        # Info icon with tooltip
        lwd_info = QLabel("ⓘ")
        lwd_info.setStyleSheet("""
            QLabel {
                color: #888;
                font-size: 16px;
                border: none;
                background: transparent;
            }
            QToolTip {
                background-color: #1a1a24;
                color: #ffffff;
                border: 2px solid #4ade80;
                padding: 12px;
                border-radius: 8px;
                font-size: 13px;
            }
        """)
        lwd_info.setToolTip(
            "Lightwalletd lets mobile wallets (like Zashi and Ywallet) "
            "connect to YOUR node instead of public servers.\n\n"
            "• More privacy - your transactions stay local\n"
            "• More decentralization - reduces reliance on third parties\n"
            "• Share with friends and family for private wallet access\n\n"
            "Requires Zebra to be fully synced."
        )
        lwd_top.addWidget(lwd_info)
        
        lwd_top.addStretch()
        
        # Toggle switch
        self.lwd_toggle = QPushButton("OFF")
        self.lwd_toggle.setCheckable(True)
        self.lwd_toggle.setFixedSize(90, 34)
        self.lwd_toggle.setStyleSheet("""
            QPushButton {
                background-color: #444;
                border: 2px solid #555;
                border-radius: 17px;
                color: white;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 10px;
            }
            QPushButton:checked {
                background-color: #4ade80;
                border-color: #4ade80;
                color: black;
            }
        """)
        self.lwd_toggle.clicked.connect(self._toggle_lightwalletd)
        lwd_top.addWidget(self.lwd_toggle)
        lwd_layout.addLayout(lwd_top)
        
        # Status row
        lwd_status_row = QHBoxLayout()
        status_label = QLabel("Status:")
        status_label.setStyleSheet("color: #888; font-size: 12px; border: none; background: transparent;")
        lwd_status_row.addWidget(status_label)
        
        self.lwd_status = QLabel("Off")
        self.lwd_status.setStyleSheet("color: #888; font-size: 12px; border: none; background: transparent;")
        lwd_status_row.addWidget(self.lwd_status)
        lwd_status_row.addStretch()
        lwd_layout.addLayout(lwd_status_row)
        
        # URL row (hidden when off)
        self.lwd_url_row = QWidget()
        self.lwd_url_row.setStyleSheet("background: transparent;")
        lwd_url_layout = QHBoxLayout(self.lwd_url_row)
        lwd_url_layout.setContentsMargins(0, 0, 0, 0)
        lwd_url_layout.setSpacing(10)
        
        self.lwd_url = QLabel("grpc://192.168.1.100:9067")
        self.lwd_url.setStyleSheet("color: #4ade80; font-size: 12px; font-family: monospace; border: none; background: transparent;")
        lwd_url_layout.addWidget(self.lwd_url)
        lwd_url_layout.addStretch()
        
        self.lwd_copy_btn = QPushButton("Copy")
        self.lwd_copy_btn.setFixedSize(90, 34)
        self.lwd_copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                border: 1px solid #444;
                border-radius: 17px;
                color: white;
                font-size: 12px;
                padding: 4px 10px;
            }
            QPushButton:hover { background-color: #3a3a4a; }
        """)
        self.lwd_copy_btn.clicked.connect(self._copy_lwd_url)
        lwd_url_layout.addWidget(self.lwd_copy_btn)
        
        self.lwd_url_row.setVisible(False)
        lwd_layout.addWidget(self.lwd_url_row)
        
        layout.addWidget(lwd_container)
        
        layout.addStretch()
        
        # Circular icon buttons - centered
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        
        # Stop/Start button
        self.stop_btn = QPushButton("⏻")
        self.stop_btn.setMinimumSize(50, 50)
        self.stop_btn.setMaximumSize(50, 50)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                border: none;
                border-radius: 25px;
                font-size: 20px;
                color: white;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #ef4444;
            }
        """)
        self.stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self.stop_btn)
        
        self.start_btn = QPushButton("⏻")
        self.start_btn.setMinimumSize(50, 50)
        self.start_btn.setMaximumSize(50, 50)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #16a34a;
                border: none;
                border-radius: 25px;
                font-size: 20px;
                color: white;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #22c55e;
            }
        """)
        self.start_btn.clicked.connect(self._start)
        self.start_btn.setVisible(False)
        btn_row.addWidget(self.start_btn)
        
        btn_row.addSpacing(30)
        
        # Restart button - red symbol
        self.restart_btn = QPushButton("↻")
        self.restart_btn.setMinimumSize(50, 50)
        self.restart_btn.setMaximumSize(50, 50)
        self.restart_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e1e28;
                border: 2px solid #444;
                border-radius: 25px;
                font-size: 22px;
                color: #ef4444;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #28283a;
                border-color: #f4b728;
            }
            QPushButton:disabled {
                color: #555;
                border-color: #222;
            }
        """)
        self.restart_btn.clicked.connect(self._restart)
        btn_row.addWidget(self.restart_btn)
        
        btn_row.addSpacing(30)
        
        # Logs button - text instead of emoji
        logs_btn = QPushButton("LOGS")
        logs_btn.setMinimumSize(50, 50)
        logs_btn.setMaximumSize(50, 50)
        logs_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e1e28;
                border: 2px solid #444;
                border-radius: 25px;
                font-size: 10px;
                font-weight: bold;
                color: #4ade80;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #28283a;
                border-color: #f4b728;
            }
        """)
        logs_btn.clicked.connect(self._show_logs)
        btn_row.addWidget(logs_btn)
        
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
    
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self._update_tray_icon("stopped")  # Initial state
        
        menu = QMenu()
        
        self.tray_stop = QAction("Stop Node", self)
        self.tray_stop.triggered.connect(self._stop)
        menu.addAction(self.tray_stop)
        
        self.tray_start = QAction("Start Node", self)
        self.tray_start.triggered.connect(self._start)
        self.tray_start.setVisible(False)
        menu.addAction(self.tray_start)
        
        menu.addSeparator()
        
        update_zecnode = QAction("Update ZecNode", self)
        update_zecnode.triggered.connect(self._update_zecnode)
        menu.addAction(update_zecnode)
        
        self.tray_update_zebra = QAction("Update Zebra", self)
        self.tray_update_zebra.triggered.connect(self._update_zebra)
        menu.addAction(self.tray_update_zebra)
        
        menu.addSeparator()
        
        self.tray_toggle_dashboard = QAction("Hide Dashboard", self)
        self.tray_toggle_dashboard.triggered.connect(self._toggle_dashboard_from_menu)
        menu.addAction(self.tray_toggle_dashboard)
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        
        self.tray.setContextMenu(menu)
        self.tray.show()
    
    def _toggle_dashboard_from_menu(self):
        """Toggle dashboard and update menu text"""
        if self.isVisible():
            self.setVisible(False)
            self.tray_toggle_dashboard.setText("Show Dashboard")
        else:
            self.setVisible(True)
            self.showNormal()
            self.raise_()
            self.tray_toggle_dashboard.setText("Hide Dashboard")
    
    def _show_dashboard(self):
        """Show and bring dashboard to front"""
        self.setVisible(True)
        self.showNormal()
        self.raise_()
    
    def _update_tray_icon(self, state: str):
        """Update tray icon - state can be 'running', 'stopped', or 'no_internet'"""
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        if state == "running":
            color = "#4ade80"  # Green
            tooltip = "ZecNode - Running"
        elif state == "no_internet":
            color = "#f4b728"  # Yellow
            tooltip = "ZecNode - No Internet"
        else:
            color = "#ef4444"  # Red
            tooltip = "ZecNode - Stopped"
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        self.tray.setIcon(QIcon(pm))
        self.tray.setToolTip(tooltip)
    
    def _start_refresh(self):
        """Start a background refresh - doesn't block UI"""
        # Exit immediately if closing
        if self._closing:
            return
        
        # Don't refresh if window is hidden - no point updating invisible UI
        if not self.isVisible():
            return
        
        # Don't refresh while an action is in progress
        if self._action_in_progress:
            return
        
        # Don't start new refresh if one is already running
        if self.refresh_thread is not None and self.refresh_thread.isRunning():
            return
        
        # Thread pool limit - if too many threads, force cleanup first
        import threading
        active_threads = threading.active_count()
        if active_threads > 100:
            print(f"Thread limit reached ({active_threads}), forcing cleanup...")
            self._cleanup_threads()
        
        # Clean up old thread
        if self.refresh_thread is not None:
            try:
                self.refresh_thread.finished.disconnect()
            except:
                pass
        
        # Start background refresh
        self.refresh_thread = RefreshThread(self.node_manager)
        self.refresh_thread.finished.connect(self._on_refresh_done)
        self.refresh_thread.start()
    
    def _cleanup_threads(self):
        """Force garbage collection to clean up zombie threads"""
        import gc
        import threading
        before = threading.active_count()
        gc.collect()
        after = threading.active_count()
        print(f"Thread cleanup: {before} -> {after} threads")
    
    def _on_refresh_done(self, status, has_internet, ssd, sd):
        """Handle refresh results from background thread"""
        # Exit if closing
        if self._closing:
            return
        
        # Status - check internet first, then running state
        if status.running and not has_internet:
            # Node is running but no internet
            self.status_dot.set_state(StatusDot.STATE_NO_INTERNET)
            self.status_text.setText("No Internet")
            self.status_text.setStyleSheet("color: #f4b728; border: none; background: transparent;")
            self._update_tray_icon("no_internet")
            # Freeze all stats when offline - show dashes
            self.peers_card.set_value("--")
            self.uptime_card.set_value("--:--:--")
            return
        elif status.running:
            # Node is running with internet
            self.status_dot.set_state(StatusDot.STATE_RUNNING)
            self.status_text.setText("Running")
            self.status_text.setStyleSheet("color: #4ade80; border: none; background: transparent;")
            self._update_tray_icon("running")
        else:
            # Node is stopped
            self.status_dot.set_state(StatusDot.STATE_STOPPED)
            self.status_text.setText("Stopped")
            self.status_text.setStyleSheet("color: #ef4444; border: none; background: transparent;")
            self._update_tray_icon("stopped")
        
        # Stats (only updated when online)
        self.peers_card.set_value(str(status.peer_count))
        self.uptime_card.set_value(status.uptime)
        
        # Disk usage
        self.ssd_card.set_value(ssd.split("/")[0].strip() if "/" in ssd else ssd)
        self.sd_card.set_value(sd.split("/")[0].strip() if "/" in sd else sd)
        
        # Sync progress
        sync_pct = min(status.sync_percent, 100.0)
        # Show at least 1% on the bar if there's any progress
        bar_value = int(sync_pct) if sync_pct >= 1.0 else (1 if sync_pct > 0 else 0)
        self.sync_progress.setValue(bar_value)
        self.sync_progress.repaint()
        self.sync_percent_label.setText(f"{sync_pct:.1f}%")
        
        # Format block height with commas
        current = f"{status.current_height:,}" if status.current_height else "0"
        
        if sync_pct >= 99.9:
            self.sync_height_label.setText(f"✓ Synced • Block {current}")
            self.sync_height_label.setStyleSheet("color: #4ade80; font-size: 10px; border: none; background: transparent;")
        else:
            self.sync_height_label.setText(f"Block {current}")
            self.sync_height_label.setStyleSheet("color: #888; font-size: 10px; border: none; background: transparent;")
        
        # Buttons
        self.stop_btn.setVisible(status.running)
        self.start_btn.setVisible(not status.running)
        self.restart_btn.setEnabled(status.running)
        
        self.tray_stop.setVisible(status.running)
        self.tray_start.setVisible(not status.running)
        self.tray_update_zebra.setEnabled(not status.running)
        
        # Lightwalletd status
        self._update_lightwalletd_status(status)
        
        # Force UI to repaint
        self.update()
        QApplication.processEvents()
    
    def _update_lightwalletd_status(self, zebra_status):
        """Update lightwalletd UI based on current state"""
        lwd_running = self.node_manager.is_lightwalletd_running()
        lwd_enabled = self.config.get("lightwalletd_enabled", False)
        is_synced = zebra_status.running and zebra_status.sync_percent >= 99.9
        
        # Auto-start if enabled and Zebra is synced
        if lwd_enabled and is_synced and not lwd_running:
            success, _ = self.node_manager.start_lightwalletd()
            lwd_running = success
        
        # Auto-stop if Zebra stops
        if lwd_running and not zebra_status.running:
            self.node_manager.stop_lightwalletd()
            lwd_running = False
        
        # Update UI
        if lwd_running:
            self.lwd_toggle.setChecked(True)
            self.lwd_toggle.setText("ON")
            self.lwd_status.setText("Running")
            self.lwd_status.setStyleSheet("color: #4ade80; font-size: 12px; border: none; background: transparent;")
            self.lwd_url.setText(self.node_manager.get_lightwalletd_url())
            self.lwd_url_row.setVisible(True)
            self.lwd_toggle.setEnabled(True)
        elif not zebra_status.running:
            self.lwd_toggle.setChecked(False)
            self.lwd_toggle.setText("OFF")
            self.lwd_status.setText("Node stopped")
            self.lwd_status.setStyleSheet("color: #888; font-size: 12px; border: none; background: transparent;")
            self.lwd_url_row.setVisible(False)
            self.lwd_toggle.setEnabled(False)
        elif zebra_status.sync_percent < 99.9:
            self.lwd_toggle.setChecked(False)
            self.lwd_toggle.setText("OFF")
            self.lwd_status.setText(f"Syncing ({zebra_status.sync_percent:.1f}%)")
            self.lwd_status.setStyleSheet("color: #888; font-size: 12px; border: none; background: transparent;")
            self.lwd_url_row.setVisible(False)
            self.lwd_toggle.setEnabled(False)
        else:
            # Zebra synced but lwd not running
            self.lwd_toggle.setChecked(False)
            self.lwd_toggle.setText("OFF")
            self.lwd_status.setText("Ready")
            self.lwd_status.setStyleSheet("color: #888; font-size: 12px; border: none; background: transparent;")
            self.lwd_url_row.setVisible(False)
            self.lwd_toggle.setEnabled(True)
    
    def _stop(self):
        self._action_in_progress = True
        self.status_text.setText("Stopping...")
        self.status_text.setStyleSheet("color: #f4b728;")
        self.stop_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
        self._run_action("stop")
    
    def _start(self):
        self._action_in_progress = True
        self.status_text.setText("Starting...")
        self.status_text.setStyleSheet("color: #f4b728;")
        self.start_btn.setEnabled(False)
        self._run_action("start")
    
    def _restart(self):
        self._action_in_progress = True
        self.status_text.setText("Restarting...")
        self.status_text.setStyleSheet("color: #f4b728;")
        self.restart_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self._run_action("restart")
    
    def _run_action(self, action):
        self.action_thread = NodeActionThread(action, self.node_manager)
        self.action_thread.finished.connect(self._on_action_done)
        self.action_thread.start()
    
    def _on_action_done(self, ok, msg):
        # Clear action flag
        self._action_in_progress = False
        
        # Re-enable buttons
        self.stop_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.restart_btn.setEnabled(True)
        
        # Clean up thread
        if hasattr(self, 'action_thread'):
            self.action_thread.deleteLater()
            self.action_thread = None
        
        if not ok:
            QMessageBox.warning(self, "Error", msg)
        self._start_refresh()
    
    def _fetch_price(self):
        """Start background price fetch"""
        if self._closing:
            return
            
        if self.price_thread is not None and self.price_thread.isRunning():
            return
        
        # Clean up old thread
        if self.price_thread is not None:
            try:
                self.price_thread.finished.disconnect()
            except:
                pass
        
        self.price_thread = PriceThread()
        self.price_thread.finished.connect(self._on_price_done)
        self.price_thread.start()
    
    def _on_price_done(self, price, change):
        """Update price display"""
        if self._closing:
            return
        
        # Only update if we got valid data - keep old value on failure
        if price is not None:
            self.price_label.setText(f"${price:,.2f}")
            
            if change is not None:
                if change >= 0:
                    self.change_label.setText(f"▲ {change:.2f}%")
                    self.change_label.setStyleSheet("color: #4ade80; font-size: 11px; border: none; background: transparent;")
                else:
                    self.change_label.setText(f"▼ {abs(change):.2f}%")
                    self.change_label.setStyleSheet("color: #ef4444; font-size: 11px; border: none; background: transparent;")
    
    def _update_zecnode(self):
        """Update ZecNode from GitHub"""
        dialog = ConfirmDialog(
            self, 
            "Update ZecNode",
            "Download and install the latest version?\n\nThe app will restart after updating."
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        
        self.update_dialog = UpdateDialog(self, "Updating ZecNode...")
        self.update_dialog.show()
        
        self.update_thread = UpdateThread("zecnode")
        self.update_thread.finished.connect(self._on_update_done)
        self.update_thread.start()
    
    def _update_zebra(self):
        """Update Zebra to latest version"""
        dialog = ConfirmDialog(
            self,
            "Update Zebra", 
            "Download and install the latest version?\n\nWarning: Major updates may require a full resync of the blockchain."
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        
        self.update_dialog = UpdateDialog(self, "Updating Zebra...")
        self.update_dialog.show()
        
        data_path = self.config.get_data_path() if hasattr(self.config, 'get_data_path') else "/mnt/zcash"
        self.update_thread = UpdateThread("zebra", data_path)
        self.update_thread.finished.connect(self._on_update_done)
        self.update_thread.start()
    
    def _on_update_done(self, success, message):
        """Handle update completion"""
        if hasattr(self, 'update_dialog'):
            self.update_dialog.close()
        
        if success:
            if message == "RESTART_ZECNODE":
                # Auto-restart ZecNode
                import subprocess
                import sys
                home = os.path.expanduser("~")
                main_py = os.path.join(home, "zecnode", "main.py")
                self.tray.hide()
                QApplication.processEvents()
                subprocess.Popen([sys.executable, main_py], cwd=os.path.join(home, "zecnode"))
                os._exit(0)
            else:
                dialog = MessageDialog(self, "Update Complete", message, is_error=False)
                dialog.exec_()
        else:
            dialog = MessageDialog(self, "Update Failed", message, is_error=True)
            dialog.exec_()
        
        self._start_refresh()
    
    def _toggle_lightwalletd(self):
        """Toggle lightwalletd on/off"""
        if self.lwd_toggle.isChecked():
            # Check if Zebra is synced
            status = self.node_manager.get_status()
            if not status.running:
                self.lwd_toggle.setChecked(False)
                self.lwd_status.setText("Requires running node")
                self.lwd_status.setStyleSheet("color: #f59e0b; font-size: 12px; border: none; background: transparent;")
                return
            
            if status.sync_percent < 100:
                self.lwd_toggle.setChecked(False)
                self.lwd_status.setText(f"Requires synced node ({status.sync_percent:.1f}%)")
                self.lwd_status.setStyleSheet("color: #f59e0b; font-size: 12px; border: none; background: transparent;")
                return
            
            # Start lightwalletd
            self.lwd_toggle.setText("...")
            self.lwd_toggle.setEnabled(False)
            self.lwd_status.setText("Starting...")
            self.lwd_status.setStyleSheet("color: #f4b728; font-size: 12px; border: none; background: transparent;")
            QApplication.processEvents()
            
            success, msg = self.node_manager.start_lightwalletd()
            
            if success:
                self.lwd_toggle.setText("ON")
                self.lwd_status.setText("Running")
                self.lwd_status.setStyleSheet("color: #4ade80; font-size: 12px; border: none; background: transparent;")
                self.lwd_url.setText(self.node_manager.get_lightwalletd_url())
                self.lwd_url_row.setVisible(True)
                self.config.set("lightwalletd_enabled", True)
            else:
                self.lwd_toggle.setChecked(False)
                self.lwd_toggle.setText("OFF")
                self.lwd_status.setText(f"Error: {msg}")
                self.lwd_status.setStyleSheet("color: #ef4444; font-size: 12px; border: none; background: transparent;")
            
            self.lwd_toggle.setEnabled(True)
        else:
            # Stop lightwalletd
            self.lwd_toggle.setText("...")
            self.lwd_toggle.setEnabled(False)
            QApplication.processEvents()
            
            self.node_manager.stop_lightwalletd()
            
            self.lwd_toggle.setText("OFF")
            self.lwd_toggle.setEnabled(True)
            self.lwd_status.setText("Off")
            self.lwd_status.setStyleSheet("color: #888; font-size: 12px; border: none; background: transparent;")
            self.lwd_url_row.setVisible(False)
            self.config.set("lightwalletd_enabled", False)
    
    def _copy_lwd_url(self):
        """Copy lightwalletd URL to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.lwd_url.text())
        # Brief visual feedback
        self.lwd_copy_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.lwd_copy_btn.setText("Copy"))
    
    def _show_logs(self):
        dialog = LogsDialog(self, self.node_manager)
        dialog.exec_()
    
    def _quit(self):
        dialog = ConfirmDialog(
            self,
            "Quit ZecNode",
            "The node will keep running in the background.\n\nQuit ZecNode?"
        )
        dialog.yes_btn.setText("Quit")
        if dialog.exec_() == QDialog.Accepted:
            self.tray.hide()
            QApplication.processEvents()
            import os
            os._exit(0)
    
    def closeEvent(self, event):
        # Hide tray and close
        self.tray.hide()
        QApplication.processEvents()
        event.accept()
        import os
        os._exit(0)

ENDOFFILE

echo ""
echo "Launching ZecNode..."
python3 main.py

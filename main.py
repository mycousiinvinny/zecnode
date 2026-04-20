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
from splash import SplashScreen


# Modern dark theme with Zcash branding
STYLESHEET = """
/* Global */
QWidget {
    background-color: #0a0a0e;
    color: #e8e8ec;
    font-family: 'Segoe UI', 'SF Pro Display', 'Ubuntu', sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #0a0a0e;
}

/* Tooltips */
QToolTip {
    background: #141419;
    background-color: #141419;
    color: #e8e8ec;
    border: 1px solid #f4b728;
    padding: 6px 10px;
    font-size: 12px;
    opacity: 255;
}

/* Labels */
QLabel {
    color: #e8e8ec;
    background: transparent;
}

QLabel#title {
    font-size: 28px;
    font-weight: bold;
    color: #f4b728;
}

QLabel#subtitle {
    font-size: 14px;
    color: #8b8b96;
}

QLabel#success {
    color: #22c55e;
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
    color: #0a0a0e;
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
    background-color: #1e1e26;
    color: #50505c;
}

QPushButton#secondary {
    background-color: #1e1e26;
    color: #e8e8ec;
    border: 1px solid #2a2a34;
}

QPushButton#secondary:hover {
    background-color: #2a2a34;
    border-color: #3a3a44;
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
    border-radius: 3px;
    background-color: #1e1e26;
    height: 6px;
    text-align: center;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #f4b728, stop:1 #ffc942);
    border-radius: 3px;
}

/* Combo Box */
QComboBox {
    background-color: #141419;
    border: 1px solid #1c1c24;
    border-radius: 8px;
    padding: 10px 15px;
    min-width: 200px;
    color: #e8e8ec;
}

QComboBox:hover {
    border-color: #f4b728;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox QAbstractItemView {
    background-color: #141419;
    border: 1px solid #1c1c24;
    selection-background-color: #f4b728;
    selection-color: #0a0a0e;
}

/* Line Edit */
QLineEdit {
    background-color: #141419;
    border: 1px solid #1c1c24;
    border-radius: 8px;
    padding: 10px 15px;
    color: #e8e8ec;
}

QLineEdit:focus {
    border-color: #f4b728;
}

/* Text Edit (Logs) */
QTextEdit {
    background-color: #08080c;
    border: 1px solid #1c1c24;
    border-radius: 8px;
    padding: 12px;
    font-family: 'JetBrains Mono', 'Consolas', 'Liberation Mono', monospace;
    font-size: 11px;
    color: #22c55e;
}

/* Scroll Bar */
QScrollBar:vertical {
    background-color: transparent;
    width: 6px;
    border-radius: 3px;
}

QScrollBar::handle:vertical {
    background-color: #2a2a34;
    border-radius: 3px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3a3a44;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* Menu */
QMenu {
    background-color: #141419;
    border: 1px solid #1c1c24;
    border-radius: 8px;
    padding: 5px;
}

QMenu::item {
    padding: 8px 20px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #f4b728;
    color: #0a0a0e;
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

    def present(window):
        """Show the window, with splash before dashboard if it's the dashboard."""
        if not isinstance(window, DashboardWindow):
            window.show()
            return

        try:
            splash = SplashScreen()
        except Exception:
            window.show()
            return

        from PyQt5.QtCore import QTimer

        app._splash_ref = splash  # prevent GC

        shown = {"done": False}
        def show_dashboard():
            if shown["done"]:
                return
            shown["done"] = True
            window.show()

        splash.finished.connect(show_dashboard)
        splash.show()
        app.processEvents()

        if window._first_refresh_emitted:
            splash.request_dismiss()
        else:
            window.first_refresh_done.connect(splash.request_dismiss)

        # Safety net: if splash never finishes, show dashboard anyway.
        QTimer.singleShot(20000, show_dashboard)

    # Check if already installed
    if config.is_installed():
        window = DashboardWindow(config)
    else:
        # Check if we're in the middle of installation (e.g., after reboot)
        phase = config.get_phase()
        
        # Check if we have existing data and just needed dependencies
        has_existing_data = config.get("has_existing_data", False)
        if has_existing_data:
            import shutil
            has_docker = shutil.which("docker") is not None
            has_curl = shutil.which("curl") is not None
            if has_docker and has_curl:
                # Dependencies installed, data exists - go straight to dashboard
                config.set("data_path", "/mnt/zebra-data")
                config.set("install_phase", Config.PHASE_COMPLETE)
                config.set("installed", True)
                config.set("docker_configured", True)
                config.save()
                window = DashboardWindow(config)
                present(window)
                sys.exit(app.exec_())
        
        if phase not in [Config.PHASE_NOT_STARTED, Config.PHASE_COMPLETE]:
            # Resume installation from where we left off
            window = InstallerWizard(config)
        else:
            import shutil
            
            data_path = "/mnt/zebra-data"
            cache_path = f"{data_path}/zebra-cache"
            state_path = f"{data_path}/zebra-state"
            
            # Try to auto-mount SSD if not already mounted
            def try_auto_mount():
                """Try to find and mount an SSD with Zebra data"""
                # Check if already mounted
                if os.path.ismount(data_path):
                    return True
                
                # Look for unmounted drives that might have Zebra data
                try:
                    # Get list of block devices
                    result = subprocess.run(
                        ["lsblk", "-rno", "NAME,TYPE,MOUNTPOINT"],
                        capture_output=True, text=True, timeout=10
                    )
                    
                    for line in result.stdout.strip().split('\n'):
                        parts = line.split()
                        if len(parts) >= 2:
                            name, dtype = parts[0], parts[1]
                            mountpoint = parts[2] if len(parts) > 2 else ""
                            
                            # Skip if not a partition or already mounted
                            if dtype != "part" or mountpoint:
                                continue
                            
                            device = f"/dev/{name}"
                            
                            # Try to mount temporarily and check for Zebra data
                            temp_mount = "/tmp/zebra-check"
                            try:
                                subprocess.run(["sudo", "mkdir", "-p", temp_mount], capture_output=True, timeout=5)
                                mount_result = subprocess.run(
                                    ["sudo", "mount", "-o", "ro", device, temp_mount],
                                    capture_output=True, timeout=10
                                )
                                
                                if mount_result.returncode == 0:
                                    # Check if this drive has Zebra data
                                    has_zebra = os.path.exists(f"{temp_mount}/zebra-cache") and \
                                                len(os.listdir(f"{temp_mount}/zebra-cache")) > 0
                                    
                                    subprocess.run(["sudo", "umount", temp_mount], capture_output=True, timeout=10)
                                    
                                    if has_zebra:
                                        # Found it! Mount properly
                                        subprocess.run(["sudo", "mkdir", "-p", data_path], capture_output=True, timeout=5)
                                        mount_result = subprocess.run(
                                            ["sudo", "mount", device, data_path],
                                            capture_output=True, timeout=10
                                        )
                                        
                                        if mount_result.returncode == 0:
                                            # Add to fstab for persistence
                                            uuid_result = subprocess.run(
                                                ["sudo", "blkid", "-s", "UUID", "-o", "value", device],
                                                capture_output=True, text=True, timeout=5
                                            )
                                            uuid = uuid_result.stdout.strip()
                                            if uuid:
                                                fstab_line = f"UUID={uuid} {data_path} ext4 defaults 0 2\n"
                                                # Check if already in fstab
                                                with open("/etc/fstab", "r") as f:
                                                    if uuid not in f.read():
                                                        subprocess.run(
                                                            ["sudo", "bash", "-c", f"echo '{fstab_line}' >> /etc/fstab"],
                                                            capture_output=True, timeout=5
                                                        )
                                            return True
                            except:
                                subprocess.run(["sudo", "umount", temp_mount], capture_output=True)
                                continue
                except:
                    pass
                
                return False
            
            # Try to auto-mount if needed
            try_auto_mount()
            
            # Check if directories exist and are not empty
            def has_data(path):
                if not os.path.exists(path):
                    return False
                try:
                    contents = os.listdir(path)
                    return len(contents) > 0
                except:
                    return False
            
            # Check if Docker and curl are installed
            has_docker = shutil.which("docker") is not None
            has_curl = shutil.which("curl") is not None
            has_dependencies = has_docker and has_curl
            
            if has_data(cache_path) or has_data(state_path):
                if has_dependencies:
                    # Data exists and dependencies installed - go to dashboard
                    config.set("data_path", data_path)
                    config.set("install_phase", Config.PHASE_COMPLETE)
                    config.set("installed", True)
                    config.set("docker_configured", True)
                    config.save()
                    window = DashboardWindow(config)
                else:
                    # Data exists but missing dependencies - go to installer to install them
                    # Skip format step since data exists
                    config.set("data_path", data_path)
                    config.set("has_existing_data", True)
                    config.save()
                    window = InstallerWizard(config)
            else:
                # No data found - go straight to installer with latest version
                config.set("zebra_version", "latest")
                config.save()
                window = InstallerWizard(config)
    
    present(window)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

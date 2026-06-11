#!/usr/bin/env python3
"""
ZecNode - One-Click Zcash Node Installer
Main entry point with professional styling
"""

import sys
import os
import subprocess
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QObject, QThread, QTimer, pyqtSignal, qInstallMessageHandler
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


def _kill_old_instances():
    """Kill any other running ZecNode instances (but not ourselves)."""
    my_pid = os.getpid()
    try:
        subprocess.run(
            ["bash", "-c",
             f"pgrep -f 'python.*main.py' | grep -v {my_pid} | xargs -r kill -9 2>/dev/null || true"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass


def _try_auto_mount(data_path):
    """Try to find and mount an SSD with Zebra data. Returns True if mounted."""
    # Check if already mounted
    if os.path.ismount(data_path):
        return True

    # Look for unmounted drives that might have Zebra data
    try:
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
                                    # nofail + short device-timeout: a missing/disconnected SSD must
                                    # never drop the Pi into emergency mode at boot (it just skips the mount).
                                    fstab_line = f"UUID={uuid} {data_path} ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2\n"
                                    # Check if already in fstab
                                    with open("/etc/fstab", "r") as f:
                                        if uuid not in f.read():
                                            subprocess.run(
                                                ["sudo", "bash", "-c", f"echo '{fstab_line}' >> /etc/fstab"],
                                                capture_output=True, timeout=5
                                            )
                                return True
                except Exception:
                    subprocess.run(["sudo", "umount", temp_mount], capture_output=True)
                    continue
    except Exception:
        pass

    return False


def _has_data(path):
    """True if the directory exists and is not empty."""
    if not os.path.exists(path):
        return False
    try:
        return len(os.listdir(path)) > 0
    except Exception:
        return False


class StartupWorker(QThread):
    """Runs the blocking startup chores — killing stale instances, auto-mounting
    the SSD, and deciding which window to open — off the UI thread so the splash
    can paint and animate instantly instead of waiting on subprocess + disk I/O.

    Emits ``decided`` with 'dashboard' or 'installer' once routing is resolved.
    The window itself is still built on the main thread (Qt widgets must be).
    """

    status = pyqtSignal(str)
    decided = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        _kill_old_instances()
        # Emitted from the worker thread; receivers must live on the main thread
        # (bound methods of main-thread QObjects) so Qt marshals the call across
        # threads — never connect this to a plain function.
        self.decided.emit(self._decide())

    def _decide(self):
        config = self.config

        # Already installed — straight to the dashboard, no disk probing needed.
        if config.is_installed():
            return "dashboard"

        phase = config.get_phase()

        # Existing data + dependencies already present → promote to a finished install.
        if config.get("has_existing_data", False):
            import shutil
            if shutil.which("docker") and shutil.which("curl"):
                config.set("data_path", "/mnt/zebra-data")
                config.set("install_phase", Config.PHASE_COMPLETE)
                config.set("installed", True)
                config.set("docker_configured", True)
                config.save()
                return "dashboard"

        # Mid-installation (e.g. resuming after a reboot) → continue the wizard.
        if phase not in (Config.PHASE_NOT_STARTED, Config.PHASE_COMPLETE):
            return "installer"

        import shutil
        data_path = "/mnt/zebra-data"
        cache_path = f"{data_path}/zebra-cache"
        state_path = f"{data_path}/zebra-state"

        self.status.emit("Checking storage…")
        _try_auto_mount(data_path)

        has_dependencies = shutil.which("docker") is not None and shutil.which("curl") is not None

        if _has_data(cache_path) or _has_data(state_path):
            if has_dependencies:
                # Data exists and dependencies installed → dashboard.
                config.set("data_path", data_path)
                config.set("install_phase", Config.PHASE_COMPLETE)
                config.set("installed", True)
                config.set("docker_configured", True)
                config.save()
                return "dashboard"
            # Data exists but missing dependencies → installer to install them.
            config.set("data_path", data_path)
            config.set("has_existing_data", True)
            config.save()
            return "installer"

        # No data found → fresh install with the latest version.
        config.set("zebra_version", "latest")
        config.save()
        return "installer"


def main():
    # Silence the harmless, noisy "QPainter::end: Painter not active" warnings
    # that animated custom widgets emit at 60fps when a frame can't paint. They
    # don't affect rendering — just drown the terminal. Everything else passes.
    def _qt_msg_filter(mode, context, message):
        if "QPainter::" in message or "Painter not active" in message:
            return
        sys.stderr.write(message + "\n")
    qInstallMessageHandler(_qt_msg_filter)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("ZecNode")
    app.setOrganizationName("ZecNode")
    app.setDesktopFileName("zecnode")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    config = Config()

    # Show the splash immediately — before any blocking startup work — so the
    # user sees ZecNode within a frame instead of a blank gap while we kill
    # stale instances and probe for the SSD. All of that now runs in a worker.
    splash = None
    try:
        splash = SplashScreen()
        app._splash_ref = splash  # prevent GC
        splash.show()
        app.processEvents()
    except Exception:
        splash = None

    state = {"shown": False}

    def reveal(window):
        if state["shown"]:
            return
        state["shown"] = True
        window.show()

    def on_decided(route):
        window = DashboardWindow(config) if route == "dashboard" else InstallerWizard(config)
        app._window_ref = window  # prevent GC

        if splash is None:
            reveal(window)
            return

        splash.finished.connect(lambda: reveal(window))

        # The dashboard waits for its first status refresh before revealing; the
        # installer has nothing to wait on, so dismiss once the splash minimum
        # display time has elapsed.
        if isinstance(window, DashboardWindow):
            if getattr(window, "_first_refresh_emitted", False):
                splash.request_dismiss()
            else:
                window.first_refresh_done.connect(splash.request_dismiss)
        else:
            splash.request_dismiss()

        # Safety net: never let a stuck splash hide the window forever.
        QTimer.singleShot(20000, lambda: reveal(window))

    # Route the worker's cross-thread signal through a main-thread QObject so the
    # window is built on the GUI thread. Connecting a worker-thread signal to a
    # plain function would run it (and create QWidgets) on the worker thread.
    class _Router(QObject):
        def handle(self, route):
            on_decided(route)

    router = _Router()
    app._startup_router = router  # prevent GC

    worker = StartupWorker(config)
    app._startup_worker = worker  # prevent GC
    if splash is not None:
        worker.status.connect(splash.set_status)
    worker.decided.connect(router.handle)
    worker.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

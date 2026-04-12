"""
ZecNode Dashboard
Professional status display and node controls
"""

import socket
import json
import os
import sys
import signal
import urllib.request
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QSystemTrayIcon,
    QMenu, QAction, QMessageBox, QDialog, QApplication,
    QSpacerItem, QSizePolicy, QFrame, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QRectF, pyqtProperty, QEasingCurve
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QTextCursor, QBrush, QPen

from config import Config, VERSION
from node_manager import NodeManager


class ToggleSwitch(QWidget):
    """Animated sliding toggle switch"""
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._enabled = True
        self._knob_x = 4.0
        self._opacity = 1.0
        self.setFixedSize(52, 28)
        self.setCursor(Qt.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"knob_x")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

    def _get_knob_x(self):
        return self._knob_x

    def _set_knob_x(self, val):
        self._knob_x = val
        self.update()

    knob_x = pyqtProperty(float, _get_knob_x, _set_knob_x)

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        if self._checked == checked:
            return
        self._checked = checked
        end = self.width() - self.height() + 4 if checked else 4.0
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(end)
        self._anim.start()

    def setEnabled(self, enabled):
        self._enabled = enabled
        self._opacity = 1.0 if enabled else 0.4
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self.update()

    def isEnabled(self):
        return self._enabled

    def mousePressEvent(self, event):
        if self._enabled:
            self._checked = not self._checked
            end = self.width() - self.height() + 4 if self._checked else 4.0
            self._anim.stop()
            self._anim.setStartValue(self._knob_x)
            self._anim.setEndValue(end)
            self._anim.start()
            self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._opacity)

        w, h = self.width(), self.height()
        radius = h / 2

        # Track
        if self._checked:
            track_color = QColor("#4ade80")
        else:
            track_color = QColor("#444")
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        # Knob
        knob_size = h - 8
        p.setBrush(QBrush(QColor("white")))
        p.drawEllipse(QRectF(self._knob_x, 4, knob_size, knob_size))

        p.end()


def check_internet(timeout=2) -> bool:
    """Check if internet is available by trying to connect to a reliable host"""
    for host in ("8.8.8.8", "1.1.1.1"):
        try:
            conn = socket.create_connection((host, 53), timeout=timeout)
            conn.close()
            return True
        except OSError:
            continue
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

    def __init__(self, action, node_manager, lwd_enabled=False):
        super().__init__()
        self.action = action
        self.node_manager = node_manager
        self.lwd_enabled = lwd_enabled

    def run(self):
        if self.action == "start":
            ok, msg = self.node_manager.start_node()
            # Auto-start lightwalletd if enabled and node started successfully
            if ok and self.lwd_enabled:
                self.node_manager.start_lightwalletd()
        elif self.action == "stop":
            # Stop lightwalletd first if running
            if self.node_manager.is_lightwalletd_running():
                self.node_manager.stop_lightwalletd()
            ok, msg = self.node_manager.stop_node()
        elif self.action == "restart":
            # Stop lightwalletd before restart, start after if enabled
            lwd_was_running = self.node_manager.is_lightwalletd_running()
            if lwd_was_running:
                self.node_manager.stop_lightwalletd()
            ok, msg = self.node_manager.restart_node()
            if ok and (self.lwd_enabled or lwd_was_running):
                self.node_manager.start_lightwalletd()
        else:
            ok, msg = False, "Unknown action"
        self.finished.emit(ok, msg)


class RefreshThread(QThread):
    """Background thread for fetching node status without blocking UI"""
    finished = pyqtSignal(object, bool, str, str, bool)  # status, has_internet, ssd, sd, lwd_running

    # Cached internet status shared across instances
    _cached_internet = True
    _last_internet_check = 0
    _cached_ssd = "--"
    _cached_sd = "--"
    _last_disk_check = 0

    def __init__(self, node_manager, config=None):
        super().__init__()
        self.node_manager = node_manager
        self.config = config
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        if not self._running:
            return

        # Check internet (only re-check every 60 seconds)
        import time
        now = time.monotonic()
        if now - RefreshThread._last_internet_check >= 60:
            RefreshThread._cached_internet = check_internet()
            RefreshThread._last_internet_check = now
        has_internet = RefreshThread._cached_internet

        if not self._running:
            return

        # Get node status (this is the slow call)
        status = self.node_manager.get_status()

        if not self._running:
            return

        # Get disk usage (only re-check every 60 seconds)
        if now - RefreshThread._last_disk_check >= 60:
            RefreshThread._cached_ssd, RefreshThread._cached_sd = self.node_manager.get_disk_usage()
            RefreshThread._last_disk_check = now
        ssd, sd = RefreshThread._cached_ssd, RefreshThread._cached_sd

        if not self._running:
            return

        # Check lightwalletd status (was previously blocking main thread)
        lwd_running = self.node_manager.is_lightwalletd_running()

        if not self._running:
            return

        self.finished.emit(status, has_internet, ssd, sd, lwd_running)


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
        """Start background log fetch"""
        if hasattr(self, '_log_thread') and self._log_thread is not None and self._log_thread.isRunning():
            return

        class LogThread(QThread):
            finished = pyqtSignal(str)
            def __init__(self, node_manager):
                super().__init__()
                self.node_manager = node_manager
            def run(self):
                logs = self.node_manager.get_logs(300)
                self.finished.emit(logs)

        self._log_thread = LogThread(self.node_manager)
        self._log_thread.finished.connect(self._on_logs_done)
        self._log_thread.start()

    def _on_logs_done(self, logs):
        """Update log display from background thread result"""
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

        # Clean up thread
        if hasattr(self, '_log_thread') and self._log_thread is not None:
            self._log_thread.deleteLater()
            self._log_thread = None
    
    def closeEvent(self, event):
        self.timer.stop()
        self.timer.deleteLater()
        if hasattr(self, '_log_thread') and self._log_thread is not None:
            self._log_thread.deleteLater()
            self._log_thread = None
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
        
        # Create opacity effect once (not per-tick)
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._opacity_effect = QGraphicsOpacityEffect()
        self._opacity_effect.setOpacity(1.0)
        self.logo_label.setGraphicsEffect(self._opacity_effect)

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

        self._opacity_effect.setOpacity(self._opacity)
    
    def set_message(self, message):
        self.message_label.setText(message)
    
    def closeEvent(self, event):
        self.pulse_timer.stop()
        super().closeEvent(event)


class UpdateThread(QThread):
    """Background thread for updates"""
    finished = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, update_type, data_path=None, zebra_version="latest"):
        super().__init__()
        self.update_type = update_type
        self.data_path = data_path
        self.zebra_version = zebra_version
    
    def run(self):
        import subprocess
        import os
        try:
            if self.update_type == "zecnode":
                home = os.path.expanduser("~")
                zecnode_dir = os.path.join(home, "zecnode")

                # Try git pull first (works if installed via git clone)
                git_check = subprocess.run(
                    ["git", "rev-parse", "--git-dir"],
                    cwd=zecnode_dir,
                    capture_output=True, timeout=5
                )

                if git_check.returncode == 0:
                    result = subprocess.run(
                        ["bash", "-c", f"cd {zecnode_dir} && rm -rf __pycache__ && git pull origin main && echo SUCCESS"],
                        capture_output=True, text=True, timeout=120
                    )
                else:
                    # Fallback: download files individually via curl
                    github_raw = "https://raw.githubusercontent.com/mycousiinvinny/zecnode/main"
                    result = subprocess.run(
                        ["bash", "-c", f"""
                            cd {zecnode_dir}
                            rm -rf __pycache__
                            curl -sSL -o main.py "{github_raw}/main.py" && \
                            curl -sSL -o config.py "{github_raw}/config.py" && \
                            curl -sSL -o node_manager.py "{github_raw}/node_manager.py" && \
                            curl -sSL -o installer.py "{github_raw}/installer.py" && \
                            curl -sSL -o dashboard.py "{github_raw}/dashboard.py" && \
                            mkdir -p zecnode-web/static && \
                            curl -sSL -o zecnode-web/server.py "{github_raw}/zecnode-web/server.py" && \
                            curl -sSL -o zecnode-web/config.py "{github_raw}/zecnode-web/config.py" && \
                            curl -sSL -o zecnode-web/node_manager.py "{github_raw}/zecnode-web/node_manager.py" && \
                            curl -sSL -o zecnode-web/crawler.py "{github_raw}/zecnode-web/crawler.py" && \
                            curl -sSL -o zecnode-web/install-web.sh "{github_raw}/zecnode-web/install-web.sh" && \
                            curl -sSL -o zecnode-web/cli-installer.py "{github_raw}/zecnode-web/cli-installer.py" && \
                            curl -sSL -o zecnode-web/static/index.html "{github_raw}/zecnode-web/static/index.html" && \
                            echo "SUCCESS"
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
                    ["docker", "pull", f"zfnd/zebra:{self.zebra_version}"],
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
                    data_path = self.data_path or "/mnt/zebra-data"
                    volume_mounts = [
                        f"{data_path}/zebra-cache:/home/zebra/.cache/zebra",
                        f"{data_path}/zebra-state:/home/zebra/.local/state/zebra"
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
                
                # Ensure zecnode network exists
                subprocess.run(["docker", "network", "create", "zecnode"], capture_output=True)
                
                # Build docker run command with same mounts
                docker_cmd = [
                    "docker", "run", "-d",
                    "--name", "zebra",
                    "--network", "zecnode",
                    "--restart", "unless-stopped",
                    "-e", "ZEBRA_RPC__LISTEN_ADDR=0.0.0.0:8232",
                    "-e", "ZEBRA_RPC__ENABLE_COOKIE_AUTH=false",
                ]
                
                # Add all volume mounts
                for mount in volume_mounts:
                    docker_cmd.extend(["-v", mount])
                
                # Add port mapping
                docker_cmd.extend(["-p", "8233:8233"])
                
                docker_cmd.append(f"zfnd/zebra:{self.zebra_version}")
                
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
        zebra_version = config.get("zebra_version", "latest")
        self.node_manager = NodeManager(config.get_data_path(), zebra_version=zebra_version)
        self._centered = False
        self._drag_pos = None
        self._tray_state = None
        
        self.setWindowTitle("ZecNode")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(600, 550)
        self.resize(600, 550)
        
        self._threads = []
        self._setup_ui()
        self._setup_tray()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._start_refresh)
        self.timer.start(10000)  # 10 seconds
        self._action_in_progress = False
        self._lwd_action_in_progress = False
        self._lwd_auto_action_in_progress = False
        self._closing = False
        self.refresh_thread = None
        self._cached_zebra_version = None
        self._zebra_version_fetched = False
        self._start_refresh()
        
        # Price timer - update every 120 seconds
        self.price_thread = None
        self.price_timer = QTimer()
        self.price_timer.timeout.connect(self._fetch_price)
        self.price_timer.start(120000)
        self._fetch_price()
    
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
        
        self.zebra_version_label = QLabel("Zebra v--")
        self.zebra_version_label.setStyleSheet("color: #555; font-size: 10px; border: none; background: transparent;")
        self.zebra_version_label.setVisible(False)  # Hidden until node confirmed running
        title_section.addWidget(self.zebra_version_label)
        
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
        
        sync_info = QLabel("ⓘ")
        sync_info.setStyleSheet("""
            QLabel {
                color: #555;
                font-size: 11px;
                border: none;
                background-color: transparent;
                padding-left: 4px;
            }
            QLabel:hover {
                color: #f4b728;
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
        sync_info.setToolTip(
            "If sync shows 0%, don't worry — your data is safe.\n\n"
            "After starting or updating, the node needs a moment\n"
            "to verify existing data before syncing resumes.\n\n"
            "Check 'Logs' for block heights to confirm progress."
        )
        sync_header.addWidget(sync_info)
        
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
        lwd_layout.setSpacing(6)

        # Top row: Title + status + info + toggle
        lwd_top = QHBoxLayout()
        lwd_top.setSpacing(6)
        lwd_title = QLabel("Lightwalletd")
        lwd_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lwd_title.setStyleSheet("color: #e8e8e8; border: none; background: transparent;")
        lwd_top.addWidget(lwd_title)

        # Status label (inline next to title)
        self.lwd_status = QLabel("")
        self.lwd_status.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
        lwd_top.addWidget(self.lwd_status)

        # Info icon with tooltip
        lwd_info = QLabel("ⓘ")
        lwd_info.setStyleSheet("""
            QLabel {
                color: #555;
                font-size: 11px;
                border: none;
                background-color: transparent;
            }
            QLabel:hover {
                color: #f4b728;
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
        self.lwd_toggle = ToggleSwitch()
        self.lwd_toggle.toggled.connect(self._toggle_lightwalletd_from_toggle)
        lwd_top.addWidget(self.lwd_toggle)
        lwd_layout.addLayout(lwd_top)

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
        
        reset_action = QAction("Reset ZecNode", self)
        reset_action.triggered.connect(self._reset_zecnode)
        menu.addAction(reset_action)
        
        self.tray_ip = QAction("IP: fetching...", self)
        self.tray_ip.triggered.connect(self._copy_ip_from_tray)
        menu.addAction(self.tray_ip)
        self._update_tray_ip()

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
    
    def _update_tray_ip(self):
        """Fetch local IP and update tray menu item"""
        def get_ip():
            return self.node_manager.get_local_ip()

        def on_ip(ip):
            self._local_ip = ip
            self.tray_ip.setText(f"IP: {ip}  (click to copy)")

        self._run_in_thread(get_ip, on_ip)

    def _copy_ip_from_tray(self):
        """Copy local IP to clipboard"""
        ip = getattr(self, '_local_ip', None)
        if ip:
            QApplication.clipboard().setText(ip)
            self.tray_ip.setText(f"IP: {ip}  ✓ Copied!")
            QTimer.singleShot(2000, lambda: self.tray_ip.setText(f"IP: {ip}  (click to copy)"))

    def _show_dashboard(self):
        """Show and bring dashboard to front"""
        self.setVisible(True)
        self.showNormal()
        self.raise_()
    
    def _update_tray_icon(self, state: str):
        """Update tray icon - state can be 'running', 'stopped', or 'no_internet'"""
        if state == self._tray_state:
            return
        self._tray_state = state
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
        try:
            if self.refresh_thread is not None and self.refresh_thread.isRunning():
                return
        except RuntimeError:
            self.refresh_thread = None

        # Clean up old thread - just drop the reference, don't deleteLater
        if self.refresh_thread is not None:
            try:
                self.refresh_thread.finished.disconnect()
            except:
                pass
            self.refresh_thread = None

        # Start background refresh
        self.refresh_thread = RefreshThread(self.node_manager, self.config)
        self.refresh_thread.finished.connect(self._on_refresh_done)
        self.refresh_thread.start()
    
    def _remove_thread(self, thread):
        """Remove a finished thread from the tracking list"""
        try:
            self._threads.remove(thread)
        except ValueError:
            pass
    
    def _on_refresh_done(self, status, has_internet, ssd, sd, lwd_running):
        """Handle refresh results from background thread"""
        # Exit if closing
        if self._closing:
            return

        # Skip UI update if an action is in progress (stop/start/restart)
        if self._action_in_progress:
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
            # Fetch Zebra version once (only on first detection of running node)
            if not self._zebra_version_fetched:
                self._fetch_zebra_version()
            if self._cached_zebra_version:
                self.zebra_version_label.setText(f"Zebra v{self._cached_zebra_version}")
            self.zebra_version_label.setVisible(True)
        else:
            # Node is stopped
            self.status_dot.set_state(StatusDot.STATE_STOPPED)
            self.status_text.setText("Stopped")
            self.status_text.setStyleSheet("color: #ef4444; border: none; background: transparent;")
            self._update_tray_icon("stopped")
            self.zebra_version_label.setVisible(False)
            # Reset so version is re-fetched when node starts again
            self._zebra_version_fetched = False

        # Stats (only updated when online)
        self.peers_card.set_value(str(status.peer_count))
        self.uptime_card.set_value(status.uptime)

        # Disk usage
        self.ssd_card.set_value(ssd.split("/")[0].strip() if "/" in ssd else ssd)
        self.sd_card.set_value(sd.split("/")[0].strip() if "/" in sd else sd)

        # Sync progress — use cached values if node hasn't reported yet
        sync_pct = min(status.sync_percent, 100.0)
        current_height = status.current_height

        if sync_pct > 0 or current_height > 0:
            # Real data from logs — cache it
            self.config.set("cached_sync_percent", sync_pct)
            self.config.set("cached_height", current_height)
        elif status.running:
            # Node running but no data yet — use cached values
            sync_pct = self.config.get("cached_sync_percent", 0.0)
            current_height = self.config.get("cached_height", 0)

        # Show at least 1% on the bar if there's any progress
        bar_value = int(sync_pct) if sync_pct >= 1.0 else (1 if sync_pct > 0 else 0)
        self.sync_progress.setValue(bar_value)
        self.sync_percent_label.setText(f"{sync_pct:.1f}%")

        # Format block height with commas
        current = f"{current_height:,}" if current_height else "0"

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

        # Lightwalletd status (using pre-fetched lwd_running, no blocking calls)
        self._update_lightwalletd_ui(status, lwd_running)
    
    def _update_lightwalletd_ui(self, zebra_status, lwd_running):
        """Update lightwalletd UI based on pre-fetched state (no blocking calls)"""
        lwd_enabled = self.config.get("lightwalletd_enabled", False)
        is_synced = zebra_status.running and zebra_status.sync_percent >= 99.9

        # Auto-start/stop in background thread to avoid blocking UI
        # Only one auto action at a time to prevent thread spam
        if not self._lwd_auto_action_in_progress:
            if lwd_enabled and is_synced and not lwd_running:
                self._lwd_auto_action_in_progress = True
                self._run_in_thread(
                    lambda: self.node_manager.start_lightwalletd(),
                    lambda result: setattr(self, '_lwd_auto_action_in_progress', False)
                )
            elif lwd_running and not zebra_status.running:
                self._lwd_auto_action_in_progress = True
                self._run_in_thread(
                    lambda: self.node_manager.stop_lightwalletd(),
                    lambda result: setattr(self, '_lwd_auto_action_in_progress', False)
                )

        # Skip lwd UI update if action in progress
        if self._lwd_action_in_progress:
            return

        # Update UI
        if lwd_running:
            self.lwd_toggle.setChecked(True)
            self.lwd_status.setText("Running")
            self.lwd_status.setStyleSheet("color: #4ade80; font-size: 11px; border: none; background: transparent;")
            self.lwd_toggle.setEnabled(True)
        elif not zebra_status.running:
            self.lwd_toggle.setChecked(False)
            self.lwd_status.setText("Node stopped")
            self.lwd_status.setStyleSheet("color: #ef4444; font-size: 11px; border: none; background: transparent;")
            self.lwd_toggle.setEnabled(False)
        elif zebra_status.sync_percent < 99.9:
            self.lwd_toggle.setChecked(False)
            self.lwd_status.setText(f"Syncing ({zebra_status.sync_percent:.1f}%)")
            self.lwd_status.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
            self.lwd_toggle.setEnabled(False)
        else:
            # Zebra synced but lwd not running
            self.lwd_toggle.setChecked(False)
            self.lwd_status.setText("")
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
        # Wait for any previous action thread to finish before starting a new one
        if hasattr(self, 'action_thread') and self.action_thread is not None:
            try:
                if self.action_thread.isRunning():
                    return  # Don't stack actions
            except RuntimeError:
                pass
        lwd_enabled = self.config.get("lightwalletd_enabled", False)
        self.action_thread = NodeActionThread(action, self.node_manager, lwd_enabled)
        self.action_thread.finished.connect(self._on_action_done)
        self.action_thread.start()

    def _on_action_done(self, ok, msg):
        # Clear action flag
        self._action_in_progress = False

        # Re-enable buttons
        self.stop_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.restart_btn.setEnabled(True)

        # Let the thread be cleaned up by _cleanup_threads (don't deleteLater here
        # since we may still be inside the thread's signal emission)

        if not ok:
            QMessageBox.warning(self, "Error", msg)
        self._start_refresh()
    
    def _fetch_zebra_version(self):
        """Fetch Zebra version once in a background thread"""
        self._zebra_version_fetched = True

        def get_version():
            return self.node_manager.get_zebra_version(self.config)

        def on_version_done(version):
            if version and version != "--":
                self._cached_zebra_version = version
                self.zebra_version_label.setText(f"Zebra v{version}")

        self._run_in_thread(get_version, on_version_done)

    def _fetch_price(self):
        """Start background price fetch"""
        if self._closing:
            return
            
        try:
            if self.price_thread is not None and self.price_thread.isRunning():
                return
        except RuntimeError:
            self.price_thread = None

        # Clean up old thread - just drop the reference
        if self.price_thread is not None:
            try:
                self.price_thread.finished.disconnect()
            except:
                pass
            self.price_thread = None

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
        zebra_version = "latest"
        self.update_thread = UpdateThread("zebra", data_path, zebra_version)
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
                # Zebra version will be updated on next refresh cycle
        else:
            dialog = MessageDialog(self, "Update Failed", message, is_error=True)
            dialog.exec_()
        
        self._start_refresh()
    
    def _toggle_lightwalletd_from_toggle(self, checked):
        """Called by ToggleSwitch signal - checked is the new state"""
        self._toggle_lightwalletd(checked)

    def _toggle_lightwalletd(self, checked=None):
        """Toggle lightwalletd on/off"""
        if checked is None:
            checked = self.lwd_toggle.isChecked()
        if checked:
            # Start lightwalletd in background thread
            self._lwd_action_in_progress = True
            self.lwd_toggle.setEnabled(False)
            self.lwd_status.setText("Starting...")
            self.lwd_status.setStyleSheet("color: #f4b728; font-size: 11px; border: none; background: transparent;")

            def start_lwd():
                success, msg = self.node_manager.start_lightwalletd()
                return success, msg

            def on_start_done(result):
                self._lwd_action_in_progress = False
                success, msg = result
                if success:
                    self.lwd_status.setText("Running")
                    self.lwd_status.setStyleSheet("color: #4ade80; font-size: 11px; border: none; background: transparent;")
                    self.config.set("lightwalletd_enabled", True)
                else:
                    self.lwd_toggle.setChecked(False)
                    self.lwd_status.setText(f"Error: {msg}")
                    self.lwd_status.setStyleSheet("color: #ef4444; font-size: 11px; border: none; background: transparent;")
                self.lwd_toggle.setEnabled(True)

            self._run_in_thread(start_lwd, on_start_done)
        else:
            # Stop lightwalletd in background thread
            self._lwd_action_in_progress = True
            self.lwd_toggle.setEnabled(False)
            self.lwd_status.setText("Stopping...")
            self.lwd_status.setStyleSheet("color: #f4b728; font-size: 11px; border: none; background: transparent;")

            def stop_lwd():
                self.node_manager.stop_lightwalletd()
                return True

            def on_stop_done(result):
                self._lwd_action_in_progress = False
                self.lwd_toggle.setEnabled(True)
                self.lwd_status.setText("")
                self.config.set("lightwalletd_enabled", False)

            self._run_in_thread(stop_lwd, on_stop_done)
    
    def _run_in_thread(self, func, callback):
        """Run a function in a background thread and call callback with result"""
        class WorkerThread(QThread):
            finished = pyqtSignal(object)
            def __init__(self, fn):
                super().__init__()
                self.fn = fn
            def run(self):
                result = self.fn()
                self.finished.emit(result)

        thread = WorkerThread(func)
        thread.finished.connect(callback)
        thread.finished.connect(lambda: self._remove_thread(thread))
        thread.start()
        self._threads.append(thread)
    
    def _show_logs(self):
        dialog = LogsDialog(self, self.node_manager)
        dialog.exec_()
    
    def _reset_zecnode(self):
        """Reset ZecNode config and restart"""
        dialog = ConfirmDialog(
            self,
            "Reset ZecNode",
            "This will reset all settings and restart ZecNode.\n\nYour node data will NOT be deleted.\n\nContinue?"
        )
        dialog.yes_btn.setText("Reset")
        if dialog.exec_() == QDialog.Accepted:
            import shutil
            import sys
            config_dir = os.path.expanduser("~/.zecnode")
            cache_dir = os.path.expanduser("~/zecnode/__pycache__")
            
            # Remove config and cache
            if os.path.exists(config_dir):
                shutil.rmtree(config_dir)
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
            
            # Restart ZecNode
            self.tray.hide()
            QApplication.processEvents()
            os.execv(sys.executable, [sys.executable, os.path.expanduser("~/zecnode/main.py")])
    
    def _shutdown(self):
        """Clean shutdown: stop timers, let Qt clean up resources, with a safety fallback."""
        # Prevent re-entry
        if self._closing:
            return
        self._closing = True

        print("[ZecNode] Shutting down...")

        # Stop all timers so no new threads are spawned
        self.timer.stop()
        self.price_timer.stop()

        # Tell refresh thread to stop
        if self.refresh_thread is not None:
            self.refresh_thread.stop()

        # Hide tray icon
        self.tray.hide()

        # Safety fallback — if clean shutdown hangs, force exit after 3 seconds
        QTimer.singleShot(3000, lambda: os._exit(0))

        # Clean Qt shutdown (releases GPU/display resources properly)
        QApplication.quit()

    def _quit(self):
        self._shutdown()

    def closeEvent(self, event):
        self._shutdown()
        event.accept()


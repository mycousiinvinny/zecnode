"""
ZecNode Dashboard
Redesigned professional UI with sidebar navigation
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
    QMenu, QAction, QDialog, QApplication,
    QSpacerItem, QSizePolicy, QFrame, QProgressBar,
    QStackedWidget, QLineEdit, QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect, QScrollArea, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QRectF, pyqtProperty, QEasingCurve, QPoint
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QTextCursor, QBrush, QPen

from config import Config, VERSION
from node_manager import NodeManager


# ============================================================
# Design Tokens
# ============================================================
C = {
    'bg':             '#0a0a0e',
    'sidebar':        '#0e0e13',
    'surface':        '#141419',
    'surface_alt':    '#18181f',
    'surface_hover':  '#1e1e26',
    'border':         '#1c1c24',
    'border_light':   '#2a2a34',
    'text':           '#e8e8ec',
    'text_sec':       '#8b8b96',
    'text_muted':     '#50505c',
    'accent':         '#f4b728',
    'accent_hover':   '#ffc942',
    'accent_dim':     'rgba(244, 183, 40, 0.08)',
    'success':        '#22c55e',
    'error':          '#ef4444',
    'warning':        '#f59e0b',
}

SIDEBAR_BTN = f"""
    QPushButton {{
        background: transparent;
        color: {C['text_sec']};
        text-align: left;
        padding: 11px 22px;
        border: none;
        border-left: 3px solid transparent;
        font-size: 13px;
        font-weight: 500;
        border-radius: 0px;
    }}
    QPushButton:hover {{
        background: rgba(255,255,255,0.03);
        color: {C['text']};
    }}
"""

SIDEBAR_BTN_ACTIVE = f"""
    QPushButton {{
        background: {C['accent_dim']};
        color: {C['accent']};
        text-align: left;
        padding: 11px 22px;
        border: none;
        border-left: 3px solid {C['accent']};
        font-size: 13px;
        font-weight: 600;
        border-radius: 0px;
    }}
"""

TITLE_BAR_HEIGHT = 46


# ============================================================
# Reusable Widgets
# ============================================================

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
        if not p.isActive():
            return
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setOpacity(self._opacity)

            w, h = self.width(), self.height()
            radius = h / 2

            if self._checked:
                track_color = QColor(C['success'])
            else:
                track_color = QColor("#3a3a44")
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(track_color))
            p.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

            knob_size = h - 8
            p.setBrush(QBrush(QColor("white")))
            p.drawEllipse(QRectF(self._knob_x, 4, knob_size, knob_size))
        finally:
            p.end()


class StatusDot(QWidget):
    """Status indicator dot"""
    STATE_STOPPED = 0
    STATE_RUNNING = 1
    STATE_NO_INTERNET = 2

    def __init__(self, size=10, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self._state = self.STATE_STOPPED

    def set_running(self, running):
        self._state = self.STATE_RUNNING if running else self.STATE_STOPPED
        self.update()

    def set_state(self, state):
        self._state = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            if self._state == self.STATE_RUNNING:
                color = QColor(C['success'])
            elif self._state == self.STATE_NO_INTERNET:
                color = QColor(C['warning'])
            else:
                color = QColor(C['error'])
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            s = self._size
            painter.drawEllipse(1, 1, s - 2, s - 2)
        finally:
            painter.end()


class StatCard(QFrame):
    """Modern stat display card"""

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setStyleSheet(f"""
            #statCard {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        title = QLabel(label)
        title.setStyleSheet(f"color: {C['text_muted']}; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; background: transparent; border: none;")
        layout.addWidget(title)

        self.value_label = QLabel("--")
        self.value_label.setFont(QFont("Segoe UI", 17, QFont.Bold))
        self.value_label.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
        layout.addWidget(self.value_label)

    def set_value(self, val):
        self.value_label.setText(val)


class InlineStat(QWidget):
    """Compact inline label for borderless footer strip: '<value> <unit>'."""

    def __init__(self, unit, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.value_label = QLabel("--")
        self.value_label.setStyleSheet(
            f"color: {C['text']}; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        )
        layout.addWidget(self.value_label)

        self.unit_label = QLabel(unit)
        self.unit_label.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; background: transparent; border: none;"
        )
        layout.addWidget(self.unit_label)

    def set_value(self, val):
        self.value_label.setText(val)


class ShieldedSupplyChart(QWidget):
    """Stacked area chart of shielded pool supply over time (Sprout + Sapling + Orchard).
    Data points: list of dicts with keys 'timestamp', 'sprout_zatoshis', 'sapling_zatoshis',
    'orchard_zatoshis'. Draws three stacked translucent gold-family layers with a smooth fill.
    """

    COLOR_SPROUT = QColor(139, 92, 246, 180)   # purple
    COLOR_SAPLING = QColor(34, 197, 94, 180)   # green
    COLOR_ORCHARD = QColor(244, 183, 40, 200)  # gold
    AXIS_COLOR = QColor(42, 42, 52)
    TEXT_COLOR = QColor(139, 139, 150)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self.setFixedHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, points):
        self._points = points or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)

            w, h = self.width(), self.height()
            pad_l, pad_r, pad_t, pad_b = 8, 8, 10, 18
            plot_w = max(1, w - pad_l - pad_r)
            plot_h = max(1, h - pad_t - pad_b)

            if not self._points or len(self._points) < 2:
                painter.setPen(self.TEXT_COLOR)
                painter.drawText(self.rect(), Qt.AlignCenter, "Loading shielded supply history…")
                return

            pts = self._points
            ts_min = pts[0]["timestamp"]
            ts_max = pts[-1]["timestamp"]
            ts_span = max(1, ts_max - ts_min)

            stacked_totals = []
            max_total = 0
            for p in pts:
                sp = p.get("sprout_zatoshis", 0) or 0
                sa = p.get("sapling_zatoshis", 0) or 0
                orch = p.get("orchard_zatoshis", 0) or 0
                total = sp + sa + orch
                stacked_totals.append((sp, sa, orch, total))
                if total > max_total:
                    max_total = total
            if max_total <= 0:
                return

            def x_for(ts):
                return pad_l + (ts - ts_min) / ts_span * plot_w

            def y_for(val):
                return pad_t + plot_h - (val / max_total) * plot_h

            def build_polygon(values_top, values_bottom):
                from PyQt5.QtGui import QPolygonF
                from PyQt5.QtCore import QPointF
                poly = QPolygonF()
                for i, p in enumerate(pts):
                    poly.append(QPointF(x_for(p["timestamp"]), values_top[i]))
                for i in range(len(pts) - 1, -1, -1):
                    poly.append(QPointF(x_for(pts[i]["timestamp"]), values_bottom[i]))
                return poly

            baseline = [y_for(0)] * len(pts)
            top_sprout = [y_for(s[0]) for s in stacked_totals]
            top_sapling = [y_for(s[0] + s[1]) for s in stacked_totals]
            top_orchard = [y_for(s[3]) for s in stacked_totals]

            painter.setPen(Qt.NoPen)

            painter.setBrush(QBrush(self.COLOR_SPROUT))
            painter.drawPolygon(build_polygon(top_sprout, baseline))

            painter.setBrush(QBrush(self.COLOR_SAPLING))
            painter.drawPolygon(build_polygon(top_sapling, top_sprout))

            painter.setBrush(QBrush(self.COLOR_ORCHARD))
            painter.drawPolygon(build_polygon(top_orchard, top_sapling))

            line_pen = QPen(QColor(244, 183, 40, 255))
            line_pen.setWidth(2)
            painter.setPen(line_pen)
            from PyQt5.QtCore import QPointF
            for i in range(len(pts) - 1):
                painter.drawLine(
                    QPointF(x_for(pts[i]["timestamp"]), top_orchard[i]),
                    QPointF(x_for(pts[i + 1]["timestamp"]), top_orchard[i + 1]),
                )

            import datetime as _dt
            painter.setPen(self.TEXT_COLOR)
            painter.setFont(QFont("Segoe UI", 8))
            start_label = _dt.datetime.fromtimestamp(ts_min).strftime("%Y")
            end_label = _dt.datetime.fromtimestamp(ts_max).strftime("%Y")
            painter.drawText(pad_l, h - 4, start_label)
            painter.drawText(w - pad_r - 36, h - 4, end_label)
        finally:
            painter.end()


# ============================================================
# Network / Price Helpers
# ============================================================

def check_internet(timeout=2):
    for host in ("8.8.8.8", "1.1.1.1"):
        try:
            conn = socket.create_connection((host, 53), timeout=timeout)
            conn.close()
            return True
        except OSError:
            continue
    return False


def fetch_zec_price():
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


def fetch_zec_chart():
    """Fetch 24h price history for sparkline"""
    try:
        url = "https://api.coingecko.com/api/v3/coins/zcash/market_chart?vs_currency=usd&days=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'ZecNode/1.0'})
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode())
            prices = [p[1] for p in data.get('prices', [])]
            return prices
    except:
        return None


# ============================================================
# Background Threads
# ============================================================

class SparklineWidget(QWidget):
    """Mini price chart with draw-on animation"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self._positive = True
        self._progress = 0.0  # 0.0 = nothing drawn, 1.0 = fully drawn
        self.setFixedSize(90, 36)

        self._anim = QPropertyAnimation(self, b"draw_progress")
        self._anim.setDuration(1200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_progress(self):
        return self._progress

    def _set_progress(self, val):
        self._progress = val
        self.update()

    draw_progress = pyqtProperty(float, _get_progress, _set_progress)

    def set_data(self, prices, positive=True):
        self._points = prices or []
        self._positive = positive
        # Animate the line drawing from 0 to 1
        self._anim.stop()
        self._progress = 0.0
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, event):
        if len(self._points) < 2 or self._progress <= 0:
            return

        p = QPainter(self)
        if not p.isActive():
            return
        try:
            p.setRenderHint(QPainter.Antialiasing)

            w, h = self.width(), self.height()
            pad = 2

            mn = min(self._points)
            mx = max(self._points)
            rng = mx - mn if mx != mn else 1.0

            n = len(self._points)
            x_step = (w - 2 * pad) / (n - 1)

            total_segments = n - 1
            segments_to_draw = self._progress * total_segments
            full_segments = int(segments_to_draw)
            partial = segments_to_draw - full_segments

            color = QColor(C['success']) if self._positive else QColor(C['error'])
            pen = QPen(color, 1.5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)

            prev_x = pad
            prev_y = h - pad - ((self._points[0] - mn) / rng) * (h - 2 * pad)

            for i in range(1, min(full_segments + 1, n)):
                x = pad + i * x_step
                y = h - pad - ((self._points[i] - mn) / rng) * (h - 2 * pad)
                p.drawLine(int(prev_x), int(prev_y), int(x), int(y))
                prev_x, prev_y = x, y

            if partial > 0 and full_segments + 1 < n:
                next_x = pad + (full_segments + 1) * x_step
                next_y = h - pad - ((self._points[full_segments + 1] - mn) / rng) * (h - 2 * pad)
                interp_x = prev_x + (next_x - prev_x) * partial
                interp_y = prev_y + (next_y - prev_y) * partial
                p.drawLine(int(prev_x), int(prev_y), int(interp_x), int(interp_y))
        finally:
            p.end()

        p.end()

        p.end()


class PriceThread(QThread):
    finished = pyqtSignal(object, object, object)  # price, change, chart_data
    def run(self):
        price, change = fetch_zec_price()
        chart = fetch_zec_chart()
        self.finished.emit(price, change, chart)


class NodeActionThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, action, node_manager, lwd_enabled=False):
        super().__init__()
        self.action = action
        self.node_manager = node_manager
        self.lwd_enabled = lwd_enabled

    def run(self):
        if self.action == "start":
            ok, msg = self.node_manager.start_node()
            if ok and self.lwd_enabled:
                self.node_manager.start_lightwalletd()
        elif self.action == "stop":
            if self.node_manager.is_arti_running():
                self.node_manager.stop_arti()
            if self.node_manager.is_lightwalletd_running():
                self.node_manager.stop_lightwalletd()
            ok, msg = self.node_manager.stop_node()
        elif self.action == "restart":
            arti_was_running = self.node_manager.is_arti_running()
            lwd_was_running = self.node_manager.is_lightwalletd_running()
            if arti_was_running:
                self.node_manager.stop_arti()
            if lwd_was_running:
                self.node_manager.stop_lightwalletd()
            ok, msg = self.node_manager.restart_node()
            if ok and (self.lwd_enabled or lwd_was_running):
                self.node_manager.start_lightwalletd()
            if ok and arti_was_running:
                self.node_manager.start_arti()
        else:
            ok, msg = False, "Unknown action"
        self.finished.emit(ok, msg)


class RefreshThread(QThread):
    finished = pyqtSignal(object, bool, str, str, bool, bool)

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

        import time
        now = time.monotonic()
        if now - RefreshThread._last_internet_check >= 60:
            RefreshThread._cached_internet = check_internet()
            RefreshThread._last_internet_check = now
        has_internet = RefreshThread._cached_internet

        if not self._running:
            return
        status = self.node_manager.get_status()
        if not self._running:
            return

        if now - RefreshThread._last_disk_check >= 60:
            RefreshThread._cached_ssd, RefreshThread._cached_sd = self.node_manager.get_disk_usage()
            RefreshThread._last_disk_check = now
        ssd, sd = RefreshThread._cached_ssd, RefreshThread._cached_sd

        if not self._running:
            return
        lwd_running = self.node_manager.is_lightwalletd_running()
        if not self._running:
            return
        arti_running = self.node_manager.is_arti_running()
        if not self._running:
            return

        self.finished.emit(status, has_internet, ssd, sd, lwd_running, arti_running)


class UpdateThread(QThread):
    finished = pyqtSignal(bool, str)

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

                git_check = subprocess.run(
                    ["git", "rev-parse", "--git-dir"],
                    cwd=zecnode_dir,
                    capture_output=True, timeout=5
                )

                if git_check.returncode == 0:
                    result = subprocess.run(
                        ["bash", "-c", f"cd {zecnode_dir} && rm -rf __pycache__ && git fetch origin main && git reset --hard origin/main && echo SUCCESS"],
                        capture_output=True, text=True, timeout=120
                    )
                else:
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
                            curl -sSL -o splash.py "{github_raw}/splash.py" && \
                            curl -sSL -o uninstall.sh "{github_raw}/uninstall.sh" && \
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
                result = subprocess.run(
                    ["docker", "pull", f"zfnd/zebra:{self.zebra_version}"],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    self.finished.emit(False, "Failed to pull Zebra image")
                    return

                volume_mounts = []
                port_mappings = ["8233:8233"]

                try:
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

                if not volume_mounts:
                    data_path = self.data_path or "/mnt/zebra-data"
                    volume_mounts = [
                        f"{data_path}/zebra-cache:/home/zebra/.cache/zebra",
                        f"{data_path}/zebra-state:/home/zebra/.local/state/zebra"
                    ]

                running = subprocess.run(
                    ["docker", "ps", "-q", "-f", "name=zebra"],
                    capture_output=True, text=True
                )
                was_running = bool(running.stdout.strip())

                if was_running:
                    subprocess.run(["docker", "stop", "zebra"], capture_output=True, timeout=30)

                subprocess.run(["docker", "rm", "zebra"], capture_output=True, timeout=10)
                subprocess.run(["docker", "network", "create", "zecnode"], capture_output=True)

                docker_cmd = [
                    "docker", "run", "-d",
                    "--name", "zebra",
                    "--network", "zecnode",
                    "--restart", "unless-stopped",
                    "-e", "ZEBRA_RPC__LISTEN_ADDR=0.0.0.0:8232",
                    "-e", "ZEBRA_RPC__ENABLE_COOKIE_AUTH=false",
                ]

                for mount in volume_mounts:
                    docker_cmd.extend(["-v", mount])

                docker_cmd.extend(["-p", "8233:8233"])
                docker_cmd.append(f"zfnd/zebra:{self.zebra_version}")

                result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=30)

                if result.returncode == 0:
                    self.finished.emit(True, "Zebra updated successfully!")
                else:
                    self.finished.emit(False, f"Failed to start Zebra: {result.stderr}")

            elif self.update_type == "lightwalletd":
                lwd_image = "mycousiinvinny/lightwalletd:arm64"

                # 1. Pull the latest image from Docker Hub
                pull = subprocess.run(
                    ["docker", "pull", lwd_image],
                    capture_output=True, text=True, timeout=300
                )
                if pull.returncode != 0:
                    self.finished.emit(False, f"Failed to pull image: {pull.stderr.strip()}")
                    return

                # 2. Check if the container is currently running
                running = subprocess.run(
                    ["docker", "ps", "-q", "-f", "name=lightwalletd"],
                    capture_output=True, text=True
                )
                was_running = bool(running.stdout.strip())

                # 3. Remove old container so a fresh one will pick up the new image.
                # (If lwd was running, ZecNode's _update_lightwalletd_image will
                # re-start it on the main thread after this thread emits success.)
                if was_running:
                    subprocess.run(["docker", "stop", "lightwalletd"], capture_output=True, timeout=30)
                subprocess.run(["docker", "rm", "-f", "lightwalletd"], capture_output=True, timeout=10)

                if "Image is up to date" in pull.stdout:
                    msg = "Already up to date."
                else:
                    msg = "Lightwalletd image updated."
                if was_running:
                    msg += " Restarting container…"
                self.finished.emit(True, f"LWD_UPDATED|{int(was_running)}|{msg}")

        except subprocess.TimeoutExpired:
            self.finished.emit(False, "Update timed out")
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


# ============================================================
# Dialogs
# ============================================================

class ConfirmDialog(QDialog):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(420, 240)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(self)
        container.setGeometry(0, 0, 420, 240)
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 12px;
            }}
        """)

        close_btn = QPushButton("\u2715", container)
        close_btn.setGeometry(376, 8, 32, 32)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {C['text_muted']}; font-size: 16px;
            }}
            QPushButton:hover {{ color: {C['text']}; }}
        """)
        close_btn.clicked.connect(self.reject)

        title_label = QLabel(title, container)
        title_label.setGeometry(0, 28, 420, 28)
        title_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title_label.setStyleSheet(f"color: {C['accent']}; border: none; background: transparent;")
        title_label.setAlignment(Qt.AlignCenter)

        msg_label = QLabel(message, container)
        msg_label.setGeometry(36, 64, 348, 70)
        msg_label.setStyleSheet(f"color: {C['text']}; font-size: 12px; border: none; background: transparent;")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)

        btn_widget = QWidget(container)
        btn_widget.setGeometry(0, 155, 420, 60)
        btn_widget.setStyleSheet("background: transparent; border: none;")

        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(50, 0, 50, 0)
        btn_layout.setSpacing(16)

        self.no_btn = QPushButton("Cancel")
        self.no_btn.setMinimumHeight(42)
        self.no_btn.setMinimumWidth(130)
        self.no_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['surface_hover']}; border: 1px solid {C['border_light']};
                color: {C['text']}; border-radius: 8px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {C['border_light']}; }}
        """)
        self.no_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.no_btn)

        self.yes_btn = QPushButton("Update")
        self.yes_btn.setMinimumHeight(42)
        self.yes_btn.setMinimumWidth(130)
        self.yes_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['accent']}; border: none;
                color: #0a0a0e; border-radius: 8px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {C['accent_hover']}; }}
        """)
        self.yes_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.yes_btn)

    def accept(self):
        self.result = True
        super().accept()


class MessageDialog(QDialog):
    def __init__(self, parent, title, message, is_error=False):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(320, 180)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(self)
        container.setGeometry(0, 0, 320, 180)
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 12px;
            }}
        """)

        close_btn = QPushButton("\u2715", container)
        close_btn.setGeometry(276, 8, 32, 32)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {C['text_muted']}; font-size: 16px; }}
            QPushButton:hover {{ color: {C['text']}; }}
        """)
        close_btn.clicked.connect(self.accept)

        title_label = QLabel(title, container)
        title_label.setGeometry(0, 28, 320, 28)
        title_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        color = C['error'] if is_error else C['success']
        title_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        title_label.setAlignment(Qt.AlignCenter)

        msg_label = QLabel(message, container)
        msg_label.setGeometry(20, 62, 280, 50)
        msg_label.setStyleSheet(f"color: {C['text']}; font-size: 12px; border: none; background: transparent;")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)

        ok_btn = QPushButton("OK", container)
        ok_btn.setGeometry(120, 125, 80, 38)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['accent']}; border: none; border-radius: 8px;
                color: #0a0a0e; font-size: 13px; font-weight: 600;
                padding: 0; min-width: 0;
            }}
            QPushButton:hover {{ background-color: {C['accent_hover']}; }}
        """)
        ok_btn.clicked.connect(self.accept)


class ErrorDialog(QDialog):
    """Friendly, dismissable error dialog. Shows a plain-language headline and
    summary, with the raw technical detail (Docker stderr, etc.) tucked behind a
    'Show details' toggle so users aren't hit with a wall of stderr by default."""

    def __init__(self, parent, headline, summary, details=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog {{ background-color: {C['surface']}; border: 1px solid {C['border']}; }}"
        )
        self.setMinimumWidth(380)
        self.setMaximumWidth(460)

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(12)

        title = QLabel(headline)
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet(f"color: {C['error']}; background: transparent; border: none;")
        title.setWordWrap(True)
        v.addWidget(title)

        body = QLabel(summary)
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {C['text']}; font-size: 12px; background: transparent; border: none;")
        v.addWidget(body)

        details = (details or "").strip()
        if details and details != summary.strip():
            self._details_box = QTextEdit()
            self._details_box.setReadOnly(True)
            self._details_box.setPlainText(details)
            self._details_box.setFixedHeight(110)
            self._details_box.setStyleSheet(
                f"QTextEdit {{ background-color: {C['bg']}; color: {C['text_sec']}; "
                f"border: 1px solid {C['border']}; border-radius: 6px; "
                f"font-family: monospace; font-size: 11px; }}"
            )
            self._details_box.hide()

            self._details_toggle = QPushButton("Show details ▾")
            self._details_toggle.setCursor(Qt.PointingHandCursor)
            self._details_toggle.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; color: {C['text_sec']}; "
                f"font-size: 11px; text-align: left; padding: 0; min-width: 0; }}"
                f"QPushButton:hover {{ color: {C['text']}; }}"
            )

            def _toggle():
                if self._details_box.isVisible():
                    self._details_box.hide()
                    self._details_toggle.setText("Show details ▾")
                else:
                    self._details_box.show()
                    self._details_toggle.setText("Hide details ▴")
                self.adjustSize()

            self._details_toggle.clicked.connect(_toggle)
            v.addWidget(self._details_toggle)
            v.addWidget(self._details_box)

        ok_btn = QPushButton("OK")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setMinimumHeight(38)
        ok_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['accent']}; border: none; border-radius: 8px; "
            f"color: #0a0a0e; font-size: 13px; font-weight: 600; padding: 0 22px; }}"
            f"QPushButton:hover {{ background-color: {C['accent_hover']}; }}"
        )
        ok_btn.clicked.connect(self.accept)
        v.addWidget(ok_btn, 0, Qt.AlignRight)


class UpdateDialog(QDialog):
    def __init__(self, parent, message="Updating..."):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(250, 180)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(self)
        container.setGeometry(0, 0, 250, 180)
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 25, 20, 25)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet("border: none; background: transparent;")
        self._opacity = 1.0
        self._fading_out = True

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zecnode-icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
        else:
            self.logo_label.setText("\u24CF")
            self.logo_label.setStyleSheet(f"font-size: 48px; color: {C['accent']}; border: none; background: transparent;")

        layout.addWidget(self.logo_label)

        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet(f"color: {C['text']}; font-size: 14px; border: none; background: transparent;")
        layout.addWidget(self.message_label)

        self._opacity_effect = QGraphicsOpacityEffect()
        self._opacity_effect.setOpacity(1.0)
        self.logo_label.setGraphicsEffect(self._opacity_effect)

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


# ============================================================
# Main Dashboard Window
# ============================================================

class DashboardWindow(QMainWindow):
    first_refresh_done = pyqtSignal()


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
        self.setMinimumSize(920, 620)
        self.resize(920, 620)

        self._threads = []
        self._sync_history = []  # list of (timestamp, sync_pct) for ETA estimation
        self._update_available = False
        self._latest_release_tag = ""
        self._latest_release_notes = ""
        self._setup_ui()
        self._setup_tray()

        # Refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._start_refresh)
        self.timer.start(10000)
        self._action_in_progress = False
        self._lwd_action_in_progress = False
        self._lwd_auto_action_in_progress = False
        self._arti_action_in_progress = False
        self._arti_auto_action_in_progress = False
        self._arti_onion_fetch_in_progress = False
        self._closing = False
        self.refresh_thread = None
        cached_ver = self.config.get("cached_zebra_version", None)
        self._cached_zebra_version = cached_ver
        self._zebra_version_fetched = False
        self._first_refresh_emitted = False

        # Apply last-known state to the UI instantly so the dashboard looks
        # "live" the moment it appears, instead of waiting 3-5s for the first
        # refresh to complete. The actual refresh still runs and overwrites.
        self._apply_cached_status()

        self._start_refresh()

        # Price timer
        self.price_thread = None
        self.price_timer = QTimer()
        self.price_timer.timeout.connect(self._fetch_price)
        self.price_timer.start(120000)
        self._fetch_price()

        # Update check (GitHub releases) — fresh on launch, then every 3h
        self._update_check_timer = QTimer()
        self._update_check_timer.timeout.connect(self._check_for_updates)
        self._update_check_timer.start(3 * 60 * 60 * 1000)
        self._check_for_updates(force=True)

        # Logs timer (only active when on logs page)
        self._log_timer = QTimer()
        self._log_timer.timeout.connect(self._refresh_logs)
        self._log_thread = None

    # ── Window drag & resize ──────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() < TITLE_BAR_HEIGHT:
            if self.isMaximized():
                return
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.pos().y() < TITLE_BAR_HEIGHT:
            self._toggle_maximize()

    def showEvent(self, event):
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

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.container.setStyleSheet(f"""
                #mainContainer {{
                    background-color: {C['bg']};
                    border: 1px solid {C['border']};
                    border-radius: 12px;
                }}
            """)
            self._max_btn.setText("\u25a1")
        else:
            self.showMaximized()
            self.container.setStyleSheet(f"""
                #mainContainer {{
                    background-color: {C['bg']};
                    border: none;
                    border-radius: 0px;
                }}
            """)
            self._max_btn.setText("\u29c9")

    # ── UI Setup ──────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        self.container = QFrame(central)
        self.container.setObjectName("mainContainer")
        self.container.setStyleSheet(f"""
            #mainContainer {{
                background-color: {C['bg']};
                border: 1px solid {C['border']};
                border-radius: 12px;
            }}
        """)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.container)

        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Title bar ──
        title_bar = QWidget()
        title_bar.setFixedHeight(TITLE_BAR_HEIGHT)
        title_bar.setStyleSheet(f"background: transparent;")

        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(18, 0, 6, 0)
        tb.setSpacing(0)

        # App name
        app_name = QLabel("ZecNode")
        app_name.setFont(QFont("Segoe UI", 14, QFont.Bold))
        app_name.setStyleSheet(f"color: {C['accent']}; background: transparent;")
        tb.addWidget(app_name)

        tb.addSpacing(8)

        ver = QLabel(f"v{VERSION}")
        ver.setStyleSheet(f"color: {C['text_muted']}; font-size: 10px; background: transparent;")
        tb.addWidget(ver)

        tb.addStretch()

        # Status in title bar — just the dot, text hidden for compat
        self.status_dot = StatusDot(8)
        tb.addWidget(self.status_dot)

        self.status_text = QLabel("")
        self.status_text.hide()

        tb.addSpacing(20)

        # Window controls
        btn_style = f"""
            QPushButton {{
                background: transparent; color: {C['text_muted']}; border: none;
                font-size: 13px; border-radius: 5px; padding: 0;
            }}
            QPushButton:hover {{
                background: {C['surface_hover']}; color: {C['text']};
            }}
        """
        close_style = f"""
            QPushButton {{
                background: transparent; color: {C['text_muted']}; border: none;
                font-size: 13px; border-radius: 5px; padding: 0;
            }}
            QPushButton:hover {{
                background: {C['error']}; color: white;
            }}
        """

        min_btn = QPushButton("\u2500")
        min_btn.setFixedSize(34, 28)
        min_btn.setStyleSheet(btn_style)
        min_btn.clicked.connect(self.showMinimized)
        tb.addWidget(min_btn)

        self._max_btn = QPushButton("\u25a1")
        self._max_btn.setFixedSize(34, 28)
        self._max_btn.setStyleSheet(btn_style)
        self._max_btn.clicked.connect(self._toggle_maximize)
        tb.addWidget(self._max_btn)

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(34, 28)
        close_btn.setStyleSheet(close_style)
        close_btn.clicked.connect(self.close)
        tb.addWidget(close_btn)

        main_layout.addWidget(title_bar)

        # Separator below title bar
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C['border']};")
        main_layout.addWidget(sep)

        # ── Content area: sidebar + pages ──
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ── Sidebar ──
        sidebar = QWidget()
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet(f"background-color: {C['sidebar']};")

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 12, 0, 16)
        sidebar_layout.setSpacing(2)

        self._nav_buttons = []
        nav_items = ["  Dashboard", "  Logs", "  Network", "  Learn", "  Settings"]

        for i, label in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(SIDEBAR_BTN_ACTIVE if i == 0 else SIDEBAR_BTN)
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Price widget at bottom of sidebar
        price_sep = QFrame()
        price_sep.setFixedHeight(1)
        price_sep.setStyleSheet(f"background: {C['border']}; margin: 0 16px;")
        sidebar_layout.addWidget(price_sep)
        sidebar_layout.addSpacing(10)

        # Price area: text left, sparkline right
        price_row = QHBoxLayout()
        price_row.setContentsMargins(16, 0, 12, 0)
        price_row.setSpacing(8)

        price_text = QVBoxLayout()
        price_text.setSpacing(1)

        price_label_header = QLabel("ZEC")
        price_label_header.setStyleSheet(f"color: {C['text_muted']}; font-size: 10px; font-weight: 600; background: transparent;")
        price_text.addWidget(price_label_header)

        self.price_label = QLabel("$--")
        self.price_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.price_label.setStyleSheet(f"color: {C['text']}; background: transparent;")
        price_text.addWidget(self.price_label)

        self.change_label = QLabel("--%")
        self.change_label.setStyleSheet(f"color: {C['text_sec']}; font-size: 10px; background: transparent;")
        price_text.addWidget(self.change_label)

        price_row.addLayout(price_text)
        price_row.addStretch()

        self.sparkline = SparklineWidget()
        price_row.addWidget(self.sparkline)

        sidebar_layout.addLayout(price_row)

        content_layout.addWidget(sidebar)

        # Sidebar right border
        sidebar_sep = QFrame()
        sidebar_sep.setFixedWidth(1)
        sidebar_sep.setStyleSheet(f"background: {C['border']};")
        content_layout.addWidget(sidebar_sep)

        # ── Page stack ──
        self.page_stack = QStackedWidget()
        self.page_stack.setStyleSheet("background: transparent;")

        self.page_stack.addWidget(self._create_dashboard_page())
        self.page_stack.addWidget(self._create_logs_page())
        self.page_stack.addWidget(self._create_network_page())
        self.page_stack.addWidget(self._create_learn_page())
        self.page_stack.addWidget(self._create_settings_page())

        content_layout.addWidget(self.page_stack, 1)
        main_layout.addWidget(content, 1)

    # ── Page creation ─────────────────────────────────────

    def _create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        # ── Sync hero ───────────────────────────────────────────
        hero = QFrame()
        hero.setObjectName("syncHero")
        hero.setStyleSheet(f"""
            #syncHero {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 14px;
            }}
        """)
        h_layout = QVBoxLayout(hero)
        h_layout.setContentsMargins(28, 26, 28, 26)
        h_layout.setSpacing(10)
        h_layout.setAlignment(Qt.AlignCenter)

        # Starts as a loading placeholder; replaced by the cached snapshot (instant
        # restart) or the first real status refresh, whichever paints first. Avoids
        # a brief flash of "0.0% / Block 0" that looks like a stopped node.
        self.sync_percent_label = QLabel("Loading…")
        self.sync_percent_label.setAlignment(Qt.AlignCenter)
        self.sync_percent_label.setFont(QFont("Segoe UI", 52, QFont.Bold))
        self.sync_percent_label.setStyleSheet(
            f"color: {C['text_sec']}; background: transparent; border: none;"
        )
        h_layout.addWidget(self.sync_percent_label)

        self.sync_height_label = QLabel("Loading node information…")
        self.sync_height_label.setAlignment(Qt.AlignCenter)
        self.sync_height_label.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 13px; background: transparent; border: none;"
        )
        h_layout.addWidget(self.sync_height_label)

        h_layout.addSpacing(6)

        self.sync_progress = QProgressBar()
        self.sync_progress.setFixedHeight(10)
        self.sync_progress.setRange(0, 100)
        self.sync_progress.setValue(0)
        self.sync_progress.setTextVisible(False)
        self.sync_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {C['surface_hover']};
                border: none;
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                border-radius: 5px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {C['accent']}, stop:1 {C['accent_hover']});
            }}
        """)
        bar_glow = QGraphicsDropShadowEffect(self.sync_progress)
        bar_glow.setBlurRadius(18)
        bar_glow.setColor(QColor(244, 183, 40, 140))
        bar_glow.setOffset(0, 0)
        self.sync_progress.setGraphicsEffect(bar_glow)
        h_layout.addWidget(self.sync_progress)

        self.sync_eta_label = QLabel("")
        self.sync_eta_label.setAlignment(Qt.AlignCenter)
        self.sync_eta_label.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; background: transparent; border: none;"
        )
        h_layout.addWidget(self.sync_eta_label)

        layout.addWidget(hero)

        # ── Zebra row (compact) ─────────────────────────────────
        zebra_row = QFrame()
        zebra_row.setObjectName("zebraRow")
        zebra_row.setStyleSheet(f"""
            #zebraRow {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 10px;
            }}
        """)
        zr = QHBoxLayout(zebra_row)
        zr.setContentsMargins(18, 12, 18, 12)
        zr.setSpacing(10)

        self.zebra_status_dot = StatusDot(9)
        zr.addWidget(self.zebra_status_dot)

        z_title = QLabel("Zebra")
        z_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        z_title.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
        zr.addWidget(z_title)

        self.zebra_version_label = QLabel("")
        self.zebra_version_label.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; background: transparent; border: none;"
        )
        zr.addWidget(self.zebra_version_label)

        # Hidden label kept so existing setText calls remain valid.
        self.zebra_status_text = QLabel("")
        self.zebra_status_text.hide()

        zr.addStretch()

        # Restart icon button (circular arrow). Visible only when running.
        self.restart_btn = QPushButton("\u27f3")
        self.restart_btn.setFixedSize(28, 28)
        self.restart_btn.setCursor(Qt.PointingHandCursor)
        self.restart_btn.setToolTip("Restart Zebra")
        self.restart_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C['warning']};
                border: none; border-radius: 14px;
                font-size: 18px; font-weight: 600; padding: 0; min-width: 0;
            }}
            QPushButton:hover {{ background: rgba(245, 158, 11, 0.12); color: #ffb84a; }}
            QPushButton:disabled {{ color: {C['text_muted']}; }}
            QToolTip {{
                background-color: {C['surface']}; color: {C['text']};
                border: 1px solid {C['accent']}; padding: 8px 10px; border-radius: 6px; font-size: 12px;
            }}
        """)
        self.restart_btn.clicked.connect(self._restart)
        zr.addWidget(self.restart_btn)

        # Zebra on/off toggle (replaces Stop/Start buttons)
        self.zebra_toggle = ToggleSwitch()
        self.zebra_toggle.toggled.connect(self._toggle_zebra_from_toggle)
        zr.addWidget(self.zebra_toggle)

        # Hidden compat buttons — other methods still call setEnabled/setVisible on these.
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.hide()
        self.stop_btn.clicked.connect(self._stop)
        self.start_btn = QPushButton("Start")
        self.start_btn.hide()
        self.start_btn.clicked.connect(self._start)

        layout.addWidget(zebra_row)

        # ── Lightwalletd row (compact) ──────────────────────────
        lwd_row = QFrame()
        lwd_row.setObjectName("lwdRow")
        lwd_row.setStyleSheet(f"""
            #lwdRow {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 10px;
            }}
        """)
        lr = QHBoxLayout(lwd_row)
        lr.setContentsMargins(18, 10, 18, 10)
        lr.setSpacing(10)

        self.lwd_status_dot = StatusDot(9)
        lr.addWidget(self.lwd_status_dot)

        lwd_title = QLabel("Lightwalletd")
        lwd_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lwd_title.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
        lr.addWidget(lwd_title)

        lwd_info = QLabel("\u24d8")
        lwd_info.setStyleSheet(f"""
            QLabel {{
                color: {C['text_muted']}; font-size: 11px; border: none; background: transparent;
            }}
            QLabel:hover {{ color: {C['accent']}; }}
            QToolTip {{
                background-color: {C['surface']}; color: {C['text']};
                border: 1px solid {C['accent']}; padding: 10px; border-radius: 6px; font-size: 12px;
            }}
        """)
        lwd_info.setToolTip(
            "Lightwalletd lets mobile wallets (like Zashi and Ywallet) "
            "connect to YOUR node instead of public servers.\n\n"
            "\u2022 More privacy \u2014 your transactions stay local\n"
            "\u2022 More decentralization \u2014 reduces reliance on third parties\n"
            "\u2022 Share with friends and family for private wallet access\n\n"
            "Requires Zebra to be fully synced."
        )
        lr.addWidget(lwd_info)

        # Hidden label kept so existing setText calls remain valid.
        self.lwd_status = QLabel("")
        self.lwd_status.hide()

        lr.addStretch()

        self.lwd_toggle = ToggleSwitch()
        self.lwd_toggle.toggled.connect(self._toggle_lightwalletd_from_toggle)
        lr.addWidget(self.lwd_toggle)

        layout.addWidget(lwd_row)

        # ── Tor / Arti row (compact) ────────────────────────────
        arti_row = QFrame()
        arti_row.setObjectName("artiRow")
        arti_row.setStyleSheet(f"""
            #artiRow {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 10px;
            }}
        """)
        arr = QHBoxLayout(arti_row)
        arr.setContentsMargins(18, 10, 18, 10)
        arr.setSpacing(10)

        self.arti_status_dot = StatusDot(9)
        arr.addWidget(self.arti_status_dot)

        arti_title = QLabel("Tor (.onion)")
        arti_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        arti_title.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
        arr.addWidget(arti_title)

        arti_info = QLabel("ⓘ")
        arti_info.setStyleSheet(f"""
            QLabel {{
                color: {C['text_muted']}; font-size: 11px; border: none; background: transparent;
            }}
            QLabel:hover {{ color: {C['accent']}; }}
            QToolTip {{
                background-color: {C['surface']}; color: {C['text']};
                border: 1px solid {C['accent']}; padding: 10px; border-radius: 6px; font-size: 12px;
            }}
        """)
        arti_info.setToolTip(
            "Tor lets people reach your node through a private .onion address,\n"
            "so their IP is never exposed to your server.\n\n"
            "• Maximum privacy — connections are routed over Tor\n"
            "• Your normal (clearnet) wallet access keeps working unchanged\n"
            "• The .onion address is permanent (saved on your SSD)\n\n"
            "Turns on automatically once your node is synced."
        )
        arr.addWidget(arti_info)

        self.arti_status = QLabel("")
        self.arti_status.setStyleSheet(f"color: {C['text_sec']}; font-size: 11px; background: transparent; border: none;")
        arr.addWidget(self.arti_status)

        arr.addStretch()

        self.arti_toggle = ToggleSwitch()
        self.arti_toggle.toggled.connect(self._toggle_arti_from_toggle)
        arr.addWidget(self.arti_toggle)

        layout.addWidget(arti_row)

        # ── .onion address row (hidden until Tor is live) ───────
        self.arti_onion_row = QFrame()
        self.arti_onion_row.setObjectName("artiOnionRow")
        self.arti_onion_row.setStyleSheet(f"""
            #artiOnionRow {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 10px;
            }}
        """)
        aor = QHBoxLayout(self.arti_onion_row)
        aor.setContentsMargins(18, 8, 18, 8)
        aor.setSpacing(10)

        self.arti_onion_label = QLabel("")
        self.arti_onion_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.arti_onion_label.setWordWrap(True)
        self.arti_onion_label.setStyleSheet(
            f"color: {C['text_sec']}; font-size: 11px; font-family: monospace; "
            f"background: transparent; border: none;"
        )
        aor.addWidget(self.arti_onion_label, 1)

        self.arti_copy_btn = QPushButton("Copy")
        self.arti_copy_btn.setCursor(Qt.PointingHandCursor)
        self.arti_copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['accent']}; color: #1a1a1a;
                border: none; border-radius: 6px;
                padding: 4px 14px; min-width: 0px; font-size: 11px; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {C['accent']}; }}
        """)
        self.arti_copy_btn.clicked.connect(self._copy_onion)
        aor.addWidget(self.arti_copy_btn)

        self.arti_qr_btn = QPushButton("QR")
        self.arti_qr_btn.setCursor(Qt.PointingHandCursor)
        self.arti_qr_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C['accent']};
                border: 1px solid {C['accent']}; border-radius: 6px;
                padding: 4px 14px; min-width: 0px; font-size: 11px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {C['surface_hover']}; }}
        """)
        self.arti_qr_btn.clicked.connect(self._show_onion_qr)
        aor.addWidget(self.arti_qr_btn)

        self.arti_onion_row.setVisible(False)
        layout.addWidget(self.arti_onion_row)

        layout.addStretch()

        # ── Stats footer strip (borderless) ─────────────────────
        stats_strip = QHBoxLayout()
        stats_strip.setContentsMargins(4, 0, 4, 0)
        stats_strip.setSpacing(14)
        stats_strip.setAlignment(Qt.AlignCenter)

        self.peers_card = InlineStat("peers")
        self.uptime_card = InlineStat("uptime")
        self.ssd_card = InlineStat("SSD")
        self.sd_card = InlineStat("SD card")

        def _dot():
            d = QLabel("\u2022")
            d.setStyleSheet(
                f"color: {C['text_muted']}; font-size: 12px; background: transparent; border: none;"
            )
            return d

        stats_strip.addWidget(self.peers_card)
        stats_strip.addWidget(_dot())
        stats_strip.addWidget(self.uptime_card)
        stats_strip.addWidget(_dot())
        stats_strip.addWidget(self.ssd_card)
        stats_strip.addWidget(_dot())
        stats_strip.addWidget(self.sd_card)

        layout.addLayout(stats_strip)

        return page

    def _create_logs_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()

        title = QLabel("Logs")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {C['text']}; background: transparent;")
        header.addWidget(title)

        header.addStretch()

        self._log_status = QLabel("\u25cf Live")
        self._log_status.setStyleSheet(f"color: {C['success']}; font-size: 12px; background: transparent;")
        header.addWidget(self._log_status)

        header.addSpacing(12)

        # Hidden compat: pause button removed, but other code paths still call setText on it.
        self._log_pause_btn = QPushButton("Pause")
        self._log_pause_btn.hide()

        layout.addLayout(header)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #08080c;
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 12px;
                font-family: 'JetBrains Mono', 'Consolas', 'Liberation Mono', monospace;
                font-size: 11px;
                color: {C['success']};
            }}
        """)
        layout.addWidget(self.log_text)

        self._log_paused = False
        return page

    def _create_network_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        # Header
        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("Network")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {C['text']}; background: transparent;")
        header.addWidget(title)
        tagline = QLabel("Live Zcash network stats and shielded supply history.")
        tagline.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; background: transparent;"
        )
        header.addWidget(tagline)

        # Freshness / loading line — tells the user whether data is loading, live,
        # or stale instead of leaving them guessing at a row of dashes.
        self.net_status_label = QLabel("")
        self.net_status_label.setStyleSheet(
            f"color: {C['text_sec']}; font-size: 11px; background: transparent;"
        )
        header.addWidget(self.net_status_label)
        layout.addLayout(header)

        # ── Top stats row ──────────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.net_height_card = StatCard("BLOCK HEIGHT")
        self.net_hashrate_card = StatCard("NETWORK HASHRATE")
        self.net_supply_card = StatCard("TOTAL SUPPLY")
        self.net_shielded_pct_card = StatCard("SHIELDED %")
        stats_row.addWidget(self.net_height_card)
        stats_row.addWidget(self.net_hashrate_card)
        stats_row.addWidget(self.net_supply_card)
        stats_row.addWidget(self.net_shielded_pct_card)
        layout.addLayout(stats_row)

        # ── Shielded supply chart (hero) ───────────────────────
        chart_card = QFrame()
        chart_card.setObjectName("chartCard")
        chart_card.setStyleSheet(f"""
            #chartCard {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 12px;
            }}
        """)
        cc = QVBoxLayout(chart_card)
        cc.setContentsMargins(20, 16, 20, 16)
        cc.setSpacing(8)

        chart_head = QHBoxLayout()
        chart_title = QLabel("Shielded Supply")
        chart_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        chart_title.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
        chart_head.addWidget(chart_title)
        chart_head.addStretch()
        self.net_shielded_total_label = QLabel("-- ZEC")
        self.net_shielded_total_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.net_shielded_total_label.setStyleSheet(
            f"color: {C['accent']}; background: transparent; border: none;"
        )
        chart_head.addWidget(self.net_shielded_total_label)
        cc.addLayout(chart_head)

        self.shielded_chart = ShieldedSupplyChart()
        cc.addWidget(self.shielded_chart, 1)

        # Legend
        legend = QHBoxLayout()
        legend.setSpacing(14)
        legend.setAlignment(Qt.AlignCenter)

        def _chip(color_rgba, label):
            row = QHBoxLayout()
            row.setSpacing(6)
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(
                f"background: {color_rgba}; border-radius: 5px; border: none;"
            )
            row.addWidget(dot)
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color: {C['text_muted']}; font-size: 11px; background: transparent; border: none;"
            )
            row.addWidget(lbl)
            wrap = QWidget()
            wrap.setLayout(row)
            return wrap

        legend.addWidget(_chip("rgba(139, 92, 246, 180)", "Sprout"))
        legend.addWidget(_chip("rgba(34, 197, 94, 180)", "Sapling"))
        legend.addWidget(_chip("rgba(244, 183, 40, 220)", "Orchard"))
        cc.addLayout(legend)

        layout.addWidget(chart_card)
        layout.addStretch()

        return page

    def _create_learn_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("Learn")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {C['text']}; background: transparent;")
        header.addWidget(title)
        tagline = QLabel("The tech behind Zcash, in plain English.")
        tagline.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; background: transparent;"
        )
        header.addWidget(tagline)
        layout.addLayout(header)

        # Scrollable card grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C['border_light']};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C['text_muted']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 4, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        topics = [
            ("Zero-Knowledge Proofs",
             "Proves a transaction is valid without revealing who sent it, who received it, or how much was sent.",
             "zk-SNARKs"),
            ("Halo 2",
             "The proof system Zcash uses today. Unlike older systems, it never required a trusted setup ceremony.",
             "Halo 2 — Pallas / Vesta curves"),
            ("Encrypted Memos",
             "Each shielded transaction can carry a private note. Only the recipient holds the key to read it.",
             "ChaCha20-Poly1305"),
            ("Transparent Pool",
             "Public addresses and amounts, just like Bitcoin. Used mainly for exchange deposits.",
             "t-addresses (t1…)"),
            ("Sprout",
             "The original shielded pool from 2016. Retired and locked behind a one-way turnstile.",
             "BCTV14 proofs (legacy)"),
            ("Sapling",
             "The shielded pool that made private transactions fast enough to run on a phone.",
             "Groth16 proofs — Jubjub curve"),
            ("Orchard",
             "The newest shielded pool. Faster, simpler, and built on Halo 2 with no trusted setup.",
             "Halo 2 proofs — Pallas curve"),
            ("Turnstiles",
             "One-way doors between shielded pools. They make sure no more ZEC ever leaves a pool than entered it.",
             "Pool value balance checks"),
            ("Address Types",
             "t1 is public. zs is shielded. u1 is a Unified Address that can hold all types in one.",
             "Transparent / Sapling / Unified"),
            ("Viewing Keys",
             "Share read-only access to your wallet without giving up the ability to spend. Useful for audits and accounting.",
             "ZIP 32 incoming / full viewing keys"),
            ("Equihash",
             "The mining puzzle that secures the network. Memory-hard, so it resists giant ASIC monopolies.",
             "Equihash 200,9 (Proof of Work)"),
            ("Network Upgrades",
             "Every couple of years, Zcash hard-forks to add features. Sapling, NU5, NU6, NU7 — each step adds new tech.",
             "ZIPs — Zcash Improvement Proposals"),
            ("Zebra",
             "The modern Rust full node, built by the Zcash Foundation. This is the node ZecNode runs.",
             "Zebra"),
            ("Lightwalletd",
             "The middleman that lets phone wallets sync without downloading the whole blockchain.",
             "Lightwalletd server"),
            ("Tor Onion Service",
             "Lets wallets reach your node through a private .onion address over Tor, so their IP is never exposed to your server.",
             "Arti — Tor in Rust"),
        ]

        for i, (title_text, body_text, tech_text) in enumerate(topics):
            grid.addWidget(self._make_learn_card(title_text, body_text, tech_text), i // 2, i % 2)

        # Make both columns share width evenly
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        return page

    def _make_learn_card(self, title_text, body_text, tech_text):
        card = QFrame()
        card.setObjectName("learnCard")
        card.setStyleSheet(f"""
            #learnCard {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 12px;
            }}
        """)
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(8)

        title = QLabel(title_text)
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
        v.addWidget(title)

        body = QLabel(body_text)
        body.setWordWrap(True)
        body.setStyleSheet(
            f"color: {C['text_sec']}; font-size: 12px; background: transparent; border: none; line-height: 1.5;"
        )
        v.addWidget(body)

        tech = QLabel(tech_text)
        tech.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 10px; font-weight: 600; "
            f"background: transparent; border: none; letter-spacing: 0.5px;"
        )
        v.addWidget(tech)

        return card

    def _create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        # ── Page header ────────────────────────────────────────
        header = QVBoxLayout()
        header.setSpacing(2)

        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {C['text']}; background: transparent;")
        header.addWidget(title)

        tagline = QLabel("Updates, network, and app management.")
        tagline.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; background: transparent;"
        )
        header.addWidget(tagline)

        layout.addLayout(header)

        # ── Updates card ──────────────────────────────────────
        updates_card = QFrame()
        updates_card.setObjectName("updatesCard")
        updates_card.setStyleSheet(f"""
            #updatesCard {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 10px;
            }}
        """)
        uc_layout = QVBoxLayout(updates_card)
        uc_layout.setContentsMargins(18, 14, 18, 14)
        uc_layout.setSpacing(10)

        uc_title = QLabel("Updates")
        uc_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        uc_title.setStyleSheet(
            f"color: {C['text']}; background: transparent; border: none;"
        )
        uc_layout.addWidget(uc_title)

        # Primary (gold) update button style
        primary_btn_css = f"""
            QPushButton {{
                background: {C['accent']}; color: #0a0a0e; border: none;
                border-radius: 6px; font-size: 12px; font-weight: 600;
                padding: 0 18px; min-width: 0;
            }}
            QPushButton:hover {{ background: {C['accent_hover']}; }}
            QPushButton:disabled {{ background: {C['surface_hover']}; color: {C['text_muted']}; }}
        """
        # Secondary (bordered) update button style
        secondary_btn_css = f"""
            QPushButton {{
                background: {C['surface_hover']}; color: {C['text']};
                border: 1px solid {C['border_light']}; border-radius: 6px;
                font-size: 12px; font-weight: 600; padding: 0 18px; min-width: 0;
            }}
            QPushButton:hover {{ background: {C['border_light']}; }}
            QPushButton:disabled {{ color: {C['text_muted']}; border-color: {C['border']}; }}
        """

        def make_update_row(title_text, version_label, btn_text, btn_css, on_click):
            row = QHBoxLayout()
            row.setSpacing(10)

            name = QLabel(title_text)
            name.setFont(QFont("Segoe UI", 12, QFont.Bold))
            name.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
            row.addWidget(name)

            version_label.setStyleSheet(
                f"color: {C['text_muted']}; font-size: 11px; background: transparent; border: none;"
            )
            row.addWidget(version_label)

            row.addStretch()

            btn = QPushButton(btn_text)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(btn_css)
            btn.clicked.connect(on_click)
            row.addWidget(btn)
            return row, btn

        # ZecNode update row
        self.settings_version_label = QLabel(f"v{VERSION}")
        zec_row, self._update_zecnode_btn = make_update_row(
            "ZecNode",
            self.settings_version_label,
            "Update",
            primary_btn_css,
            self._update_zecnode,
        )
        uc_layout.addLayout(zec_row)

        # "What's new" clickable link (hidden until an update is detected)
        self._whats_new_label = QLabel("")
        self._whats_new_label.setStyleSheet(
            f"color: {C['accent']}; font-size: 11px; background: transparent; border: none;"
        )
        self._whats_new_label.setVisible(False)
        self._whats_new_label.linkActivated.connect(lambda _=None: self._show_release_notes())
        self._whats_new_label.setCursor(Qt.PointingHandCursor)
        uc_layout.addWidget(self._whats_new_label)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {C['border']}; max-height: 1px; border: none;")
        uc_layout.addWidget(divider)

        # Zebra update row
        self.settings_zebra_label = QLabel("v--")
        zeb_row, self.update_zebra_btn = make_update_row(
            "Zebra",
            self.settings_zebra_label,
            "Update",
            primary_btn_css,
            self._update_zebra,
        )
        uc_layout.addLayout(zeb_row)

        # Divider
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setStyleSheet(f"background-color: {C['border']}; max-height: 1px; border: none;")
        uc_layout.addWidget(divider2)

        # Lightwalletd update row
        self.settings_lwd_label = QLabel("docker image")
        lwd_row, self.update_lwd_btn = make_update_row(
            "Lightwalletd",
            self.settings_lwd_label,
            "Update",
            primary_btn_css,
            self._update_lightwalletd_image,
        )
        uc_layout.addLayout(lwd_row)

        # Apply badge state if we already know about an update
        self._refresh_update_badge()

        layout.addWidget(updates_card)

        # ── Network card ──────────────────────────────────────
        net_card = QFrame()
        net_card.setObjectName("netCard")
        net_card.setStyleSheet(f"""
            #netCard {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 10px;
            }}
        """)
        nc_layout = QVBoxLayout(net_card)
        nc_layout.setContentsMargins(18, 14, 18, 14)
        nc_layout.setSpacing(10)

        nc_title = QLabel("Network")
        nc_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        nc_title.setStyleSheet(
            f"color: {C['text']}; background: transparent; border: none;"
        )
        nc_layout.addWidget(nc_title)

        ip_row = QHBoxLayout()
        ip_row.setSpacing(10)

        ip_prefix = QLabel("LAN IP")
        ip_prefix.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        ip_row.addWidget(ip_prefix)

        # Monospace "read-only input" style for the IP value
        self.ip_label = QLabel("Fetching...")
        self.ip_label.setStyleSheet(f"""
            QLabel {{
                background: {C['surface_hover']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 5px;
                font-family: 'JetBrains Mono', 'Consolas', 'Liberation Mono', monospace;
                font-size: 12px;
                padding: 5px 10px;
            }}
        """)
        ip_row.addWidget(self.ip_label)

        self.copy_ip_btn = QPushButton("Copy")
        self.copy_ip_btn.setFixedSize(72, 28)
        self.copy_ip_btn.setCursor(Qt.PointingHandCursor)
        self.copy_ip_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['surface_hover']}; color: {C['text_sec']};
                border: 1px solid {C['border']}; border-radius: 5px;
                font-size: 11px; font-weight: 600;
                padding: 0; min-width: 0;
            }}
            QPushButton:hover {{ background: {C['border_light']}; color: {C['text']}; }}
        """)
        self.copy_ip_btn.clicked.connect(self._copy_ip_settings)
        ip_row.addWidget(self.copy_ip_btn)

        ip_row.addStretch()
        nc_layout.addLayout(ip_row)

        layout.addWidget(net_card)

        # ── Danger zone card ──────────────────────────────────
        danger_card = QFrame()
        danger_card.setObjectName("dangerCard")
        danger_card.setStyleSheet(f"""
            #dangerCard {{
                background-color: {C['surface']};
                border: 1px solid #3a1a1a;
                border-radius: 10px;
            }}
        """)
        dc_layout = QVBoxLayout(danger_card)
        dc_layout.setContentsMargins(18, 14, 18, 14)
        dc_layout.setSpacing(8)

        dc_title = QLabel("Danger Zone")
        dc_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        dc_title.setStyleSheet(f"color: {C['error']}; background: transparent; border: none;")
        dc_layout.addWidget(dc_title)

        dc_desc = QLabel("Wipes app settings and restarts ZecNode. Node data is preserved.")
        dc_desc.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; background: transparent; border: none;"
        )
        dc_desc.setWordWrap(True)
        dc_layout.addWidget(dc_desc)

        reset_btn = QPushButton("Reset ZecNode")
        reset_btn.setFixedHeight(32)
        reset_btn.setFixedWidth(140)
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C['error']};
                border: 1px solid {C['error']}; border-radius: 6px;
                font-size: 12px; font-weight: 600;
                padding: 0; min-width: 0;
            }}
            QPushButton:hover {{ background: #2a1a1a; }}
        """)
        reset_btn.clicked.connect(self._reset_zecnode)
        reset_glow = QGraphicsDropShadowEffect(reset_btn)
        reset_glow.setBlurRadius(16)
        reset_glow.setColor(QColor(239, 68, 68, 110))
        reset_glow.setOffset(0, 0)
        reset_btn.setGraphicsEffect(reset_glow)
        dc_layout.addWidget(reset_btn)

        layout.addWidget(danger_card)
        layout.addStretch()

        # Fetch IP
        self._update_settings_ip()

        return page

    # ── Page switching ────────────────────────────────────

    def _switch_page(self, index):
        self.page_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setStyleSheet(SIDEBAR_BTN_ACTIVE if i == index else SIDEBAR_BTN)

        # Handle logs timer
        if index == 1:
            self._log_paused = False
            self._log_pause_btn.setText("Pause")
            self._log_status.setText("\u25cf Live")
            self._log_status.setStyleSheet(f"color: {C['success']}; font-size: 12px; background: transparent;")
            self._refresh_logs()
            self._log_timer.start(15000)
        else:
            self._log_timer.stop()

        # Handle network tab — fetch on entry, refresh every 2 minutes while on page
        if index == 2:
            self._refresh_network_data()
            if not hasattr(self, '_network_timer') or self._network_timer is None:
                self._network_timer = QTimer()
                self._network_timer.timeout.connect(self._refresh_network_data)
            self._network_timer.start(120000)
        else:
            if hasattr(self, '_network_timer') and self._network_timer is not None:
                self._network_timer.stop()

    # ── Logs page methods ─────────────────────────────────

    def _toggle_log_pause(self):
        self._log_paused = not self._log_paused
        if self._log_paused:
            self._log_timer.stop()
            self._log_pause_btn.setText("Resume")
            self._log_status.setText("\u25cf Paused")
            self._log_status.setStyleSheet(f"color: {C['text_sec']}; font-size: 12px; background: transparent;")
        else:
            self._log_timer.start(15000)
            self._log_pause_btn.setText("Pause")
            self._log_status.setText("\u25cf Live")
            self._log_status.setStyleSheet(f"color: {C['success']}; font-size: 12px; background: transparent;")
            self._refresh_logs()

    def _refresh_logs(self):
        if self._log_thread is not None:
            try:
                if self._log_thread.isRunning():
                    return
            except RuntimeError:
                pass

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
        skip_phrases = [
            "initialized disabled sentry",
            "Thank you for running",
            "You're helping to strengthen"
        ]
        filtered = [line for line in logs.split('\n') if not any(p in line for p in skip_phrases)]

        self.log_text.setPlainText('\n'.join(filtered))
        self.log_text.moveCursor(QTextCursor.End)
        self.log_text.ensureCursorVisible()

        if self._log_thread is not None:
            self._log_thread.deleteLater()
            self._log_thread = None

    # ── Settings page methods ─────────────────────────────

    def _update_settings_ip(self):
        def get_ip():
            return self.node_manager.get_local_ip()

        def on_ip(ip):
            self._local_ip = ip
            self.ip_label.setText(ip)

        self._run_in_thread(get_ip, on_ip)

    def _copy_ip_settings(self):
        ip = getattr(self, '_local_ip', None)
        if ip:
            QApplication.clipboard().setText(ip)
            self.copy_ip_btn.setText("\u2713 Copied")
            QTimer.singleShot(2000, lambda: self.copy_ip_btn.setText("Copy"))

    # ── System tray ───────────────────────────────────────

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self._update_tray_icon("stopped")

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
        if self.isVisible():
            self.setVisible(False)
            self.tray_toggle_dashboard.setText("Show Dashboard")
        else:
            self.setVisible(True)
            self.showNormal()
            self.raise_()
            self.tray_toggle_dashboard.setText("Hide Dashboard")

    def _update_tray_ip(self):
        def get_ip():
            return self.node_manager.get_local_ip()

        def on_ip(ip):
            self._local_ip = ip
            self.tray_ip.setText(f"IP: {ip}  (click to copy)")

        self._run_in_thread(get_ip, on_ip)

    def _copy_ip_from_tray(self):
        ip = getattr(self, '_local_ip', None)
        if ip:
            QApplication.clipboard().setText(ip)
            self.tray_ip.setText(f"IP: {ip}  \u2713 Copied!")
            QTimer.singleShot(2000, lambda: self.tray_ip.setText(f"IP: {ip}  (click to copy)"))

    def _show_dashboard(self):
        self.setVisible(True)
        self.showNormal()
        self.raise_()

    def _update_tray_icon(self, state):
        if state == self._tray_state:
            return
        self._tray_state = state
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        if state == "running":
            color = C['success']
            tooltip = "ZecNode - Running"
        elif state == "no_internet":
            color = C['warning']
            tooltip = "ZecNode - No Internet"
        else:
            color = C['error']
            tooltip = "ZecNode - Stopped"
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        self.tray.setIcon(QIcon(pm))
        self.tray.setToolTip(tooltip)

    # ── Refresh logic ─────────────────────────────────────

    def _start_refresh(self):
        if self._closing:
            return
        # Note: intentionally NOT gated on isVisible() — ZecNode runs minimized to the
        # tray, and pausing refreshes there froze the status snapshot (stale data on
        # reopen) and the tray icon. get_status is cheap, so keep refreshing while hidden.
        if self._action_in_progress:
            return
        try:
            if self.refresh_thread is not None and self.refresh_thread.isRunning():
                return
        except RuntimeError:
            self.refresh_thread = None

        if self.refresh_thread is not None:
            try:
                self.refresh_thread.finished.disconnect()
            except:
                pass
            self.refresh_thread = None

        self.refresh_thread = RefreshThread(self.node_manager, self.config)
        self.refresh_thread.finished.connect(self._on_refresh_done)
        self.refresh_thread.start()

    def _remove_thread(self, thread):
        try:
            self._threads.remove(thread)
        except ValueError:
            pass

    def _on_refresh_done(self, status, has_internet, ssd, sd, lwd_running, arti_running):
        if self._closing:
            return
        first_refresh = not self._first_refresh_emitted
        if first_refresh:
            self._first_refresh_emitted = True
        if self._action_in_progress:
            if first_refresh:
                self.first_refresh_done.emit()
            return

        # Status — title bar
        if status.running and not has_internet:
            self.status_dot.set_state(StatusDot.STATE_NO_INTERNET)
            self.status_text.setText("No Internet")
            self.status_text.setStyleSheet(f"color: {C['warning']}; font-size: 12px; background: transparent;")
            self._update_tray_icon("no_internet")

            self.zebra_status_dot.set_state(StatusDot.STATE_NO_INTERNET)
            self.zebra_status_text.setText("No Internet")
            self.zebra_status_text.setStyleSheet(f"color: {C['warning']}; font-size: 12px; background: transparent; border: none;")

            self.lwd_status_dot.set_state(StatusDot.STATE_NO_INTERNET)

            self.peers_card.set_value("--")
            self.uptime_card.set_value("--:--:--")
            if first_refresh:
                self.first_refresh_done.emit()
            return
        elif status.running:
            self.status_dot.set_state(StatusDot.STATE_RUNNING)
            self.status_text.setText("Running")
            self.status_text.setStyleSheet(f"color: {C['success']}; font-size: 12px; background: transparent;")
            self._update_tray_icon("running")

            self.zebra_status_dot.set_state(StatusDot.STATE_RUNNING)
            self.zebra_status_text.setText("Running")
            self.zebra_status_text.setStyleSheet(f"color: {C['success']}; font-size: 12px; background: transparent; border: none;")

            if not self._zebra_version_fetched:
                self._fetch_zebra_version()
            if self._cached_zebra_version:
                self.zebra_version_label.setText(f"v{self._cached_zebra_version}")
                self.settings_zebra_label.setText(f"v{self._cached_zebra_version}")
        else:
            self.status_dot.set_state(StatusDot.STATE_STOPPED)
            self.status_text.setText("Stopped")
            self.status_text.setStyleSheet(f"color: {C['error']}; font-size: 12px; background: transparent;")
            self._update_tray_icon("stopped")

            self.zebra_status_dot.set_state(StatusDot.STATE_STOPPED)
            self.zebra_status_text.setText("Stopped")
            self.zebra_status_text.setStyleSheet(f"color: {C['error']}; font-size: 12px; background: transparent; border: none;")

            self.zebra_version_label.setText("")
            self._zebra_version_fetched = False

        # Stats
        self.peers_card.set_value(str(status.peer_count))
        self.uptime_card.set_value(status.uptime)

        self.ssd_card.set_value(ssd.split("/")[0].strip() if "/" in ssd else ssd)
        self.sd_card.set_value(sd.split("/")[0].strip() if "/" in sd else sd)

        # Sync
        sync_pct = min(status.sync_percent, 100.0)
        current_height = status.current_height

        if sync_pct > 0 or current_height > 0:
            self.config.set_deferred("cached_sync_percent", sync_pct)
            self.config.set_deferred("cached_height", current_height)
        elif status.running:
            sync_pct = self.config.get("cached_sync_percent", 0.0)
            current_height = self.config.get("cached_height", 0)

        bar_value = int(sync_pct) if sync_pct >= 1.0 else (1 if sync_pct > 0 else 0)
        self.sync_progress.setValue(bar_value)

        current = f"{current_height:,}" if current_height else "0"

        if sync_pct >= 99.9:
            self.sync_percent_label.setText("\u2713 Synced")
            self.sync_percent_label.setStyleSheet(
                f"color: {C['accent']}; background: transparent; border: none;"
            )
            if not isinstance(self.sync_percent_label.graphicsEffect(), QGraphicsDropShadowEffect):
                glow = QGraphicsDropShadowEffect(self.sync_percent_label)
                glow.setBlurRadius(28)
                glow.setColor(QColor(244, 183, 40, 180))
                glow.setOffset(0, 0)
                self.sync_percent_label.setGraphicsEffect(glow)
            self.sync_height_label.setText(f"Block {current}")
            self.sync_height_label.setStyleSheet(
                f"color: {C['text']}; font-size: 15px; font-weight: 600; background: transparent; border: none;"
            )
            self.sync_eta_label.setText("")
            self._sync_history = []
        else:
            self.sync_percent_label.setText(f"{sync_pct:.1f}%")
            self.sync_percent_label.setStyleSheet(
                f"color: {C['text']}; background: transparent; border: none;"
            )
            if self.sync_percent_label.graphicsEffect() is not None:
                self.sync_percent_label.setGraphicsEffect(None)
            self.sync_height_label.setText(f"Block {current}")
            self.sync_height_label.setStyleSheet(
                f"color: {C['text_muted']}; font-size: 13px; background: transparent; border: none;"
            )
            self._update_sync_eta(sync_pct, status.running)

        # Buttons
        self.restart_btn.setVisible(status.running)
        self.zebra_toggle.setChecked(status.running)
        if not self._action_in_progress:
            self.zebra_toggle.setEnabled(True)

        self.tray_stop.setVisible(status.running)
        self.tray_start.setVisible(not status.running)
        # Update handles its own stop/start — only block during in-flight actions.
        self.tray_update_zebra.setEnabled(not self._action_in_progress)
        self.update_zebra_btn.setEnabled(not self._action_in_progress)

        # Lightwalletd
        self._update_lightwalletd_ui(status, lwd_running)

        # Arti / Tor
        self._update_arti_ui(status, arti_running, lwd_running)

        # Persist snapshot so next startup looks instant
        self._save_status_snapshot(status, has_internet, ssd, sd, lwd_running, arti_running)

        if first_refresh:
            self.first_refresh_done.emit()

    def _update_lightwalletd_ui(self, zebra_status, lwd_running):
        lwd_enabled = self.config.get("lightwalletd_enabled", False)
        is_synced = zebra_status.running and zebra_status.sync_percent >= 99.9

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

        if self._lwd_action_in_progress:
            return

        if lwd_running:
            self.lwd_toggle.setChecked(True)
            self.lwd_status.setText("Running")
            self.lwd_status.setStyleSheet(f"color: {C['success']}; font-size: 11px; background: transparent; border: none;")
            self.lwd_status_dot.set_state(StatusDot.STATE_RUNNING)
            self.lwd_toggle.setEnabled(True)
        elif not zebra_status.running:
            self.lwd_toggle.setChecked(False)
            self.lwd_status.setText("Node stopped")
            self.lwd_status.setStyleSheet(f"color: {C['error']}; font-size: 11px; background: transparent; border: none;")
            self.lwd_status_dot.set_state(StatusDot.STATE_STOPPED)
            self.lwd_toggle.setEnabled(False)
        elif zebra_status.sync_percent < 99.9:
            self.lwd_toggle.setChecked(False)
            self.lwd_status.setText(f"Syncing ({zebra_status.sync_percent:.1f}%)")
            self.lwd_status.setStyleSheet(f"color: {C['text_sec']}; font-size: 11px; background: transparent; border: none;")
            self.lwd_status_dot.set_state(StatusDot.STATE_STOPPED)
            self.lwd_toggle.setEnabled(False)
        else:
            self.lwd_toggle.setChecked(False)
            self.lwd_status.setText("")
            self.lwd_status_dot.set_state(StatusDot.STATE_STOPPED)
            self.lwd_toggle.setEnabled(True)

    def _start_arti_and_fetch_onion(self):
        """Worker: start Arti and return (ok, onion). Config is written by the
        main-thread callback to avoid cross-thread config writes."""
        ok, _ = self.node_manager.start_arti()
        onion = self.node_manager.get_onion_address() if ok else None
        return ok, onion

    def _show_onion(self, onion):
        """Show or hide the .onion address row (shown as <onion>:443)."""
        if onion:
            self.arti_onion_label.setText(f"{onion}:443")
            self.arti_onion_row.setVisible(True)
        else:
            self.arti_onion_row.setVisible(False)

    def _update_arti_ui(self, zebra_status, arti_running, lwd_running):
        arti_enabled = self.config.get("arti_enabled", False)

        # Option A: keep the chain in sync with the user's intent.
        # Arti needs lightwalletd up (which needs Zebra synced), so it
        # auto-starts once lightwalletd is running and stops if it goes away.
        if not self._arti_auto_action_in_progress:
            if arti_enabled and lwd_running and not arti_running:
                self._arti_auto_action_in_progress = True

                def _auto_done(result):
                    self._arti_auto_action_in_progress = False
                    if self._closing:
                        return
                    ok, onion = result
                    if ok and onion:
                        self.config.set("arti_onion_address", onion)

                self._run_in_thread(self._start_arti_and_fetch_onion, _auto_done)
            elif arti_running and not lwd_running:
                self._arti_auto_action_in_progress = True
                self._run_in_thread(
                    lambda: self.node_manager.stop_arti(),
                    lambda result: setattr(self, '_arti_auto_action_in_progress', False)
                )

        if self._arti_action_in_progress:
            return

        # Toggle reflects ACTUAL running state and is gated on sync — same as
        # lightwalletd — so a restart shows it ON when Arti is live, and it can't
        # be flipped on before the node is synced.
        is_synced = zebra_status.running and zebra_status.sync_percent >= 99.9

        if arti_running:
            self.arti_toggle.setChecked(True)
            self.arti_toggle.setEnabled(True)
            self.arti_status_dot.set_state(StatusDot.STATE_RUNNING)
            self.arti_status.setText("Live on Tor")
            self.arti_status.setStyleSheet(f"color: {C['success']}; font-size: 11px; background: transparent; border: none;")
            onion = self.config.get("arti_onion_address", "")
            self._show_onion(onion)
            # Self-heal: Arti is running but we don't have the address cached yet
            # (e.g. the first-run fetch missed during the initial image pull).
            if not onion and not self._arti_onion_fetch_in_progress:
                self._arti_onion_fetch_in_progress = True

                def _onion_fetched(addr):
                    self._arti_onion_fetch_in_progress = False
                    if self._closing:
                        return
                    if addr:
                        self.config.set("arti_onion_address", addr)
                        self._show_onion(addr)

                self._run_in_thread(
                    lambda: self.node_manager.get_onion_address(),
                    _onion_fetched
                )
        elif not zebra_status.running:
            self.arti_toggle.setChecked(False)
            self.arti_toggle.setEnabled(False)
            self.arti_status_dot.set_state(StatusDot.STATE_STOPPED)
            self.arti_status.setText("Node stopped")
            self.arti_status.setStyleSheet(f"color: {C['error']}; font-size: 11px; background: transparent; border: none;")
            self._show_onion("")
        elif not is_synced:
            # Syncing — Tor can't start yet, so the toggle is disabled (matches lightwalletd).
            self.arti_toggle.setChecked(False)
            self.arti_toggle.setEnabled(False)
            self.arti_status_dot.set_state(StatusDot.STATE_STOPPED)
            self.arti_status.setText("Starts when synced")
            self.arti_status.setStyleSheet(f"color: {C['text_sec']}; font-size: 11px; background: transparent; border: none;")
            self._show_onion("")
        else:
            # Synced but Arti not running — toggle is available to flip on.
            self.arti_toggle.setChecked(False)
            self.arti_toggle.setEnabled(True)
            self.arti_status_dot.set_state(StatusDot.STATE_STOPPED)
            self.arti_status.setText("")
            self._show_onion("")

    # ── Node actions ──────────────────────────────────────

    def _stop(self):
        self._action_in_progress = True
        self.status_text.setText("Stopping...")
        self.status_text.setStyleSheet(f"color: {C['accent']}; font-size: 12px; background: transparent;")
        self.zebra_status_text.setText("Stopping...")
        self.zebra_status_text.setStyleSheet(f"color: {C['accent']}; font-size: 12px; background: transparent; border: none;")
        self.restart_btn.setEnabled(False)
        self.zebra_toggle.setEnabled(False)
        self._run_action("stop")

    def _start(self):
        self._action_in_progress = True
        self.status_text.setText("Starting...")
        self.status_text.setStyleSheet(f"color: {C['accent']}; font-size: 12px; background: transparent;")
        self.zebra_status_text.setText("Starting...")
        self.zebra_status_text.setStyleSheet(f"color: {C['accent']}; font-size: 12px; background: transparent; border: none;")
        self.zebra_toggle.setEnabled(False)
        self._run_action("start")

    def _restart(self):
        self._action_in_progress = True
        self.status_text.setText("Restarting...")
        self.status_text.setStyleSheet(f"color: {C['accent']}; font-size: 12px; background: transparent;")
        self.zebra_status_text.setText("Restarting...")
        self.zebra_status_text.setStyleSheet(f"color: {C['accent']}; font-size: 12px; background: transparent; border: none;")
        self.restart_btn.setEnabled(False)
        self.zebra_toggle.setEnabled(False)
        self._run_action("restart")

    def _run_action(self, action):
        self._last_action = action
        if hasattr(self, 'action_thread') and self.action_thread is not None:
            try:
                if self.action_thread.isRunning():
                    return
            except RuntimeError:
                pass
        lwd_enabled = self.config.get("lightwalletd_enabled", False)
        self.action_thread = NodeActionThread(action, self.node_manager, lwd_enabled)
        self.action_thread.finished.connect(self._on_action_done)
        self.action_thread.start()

    def _on_action_done(self, ok, msg):
        self._action_in_progress = False
        self.restart_btn.setEnabled(True)
        self.zebra_toggle.setEnabled(True)

        if not ok:
            action = getattr(self, '_last_action', None)
            headline, summary, details = self._friendly_action_error(action, msg)
            ErrorDialog(self, headline, summary, details).exec_()
        self._start_refresh()

    @staticmethod
    def _friendly_action_error(action, msg):
        """Turn a node action failure into (headline, summary, details).

        Short, already-readable messages from node_manager (e.g. "SSD not
        mounted…") are shown as-is; long/raw output (Docker stderr) is replaced
        with a calm summary and tucked into the details pane."""
        headlines = {
            "start":   "Couldn't start the node",
            "stop":    "Couldn't stop the node",
            "restart": "Couldn't restart the node",
        }
        verbs = {"start": "starting", "stop": "stopping", "restart": "restarting"}
        headline = headlines.get(action, "Something went wrong")
        msg = (msg or "").strip()

        # A short, single-line message is almost always the friendly, actionable
        # one node_manager raises on purpose — surface it directly.
        if msg and len(msg) <= 160 and "\n" not in msg:
            return headline, msg, None

        summary = (
            f"Something went wrong while {verbs.get(action, 'working')}. "
            "This is usually temporary — make sure Docker is running, then try again."
        )
        return headline, summary, (msg or None)

    # ── Version & price ───────────────────────────────────

    def _fetch_zebra_version(self):
        if getattr(self, '_zebra_version_fetch_in_flight', False):
            return
        self._zebra_version_fetch_in_flight = True

        def get_version():
            return self.node_manager.get_zebra_version(self.config)

        def on_version_done(version):
            self._zebra_version_fetch_in_flight = False
            if version and version != "--":
                self._cached_zebra_version = version
                self.zebra_version_label.setText(f"v{version}")
                self.settings_zebra_label.setText(f"v{version}")
                self.config.set("cached_zebra_version", version)
                self.config.save()
                self._zebra_version_fetched = True

        self._run_in_thread(get_version, on_version_done)

    def _set_network_status(self, text, color=None):
        """Update the Network tab freshness line."""
        if getattr(self, 'net_status_label', None) is None:
            return
        self.net_status_label.setText(text)
        self.net_status_label.setStyleSheet(
            f"color: {color or C['text_sec']}; font-size: 11px; background: transparent;"
        )

    def _refresh_network_data(self):
        """Fetch network info + shielded supply history from zcashinfo.com."""
        if self._closing:
            return

        # On the very first fetch the cards are empty — show a loading placeholder
        # rather than dashes. On later refreshes keep the last-known values visible
        # so the page never blinks back to blank while updating.
        first_load = not getattr(self, '_network_loaded', False)
        if first_load:
            for card in (self.net_height_card, self.net_hashrate_card,
                         self.net_supply_card, self.net_shielded_pct_card):
                card.set_value("…")
        self._set_network_status("Updating…", C['text_sec'])

        def fetch():
            import urllib.request, json as _json
            headers = {'User-Agent': 'ZecNode/1.0'}
            result = {
                "info": None, "pools": None, "history": None,
                "mining_history": None, "error": None,
            }
            try:
                req = urllib.request.Request("https://api.zcashinfo.com/api/v1/info", headers=headers)
                with urllib.request.urlopen(req, timeout=10) as r:
                    result["info"] = _json.loads(r.read().decode())
            except Exception as e:
                result["error"] = str(e)
            try:
                req = urllib.request.Request("https://api.zcashinfo.com/api/v1/coin-pools", headers=headers)
                with urllib.request.urlopen(req, timeout=10) as r:
                    result["pools"] = _json.loads(r.read().decode())
            except Exception:
                pass
            try:
                req = urllib.request.Request("https://api.zcashinfo.com/api/v1/coin-pools/history", headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    result["history"] = _json.loads(r.read().decode())
            except Exception:
                pass
            try:
                req = urllib.request.Request("https://api.zcashinfo.com/api/v1/mining/history", headers=headers)
                with urllib.request.urlopen(req, timeout=10) as r:
                    result["mining_history"] = _json.loads(r.read().decode())
            except Exception:
                pass
            return result

        def on_done(result):
            if self._closing:
                return
            info = result.get("info") or {}
            pools = result.get("pools") or {}
            history = result.get("history") or []
            mining_history = result.get("mining_history") or {}

            # Primary endpoint failed — show a clear stale/failed state instead of
            # silently swallowing the error and leaving dashes on screen.
            if not info:
                if getattr(self, '_network_loaded', False):
                    self._set_network_status(
                        "Couldn't refresh — showing last known data", C['warning'])
                else:
                    for card in (self.net_height_card, self.net_hashrate_card,
                                 self.net_supply_card, self.net_shielded_pct_card):
                        card.set_value("--")
                    self._set_network_status(
                        "Couldn't load network data — will retry", C['error'])
                return

            self._network_loaded = True

            if info:
                height = info.get("best_block") or info.get("chain_tip") or 0
                self.net_height_card.set_value(f"{height:,}")

            buckets = mining_history.get("buckets") or []
            if buckets:
                latest = buckets[-1]
                sols_per_sec = latest.get("avg_network_hashrate_sols") or 0
                self.net_hashrate_card.set_value(self._format_hashrate(sols_per_sec))

            if pools:
                total_zat = pools.get("total_supply_zatoshis") or 0
                total_zec = total_zat / 1e8
                self.net_supply_card.set_value(f"{total_zec/1e6:.2f}M ZEC")

                shielded_zat = (
                    (pools.get("sapling_zatoshis") or 0)
                    + (pools.get("orchard_zatoshis") or 0)
                    + (pools.get("sprout_zatoshis") or 0)
                )
                shielded_zec = shielded_zat / 1e8
                if total_zat > 0:
                    pct = shielded_zat / total_zat * 100
                    self.net_shielded_pct_card.set_value(f"{pct:.1f}%")
                self.net_shielded_total_label.setText(f"{shielded_zec/1e6:.3f}M ZEC")

            if history:
                self.shielded_chart.set_data(history)

            import time as _time
            self._set_network_status(
                f"Updated {_time.strftime('%H:%M')}", C['success'])

        self._run_in_thread(fetch, on_done)

    @staticmethod
    def _format_compact(n):
        """Format a large number compactly, e.g. 131,962,257 -> 131.96M."""
        try:
            n = float(n)
        except (TypeError, ValueError):
            return "--"
        if n >= 1e12:
            return f"{n/1e12:.2f}T"
        if n >= 1e9:
            return f"{n/1e9:.2f}B"
        if n >= 1e6:
            return f"{n/1e6:.2f}M"
        if n >= 1e3:
            return f"{n/1e3:.2f}K"
        return f"{n:.0f}"

    def _save_status_snapshot(self, status, has_internet, ssd, sd, lwd_running, arti_running=False):
        """Persist the current status so the next startup can paint it immediately.
        Deferred + throttled to ~once per minute to spare the SD card."""
        try:
            snap = {
                "running": bool(status.running),
                "peer_count": int(status.peer_count or 0),
                "uptime": str(status.uptime or ""),
                "sync_percent": float(status.sync_percent or 0.0),
                "current_height": int(status.current_height or 0),
                "has_internet": bool(has_internet),
                "ssd": str(ssd or "--"),
                "sd": str(sd or "--"),
                "lwd_running": bool(lwd_running),
                "arti_running": bool(arti_running),
            }
            self.config.set_deferred("status_snapshot", snap)
            self.config.save_throttled(60.0)
        except Exception:
            pass

    def _apply_cached_status(self):
        """Paint the dashboard with the last saved snapshot. Runs once on init."""
        snap = self.config.get("status_snapshot", None)
        if not isinstance(snap, dict):
            return

        running = snap.get("running", False)

        # A cached "stopped" snapshot is treated as unknown, not painted. The node
        # normally keeps running while the app is closed, so a stopped snapshot is
        # usually just stale — painting it would flash a wrong "0% / stopped" state.
        # Keep the "Loading…" placeholder and let the first live refresh paint the
        # truth (a few seconds). A running snapshot is safe to restore instantly.
        if not running:
            return

        has_internet = snap.get("has_internet", True)
        peer_count = snap.get("peer_count", 0)
        uptime = snap.get("uptime", "--:--:--")
        sync_pct = float(snap.get("sync_percent", 0.0))
        current_height = int(snap.get("current_height", 0))
        ssd = snap.get("ssd", "--")
        sd = snap.get("sd", "--")
        lwd_running = snap.get("lwd_running", False)
        arti_running = snap.get("arti_running", False)

        # Title-bar + Zebra dots
        if running and not has_internet:
            self.status_dot.set_state(StatusDot.STATE_NO_INTERNET)
            self.zebra_status_dot.set_state(StatusDot.STATE_NO_INTERNET)
            self.lwd_status_dot.set_state(StatusDot.STATE_NO_INTERNET)
        elif running:
            self.status_dot.set_state(StatusDot.STATE_RUNNING)
            self.zebra_status_dot.set_state(StatusDot.STATE_RUNNING)
            self.lwd_status_dot.set_state(
                StatusDot.STATE_RUNNING if lwd_running else StatusDot.STATE_STOPPED
            )
        else:
            self.status_dot.set_state(StatusDot.STATE_STOPPED)
            self.zebra_status_dot.set_state(StatusDot.STATE_STOPPED)
            self.lwd_status_dot.set_state(StatusDot.STATE_STOPPED)

        if self._cached_zebra_version:
            self.zebra_version_label.setText(f"v{self._cached_zebra_version}")

        # Zebra toggle and restart visibility
        self.zebra_toggle.setChecked(running)
        self.restart_btn.setVisible(running)
        self.lwd_toggle.setChecked(lwd_running)

        # Arti / Tor — toggle reflects ACTUAL running state (like lightwalletd), so a
        # restart shows it ON when Arti is live; show .onion if it was live.
        self.arti_toggle.setChecked(arti_running)
        self.arti_status_dot.set_state(
            StatusDot.STATE_RUNNING if arti_running else StatusDot.STATE_STOPPED
        )
        self._show_onion(self.config.get("arti_onion_address", "") if arti_running else "")

        # Stats footer
        self.peers_card.set_value(str(peer_count) if running else "--")
        self.uptime_card.set_value(uptime if running else "--:--:--")
        self.ssd_card.set_value(ssd.split("/")[0].strip() if "/" in ssd else ssd)
        self.sd_card.set_value(sd.split("/")[0].strip() if "/" in sd else sd)

        # Sync hero
        bar_value = int(sync_pct) if sync_pct >= 1.0 else (1 if sync_pct > 0 else 0)
        self.sync_progress.setValue(bar_value)
        current = f"{current_height:,}" if current_height else "0"
        if sync_pct >= 99.9:
            self.sync_percent_label.setText("\u2713 Synced")
            self.sync_percent_label.setStyleSheet(
                f"color: {C['accent']}; background: transparent; border: none;"
            )
            self.sync_height_label.setText(f"Block {current}")
            self.sync_height_label.setStyleSheet(
                f"color: {C['text']}; font-size: 15px; font-weight: 600; background: transparent; border: none;"
            )
        else:
            self.sync_percent_label.setText(f"{sync_pct:.1f}%")
            self.sync_percent_label.setStyleSheet(
                f"color: {C['text']}; background: transparent; border: none;"
            )
            self.sync_height_label.setText(f"Block {current}")
            self.sync_height_label.setStyleSheet(
                f"color: {C['text_muted']}; font-size: 13px; background: transparent; border: none;"
            )

        # Tray icon
        if running and not has_internet:
            self._update_tray_icon("no_internet")
        elif running:
            self._update_tray_icon("running")
        else:
            self._update_tray_icon("stopped")

    def _check_for_updates(self, force=False):
        """Check GitHub for a newer ZecNode release. Cached via config.
        Periodic checks (the 3h timer) are throttled to 2h; `force` (used on
        launch) bypasses that, with a 60s floor to avoid hammering on rapid restarts."""
        if self._closing:
            return

        import time as _time
        now = int(_time.time())
        last_check = self.config.get("last_update_check", 0)
        min_interval = 60 if force else 2 * 3600
        if now - last_check < min_interval:
            # Use cached result
            tag = self.config.get("latest_release_tag", "")
            notes = self.config.get("latest_release_notes", "")
            if tag:
                self._apply_release_info(tag, notes)
            return

        def fetch():
            import urllib.request, json as _json
            try:
                req = urllib.request.Request(
                    "https://api.github.com/repos/mycousiinvinny/zecnode/releases/latest",
                    headers={
                        'User-Agent': 'ZecNode/1.0',
                        'Accept': 'application/vnd.github+json',
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    return _json.loads(r.read().decode())
            except Exception:
                return None

        def on_done(release):
            if self._closing or not release:
                return
            tag = (release.get("tag_name") or "").lstrip("v")
            notes = release.get("body") or ""
            self.config.set("last_update_check", now)
            self.config.set("latest_release_tag", tag)
            self.config.set("latest_release_notes", notes)
            self.config.save()
            self._apply_release_info(tag, notes)

        self._run_in_thread(fetch, on_done)

    def _apply_release_info(self, tag, notes):
        """Given the latest release tag, toggle the update badge + store notes."""
        self._latest_release_tag = tag
        self._latest_release_notes = notes
        newer = tag and self._is_newer_version(tag, VERSION)
        self._update_available = bool(newer)
        self._refresh_update_badge()

    def _refresh_update_badge(self):
        """Toggle the gold-dot badge on the Settings nav button and Update ZecNode button."""
        # Settings sidebar button is index 4 (Dashboard, Logs, Network, Learn, Settings)
        try:
            settings_btn = self._nav_buttons[4]
            base = "  Settings"
            settings_btn.setText(f"{base}  \u2022" if self._update_available else base)
        except (IndexError, AttributeError):
            pass

        # Update ZecNode button in the Settings page
        btn = getattr(self, "_update_zecnode_btn", None)
        if btn is not None:
            base = "Update"
            btn.setText(f"{base}  \u2022" if self._update_available else base)

        # What's new label
        whats_new = getattr(self, "_whats_new_label", None)
        if whats_new is not None:
            if self._update_available and self._latest_release_tag:
                whats_new.setText(
                    f'<a href="#whatsnew" style="color: {C["accent"]}; text-decoration: none;">'
                    f"What's new in v{self._latest_release_tag} \u2192</a>"
                )
                whats_new.setVisible(True)
            else:
                whats_new.setVisible(False)

    @staticmethod
    def _is_newer_version(candidate, current):
        def parse(v):
            try:
                return tuple(int(x) for x in str(v).lstrip("v").split(".") if x.isdigit())
            except Exception:
                return (0,)
        return parse(candidate) > parse(current)

    def _show_release_notes(self):
        tag = self._latest_release_tag or "?"
        notes = self._latest_release_notes or "(no release notes available)"

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        dlg.setModal(True)
        dlg.setFixedSize(520, 420)
        dlg.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(dlg)
        container.setGeometry(0, 0, 520, 420)
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {C['surface']};
                border: 1px solid {C['border']};
                border-radius: 12px;
            }}
        """)

        v = QVBoxLayout(container)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel(f"What's new in v{tag}")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet(f"color: {C['accent']}; background: transparent; border: none;")
        header_row.addWidget(title)
        header_row.addStretch()

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {C['text_muted']}; font-size: 14px; min-width: 0; padding: 0;
            }}
            QPushButton:hover {{ color: {C['text']}; }}
        """)
        close_btn.clicked.connect(dlg.accept)
        header_row.addWidget(close_btn)
        v.addLayout(header_row)

        body = QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(notes)
        body.setStyleSheet(f"""
            QTextEdit {{
                background-color: {C['background'] if 'background' in C else '#08080c'};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 12px;
                color: {C['text']};
                font-size: 12px;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }}
        """)
        v.addWidget(body, 1)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedHeight(32)
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['accent']}; color: #0a0a0e; border: none;
                border-radius: 6px; font-size: 12px; font-weight: 600;
                padding: 0 24px; min-width: 0;
            }}
            QPushButton:hover {{ background-color: {C['accent_hover']}; }}
        """)
        ok_btn.clicked.connect(dlg.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        v.addLayout(btn_row)

        dlg.exec_()

    def _update_sync_eta(self, sync_pct, running):
        """Append a sync sample and, if enough data is available, show an ETA."""
        if not running or sync_pct <= 0:
            self.sync_eta_label.setText("")
            return

        import time as _time
        now = _time.time()
        # Keep last 30 minutes of samples
        self._sync_history = [
            (t, p) for (t, p) in self._sync_history if now - t < 1800
        ]
        self._sync_history.append((now, sync_pct))

        if len(self._sync_history) < 2:
            self.sync_eta_label.setText("Calculating ETA…")
            return

        oldest_t, oldest_pct = self._sync_history[0]
        span_t = now - oldest_t
        span_pct = sync_pct - oldest_pct

        if span_t < 30 or span_pct <= 0:
            self.sync_eta_label.setText("Calculating ETA…")
            return

        pct_per_sec = span_pct / span_t
        remaining_pct = 100.0 - sync_pct
        eta_sec = remaining_pct / pct_per_sec
        self.sync_eta_label.setText(f"~{self._format_duration(eta_sec)} until synced")

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        if seconds < 86400:
            h, m = divmod(seconds // 60, 60)
            return f"{h}h {m}m" if m else f"{h}h"
        d, rem = divmod(seconds, 86400)
        h = rem // 3600
        return f"{d}d {h}h" if h else f"{d}d"

    @staticmethod
    def _format_hashrate(sols_per_sec):
        """Format Equihash solutions/second into the right SI scale.
        Zcash uses Equihash, so the unit is Sol/s (not H/s).
        """
        try:
            s = float(sols_per_sec)
        except (TypeError, ValueError):
            return "--"
        if s >= 1e15:
            return f"{s/1e15:.2f} PSol/s"
        if s >= 1e12:
            return f"{s/1e12:.2f} TSol/s"
        if s >= 1e9:
            return f"{s/1e9:.2f} GSol/s"
        if s >= 1e6:
            return f"{s/1e6:.2f} MSol/s"
        if s >= 1e3:
            return f"{s/1e3:.2f} kSol/s"
        return f"{s:.0f} Sol/s"

    def _fetch_price(self):
        if self._closing:
            return
        try:
            if self.price_thread is not None and self.price_thread.isRunning():
                return
        except RuntimeError:
            self.price_thread = None

        if self.price_thread is not None:
            try:
                self.price_thread.finished.disconnect()
            except:
                pass
            self.price_thread = None

        self.price_thread = PriceThread()
        self.price_thread.finished.connect(self._on_price_done)
        self.price_thread.start()

    def _on_price_done(self, price, change, chart_data):
        if self._closing:
            return

        if price is not None:
            self.price_label.setText(f"${price:,.2f}")

            positive = True
            if change is not None:
                if change >= 0:
                    self.change_label.setText(f"\u25b2 {change:.2f}%")
                    self.change_label.setStyleSheet(f"color: {C['success']}; font-size: 10px; background: transparent;")
                    positive = True
                else:
                    self.change_label.setText(f"\u25bc {abs(change):.2f}%")
                    self.change_label.setStyleSheet(f"color: {C['error']}; font-size: 10px; background: transparent;")
                    positive = False

            if chart_data and len(chart_data) > 2:
                self.sparkline.set_data(chart_data, positive)

    # ── Updates ───────────────────────────────────────────

    def _update_zecnode(self):
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
        dialog = ConfirmDialog(
            self,
            "Update Zebra",
            "Download and install the latest Zebra version?\n\n"
            "Zebra will automatically stop, update, and restart.\n\n"
            "Warning: Major updates may require a full resync of the blockchain."
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        # Force a re-query of the Zebra version after the update finishes —
        # otherwise the dashboard would keep showing the pre-update cached version.
        self._zebra_version_fetched = False

        self.update_dialog = UpdateDialog(self, "Updating Zebra...")
        self.update_dialog.show()

        data_path = self.config.get_data_path() if hasattr(self.config, 'get_data_path') else "/mnt/zebra-data"
        zebra_version = "latest"
        self.update_thread = UpdateThread("zebra", data_path, zebra_version)
        self.update_thread.finished.connect(self._on_update_done)
        self.update_thread.start()

    def _update_lightwalletd_image(self):
        dialog = ConfirmDialog(
            self,
            "Update Lightwalletd",
            "Download and install the latest Lightwalletd image?\n\n"
            "If Lightwalletd is running it will briefly restart."
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        self.update_dialog = UpdateDialog(self, "Updating Lightwalletd...")
        self.update_dialog.show()

        self.update_thread = UpdateThread("lightwalletd")
        self.update_thread.finished.connect(self._on_update_done)
        self.update_thread.start()

    def _on_update_done(self, success, message):
        if hasattr(self, 'update_dialog'):
            self.update_dialog.close()

        if success:
            if message.startswith("LWD_UPDATED|"):
                # Format: LWD_UPDATED|<was_running 0/1>|<human_message>
                _, was_running_str, human = message.split("|", 2)
                was_running = was_running_str == "1"
                if was_running:
                    # Restart LWD via the normal node_manager path to pick up the new image
                    def restart_lwd():
                        return self.node_manager.start_lightwalletd()
                    def on_restarted(_result):
                        MessageDialog(self, "Update Complete",
                                      human.replace(" Restarting container…", ""),
                                      is_error=False).exec_()
                        self._start_refresh()
                    self._run_in_thread(restart_lwd, on_restarted)
                else:
                    MessageDialog(self, "Update Complete", human, is_error=False).exec_()
                    self._start_refresh()
                return

            if message == "RESTART_ZECNODE":
                import subprocess
                import sys
                home = os.path.expanduser("~")
                main_py = os.path.join(home, "zecnode", "main.py")
                self.tray.hide()
                QApplication.processEvents()
                subprocess.Popen([sys.executable, main_py], cwd=os.path.join(home, "zecnode"))
                os._exit(0)
            else:
                # Re-arm version-cache reset; the one in _update_zebra gets
                # clobbered by polls firing during the update window.
                self._zebra_version_fetched = False
                dialog = MessageDialog(self, "Update Complete", message, is_error=False)
                dialog.exec_()
        else:
            dialog = MessageDialog(self, "Update Failed", message, is_error=True)
            dialog.exec_()

        self._start_refresh()

    # ── Zebra toggle ──────────────────────────────────────

    def _toggle_zebra_from_toggle(self, checked):
        if checked:
            self._start()
        else:
            self._stop()

    # ── Lightwalletd toggle ───────────────────────────────

    def _toggle_lightwalletd_from_toggle(self, checked):
        self._toggle_lightwalletd(checked)

    def _toggle_lightwalletd(self, checked=None):
        if checked is None:
            checked = self.lwd_toggle.isChecked()
        if checked:
            self._lwd_action_in_progress = True
            self.lwd_toggle.setEnabled(False)
            self.lwd_status.setText("Starting...")
            self.lwd_status.setStyleSheet(f"color: {C['accent']}; font-size: 11px; background: transparent; border: none;")

            def start_lwd():
                success, msg = self.node_manager.start_lightwalletd()
                return success, msg

            def on_start_done(result):
                self._lwd_action_in_progress = False
                success, msg = result
                if success:
                    self.lwd_status.setText("Running")
                    self.lwd_status.setStyleSheet(f"color: {C['success']}; font-size: 11px; background: transparent; border: none;")
                    self.config.set("lightwalletd_enabled", True)
                else:
                    self.lwd_toggle.setChecked(False)
                    self.lwd_status.setText(f"Error: {msg}")
                    self.lwd_status.setStyleSheet(f"color: {C['error']}; font-size: 11px; background: transparent; border: none;")
                self.lwd_toggle.setEnabled(True)

            self._run_in_thread(start_lwd, on_start_done)
        else:
            self._lwd_action_in_progress = True
            self.lwd_toggle.setEnabled(False)
            self.lwd_status.setText("Stopping...")
            self.lwd_status.setStyleSheet(f"color: {C['accent']}; font-size: 11px; background: transparent; border: none;")

            def stop_lwd():
                self.node_manager.stop_lightwalletd()
                return True

            def on_stop_done(result):
                self._lwd_action_in_progress = False
                self.lwd_toggle.setEnabled(True)
                self.lwd_status.setText("")
                self.config.set("lightwalletd_enabled", False)

            self._run_in_thread(stop_lwd, on_stop_done)

    def _copy_onion(self):
        onion = self.config.get("arti_onion_address", "")
        if onion:
            QApplication.clipboard().setText(f"{onion}:443")
            self.arti_copy_btn.setText("Copied!")
            QTimer.singleShot(1500, lambda: self.arti_copy_btn.setText("Copy")
                              if not self._closing else None)

    def _show_onion_qr(self):
        """Pop up a scannable QR of THIS node's own .onion address (read live
        from config), so a phone wallet can grab the long string without typing.

        The QR is rendered by the system 'qrencode' tool, which can take a few
        seconds (or hang on a missing binary), so it runs in a worker thread: the
        dialog opens instantly with a 'Generating…' placeholder and fills in once
        the image is ready."""
        onion = self.config.get("arti_onion_address", "")
        if not onion:
            return
        data = f"{onion}:443"

        dlg = QDialog(self)
        # Frameless to match the app's other dialogs (no native title-bar buttons);
        # the Close button below is the single way out.
        dlg.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        # Application-modal but shown via show() (not exec_) so we don't block the
        # event loop while qrencode runs — the worker can still update this dialog.
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setStyleSheet(f"QDialog {{ background-color: {C['surface']}; "
                          f"border: 1px solid {C['accent']}; }}")
        v = QVBoxLayout(dlg)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)

        title = QLabel("Scan with your phone")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet(f"color: {C['text']}; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)

        # Body swaps from placeholder → QR image (or install hint) when ready.
        body = QLabel("Generating QR…")
        body.setMinimumSize(180, 180)
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {C['text_sec']}; font-size: 12px; background: transparent;")
        v.addWidget(body, 0, Qt.AlignCenter)

        addr = QLabel(data)
        addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        addr.setWordWrap(True)
        addr.setAlignment(Qt.AlignCenter)
        addr.setStyleSheet(f"color: {C['text_sec']}; font-size: 11px; "
                           f"font-family: monospace; background: transparent;")
        addr.hide()
        v.addWidget(addr)

        hint = QLabel("Scan, then paste into your wallet's custom-server field.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; background: transparent;")
        hint.hide()
        v.addWidget(hint)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['accent']}; color: #1a1a1a;
                border: none; border-radius: 6px; padding: 8px 20px; font-weight: 600;
            }}
        """)
        close_btn.clicked.connect(dlg.accept)
        v.addWidget(close_btn, 0, Qt.AlignCenter)

        # Keep a reference so the dialog isn't garbage-collected while shown.
        self._qr_dialog = dlg
        dlg.finished.connect(lambda *_: setattr(self, '_qr_dialog', None))

        def generate():
            import subprocess
            try:
                result = subprocess.run(
                    # -m 4: a full 4-module white quiet zone baked into the image so
                    # the code scans without relying on extra CSS padding.
                    ["qrencode", "-o", "-", "-t", "PNG", "-s", "7", "-m", "4", data],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0 and result.stdout:
                    return result.stdout
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass
            return None

        def on_qr_done(png):
            if self._closing or self._qr_dialog is not dlg:
                return
            if png:
                pm = QPixmap()
                pm.loadFromData(png)
                # Pin the label to the pixmap's exact (square) size and clear the
                # placeholder's word-wrap / min-size / scaling so nothing can stretch
                # the QR — a distorted, non-square code won't scan.
                body.setText("")
                body.setWordWrap(False)
                body.setScaledContents(False)
                body.setMinimumSize(0, 0)
                body.setFixedSize(pm.size())
                body.setPixmap(pm)
                # White card behind the QR so it scans on the dark theme. No padding:
                # the quiet zone is baked into the image (qrencode -m 4) and padding
                # would clip the fixed-size pixmap.
                body.setStyleSheet("background: white; border-radius: 8px;")
                addr.show()
                hint.show()
            else:
                body.setText("QR generator isn't installed.\n\nInstall it once with:\n"
                             "sudo apt install qrencode")
                body.setStyleSheet(f"color: {C['text_sec']}; font-size: 12px; background: transparent;")
            dlg.adjustSize()

        dlg.show()
        self._run_in_thread(generate, on_qr_done)

    def _toggle_arti_from_toggle(self, checked):
        self._toggle_arti(checked)

    def _toggle_arti(self, checked=None):
        if checked is None:
            checked = self.arti_toggle.isChecked()
        if checked:
            self._arti_action_in_progress = True
            self.arti_toggle.setEnabled(False)
            self.config.set("arti_enabled", True)
            self.arti_status.setText("Starting Tor...")
            self.arti_status.setStyleSheet(f"color: {C['accent']}; font-size: 11px; background: transparent; border: none;")

            def start_arti():
                ok, msg = self.node_manager.start_arti()
                onion = self.node_manager.get_onion_address() if ok else None
                return ok, msg, onion

            def on_start_done(result):
                self._arti_action_in_progress = False
                if self._closing:
                    return
                ok, msg, onion = result
                if ok:
                    self.arti_status_dot.set_state(StatusDot.STATE_RUNNING)
                    self.arti_status.setText("Live on Tor")
                    self.arti_status.setStyleSheet(f"color: {C['success']}; font-size: 11px; background: transparent; border: none;")
                    if onion:
                        self.config.set("arti_onion_address", onion)
                        self._show_onion(onion)
                else:
                    self.arti_status.setText(f"Error: {msg}")
                    self.arti_status.setStyleSheet(f"color: {C['error']}; font-size: 11px; background: transparent; border: none;")
                self.arti_toggle.setEnabled(True)

            self._run_in_thread(start_arti, on_start_done)
        else:
            self._arti_action_in_progress = True
            self.arti_toggle.setEnabled(False)
            self.config.set("arti_enabled", False)
            self.arti_status.setText("Stopping...")
            self.arti_status.setStyleSheet(f"color: {C['accent']}; font-size: 11px; background: transparent; border: none;")

            def stop_arti():
                self.node_manager.stop_arti()
                return True

            def on_stop_done(result):
                self._arti_action_in_progress = False
                if self._closing:
                    return
                self.arti_toggle.setEnabled(True)
                self.arti_status.setText("")
                self.arti_status_dot.set_state(StatusDot.STATE_STOPPED)
                self._show_onion("")

            self._run_in_thread(stop_arti, on_stop_done)

    # ── Utilities ─────────────────────────────────────────

    def _run_in_thread(self, func, callback):
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

    def _reset_zecnode(self):
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

            if os.path.exists(config_dir):
                shutil.rmtree(config_dir)
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)

            self.tray.hide()
            QApplication.processEvents()
            os.execv(sys.executable, [sys.executable, os.path.expanduser("~/zecnode/main.py")])

    # ── Shutdown ──────────────────────────────────────────

    def _shutdown(self):
        if self._closing:
            return
        self._closing = True

        print("[ZecNode] Shutting down...")

        # Flush any deferred config writes before we exit.
        try:
            self.config.flush()
        except Exception:
            pass

        self.timer.stop()
        self.price_timer.stop()
        self._log_timer.stop()

        if self.refresh_thread is not None:
            self.refresh_thread.stop()

        self.tray.hide()
        QTimer.singleShot(3000, lambda: os._exit(0))
        QApplication.quit()

    def _quit(self):
        self._shutdown()

    def closeEvent(self, event):
        self._shutdown()
        event.accept()

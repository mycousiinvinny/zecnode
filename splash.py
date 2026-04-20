"""ZecNode welcome splash screen shown while the dashboard loads its first status."""

import os

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, pyqtSignal, QRect
from PyQt5.QtGui import QPixmap, QRegion
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect
)

from config import VERSION


ACCENT = "#f4b728"
BG = "#0a0a0e"
TEXT = "#e8e8ec"
TEXT_MUTED = "#8b8b96"


class SplashScreen(QWidget):
    """Frameless welcome screen. Emits finished() after fade-out completes."""

    MIN_DISPLAY_MS = 1200
    FADE_MS = 400
    SAFETY_DISMISS_MS = 15000

    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(480, 360)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG};
                color: {TEXT};
            }}
            QLabel {{
                background: transparent;
            }}
        """)

        self._dismiss_requested = False
        self._min_elapsed = False
        self._finished_emitted = False
        self._fade_started = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 48, 40, 36)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zecnode-icon.png")
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        if os.path.exists(icon_path):
            pm = QPixmap(icon_path).scaled(
                128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            logo.setPixmap(pm)
        layout.addWidget(logo)

        layout.addSpacing(4)

        title = QLabel("Welcome to ZecNode")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {ACCENT}; font-size: 22px; font-weight: 600; letter-spacing: 0.5px;"
        )
        layout.addWidget(title)

        tagline = QLabel("Your Zcash node, simplified.")
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        layout.addWidget(tagline)

        layout.addStretch()

        ver = QLabel(f"v{VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(ver)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        QTimer.singleShot(self.MIN_DISPLAY_MS, self._on_min_elapsed)
        # Safety net: never let the splash block the dashboard indefinitely.
        QTimer.singleShot(self.SAFETY_DISMISS_MS, self.request_dismiss)

    def showEvent(self, event):
        super().showEvent(event)
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h, r = self.width(), self.height(), 18
        # Rounded rect as union of two crossed rects + four corner circles.
        region = QRegion(r, 0, w - 2 * r, h, QRegion.Rectangle)
        region = region.united(QRegion(0, r, w, h - 2 * r, QRegion.Rectangle))
        region = region.united(QRegion(0, 0, 2 * r, 2 * r, QRegion.Ellipse))
        region = region.united(QRegion(w - 2 * r, 0, 2 * r, 2 * r, QRegion.Ellipse))
        region = region.united(QRegion(0, h - 2 * r, 2 * r, 2 * r, QRegion.Ellipse))
        region = region.united(QRegion(w - 2 * r, h - 2 * r, 2 * r, 2 * r, QRegion.Ellipse))
        self.setMask(region)

    def request_dismiss(self):
        """Called when dashboard is ready. Fades out once minimum time has elapsed."""
        if self._finished_emitted:
            return
        self._dismiss_requested = True
        if self._min_elapsed:
            self._fade_out()

    def _on_min_elapsed(self):
        self._min_elapsed = True
        if self._dismiss_requested:
            self._fade_out()

    def _fade_out(self):
        if self._finished_emitted or self._fade_started:
            return
        self._fade_started = True
        try:
            self._anim = QPropertyAnimation(self._opacity, b"opacity")
            self._anim.setDuration(self.FADE_MS)
            self._anim.setStartValue(self._opacity.opacity())
            self._anim.setEndValue(0.0)
            self._anim.finished.connect(self._on_fade_done)
            self._anim.start()
        except Exception:
            self._on_fade_done()

    def _on_fade_done(self):
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self.finished.emit()
        self.close()

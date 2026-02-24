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
from PyQt5.QtGui import QFont, QPainter, QColor, QBrush, QPainterPath, QPen, QPolygon
from PyQt5.QtCore import QPoint, QRect

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
        zebra_version = config.get("zebra_version", "3.1.0")
        self.node_manager = NodeManager(zebra_version=zebra_version)
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
        
        # Check if we have existing data and just needed dependencies installed
        has_existing_data = self.config.get("has_existing_data", False)
        if has_existing_data and self.node_manager.check_docker_installed() and self.node_manager.check_curl_installed():
            # Dependencies now installed, data exists - mark complete and go to dashboard
            self.config.set("data_path", "/mnt/zebra-data")
            self.config.mark_installed()
            self.config.set("docker_configured", True)
            self.config.save()
            # Close installer and open dashboard
            from dashboard import DashboardWindow
            self.hide()
            self.dashboard = DashboardWindow(self.config)
            self.dashboard.show()
            return
        
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
        
        title = QLabel("Reboot Required")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setStyleSheet("color: #f4b728;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        layout.addItem(self._spacer(20))
        
        info = QLabel(
            "Docker has been installed.\n\n"
            "After reboot, run ZecNode again\n"
            "to continue the installation."
        )
        info.setFont(QFont("Segoe UI", 14))
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #888;")
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


"""
ZecNode Configuration Management
Handles persistent settings and installation state
Supports resuming installation after reboot
"""

import json
from pathlib import Path
from typing import Optional

VERSION = "2.0.0"


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

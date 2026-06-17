"""
ZecNode Configuration Management
Handles persistent settings and installation state
Supports resuming installation after reboot
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

VERSION = "3.2.3"


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
        "arti_enabled": False,          # Tor onion-service (opt-in privacy)
        "arti_onion_address": "",       # cached .onion for instant display
    }
    
    def __init__(self):
        self._ensure_config_dir()
        self._config = self._load_config()
        self._last_save_time = 0.0
        self._dirty = False
    
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
        """Save current config to file atomically (write-temp + rename)."""
        tmp_path = self.CONFIG_FILE.with_suffix('.json.tmp')
        with open(tmp_path, 'w') as f:
            json.dump(self._config, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.CONFIG_FILE)
        self._last_save_time = time.monotonic()
        self._dirty = False

    def save_throttled(self, min_interval_seconds: float = 60.0):
        """Save to disk only if the throttle interval has elapsed since last save.
        Intended for hot-path values (status snapshots, sync cache) to reduce SD wear."""
        if not self._dirty:
            return
        if time.monotonic() - self._last_save_time < min_interval_seconds:
            return
        self.save()

    def flush(self):
        """Force-save any pending changes, ignoring the throttle. Call on shutdown."""
        if self._dirty:
            self.save()

    def get(self, key: str, default=None):
        """Get a config value"""
        return self._config.get(key, default)

    def set(self, key: str, value):
        """Set a config value and save immediately."""
        if self._config.get(key) == value:
            return
        self._config[key] = value
        self.save()

    def set_deferred(self, key: str, value):
        """Set a config value in memory only. Caller must trigger save() / save_throttled() / flush()."""
        if self._config.get(key) == value:
            return
        self._config[key] = value
        self._dirty = True
    
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

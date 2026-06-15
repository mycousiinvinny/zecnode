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
    MOUNT_PATH = "/mnt/zebra-data"
    
    # Lightwalletd
    LWD_CONTAINER_NAME = "lightwalletd"
    LWD_IMAGE_NAME = "mycousiinvinny/lightwalletd:arm64"
    LWD_PORT = 9067

    # Arti (Tor onion-service sidecar in front of lightwalletd)
    ARTI_CONTAINER_NAME = "arti"
    ARTI_IMAGE_NAME = "mycousiinvinny/arti:arm64"
    ARTI_NICKNAME = "zecnode"
    ARTI_DATA_DIR = "/mnt/zebra-data/arti"   # persistent onion keys (BACK THIS UP)
    
    # Directory structure on SSD
    # Step 6: sudo mkdir -p /mnt/zebra-data/{docker,containerd}
    DOCKER_DIR = "docker"
    CONTAINERD_DIR = "containerd"
    # Step 7: mkdir -p /mnt/zebra-data/zebra-{cache,state}
    ZEBRA_CACHE_DIR = "zebra-cache"
    ZEBRA_STATE_DIR = "zebra-state"
    
    # Quick Sync (snapshot import) — collapses days of P2P sync into hours by
    # importing a daily ValarGroup Zebra state snapshot.
    QUICKSYNC_CONTAINER_NAME = "zecnode-quicksync"
    QUICKSYNC_IMAGE_NAME = "alpine:3"
    QUICKSYNC_LATEST_URL = "https://zebra-snapshots.nyc3.cdn.digitaloceanspaces.com/mainnet/latest.json"
    # Zebra's on-disk database format the snapshot must match. If ValarGroup
    # moves ahead of the zfnd/zebra image we ship, refuse rather than corrupt.
    QUICKSYNC_DB_MAJOR = 27
    # Extracted RocksDB state is a bit larger than the zstd tarball.
    QUICKSYNC_EXTRACT_RATIO = 1.12
    # Tarball + extracted state coexist briefly, plus headroom.
    QUICKSYNC_SPACE_FACTOR = 2.25

    # Zcash mainnet approximate current height
    ESTIMATED_TARGET_HEIGHT = 3_200_000
    
    _cached_started_at = None
    _cached_peer_count = 0

    def __init__(self, data_path: Optional[Path] = None, zebra_version: str = "latest"):
        self.data_path = data_path or Path(self.MOUNT_PATH)
        self.zebra_version = zebra_version
        self.IMAGE_NAME = f"zfnd/zebra:{zebra_version}"
    
    # ==================== SYSTEM CHECKS ====================
    
    def check_curl_installed(self) -> bool:
        """Check if curl is installed"""
        return shutil.which("curl") is not None
    
    def check_docker_installed(self) -> bool:
        """Check if Docker is installed"""
        return shutil.which("docker") is not None

    def check_qrencode_installed(self) -> bool:
        """Check if qrencode is installed (powers the .onion QR code)"""
        return shutil.which("qrencode") is not None
    
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
        Refresh the apt package index only — NO `apt upgrade`.

        We deliberately don't upgrade the user's installed packages: it's slow,
        it can prompt (and hang), and it's not our place to change software the
        user didn't ask us to touch. We just need a current index so the curl /
        Docker / qrencode installs below can find their packages.
        """
        if progress_callback:
            progress_callback("Disabling sleep mode...")

        # Disable sleep/suspend so node stays online 24/7
        self._disable_sleep_mode()

        if progress_callback:
            progress_callback("Refreshing package list...")

        # `sudo env VAR=...` sets the vars inside the root process (survives sudo's
        # env_reset) so apt never pops an interactive prompt; stdin=DEVNULL is a
        # second guard. apt-get is the script-stable CLI.
        apt = ["sudo", "env",
               "DEBIAN_FRONTEND=noninteractive",
               "NEEDRESTART_MODE=a",
               "NEEDRESTART_SUSPEND=1"]

        def run_apt(args, timeout):
            return subprocess.run(
                apt + args,
                capture_output=True, text=True,
                stdin=subprocess.DEVNULL, timeout=timeout
            )

        try:
            result = run_apt(["apt-get", "update", "--fix-missing"], 600)

            if result.returncode != 0:
                err = result.stderr or ""
                # Another package manager holding the dpkg/apt lock? Wait and retry once.
                if "lock" in err.lower() or "another process" in err.lower():
                    if progress_callback:
                        progress_callback("Waiting for another update to finish...")
                    time.sleep(15)
                    result = run_apt(["apt-get", "update", "--fix-missing"], 600)
                if result.returncode != 0:
                    return False, ("Couldn't refresh the package list. Check your internet "
                                   "connection and try again.\n\n"
                                   f"{(result.stderr or '').strip()[:300]}")

            return True, "Package list refreshed"

        except subprocess.TimeoutExpired:
            return False, ("Refreshing the package list timed out — this is usually a slow "
                           "network. Check your connection and try again.")
        except Exception as e:
            return False, f"Package refresh error: {str(e)}"
    
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
                # Write directly (NO sudo): these live in the user's own home,
                # and a GUI install can't supply a sudo password — the old sudo
                # writes silently failed, which is why the menu entry / app icon
                # never got created on no-passwordless-sudo systems (Ubuntu).
                desktop_file = f"{autostart_dir}/zecnode-nosleep.desktop"
                try:
                    os.makedirs(autostart_dir, exist_ok=True)
                    with open(desktop_file, "w") as _f:
                        _f.write(desktop_entry)
                except OSError:
                    pass
                
                # Create application menu entry for ZecNode
                app_entry = f"""[Desktop Entry]
Type=Application
Name=ZecNode
Comment=Zcash Node Dashboard
Exec=bash -c "cd {home_dir}/zecnode && python3 main.py"
Icon={home_dir}/zecnode/zecnode-icon.png
Terminal=false
Categories=Utility;Network;
StartupWMClass=ZecNode
"""
                # StartupWMClass MUST match the running window's WM_CLASS — Qt
                # sets the X11 res_class to the applicationName ("ZecNode") — or
                # GNOME can't tie the window to this entry and shows its generic
                # gear instead of the logo. Written directly, no sudo (see above).
                app_file = f"{applications_dir}/zecnode.desktop"
                try:
                    os.makedirs(applications_dir, exist_ok=True)
                    with open(app_file, "w") as _f:
                        _f.write(app_entry)
                    os.chmod(app_file, 0o755)
                    subprocess.run(["update-desktop-database", applications_dir],
                                   capture_output=True, timeout=10)
                except OSError:
                    pass
                
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
                ["sudo", "env", "DEBIAN_FRONTEND=noninteractive", "NEEDRESTART_MODE=a",
                 "apt", "install", "-y", "curl"],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=120
            )

            if result.returncode != 0:
                return False, f"Failed to install curl: {result.stderr}"
            
            return True, "curl installed"
            
        except subprocess.TimeoutExpired:
            return False, "curl installation timed out"
        except Exception as e:
            return False, f"curl installation error: {str(e)}"

    def install_qrencode(self, progress_callback=None) -> Tuple[bool, str]:
        """Install qrencode (powers the dashboard's .onion QR code).

        Optional convenience tool — callers should treat a failure as non-fatal.
        """
        if progress_callback:
            progress_callback("Installing qrencode...")

        try:
            result = subprocess.run(
                ["sudo", "env", "DEBIAN_FRONTEND=noninteractive", "NEEDRESTART_MODE=a",
                 "apt", "install", "-y", "qrencode"],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=120
            )

            if result.returncode != 0:
                return False, f"Failed to install qrencode: {result.stderr}"

            return True, "qrencode installed"

        except subprocess.TimeoutExpired:
            return False, "qrencode installation timed out"
        except Exception as e:
            return False, f"qrencode installation error: {str(e)}"

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
            
            # Run Docker install script. get.docker.com runs apt-get internally, so
            # the same non-interactive env applies — otherwise a needrestart prompt
            # mid-script would hang until the timeout.
            result = subprocess.run(
                ["sudo", "env", "DEBIAN_FRONTEND=noninteractive", "NEEDRESTART_MODE=a",
                 "NEEDRESTART_SUSPEND=1", "sh", "/tmp/get-docker.sh"],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
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
            fstab_entry = f"UUID={uuid} {self.MOUNT_PATH} ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2"
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
    
    def _zebra_run_argv(self):
        """The `docker run` argv for the Zebra node container — the single
        source of truth shared by start_node() and the Quick Sync worker's
        auto-start (so the two can never drift apart)."""
        cache_path = f"{self.MOUNT_PATH}/{self.ZEBRA_CACHE_DIR}"
        state_path = f"{self.MOUNT_PATH}/{self.ZEBRA_STATE_DIR}"
        return [
            "docker", "run", "-d",
            "--name", self.CONTAINER_NAME,
            "--network", "zecnode",
            "-v", f"{cache_path}:/home/zebra/.cache/zebra",
            "-v", f"{state_path}:/home/zebra/.local/state/zebra",
            "-p", "8233:8233",
            "-e", "ZEBRA_RPC__LISTEN_ADDR=0.0.0.0:8232",
            "-e", "ZEBRA_RPC__ENABLE_COOKIE_AUTH=false",
            "--restart", "unless-stopped",
            self.IMAGE_NAME,
        ]

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

        # Never start Zebra mid-Quick-Sync — the import wipes and replaces its database.
        if self.is_quicksync_active():
            return False, "Quick Sync is in progress. Wait for it to finish (your node starts automatically) or cancel it first."
        
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
            # Zebra 4.0.0+ stores data in /home/zebra/.cache/zebra
            result = subprocess.run(
                self._zebra_run_argv(), capture_output=True, text=True
            )
            
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
                self._cached_started_at = None
                return status

            # Get container uptime (cache StartedAt since it never changes while running)
            if self._cached_started_at is None:
                result = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.StartedAt}}", self.CONTAINER_NAME],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self._cached_started_at = result.stdout.strip()

            if self._cached_started_at:
                status.uptime = self._calculate_uptime(self._cached_started_at)
            
            # Get logs
            result = subprocess.run(
                ["docker", "logs", "--tail", "30", self.CONTAINER_NAME],
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
                self._cached_peer_count = status.peer_count
            elif status.running:
                status.peer_count = self._cached_peer_count
            
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
                text=True,
                timeout=15
            )
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "Error: timed out fetching logs"
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
                text=True,
                timeout=5
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
                text=True,
                timeout=5
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
    
    def get_zebra_version(self, config=None) -> str:
        """Get the Zebra version by querying the running container, or from saved config"""
        try:
            # First check if container is running
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.CONTAINER_NAME}"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.stdout.strip():
                # Container is running - query actual Zebra version
                result = subprocess.run(
                    ["docker", "exec", self.CONTAINER_NAME, "zebrad", "--version"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    # Output is like "zebrad 4.1.0"
                    version_str = result.stdout.strip()
                    if "zebrad" in version_str:
                        version = version_str.replace("zebrad", "").strip()
                    else:
                        version = version_str
                    # Save to config for when stopped
                    if config and version and version != "--":
                        config.set("zebra_actual_version", version)
                        config.save()
                    return version
            else:
                # Container stopped - try saved version from config first
                if config:
                    saved_version = config.get("zebra_actual_version")
                    if saved_version:
                        return saved_version
                
                # Fall back to image tag
                result = subprocess.run(
                    ["docker", "inspect", "--format", "{{.Config.Image}}", self.CONTAINER_NAME],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    image = result.stdout.strip()
                    if ":" in image:
                        tag = image.split(":")[-1]
                        if tag != "latest":
                            return tag
                        return "latest"
        except:
            pass
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
            
            # Create zcash.conf for lightwalletd (it just needs rpcbind and rpcport)
            conf_dir = Path.home() / ".zecnode"
            conf_dir.mkdir(exist_ok=True)
            conf_file = conf_dir / "zcash.conf"
            conf_file.write_text(f"rpcbind={self.CONTAINER_NAME}\nrpcport=8232\nrpcuser=zecnode\nrpcpassword=zecnode\n")
            
            # Create lightwalletd cache directory on SSD (root-owned mount)
            lwd_cache = "/mnt/zebra-data/lightwalletd"
            subprocess.run(
                ["sudo", "mkdir", "-p", lwd_cache],
                capture_output=True, timeout=5
            )
            subprocess.run(
                ["sudo", "chmod", "777", lwd_cache],
                capture_output=True, timeout=5
            )
            
            # Start lightwalletd container on same network as Zebra
            # Uses container name 'zebra' for DNS resolution
            result = subprocess.run([
                "docker", "run", "-d",
                "--name", self.LWD_CONTAINER_NAME,
                "--network", "zecnode",
                "-p", f"{self.LWD_PORT}:9067",
                "-v", f"{conf_file}:/app/zcash.conf:ro",
                "-v", f"{lwd_cache}:/var/lib/lightwalletd",
                "--restart", "unless-stopped",
                self.LWD_IMAGE_NAME,
                "--zcash-conf-path", "/app/zcash.conf",
                "--data-dir", "/var/lib/lightwalletd",
                "--grpc-bind-addr", "0.0.0.0:9067",
                "--no-tls-very-insecure",
                "--log-file", "/dev/stdout"
            ], capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                return False, f"Failed to start lightwalletd: {result.stderr}"
            
            return True, "Lightwalletd started"
            
        except subprocess.TimeoutExpired:
            return False, "Timeout starting lightwalletd"
        except Exception as e:
            return False, f"Error: {str(e)}"
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
        return f"http://{self.get_local_ip()}:{self.LWD_PORT}"

    # ==================== ARTI / TOR ONION SERVICE ====================
    #
    # Arti sits in front of lightwalletd, exposing <onion>.onion:9067 over Tor.
    # The clearnet path stays untouched; this is an opt-in privacy door.
    # Onion keys live in ARTI_DATA_DIR on the SSD and are permanent.

    def is_arti_running(self) -> bool:
        """Check if the Arti (Tor) container is running"""
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.ARTI_CONTAINER_NAME}"],
                capture_output=True, text=True, timeout=5
            )
            return bool(result.stdout.strip())
        except:
            return False

    def _get_lwd_container_ip(self) -> Optional[str]:
        """Look up lightwalletd's IP on the zecnode docker bridge.

        Arti's proxy_ports requires a literal IP:port (it does not resolve
        container names), so we template lightwalletd's current bridge IP
        into arti.toml at start time instead of recreating the network."""
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f",
                 "{{.NetworkSettings.Networks.zecnode.IPAddress}}",
                 self.LWD_CONTAINER_NAME],
                capture_output=True, text=True, timeout=5
            )
            ip = result.stdout.strip()
            return ip if ip else None
        except:
            return None

    def _write_arti_config(self, lwd_ip: str) -> Path:
        """Write arti.toml (forwarding the onion port to lightwalletd) to
        ~/.zecnode and return its path. Bind-mounted read-only into the container."""
        conf_dir = Path.home() / ".zecnode"
        conf_dir.mkdir(exist_ok=True)
        conf_file = conf_dir / "arti.toml"
        conf_file.write_text(
            "[application]\n"
            "allow_running_as_root = true\n\n"
            "[storage]\n"
            'state_dir = "/var/lib/arti"\n'
            'cache_dir = "/var/lib/arti/cache"\n\n'
            "[storage.permissions]\n"
            "dangerously_trust_everyone = true\n\n"
            "[logging]\n"
            'console = "info"\n\n'
            f'[onion_services."{self.ARTI_NICKNAME}"]\n'
            "enabled = true\n"
            "proxy_ports = [\n"
            f'    ["443", "{lwd_ip}:9067"],\n'
            "]\n"
        )
        return conf_file

    def get_onion_address(self, generate: bool = False) -> Optional[str]:
        """Return the node's .onion address, or None if not available yet.

        With generate=True the identity key is created if missing (this is what
        makes the address permanent). Runs a short-lived arti container that
        reads/creates the key in ARTI_DATA_DIR."""
        try:
            subprocess.run(["sudo", "mkdir", "-p", self.ARTI_DATA_DIR],
                           capture_output=True, timeout=5)
            conf_file = Path.home() / ".zecnode" / "arti.toml"
            if not conf_file.exists():
                # Need a config to know the nickname; the IP is irrelevant for key ops
                self._write_arti_config(self._get_lwd_container_ip() or "127.0.0.1")
            gen = "if-needed" if generate else "no"
            result = subprocess.run([
                "docker", "run", "--rm",
                "-v", f"{self.ARTI_DATA_DIR}:/var/lib/arti",
                "-v", f"{conf_file}:/etc/arti.toml:ro",
                self.ARTI_IMAGE_NAME,
                "-c", "/etc/arti.toml", "--disable-fs-permission-checks",
                "hss", "--nickname", self.ARTI_NICKNAME,
                "onion-address", "--generate", gen
            ], capture_output=True, text=True, timeout=60)
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.endswith(".onion"):
                    return line
            return None
        except:
            return None

    def start_arti(self) -> Tuple[bool, str]:
        """Start the Arti Tor onion-service sidecar.

        Auto-starts the dependency chain (Zebra -> lightwalletd) if needed,
        then templates lightwalletd's bridge IP into arti.toml and launches Arti."""
        try:
            if self.is_arti_running():
                return True, "Arti already running"

            # Ensure the chain is up (one toggle, it just works)
            if not self.get_status().running:
                self.start_node()
            if not self.is_lightwalletd_running():
                self.start_lightwalletd()

            # Arti's proxy target must be a literal IP — wait for lwd's bridge IP
            lwd_ip = None
            for _ in range(15):
                lwd_ip = self._get_lwd_container_ip()
                if lwd_ip:
                    break
                time.sleep(1)
            if not lwd_ip:
                return False, "Could not determine lightwalletd address"

            conf_file = self._write_arti_config(lwd_ip)

            # Persistent key dir on the SSD (root-owned mount; arti runs as root)
            subprocess.run(["sudo", "mkdir", "-p", self.ARTI_DATA_DIR],
                           capture_output=True, timeout=5)

            # Pre-generate the identity key so the .onion is known and stable
            self.get_onion_address(generate=True)

            subprocess.run(["docker", "rm", "-f", self.ARTI_CONTAINER_NAME],
                           capture_output=True)
            subprocess.run(["docker", "network", "create", "zecnode"],
                           capture_output=True)
            result = subprocess.run([
                "docker", "run", "-d",
                "--name", self.ARTI_CONTAINER_NAME,
                "--network", "zecnode",
                "-v", f"{self.ARTI_DATA_DIR}:/var/lib/arti",
                "-v", f"{conf_file}:/etc/arti.toml:ro",
                "--restart", "unless-stopped",
                self.ARTI_IMAGE_NAME,
                "proxy", "-c", "/etc/arti.toml", "--disable-fs-permission-checks"
            ], capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                return False, f"Failed to start Arti: {result.stderr}"
            return True, "Arti started"
        except subprocess.TimeoutExpired:
            return False, "Timeout starting Arti"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def stop_arti(self) -> Tuple[bool, str]:
        """Stop the Arti container"""
        try:
            subprocess.run(
                ["docker", "stop", "-t", "3", self.ARTI_CONTAINER_NAME],
                capture_output=True, text=True, timeout=10
            )
            subprocess.run(
                ["docker", "rm", "-f", self.ARTI_CONTAINER_NAME],
                capture_output=True
            )
            return True, "Arti stopped"
        except Exception as e:
            return False, f"Error: {str(e)}"

    # ==================== QUICK SYNC (SNAPSHOT IMPORT) ====================
    #
    # Instead of verifying the whole chain from scratch (days on a Pi), import
    # a daily Zebra state snapshot published by ValarGroup (~4-6 hours wired).
    # The work runs in a detached helper container with --restart unless-stopped,
    # so it survives reboots, power loss and the dashboard being closed; the
    # dashboards only OBSERVE it via a status file + file sizes on disk.
    # Trust note: a snapshot is not consensus-validated — the user is trusting
    # ValarGroup's copy of the chain. The sha256 check only guards transit
    # corruption. The UI says so before starting.

    def _quicksync_dir(self) -> str:
        return f"{self.MOUNT_PATH}/quicksync"

    def is_quicksync_active(self) -> bool:
        """True while an import is running or waiting to be finalized.
        Once the 'done' marker exists the data is in place and Zebra may start."""
        qs_dir = self._quicksync_dir()
        return os.path.isdir(qs_dir) and not os.path.exists(f"{qs_dir}/done")

    def fetch_quicksync_manifest(self) -> Optional[dict]:
        """Fetch latest.json from the snapshot CDN: current URL(s), sha256,
        exact size, height and db format version. None on any failure."""
        try:
            import json
            import urllib.request
            req = urllib.request.Request(
                self.QUICKSYNC_LATEST_URL, headers={"User-Agent": "ZecNode"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                manifest = json.loads(resp.read().decode())
            required = ("url", "filename", "sha256", "size_bytes", "height", "db_major")
            if not all(k in manifest for k in required):
                return None
            return manifest
        except Exception:
            return None

    def quicksync_free_bytes(self) -> int:
        """Free space on the SSD."""
        try:
            return shutil.disk_usage(self.MOUNT_PATH).free
        except Exception:
            return 0

    def quicksync_required_bytes(self, manifest: dict) -> int:
        return int(int(manifest["size_bytes"]) * self.QUICKSYNC_SPACE_FACTOR)

    def is_on_wifi(self) -> bool:
        """True if the default route goes out over a wireless interface.
        Wired vs WiFi is the single biggest Quick Sync speed factor."""
        try:
            result = subprocess.run(
                ["ip", "route", "get", "8.8.8.8"],
                capture_output=True, text=True, timeout=5
            )
            match = re.search(r'\bdev\s+(\S+)', result.stdout)
            return bool(match and match.group(1).startswith("wl"))
        except Exception:
            return False

    def _write_quicksync_script(self, qs_dir: str, manifest: dict):
        """Generate the worker script the helper container runs. Every step
        resumes or re-runs safely, so the restart policy self-heals failures."""
        import shlex
        urls = manifest.get("urls") or [manifest["url"]]
        # Exact command the worker uses to bring the node up when it finishes,
        # built from the same source as start_node so they never diverge.
        zebra_cmd = " ".join(shlex.quote(a) for a in self._zebra_run_argv())
        script = f"""#!/bin/sh
# ZecNode Quick Sync worker — generated, do not edit.
# Runs in an alpine container with /mnt/zebra-data mounted at /data.
QS=/data/quicksync
FILE="{manifest['filename']}"
SHA256="{manifest['sha256']}"
SIZE={int(manifest['size_bytes'])}

status() {{
  printf '{{"phase":"%s","note":"%s"}}' "$1" "$2" > "$QS/.st.tmp" && mv "$QS/.st.tmp" "$QS/status.json"
}}

# Finished on a previous run (container restarted after done) — just idle.
[ -f "$QS/done" ] && {{ status done ""; exec tail -f /dev/null; }}

status preparing ""
apk add --no-cache aria2 zstd tar ca-certificates >/dev/null 2>&1 \\
  || {{ status error "package install failed (no internet?)"; sleep 5; exit 1; }}

if [ ! -f "$QS/verified" ]; then
  status download ""
  # -c resumes a partial file; mirrors are alternate sources for the same file.
  # DigitalOcean Spaces drops connections, so retry forever with a short wait.
  aria2c -c --max-tries=0 --retry-wait=8 -x16 -s16 \\
    --allow-overwrite=true --file-allocation=none --summary-interval=0 \\
    --checksum=sha-256=$SHA256 -d "$QS" -o "$FILE" \\
    {' '.join(urls)}
  if [ $? -ne 0 ]; then
    got=$(stat -c %s "$QS/$FILE" 2>/dev/null || echo 0)
    if [ "$got" -ge "$SIZE" ]; then
      # Complete but failed the checksum — start the download over clean.
      rm -f "$QS/$FILE" "$QS/$FILE.aria2"
      status error "checksum mismatch - restarting download"
    else
      status error "download interrupted"
    fi
    sleep 5
    exit 1
  fi
  touch "$QS/verified"
fi

status extract ""
mkdir -p /data/zebra-cache
# Old/partial chain state must not mix with snapshot data — wipe, then unpack.
# (Re-runs after an interrupted extract land here again, which is correct.)
find /data/zebra-cache -mindepth 1 -maxdepth 1 -exec rm -rf {{}} +
zstd -dc "$QS/$FILE" | tar -x -C /data/zebra-cache \\
  || {{ status error "unpack failed"; sleep 5; exit 1; }}

status finalize ""
# Snapshot files arrive as UID 10001 (the zebra container user); the dir
# itself must match so Zebra can write its peers file etc.
chown 10001:10001 /data/zebra-cache
rm -f "$QS/$FILE" "$QS/verified"
touch "$QS/done"
status done ""

# Start the node ourselves so it comes up even if the dashboard is closed.
# We reach the host Docker daemon through the mounted socket. If the dashboard
# already started it this no-ops; if Docker/socket isn't reachable we just idle
# and the dashboard starts the node the next time it's opened.
apk add --no-cache docker-cli >/dev/null 2>&1
if [ -z "$(docker ps -q -f name=zebra 2>/dev/null)" ]; then
  docker network create zecnode >/dev/null 2>&1
  docker rm -f zebra >/dev/null 2>&1
  {zebra_cmd} >/dev/null 2>&1
fi
if [ -n "$(docker ps -q -f name=zebra 2>/dev/null)" ]; then
  # Node is up — stop watching and remove this worker. (Reboot survival needs
  # --restart unless-stopped, so a plain exit would just relaunch us; removing
  # ourselves through the socket is the clean way to stop. The staging dir is
  # left for the dashboard to tidy on next open.)
  exec docker rm -f zecnode-quicksync
fi
exec tail -f /dev/null
"""
        with open(f"{qs_dir}/snap.sh", "w") as f:
            f.write(script)

    def start_quicksync(self, manifest: dict) -> Tuple[bool, str]:
        """Stop the node chain and launch the detached snapshot-import worker."""
        try:
            import json
            if self.is_quicksync_running():
                return True, "Quick Sync already running"
            if int(manifest.get("db_major", -1)) != self.QUICKSYNC_DB_MAJOR:
                return False, ("The latest snapshot uses a newer database format than this "
                               "version of ZecNode supports. Update ZecNode and try again.")
            if not os.path.ismount(self.MOUNT_PATH):
                return False, f"SSD not mounted at {self.MOUNT_PATH}."
            free = self.quicksync_free_bytes()
            need = self.quicksync_required_bytes(manifest)
            if free < need:
                return False, (f"Not enough free space on the SSD: Quick Sync needs about "
                               f"{need // 2**30} GiB free, but only {free // 2**30} GiB is available.")

            # The import replaces Zebra's database — take the whole chain down.
            if self.is_arti_running():
                self.stop_arti()
            if self.is_lightwalletd_running():
                self.stop_lightwalletd()
            if self.get_status().running:
                self.stop_node()

            qs_dir = self._quicksync_dir()
            # /mnt/zebra-data is owned by the user, so create + clean the staging
            # dir WITHOUT sudo — a GUI launch can't supply a sudo password, and
            # every sudo here would silently fail (manifest.json then can't be
            # written). The worker container writes its markers as root, but they
            # live inside this user-owned dir, so the user can still unlink them.
            os.makedirs(qs_dir, exist_ok=True)
            for _m in ("status.json", "done", "verified"):
                try:
                    os.remove(f"{qs_dir}/{_m}")
                except OSError:
                    pass
            # Drop stale tarballs left from a different snapshot.
            for _f in os.listdir(qs_dir):
                if ".tar.zst" in _f and not _f.startswith(manifest["filename"]):
                    try:
                        os.remove(os.path.join(qs_dir, _f))
                    except OSError:
                        pass

            with open(f"{qs_dir}/manifest.json", "w") as f:
                json.dump(manifest, f, indent=2)
            self._write_quicksync_script(qs_dir, manifest)

            subprocess.run(["docker", "rm", "-f", self.QUICKSYNC_CONTAINER_NAME],
                           capture_output=True)
            result = subprocess.run([
                "docker", "run", "-d",
                "--name", self.QUICKSYNC_CONTAINER_NAME,
                "-v", f"{self.MOUNT_PATH}:/data",
                # The Docker socket lets the worker start the node itself when the
                # import finishes — so the node comes up even if the dashboard is
                # closed, instead of waiting for the app to notice "done".
                "-v", "/var/run/docker.sock:/var/run/docker.sock",
                "--restart", "unless-stopped",
                self.QUICKSYNC_IMAGE_NAME,
                "sh", "/data/quicksync/snap.sh"
            ], capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                shutil.rmtree(qs_dir, ignore_errors=True)
                return False, f"Failed to start Quick Sync: {result.stderr}"
            return True, "Quick Sync started"
        except subprocess.TimeoutExpired:
            return False, "Timeout starting Quick Sync"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def is_quicksync_running(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.QUICKSYNC_CONTAINER_NAME}"],
                capture_output=True, text=True, timeout=5
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    # In-memory samples for download speed and a 10s extract-progress cache —
    # `du` over ~300 GiB of .sst files is too heavy to run on every poll.
    _qs_rate_sample = None
    _qs_du_cache = (0.0, 0)

    def _quicksync_extracted_bytes(self, cache_path: str) -> int:
        now = time.monotonic()
        last_time, last_val = NodeManager._qs_du_cache
        if now - last_time < 10:
            return last_val
        try:
            result = subprocess.run(["du", "-sb", cache_path],
                                    capture_output=True, text=True, timeout=60)
            val = int(result.stdout.split()[0])
        except Exception:
            val = last_val
        NodeManager._qs_du_cache = (now, val)
        return val

    def get_quicksync_status(self) -> Optional[dict]:
        """Observe the import from disk + docker state. None when no import
        exists. The returned headline/detail strings are shared by both UIs.
        Overall percent: download 0-45, verify ~46, extract 50-98, done 100."""
        qs_dir = self._quicksync_dir()
        if not os.path.isdir(qs_dir):
            return None
        import json

        def _result(phase, percent, headline, detail, error=False):
            return {"phase": phase, "percent": round(min(max(percent, 0.0), 100.0), 1),
                    "headline": headline, "detail": detail, "error": error}

        try:
            with open(f"{qs_dir}/manifest.json") as f:
                manifest = json.load(f)
        except Exception:
            return _result("error", 0, "Quick Sync problem",
                           "Setup files are missing — cancel and start again.", error=True)

        phase, note = "preparing", ""
        try:
            with open(f"{qs_dir}/status.json") as f:
                st = json.load(f)
            phase = st.get("phase", "preparing")
            note = st.get("note", "")
        except Exception:
            pass

        if phase == "done":
            return _result("done", 100, "Quick Sync complete", "Starting your node…")

        # The worker has --restart unless-stopped, so "not running" normally
        # just means it's mid-restart; only a missing container is a problem.
        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", self.QUICKSYNC_CONTAINER_NAME],
            capture_output=True, text=True, timeout=5
        )
        if inspect.returncode != 0:
            return _result("error", 0, "Quick Sync stopped unexpectedly",
                           "Its worker container is gone — cancel and start again.", error=True)

        size = int(manifest["size_bytes"])
        tar_path = f"{qs_dir}/{manifest['filename']}"

        if phase in ("download", "error", "preparing"):
            try:
                # aria2c's parallel connections seek-write at spread-out offsets,
                # so the partial file is SPARSE: its logical size (os.path.getsize
                # / st_size) jumps to a near-full value immediately while almost
                # nothing is on disk. st_blocks*512 is the ACTUAL bytes written —
                # that's what reflects real download progress, rate, and ETA.
                done_bytes = os.stat(tar_path).st_blocks * 512
            except Exception:
                done_bytes = 0
            if phase == "preparing" and done_bytes == 0:
                # 0% (not 1%) so the bar doesn't dip back when the real download
                # starts at ~0 — progress only ever moves forward. The headline
                # makes clear it's the pre-download setup step.
                return _result("preparing", 0, "Quick Sync — getting ready",
                               "Setting up the download…")
            if done_bytes >= size:
                return _result("verify", 46, "Verifying snapshot",
                               "Checking the download for corruption — roughly 20 minutes…")
            percent = done_bytes / size * 45
            detail = f"{done_bytes / 2**30:.1f} of {size / 2**30:.0f} GiB"
            now = time.monotonic()
            if NodeManager._qs_rate_sample:
                t0, b0 = NodeManager._qs_rate_sample
                if now > t0 and done_bytes > b0:
                    rate = (done_bytes - b0) / (now - t0)
                    if rate > 100_000:
                        eta_h = (size - done_bytes) / rate / 3600
                        eta = f"about {eta_h:.1f} h left" if eta_h >= 1 else f"about {eta_h * 60:.0f} min left"
                        detail += f" — {rate / 2**20:.0f} MB/s, {eta}"
            NodeManager._qs_rate_sample = (now, done_bytes)
            if phase == "error":
                return _result("download", percent, "Quick Sync — retrying",
                               f"Hiccup ({note}) — it recovers automatically. {detail}")
            return _result("download", percent, "Downloading snapshot",
                           f"{detail} · Safe to close this window — it keeps running.")

        if phase == "extract":
            extracted = self._quicksync_extracted_bytes(f"{self.MOUNT_PATH}/{self.ZEBRA_CACHE_DIR}")
            est_total = size * self.QUICKSYNC_EXTRACT_RATIO
            percent = 50 + min(extracted / est_total, 1.0) * 48
            return _result("extract", min(percent, 98.0), "Unpacking blockchain",
                           "Slowest step — typically 2–3 hours on a Pi. Safe to close this window.")

        if phase == "finalize":
            return _result("finalize", 99, "Finishing up", "Cleaning up…")

        return _result(phase, 0, "Quick Sync", note or "Working…")

    def cancel_quicksync(self) -> Tuple[bool, str]:
        """Stop the worker and delete the staging area (partial tarball, markers).
        If extraction had already begun, the old chain state is gone — the caller
        should warn the user before getting here."""
        try:
            subprocess.run(["docker", "rm", "-f", self.QUICKSYNC_CONTAINER_NAME],
                           capture_output=True, timeout=30)
            shutil.rmtree(self._quicksync_dir(), ignore_errors=True)
            NodeManager._qs_rate_sample = None
            return True, "Quick Sync cancelled"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def finish_quicksync(self) -> Tuple[bool, str]:
        """Called by a dashboard when the worker reports done: remove the worker,
        clear the staging area, and hand off to a normal node start."""
        try:
            subprocess.run(["docker", "rm", "-f", self.QUICKSYNC_CONTAINER_NAME],
                           capture_output=True, timeout=30)
            shutil.rmtree(self._quicksync_dir(), ignore_errors=True)
            NodeManager._qs_rate_sample = None
            return self.start_node()
        except Exception as e:
            return False, f"Error: {str(e)}"


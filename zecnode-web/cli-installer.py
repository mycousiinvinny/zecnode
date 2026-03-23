#!/usr/bin/env python3
"""
ZecNode CLI Installer
For headless Raspberry Pi setups — installs everything via terminal.
"""

import sys
import os
import time
import subprocess

# Add parent directory for shared modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from node_manager import NodeManager
from config import Config


def check_sudo():
    """Ensure sudo is available — cache credentials for this session"""
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True, timeout=5
        )
        if result.returncode != 0:
            print("  Sudo access required. Enter your password:")
            os.system("sudo -v")
            # Verify it worked
            result = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5)
            if result.returncode != 0:
                print("  Error: Could not authenticate sudo.")
                sys.exit(1)
            print("")
    except Exception:
        pass


def print_banner():
    print("")
    print("=" * 50)
    print("        ZecNode — Headless Installer")
    print("=" * 50)
    print("")


def print_step(step, total, message):
    print(f"\n[{step}/{total}] {message}")
    print("-" * 40)


def confirm(message):
    """Ask user to confirm with y/n"""
    while True:
        response = input(f"{message} (y/n): ").strip().lower()
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False


def progress(message):
    """Progress callback for node_manager methods"""
    print(f"  → {message}")


def select_drive(node_manager):
    """Detect and let user select a drive"""
    print("  Scanning for external drives...")
    drives = node_manager.detect_external_drives()

    if not drives:
        print("")
        print("  No suitable drives found.")
        print("  Make sure your SSD is plugged in (must be > 100GB).")
        return None, None

    print("")
    print("  ┌─────────────────────────────────────────────┐")
    print("  │  WARNING: The selected drive will be        │")
    print("  │  COMPLETELY ERASED. All data will be lost.  │")
    print("  │  OS drives have been excluded.              │")
    print("  └─────────────────────────────────────────────┘")
    print("")

    for i, drive in enumerate(drives):
        mounted = f" (mounted: {drive.mount_point})" if drive.mount_point else ""
        print(f"  [{i + 1}] {drive.device} — {drive.size_human} — {drive.model}{mounted}")

    print("")

    while True:
        try:
            choice = input(f"  Select drive (1-{len(drives)}), or 'q' to quit: ").strip()
            if choice.lower() == "q":
                return None, None
            idx = int(choice) - 1
            if 0 <= idx < len(drives):
                drive = drives[idx]
                print(f"\n  Selected: {drive.device} — {drive.size_human} — {drive.model}")
                if confirm(f"  Format {drive.device}? THIS WILL ERASE ALL DATA"):
                    return drive.device, drive.partitions[0] if drive.partitions else f"{drive.device}1"
                else:
                    return None, None
        except (ValueError, IndexError):
            print("  Invalid selection.")


def main():
    print_banner()
    check_sudo()

    config = Config()
    node_manager = NodeManager(config.get_data_path(), zebra_version="latest")

    # Check current install phase
    phase = config.get_phase()
    total_steps = 8

    # ── Resume after reboot ──
    if phase == Config.PHASE_DOCKER_INSTALLED:
        print("  Resuming installation after reboot...")
        print("")

        # Verify Docker works
        if not node_manager.check_docker_running():
            print("  Error: Docker is not running after reboot.")
            print("  Try: sudo systemctl start docker")
            sys.exit(1)

        if not node_manager.check_user_in_docker_group():
            print("  Error: User not in docker group.")
            print("  Try: sudo usermod -aG docker $USER && sudo reboot")
            sys.exit(1)

        print("  Docker is working. Continuing setup...\n")

        # Jump to drive setup
        drive = config.get_selected_drive()
        if drive:
            device = config.get("selected_drive")
            partition = config.get("selected_partition")
        else:
            print_step(4, total_steps, "Select Drive")
            device, partition = select_drive(node_manager)
            if not device:
                print("  No drive selected. Exiting.")
                sys.exit(0)
            config.set_selected_drive(device, partition)

        # Format
        print_step(5, total_steps, f"Formatting {device}")
        ok, msg = node_manager.format_drive(device, progress_callback=progress)
        if not ok:
            print(f"  Error: {msg}")
            sys.exit(1)
        print(f"  Done: {msg}")

        # Get partition name after format
        partition = f"{device}1"
        config.set("selected_partition", partition)

        # Mount
        print_step(6, total_steps, f"Mounting {partition}")
        ok, msg = node_manager.mount_drive(partition, progress_callback=progress)
        if not ok:
            print(f"  Error: {msg}")
            sys.exit(1)
        print(f"  Done: {msg}")
        config.set_phase(Config.PHASE_DRIVE_READY)

        # Configure Docker for SSD
        print_step(7, total_steps, "Configuring Docker to use SSD")
        ok, msg = node_manager.configure_docker_for_ssd(progress_callback=progress)
        if not ok:
            print(f"  Error: {msg}")
            sys.exit(1)
        print(f"  Done: {msg}")
        config.set_phase(Config.PHASE_DOCKER_ON_SSD)

        # Pull image + create dirs + start
        print_step(8, total_steps, "Setting up Zebra node")

        progress("Pulling Zebra Docker image (this may take a while)...")
        ok, msg = node_manager.pull_zebra_image(progress_callback=progress)
        if not ok:
            print(f"  Error: {msg}")
            sys.exit(1)
        print(f"  Done: {msg}")

        progress("Creating directories...")
        ok, msg = node_manager.create_zebra_directories(progress_callback=progress)
        if not ok:
            print(f"  Error: {msg}")
            sys.exit(1)

        progress("Starting Zebra node...")
        ok, msg = node_manager.start_node(progress_callback=progress)
        if not ok:
            print(f"  Error: {msg}")
            sys.exit(1)
        print(f"  Done: {msg}")

        # Mark complete
        config.set("installed", True)
        config.set("docker_configured", True)
        config.set_phase(Config.PHASE_COMPLETE)

        print("")
        print("=" * 50)
        print("  ZecNode installation complete!")
        print("=" * 50)
        print("")
        print("  Your Zcash node is now running and syncing.")
        print("  Initial sync will take several hours.")
        print("")
        print("  To set up the web dashboard:")
        print("    cd ~/zecnode/zecnode-web && ./install-web.sh")
        print("")
        return

    # ── Fresh install ──
    if phase not in (Config.PHASE_NOT_STARTED, Config.PHASE_COMPLETE):
        print(f"  Install in unknown state: {phase}")
        if not confirm("  Reset and start fresh?"):
            sys.exit(0)
        config.reset_installation()

    if config.is_installed():
        print("  ZecNode is already installed.")
        if not confirm("  Reinstall from scratch?"):
            sys.exit(0)
        config.reset_installation()

    # Step 1: Select drive
    print_step(1, total_steps, "Select Drive")
    device, partition = select_drive(node_manager)
    if not device:
        print("  No drive selected. Exiting.")
        sys.exit(0)
    config.set_selected_drive(device, partition)

    # Step 2: System update
    print_step(2, total_steps, "Updating system")
    ok, msg = node_manager.update_system(progress_callback=progress)
    if not ok:
        print(f"  Warning: {msg}")
        print("  Continuing anyway...")
    else:
        print(f"  Done: {msg}")
    config.set_phase(Config.PHASE_SYSTEM_UPDATED)

    # Step 3: Install Docker
    print_step(3, total_steps, "Installing Docker")

    if node_manager.check_docker_installed():
        print("  Docker already installed, skipping.")
    else:
        ok, msg = node_manager.install_docker(progress_callback=progress)
        if not ok:
            print(f"  Error: {msg}")
            sys.exit(1)
        print(f"  Done: {msg}")

    config.set_phase(Config.PHASE_DOCKER_INSTALLED)

    # Reboot required
    print("")
    print("  ┌───────────────────────────────────────────────────────┐")
    print("  │  Reboot required for Docker to work.                 │")
    print("  │                                                      │")
    print("  │  After reboot, run this installer again:             │")
    print("  │  python3 ~/zecnode/zecnode-web/cli-installer.py      │")
    print("  └───────────────────────────────────────────────────────┘")
    print("")

    if confirm("  Reboot now?"):
        os.system("sudo reboot")
    else:
        print("  Run 'sudo reboot' when ready, then re-run this installer.")


if __name__ == "__main__":
    main()

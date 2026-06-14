#!/bin/bash
# ZecNode Uninstaller
#   (no args)   remove the app, config, and containers — PRESERVE blockchain data
#   --wipe      ALSO erase ALL data on the SSD (a true from-scratch reset)
#   -y / --yes  skip the confirmation prompts (for automation)

WIPE=0
ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        --wipe|--full) WIPE=1 ;;
        -y|--yes)      ASSUME_YES=1 ;;
    esac
done

DATA_DIR="/mnt/zebra-data"

echo "================================"
echo "      ZecNode Uninstaller"
echo "================================"
echo ""
echo "This will remove:"
echo "  - ZecNode app code      (~/zecnode)"
echo "  - ZecNode config        (~/.zecnode)"
echo "  - Desktop + autostart entries"
echo "  - Docker containers     (zebra, lightwalletd, arti, zecnode-quicksync)"
echo "  - Docker network        (zecnode)"
echo ""
if [[ $WIPE -eq 1 ]]; then
    echo "  *** FULL WIPE ***"
    echo "  - ALL blockchain data on the SSD at $DATA_DIR will be ERASED."
    echo "    You will have to sync the node from scratch. This cannot be undone."
else
    echo "Your blockchain data at $DATA_DIR is PRESERVED (reinstalling is near-instant)."
    echo "Run with --wipe to also erase the SSD for a true from-scratch reset."
fi
echo ""

if [[ $ASSUME_YES -ne 1 ]]; then
    read -p "Continue? [y/N] " -r REPLY
    echo ""
    [[ $REPLY =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
    if [[ $WIPE -eq 1 ]]; then
        read -p "This ERASES your blockchain data. Type ERASE to confirm: " -r CONFIRM
        echo ""
        [[ $CONFIRM == "ERASE" ]] || { echo "Aborted."; exit 0; }
    fi
fi

# Cache sudo credentials once up front (this Pi prompts for a password).
sudo -v || { echo "Need sudo to continue."; exit 1; }

echo "Stopping ZecNode..."
pkill -9 -f 'python.*main.py' 2>/dev/null || true
sleep 1

# Tear down Docker containers + network
if command -v docker &> /dev/null; then
    echo "Removing Docker containers..."
    sudo docker rm -f zebra lightwalletd arti zecnode-quicksync 2>/dev/null || true
    sudo docker network rm zecnode 2>/dev/null || true
fi

if [[ $WIPE -eq 1 ]]; then
    echo "Erasing all data on the SSD ($DATA_DIR)..."
    # Stop Docker so nothing holds the drive (its data lives on the SSD).
    sudo systemctl stop docker docker.socket containerd 2>/dev/null || true
    sleep 1
    # Make sure the SSD is actually mounted, so we erase the real drive and not
    # an empty mount-point folder on the SD card. Only ever touch $DATA_DIR.
    mountpoint -q "$DATA_DIR" || sudo mount "$DATA_DIR" 2>/dev/null || sudo mount -a 2>/dev/null || true
    if mountpoint -q "$DATA_DIR"; then
        sudo find "$DATA_DIR" -mindepth 1 -maxdepth 1 ! -name 'lost+found' -exec rm -rf {} + 2>/dev/null
        echo "SSD data erased."
    else
        echo "WARNING: $DATA_DIR is not mounted — nothing erased."
        echo "         Mount the SSD and re-run with --wipe, or erase it manually."
    fi
    # Reset Docker's storage so the next install reconfigures it cleanly.
    sudo rm -rf /var/lib/docker /var/lib/containerd 2>/dev/null || true
    sudo systemctl start docker 2>/dev/null || true
fi

# Remove app + config + desktop entries
echo "Removing app and config..."
rm -rf "$HOME/zecnode" "$HOME/.zecnode"
rm -f "$HOME/.local/share/applications/zecnode.desktop"
rm -f "$HOME/.config/autostart/zecnode-nosleep.desktop"

echo ""
echo "================================"
echo "      ZecNode Uninstalled"
echo "================================"
echo ""
if [[ $WIPE -eq 1 ]]; then
    echo "Everything erased, including the SSD — this is a clean slate."
else
    echo "Blockchain data preserved at $DATA_DIR."
fi
echo ""
echo "To reinstall:"
echo "  sudo apt install curl -y && curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install.sh | bash"
echo ""

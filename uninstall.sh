#!/bin/bash
echo "================================"
echo "      ZecNode Uninstaller"
echo "================================"
echo ""
echo "This will remove:"
echo "  - ZecNode app code      (~/zecnode)"
echo "  - ZecNode config        (~/.zecnode)"
echo "  - Desktop menu entries  (~/.local/share/applications/zecnode.desktop)"
echo "  - Autostart entry       (~/.config/autostart/zecnode-nosleep.desktop)"
echo "  - Docker containers     (zebra, lightwalletd)"
echo "  - Docker network        (zecnode)"
echo ""
echo "Your blockchain data at /mnt/zebra-data is PRESERVED."
echo "Reinstalling will be near-instant since no resync is needed."
echo ""

read -p "Continue? [y/N] " -r REPLY
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Ensure sudo credentials are cached
sudo -v

# Kill any running ZecNode python process
echo "Stopping ZecNode..."
pkill -9 -f 'python.*zecnode.*main.py' 2>/dev/null || true
sleep 1

# Tear down Docker containers + network
if command -v docker &> /dev/null; then
    echo "Stopping Docker containers..."
    sudo docker stop zebra lightwalletd 2>/dev/null || true
    sudo docker rm -f zebra lightwalletd 2>/dev/null || true
    sudo docker network rm zecnode 2>/dev/null || true
else
    echo "Docker not installed — skipping container cleanup."
fi

# Remove app + config
echo "Removing app and config..."
rm -rf "$HOME/zecnode"
rm -rf "$HOME/.zecnode"

# Remove desktop entries
rm -f "$HOME/.local/share/applications/zecnode.desktop"
rm -f "$HOME/.config/autostart/zecnode-nosleep.desktop"

echo ""
echo "================================"
echo "      ZecNode Uninstalled"
echo "================================"
echo ""
echo "Blockchain data preserved at /mnt/zebra-data."
echo ""
echo "To reinstall:"
echo "  sudo apt install curl -y && curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install.sh | bash"
echo ""

#!/bin/bash
# ZecNode Web Dashboard Installer
# For headless Raspberry Pi setups

set -e

echo "================================"
echo "  ZecNode Web Dashboard Setup"
echo "================================"
echo ""

# Find zecnode-web directory
if [ -d "$HOME/zecnode/zecnode-web" ]; then
    WEB_DIR="$HOME/zecnode/zecnode-web"
elif [ -d "$HOME/zecnode-web" ]; then
    WEB_DIR="$HOME/zecnode-web"
else
    echo "Error: ZecNode web files not found."
    echo "Install git and clone the repo first:"
    echo "  sudo apt update && sudo apt install -y git && git clone https://github.com/mycousiinvinny/zecnode.git ~/zecnode"
    exit 1
fi

# Kill any existing server.py processes
echo "[1/3] Stopping any running instances..."
pkill -f "python3.*server.py" 2>/dev/null || true
sleep 1

# Install dependencies
echo "[2/3] Installing dependencies..."
if ! command -v pip3 &> /dev/null; then
    echo "  Installing pip3..."
    sudo apt install -y python3-pip
fi
sudo pip3 install flask flask-cors --break-system-packages

# Create systemd service
echo "[3/3] Setting up auto-start service..."
sudo tee /etc/systemd/system/zecnode-web.service > /dev/null <<EOF
[Unit]
Description=ZecNode Web Dashboard
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$WEB_DIR
ExecStart=/usr/bin/python3 -u $WEB_DIR/server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable zecnode-web
sudo systemctl start zecnode-web

# Get local IP
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "================================"
echo "  Setup Complete!"
echo "================================"
echo ""
echo "  Web dashboard: http://$LOCAL_IP:5000"
echo ""
echo "  Commands:"
echo "    sudo systemctl status zecnode-web   - Check status"
echo "    sudo systemctl restart zecnode-web  - Restart"
echo "    sudo systemctl stop zecnode-web     - Stop"
echo "    sudo systemctl disable zecnode-web  - Disable auto-start"
echo ""

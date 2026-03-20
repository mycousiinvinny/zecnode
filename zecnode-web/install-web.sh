#!/bin/bash
# ZecNode Web Dashboard Installer
# For headless Raspberry Pi setups

set -e

echo "================================"
echo "  ZecNode Web Dashboard Setup"
echo "================================"
echo ""

# Check if running on Pi
if [ ! -d "$HOME/zecnode/zecnode-web" ]; then
    echo "Error: ZecNode not found at ~/zecnode"
    echo "Clone the repo first: git clone https://github.com/mycousiinvinny/zecnode.git ~/zecnode"
    exit 1
fi

# Kill any existing server.py processes
echo "[1/3] Stopping any running instances..."
pkill -f "python3.*server.py" 2>/dev/null || true
sleep 1

# Install dependencies
echo "[2/3] Installing dependencies..."
pip3 install flask flask-cors --break-system-packages 2>/dev/null || pip3 install flask flask-cors

# Create systemd service
echo "[3/3] Setting up auto-start service..."
sudo bash -c "cat > /etc/systemd/system/zecnode-web.service" <<EOF
[Unit]
Description=ZecNode Web Dashboard
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/zecnode/zecnode-web
ExecStartPre=/bin/bash -c 'pkill -f "python3.*server.py" || true'
ExecStart=/usr/bin/python3 -u $HOME/zecnode/zecnode-web/server.py
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

# ZecNode Web Dashboard

A web-based dashboard for managing your Zcash node remotely. Control your node from any device on your network — phone, laptop, or tablet.

![ZecNode Web Dashboard](https://img.shields.io/badge/ZecNode-Web-f4b728)

## Features

- **Remote node control** — Start, stop, and restart your Zebra node from any browser
- **Real-time monitoring** — Sync progress, block height, peers, uptime, and disk usage
- **Lightwalletd management** — Toggle lightwalletd on/off with one click
- **Network map** — See your node and connected peers on a global map
- **Auto-start** — Runs as a system service, starts on boot
- **Mobile friendly** — Works on phones and tablets

## Requirements

- Raspberry Pi with ZecNode already installed and configured
- SSH access to the Pi
- SSD mounted and Zebra container set up

## Installation

SSH into your Raspberry Pi and run:

```bash
cd ~/zecnode/zecnode-web && ./install-web.sh
```

The script will:
1. Install required Python packages (Flask)
2. Set up a system service that starts automatically on boot
3. Display the URL to access your dashboard

## Usage

After installation, open a browser on any device connected to the same network and go to:

```
http://<your-pi-ip>:5000
```

To find your Pi's IP address:

```bash
hostname -I
```

## Service Commands

- Check status: `sudo systemctl status zecnode-web`
- Restart: `sudo systemctl restart zecnode-web`
- Stop: `sudo systemctl stop zecnode-web`
- Disable auto-start: `sudo systemctl disable zecnode-web`
- Enable auto-start: `sudo systemctl enable zecnode-web`

## Troubleshooting

**Dashboard not loading?**
- Make sure the service is running: `sudo systemctl status zecnode-web`
- Check that your device is on the same network as the Pi
- Verify the Pi's IP address: `hostname -I`

**Node controls not responding?**
- Make sure only one instance of server.py is running: `ps aux | grep server.py`
- Restart the service: `sudo systemctl restart zecnode-web`

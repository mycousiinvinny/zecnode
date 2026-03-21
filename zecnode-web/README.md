# ZecNode Web Dashboard

A web-based dashboard for managing your Zcash node remotely. Control your node from any device on your network — phone, laptop, or tablet.

![ZecNode Web Dashboard](https://img.shields.io/badge/ZecNode-Web-f4b728)

## Features

- **Remote node control** — Start, stop, and restart your Zebra node from any browser
- **Real-time monitoring** — Sync progress, block height, peers, uptime, and disk usage
- **Lightwalletd management** — Toggle lightwalletd on/off with one click
- **Network map (Coming Soon)** — See your node and connected peers on a global map
- **Auto-start** — Runs as a system service, starts on boot
- **Mobile friendly** — Works on phones and tablets

## Prerequisites

1. Flash **Raspberry Pi OS** to your SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. In the imager settings, enable **SSH** and set a **username/password**
3. Configure **WiFi** or plug in ethernet
4. Boot the Pi and SSH in: `ssh username@yourPiLocalIP`
5. Plug in your **SSD** (must be > 500GB)

## Headless Install (Fresh Pi)

If you're setting up a Raspberry Pi from scratch without a monitor, the CLI installer handles everything — system updates, Docker, SSD formatting, and starting the node.

SSH into your Pi and run:

```bash
git clone https://github.com/mycousiinvinny/zecnode.git ~/zecnode && python3 ~/zecnode/zecnode-web/cli-installer.py
```

The installer will:
1. Detect your SSD and let you select it (OS drives are excluded)
2. Update system packages
3. Install Docker
4. Reboot (required for Docker)
5. After reboot, run the installer again — it resumes automatically
6. Format and mount the SSD
7. Configure Docker to use the SSD
8. Pull and start the Zebra node

After the node is running, set up the web dashboard:

```bash
cd ~/zecnode/zecnode-web && ./install-web.sh
```

## Web Dashboard Install (Existing ZecNode)

If you already have ZecNode installed and running, just set up the web dashboard:

```bash
cd ~/zecnode/zecnode-web && ./install-web.sh
```

The script will:
1. Install required Python packages (Flask)
2. Set up a system service that starts automatically on boot
3. Display the URL to access your dashboard

## Usage

Open a browser on any device connected to the same network and go to:

```
http://<your-pi-ip>:5000
```

To find your Pi's IP address: `hostname -I`

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

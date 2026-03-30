# ZecNode Web Dashboard

A web based dashboard for managing your Zcash node remotely. Control your node from any device on your network — phone, laptop, or tablet.

![ZecNode Web Dashboard](https://img.shields.io/badge/ZecNode-Web-f4b728)

## Features

- **Remote node control** — Start, stop, and restart your Zebra node from any browser
- **Real-time monitoring** — Sync progress, block height, peers, uptime, and disk usage
- **Lightwalletd management** — Toggle lightwalletd on/off with one click
- **Network map** — Live map of every active Zcash node worldwide, discovered by a built-in P2P network crawler
- **Heatmap view** — Toggle between individual node dots and a heatmap showing node density
- **One-click updates** — Pull the latest version from GitHub directly from the dashboard
- **Auto-refresh logs** — Node logs update every 60 seconds while viewing
- **IPv4 and IPv6 support** — Crawler discovers nodes on both protocols
- **Auto-start** — Runs as a system service, starts on boot
- **Mobile friendly** — Works on phones and tablets

## Network Crawler

The dashboard includes a built-in Zcash P2P network crawler that discovers active nodes worldwide. It works by:

1. Connecting to DNS seed nodes
2. Reading Zebra's peer cache file to find nodes that connected inbound (including firewalled nodes)
3. Performing the Zcash protocol handshake (version/verack)
4. Requesting peer lists via `getaddr`
5. Recursively discovering new peers from responses
6. Geolocating all discovered IPs (IPv4 and IPv6) and plotting them on the map

The crawler runs automatically every 30 minutes with 20 concurrent connections and caches results so they persist across reboots. Discovered nodes expire after 7 days if not rediscovered.

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
sudo apt update && sudo apt install -y git && git clone https://github.com/mycousiinvinny/zecnode.git ~/zecnode && python3 ~/zecnode/zecnode-web/cli-installer.py
```

The installer will:
1. Detect your SSD and let you select it (OS drives are excluded)
2. Update system packages
3. Install Docker
4. Reboot (required for Docker) — your SSH session will disconnect, this is normal
5. After reboot, SSH back in and re-run the installer:
   ```bash
   python3 ~/zecnode/zecnode-web/cli-installer.py
   ```
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
3. Display the URL to access your dashboard (e.g. `http://192.168.x.x:5000`)

## Updating

From the dashboard, click the **Update** button to pull the latest version from GitHub and restart automatically.

Or manually via SSH:

```bash
cd ~/zecnode && git pull origin main && sudo systemctl restart zecnode-web
```

## Usage

Open a browser on any device connected to the same network and go to the URL shown at the end of the install script.

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

**Peers showing 0?**
- This is normal briefly after starting — the peer count is cached and will update once Zebra logs a new count

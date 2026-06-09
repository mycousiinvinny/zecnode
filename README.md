# ZecNode

Run a Zcash node in only 2 commands!

![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%7C%20Linux-green)

## Disclaimer

ZecNode is an independent community project and is not affiliated with, endorsed by, or associated with the Electric Coin Company, Zcash Foundation, or any official Zcash organization.

## Install

Open Terminal and run:

*sudo apt install curl -y && curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install.sh | bash*

Command after reboot:

*curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install.sh | bash*

Please report any bugs you find.

Enjoy!

## What is this?

A GUI installer and dashboard for running a Zcash full node. I built it because setting up a node manually is tedious - you have to install Docker, format drives, edit config files, etc. Even more tedious if you don't use Docker. This handles all of that.

## Why a Raspberry Pi?

Running a node on your main computer kind of sucks. It eats up resources, needs to stay on 24/7, and uses way more electricity than necessary. A Pi 5 with an SSD runs the full Zcash blockchain for like $5/year in electricity, sits in a corner, and just works. Set it and forget it.

## Requirements

- Raspberry Pi 5 (recommended) or any Linux PC
- External SSD (500GB minimum)
- Internet connection
- About 20 minutes for initial setup. Much less if your system is up to date.

## What it does

- Installs Docker and Zebra (Zcash node software)
- Formats and mounts your SSD
- Shows sync progress, peer count, disk usage
- Runs in the system tray
- **Web dashboard** for headless setups — manage and monitor your node from any browser on your network
- Notifies you when a new version is available, and updates in one click
- Restarts automatically after reboots or power outages
- Built-in **Learn** tab explaining the tech behind Zcash in plain English
- Optional **Tor** support — share your node over a private `.onion` address

## Connect privately over Tor (.onion)

ZecNode can expose your node over Tor as a `.onion` address, so wallets can connect **without ever revealing their IP to your server**. It's an opt-in toggle in Settings (and in the web dashboard) — flip it on and your node gets a permanent `.onion` address.

### Connecting a wallet to it

A `.onion` can only be reached *through* Tor, so the wallet needs a Tor path:

1. Install **Orbot** (the Tor app) on the phone and turn on its VPN mode — or use a wallet that has Tor built in.
2. In the wallet's server settings, point lightwalletd at your address:
   `http://<your-node>.onion:443`
   Use `http`, not `https` — Tor already encrypts the connection end-to-end, so no TLS is needed.
3. Sync. The wallet now talks to your node entirely over Tor.

> **Tip:** On the desktop dashboard, click **QR** next to your `.onion` to scan the address straight into your phone — no typing 56 characters.

Your normal (clearnet) wallet access keeps working unchanged — Tor is just an extra private door.

## Screenshot

<img width="988" height="903" alt="dashboard" src="https://github.com/user-attachments/assets/ff7866ec-7e5f-44c4-a61e-5fb08029ca95" />

## Why run a node?

More nodes = more decentralization = stronger network. That's it.

## Uninstall

If you ever need to uninstall, run:

*curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/uninstall.sh | bash*

Your blockchain data at `/mnt/zebra-data` is preserved, so reinstalling is near-instant.

## Roadmap

- Mac version coming eventually
- Windows version coming eventually



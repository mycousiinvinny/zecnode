# ZecNode

Run a Zcash node without touching the command line.

![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%7C%20Linux-green)
![License](https://img.shields.io/badge/License-MIT-blue)

## What is this?

A GUI installer and dashboard for running a Zcash full node. I built it because setting up a node manually is tedious - you have to install Docker, format drives, edit config files, etc. This handles all of that.

## Why a Raspberry Pi?

Running a node on your main computer kind of sucks. It eats up resources, needs to stay on 24/7, and uses way more electricity than necessary. A Pi 5 with an SSD runs the full Zcash blockchain for like $5/year in electricity, sits in a corner, and just works. Set it and forget it.

## Install

```bash
curl -sSL https://raw.githubusercontent.com/YOURUSERNAME/zecnode/main/install_zecnode.sh | bash
```

## Requirements

- Raspberry Pi 5 (recommended) or any Linux PC
- External SSD (500GB minimum)
- Internet connection
- About 30 minutes for initial setup

## What it does

- Installs Docker and Zebra (Zcash node software)
- Formats and mounts your SSD
- Shows sync progress, peer count, disk usage
- Runs in the system tray
- Restarts automatically after reboots or power outages

## Screenshots

*Coming soon*

## Why run a node?

More nodes = more decentralization = stronger network. That's it.

## Roadmap

- Mac version coming eventually
- Windows version coming eventually

## License

MIT - do whatever you want with it.

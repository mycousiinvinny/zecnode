# ZecNode

Run a Zcash node without touching the command line.

![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%7C%20Linux-green)

## Install

*sudo apt install curl -y && curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install_zecnode.sh | bash*

Command after reboot

*curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install_zecnode.sh | bash*

Curl has to be installed beforehand. Please report any bugs you find. Enjoy!

## What is this?

A GUI installer and dashboard for running a Zcash full node. I built it because setting up a node manually is tedious - you have to install Docker, format drives, edit config files, etc. This handles all of that.

## Why a Raspberry Pi?

Running a node on your main computer kind of sucks. It eats up resources, needs to stay on 24/7, and uses way more electricity than necessary. A Pi 5 with an SSD runs the full Zcash blockchain for like $5/year in electricity, sits in a corner, and just works. Set it and forget it.

## Requirements

- Raspberry Pi 5 (recommended) or any Linux PC
- External SSD (500GB minimum)
- Internet connection
- About 30 minutes for initial setup. Much less if your system is up to date.

## What it does

- Installs Docker and Zebra (Zcash node software)
- Formats and mounts your SSD
- Shows sync progress, peer count, disk usage
- Runs in the system tray
- Restarts automatically after reboots or power outages

## Screenshots
<img width="1184" height="1214" alt="getStarted" src="https://github.com/user-attachments/assets/2dcbc4b8-496a-406b-acbc-b07221fc5ade" />
<img width="1184" height="1214" alt="dockerinstall" src="https://github.com/user-attachments/assets/348660b4-a4d9-49a2-a521-5436fe40970d" />
<img width="1184" height="1214" alt="reboot" src="https://github.com/user-attachments/assets/7ad8e53d-9ea8-4b23-8adb-9ab011f76e57" />
<img width="1179" height="1211" alt="format" src="https://github.com/user-attachments/assets/7fc76ccc-c711-4c42-823e-353d5a1883a3" />
<img width="1179" height="1211" alt="sda" src="https://github.com/user-attachments/assets/ea79f6c9-ac3d-4d60-a74a-b8754e77ad6f" />
<img width="1179" height="1211" alt="formatinstall" src="https://github.com/user-attachments/assets/e4b59f4c-eefd-4cc7-9b0d-31e70bfa3adf" />
<img width="1183" height="1204" alt="yourallset" src="https://github.com/user-attachments/assets/24621b45-f8d0-45b5-8f3c-0a0bf6e114eb" />
<img width="764" height="861" alt="dashboard" src="https://github.com/user-attachments/assets/a948271f-801d-4180-888c-f455a8dea6a1" />

## Why run a node?

More nodes = more decentralization = stronger network. That's it.

## Roadmap

- Mac version coming eventually
- Windows version coming eventually

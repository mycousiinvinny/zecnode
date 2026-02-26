# ZecNode

Run a Zcash node in only 2 commands!

![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%7C%20Linux-green)

## Disclaimer

ZecNode is an independent community project and is not affiliated with, endorsed by, or associated with the Electric Coin Company, Zcash Foundation, or any official Zcash organization.

## Install

Open Terminal and run:

*sudo apt install curl -y && curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install.sh | sudo bash*

Command after reboot:

*curl -sSL https://raw.githubusercontent.com/mycousiinvinny/zecnode/main/install.sh | sudo bash* 

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
- Restarts automatically after reboots or power outages

## Screenshot

<img width="988" height="903" alt="dashboard" src="https://github.com/user-attachments/assets/ff7866ec-7e5f-44c4-a61e-5fb08029ca95" />

## Why run a node?

More nodes = more decentralization = stronger network. That's it.

## Roadmap

- Mac version coming eventually
- Windows version coming eventually

## Beta Testing



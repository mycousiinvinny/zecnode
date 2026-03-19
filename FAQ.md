# FAQ

## Why does it ask for my system password twice?

**Before reboot:** The installer needs your system password to update system packages and install Docker. A reboot is required for Docker permissions to take effect.

**After reboot:** Your system password is needed again to format the SSD, configure system mounts, and start the Zcash node.

## Why is a reboot required?

Docker requires your user to be added to the "docker" group. This group membership only takes effect after logging out and back in, or rebooting.

## How long does the initial sync take?

Depends on your internet speed and hardware. On a Raspberry Pi 5 with decent internet, expect 48-120 hours for a full sync.

## Can I use an HDD instead of an SSD?

Not recommended. The Zcash blockchain requires fast random reads/writes. An HDD will be extremely slow and may not keep up with the network.

## What's the minimum SSD size?

1 TB is recommended. 500 GB will work. The blockchain is currently around 285GB and growing.

## Can I run this on something other than a Raspberry Pi?

Yes, any Linux system with Docker support will work. Ubuntu, Debian, and their derivatives are tested.

## How do I check if my node is synced?

Open the dashboard - when sync progress shows 100% and displays "✓ Synced", you're fully synced.

## How do I update ZecNode?

Right click the green circle at the top right of your screen. Click "Update ZecNode". That's it!

## Will my node still run if I close the dashboard?

Yes! Your node will run in the background.

## What happens if my computer shuts off?

As long as your node was running when your computer turned off, it will automatically start the node back up when your computer turns back on. Keep in mind, if your node was stopped for any reason prior to being turned off, it will not auto start. Node running when reboot = auto start on reboot. Node stopped when reboot = no auto start on reboot. 

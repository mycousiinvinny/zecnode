# FAQ

## Why does it ask for my password twice?

**Before reboot:** The installer needs your password to update system packages and install Docker. A reboot is required for Docker permissions to take effect.

**After reboot:** Your password is needed again to format the SSD, configure system mounts, and start the Zcash node.

## Why is a reboot required?

Docker requires your user to be added to the "docker" group. This group membership only takes effect after logging out and back in, or rebooting.

## How long does the initial sync take?

Depends on your internet speed and hardware. On a Raspberry Pi 5 with decent internet, expect 24-48 hours for a full sync.

## Can I use an HDD instead of an SSD?

Not recommended. The Zcash blockchain requires fast random reads/writes. An HDD will be extremely slow and may not keep up with the network.

## What's the minimum SSD size?

500GB recommended. The blockchain is currently around 100GB and growing.

## Can I run this on something other than a Raspberry Pi?

Yes, any Linux system with Docker support will work. Ubuntu, Debian, and their derivatives are tested.

## How do I check if my node is synced?

Open the dashboard - when sync progress shows 100% and displays "✓ Synced", you're fully synced.

## How do I update ZecNode?

Run the install command again. It will update the app files without touching your blockchain data.

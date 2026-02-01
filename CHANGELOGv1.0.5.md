# Changelog v1.0.5

## v1.0.5 - February 1st 2026

- Fixed: Changed refresh from 1 second to every 5 seconds. This reduces thread creation by 80%. (I think the freeze issue is fixed. After dashboard was open for long periods of time, it would freeze after closing. Testing potential fixes. Not a memory leak.)

- Updated: installer & dashboard UI
  
- Added: Tray icon toggle (single click show/hide)
  
- Added: Close Dashboard in tray menu
  
- Added: Auto-update and restart (no sudo needed)
  
- Fixed: sync progress bar rounding. Now it updates properly.

## v1.0.4 - January 25th 2026

- Added: Update ZecNode & Update Zebra in tray menu. Update Zebra **DOES ERASE BLOCKCHAIN DATA**. Update Zebra once a year or if recommended by Zcash Foundation

- Added: UI tweaks

## v1.0.3 - January 24th 2026

- Added: Live ZEC price display with 24h change (updates every 30 seconds)

## v1.0.2 - January 20th 2026

- Fixed: Significant dashboard freeze when closing dashboard after 55% sync or if dashboard has stayed open for long periods of time. This occured if you didnt close dashboard after initial install. ~10 second freeze still happens. 

- Fixed: App icon now shows as "open" in taskbar/dock when dashboard is running.

- Added: Zcash logo as app icon


## v1.0.1 - January 2026

- Fixed: App now opens properly from application menu after closing

- Fixed: Closing dashboard no longer leaves orphaned tray icons

- Added: disable sleep mode in installer


## v1.0.0 - January 2026

Initial release.

- GUI installer for Zcash nodes
- Dashboard with sync progress, peer count, uptime, disk usage
- Auto-detects existing Zebra nodes (skips straight to dashboard)
- System tray with status indicator. Right click to start/stop node, close dashboard
- Auto-restart after reboot. Node must still be running when reboot happens. If node is manually stopped, it will NOT restart on reboot.
- Internet disconnect detection (yellow status, frozen stats)
- Resizable window for different screen sizes
- Works on Raspberry Pi and Linux
- Added ZecNode to application menu for easy launch

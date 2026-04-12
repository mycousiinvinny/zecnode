# v2.1.1 - April 12th 2026 - UI & Bug Fixes

- Fixed lightwalletd permission error (Error 13) when starting on root-owned SSD mount

- Fixed ZecNode update failing when local files were modified (uses git reset instead of pull)

- Fixed crash on launch (_threads not initialized before tray setup)

- Updated all Zebra version fallbacks from hardcoded versions to "latest"

- Lightwalletd toggle replaced with animated sliding switch

- Removed URL row from lightwalletd card — IP now accessible from tray menu

- Added "IP: (click to copy)" to system tray menu

- Cleaned up lightwalletd card layout — status text inline with title

# v2.1.0 - March 18th 2026 - Performance & Stability

 - Fixed freeze on quit — replaced SIGKILL with clean Qt shutdown
   
 - Reduced refresh interval from 3s to 10s
    
 - Price updates changed from 30s to 120s
   
 - Disk usage checks reduced to every 60s instead of every refresh
   
 - Internet check cached, re-checked every 60s
   
 - Zebra version fetched once on node start instead of every refresh
   
 - Docker logs reduced from 200 to 30 lines per status check
   
 - Docker inspect (uptime) cached instead of querying every refresh
   
 - Tray icon only redrawn when state changes
   
 - Removed redundant widget repaint on every refresh
   
 - Fixed lightwalletd thread spam — limited to one auto-start/stop attempt at a time
   
 - Threads cleaned up immediately on finish instead of every 30 minutes
   
 - Lightwalletd now starts/stops with the node instead of waiting for next refresh
   
 - Sync progress and block height cached — no more 0% after stop/start or reboot

# v2.0.0 - March 9th 2026

- Fixed major freeze after closing dashboard. Caused by zombie Qthread buildup. STILL TESTING

# v2.0.0 - February 20th 2026

## Major Fixes:

- Fixed volume mount paths. Data now correctly saves to SSD instead of inside Docker container and fixed data loss on docker rm zebra

- Fixed double window bug after reboot with existing data

- Fixed UI flicker when stopping node (status briefly showing "Running" before "Stopped")

## New Features:

- Added Zebra version display on dashboard (shows when node is running)

- Added "Reset ZecNode" in tray menu (clears config, restarts fresh)

- Added "Update to Beta" in tray menu (pulls from beta branch)

- Added zecnode --reset command line option

- Added info tooltip for Sync Progress (explains 0% after updates)

- Added auto-mount detection for SSDs with existing Zebra data

## Improvements: 

- Removed welcome dialog - goes straight to installer with latest Zebra

- Update Zebra now pulls latest instead of same version
  
- Update Zebra now includes network and RPC settings for lightwalletd compatibility
  
- Zebra version label hidden when node stopped, shows when running
  
- Both info icons (Sync Progress, Lightwalletd) now match styling with hover effect
  
- Refresh rate changed to 3 seconds (was 5)
  
- Thread cleanup runs every 30 minutes (was 1 hour)
  
- Removed processEvents() on quit to prevent potential freeze after long runtime (currently testing)

## Lightwalletd Fixes: 

- Fixed cache persistence across restarts

- Fixed URL format (http:// instead of grpc://)

- Fixed UI freeze when toggling lightwalletd on/off

# v1.0.5 - February 1st 2026

- Fixed: Changed refresh from 1 second to every 5 seconds. This reduces thread creation by 80%. (I think the freeze issue is fixed. After dashboard was open for long periods of time, it would freeze after closing. Testing potential fixes. Not a memory leak.)

- Updated: installer & dashboard UI
  
- Added: Tray icon toggle (single click show/hide)
  
- Added: Close Dashboard in tray menu
  
- Added: Auto-update and restart (no sudo needed)
  
- Fixed: sync progress bar rounding. Now it updates properly.

# v1.0.4 - January 25th 2026

- Added: Update ZecNode & Update Zebra in tray menu. Update Zebra **DOES ERASE BLOCKCHAIN DATA**. Update Zebra once a year or if recommended by Zcash Foundation

- Added: UI tweaks

# v1.0.3 - January 24th 2026

- Added: Live ZEC price display with 24h change (updates every 30 seconds)

# v1.0.2 - January 20th 2026

- Fixed: Significant dashboard freeze when closing dashboard after 55% sync or if dashboard has stayed open for long periods of time. This occured if you didnt close dashboard after initial install. ~10 second freeze still happens. 

- Fixed: App icon now shows as "open" in taskbar/dock when dashboard is running.

- Added: Zcash logo as app icon


# v1.0.1 - January 2026

- Fixed: App now opens properly from application menu after closing

- Fixed: Closing dashboard no longer leaves orphaned tray icons

- Added: disable sleep mode in installer


# v1.0.0 - January 2026

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

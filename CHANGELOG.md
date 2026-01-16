# Changelog

## v1.0.0 - January 2025

Initial release.

- GUI installer for Zcash nodes
- Dashboard with sync progress, peer count, uptime, disk usage
- Auto-detects existing Zebra nodes (skips straight to dashboard)
- System tray with status indicator
- Auto-restart after reboot. Node must still be running when reboot happens. If node is manually stopped, it will NOT restart on reboot.
- Internet disconnect detection (yellow status, frozen stats)
- Resizable window for different screen sizes
- Works on Raspberry Pi and Linux
- Added sleep mode disabled. Pi must be on 24/7 for node to run

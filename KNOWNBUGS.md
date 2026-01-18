# Known Bugs

## Potential Memory Leak During Sync

**Status:** Investigating

**Symptoms:**
- Dashboard becomes slow/unresponsive over time
- System may freeze after extended use
- RSS memory usage climbs continuously without dropping

**When it occurs:**
- Most noticeable while node is actively syncing past 50%
- The dashboard refresh loop runs continuously, updating sync progress, block height, peers, etc.

**Possible causes:**
- String formatting creating new objects every refresh cycle
- Docker subprocess calls not being cleaned up
- Log parsing accumulating data

**Workaround:**
- Close and reopen the dashboard periodically during long sync sessions
- The node continues running in Docker regardless of dashboard state

**Monitoring:**
```bash
watch -n 5 'ps -o pid,rss,vsz,comm -p $(pgrep -f main.py)'
```

Normal RSS: ~130MB  
Concerning: 250MB+  
Problem: 400MB+

---

*Last updated: January 2026*

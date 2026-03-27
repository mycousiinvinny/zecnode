#!/usr/bin/env python3
"""
ZecNode Web Dashboard - Backend API
Provides REST API for controlling the Zcash node
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os
import sys
import threading

# Add parent directory to path to import node_manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from node_manager import NodeManager
from config import Config, VERSION
from crawler import ZcashCrawler

app = Flask(__name__, static_folder='static')
CORS(app)

# Initialize config and node manager
config = Config()
data_path = config.get_data_path()
zebra_version = config.get("zebra_version", "latest")
node_manager = NodeManager(data_path=data_path, zebra_version=zebra_version)

# Caching for expensive calls
import time

_disk_cache = {"ssd": "--", "sd": "--", "time": 0}
_version_cache = {"version": "--", "fetched": False}
# Start network crawler in background
crawler = ZcashCrawler()
crawler_thread = threading.Thread(target=crawler.start_periodic, args=(1800,), daemon=True)
crawler_thread.start()

_sync_cache = {
    "sync_percent": config.get("cached_sync_percent", 0.0),
    "height": config.get("cached_height", 0)
}


# ==================== STATIC FILES ====================

@app.route('/')
def index():
    """Serve the main dashboard"""
    return send_from_directory('static', 'index.html')


@app.route('/<path:path>')
def static_files(path):
    """Serve static files"""
    return send_from_directory('static', path)


# ==================== NODE STATUS ====================

@app.route('/api/status')
def get_status():
    """Get current node status"""
    now = time.time()

    status = node_manager.get_status()

    # Cache sync progress so it doesn't show 0% after stop/start
    sync_pct = status.sync_percent
    current_height = status.current_height
    if sync_pct > 0 or current_height > 0:
        _sync_cache["sync_percent"] = sync_pct
        _sync_cache["height"] = current_height
        config.set("cached_sync_percent", sync_pct)
        config.set("cached_height", current_height)
    else:
        sync_pct = _sync_cache["sync_percent"]
        current_height = _sync_cache["height"]

    # Cache disk usage (refresh every 60 seconds)
    if now - _disk_cache["time"] >= 60:
        _disk_cache["ssd"], _disk_cache["sd"] = node_manager.get_disk_usage()
        _disk_cache["time"] = now

    # Cache zebra version (fetch once when node is running, reset when stopped)
    if status.running and not _version_cache["fetched"]:
        _version_cache["version"] = node_manager.get_zebra_version(config)
        _version_cache["fetched"] = True
    elif not status.running:
        _version_cache["fetched"] = False

    # Auto-start/stop lightwalletd (same logic as desktop)
    lwd_running = node_manager.is_lightwalletd_running()
    lwd_enabled = config.get("lightwalletd_enabled", False)
    is_synced = status.running and sync_pct >= 99.9

    if lwd_enabled and is_synced and not lwd_running:
        lwd_ok, _ = node_manager.start_lightwalletd()
        lwd_running = lwd_ok
    elif lwd_running and not status.running:
        node_manager.stop_lightwalletd()
        lwd_running = False

    lwd_url = node_manager.get_lightwalletd_url() if lwd_running else None

    return jsonify({
        "running": status.running,
        "sync_percent": sync_pct,
        "current_height": current_height,
        "target_height": status.target_height,
        "peer_count": status.peer_count,
        "uptime": status.uptime,
        "version": _version_cache["version"],
        "ssd_usage": _disk_cache["ssd"],
        "sd_usage": _disk_cache["sd"],
        "lightwalletd": {
            "running": lwd_running,
            "url": lwd_url
        },
        "zecnode_version": VERSION
    })


# ==================== NODE CONTROL ====================

@app.route('/api/start', methods=['POST'])
def start_node():
    """Start the Zebra node — returns immediately, runs in background"""
    # Pre-flight checks (fast, run synchronously)
    if not os.path.ismount(node_manager.MOUNT_PATH):
        return jsonify({
            "success": False,
            "message": f"SSD not mounted at {node_manager.MOUNT_PATH}. Please reconnect the SSD and try again."
        })

    thread = threading.Thread(target=node_manager.start_node, daemon=True)
    thread.start()
    return jsonify({
        "success": True,
        "message": "Starting node..."
    })


@app.route('/api/stop', methods=['POST'])
def stop_node():
    """Stop the Zebra node"""
    def _stop_all():
        if node_manager.is_lightwalletd_running():
            node_manager.stop_lightwalletd()
        node_manager.stop_node()

    thread = threading.Thread(target=_stop_all, daemon=True)
    thread.start()
    return jsonify({
        "success": True,
        "message": "Stopping node...",
        "lightwalletd": {
            "running": False,
            "url": None
        }
    })


@app.route('/api/restart', methods=['POST'])
def restart_node():
    """Restart the Zebra node — returns immediately, runs in background"""
    def _restart():
        if node_manager.is_lightwalletd_running():
            node_manager.stop_lightwalletd()
        node_manager.restart_node()

    thread = threading.Thread(target=_restart, daemon=True)
    thread.start()
    return jsonify({
        "success": True,
        "message": "Restarting node..."
    })


# ==================== LOGS ====================

@app.route('/api/logs')
def get_logs():
    """Get recent node logs"""
    lines = request.args.get('lines', 100, type=int)
    logs = node_manager.get_logs(lines=lines)
    return jsonify({
        "logs": logs
    })


# ==================== LIGHTWALLETD ====================

@app.route('/api/lightwalletd/start', methods=['POST'])
def start_lightwalletd():
    """Start lightwalletd"""
    success, message = node_manager.start_lightwalletd()
    if success:
        config.set("lightwalletd_enabled", True)
    return jsonify({
        "success": success,
        "message": message,
        "url": node_manager.get_lightwalletd_url() if success else None
    })


@app.route('/api/lightwalletd/stop', methods=['POST'])
def stop_lightwalletd():
    """Stop lightwalletd"""
    success, message = node_manager.stop_lightwalletd()
    if success:
        config.set("lightwalletd_enabled", False)
    return jsonify({
        "success": success,
        "message": message
    })


@app.route('/api/lightwalletd/toggle', methods=['POST'])
def toggle_lightwalletd():
    """Toggle lightwalletd on/off"""
    if node_manager.is_lightwalletd_running():
        success, message = node_manager.stop_lightwalletd()
        if success:
            config.set("lightwalletd_enabled", False)
        return jsonify({
            "success": success,
            "message": message,
            "running": False
        })
    else:
        success, message = node_manager.start_lightwalletd()
        if success:
            config.set("lightwalletd_enabled", True)
        return jsonify({
            "success": success,
            "message": message,
            "running": success,
            "url": node_manager.get_lightwalletd_url() if success else None
        })


# ==================== SYSTEM INFO ====================

@app.route('/api/info')
def get_info():
    """Get system info"""
    local_ip = node_manager.get_local_ip()
    docker_root = node_manager.get_docker_root_dir()
    docker_on_ssd = node_manager.verify_docker_on_ssd()
    
    return jsonify({
        "local_ip": local_ip,
        "docker_root": docker_root,
        "docker_on_ssd": docker_on_ssd,
        "data_path": str(data_path),
        "zecnode_version": VERSION
    })


# ==================== NODE REGISTRATION (for map) ====================

# In-memory storage for registered nodes (would use database in production)
registered_nodes = []

# Cache for peer nodes (refresh every 30 minutes)
peers_cache = {
    "peers": [],
    "last_fetch": 0
}

@app.route('/api/nodes')
def get_nodes():
    """Get list of registered public nodes"""
    return jsonify({
        "nodes": registered_nodes,
        "count": len(registered_nodes)
    })


@app.route('/api/nodes/peers')
def get_peers():
    """Get peer nodes from Zebra's peer cache and geolocate them"""
    import json
    import time
    import os
    
    # Check cache (30 minute TTL)
    if time.time() - peers_cache["last_fetch"] < 1800 and peers_cache["peers"]:
        return jsonify({
            "success": True,
            "peers": peers_cache["peers"],
            "count": len(peers_cache["peers"]),
            "cached": True
        })
    
    try:
        # Read peers file
        peers_file = "/mnt/zebra-data/zebra-cache/network/mainnet.peers"
        
        if not os.path.exists(peers_file):
            return jsonify({
                "success": False,
                "error": "Peers file not found",
                "peers": []
            })
        
        with open(peers_file, 'r') as f:
            lines = f.readlines()
        
        # Parse IPs (limit to 100 for geolocation)
        ips = []
        for line in lines[:100]:
            line = line.strip()
            if ':' in line:
                ip = line.split(':')[0]
                # Skip IPv6 and private IPs
                if '.' in ip and not ip.startswith('10.') and not ip.startswith('192.168.') and not ip.startswith('172.'):
                    ips.append(ip)
        
        # Batch geolocation using ip-api.com batch endpoint (up to 100 at once)
        # POST to http://ip-api.com/batch with JSON array of IPs
        import urllib.request
        
        batch_url = 'http://ip-api.com/batch?fields=status,query,lat,lon,city,country'
        batch_data = json.dumps(ips[:100]).encode('utf-8')
        
        req = urllib.request.Request(
            batch_url,
            data=batch_data,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            geo_results = json.loads(response.read().decode())
        
        peers = []
        for geo in geo_results:
            if geo.get("status") == "success" and geo.get("lat") and geo.get("lon"):
                peers.append({
                    "ip": geo.get("query"),
                    "lat": geo.get("lat"),
                    "lng": geo.get("lon"),
                    "city": geo.get("city", ""),
                    "country": geo.get("country", ""),
                    "status": "online"
                })
        
        # Update cache
        peers_cache["peers"] = peers
        peers_cache["last_fetch"] = time.time()
        
        return jsonify({
            "success": True,
            "peers": peers,
            "count": len(peers),
            "total_in_file": len(lines),
            "cached": False
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "peers": peers_cache.get("peers", [])
        })


@app.route('/api/nodes/lightwalletd')
def get_lightwalletd_servers():
    """Fetch lightwalletd servers from hosh.zec.rocks and geolocate them"""
    import urllib.request
    import json
    import socket
    import time
    
    # Check cache (10 minute TTL)
    if time.time() - lwd_servers_cache["last_fetch"] < 600 and lwd_servers_cache["servers"]:
        return jsonify({
            "success": True,
            "servers": lwd_servers_cache["servers"],
            "count": len(lwd_servers_cache["servers"]),
            "cached": True
        })
    
    try:
        # Fetch server list from hosh.zec.rocks
        with urllib.request.urlopen('https://hosh.zec.rocks/api/v0/zec.json', timeout=10) as response:
            data = json.loads(response.read().decode())
        
        servers = []
        
        # Process each server (limit to online servers)
        for server in data:
            if not isinstance(server, dict):
                continue
                
            # Skip offline servers
            if server.get("status") != "Online":
                continue
            
            # Get server hostname
            host = server.get("server", "")
            if not host:
                continue
            
            # Skip .onion addresses (can't geolocate)
            if ".onion" in host:
                continue
            
            # Extract hostname (remove port)
            hostname = host.split(":")[0]
            
            try:
                # Resolve hostname to IP
                ip = socket.gethostbyname(hostname)
                
                # Geolocate IP using ipapi.co (more permissive)
                geo_url = f'https://ipapi.co/{ip}/json/'
                req = urllib.request.Request(geo_url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
                with urllib.request.urlopen(req, timeout=5) as geo_response:
                    geo_data = json.loads(geo_response.read().decode())
                
                if geo_data.get("latitude") and geo_data.get("longitude"):
                    servers.append({
                        "name": host,
                        "url": f"https://{host}" if ":443" in host else f"http://{host}",
                        "lat": geo_data.get("latitude"),
                        "lng": geo_data.get("longitude"),
                        "city": geo_data.get("city"),
                        "country": geo_data.get("country_name"),
                        "status": "online",
                        "version": server.get("version", ""),
                        "uptime": server.get("calendar_uptime", ""),
                        "block_height": server.get("block_height", 0)
                    })
                    
                    # Rate limit to avoid hitting API too hard
                    time.sleep(0.2)
                    
            except Exception as e:
                # Skip servers we can't resolve/geolocate
                continue
            
            # Limit to first 50 servers to avoid timeout
            if len(servers) >= 50:
                break
        
        # Update cache
        lwd_servers_cache["servers"] = servers
        lwd_servers_cache["last_fetch"] = time.time()
        
        return jsonify({
            "success": True,
            "servers": servers,
            "count": len(servers),
            "cached": False
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "servers": lwd_servers_cache.get("servers", [])
        })


# Cache for lightwalletd servers (refresh every 10 minutes)
lwd_servers_cache = {
    "servers": [],
    "last_fetch": 0
}


@app.route('/api/nodes/self')
def get_self_node():
    """Get this node's info with geolocation"""
    import urllib.request
    import json
    
    try:
        # Get public IP and geolocation
        with urllib.request.urlopen('https://ipapi.co/json/', timeout=5) as response:
            geo_data = json.loads(response.read().decode())
        
        status = node_manager.get_status()
        lwd_running = node_manager.is_lightwalletd_running()
        
        return jsonify({
            "success": True,
            "node": {
                "name": "My ZecNode",
                "lat": geo_data.get("latitude"),
                "lng": geo_data.get("longitude"),
                "city": geo_data.get("city"),
                "country": geo_data.get("country_name"),
                "ip": geo_data.get("ip"),
                "status": "online" if status.running else "offline",
                "sync": status.sync_percent,
                "lwd_running": lwd_running,
                "lwd_url": node_manager.get_lightwalletd_url() if lwd_running else None
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route('/api/nodes/register', methods=['POST'])
def register_node():
    """Register this node as a public lightwalletd server"""
    data = request.get_json() or {}
    
    # Get node info
    local_ip = node_manager.get_local_ip()
    lwd_running = node_manager.is_lightwalletd_running()
    
    if not lwd_running:
        return jsonify({
            "success": False,
            "message": "Lightwalletd must be running to register"
        }), 400
    
    node_info = {
        "name": data.get("name", f"ZecNode-{local_ip}"),
        "url": data.get("url", node_manager.get_lightwalletd_url()),
        "ip": local_ip,
        "status": "online"
    }
    
    # Add to registered nodes (in production, would save to database)
    registered_nodes.append(node_info)
    
    return jsonify({
        "success": True,
        "message": "Node registered",
        "node": node_info
    })


# ==================== CRAWLED NODES ====================

@app.route('/api/nodes/crawled')
def get_crawled_nodes():
    """Get all discovered Zcash nodes from the network crawler"""
    nodes = crawler.get_nodes()
    return jsonify({
        "success": True,
        "nodes": nodes,
        "count": len(nodes),
        "last_crawl": crawler.last_crawl_time
    })


@app.route('/api/nodes/crawl', methods=['POST'])
def trigger_crawl():
    """Manually trigger a network crawl"""
    if crawler.is_crawling:
        return jsonify({"success": False, "message": "Crawl already in progress"})
    threading.Thread(target=crawler.run_crawl, daemon=True).start()
    return jsonify({"success": True, "message": "Crawl started"})


# ==================== UPDATE ====================

@app.route('/api/update', methods=['POST'])
def update_dashboard():
    """Pull latest code from GitHub and restart the service"""
    import subprocess

    # Find the repo root (parent of zecnode-web)
    web_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(web_dir)

    try:
        # Git pull
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=repo_dir,
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            return jsonify({
                "success": False,
                "message": f"Git pull failed: {result.stderr.strip()}"
            })

        pull_output = result.stdout.strip()

        if "Already up to date" in pull_output:
            return jsonify({
                "success": True,
                "message": "Already up to date",
                "updated": False
            })

        # Restart the service in background so the response can be sent
        subprocess.Popen(
            ["sudo", "systemctl", "restart", "zecnode-web"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        return jsonify({
            "success": True,
            "message": "Update pulled. Dashboard is restarting...",
            "updated": True
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "message": "Update timed out"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        })


# ==================== MAIN ====================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='ZecNode Web Dashboard')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', default=5000, type=int, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    print(f"Starting ZecNode Web Dashboard on http://{args.host}:{args.port}")
    print(f"Access from other devices: http://{node_manager.get_local_ip()}:{args.port}")
    
    app.run(host=args.host, port=args.port, debug=args.debug)

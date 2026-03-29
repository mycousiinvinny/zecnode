#!/usr/bin/env python3
"""
ZecNode Network Crawler
Discovers active Zcash nodes by implementing the P2P wire protocol from scratch.
Connects to DNS seeds, performs handshakes, and recursively discovers peers.
"""

import hashlib
import json
import os
import random
import socket
import struct
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import urllib.request

# ==================== ZCASH PROTOCOL CONSTANTS ====================

MAGIC = b'\x24\xe9\x27\x64'  # Zcash mainnet
MAINNET_PORT = 8233
PROTOCOL_VERSION = 170140  # NU6 minimum (rejected below this)
USER_AGENT = b'/ZecNode-Crawler:0.1.0/'
SERVICES = 0  # We don't offer any services

DNS_SEEDS = [
    'mainnet.seeder.zfnd.org',
    'mainnet.is.yolo.money',
]

# Header: magic(4) + command(12) + payload_len(4) + checksum(4) = 24 bytes
HEADER_SIZE = 24


# ==================== WIRE PROTOCOL ====================

def double_sha256(data: bytes) -> bytes:
    """SHA256(SHA256(data))"""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def build_header(command: str, payload: bytes) -> bytes:
    """Build a 24-byte message header."""
    cmd_bytes = command.encode('ascii').ljust(12, b'\x00')
    checksum = double_sha256(payload)[:4]
    return struct.pack('<4s12sI', MAGIC, cmd_bytes, len(payload)) + checksum


def build_message(command: str, payload: bytes = b'') -> bytes:
    """Build a complete message (header + payload)."""
    return build_header(command, payload) + payload


def encode_var_str(s: bytes) -> bytes:
    """Encode a variable-length string (compact size + bytes)."""
    return encode_compact_size(len(s)) + s


def encode_compact_size(n: int) -> bytes:
    """Encode a Bitcoin/Zcash compact size integer."""
    if n < 253:
        return struct.pack('<B', n)
    elif n <= 0xFFFF:
        return struct.pack('<BH', 253, n)
    elif n <= 0xFFFFFFFF:
        return struct.pack('<BI', 254, n)
    else:
        return struct.pack('<BQ', 255, n)


def decode_compact_size(data: bytes, offset: int) -> Tuple[int, int]:
    """Decode a compact size integer. Returns (value, new_offset)."""
    first = data[offset]
    if first < 253:
        return first, offset + 1
    elif first == 253:
        return struct.unpack_from('<H', data, offset + 1)[0], offset + 3
    elif first == 254:
        return struct.unpack_from('<I', data, offset + 1)[0], offset + 5
    else:
        return struct.unpack_from('<Q', data, offset + 1)[0], offset + 9


def ip_to_ipv6_mapped(ip: str) -> bytes:
    """Convert IPv4 string to 16-byte IPv6-mapped address."""
    parts = [int(x) for x in ip.split('.')]
    return b'\x00' * 10 + b'\xff\xff' + bytes(parts)


def ipv6_to_ipv4(addr: bytes) -> Optional[str]:
    """Extract IPv4 from 16-byte IPv6-mapped address. Returns None if not IPv4."""
    if addr[:12] == b'\x00' * 10 + b'\xff\xff':
        return '.'.join(str(b) for b in addr[12:16])
    return None


def bytes_to_ipv6(addr: bytes) -> Optional[str]:
    """Convert 16-byte address to IPv6 string. Returns None if it's IPv4-mapped or all zeros."""
    if addr == b'\x00' * 16:
        return None
    # Skip IPv4-mapped — handled by ipv6_to_ipv4
    if addr[:12] == b'\x00' * 10 + b'\xff\xff':
        return None
    # Format as IPv6
    groups = [f'{addr[i] << 8 | addr[i+1]:x}' for i in range(0, 16, 2)]
    return ':'.join(groups)


def is_public_ipv6(ip: str) -> bool:
    """Check if an IPv6 address is publicly routable."""
    if ip.startswith('fe80:') or ip.startswith('fc') or ip.startswith('fd'):
        return False  # link-local or unique local
    if ip == '::1' or ip.startswith('::ffff:'):
        return False  # loopback or IPv4-mapped
    return True


def ip_to_bytes(ip: str) -> bytes:
    """Convert IPv4 or IPv6 string to 16-byte address."""
    if ':' in ip:
        return socket.inet_pton(socket.AF_INET6, ip)
    return ip_to_ipv6_mapped(ip)


def build_net_addr(ip: str, port: int, services: int = 0) -> bytes:
    """Build a 26-byte network address (services + ipv6 + port)."""
    return struct.pack('<Q', services) + ip_to_bytes(ip) + struct.pack('>H', port)


def build_version_payload(remote_ip: str, remote_port: int) -> bytes:
    """Build the version message payload."""
    payload = b''
    payload += struct.pack('<i', PROTOCOL_VERSION)     # nVersion
    payload += struct.pack('<Q', SERVICES)              # nServices
    payload += struct.pack('<q', int(time.time()))      # nTime
    payload += build_net_addr(remote_ip, remote_port)   # addr_recv (26 bytes)
    payload += build_net_addr('0.0.0.0', 0)             # addr_from (26 bytes)
    payload += struct.pack('<Q', random.getrandbits(64)) # nNonce
    payload += encode_var_str(USER_AGENT)               # strSubVer
    payload += struct.pack('<i', 0)                     # nStartHeight
    payload += struct.pack('<?', False)                 # fRelay
    return payload


def parse_addr_payload(payload: bytes) -> List[Tuple[str, int]]:
    """Parse an addr message payload. Returns list of (ip, port) tuples."""
    peers = []
    try:
        count, offset = decode_compact_size(payload, 0)
        # Sanity check
        if count > 5000:
            return peers

        for _ in range(count):
            if offset + 30 > len(payload):
                break
            # timestamp (4) + services (8) + ipv6 (16) + port (2) = 30 bytes
            _timestamp = struct.unpack_from('<I', payload, offset)[0]
            offset += 4
            _services = struct.unpack_from('<Q', payload, offset)[0]
            offset += 8
            addr_bytes = payload[offset:offset + 16]
            offset += 16
            port = struct.unpack_from('>H', payload, offset)[0]
            offset += 2

            # Try IPv4 first, then IPv6
            ip = ipv6_to_ipv4(addr_bytes)
            if ip and is_public_ip(ip) and port == MAINNET_PORT:
                peers.append((ip, port))
            else:
                ip6 = bytes_to_ipv6(addr_bytes)
                if ip6 and is_public_ipv6(ip6) and port == MAINNET_PORT:
                    peers.append((ip6, port))
    except Exception:
        pass

    return peers


def is_public_ip(ip: str) -> bool:
    """Check if an IP address is publicly routable."""
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False

    if a == 0 or a == 10 or a == 127:
        return False
    if a == 172 and 16 <= b <= 31:
        return False
    if a == 192 and b == 168:
        return False
    if a >= 224:  # multicast / reserved
        return False
    return True


# ==================== NODE CONNECTION ====================

def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes from socket."""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data


def recv_message(sock: socket.socket) -> Tuple[str, bytes]:
    """Receive one message from socket. Returns (command, payload)."""
    header = recv_exact(sock, HEADER_SIZE)
    magic = header[:4]
    if magic != MAGIC:
        raise ValueError(f"Bad magic: {magic.hex()}")

    command = header[4:16].rstrip(b'\x00').decode('ascii')
    payload_len = struct.unpack_from('<I', header, 16)[0]
    checksum = header[20:24]

    if payload_len > 4_000_000:  # sanity limit
        raise ValueError(f"Payload too large: {payload_len}")

    payload = recv_exact(sock, payload_len) if payload_len > 0 else b''

    # Verify checksum
    expected = double_sha256(payload)[:4]
    if checksum != expected:
        raise ValueError("Checksum mismatch")

    return command, payload


def crawl_node(ip: str, port: int = MAINNET_PORT, connect_timeout: float = 5.0) -> List[Tuple[str, int]]:
    """
    Connect to a Zcash node, perform handshake, and request peers.
    Returns list of discovered (ip, port) tuples.
    """
    peers = []
    family = socket.AF_INET6 if ':' in ip else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(connect_timeout)

    try:
        sock.connect((ip, port))
        # Switch to longer timeout for message exchange
        sock.settimeout(10.0)

        # Send version
        version_payload = build_version_payload(ip, port)
        sock.sendall(build_message('version', version_payload))

        # Read messages until we complete handshake and get addr
        got_version = False
        got_verack = False
        sent_getaddr = False
        addr_deadline = None

        for _ in range(50):  # max messages to process
            try:
                command, payload = recv_message(sock)
            except (socket.timeout, ConnectionError, ValueError):
                break

            if command == 'version':
                got_version = True
                sock.sendall(build_message('verack'))

            elif command == 'verack':
                got_verack = True

            elif command == 'ping':
                # Respond with pong (echo the nonce) to keep connection alive
                sock.sendall(build_message('pong', payload))

            elif command == 'addr':
                new_peers = parse_addr_payload(payload)
                peers.extend(new_peers)
                # Reset deadline — more addr messages may follow
                if addr_deadline:
                    addr_deadline = time.time() + 5

            elif command == 'reject':
                break

            # Once handshake is complete, send getaddr
            if got_version and got_verack and not sent_getaddr:
                sock.sendall(build_message('getaddr'))
                sent_getaddr = True
                addr_deadline = time.time() + 15  # wait up to 15s for addr

            # Check deadline
            if addr_deadline and time.time() > addr_deadline:
                break

    except (socket.timeout, ConnectionError, OSError):
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass

    return peers


# ==================== GEOLOCATION ====================

def geolocate_batch(ips: List[str]) -> Dict[str, dict]:
    """
    Geolocate a list of IPs using ip-api.com batch endpoint.
    Returns dict mapping IP -> {lat, lng, city, country}.
    """
    results = {}

    # Process in chunks of 100
    for i in range(0, len(ips), 100):
        chunk = ips[i:i + 100]

        try:
            data = json.dumps(chunk).encode('utf-8')
            req = urllib.request.Request(
                'http://ip-api.com/batch?fields=status,query,lat,lon,city,country',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                geo_results = json.loads(response.read().decode())

            for geo in geo_results:
                if geo.get('status') == 'success' and geo.get('lat') and geo.get('lon'):
                    results[geo['query']] = {
                        'lat': geo['lat'],
                        'lng': geo['lon'],
                        'city': geo.get('city', ''),
                        'country': geo.get('country', '')
                    }
        except Exception:
            pass

        # Rate limit: 1.5s between batch requests
        if i + 100 < len(ips):
            time.sleep(1.5)

    return results


# ==================== CRAWLER ====================

class ZcashCrawler:
    """Discovers Zcash nodes by crawling the P2P network."""

    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.path.join(os.path.expanduser('~'), '.zecnode')
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_file = os.path.join(cache_dir, 'crawled_nodes.json')

        self.nodes: Dict[str, dict] = {}  # ip -> node data
        self.lock = threading.Lock()
        self.is_crawling = False
        self.last_crawl_time = None
        self._running = True

        # Load existing cache
        self._load_cache()

    def _load_cache(self):
        """Load cached nodes from disk."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                for node in data.get('nodes', []):
                    self.nodes[node['ip']] = node
                self.last_crawl_time = data.get('last_crawl')
        except Exception:
            pass

    def _save_cache(self):
        """Save nodes to disk atomically."""
        try:
            data = {
                'last_crawl': self.last_crawl_time,
                'node_count': len(self.nodes),
                'nodes': list(self.nodes.values())
            }
            tmp = self.cache_file + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(data, f)
            os.replace(tmp, self.cache_file)
        except Exception:
            pass

    def resolve_seeds(self) -> List[str]:
        """Resolve DNS seeds to get initial peer IPs (IPv4 and IPv6)."""
        ips = []
        for seed in DNS_SEEDS:
            # IPv4
            try:
                results = socket.getaddrinfo(seed, MAINNET_PORT, socket.AF_INET)
                for result in results:
                    ip = result[4][0]
                    if is_public_ip(ip):
                        ips.append(ip)
            except Exception:
                pass
            # IPv6
            try:
                results = socket.getaddrinfo(seed, MAINNET_PORT, socket.AF_INET6)
                for result in results:
                    ip = result[4][0]
                    if is_public_ipv6(ip):
                        ips.append(ip)
            except Exception:
                pass
        return list(set(ips))

    def run_crawl(self):
        """Execute one full crawl cycle."""
        if self.is_crawling:
            return
        self.is_crawling = True

        try:
            # Resolve DNS seeds
            seed_ips = self.resolve_seeds()
            if not seed_ips:
                return

            queue = deque(seed_ips)
            visited = set()
            discovered = {}  # ip -> port
            max_nodes = 2000

            # Crawl nodes using thread pool
            with ThreadPoolExecutor(max_workers=10) as executor:
                while queue and len(visited) < max_nodes:
                    # Submit batch of work
                    batch = []
                    while queue and len(batch) < 10:
                        ip = queue.popleft()
                        if ip not in visited:
                            visited.add(ip)
                            batch.append(ip)

                    if not batch:
                        break

                    futures = {
                        executor.submit(crawl_node, ip): ip
                        for ip in batch
                    }

                    for future in as_completed(futures, timeout=30):
                        ip = futures[future]
                        try:
                            peers = future.result()
                            # Mark this IP as a live node
                            discovered[ip] = MAINNET_PORT

                            # Add new peers to queue
                            for peer_ip, peer_port in peers:
                                if peer_ip not in visited and len(visited) + len(queue) < max_nodes:
                                    queue.append(peer_ip)
                        except Exception:
                            pass

            if not discovered:
                return

            # Geolocate new IPs (skip ones we already have)
            with self.lock:
                existing_ips = set(self.nodes.keys())

            new_ips = [ip for ip in discovered if ip not in existing_ips]
            all_ips = list(discovered.keys())

            # Geolocate new IPs
            geo_data = {}
            if new_ips:
                geo_data = geolocate_batch(new_ips)

            # Update nodes
            now = datetime.now(timezone.utc).isoformat()
            with self.lock:
                # Update last_seen for all discovered nodes
                for ip in all_ips:
                    if ip in self.nodes:
                        self.nodes[ip]['last_seen'] = now
                    elif ip in geo_data:
                        self.nodes[ip] = {
                            'ip': ip,
                            'port': MAINNET_PORT,
                            'lat': geo_data[ip]['lat'],
                            'lng': geo_data[ip]['lng'],
                            'city': geo_data[ip]['city'],
                            'country': geo_data[ip]['country'],
                            'last_seen': now
                        }

                # Expire nodes not seen in 7 days
                cutoff = time.time() - 604800
                expired = []
                for ip, node in self.nodes.items():
                    try:
                        seen = datetime.fromisoformat(node['last_seen']).timestamp()
                        if seen < cutoff:
                            expired.append(ip)
                    except Exception:
                        expired.append(ip)
                for ip in expired:
                    del self.nodes[ip]

                self.last_crawl_time = now

            self._save_cache()

        except Exception:
            pass
        finally:
            self.is_crawling = False

    def get_nodes(self) -> List[dict]:
        """Get current list of geolocated nodes (thread-safe)."""
        with self.lock:
            return list(self.nodes.values())

    def start_periodic(self, interval: int = 1800):
        """Run crawl cycles periodically. Call this from a daemon thread."""
        while self._running:
            try:
                self.run_crawl()
            except Exception:
                pass
            # Sleep in small increments so we can stop quickly
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

    def stop(self):
        """Signal the crawler to stop."""
        self._running = False


# ==================== STANDALONE TEST ====================

if __name__ == '__main__':
    print("ZecNode Network Crawler — standalone test")
    print("=" * 50)

    crawler = ZcashCrawler()

    print("\nResolving DNS seeds...")
    seeds = crawler.resolve_seeds()
    print(f"  Found {len(seeds)} seed IPs: {seeds[:5]}...")

    print("\nStarting crawl (this may take a few minutes)...")
    start = time.time()
    crawler.run_crawl()
    elapsed = time.time() - start

    nodes = crawler.get_nodes()
    print(f"\nCrawl complete in {elapsed:.1f}s")
    print(f"  Discovered {len(nodes)} geolocated nodes")

    if nodes:
        print("\n  Sample nodes:")
        for node in nodes[:10]:
            print(f"    {node['ip']:>15}  {node['city']}, {node['country']}  ({node['lat']}, {node['lng']})")

    print(f"\n  Cache saved to: {crawler.cache_file}")

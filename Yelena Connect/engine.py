"""
engine.py - Backend for Yelena Connect
Handles: ADB connection, scrcpy, resource monitoring, notifications, media control, phone calls
"""

import subprocess
import threading
import time
import os
import re
import json
from pathlib import Path

import socket
import asyncio

# WebSocket server — requiere: pip install websockets --break-system-packages
try:
    import websockets
    import websockets.server
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    print("[ws] 'websockets' no instalado. Corre: pip install websockets --break-system-packages")

# UDP broadcast discovery — sin dependencias extra

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SCRCPY_DIR = BASE_DIR / "scrcpy"
SCRCPY_BIN = SCRCPY_DIR / "scrcpy"
ADB_BIN = SCRCPY_DIR / "adb"


def get_adb():
    """Return adb path: bundled first, then system."""
    if ADB_BIN.exists():
        return str(ADB_BIN)
    return "adb"


def get_scrcpy():
    """Return scrcpy path: bundled first, then system."""
    if SCRCPY_BIN.exists():
        return str(SCRCPY_BIN)
    return "scrcpy"


# ─── ADB Helpers ──────────────────────────────────────────────────────────────

def adb(args: list, device_serial: str = None, timeout: int = 5) -> str:
    """Run an adb command and return stdout. Returns '' on error."""
    cmd = [get_adb()]
    if device_serial:
        cmd += ["-s", device_serial]
    cmd += args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except Exception:
        return ""


def adb_shell(cmd_str: str, device_serial: str = None, timeout: int = 5) -> str:
    return adb(["shell", cmd_str], device_serial=device_serial, timeout=timeout)


# ─── Device Discovery ─────────────────────────────────────────────────────────

def list_devices() -> list[dict]:
    """
    Returns a list of connected ADB devices.
    Each entry: {"serial": str, "state": str, "name": str, "type": "usb"|"wifi"}
    """
    output = adb(["devices", "-l"], timeout=8)
    devices = []
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line or "offline" in line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        if state != "device":
            continue

        # Try to get a friendly name
        model = adb(["-s", serial, "shell", "getprop", "ro.product.model"], timeout=3).strip()
        name = model if model else serial

        # Determine type by serial format (IP:PORT = wifi)
        conn_type = "wifi" if re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", serial) else "usb"

        devices.append({
            "serial": serial,
            "state": state,
            "name": name,
            "type": conn_type,
        })
    return devices


def connect_wifi(ip: str, port: int = 5555) -> tuple[bool, str]:
    """Connect to a device over WiFi. Returns (success, message)."""
    output = adb(["connect", f"{ip}:{port}"], timeout=10)
    if "connected" in output.lower():
        return True, output
    return False, output


def disconnect_wifi(serial: str) -> bool:
    output = adb(["disconnect", serial], timeout=5)
    return "disconnected" in output.lower()


# ─── scrcpy ───────────────────────────────────────────────────────────────────

class ScrcpySession:
    """Lanza scrcpy como proceso independiente."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def start(self, serial: str) -> bool:
        self.stop()
        if SCRCPY_BIN.exists():
            SCRCPY_BIN.chmod(0o755)
        cmd = [get_scrcpy(), "-s", serial]
        try:
            env = os.environ.copy()
            with self._lock:
                self._proc = subprocess.Popen(
                    cmd, env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            print(f"[scrcpy] Lanzado PID={self._proc.pid}")
            return True
        except Exception as e:
            print(f"[scrcpy] Error: {e}")
            return False

    def stop(self):
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None


# ─── Resource Monitor ─────────────────────────────────────────────────────────




class ResourceMonitor:
    def __init__(self):
        self._serial: str | None = None
        self._data: dict = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list = []
        self._interval = 2.0  # seconds

    def set_serial(self, serial: str):
        self._serial = serial

    def add_callback(self, cb):
        self._callbacks.append(cb)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            if self._serial:
                data = self._fetch()
                self._data = data
                for cb in self._callbacks:
                    try:
                        cb(data)
                    except Exception:
                        pass
            time.sleep(self._interval)

    def _fetch(self) -> dict:
        s = self._serial
        result = {}

        # CPU
        try:
            cpu_raw = adb_shell("dumpsys cpuinfo | grep TOTAL", s, timeout=4)
            match = re.search(r"([\d.]+)%\s+TOTAL", cpu_raw)
            if match:
                result["cpu"] = float(match.group(1))
            else:
                # Fallback: /proc/stat
                stat1 = adb_shell("cat /proc/stat | head -1", s, timeout=3)
                time.sleep(0.5)
                stat2 = adb_shell("cat /proc/stat | head -1", s, timeout=3)
                result["cpu"] = self._parse_cpu_stat(stat1, stat2)
        except Exception:
            result["cpu"] = 0.0

        # RAM
        try:
            mem_raw = adb_shell("cat /proc/meminfo", s, timeout=4)
            total = self._parse_meminfo(mem_raw, "MemTotal")
            available = self._parse_meminfo(mem_raw, "MemAvailable")
            if total and available:
                used = total - available
                result["ram_used_mb"] = round(used / 1024)
                result["ram_total_mb"] = round(total / 1024)
                result["ram_pct"] = round(used / total * 100, 1)
        except Exception:
            result["ram_used_mb"] = 0
            result["ram_total_mb"] = 0
            result["ram_pct"] = 0.0

        # Battery
        try:
            bat_raw = adb_shell("dumpsys battery", s, timeout=4)
            level_m = re.search(r"level:\s*(\d+)", bat_raw)
            temp_m = re.search(r"temperature:\s*(\d+)", bat_raw)
            charging_m = re.search(r"status:\s*(\d+)", bat_raw)
            result["battery_pct"] = int(level_m.group(1)) if level_m else 0
            result["battery_temp"] = round(int(temp_m.group(1)) / 10, 1) if temp_m else 0.0
            # status 2 = charging
            result["battery_charging"] = (int(charging_m.group(1)) == 2) if charging_m else False
        except Exception:
            result["battery_pct"] = 0
            result["battery_temp"] = 0.0
            result["battery_charging"] = False

        # Storage
        try:
            df_raw = adb_shell("df /data 2>/dev/null | tail -1", s, timeout=4)
            parts = df_raw.split()
            if len(parts) >= 4:
                total_k = int(re.sub(r"[^\d]", "", parts[1]))
                used_k = int(re.sub(r"[^\d]", "", parts[2]))
                result["storage_used_gb"] = round(used_k / 1024 / 1024, 1)
                result["storage_total_gb"] = round(total_k / 1024 / 1024, 1)
                result["storage_pct"] = round(used_k / total_k * 100, 1) if total_k else 0
        except Exception:
            result["storage_used_gb"] = 0.0
            result["storage_total_gb"] = 0.0
            result["storage_pct"] = 0.0

        return result

    def _parse_cpu_stat(self, stat1: str, stat2: str) -> float:
        try:
            v1 = list(map(int, stat1.split()[1:]))
            v2 = list(map(int, stat2.split()[1:]))
            idle1, idle2 = v1[3], v2[3]
            total1, total2 = sum(v1), sum(v2)
            diff_total = total2 - total1
            diff_idle = idle2 - idle1
            if diff_total == 0:
                return 0.0
            return round((1 - diff_idle / diff_total) * 100, 1)
        except Exception:
            return 0.0

    def _parse_meminfo(self, raw: str, key: str) -> int | None:
        match = re.search(rf"{key}:\s+(\d+)\s+kB", raw)
        return int(match.group(1)) if match else None

    def get_data(self) -> dict:
        return self._data.copy()


# ─── Notification Monitor ─────────────────────────────────────────────────────

class NotificationMonitor:
    def __init__(self):
        self._serial: str | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list = []
        self._seen_ids: set = set()
        self._interval = 3.0

    def set_serial(self, serial: str):
        self._serial = serial
        self._seen_ids.clear()

    def add_callback(self, cb):
        self._callbacks.append(cb)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            if self._serial:
                notifs = self._fetch()
                for cb in self._callbacks:
                    try:
                        cb(notifs)
                    except Exception:
                        pass
            time.sleep(self._interval)

    def _fetch(self) -> list[dict]:
        raw = adb_shell("dumpsys notification --noredact 2>/dev/null", self._serial, timeout=8)
        return self._parse_notifications(raw)

    def _parse_notifications(self, raw: str) -> list[dict]:
        notifications = []
        # Match notification blocks
        blocks = re.split(r"NotificationRecord\(", raw)
        for block in blocks[1:]:
            try:
                pkg_m = re.search(r"pkg=(\S+)", block)
                title_m = re.search(r"android\.title[^=]*=\s*([^\n]+)", block)
                text_m = re.search(r"android\.text[^=]*=\s*([^\n]+)", block)
                id_m = re.search(r"id=(\d+)", block)

                pkg = pkg_m.group(1) if pkg_m else "unknown"
                title = title_m.group(1).strip() if title_m else ""
                text = text_m.group(1).strip() if text_m else ""
                notif_id = id_m.group(1) if id_m else ""

                if not title and not text:
                    continue

                # Clean up values
                title = re.sub(r"\s+", " ", title)[:80]
                text = re.sub(r"\s+", " ", text)[:120]

                notifications.append({
                    "id": f"{pkg}_{notif_id}",
                    "package": pkg,
                    "app": self._pkg_to_name(pkg),
                    "title": title,
                    "text": text,
                })
            except Exception:
                continue

        # Deduplicate by id
        seen = set()
        unique = []
        for n in notifications:
            if n["id"] not in seen:
                seen.add(n["id"])
                unique.append(n)

        return unique[:30]  # Max 30 notifications

    def _pkg_to_name(self, pkg: str) -> str:
        mapping = {
            "com.whatsapp": "WhatsApp",
            "com.telegram.messenger": "Telegram",
            "org.telegram.messenger": "Telegram",
            "com.google.android.gm": "Gmail",
            "com.instagram.android": "Instagram",
            "com.twitter.android": "Twitter/X",
            "com.spotify.music": "Spotify",
            "com.google.android.youtube": "YouTube",
            "com.android.phone": "Phone",
            "com.google.android.apps.messaging": "Messages",
            "com.facebook.katana": "Facebook",
            "com.discord": "Discord",
        }
        return mapping.get(pkg, pkg.split(".")[-1].capitalize())


# ─── Media Controller ─────────────────────────────────────────────────────────

class MediaController:
    def __init__(self):
        self._serial: str | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list = []
        self._interval = 2.0
        self._current: dict = {}

    def set_serial(self, serial: str):
        self._serial = serial

    def add_callback(self, cb):
        self._callbacks.append(cb)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            if self._serial:
                data = self._fetch_media_info()
                self._current = data
                for cb in self._callbacks:
                    try:
                        cb(data)
                    except Exception:
                        pass
            time.sleep(self._interval)

    def _fetch_media_info(self) -> dict:
        result = {"title": "", "artist": "", "album": "", "playing": False, "package": ""}

        # ── Estrategia 1: media_controller (más confiable en Samsung/Android 10+)
        # Formato típico:
        #   PlaybackState {state=3, ...}
        #   description=Major Tom (Völlig losgelöst) - Single Version
        #   metadata: size=5
        #     android.media.metadata.TITLE=Major Tom ...
        #     android.media.metadata.ARTIST=Peter Schilling
        raw = adb_shell("dumpsys media_session 2>/dev/null", self._serial, timeout=7)

        if raw:
            # Estado de reproducción
            sm = re.search(r"state=(\d+)", raw)
            if sm:
                result["playing"] = int(sm.group(1)) == 3

            # Package de la sesión activa
            pm = re.search(r"package=(\S+)", raw)
            if pm:
                result["package"] = pm.group(1)

            # Metadatos — buscar DENTRO del bloque "metadata:" ignorando "null, size=0"
            # Samsung escribe líneas como:
            #   android.media.metadata.TITLE (TEXT) : Major Tom...
            # o sin espacios:
            #   android.media.metadata.TITLE=Major Tom...
            for meta_key, field in [
                ("TITLE",  "title"),
                ("ARTIST", "artist"),
                ("ALBUM",  "album"),
            ]:
                # Formato con " : " o "=" después del key
                m = re.search(
                    rf"android\.media\.metadata\.{meta_key}\s*(?:\([^)]+\))?\s*[=:]\s*(.+)",
                    raw, re.IGNORECASE
                )
                if m:
                    val = m.group(1).strip().strip(",").strip()
                    # Ignorar valores basura
                    if val and val.lower() not in ("null", "none", "") \
                            and not val.startswith("size="):
                        result[field] = val[:80]

        # ── Estrategia 2: si title sigue vacío, leer notificación MediaStyle
        if not result["title"]:
            notif = adb_shell(
                "dumpsys notification --noredact 2>/dev/null", self._serial, timeout=6
            )
            if notif:
                blocks = re.split(r"NotificationRecord\(", notif)
                for block in blocks[1:]:
                    if "MediaStyle" not in block and "mediaSession" not in block:
                        continue
                    tm = re.search(r"android\.title\b[^=\n]*=\s*([^\n]+)", block)
                    am = re.search(r"android\.text\b[^=\n]*=\s*([^\n]+)",  block)
                    if tm:
                        val = tm.group(1).strip()
                        if val and "null" not in val.lower():
                            result["title"] = val[:80]
                            result["playing"] = True
                    if am:
                        val = am.group(1).strip()
                        if val and "null" not in val.lower():
                            result["artist"] = val[:60]
                    if result["title"]:
                        break

        # ── Estrategia 3: description= como último recurso
        if not result["title"] and raw:
            dm = re.search(r"\bdescription\s*=\s*([^\n,]+)", raw, re.IGNORECASE)
            if dm:
                val = dm.group(1).strip()
                if val and "null" not in val.lower() and not val.startswith("size="):
                    result["title"] = val[:80]

        return result

    def play_pause(self):
        self._keyevent(85)  # KEYCODE_MEDIA_PLAY_PAUSE

    def next_track(self):
        self._keyevent(87)  # KEYCODE_MEDIA_NEXT

    def prev_track(self):
        self._keyevent(88)  # KEYCODE_MEDIA_PREVIOUS

    def volume_up(self):
        self._keyevent(24)  # KEYCODE_VOLUME_UP

    def volume_down(self):
        self._keyevent(25)  # KEYCODE_VOLUME_DOWN

    def _keyevent(self, code: int):
        if self._serial:
            adb_shell(f"input keyevent {code}", self._serial)

    def get_current(self) -> dict:
        return self._current.copy()


# ─── Phone / Keypad ───────────────────────────────────────────────────────────

class PhoneController:
    def __init__(self):
        self._serial: str | None = None

    def set_serial(self, serial: str):
        self._serial = serial

    def dial(self, number: str) -> bool:
        """Open the dialer with a number."""
        if not self._serial:
            return False
        clean = re.sub(r"[^\d+*#]", "", number)
        if not clean:
            return False
        out = adb_shell(
            f"am start -a android.intent.action.CALL -d tel:{clean}",
            self._serial
        )
        return "Error" not in out

    def open_dialer(self, number: str = "") -> bool:
        """Open the dialer view (without calling)."""
        if not self._serial:
            return False
        clean = re.sub(r"[^\d+*#]", "", number)
        uri = f"tel:{clean}" if clean else "tel:"
        out = adb_shell(
            f"am start -a android.intent.action.DIAL -d {uri}",
            self._serial
        )
        return "Error" not in out

    def end_call(self) -> bool:
        if not self._serial:
            return False
        adb_shell("input keyevent 6", self._serial)  # KEYCODE_ENDCALL
        return True

    def send_dtmf(self, digit: str):
        """Send a DTMF tone (for keypad during call)."""
        dtmf_map = {
            "0": 7, "1": 8, "2": 9, "3": 10, "4": 11,
            "5": 12, "6": 13, "7": 14, "8": 15, "9": 16,
            "*": 17, "#": 18,
        }
        code = dtmf_map.get(digit)
        if code and self._serial:
            adb_shell(f"input keyevent {code}", self._serial)


# ─── Connection Manager (top-level facade) ────────────────────────────────────

class ConnectionManager:
    """
    Central manager. gtk.py only talks to this.
    """
    def __init__(self):
        self.serial: str | None = None
        self.device_name: str = "No device"
        self.device_type: str = "none"

        self.scrcpy = ScrcpySession()
        self.resources = ResourceMonitor()
        self.notifications = NotificationMonitor()
        self.media = MediaController()
        self.phone = PhoneController()

        self._on_connect_cbs: list = []
        self._on_disconnect_cbs: list = []

    # ── Callbacks ──────────────────────────────────────────────────────────

    def on_connect(self, cb):
        self._on_connect_cbs.append(cb)

    def on_disconnect(self, cb):
        self._on_disconnect_cbs.append(cb)

    # ── Device handling ────────────────────────────────────────────────────

    def connect_device(self, device: dict) -> bool:
        self.disconnect()
        self.serial = device["serial"]
        self.device_name = device["name"]
        self.device_type = device["type"]

        self.resources.set_serial(self.serial)
        self.notifications.set_serial(self.serial)
        self.media.set_serial(self.serial)
        self.phone.set_serial(self.serial)

        self.resources.start()
        self.notifications.start()
        self.media.start()

        for cb in self._on_connect_cbs:
            try:
                cb(device)
            except Exception:
                pass
        return True

    def disconnect(self):
        self.resources.stop()
        self.notifications.stop()
        self.media.stop()
        self.scrcpy.stop()
        self.serial = None
        self.device_name = "No device"
        for cb in self._on_disconnect_cbs:
            try:
                cb()
            except Exception:
                pass

    def start_screen_mirror(self) -> bool:
        if not self.serial:
            return False
        return self.scrcpy.start(self.serial)

    def stop_screen_mirror(self):
        self.scrcpy.stop()

    def get_devices(self) -> list[dict]:
        return list_devices()

    def connect_wifi_device(self, ip: str, port: int = 5555):
        return connect_wifi(ip, port)

    def is_connected(self) -> bool:
        return self.serial is not None


# Singleton
manager = ConnectionManager()


# ─── WebSocket Server ─────────────────────────────────────────────────────────

def _get_local_ip() -> str:
    """Obtiene la IP local de la máquina en la red."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class YelenaDiscovery:
    """
    Descubrimiento via UDP broadcast — igual que KDE Connect.

    Usa DOS sockets separados:
      - _send_sock: socket efímero para enviar broadcasts (puerto aleatorio)
      - _recv_sock: socket fijo en UDP_PORT para recibir broadcasts

    Esto evita el conflicto donde un solo socket no puede
    enviar Y recibir al mismo tiempo de forma fiable.
    """

    UDP_PORT  = 1716
    BROADCAST = "255.255.255.255"
    INTERVAL  = 3.0

    def __init__(self, ws_port: int = 8765):
        self._ws_port      = ws_port
        self._running      = False
        self._send_sock    = None   # solo envía, puerto efímero
        self._recv_sock    = None   # solo recibe, puerto 1716
        self._thread_send  = None
        self._thread_recv  = None
        self._devices      = {}
        self._on_found_cbs = []
        self._on_lost_cbs  = []

    def on_device_found(self, cb):
        self._on_found_cbs.append(cb)

    def on_device_lost(self, cb):
        self._on_lost_cbs.append(cb)

    @property
    def discovered_devices(self) -> list:
        return list(self._devices.values())

    def start(self):
        if self._running:
            return
        self._running = True
        try:
            # Socket de ENVÍO — puerto aleatorio, solo broadcast
            self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Socket de RECEPCIÓN — escucha en puerto fijo
            self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._recv_sock.bind(("", self.UDP_PORT))
            self._recv_sock.settimeout(2.0)

            self._thread_send = threading.Thread(target=self._send_loop, daemon=True)
            self._thread_recv = threading.Thread(target=self._recv_loop, daemon=True)
            self._thread_send.start()
            self._thread_recv.start()
            print(f"[udp] Descubrimiento iniciado — escuchando en :{self.UDP_PORT}")
        except Exception as e:
            print(f"[udp] Error: {e}")
            self._running = False

    def stop(self):
        self._running = False
        for s in [self._send_sock, self._recv_sock]:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        self._send_sock = None
        self._recv_sock = None

    def _get_broadcast_addr(self) -> str:
        """Calcula la dirección de broadcast de la subred local."""
        try:
            ip = _get_local_ip()
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.255"
        except Exception:
            pass
        return "255.255.255.255"

    def _make_packet(self) -> bytes:
        import platform
        return json.dumps({
            "type":    "yelena",
            "name":    socket.gethostname(),
            "ip":      _get_local_ip(),
            "port":    self._ws_port,
            "os":      f"{platform.system()} {platform.release()}",
            "version": "1",
        }).encode("utf-8")

    def _send_loop(self):
        while self._running:
            try:
                if self._send_sock:
                    pkt  = self._make_packet()
                    bcast = self._get_broadcast_addr()
                    # Enviar a ambos: broadcast de subred Y 255.255.255.255
                    self._send_sock.sendto(pkt, (bcast, self.UDP_PORT))
                    self._send_sock.sendto(pkt, ("255.255.255.255", self.UDP_PORT))
            except Exception as e:
                print(f"[udp] send error: {e}")
            time.sleep(self.INTERVAL)

    def _recv_loop(self):
        my_ip = _get_local_ip()
        print(f"[udp] Escuchando broadcasts en :{self.UDP_PORT} (mi IP: {my_ip})")
        while self._running:
            try:
                if not self._recv_sock:
                    break
                data, addr = self._recv_sock.recvfrom(4096)
                src_ip = addr[0]
                if src_ip == my_ip:
                    continue
                print(f"[udp] Paquete de {src_ip}: {data[:80]}")
                try:
                    payload = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
                if payload.get("type") != "yelena":
                    continue
                device = {
                    "name": payload.get("name", src_ip),
                    "ip":   src_ip,
                    "port": payload.get("port", 8766),
                    "os":   payload.get("os", "Android"),
                    "type": "wifi",
                }
                is_new = src_ip not in self._devices
                self._devices[src_ip] = device
                if is_new:
                    print(f"[udp] Dispositivo encontrado: {device['name']} @ {src_ip}")
                    for cb in self._on_found_cbs:
                        try:
                            cb(device)
                        except Exception:
                            pass

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[udp] Error recibiendo: {e}")
                break


class YelenaWebSocketServer:
    """
    Servidor WebSocket — datos del PC → app Android.

    Monitores nativos del PC (independientes de ADB):
      - Recursos: psutil (CPU, RAM, disco, uptime)
      - Media:    via ADB si hay dispositivo conectado
      - Notifs:   via ADB si hay dispositivo conectado
      - Portapapeles: xclip/xsel bidireccional

    Mensajes enviados al cliente:
      pc_info, resources, media, notifications, clipboard, pong

    Mensajes recibidos:
      ping, media_command, terminal, clipboard_set
    """

    WS_PORT = 8765

    def __init__(self, conn_manager):
        self._mgr                  = conn_manager
        self._clients              : set = set()
        self._loop                 : asyncio.AbstractEventLoop | None = None
        self._thread               : threading.Thread | None = None
        self._running              = False
        self._start_time           = time.time()
        self._last_clipboard       = ""
        self._on_ws_connect_cbs    : list = []
        self._on_ws_disconnect_cbs : list = []
        self._connected_clients    : dict = {}
        self._bash = self._PersistentBash()  # bash persistente para terminal

        # Verificar psutil
        try:
            import psutil
            self._has_psutil = True
        except ImportError:
            self._has_psutil = False
            print("[ws] 'psutil' no instalado. Corre: pip install psutil --break-system-packages")

    def on_client_connected(self, cb):
        """cb(device_info) cuando un cliente Android se conecta por WiFi."""
        self._on_ws_connect_cbs.append(cb)

    def on_client_disconnected(self, cb):
        """cb(ip) cuando un cliente Android se desconecta."""
        self._on_ws_disconnect_cbs.append(cb)

    def has_wifi_clients(self) -> bool:
        return len(self._clients) > 0

    def get_wifi_clients(self) -> list:
        return list(self._connected_clients.values())

    # ── Control ───────────────────────────────────────────────────────────────

    def start(self):
        if self._running or not HAS_WEBSOCKETS:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print(f"[ws] Servidor iniciado en ws://{_get_local_ip()}:{self.WS_PORT}")

    def stop(self):
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ── Loop asyncio ──────────────────────────────────────────────────────────

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            print(f"[ws] Error en loop: {e}")

    async def _serve(self):
        async with websockets.server.serve(
            self._handle_client, "0.0.0.0", self.WS_PORT,
            ping_interval=None,  # sin ping del servidor — Android reconnecta solo
            close_timeout=5,
        ):
            print(f"[ws] Escuchando en ws://0.0.0.0:{self.WS_PORT} (cualquier path)")
            loop = asyncio.get_event_loop()
            loop.create_task(self._resource_loop())
            loop.create_task(self._clipboard_loop())
            while self._running:
                await asyncio.sleep(1)

    # ── Loops de broadcast ────────────────────────────────────────────────────

    async def _resource_loop(self):
        """Envía recursos del PC cada 2 segundos sin bloquear el event loop."""
        loop = asyncio.get_event_loop()
        while self._running:
            if self._clients:
                # run_in_executor evita que psutil.cpu_percent(interval=0.1)
                # bloquee el event loop y corrompa la conexión WebSocket
                data = await loop.run_in_executor(None, self._get_pc_resources)
                await self._broadcast_async("resources", data)
            await asyncio.sleep(2)

    async def _clipboard_loop(self):
        """Monitorea el portapapeles del PC y notifica cambios."""
        while self._running:
            if self._clients:
                current = self._get_clipboard()
                if current and current != self._last_clipboard:
                    self._last_clipboard = current
                    # Guardar en historial (máx 20 entradas)
                    hist = self._clipboard_history
                    if current not in hist:
                        hist.insert(0, current)
                        if len(hist) > 20:
                            hist.pop()
                    await self._broadcast_async("clipboard", {"text": current})
            await asyncio.sleep(1)

    # ── Handler por cliente ───────────────────────────────────────────────────

    async def _handle_client(self, websocket, path=None):
        self._clients.add(websocket)
        ip = websocket.remote_address[0] if websocket.remote_address else "?"
        print(f"[ws] Cliente conectado: {ip}  path={path}  (total: {len(self._clients)})")

        # Guardar info del cliente
        device_info = {"name": ip, "ip": ip, "port": 0, "type": "wifi"}
        self._connected_clients[ip] = device_info

        # Disparar callbacks de conexión WiFi
        for cb in self._on_ws_connect_cbs:
            try:
                cb(device_info)
            except Exception:
                pass

        try:
            # Enviar estado inicial completo
            await self._send(websocket, "pc_info", self._pc_info())
            loop = asyncio.get_event_loop()
            res  = await loop.run_in_executor(None, self._get_pc_resources)
            await self._send(websocket, "resources", res)
            # Mandar portapapeles actual al nuevo cliente
            current_clip = self._get_clipboard()
            if current_clip:
                await self._send(websocket, "clipboard", {"text": current_clip})
            # Resetear _last_clipboard para que el eco no bloquee mensajes del móvil
            self._last_clipboard = ""
            async for raw in websocket:
                await self._handle_message(websocket, raw)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[ws] Error con cliente {ip}: {e}")
        finally:
            self._clients.discard(websocket)
            self._connected_clients.pop(ip, None)
            print(f"[ws] Cliente desconectado: {ip}  (total: {len(self._clients)})")
            for cb in self._on_ws_disconnect_cbs:
                try:
                    cb(ip)
                except Exception:
                    pass

    async def _handle_message(self, ws, raw: str):
        try:
            msg   = json.loads(raw)
            mtype = msg.get("type", "")
            payload = msg.get("payload", "")
            if isinstance(payload, str) and payload:
                try:
                    payload = json.loads(payload)
                except Exception:
                    pass

            if mtype == "ping":
                await self._send(ws, "pong", "")

            elif mtype == "media_command":
                action = payload.get("action", "") if isinstance(payload, dict) else ""
                if self._mgr.is_connected():
                    # Controlar media del teléfono via ADB
                    {"play_pause": self._mgr.media.play_pause,
                     "next":       self._mgr.media.next_track,
                     "prev":       self._mgr.media.prev_track,
                     "vol_up":     self._mgr.media.volume_up,
                     "vol_down":   self._mgr.media.volume_down,
                    }.get(action, lambda: None)()
                else:
                    # Sin ADB — controlar media del PC con playerctl
                    cmd_map = {
                        "play_pause": ["playerctl", "play-pause"],
                        "next":       ["playerctl", "next"],
                        "prev":       ["playerctl", "previous"],
                        "vol_up":     ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
                        "vol_down":   ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"],
                    }
                    cmd = cmd_map.get(action)
                    if cmd:
                        try:
                            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                        except Exception as e:
                            print(f"[ws] media cmd error: {e}")

            elif mtype == "terminal":
                cmd = payload.get("command", "") if isinstance(payload, dict) else str(payload)
                if cmd:
                    out, code = self._run_terminal(cmd)
                    await self._send(ws, "terminal_output",
                                     {"output": out, "exitCode": code})

            elif mtype == "clipboard_set":
                text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
                if text and text != self._last_clipboard:
                    self._last_clipboard = text   # evitar eco — actualizar ANTES de set
                    self._set_clipboard(text)
                    print(f"[clipboard] PC←Android: {text[:40]}")

            elif mtype == "file_send":
                # Móvil → PC: guardar archivo
                import base64
                name = payload.get("name", "archivo") if isinstance(payload, dict) else "archivo"
                data = payload.get("data", "")         if isinstance(payload, dict) else ""
                if data:
                    try:
                        dest    = os.path.join(os.path.expanduser("~"), "Downloads", name)
                        decoded = base64.b64decode(data)
                        with open(dest, "wb") as f:
                            f.write(decoded)
                        print(f"[ws] Archivo recibido: {dest}")
                        await self._send(ws, "file_received", {"name": name, "path": dest})
                    except Exception as e:
                        print(f"[ws] Error guardando archivo: {e}")

            # ── Procesos ──────────────────────────────────────────────────────
            elif mtype == "get_processes":
                await self._send(ws, "processes", self._get_processes())

            elif mtype == "kill_process":
                pid = payload.get("pid") if isinstance(payload, dict) else None
                if pid:
                    result = self._kill_process(int(pid))
                    await self._send(ws, "process_killed", {"pid": pid, "ok": result})

            # ── Apps instaladas ───────────────────────────────────────────────
            elif mtype == "get_apps":
                await self._send(ws, "apps", self._get_apps())

            elif mtype == "launch_app":
                app = payload.get("exec", "") if isinstance(payload, dict) else ""
                if app:
                    self._launch_app(app)

            # ── Ratón / teclado ───────────────────────────────────────────────
            elif mtype == "mouse_move":
                dx = payload.get("dx", 0) if isinstance(payload, dict) else 0
                dy = payload.get("dy", 0) if isinstance(payload, dict) else 0
                self._mouse_move(int(dx), int(dy))

            elif mtype == "mouse_click":
                btn = payload.get("button", "left") if isinstance(payload, dict) else "left"
                self._mouse_click(btn)

            elif mtype == "mouse_scroll":
                direction = payload.get("direction", "down") if isinstance(payload, dict) else "down"
                self._mouse_scroll(direction)

            elif mtype == "key_press":
                key = payload.get("key", "") if isinstance(payload, dict) else ""
                if key:
                    self._key_press(key)

            elif mtype == "type_text":
                text = payload.get("text", "") if isinstance(payload, dict) else ""
                if text:
                    self._type_text(text)

            # ── Brillo ────────────────────────────────────────────────────────
            elif mtype == "set_brightness":
                val = payload.get("value", 50) if isinstance(payload, dict) else 50
                self._set_brightness(int(val))

            elif mtype == "get_brightness":
                val = self._get_brightness()
                await self._send(ws, "brightness", {"value": val})

            # ── Notificación del teléfono al PC ───────────────────────────────
            elif mtype == "send_notification":
                title = payload.get("title", "") if isinstance(payload, dict) else ""
                body  = payload.get("body",  "") if isinstance(payload, dict) else ""
                self._desktop_notify(title, body)

            # ── Presentación ──────────────────────────────────────────────────
            elif mtype == "presentation":
                action = payload.get("action", "") if isinstance(payload, dict) else ""
                self._presentation_control(action)

            # ── Portapapeles historial ─────────────────────────────────────────
            elif mtype == "get_clipboard_history":
                await self._send(ws, "clipboard_history",
                                 {"items": self._clipboard_history})

        except Exception as e:
            print(f"[ws] Error procesando mensaje: {e}")

    # ── Broadcast ─────────────────────────────────────────────────────────────

    def broadcast_media(self, data: dict):
        """Llamado por ADB MediaController cuando cambia la canción."""
        self._broadcast("media", {
            "title":   data.get("title",  ""),
            "artist":  data.get("artist", ""),
            "album":   data.get("album",  ""),
            "playing": data.get("playing", False),
        })

    def broadcast_notifications(self, notifs: list):
        """Llamado por ADB NotificationMonitor — notificaciones DEL TELÉFONO → PC."""
        # Estas son notificaciones del teléfono, no del PC.
        # Las enviamos como "phone_notifications" para distinguirlas.
        self._broadcast("phone_notifications", [
            {"id": n.get("id",""), "app": n.get("app",""),
             "title": n.get("title",""), "body": n.get("text",""),
             "time": int(time.time() * 1000)}
            for n in notifs
        ])

    def broadcast_resources(self, data: dict):
        """Ignorado — los recursos del PC los obtiene _resource_loop directamente."""
        pass

    def _broadcast(self, mtype: str, payload):
        if not self._clients or not self._loop:
            return
        asyncio.run_coroutine_threadsafe(
            self._broadcast_async(mtype, payload), self._loop
        )

    async def _broadcast_async(self, mtype: str, payload):
        if not self._clients:
            return
        msg  = json.dumps({"type": mtype, "payload": json.dumps(payload)})
        dead = set()
        for ws in self._clients.copy():
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    @staticmethod
    async def _send(ws, mtype: str, payload):
        msg = json.dumps({"type": mtype, "payload": json.dumps(payload)})
        await ws.send(msg)

    # ── Recursos del PC via psutil ────────────────────────────────────────────

    def _get_pc_resources(self) -> dict:
        if not self._has_psutil:
            return {
                "cpuPercent": 0, "ramUsedGb": 0, "ramTotalGb": 0,
                "ramPercent": 0, "diskUsedGb": 0, "diskTotalGb": 0,
                "diskPercent": 0, "uptimeSeconds": int(time.time() - self._start_time),
            }
        try:
            import psutil
            cpu   = psutil.cpu_percent(interval=0.1)
            ram   = psutil.virtual_memory()
            disk  = psutil.disk_usage("/")
            boot  = psutil.boot_time()
            return {
                "cpuPercent":    round(cpu, 1),
                "ramUsedGb":     round(ram.used  / 1024**3, 2),
                "ramTotalGb":    round(ram.total / 1024**3, 2),
                "ramPercent":    round(ram.percent, 1),
                "diskUsedGb":    round(disk.used  / 1024**3, 1),
                "diskTotalGb":   round(disk.total / 1024**3, 1),
                "diskPercent":   round(disk.percent, 1),
                "uptimeSeconds": int(time.time() - boot),
            }
        except Exception as e:
            print(f"[ws] psutil error: {e}")
            return {"cpuPercent": 0, "ramUsedGb": 0, "ramTotalGb": 0,
                    "ramPercent": 0, "diskUsedGb": 0, "diskTotalGb": 0,
                    "diskPercent": 0, "uptimeSeconds": 0}

    # ── Portapapeles ──────────────────────────────────────────────────────────

    def _make_clipboard_env(self) -> dict:
        """Construye entorno con DISPLAY y XAUTHORITY correctos para xclip."""
        env = os.environ.copy()

        # Asegurar DISPLAY
        if not env.get("DISPLAY"):
            env["DISPLAY"] = ":0"

        # Siempre buscar XAUTHORITY — no asumir que el env ya lo tiene correcto
        import glob
        uid = os.getuid()
        xauth_candidates = [
            os.path.expanduser("~/.Xauthority"),
            f"/run/user/{uid}/gdm/Xauthority",
            f"/run/user/{uid}/.Xauthority",
            f"/tmp/.xauth-{uid}",
        ]
        xauth_candidates += glob.glob("/tmp/.xauth*") + glob.glob("/tmp/.Xauth*")
        for path in xauth_candidates:
            if os.path.exists(path):
                env["XAUTHORITY"] = path
                break

        return env

    def _get_clipboard(self) -> str:
        """Lee portapapeles del PC."""
        env = self._make_clipboard_env()
        try:
            r = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True, timeout=2, env=env
            )
            if r.returncode == 0:
                text = r.stdout.decode("utf-8", errors="replace").strip()
                return text  # puede ser vacío — el loop lo ignora
            # rc=1 + "target STRING not available" = portapapeles vacío, ignorar
            stderr = r.stderr.decode(errors="replace")
            if "target STRING not available" in stderr or "not available" in stderr:
                return ""  # normal, no imprimir nada
            print(f"[clipboard] xclip error (rc={r.returncode}): {stderr[:80]}")
        except FileNotFoundError:
            print("[clipboard] xclip no encontrado: sudo apt install xclip")
        except Exception as e:
            print(f"[clipboard] get error: {e}")
        return ""

    def _set_clipboard(self, text: str):
        """Escribe en el portapapeles del PC."""
        env = self._make_clipboard_env()
        try:
            r = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode("utf-8"),
                capture_output=True, timeout=2, env=env
            )
            if r.returncode == 0:
                self._last_clipboard = text
                print(f"[clipboard] PC←Android: {text[:40]}")
                return
            else:
                print(f"[clipboard] xclip -i error (rc={r.returncode}): {r.stderr.decode()[:60]}")
        except FileNotFoundError:
            print("[clipboard] xclip no encontrado: sudo apt install xclip")
        except Exception as e:
            print(f"[clipboard] set error: {e}")

    # ── Terminal ──────────────────────────────────────────────────────────────

    def _run_terminal(self, cmd: str) -> tuple[str, int]:
        """
        Ejecuta comandos en un bash persistente.
        El mismo proceso bash se reutiliza entre comandos,
        así cd y variables de entorno persisten entre llamadas.
        """
        return self._bash.run(cmd)

    class _PersistentBash:
        """Proceso bash único que mantiene estado (cwd, variables) entre comandos."""
        SENTINEL = "__YELENA_CMD_DONE__"

        def __init__(self):
            import subprocess, os
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["HOME"] = os.path.expanduser("~")
            self._proc = subprocess.Popen(
                ["/bin/bash", "--norc", "--noprofile"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                bufsize=1,
            )

        def run(self, cmd: str, timeout: float = 15.0) -> tuple:
            import select, time
            if self._proc.poll() is not None:
                self.__init__()  # reiniciar si murió
            try:
                # Escribir comando + sentinel para saber cuándo terminó
                sentinel_cmd = f'{cmd}\necho "{self.SENTINEL}:$?"\n'
                self._proc.stdin.write(sentinel_cmd)
                self._proc.stdin.flush()
            except Exception as e:
                return str(e), 1

            lines = []
            exit_code = 0
            deadline = time.time() + timeout
            try:
                while time.time() < deadline:
                    ready = select.select([self._proc.stdout], [], [], 0.1)[0]
                    if not ready:
                        continue
                    line = self._proc.stdout.readline()
                    if not line:
                        break
                    if line.startswith(self.SENTINEL + ":"):
                        exit_code = int(line.split(":")[1].strip() or "0")
                        break
                    lines.append(line.rstrip())
            except Exception as e:
                return str(e), 1

            out = "\n".join(lines).strip()
            return out or "(sin salida)", exit_code

    # ── Info del PC ───────────────────────────────────────────────────────────

    def _pc_info(self) -> dict:
        import platform
        return {
            "hostname": socket.gethostname(),
            "os":       f"{platform.system()} {platform.release()}",
            "version":  "Yelena Connect v0.2",
        }

    # ── Procesos ──────────────────────────────────────────────────────────────

    def _get_processes(self) -> list:
        """
        cpu_percent() siempre da 0 en la primera llamada por proceso.
        Solución: guardar los mismos objetos Process entre las dos pasadas.
        """
        try:
            import psutil, time
            # Primera pasada — inicializar contadores en los mismos objetos
            procs_map = {}
            for p in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    p.cpu_percent()          # inicializar — devuelve 0, ignorar
                    procs_map[p.pid] = p
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            time.sleep(0.5)
            # Segunda pasada — llamar cpu_percent() en los MISMOS objetos
            result = []
            for pid, p in procs_map.items():
                try:
                    cpu = p.cpu_percent()    # ahora sí devuelve valor real
                    mem = p.memory_percent()
                    result.append({
                        "pid":  pid,
                        "name": p.name(),
                        "cpu":  round(cpu, 1),
                        "mem":  round(mem, 1),
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return sorted(result, key=lambda x: (x['cpu'], x['mem']), reverse=True)
        except Exception as e:
            print(f"[ws] get_processes error: {e}")
            return []

    def _kill_process(self, pid: int) -> bool:
        try:
            import psutil
            p = psutil.Process(pid)
            p.terminate()
            return True
        except Exception as e:
            print(f"[ws] kill_process {pid}: {e}")
            return False

    # ── Apps instaladas ───────────────────────────────────────────────────────

    def _get_apps(self) -> list:
        """Lee .desktop files para listar apps instaladas."""
        apps = []
        search_dirs = [
            "/usr/share/applications",
            "/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications"),
        ]
        seen = set()
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if not fname.endswith(".desktop"):
                    continue
                path = os.path.join(d, fname)
                try:
                    name = exec_ = icon = ""
                    nodisplay = False
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("Name=") and not name:
                                name = line[5:]
                            elif line.startswith("Exec=") and not exec_:
                                exec_ = line[5:].split()[0].replace("%U","").replace("%F","").strip()
                            elif line.startswith("Icon=") and not icon:
                                icon = line[5:]
                            elif line == "NoDisplay=true":
                                nodisplay = True
                    if name and exec_ and not nodisplay and exec_ not in seen:
                        seen.add(exec_)
                        apps.append({"name": name, "exec": exec_, "icon": icon})
                except Exception:
                    pass
        return sorted(apps, key=lambda x: x['name'].lower())[:100]

    def _launch_app(self, exec_path: str):
        try:
            env = os.environ.copy()
            env.setdefault("DISPLAY", ":0")
            subprocess.Popen(
                exec_path, shell=True, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print(f"[ws] App lanzada: {exec_path}")
        except Exception as e:
            print(f"[ws] launch_app error: {e}")

    # ── Teclado y teclas especiales ─────────────────────────────────────────────
    # Detección automática del entorno — funciona en cualquier sistema Linux:
    #   - Wayland puro (GNOME, KDE con Wayland)  → ydotool
    #   - X11 o Xwayland (KDE Plasma, XFCE, etc) → xdotool con DISPLAY correcto

    @staticmethod
    def _detect_display() -> dict:
        """Detecta DISPLAY y XAUTHORITY correctos para xdotool."""
        import glob
        env = os.environ.copy()

        # Si DISPLAY ya está seteado en el entorno, usarlo
        if not env.get("DISPLAY"):
            # Buscar sockets X11 activos
            sockets = sorted(glob.glob("/tmp/.X11-unix/X*"))
            if sockets:
                num = sockets[0].replace("/tmp/.X11-unix/X", "")
                env["DISPLAY"] = f":{num}"
            else:
                env["DISPLAY"] = ":0"

        # Buscar XAUTHORITY si no está
        if not env.get("XAUTHORITY"):
            uid = os.getuid()
            for path in [
                os.path.expanduser("~/.Xauthority"),
                f"/run/user/{uid}/gdm/Xauthority",
                f"/run/user/{uid}/.Xauthority",
            ] + sorted(glob.glob("/tmp/.xauth*")):
                if os.path.exists(path):
                    env["XAUTHORITY"] = path
                    break

        return env

    @staticmethod
    def _detect_ydotool_socket() -> str | None:
        """Encuentra el socket de ydotoold si está corriendo."""
        uid = os.getuid()
        candidates = [
            f"/run/user/{uid}/.ydotool_socket",
            "/tmp/.ydotool_socket",
            f"/run/ydotoold/ydotoold.socket",
        ]
        for s in candidates:
            if os.path.exists(s):
                return s
        return None

    def _xdo(self, *args, timeout: float = 2.0):
        """xdotool — X11 y Xwayland."""
        import shutil
        if not shutil.which("xdotool"):
            print("[input] Instala xdotool: sudo apt install xdotool")
            return
        env = self._detect_display()
        try:
            r = subprocess.run(["xdotool", *args], env=env,
                               capture_output=True, timeout=timeout)
            if r.returncode != 0:
                err = r.stderr.decode(errors="replace").strip()
                if err:
                    print(f"[xdotool] {err[:80]}")
        except Exception as e:
            print(f"[xdotool] {e}")

    def _ydo(self, *args, timeout: float = 2.0):
        """ydotool — Wayland nativo."""
        import shutil
        if not shutil.which("ydotool"):
            print("[input] Instala ydotool: sudo apt install ydotool")
            return
        sock = self._detect_ydotool_socket()
        if not sock:
            print("[input] ydotoold no está corriendo: ydotoold &")
            return
        env = os.environ.copy()
        env["YDOTOOL_SOCKET"] = sock
        try:
            r = subprocess.run(["ydotool", *args], env=env,
                               capture_output=True, timeout=timeout)
            if r.returncode != 0:
                err = r.stderr.decode(errors="replace").strip()
                if err:
                    print(f"[ydotool] {err[:80]}")
        except Exception as e:
            print(f"[ydotool] {e}")

    def _input_cmd(self, xdo_args: list, ydo_args: list):
        """
        Usa xdotool si DISPLAY está disponible (X11 o Xwayland),
        si no usa ydotool (Wayland puro sin Xwayland).
        Esta es exactamente la lógica de KDE Connect.
        """
        env = self._detect_display()
        display = env.get("DISPLAY", "")
        # Verificar que el DISPLAY es válido probando xdpyinfo
        x11_ok = False
        if display:
            try:
                r = subprocess.run(
                    ["xdpyinfo"], env=env,
                    capture_output=True, timeout=1
                )
                x11_ok = r.returncode == 0
            except Exception:
                x11_ok = False

        if x11_ok:
            self._xdo(*xdo_args)
        else:
            self._ydo(*ydo_args)

    def _key_press(self, key: str):
        self._input_cmd(
            xdo_args=["key", key],
            ydo_args=["key", key],
        )

    def _type_text(self, text: str):
        self._input_cmd(
            xdo_args=["type", "--clearmodifiers", "--delay", "20", "--", text],
            ydo_args=["type", "--", text],
        )

    # ── Brillo ────────────────────────────────────────────────────────────────

    def _get_brightness(self) -> int:
        try:
            r = subprocess.run(
                ["brightnessctl", "g"], capture_output=True, text=True, timeout=2
            )
            current = int(r.stdout.strip())
            m = subprocess.run(
                ["brightnessctl", "m"], capture_output=True, text=True, timeout=2
            )
            maximum = int(m.stdout.strip()) or 100
            return round(current / maximum * 100)
        except Exception:
            return -1  # -1 = no disponible

    def _set_brightness(self, percent: int):
        try:
            subprocess.run(
                ["brightnessctl", "s", f"{max(1, min(100, percent))}%"],
                capture_output=True, timeout=2
            )
        except Exception:
            pass

    # ── Notificaciones de escritorio ──────────────────────────────────────────

    def _desktop_notify(self, title: str, body: str):
        try:
            subprocess.Popen(
                ["notify-send", "--app-name=Yelena Connect", title, body],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

    # ── Presentación ──────────────────────────────────────────────────────────

    def _presentation_control(self, action: str):
        """Controla presentaciones con xdotool (LibreOffice Impress, evince, etc.)"""
        key_map = {
            "next":     "Right",
            "prev":     "Left",
            "start":    "F5",
            "end":      "Escape",
            "black":    "b",       # pantalla negra en LibreOffice
            "white":    "w",
        }
        key = key_map.get(action)
        if key:
            self._key_press(key)

    # ── Historial del portapapeles ────────────────────────────────────────────

    @property
    def _clipboard_history(self) -> list:
        if not hasattr(self, '_clip_history'):
            self._clip_history = []
        return self._clip_history

    def get_connection_info(self) -> dict:
        return {"ip": _get_local_ip(), "port": self.WS_PORT, "name": socket.gethostname()}

    def get_qr_text(self) -> str:
        return json.dumps(self.get_connection_info())



# ─── Parche: integrar WS server en ConnectionManager ─────────────────────────
# Guardamos la clase original y la extendemos

_OrigConnectionManager = ConnectionManager

class ConnectionManager(_OrigConnectionManager):
    def __init__(self):
        super().__init__()
        self.ws_server = YelenaWebSocketServer(self)
        self.discovery = YelenaDiscovery(ws_port=YelenaWebSocketServer.WS_PORT)

        self.ws_server.start()
        self.discovery.start()

        # Callbacks ADB → broadcast WebSocket
        self.resources.add_callback(self.ws_server.broadcast_resources)
        self.notifications.add_callback(self.ws_server.broadcast_notifications)
        self.media.add_callback(self.ws_server.broadcast_media)

    def on_android_found(self, cb):
        self.discovery.on_device_found(cb)

    def on_android_lost(self, cb):
        self.discovery.on_device_lost(cb)

    def get_android_devices(self) -> list:
        return self.discovery.discovered_devices

    def on_wifi_connected(self, cb):
        """Callback cuando app Android se conecta por WebSocket WiFi."""
        self.ws_server.on_client_connected(cb)

    def on_wifi_disconnected(self, cb):
        """Callback cuando app Android se desconecta."""
        self.ws_server.on_client_disconnected(cb)

    def is_wifi_connected(self) -> bool:
        return self.ws_server.has_wifi_clients()

    def disconnect(self):
        super().disconnect()

# Singleton
manager = ConnectionManager()

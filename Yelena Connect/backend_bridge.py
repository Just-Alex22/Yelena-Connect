import asyncio, json, sys, os, time, logging, signal, hashlib
import threading, subprocess, tempfile, zipfile, io, base64
from pathlib import Path
from collections import OrderedDict, deque
from datetime import datetime
from typing import Optional, Dict, List
import websockets
from engine import manager
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QTimer
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("yconnect-bridge")
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR  = Path.home() / ".config" / "y-connect"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DEVICE_DB   = CONFIG_DIR / "devices.json"
PREFS_FILE  = CONFIG_DIR / "prefs.json"
TRANSFER_DIR = CONFIG_DIR / "transfers"
TRANSFER_DIR.mkdir(exist_ok=True)
BRIDGE_PORT = 8767  
_flutter_process: Optional[subprocess.Popen] = None
_qapp: Optional[QApplication] = None
_tray: Optional[QSystemTrayIcon] = None
def _net_quality(rssi):
    if rssi >= -55: return "excellent"
    if rssi >= -65: return "good"
    if rssi >= -75: return "fair"
    return "poor"
def _signal_icon_name(connected, rssi):
    if not connected or rssi == -1:
        return "stat0"
    elif rssi >= -60:
        return "stat4"
    elif rssi >= -70:
        return "stat3"
    elif rssi >= -80:
        return "stat2"
    else:
        return "stat1"
def _ws_send(mtype, payload):
    if hasattr(manager, "ws_server") and manager.ws_server:
        manager.ws_server.broadcast(mtype, payload)
class DeviceMemory:
    def __init__(self):
        self._db: Dict[str, dict] = {}
        self._load()
    def _load(self):
        try:
            if DEVICE_DB.exists():
                self._db = json.loads(DEVICE_DB.read_text())
                log.info("Device memory: %d devices", len(self._db))
        except Exception as e:
            log.warning("device mem: %s", e); self._db = {}
    def _save(self):
        try: DEVICE_DB.write_text(json.dumps(self._db, indent=2, ensure_ascii=False))
        except Exception as e: log.warning("save: %s", e)
    def _fp(self, d):
        return hashlib.sha256(f"{d.get('name','')}|{d.get('mac','')}|{d.get('model','')}".encode()).hexdigest()[:16]
    def remember(self, d):
        fp = self._fp(d)
        e = self._db.setdefault(fp, {"name":d.get("name",""),"mac":d.get("mac",""),
            "model":d.get("model",""),"ip":d.get("ip",""),"trusted":False,
            "first_seen":time.time(),"last_seen":time.time(),"connect_count":0})
        e["name"]=d.get("name",e["name"]); e["ip"]=d.get("ip",e["ip"])
        e["last_seen"]=time.time(); e["connect_count"]+=1; self._save(); return fp
    def lookup(self, d): return self._db.get(self._fp(d))
    def is_trusted(self, d):
        e = self.lookup(d); return e.get("trusted", False) if e else False
    def set_trusted(self, d, t=True):
        fp = self._fp(d)
        if fp in self._db: self._db[fp]["trusted"] = t; self._save()
    def last_seen_str(self, d):
        e = self.lookup(d)
        if not e or not e.get("last_seen"): return ""
        return datetime.fromtimestamp(e["last_seen"]).strftime("%Y-%m-%d %H:%M")
    @property
    def all_devices(self): return dict(self._db)
class Preferences:
    DEFAULTS = {"auto_reconnect":True,"clipboard_auto":False,"battery_alert_threshold":15}
    def __init__(self): self._data=dict(self.DEFAULTS); self._load()
    def _load(self):
        try:
            if PREFS_FILE.exists(): self._data.update(json.loads(PREFS_FILE.read_text()))
        except: pass
    def _save(self):
        try: PREFS_FILE.write_text(json.dumps(self._data, indent=2))
        except: pass
    def get(self, k, d=None): return self._data.get(k, d if d is not None else self.DEFAULTS.get(k))
    def set(self, k, v): self._data[k]=v; self._save()
class NetworkMonitor:
    def __init__(self): self._history=[]; self._quality="unknown"
    def update_rssi(self, rssi):
        self._history.append(rssi)
        if len(self._history)>10: self._history.pop(0)
        self._quality = _net_quality(sum(self._history)/len(self._history))
        bridge.send({"t":"net","d":self._quality})
    @property
    def quality(self): return self._quality
    def should_compress(self): return self._quality in ("fair","poor")
    def chunk_size(self):
        return {"excellent":512*1024,"good":256*1024,"fair":128*1024,"poor":64*1024,"unknown":256*1024}.get(self._quality,256*1024)
class SmartReconnector:
    def __init__(self):
        self._attempt=0; self._active=False; self._timer=None; self._device=None
    @property
    def active(self): return self._active
    def start(self, device=None):
        if self._active: return
        self._active=True; self._attempt=0; self._device=device; self._schedule()
    def stop(self): self._active=False; self._timer=None; self._attempt=0
    def _schedule(self):
        if not self._active: return
        self._attempt += 1
        delay = min(1.5*(2**(self._attempt-1)), 60.0)
        import random; delay = max(0.5, delay + delay*0.3*(random.random()*2-1))
        bridge.send({"t":"reconn","d":{"s":"trying","a":self._attempt}})
        self._timer = asyncio.get_event_loop().call_later(delay, self._try)
    def _try(self):
        if not self._active: return
        if manager.is_connected() or manager.is_wifi_connected():
            bridge.send({"t":"reconn","d":{"s":"ok","a":self._attempt}}); self.stop(); return
        try:
            if hasattr(manager,"discovery") and manager.discovery: getattr(manager.discovery,"scan_once",lambda:None)()
        except: pass
        self._schedule()
class ContextEngine:
    def __init__(self, dm): self._dm=dm; self._recent_files=[]; self._media_playing=False; self._phone_battery=None
    def record_file_sent(self, p): self._recent_files.insert(0,p); self._recent_files=self._recent_files[:20]
    def set_media_state(self, p): self._media_playing=p
    def set_phone_battery(self, p): self._phone_battery=p
class NotificationAI:
    def __init__(self): self._seen=OrderedDict()
    def process(self, notifs):
        now=time.time()
        for k in [k for k,t in self._seen.items() if now-t>30]: del self._seen[k]
        out=[]
        for n in notifs:
            h=hashlib.md5(f"{n.get('app','')}|{n.get('title','')}|{n.get('body','')}".encode()).hexdigest()
            if h not in self._seen: self._seen[h]=now; out.append(n)
        return out
class ClipboardSync:
    def __init__(self): self._last_sent=""; self._last_recv=""
    def send_clipboard(self, text=None):
        if text and text != self._last_sent:
            self._last_sent = text; _ws_send("clipboard", {"text": text})
    def receive_clipboard(self, text):
        if text != self._last_recv and text != self._last_sent:
            self._last_recv = text
            bridge.send({"t":"clip","d":text})
class TransferManager:
    MAX_SIZE = 100*1024*1024
    MAX_LOG = 50
    def __init__(self, nm): self._nm=nm; self._active={}; self._log=[]
    def send_file(self, path, compress=None):
        try:
            fsize = os.path.getsize(path)
            if fsize > self.MAX_SIZE:
                bridge.send({"t":"xfer","d":{"file":Path(path).name,"progress":0,"done":True,"error":"Too large"}})
                return
            fname     = Path(path).name
            ext       = Path(path).suffix.lstrip(".").upper() or "FILE"
            tid       = hashlib.md5(f"{path}{time.time()}".encode()).hexdigest()[:8]
            if compress is None: compress = fsize > 256*1024 and self._nm.should_compress()
            with open(path,"rb") as f: raw = f.read()
            if compress:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf: zf.writestr(fname, raw)
                raw = buf.getvalue(); fname += ".zip"
            b64   = base64.b64encode(raw).decode()
            cs    = 65536
            total = max(1, (len(b64) + cs - 1) // cs)
            _ws_send("file_offer", {
                "transfer_id":  tid,
                "name":         Path(path).name,
                "size":         fsize,
                "ext":          ext,
                "total_chunks": total,
                "compressed":   compress,
            })
            self._active[tid] = {"b64": b64, "fname": fname, "orig_name": Path(path).name,
                                 "total": total, "compress": compress, "cs": cs}
            bridge.send({"t":"xfer","d":{"id":tid,"file":Path(path).name,"progress":0,"done":False,"waiting":True}})
        except Exception as e:
            log.error("Transfer error: %s", e)
            bridge.send({"t":"xfer","d":{"file":Path(path).name,"done":True,"error":str(e)}})
    def on_file_accepted(self, tid):
        entry = self._active.get(tid)
        if not entry:
            return
        b64   = entry["b64"]; cs = entry["cs"]; total = entry["total"]
        fname = entry["fname"]; orig = entry["orig_name"]; comp = entry["compress"]
        try:
            for i in range(total):
                s = i * cs; e = min(s + cs, len(b64))
                _ws_send("file_chunk", {
                    "transfer_id": tid, "name": fname, "chunk_index": i,
                    "total_chunks": total, "data": b64[s:e],
                    "is_last": i == total - 1, "compressed": comp, "original_name": orig,
                })
                bridge.send({"t":"xfer","d":{"id":tid,"progress":(i+1)/total,"file":orig,"done":False,"waiting":False}})
                time.sleep(0.005)
            bridge.send({"t":"xfer","d":{"id":tid,"progress":1,"file":orig,"done":True}})
        except Exception as e:
            log.error("Transfer send error: %s", e)
            bridge.send({"t":"xfer","d":{"file":orig,"done":True,"error":str(e)}})
        finally:
            self._active.pop(tid, None)
    def on_file_rejected(self, tid):
        entry = self._active.pop(tid, None)
        fname = entry["orig_name"] if entry else "?"
        bridge.send({"t":"xfer","d":{"id":tid,"file":fname,"done":True,"error":"Rejected by device"}})
class Bridge:
    def __init__(self):
        self.clients: set = set()
        self.queue: deque = deque()
        self.connected = False
        self.rssi = -1
        self.current_device = None
    def send(self, msg):
        self.queue.append(json.dumps(msg))
    async def _broadcast_loop(self):
        while True:
            while self.queue:
                msg = self.queue.popleft()
                dead = set()
                for ws in self.clients:
                    try: await ws.send(msg)
                    except: dead.add(ws)
                self.clients -= dead
            await asyncio.sleep(0.016)
    async def _handler(self, websocket):
        self.clients.add(websocket)
        try:
            await websocket.send(json.dumps({"t":"bridge_ready"}))
            info = manager.ws_server.get_connection_info()
            await websocket.send(json.dumps({"t":"qr_info","d":{"ip":info["ip"],"port":info["port"]}}))
            devs = []
            for fp, d in device_mem.all_devices.items():
                devs.append({"name":d.get("name","?"),"trusted":d.get("trusted",False),
                             "last_seen":d.get("last_seen",0)})
            await websocket.send(json.dumps({"t":"known_devices","d":devs}))
            if self.connected and self.current_device:
                await websocket.send(json.dumps({"t":"conn","d":self.current_device}))
            try:
                qr = manager.ws_server.get_qr_text()
                if qr:
                    await websocket.send(json.dumps({"t":"qr_text","d":qr}))
            except Exception as e:
                log.warning("QR text fetch failed: %s", e)
        except Exception as e:
            log.warning("Initial send failed: %s", e)
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                    await self._handle_command(data, websocket)
                except Exception as e:
                    log.error("Command error: %s", e)
        finally:
            self.clients.discard(websocket)
    async def _handle_command(self, data, ws):
        t = data.get("t", "")
        d = data.get("d", {})
        if t == "cmd":
            action = data.get("a", "")
            if action == "play_pause":
                _ws_send("phone_media_command", {"action":"play_pause"})
            elif action == "next":
                _ws_send("phone_media_command", {"action":"next"})
            elif action == "prev":
                _ws_send("phone_media_command", {"action":"prev"})
            elif action == "vol_up":
                _ws_send("phone_media_command", {"action":"vol_up"})
            elif action == "vol_down":
                _ws_send("phone_media_command", {"action":"vol_down"})
            elif action == "mute":
                _ws_send("phone_media_command", {"action":"vol_mute"})
        elif t == "send_clip":
            clipboard_sync.send_clipboard()
        elif t == "send_text":
            text = data.get("d", "")
            if text:
                _ws_send("clipboard", {"text": text})
        elif t == "send_file":
            path = data.get("d", "")
            compress = data.get("compress", True)
            if path and os.path.isfile(path):
                context.record_file_sent(path)
                threading.Thread(target=transfer_mgr.send_file,
                                 args=(path,), kwargs={"compress": compress}, daemon=True).start()
        elif t == "pair":
            ip = data.get("ip", "")
            trust = data.get("trust", False)
            if trust: manager.accept_pair(ip, trust=True)
            else: manager.accept_pair(ip, trust=False)
        elif t == "pair_reject":
            manager.reject_pair(data.get("ip", ""))
        elif t == "qr_text":
            try:
                await ws.send(json.dumps({"t":"qr_text","d":manager.ws_server.get_qr_text()}))
            except: pass
    async def run(self):
        log.info("Bridge listening on ws://127.0.0.1:%d", BRIDGE_PORT)
        async with websockets.serve(self._handler, "127.0.0.1", BRIDGE_PORT):
            await self._broadcast_loop()
bridge = Bridge()
prefs = Preferences()
device_mem = DeviceMemory()
net_monitor = NetworkMonitor()
reconnector = SmartReconnector()
notif_ai = NotificationAI()
transfer_mgr = TransferManager(net_monitor)
clipboard_sync = ClipboardSync()
context = ContextEngine(device_mem)
def _on_wifi_conn(device):
    bridge.connected = True; bridge.rssi = -1; bridge.current_device = device
    device_mem.remember(device)
    bridge.send({"t":"conn","d":device})
    if reconnector.active:
        reconnector.stop()
        bridge.send({"t":"reconn","d":{"s":"ok","a":0}})
    _update_tray()
def _on_wifi_disc(ip):
    if not manager.is_connected() and not manager.is_wifi_connected():
        bridge.connected = False; bridge.rssi = -1; bridge.current_device = None
        bridge.send({"t":"disc","d":ip})
        if prefs.get("auto_reconnect", True) and not reconnector.active:
            reconnector.start()
        _update_tray()
def _on_found(device):
    name = device.get("name","Android"); ip = device.get("ip","?")
    log.info("Found: %s @ %s", name, ip)
    entry = device_mem.lookup(device)
    if entry:
        bridge.send({"t":"toast","d":{"title":"Y-Connect","body":f"{name} is nearby"}})
        devs = []
        for fp, d in device_mem.all_devices.items():
            devs.append({"name":d.get("name","?"),"trusted":d.get("trusted",False),
                         "last_seen":d.get("last_seen",0)})
        bridge.send({"t":"known_devices","d":devs})
def _on_pair(ip, device_name):
    bridge.send({"t":"pair_request","d":{"ip":ip,"name":device_name}})
def _on_battery(ip, pct, charging):
    bridge.send({"t":"bat","d":{"pct":pct,"ch":charging}})
    context.set_phone_battery(pct)
def _on_rssi(rssi):
    if rssi != bridge.rssi:
        bridge.rssi = rssi
        net_monitor.update_rssi(rssi)
        bridge.send({"t":"rssi","d":rssi})
    _update_tray()
def _on_resources(d):
    bridge.send({"t":"res","d":d})
def _on_media(d):
    bridge.send({"t":"phone_media","d":d})
    context.set_media_state(d.get("playing", False))
def _on_accent_color(hex_color):
    bridge.send({"t":"accent_color","d":{"hex":hex_color}})
def _on_phone_notifs(notifs):
    bridge.send({"t":"notifs","d":notifs})
def _on_file_accept(tid):
    threading.Thread(target=transfer_mgr.on_file_accepted, args=(tid,), daemon=True).start()
def _on_file_reject(tid):
    transfer_mgr.on_file_rejected(tid)
def _on_volume(lvl):
    bridge.send({"t":"vol","d":lvl})
def _tray_icon_for_state():
    name = _signal_icon_name(bridge.connected, bridge.rssi)
    svg = SCRIPT_DIR / "assets" / f"{name}.svg"
    if svg.exists():
        return QIcon(str(svg))
    logo = SCRIPT_DIR / "assets" / "logo.svg"
    if logo.exists():
        return QIcon(str(logo))
    return QIcon.fromTheme("network-wireless")
def _tray_title_text():
    if bridge.connected:
        dname = bridge.current_device.get("name", "Android") if bridge.current_device else "Android"
        return f"Y-Connect  —  {dname} ({net_monitor.quality})"
    return "Y-Connect  —  Disconnected"
def _update_tray():
    if _tray is None:
        return
    _tray.setIcon(_tray_icon_for_state())
    _tray.setToolTip(_tray_title_text())
def _poll_signal():
    rssi = bridge.rssi
    srv = getattr(manager, 'ws_server', None)
    if srv:
        engine_rssi = getattr(srv, '_last_wifi_rssi', None)
        if engine_rssi is not None and engine_rssi != bridge.rssi:
            rssi = engine_rssi
            bridge.rssi = rssi
            net_monitor.update_rssi(rssi)
            bridge.send({"t":"rssi","d":rssi})
    if bridge.connected and rssi == -1:
        if not manager.is_wifi_connected():
            bridge.connected = False
            bridge.current_device = None
            bridge.send({"t":"disc","d":""})
    _update_tray()
def _launch_flutter():
    global _flutter_process
    if _flutter_process and _flutter_process.poll() is None:
        log.info("Flutter already running (pid %d)", _flutter_process.pid)
        return
    release_bin = SCRIPT_DIR / "build" / "linux" / "x64" / "release" / "bundle" / "yconnect"
    debug_bin = SCRIPT_DIR / "build" / "linux" / "x64" / "debug" / "bundle" / "yconnect"
    binary = None
    if release_bin.exists():
        binary = release_bin
    elif debug_bin.exists():
        binary = debug_bin
    if binary and binary.exists():
        log.info("Launching Flutter: %s", binary)
        _flutter_process = subprocess.Popen(
            [str(binary)],
            cwd=str(SCRIPT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        log.info("No Flutter build found, launching via 'flutter run'...")
        _flutter_process = subprocess.Popen(
            ["flutter", "run", "-d", "linux"],
            cwd=str(SCRIPT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
def _do_quit():
    global _flutter_process
    log.info("Exiting Y-Connect")
    if _flutter_process and _flutter_process.poll() is None:
        _flutter_process.terminate()
        try:
            _flutter_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _flutter_process.kill()
    try: manager.discovery.stop()
    except: pass
    if _tray:
        _tray.setVisible(False)
    if _qapp:
        _qapp.quit()
    os._exit(0)
def _build_tray():
    global _tray
    _tray = QSystemTrayIcon()
    _tray.setIcon(_tray_icon_for_state())
    _tray.setToolTip("Y-Connect")
    _tray.activated.connect(
        lambda r: _launch_flutter() if r == QSystemTrayIcon.Trigger else None
    )
    menu = QMenu()
    a_show = QAction("Show Window", menu)
    a_show.triggered.connect(lambda: _launch_flutter())
    menu.addAction(a_show)
    menu.addSeparator()
    a_pause = QAction("Media  ▸  Play/Pause", menu)
    a_pause.triggered.connect(lambda: _ws_send("phone_media_command", {"action":"play_pause"}))
    menu.addAction(a_pause)
    a_next = QAction("Media  ▸  Next", menu)
    a_next.triggered.connect(lambda: _ws_send("phone_media_command", {"action":"next"}))
    menu.addAction(a_next)
    a_prev = QAction("Media  ▸  Previous", menu)
    a_prev.triggered.connect(lambda: _ws_send("phone_media_command", {"action":"prev"}))
    menu.addAction(a_prev)
    menu.addSeparator()
    a_vup = QAction("Volume  ▸  Up", menu)
    a_vup.triggered.connect(lambda: _ws_send("phone_media_command", {"action":"vol_up"}))
    menu.addAction(a_vup)
    a_vdn = QAction("Volume  ▸  Down", menu)
    a_vdn.triggered.connect(lambda: _ws_send("phone_media_command", {"action":"vol_down"}))
    menu.addAction(a_vdn)
    a_mut = QAction("Volume  ▸  Mute", menu)
    a_mut.triggered.connect(lambda: _ws_send("phone_media_command", {"action":"vol_mute"}))
    menu.addAction(a_mut)
    menu.addSeparator()
    a_quit = QAction("Quit", menu)
    a_quit.triggered.connect(_do_quit)
    menu.addAction(a_quit)
    _tray.setContextMenu(menu)
    _tray.setVisible(True)
    _sig_timer = QTimer()
    _sig_timer.timeout.connect(_poll_signal)
    _sig_timer.start(3000)
def main():
    global _qapp, _flutter_process
    manager.on_wifi_connected(_on_wifi_conn)
    manager.on_wifi_disconnected(_on_wifi_disc)
    manager.on_android_found(_on_found)
    manager.on_pair_request(_on_pair)
    manager.on_battery_update(_on_battery)
    manager.on_rssi_changed(_on_rssi)
    manager.on_resources_changed(_on_resources)
    manager.on_phone_media_changed(_on_media)
    manager.on_accent_color_changed(_on_accent_color)
    manager.on_phone_notifs_changed(_on_phone_notifs)
    manager.on_file_accept_changed(_on_file_accept)
    manager.on_file_reject_changed(_on_file_reject)
    manager.on_phone_volume_changed(_on_volume)
    log.info("Y-Connect bridge v2.0 starting")
    _qapp = QApplication.instance() or QApplication(sys.argv)
    _qapp.setQuitOnLastWindowClosed(False)
    _build_tray()
    _launch_flutter()
    loop = asyncio.new_event_loop()
    def _run_bridge():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bridge.run())
        except Exception as e:
            log.error("Bridge error: %s", e)
    bridge_thread = threading.Thread(target=_run_bridge, daemon=True)
    bridge_thread.start()
    def _shutdown():
        log.info("Shutting down")
        _do_quit()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: _shutdown())
    log.info("Y-Connect tray active")
    sys.exit(_qapp.exec())
if __name__ == "__main__":
    main()
"""
ui.py - Yelena Connect
GTK3 + Adwaita oscuro. Estilo GNOME compacto.
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gio, Gdk, Pango, GdkPixbuf
import cairo

import os
import math
import hashlib
import threading
import collections
import subprocess
from pathlib import Path
from engine import manager

BASE_DIR   = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"

DARK_ACCENTS = [
    "#1a2a3a","#1e2d1e","#2a1a2e","#2a1e1a",
    "#1a2a2a","#2e2a1a","#1e1a2e","#2a2a1a",
    "#1a1e2e","#2e1a1e","#1a2e2a","#2a1a1a",
]

def accent_for(title: str) -> str:
    if not title: return "#1a1a1a"
    return DARK_ACCENTS[int(hashlib.md5(title.encode()).hexdigest(),16) % len(DARK_ACCENTS)]

# ── CSS compacto estilo GNOME ──────────────────────────────────────────────────
CSS = """
.main-bg        { background-color: #242424; }

.app-title      { font-size: 13px; font-weight: 700; color: #eeeeec; }
.device-sub     { font-size: 10px; color: #888a85; }
.device-sub.connected { color: #57e389; }

.media-bar      { background-color: #1e1e1e; padding: 6px 12px; }
.media-title    { font-size: 11px; font-weight: 700; color: #eeeeec; }
.media-artist   { font-size: 10px; color: #888a85; }
.media-btn      { background-color: transparent; border-radius: 6px;
                  color: #eeeeec; min-width: 26px; min-height: 26px; }
.media-btn:hover{ background-color: rgba(255,255,255,0.08); }
.media-btn-play { background-color: rgba(255,255,255,0.12); border-radius: 50%;
                  color: #eeeeec; min-width: 30px; min-height: 30px; }
.media-btn-play:hover { background-color: rgba(255,255,255,0.20); }

.section-title  { font-size: 9px; font-weight: 700; color: #555753; }
.notif-bg       { background-color: #242424; }
.notif-card     { background-color: #2e2e2e; border-radius: 6px;
                  padding: 5px 9px; margin: 1px 6px; }
.notif-card:hover { background-color: #363636; }
.notif-app      { font-size: 9px; font-weight: 700; color: #5294e2; }
.notif-title    { font-size: 10px; font-weight: 600; color: #eeeeec; }
.notif-body     { font-size: 10px; color: #888a85; }

.res-section    { background-color: #2e2e2e; border-radius: 8px;
                  padding: 8px 10px; margin: 4px; }
.res-label      { font-size: 9px; color: #888a85; }
.res-value      { font-size: 9px; font-weight: 700; color: #eeeeec; }

.keypad-section { background-color: #2e2e2e; border-radius: 8px;
                  padding: 8px 10px; margin: 4px; }
.keypad-entry   { font-size: 13px; font-weight: 700; color: #eeeeec;
                  background-color: #1e1e1e; border-radius: 6px; }
.keypad-digit   { background-color: #3d3d3d; border-radius: 6px;
                  font-size: 12px; font-weight: 600; color: #eeeeec;
                  min-width: 36px; min-height: 30px; }
.keypad-digit:hover  { background-color: #484848; }
.keypad-digit:active { background-color: #3584e4; color: #fff; }
.keypad-call  { background-color: #26a269; color: #fff;
                border-radius: 6px; min-height: 30px; }
.keypad-call:hover  { background-color: #2ec27e; }
.keypad-end   { background-color: #c01c28; color: #fff;
                border-radius: 6px; min-height: 30px; }
.keypad-end:hover   { background-color: #e01b24; }
.keypad-del   { background-color: #3d3d3d; color: #f66151;
                border-radius: 6px; min-height: 30px; }
.keypad-del:hover   { background-color: #484848; }

.connect-overlay { background-color: rgba(0,0,0,0.85); }
.connect-card    { background-color: #2e2e2e; border-radius: 12px; padding: 20px; }
.primary-btn   { background-color: #3584e4; color: #fff; border-radius: 6px;
                 font-weight: 700; font-size: 11px; min-height: 30px; }
.primary-btn:hover { background-color: #1c71d8; }
.secondary-btn { background-color: #3d3d3d; color: #eeeeec; border-radius: 6px;
                 font-weight: 600; font-size: 11px; min-height: 30px; }
.secondary-btn:hover { background-color: #484848; }
.device-row-btn  { background-color: #3d3d3d; border-radius: 8px; }
.device-row-btn:hover { background-color: #484848; }
.device-row-name { font-size: 11px; font-weight: 700; color: #eeeeec; }
.device-row-sub  { font-size: 9px; color: #888a85; }

.header-icon-btn { background-color: transparent; border-radius: 6px;
                   color: #eeeeec; min-width: 28px; min-height: 28px; }
.header-icon-btn:hover { background-color: rgba(255,255,255,0.08); }

entry { background-color: #1e1e1e; color: #eeeeec; border-radius: 6px;
        font-size: 11px; }
entry:focus { border-color: #3584e4; }
separator   { background-color: #1a1a1a; min-height: 1px; min-width: 1px; }
scrolledwindow { background-color: transparent; }
viewport       { background-color: transparent; }
"""

def apply_css():
    os.environ.setdefault("GTK_MODULES", "")
    s = Gtk.Settings.get_default()
    s.set_property("gtk-theme-name", "Adwaita")
    s.set_property("gtk-application-prefer-dark-theme", True)
    p = Gtk.CssProvider()
    p.load_from_data(CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

# Inicializar GStreamer

# ── helpers ───────────────────────────────────────────────────────────────────
def lbl(text, css=None, halign=Gtk.Align.START, ellipsize=None):
    w = Gtk.Label(label=text)
    w.set_halign(halign)
    w.set_xalign(0.0 if halign == Gtk.Align.START else 0.5)
    if css:
        for c in css.split(): w.get_style_context().add_class(c)
    if ellipsize: w.set_ellipsize(ellipsize)
    return w

def icon_btn(icon, css="media-btn", tip=None):
    b = Gtk.Button()
    b.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.SMALL_TOOLBAR))
    b.set_relief(Gtk.ReliefStyle.NONE)
    for c in css.split(): b.get_style_context().add_class(c)
    if tip: b.set_tooltip_text(tip)
    return b

def txt_btn(text, css="secondary-btn"):
    b = Gtk.Button(label=text)
    b.set_relief(Gtk.ReliefStyle.NONE)
    for c in css.split(): b.get_style_context().add_class(c)
    return b

def cls(w, *classes):
    for c in classes: w.get_style_context().add_class(c)
    return w


# ── SparkGraph Cairo compacto ─────────────────────────────────────────────────
class SparkGraph(Gtk.DrawingArea):
    COLORS = {
        "cpu":     (0.21, 0.52, 0.89),
        "ram":     (0.15, 0.63, 0.41),
        "bat":     (0.97, 0.80, 0.22),
        "storage": (0.95, 0.47, 0.13),
    }

    def __init__(self, key: str, n: int = 60):
        super().__init__()
        self._data  = collections.deque([0.0]*n, maxlen=n)
        self._color = self.COLORS.get(key, (0.5,0.5,0.5))
        self.set_size_request(-1, 32)
        self.set_hexpand(True)
        self.connect("draw", self._draw)

    def push(self, v: float):
        self._data.append(max(0.0, min(1.0, v)))
        self.queue_draw()

    def _draw(self, widget, cr):
        a = widget.get_allocation()
        w, h = a.width, a.height
        vals = list(self._data)
        n = len(vals)

        # fondo
        cr.set_source_rgb(0.10, 0.10, 0.10)
        cr.rectangle(0,0,w,h); cr.fill()

        if n < 2: return
        step = w/(n-1)
        R,G,B = self._color

        # área
        cr.set_source_rgba(R,G,B,0.10)
        cr.move_to(0,h)
        for i,v in enumerate(vals): cr.line_to(i*step, h-v*(h-4)-2)
        cr.line_to((n-1)*step,h); cr.close_path(); cr.fill()

        # línea
        cr.set_source_rgba(R,G,B,0.80)
        cr.set_line_width(1.4)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(0, h-vals[0]*(h-4)-2)
        for i,v in enumerate(vals[1:],1): cr.line_to(i*step, h-v*(h-4)-2)
        cr.stroke()

        # punto
        cr.set_source_rgba(R,G,B,1.0)
        cr.arc((n-1)*step, h-vals[-1]*(h-4)-2, 2.5, 0, 2*math.pi); cr.fill()


# ── ResourcePanel ─────────────────────────────────────────────────────────────
class ResourcePanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cls(self, "res-section")
        self.pack_start(lbl("Recursos", "section-title"), False, False, 0)
        self._graphs, self._vals = {}, {}
        for key, name in [("cpu","CPU"),("ram","RAM"),("bat","Batería"),("storage","Almac.")]:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            l = lbl(name, "res-label"); l.set_hexpand(True)
            v = lbl("--", "res-value", halign=Gtk.Align.END)
            hdr.pack_start(l,False,False,0); hdr.pack_start(v,False,False,0)
            g = SparkGraph(key)
            row.pack_start(hdr,False,False,0); row.pack_start(g,False,False,0)
            self.pack_start(row, False, False, 0)
            self._graphs[key]=g; self._vals[key]=v

    def update(self, d: dict):
        GLib.idle_add(self._render, d)

    def _render(self, d):
        cpu = d.get("cpu",0)
        self._vals["cpu"].set_text(f"{cpu:.0f}%"); self._graphs["cpu"].push(cpu/100)

        u,t,p = d.get("ram_used_mb",0),d.get("ram_total_mb",1),d.get("ram_pct",0)
        self._vals["ram"].set_text(f"{u}/{t}MB"); self._graphs["ram"].push(p/100)

        bat,tmp,chg = d.get("battery_pct",0),d.get("battery_temp",0),d.get("battery_charging",False)
        self._vals["bat"].set_text(f"{bat}% {tmp}°C"+(" C" if chg else ""))
        self._graphs["bat"].push(bat/100)

        su,st,sp = d.get("storage_used_gb",0),d.get("storage_total_gb",1),d.get("storage_pct",0)
        self._vals["storage"].set_text(f"{su}/{st}GB"); self._graphs["storage"].push(sp/100)


# ── NotificationPanel ─────────────────────────────────────────────────────────
class NotificationPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        cls(self, "notif-bg"); self.set_vexpand(True)

        hdr = Gtk.Box(); hdr.set_border_width(6); hdr.set_margin_start(4)
        self._count = lbl("Notificaciones","section-title")
        hdr.pack_start(self._count,False,False,0)
        self.pack_start(hdr,False,False,0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._list.set_margin_bottom(6)
        scroll.add(self._list)
        self.pack_start(scroll,True,True,0)

        self._empty = lbl("Sin notificaciones","res-label",halign=Gtk.Align.CENTER)
        self._empty.set_margin_top(16)
        self._list.pack_start(self._empty,False,False,0)

    def update(self, notifs: list):
        GLib.idle_add(self._render, notifs)

    def _render(self, notifs):
        for ch in self._list.get_children(): self._list.remove(ch)
        self._count.set_text(f"Notificaciones  ({len(notifs)})" if notifs else "Notificaciones")
        if not notifs:
            self._list.pack_start(self._empty,False,False,0)
        else:
            for n in notifs:
                eb = Gtk.EventBox()
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                cls(card,"notif-card")
                card.pack_start(lbl(n.get("app","App"),"notif-app"),False,False,0)
                if t := n.get("title",""): card.pack_start(lbl(t,"notif-title",ellipsize=Pango.EllipsizeMode.END),False,False,0)
                if x := n.get("text",""):  card.pack_start(lbl(x,"notif-body", ellipsize=Pango.EllipsizeMode.END),False,False,0)
                eb.add(card); self._list.pack_start(eb,False,False,0)
        self._list.show_all()


# ── MediaBar ──────────────────────────────────────────────────────────────────
class MediaBar(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cls(self,"media-bar"); self.set_hexpand(True)
        self._last_title = ""

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        info.set_hexpand(True); info.set_valign(Gtk.Align.CENTER)
        self._title  = lbl("Sin reproducción","media-title", ellipsize=Pango.EllipsizeMode.END)
        self._artist = lbl("","media-artist",                ellipsize=Pango.EllipsizeMode.END)
        info.pack_start(self._title, False,False,0)
        info.pack_start(self._artist,False,False,0)

        ctrls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        ctrls.set_valign(Gtk.Align.CENTER)
        self._vdn  = icon_btn("audio-volume-low-symbolic",    tip="Bajar volumen")
        self._prev = icon_btn("media-skip-backward-symbolic", tip="Anterior")
        self._play = icon_btn("media-playback-start-symbolic","media-btn-play","Reproducir/Pausar")
        self._next = icon_btn("media-skip-forward-symbolic",  tip="Siguiente")
        self._vup  = icon_btn("audio-volume-high-symbolic",   tip="Subir volumen")
        self._vdn.connect ("clicked", lambda _: manager.media.volume_down())
        self._prev.connect("clicked", lambda _: manager.media.prev_track())
        self._play.connect("clicked", lambda _: manager.media.play_pause())
        self._next.connect("clicked", lambda _: manager.media.next_track())
        self._vup.connect ("clicked", lambda _: manager.media.volume_up())
        for b in [self._vdn,self._prev,self._play,self._next,self._vup]:
            ctrls.pack_start(b,False,False,0)

        self.pack_start(info, True, True, 0)
        self.pack_start(ctrls,False,False,0)

    def update(self, data: dict):
        title  = data.get("title")  or "Sin reproducción"
        artist = data.get("artist") or ""
        playing = data.get("playing",False)
        self._title.set_text(title)
        self._artist.set_text(artist)
        icon = "media-playback-pause-symbolic" if playing else "media-playback-start-symbolic"
        self._play.set_image(Gtk.Image.new_from_icon_name(icon,Gtk.IconSize.SMALL_TOOLBAR))
        if title != self._last_title:
            self._last_title = title
            c = accent_for(title)
            rgba = Gdk.RGBA()
            rgba.red   = int(c[1:3],16)/255
            rgba.green = int(c[3:5],16)/255
            rgba.blue  = int(c[5:7],16)/255
            rgba.alpha = 1.0
            self.override_background_color(Gtk.StateFlags.NORMAL, rgba)


# ── KeypadPanel ───────────────────────────────────────────────────────────────
class KeypadPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cls(self,"keypad-section")
        self.pack_start(lbl("Teclado","section-title"),False,False,0)

        self._entry = Gtk.Entry()
        cls(self._entry,"keypad-entry")
        self._entry.set_placeholder_text("Número"); self._entry.set_hexpand(True)
        self.pack_start(self._entry,False,False,0)

        grid = Gtk.Grid()
        grid.set_column_spacing(4); grid.set_row_spacing(4)
        grid.set_column_homogeneous(True); grid.set_hexpand(True)
        for r,keys in enumerate([["1","2","3"],["4","5","6"],["7","8","9"],["*","0","#"]]):
            for c,k in enumerate(keys):
                b = txt_btn(k,"keypad-digit"); b.set_hexpand(True)
                b.connect("clicked",self._digit,k)
                grid.attach(b,c,r,1,1)
        self.pack_start(grid,True,True,0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        call_b = icon_btn("call-start-symbolic","keypad-call","Llamar");  call_b.set_hexpand(True)
        del_b  = icon_btn("edit-clear-symbolic", "keypad-del", "Borrar")
        end_b  = icon_btn("call-stop-symbolic",  "keypad-end", "Colgar"); end_b.set_hexpand(True)
        call_b.connect("clicked",self._call)
        del_b.connect ("clicked",self._delete)
        end_b.connect ("clicked",self._end)
        actions.pack_start(call_b,True, True, 0)
        actions.pack_start(del_b, False,False,0)
        actions.pack_start(end_b, True, True, 0)
        self.pack_start(actions,False,False,0)

    def _digit(self,_,d):
        self._entry.set_text(self._entry.get_text()+d)
        self._entry.set_position(-1); manager.phone.send_dtmf(d)
    def _delete(self,_): self._entry.set_text(self._entry.get_text()[:-1])
    def _call(self,_):
        n=self._entry.get_text().strip()
        if n: manager.phone.dial(n)
    def _end(self,_): manager.phone.end_call()


# ── ConnectPanel ──────────────────────────────────────────────────────────────
class ConnectPanel(Gtk.EventBox):
    def __init__(self, on_selected):
        super().__init__()
        cls(self,"connect-overlay"); self._cb = on_selected

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_halign(Gtk.Align.CENTER); outer.set_valign(Gtk.Align.CENTER)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        cls(card,"connect-card"); card.set_size_request(340,-1)

        card.pack_start(lbl("Conectar dispositivo","media-title",halign=Gtk.Align.CENTER),False,False,0)
        card.pack_start(Gtk.Separator(),False,False,2)

        # ── Dispositivos ADB (USB / WiFi ADB) ────────────────────────────────
        card.pack_start(lbl("USB / ADB","section-title"),False,False,0)
        self._device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.pack_start(self._device_box,False,False,0)

        scan = txt_btn("Buscar dispositivos","secondary-btn")
        scan.connect("clicked",lambda _: self.refresh())
        card.pack_start(scan,False,False,0)
        card.pack_start(Gtk.Separator(),False,False,2)

        # ── Dispositivos Android por WiFi (mDNS) ─────────────────────────────
        wifi_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        wifi_hdr.set_halign(Gtk.Align.CENTER)
        wifi_hdr.pack_start(
            Gtk.Image.new_from_icon_name("network-wireless-symbolic", Gtk.IconSize.SMALL_TOOLBAR),
            False, False, 0)
        wifi_hdr.pack_start(lbl("App Android (WiFi automático)", "section-title"), False, False, 0)
        card.pack_start(wifi_hdr, False, False, 0)

        self._android_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.pack_start(self._android_box, False, False, 0)

        self._android_status = lbl("Buscando en la red...", "device-row-sub", halign=Gtk.Align.CENTER)
        self._android_status.set_opacity(0.5)
        card.pack_start(self._android_status, False, False, 0)

        card.pack_start(Gtk.Separator(),False,False,2)

        # ── WiFi ADB manual ──────────────────────────────────────────────────
        card.pack_start(lbl("WiFi / ADB inalámbrico","res-label",halign=Gtk.Align.CENTER),False,False,0)
        ip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._ip   = Gtk.Entry(); self._ip.set_placeholder_text("192.168.x.x"); self._ip.set_hexpand(True)
        self._port = Gtk.Entry(); self._port.set_placeholder_text("5555"); self._port.set_max_length(5); self._port.set_width_chars(6)
        ip_row.pack_start(self._ip,  True, True, 0)
        ip_row.pack_start(self._port,False,False,0)
        card.pack_start(ip_row,False,False,0)

        wifi = txt_btn("Conectar por WiFi","primary-btn")
        wifi.connect("clicked",self._on_wifi)
        card.pack_start(wifi,False,False,0)

        # ── QR para app Android ──────────────────────────────────────────────
        card.pack_start(Gtk.Separator(),False,False,2)

        qr_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        qr_header.set_halign(Gtk.Align.CENTER)
        qr_icon = Gtk.Image.new_from_icon_name("view-grid-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        qr_icon.set_opacity(0.6)
        qr_header.pack_start(qr_icon, False, False, 0)
        qr_header.pack_start(lbl("App Android (QR manual)", "res-label"), False, False, 0)
        card.pack_start(qr_header, False, False, 0)

        self._qr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._qr_box.set_halign(Gtk.Align.CENTER)
        card.pack_start(self._qr_box, False, False, 0)

        self._qr_info = lbl("", "device-row-sub", halign=Gtk.Align.CENTER)
        self._qr_info.set_selectable(True)
        card.pack_start(self._qr_info, False, False, 0)

        self._status = lbl("","res-label",halign=Gtk.Align.CENTER)
        card.pack_start(self._status,False,False,0)

        outer.pack_start(card,False,False,0)
        self.add(outer)

        # Registrar callbacks mDNS para actualización en vivo
        manager.on_android_found(lambda d: GLib.idle_add(self._on_android_found, d))
        manager.on_android_lost(lambda n: GLib.idle_add(self._on_android_lost, n))

        GLib.idle_add(self.refresh)

    def _on_android_found(self, device: dict):
        """Llamado cuando mDNS detecta una app Android en la red."""
        self._android_status.set_text(f"1 dispositivo encontrado")
        self._add_android_btn(device)
        self._android_box.show_all()
        return False

    def _on_android_lost(self, name: str):
        """Llamado cuando una app Android desaparece de la red."""
        devices = manager.get_android_devices()
        self._refresh_android_list(devices)
        return False

    def _refresh_android_list(self, devices: list):
        for ch in self._android_box.get_children():
            self._android_box.remove(ch)
        if not devices:
            self._android_status.set_text("Buscando en la red...")
        else:
            self._android_status.set_text(f"{len(devices)} dispositivo(s) encontrado(s)")
            for dev in devices:
                self._add_android_btn(dev)
        self._android_box.show_all()

    def _add_android_btn(self, dev: dict):
        btn = Gtk.Button()
        cls(btn,"device-row-btn"); btn.set_relief(Gtk.ReliefStyle.NONE)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_border_width(6)
        row.pack_start(
            Gtk.Image.new_from_icon_name("phone-symbolic", Gtk.IconSize.LARGE_TOOLBAR),
            False, False, 0)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        info.pack_start(lbl(dev["name"],"device-row-name"),False,False,0)
        info.pack_start(lbl(f"WiFi  {dev['ip']}:{dev['port']}","device-row-sub"),False,False,0)
        row.pack_start(info,True,True,0); btn.add(row)
        # Para WiFi directo al teléfono usamos connect_wifi_device
        btn.connect("clicked", lambda _,d=dev: self._connect_android_wifi(d))
        self._android_box.pack_start(btn,False,False,0)

    def _connect_android_wifi(self, dev: dict):
        """Conecta al teléfono por WiFi directo (app Android como servidor)."""
        self._status.set_text(f"Conectando a {dev['name']}...")
        # El teléfono actúa como servidor en este caso
        # Por ahora notificamos al callback principal
        self._cb({"name": dev["name"], "serial": dev["ip"],
                  "type": "wifi", "ip": dev["ip"], "port": dev["port"]})

    def refresh(self):
        for ch in self._device_box.get_children(): self._device_box.remove(ch)
        self._status.set_text("Buscando...")
        threading.Thread(
            target=lambda: GLib.idle_add(self._populate, manager.get_devices()),
            daemon=True
        ).start()
        # Actualizar lista Android con lo que ya se encontró
        self._refresh_android_list(manager.get_android_devices())
        GLib.idle_add(self._build_qr)
        return False

    def _build_qr(self):
        # Limpiar QR anterior
        for ch in self._qr_box.get_children(): self._qr_box.remove(ch)

        info = manager.ws_server.get_connection_info()
        self._qr_info.set_text(f"{info['ip']}:{info['port']}")

        try:
            import qrcode as _qr
            import tempfile, os
            from gi.repository import GdkPixbuf

            img = _qr.make(manager.ws_server.get_qr_text())
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name); tmp.close()
            pb  = GdkPixbuf.Pixbuf.new_from_file_at_scale(tmp.name, 180, 180, True)
            os.unlink(tmp.name)

            qr_img = Gtk.Image.new_from_pixbuf(pb)
            qr_img.set_halign(Gtk.Align.CENTER)
            self._qr_box.pack_start(qr_img, False, False, 0)

        except ImportError:
            hint = lbl(
                "pip install qrcode[pil]\n--break-system-packages",
                "device-row-sub", halign=Gtk.Align.CENTER
            )
            hint.set_justify(Gtk.Justification.CENTER)
            self._qr_box.pack_start(hint, False, False, 0)
        except Exception as e:
            print(f"[qr] {e}")

        self._qr_box.show_all()

    def _populate(self, devices):
        self._status.set_text(f"{len(devices)} dispositivo(s)" if devices else "Sin dispositivos")
        for dev in devices:
            btn = Gtk.Button(); cls(btn,"device-row-btn"); btn.set_relief(Gtk.ReliefStyle.NONE)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); row.set_border_width(6)
            icon_name = "phone-symbolic" if dev["type"]=="usb" else "network-wireless-symbolic"
            row.pack_start(Gtk.Image.new_from_icon_name(icon_name,Gtk.IconSize.LARGE_TOOLBAR),False,False,0)
            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            info.pack_start(lbl(dev["name"],"device-row-name"),False,False,0)
            info.pack_start(lbl(f"{dev['type'].upper()}  {dev['serial']}","device-row-sub"),False,False,0)
            row.pack_start(info,True,True,0); btn.add(row)
            btn.connect("clicked",lambda _,d=dev: self._cb(d))
            self._device_box.pack_start(btn,False,False,0)
        self._device_box.show_all()

    def _on_wifi(self,_):
        ip = self._ip.get_text().strip()
        port_txt = self._port.get_text().strip()
        port = int(port_txt) if port_txt.isdigit() else 5555
        if not ip: self._status.set_text("Ingresa una IP"); return
        self._status.set_text(f"Conectando a {ip}:{port}...")
        def do():
            ok,msg = manager.connect_wifi_device(ip,port)
            GLib.idle_add(lambda: (
                (self._status.set_text("Conectado!"), GLib.timeout_add(600,self.refresh))
                if ok else self._status.set_text(f"Error: {msg[:50]}")
            ))
        threading.Thread(target=do,daemon=True).start()


# ── Transferencia de archivos ─────────────────────────────────────────────────
def _adb_bin():
    p = BASE_DIR/"scrcpy"/"adb"
    return str(p) if p.exists() else "adb"

def _toast(parent, msg):
    d = Gtk.MessageDialog(transient_for=parent,
        message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=msg)
    d.run(); d.destroy()

def transfer_pc_to_phone(parent):
    dlg = Gtk.FileChooserDialog(title="Enviar archivo al teléfono",
        parent=parent, action=Gtk.FileChooserAction.OPEN)
    dlg.add_button("Cancelar",Gtk.ResponseType.CANCEL)
    dlg.add_button("Enviar",  Gtk.ResponseType.OK)
    if dlg.run() == Gtk.ResponseType.OK:
        path = dlg.get_filename(); dlg.destroy()
        if path and manager.is_connected():
            def push():
                dest = f"/sdcard/Download/{os.path.basename(path)}"
                r = subprocess.run([_adb_bin(),"-s",manager.serial,"push",path,dest],
                    capture_output=True,text=True)
                GLib.idle_add(lambda: _toast(parent,
                    "Archivo enviado" if r.returncode==0 else f"Error: {r.stderr[:80]}"))
            threading.Thread(target=push,daemon=True).start()
    else:
        dlg.destroy()

def transfer_phone_to_pc(parent):
    pdlg = Gtk.Dialog(title="Ruta en el teléfono",parent=parent)
    pdlg.add_button("Cancelar",Gtk.ResponseType.CANCEL)
    pdlg.add_button("Siguiente",Gtk.ResponseType.OK)
    pdlg.set_default_size(360,-1)
    box = pdlg.get_content_area(); box.set_spacing(6); box.set_border_width(14)
    box.pack_start(lbl("Ruta del archivo en el teléfono:","res-label"),False,False,0)
    entry = Gtk.Entry(); entry.set_text("/sdcard/Download/"); entry.set_hexpand(True)
    box.pack_start(entry,False,False,0); pdlg.show_all()
    if pdlg.run() != Gtk.ResponseType.OK: pdlg.destroy(); return
    remote = entry.get_text().strip(); pdlg.destroy()
    if not remote: return

    fdlg = Gtk.FileChooserDialog(title="Guardar en...",parent=parent,
        action=Gtk.FileChooserAction.SELECT_FOLDER)
    fdlg.add_button("Cancelar",Gtk.ResponseType.CANCEL)
    fdlg.add_button("Guardar aquí",Gtk.ResponseType.OK)
    if fdlg.run() == Gtk.ResponseType.OK:
        dest = fdlg.get_filename(); fdlg.destroy()
        if dest and manager.is_connected():
            def pull():
                r = subprocess.run([_adb_bin(),"-s",manager.serial,"pull",remote,dest],
                    capture_output=True,text=True)
                GLib.idle_add(lambda: _toast(parent,
                    "Archivo recibido" if r.returncode==0 else f"Error: {r.stderr[:80]}"))
            threading.Thread(target=pull,daemon=True).start()
    else:
        fdlg.destroy()


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Yelena Connect")
        self.set_default_size(700, 680)
        self.set_size_request(540, 560)
        self.set_resizable(True)
        self._connected = False
        self.connect("destroy", lambda _: manager.disconnect())

        # ── HeaderBar nativa GNOME ────────────────────────────────────────────
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        self._hb = hb
        self.set_titlebar(hb)

        # ── Izquierda: [logo] Nombre / subtítulo ─────────────────────────────
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        left_box.set_valign(Gtk.Align.CENTER)

        logo_path = ASSETS_DIR / "logo.svg"
        if logo_path.exists():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(str(logo_path), 22, 22)
                left_box.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
            except Exception: pass
        else:
            left_box.pack_start(
                Gtk.Image.new_from_icon_name("phone-symbolic", Gtk.IconSize.LARGE_TOOLBAR),
                False, False, 0
            )

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        text_box.set_valign(Gtk.Align.CENTER)

        app_name = Gtk.Label(label="Yelena Connect")
        app_name.set_halign(Gtk.Align.START)
        app_name.get_style_context().add_class("app-title")

        self._sub_lbl = Gtk.Label(label="Sin dispositivo conectado")
        self._sub_lbl.set_halign(Gtk.Align.START)
        self._sub_lbl.get_style_context().add_class("device-sub")

        text_box.pack_start(app_name,      False, False, 0)
        text_box.pack_start(self._sub_lbl, False, False, 0)
        left_box.pack_start(text_box, False, False, 0)
        left_box.show_all()
        hb.pack_start(left_box)

        # ── Derecha: Conectar | Mirror | Refrescar | Enviar | Recibir | Acerca de
        b_about = icon_btn("help-about-symbolic",     "header-icon-btn", "Acerca de")
        b_about.connect("clicked", self._show_about)
        hb.pack_end(b_about)

        b_qr = icon_btn("view-grid-symbolic", "header-icon-btn", "Conectar app Android (QR)")
        b_qr.connect("clicked", self._show_qr)
        hb.pack_end(b_qr)

        b2 = icon_btn("document-save-symbolic",       "header-icon-btn", "Recibir archivo del teléfono")
        b2.connect("clicked", lambda _: transfer_phone_to_pc(self))
        hb.pack_end(b2)

        b1 = icon_btn("document-send-symbolic",       "header-icon-btn", "Enviar archivo al teléfono")
        b1.connect("clicked", lambda _: transfer_pc_to_phone(self))
        hb.pack_end(b1)

        b_refresh = icon_btn("view-refresh-symbolic",  "header-icon-btn", "Refrescar")
        b_refresh.connect("clicked", self._on_refresh)
        hb.pack_end(b_refresh)

        self._btn_mirror = icon_btn(
            "video-display-symbolic", "header-icon-btn", "Abrir mirror de pantalla"
        )
        self._btn_mirror.connect("clicked", self._on_mirror)
        self._btn_mirror.set_sensitive(False)
        hb.pack_end(self._btn_mirror)

        self._btn_connect = icon_btn(
            "network-wired-symbolic", "header-icon-btn", "Conectar dispositivo"
        )
        self._btn_connect.connect("clicked", lambda _: self._toggle_connect())
        hb.pack_end(self._btn_connect)

        # ── Layout principal ──────────────────────────────────────────────────
        overlay = Gtk.Overlay()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cls(content, "main-bg")

        self.media_bar = MediaBar()
        content.pack_start(self.media_bar, False, False, 0)
        content.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
        )

        self.notif_panel = NotificationPanel()
        content.pack_start(self.notif_panel, True, True, 0)
        content.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
        )

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.res_panel    = ResourcePanel()
        self.keypad_panel = KeypadPanel()
        bottom.pack_start(self.res_panel,    True, True, 0)
        bottom.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0
        )
        bottom.pack_start(self.keypad_panel, True, True, 0)
        content.pack_start(bottom, False, False, 0)

        overlay.add(content)
        self._connect_panel = ConnectPanel(self._on_device_selected)
        self._connect_panel.set_hexpand(True)
        self._connect_panel.set_vexpand(True)
        overlay.add_overlay(self._connect_panel)
        self._connect_panel.show_all()
        self.add(overlay)
        overlay.show_all()

        manager.resources.add_callback(self.res_panel.update)
        manager.notifications.add_callback(self.notif_panel.update)
        manager.media.add_callback(lambda d: GLib.idle_add(self.media_bar.update, d))
        manager.on_connect(self._on_connected)
        manager.on_disconnect(self._on_disconnected)

    # ── Mirror ────────────────────────────────────────────────────────────────
    def _on_mirror(self, _):
        if manager.scrcpy.is_running():
            manager.stop_screen_mirror()
            self._btn_mirror.set_tooltip_text("Abrir mirror de pantalla")
            img = Gtk.Image.new_from_icon_name("phone-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
            self._btn_mirror.set_image(img)
        else:
            manager.start_screen_mirror()
            self._btn_mirror.set_tooltip_text("Detener mirror de pantalla")
            img = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
            self._btn_mirror.set_image(img)

    # ── QR para app Android ───────────────────────────────────────────────────
    def _show_qr(self, _):
        info = manager.ws_server.get_connection_info()
        ip   = info["ip"]
        port = info["port"]
        name = info["name"]

        dlg = Gtk.Dialog(title="Conectar app Android", transient_for=self)
        dlg.set_default_size(360, -1)
        box = dlg.get_content_area()
        box.set_spacing(12)
        box.set_border_width(20)

        # Título
        t = lbl("Escanea este código con la app", "media-title", halign=Gtk.Align.CENTER)
        t.set_hexpand(True)
        box.pack_start(t, False, False, 0)

        # Intentar generar QR con qrcode
        qr_shown = False
        try:
            import qrcode as _qr
            import tempfile, os
            from gi.repository import GdkPixbuf

            qr_text = manager.ws_server.get_qr_text()
            img = _qr.make(qr_text)
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name)
            tmp.close()

            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(tmp.name, 240, 240, True)
            qr_img = Gtk.Image.new_from_pixbuf(pb)
            qr_img.set_halign(Gtk.Align.CENTER)
            box.pack_start(qr_img, False, False, 0)
            os.unlink(tmp.name)
            qr_shown = True
        except Exception as e:
            print(f"[qr] No se pudo generar imagen QR: {e}")

        if not qr_shown:
            msg = lbl(
                "Instala qrcode para ver el código:\n"
                "pip install qrcode[pil] --break-system-packages",
                "res-label", halign=Gtk.Align.CENTER
            )
            msg.set_justify(Gtk.Justification.CENTER)
            box.pack_start(msg, False, False, 0)

        # Info de conexión manual
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(sep, False, False, 4)

        info_lbl = lbl(
            f"O conecta manualmente:\n  IP:    {ip}\n  Puerto: {port}\n  Nombre: {name}",
            "res-label"
        )
        info_lbl.set_selectable(True)   # permite copiar
        box.pack_start(info_lbl, False, False, 0)

        dlg.add_button("Cerrar", Gtk.ResponseType.CLOSE)
        dlg.show_all()
        dlg.run()
        dlg.destroy()

    # ── Acerca de ─────────────────────────────────────────────────────────────
    def _show_about(self, _):
        about = Gtk.AboutDialog(transient_for=self)
        about.set_program_name("Yelena Connect")
        about.set_version("v0.2-beta")
        about.set_copyright("© 2026 CuerdOS")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://cuerdos.github.io")
        about.set_website_label("Visitar Página Web")
        about.set_comments("Controla tu teléfono desde tu PC")
        logo = str(ASSETS_DIR / "logo.svg")
        if os.path.exists(logo):
            try:
                about.set_logo(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(logo, 96, 96, True)
                )
            except Exception: pass
        about.run(); about.destroy()

    # ── Refrescar ─────────────────────────────────────────────────────────────
    def _on_refresh(self, _):
        if not manager.is_connected(): return
        manager.resources.stop()
        manager.notifications.stop()
        manager.media.stop()
        GLib.timeout_add(250, self._restart_monitors)

    def _restart_monitors(self):
        manager.resources.start()
        manager.notifications.start()
        manager.media.start()
        return False

    # ── Conexión ──────────────────────────────────────────────────────────────
    def _toggle_connect(self):
        if self._connected:
            manager.disconnect()
        else:
            self._connect_panel.show_all()
            GLib.idle_add(self._connect_panel.refresh)

    def _on_device_selected(self, device):
        self._connect_panel.hide()
        threading.Thread(
            target=manager.connect_device, args=(device,), daemon=True
        ).start()

    def _on_connected(self, device):
        GLib.idle_add(self._do_connected, device)

    def _do_connected(self, device):
        self._connected = True
        tag = "USB" if device["type"] == "usb" else "WiFi"
        self._sub_lbl.set_text(f"{device['name']}  [{tag}]")
        self._sub_lbl.get_style_context().add_class("connected")
        self._btn_connect.set_tooltip_text("Desconectar")
        self._btn_connect.set_image(
            Gtk.Image.new_from_icon_name("network-offline-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        self._btn_mirror.set_sensitive(True)
        self._connect_panel.hide()

    def _on_disconnected(self):
        GLib.idle_add(self._do_disconnected)

    def _do_disconnected(self):
        self._connected = False
        self._sub_lbl.set_text("Sin dispositivo conectado")
        self._sub_lbl.get_style_context().remove_class("connected")
        self._btn_connect.set_tooltip_text("Conectar dispositivo")
        self._btn_connect.set_image(
            Gtk.Image.new_from_icon_name("network-wired-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        self._btn_mirror.set_sensitive(False)
        self._btn_mirror.set_tooltip_text("Abrir mirror de pantalla")
        self._btn_mirror.set_image(
            Gtk.Image.new_from_icon_name("video-display-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        manager.stop_screen_mirror()
        self._connect_panel.show_all()


# ── Aplicación ────────────────────────────────────────────────────────────────
class YelenaApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="org.cuerdos.yelena",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )

    def do_activate(self):
        apply_css()
        win = MainWindow(self)
        win.show_all()
        win.present()

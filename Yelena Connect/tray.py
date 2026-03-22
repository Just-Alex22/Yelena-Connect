"""
tray.py — Yelena Connect System Tray Applet
Reemplaza ui.py completamente. Sin ventana principal.

Dependencias:
  pip install ayatana-appindicator3 --break-system-packages
  o bien usa gi.repository.AppIndicator3 si está disponible

Menú del tray:
  [estado de conexión — click abre QR]
  ─────────────────────────────────────
  Enviar archivos
  Recibir archivos
  ─────────────────────────────────────
  Acerca de
  Idioma ▶ Español / English / Português / Català
  Salir
"""

import gi
gi.require_version("Gtk",   "3.0")
gi.require_version("GLib",  "2.0")
gi.require_version("GdkPixbuf", "2.0")

try:
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3
    HAS_INDICATOR = True
except Exception:
    HAS_INDICATOR = False

from gi.repository import Gtk, GLib, GdkPixbuf

import os
import sys
import threading
import subprocess
import tempfile
from pathlib import Path

from engine import manager

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH      = ASSETS_DIR / "logo.svg"

def _is_dark_theme() -> bool:
    """Detecta si el sistema está en modo oscuro via GTK o gsettings."""
    # Método 1: GTK settings
    try:
        settings = Gtk.Settings.get_default()
        if settings:
            theme = settings.get_property("gtk-theme-name") or ""
            if any(x in theme.lower() for x in ["dark", "oscuro", "noir"]):
                return True
            prefer_dark = settings.get_property("gtk-application-prefer-dark-theme")
            if prefer_dark:
                return True
    except Exception:
        pass

    # Método 2: gsettings (GNOME/KDE)
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2
        )
        if "dark" in r.stdout.lower():
            return True
    except Exception:
        pass

    # Método 3: KDE plasma color scheme
    try:
        r = subprocess.run(
            ["kreadconfig5", "--group", "General", "--key", "ColorScheme"],
            capture_output=True, text=True, timeout=2
        )
        if "dark" in r.stdout.lower():
            return True
    except Exception:
        pass

    return False  # default: modo claro

def _svg_to_png(svg_path: Path, size: int = 22) -> str | None:
    """Convierte SVG a PNG temporal. Retorna path o None si falla."""
    import tempfile
    try:
        tmp = Path(tempfile.mktemp(suffix=".png"))
        r = subprocess.run(
            ["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(tmp), str(svg_path)],
            capture_output=True, timeout=3
        )
        if r.returncode == 0 and tmp.exists():
            return str(tmp)
    except FileNotFoundError:
        pass
    try:
        tmp = Path(tempfile.mktemp(suffix=".png"))
        r = subprocess.run(
            ["convert", "-background", "none", "-resize", f"{size}x{size}",
             str(svg_path), str(tmp)],
            capture_output=True, timeout=3
        )
        if r.returncode == 0 and tmp.exists():
            return str(tmp)
    except FileNotFoundError:
        pass
    return None

def _resolve_tray_icon() -> str:
    """
    Resuelve el ícono correcto según el tema del sistema:
      assets/tray-icon-dark.svg  → modo oscuro
      assets/tray-icon-light.svg → modo claro
      assets/tray-icon.svg       → cualquier tema (fallback)
      assets/tray-icon.png       → PNG directo
    """
    dark = _is_dark_theme()
    candidates = [
        ASSETS_DIR / (f"tray-icon-{'dark' if dark else 'light'}.svg"),
        ASSETS_DIR / (f"tray-icon-{'dark' if dark else 'light'}.png"),
        ASSETS_DIR / "tray-icon.svg",
        ASSETS_DIR / "tray-icon.png",
        LOGO_PATH,
    ]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        return "network-wireless"
    if src.suffix == ".png":
        return str(src)
    # SVG → PNG para compatibilidad con AppIndicator3 en KDE
    png = _svg_to_png(src)
    return png if png else str(src)

TRAY_ICON_PATH = _resolve_tray_icon()

# ─── i18n mínimo ──────────────────────────────────────────────────────────────
STRINGS = {
    "es": {
        "connecting":     "Buscando dispositivos...",
        "connected":      "Conectado: {}",
        "disconnected":   "Desconectado — Toca para conectar",
        "send_files":     "Enviar archivos",
        "recv_files":     "Recibir archivos",
        "about":          "Acerca de",
        "language":       "Idioma",
        "quit":           "Salir",
        "qr_title":       "Conectar app Android",
        "qr_subtitle":    "Escanea este código con la app Yelena Connect",
        "qr_manual":      "Conexión manual: {}:{}",
        "qr_no_lib":      "Instala qrcode:\npip install qrcode[pil] --break-system-packages",
        "about_text":     "Yelena Connect v0.2\n© 2026 CuerdOS\nLicencia GPL 3.0\ncuerdos.github.io",
        "send_title":     "Enviar archivo al teléfono",
        "recv_title":     "Recibir archivo del teléfono",
        "no_device":      "Sin dispositivo conectado",
        "sending":        "Enviando...",
        "received":       "Guardado en {}",
        "error":          "Error: {}",
    },
    "en": {
        "connecting":     "Looking for devices...",
        "connected":      "Connected: {}",
        "disconnected":   "Disconnected — Tap to connect",
        "send_files":     "Send files",
        "recv_files":     "Receive files",
        "about":          "About",
        "language":       "Language",
        "quit":           "Quit",
        "qr_title":       "Connect Android app",
        "qr_subtitle":    "Scan this code with the Yelena Connect app",
        "qr_manual":      "Manual: {}:{}",
        "qr_no_lib":      "Install qrcode:\npip install qrcode[pil] --break-system-packages",
        "about_text":     "Yelena Connect v0.2\n© 2026 CuerdOS\nGPL 3.0 License\ncuerdos.github.io",
        "send_title":     "Send file to phone",
        "recv_title":     "Receive file from phone",
        "no_device":      "No device connected",
        "sending":        "Sending...",
        "received":       "Saved to {}",
        "error":          "Error: {}",
    },
    "pt": {
        "connecting":     "Procurando dispositivos...",
        "connected":      "Conectado: {}",
        "disconnected":   "Desconectado — Toque para conectar",
        "send_files":     "Enviar arquivos",
        "recv_files":     "Receber arquivos",
        "about":          "Sobre",
        "language":       "Idioma",
        "quit":           "Sair",
        "qr_title":       "Conectar app Android",
        "qr_subtitle":    "Escaneie este código com o app Yelena Connect",
        "qr_manual":      "Manual: {}:{}",
        "qr_no_lib":      "Instale qrcode:\npip install qrcode[pil] --break-system-packages",
        "about_text":     "Yelena Connect v0.2\n© 2026 CuerdOS\nLicença GPL 3.0\ncuerdos.github.io",
        "send_title":     "Enviar arquivo para o celular",
        "recv_title":     "Receber arquivo do celular",
        "no_device":      "Sem dispositivo conectado",
        "sending":        "Enviando...",
        "received":       "Salvo em {}",
        "error":          "Erro: {}",
    },
    "ca": {
        "connecting":     "Cercant dispositius...",
        "connected":      "Connectat: {}",
        "disconnected":   "Desconnectat — Toca per connectar",
        "send_files":     "Enviar fitxers",
        "recv_files":     "Rebre fitxers",
        "about":          "Quant a",
        "language":       "Idioma",
        "quit":           "Sortir",
        "qr_title":       "Connectar app Android",
        "qr_subtitle":    "Escaneja aquest codi amb l'app Yelena Connect",
        "qr_manual":      "Manual: {}:{}",
        "qr_no_lib":      "Instal·la qrcode:\npip install qrcode[pil] --break-system-packages",
        "about_text":     "Yelena Connect v0.2\n© 2026 CuerdOS\nLlicència GPL 3.0\ncuerdos.github.io",
        "send_title":     "Enviar fitxer al telèfon",
        "recv_title":     "Rebre fitxer del telèfon",
        "no_device":      "Sense dispositiu connectat",
        "sending":        "Enviant...",
        "received":       "Desat a {}",
        "error":          "Error: {}",
    },
}

LANG_NAMES = {"es": "Español", "en": "English", "pt": "Português", "ca": "Català"}


class YelenaTray:
    def __init__(self):
        self._lang   = "es"
        self._connected  = False
        self._device_name = ""
        self._qr_window   = None

        # Registrar callbacks del engine
        manager.on_connect(self._on_device_connected)          # ADB
        manager.on_disconnect(self._on_device_disconnected)    # ADB
        manager.on_android_found(self._on_android_found)       # UDP discovery
        manager.on_wifi_connected(self._on_wifi_connected)     # WebSocket WiFi
        manager.on_wifi_disconnected(self._on_wifi_disconnected)

        self._build_indicator()
        self._update_menu()

    def _(self, key, *args):
        """Traducción."""
        tmpl = STRINGS.get(self._lang, STRINGS["es"]).get(key, key)
        return tmpl.format(*args) if args else tmpl

    # ── Indicador ─────────────────────────────────────────────────────────────

    def _build_indicator(self):
        icon = TRAY_ICON_PATH

        if HAS_INDICATOR:
            self._indicator = AppIndicator3.Indicator.new(
                "yelena-connect", icon,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            # Escuchar cambios de tema para actualizar el ícono
            try:
                settings = Gtk.Settings.get_default()
                if settings:
                    settings.connect("notify::gtk-theme-name",
                        lambda *_: self._indicator.set_icon_full(
                            _resolve_tray_icon(), "Yelena Connect"))
                    settings.connect("notify::gtk-application-prefer-dark-theme",
                        lambda *_: self._indicator.set_icon_full(
                            _resolve_tray_icon(), "Yelena Connect"))
            except Exception:
                pass
            self._menu = Gtk.Menu()
            self._indicator.set_menu(self._menu)
        else:
            # Fallback: StatusIcon (deprecated pero funciona)
            self._status_icon = Gtk.StatusIcon()
            if LOGO_PATH.exists():
                self._status_icon.set_from_file(TRAY_ICON_PATH)
            else:
                self._status_icon.set_from_icon_name("network-wireless")
            self._status_icon.set_tooltip_text("Yelena Connect")
            self._status_icon.connect("popup-menu", self._on_status_icon_popup)
            self._menu = Gtk.Menu()

    def _update_menu(self):
        for item in self._menu.get_children():
            self._menu.remove(item)

        # ── Estado / botón de conexión ─────────────────────────────────────
        if self._connected:
            lbl = self._("connected", self._device_name)
        else:
            lbl = self._("disconnected")

        conn_item = Gtk.MenuItem(label=lbl)
        conn_item.connect("activate", self._on_conn_clicked)
        self._menu.append(conn_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        # ── Enviar / Recibir ───────────────────────────────────────────────
        send_item = Gtk.MenuItem(label=self._("send_files"))
        send_item.connect("activate", self._on_send)
        send_item.set_sensitive(self._connected)
        self._menu.append(send_item)

        recv_item = Gtk.MenuItem(label=self._("recv_files"))
        recv_item.connect("activate", self._on_recv)
        recv_item.set_sensitive(self._connected)
        self._menu.append(recv_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        # ── Acerca de ──────────────────────────────────────────────────────
        about_item = Gtk.MenuItem(label=self._("about"))
        about_item.connect("activate", self._on_about)
        self._menu.append(about_item)

        # ── Idioma ────────────────────────────────────────────────────────
        lang_item = Gtk.MenuItem(label=self._("language"))
        lang_menu = Gtk.Menu()
        for code, name in LANG_NAMES.items():
            li = Gtk.CheckMenuItem(label=name)
            li.set_active(code == self._lang)
            li.connect("activate", self._on_lang, code)
            lang_menu.append(li)
        lang_item.set_submenu(lang_menu)
        self._menu.append(lang_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        # ── Salir ─────────────────────────────────────────────────────────
        quit_item = Gtk.MenuItem(label=self._("quit"))
        quit_item.connect("activate", self._on_quit)
        self._menu.append(quit_item)

        self._menu.show_all()

    # ── Callbacks engine ──────────────────────────────────────────────────────

    def _on_device_connected(self, device: dict):
        """Dispositivo conectado por ADB/USB."""
        self._connected   = True
        self._device_name = device.get("name", "")
        GLib.idle_add(self._update_menu)

    def _on_device_disconnected(self):
        """Dispositivo ADB desconectado — solo marcar si tampoco hay WiFi."""
        if not manager.is_wifi_connected():
            self._connected   = False
            self._device_name = ""
            GLib.idle_add(self._update_menu)

    def _on_wifi_connected(self, device: dict):
        """App Android conectada por WebSocket WiFi."""
        self._connected   = True
        self._device_name = device.get("name", device.get("ip", "Android"))
        print(f"[tray] App Android conectada por WiFi: {self._device_name}")
        GLib.idle_add(self._update_menu)

    def _on_wifi_disconnected(self, ip: str):
        """App Android desconectada por WiFi."""
        if not manager.is_connected() and not manager.is_wifi_connected():
            self._connected   = False
            self._device_name = ""
            GLib.idle_add(self._update_menu)

    def _on_android_found(self, device: dict):
        """App Android detectada por UDP — aún no conectada."""
        print(f"[tray] App Android en red: {device['name']} @ {device['ip']}")

    # ── Acciones menú ─────────────────────────────────────────────────────────

    def _on_conn_clicked(self, _):
        """Abre ventana flotante con QR."""
        if self._qr_window and self._qr_window.get_visible():
            self._qr_window.present()
            return
        self._qr_window = self._build_qr_window()
        self._qr_window.show_all()

    def _build_qr_window(self) -> Gtk.Window:
        win = Gtk.Window(title=self._("qr_title"))
        win.set_default_size(300, -1)
        win.set_resizable(False)
        win.set_keep_above(True)
        win.set_position(Gtk.WindowPosition.MOUSE)
        win.set_border_width(20)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        win.add(box)

        # Subtítulo
        sub = Gtk.Label(label=self._("qr_subtitle"))
        sub.set_line_wrap(True)
        sub.get_style_context().add_class("dim-label")
        box.pack_start(sub, False, False, 0)

        # QR
        info = manager.ws_server.get_connection_info()
        qr_shown = False
        try:
            import qrcode as _qr
            img = _qr.make(manager.ws_server.get_qr_text())
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name); tmp.close()
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(tmp.name, 220, 220, True)
            os.unlink(tmp.name)
            qr_img = Gtk.Image.new_from_pixbuf(pb)
            qr_img.set_halign(Gtk.Align.CENTER)
            box.pack_start(qr_img, False, False, 0)
            qr_shown = True
        except Exception as e:
            print(f"[qr] {e}")

        if not qr_shown:
            hint = Gtk.Label(label=self._("qr_no_lib"))
            hint.set_justify(Gtk.Justification.CENTER)
            box.pack_start(hint, False, False, 0)

        # IP:puerto seleccionable
        ip_lbl = Gtk.Label(label=self._("qr_manual", info["ip"], info["port"]))
        ip_lbl.set_selectable(True)
        ip_lbl.set_halign(Gtk.Align.CENTER)
        box.pack_start(ip_lbl, False, False, 0)

        # Botón cerrar
        close_btn = Gtk.Button(label="Cerrar")
        close_btn.connect("clicked", lambda _: win.destroy())
        box.pack_start(close_btn, False, False, 0)

        return win

    def _on_send(self, _):
        """Selecciona archivo y lo envía por ADB push."""
        if not manager.is_connected() and not manager.is_wifi_connected():
            self._notify(self._("no_device"))
            return
        dlg = Gtk.FileChooserDialog(
            title=self._("send_title"),
            action=Gtk.FileChooserAction.OPEN,
        )
        dlg.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dlg.add_button("Enviar",   Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            dlg.destroy()
            if path:
                threading.Thread(
                    target=self._do_send, args=(path,), daemon=True
                ).start()
        else:
            dlg.destroy()

    def _do_send(self, path: str):
        fname = Path(path).name
        # Intentar ADB primero si hay USB
        if manager.is_connected() and manager.serial:
            from engine import adb
            result = adb(["push", path, "/sdcard/Download/"],
                         device_serial=manager.serial, timeout=60)
            if "pushed" in result or "1 file" in result:
                GLib.idle_add(self._notify, f"✓ {fname} enviado (ADB)")
                return
        # Enviar via WebSocket base64
        try:
            import base64 as _b64
            with open(path, "rb") as f:
                raw = f.read()
            # Limitar a 50MB
            if len(raw) > 50 * 1024 * 1024:
                GLib.idle_add(self._notify, "Archivo demasiado grande (máx 50MB)")
                return
            data = _b64.b64encode(raw).decode()
            if manager.ws_server._clients and manager.ws_server._loop:
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    manager.ws_server._broadcast_async(
                        "file_send", {"name": fname, "data": data}
                    ),
                    manager.ws_server._loop
                )
                GLib.idle_add(self._notify, f"✓ {fname} enviado ({len(raw)//1024}KB)")
            else:
                GLib.idle_add(self._notify, self._("no_device"))
        except Exception as e:
            GLib.idle_add(self._notify, self._("error", str(e)[:60]))

    def _on_recv(self, _):
        """Lista archivos en /sdcard/Download y permite descargarlos."""
        if not manager.is_connected() and not manager.is_wifi_connected():
            self._notify(self._("no_device"))
            return
        # Solo ADB puede listar archivos directamente
        if not manager.is_connected() or not manager.serial:
            self._notify("Recibir archivos requiere conexión USB/ADB")
            return
        from engine import adb
        serial = manager.serial
        raw = adb(["shell", "ls", "/sdcard/Download/"],
                  device_serial=serial, timeout=10)
        files = [f.strip() for f in raw.splitlines() if f.strip()]
        if not files:
            self._notify("No hay archivos en /sdcard/Download/")
            return

        dlg = Gtk.Dialog(title=self._("recv_title"))
        dlg.set_default_size(360, 300)
        box = dlg.get_content_area()
        box.set_border_width(12)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(200)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for f in files:
            row = Gtk.ListBoxRow()
            row.add(Gtk.Label(label=f, xalign=0))
            listbox.add(row)
        scroll.add(listbox)
        box.pack_start(scroll, True, True, 0)

        dlg.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dlg.add_button("Descargar", Gtk.ResponseType.OK)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            row = listbox.get_selected_row()
            if row:
                fname = files[row.get_index()]
                dlg.destroy()
                save_dlg = Gtk.FileChooserDialog(
                    title="Guardar como",
                    action=Gtk.FileChooserAction.SAVE,
                )
                save_dlg.set_current_name(fname)
                save_dlg.add_button("Cancelar", Gtk.ResponseType.CANCEL)
                save_dlg.add_button("Guardar",  Gtk.ResponseType.OK)
                if save_dlg.run() == Gtk.ResponseType.OK:
                    dest = save_dlg.get_filename()
                    save_dlg.destroy()
                    threading.Thread(
                        target=self._do_recv,
                        args=(fname, dest, serial),
                        daemon=True
                    ).start()
                else:
                    save_dlg.destroy()
            else:
                dlg.destroy()
        else:
            dlg.destroy()

    def _do_recv(self, fname: str, dest: str, serial: str):
        from engine import adb
        result = adb(
            ["pull", f"/sdcard/Download/{fname}", dest],
            device_serial=serial, timeout=60
        )
        if "pulled" in result or "1 file" in result:
            GLib.idle_add(self._notify, self._("received", dest))
        else:
            GLib.idle_add(self._notify, self._("error", result[:60] or "sin respuesta"))

    def _on_about(self, _):
        about = Gtk.AboutDialog()
        about.set_program_name("Yelena Connect")
        about.set_version("v0.2-beta")
        about.set_copyright("© 2026 CuerdOS")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://cuerdos.github.io")
        about.set_website_label("Visitar Página Web")
        about.set_comments("Controla tu teléfono desde tu PC")
        if LOGO_PATH.exists():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(LOGO_PATH), 96, 96, True)
                about.set_logo(pb)
            except Exception:
                pass
        about.run()
        about.destroy()

    def _on_lang(self, item: Gtk.CheckMenuItem, code: str):
        if item.get_active():
            self._lang = code
            GLib.idle_add(self._update_menu)

    def _on_quit(self, _):
        manager.discovery.stop()
        Gtk.main_quit()

    def _on_status_icon_popup(self, icon, button, time):
        self._menu.popup(None, None, None, None, button, time)

    # ── Notificación de escritorio ────────────────────────────────────────────

    def _notify(self, msg: str):
        try:
            subprocess.Popen(
                ["notify-send", "Yelena Connect", msg,
                 "--icon", str(LOGO_PATH) if LOGO_PATH.exists() else "network-wireless"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            print(f"[tray] {msg}")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        print("[tray] Yelena Connect iniciado en system tray")
        Gtk.main()

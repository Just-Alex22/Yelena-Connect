"""
main.py — Yelena Connect System Tray Applet
Punto de entrada. Fuerza X11 para compatibilidad con GTK+AppIndicator.
"""
import os
os.environ.setdefault("GDK_BACKEND", "x11")

from tray import YelenaTray

if __name__ == "__main__":
    app = YelenaTray()
    app.run()

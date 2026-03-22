# Yelena Connect

<p align="center">
  <img src="Yelena Connect/assets/logo.svg" alt="Yelena Connect Logo" width="150"/>
</p>

## What is Yelena Connect?

**Yelena Connect** is a free and open source app that lets you control your Linux PC from your Android phone over Wi-Fi. No USB cable, no cloud account, no proprietary services, just your local network.

## Features

- **Remote keyboard** — type text and send special keys (Ctrl+C, arrows, Esc...) directly to your PC
- **Clipboard sync** — bidirectional clipboard between phone and PC in real time
- **Media controls** — play, pause, skip tracks and adjust volume
- **System monitor** — real-time CPU, RAM, disk usage and uptime
- **Process manager** — view all running processes and kill them
- **App launcher** — open installed applications remotely
- **Notifications** — view PC notifications on your phone
- **File transfer** — send files between devices
- **QR code pairing** — scan to connect instantly, no manual setup

## How does it work?

The PC runs a lightweight GTK3 system tray applet that opens a WebSocket server on your local network. The Android app discovers it automatically via UDP broadcast and connects to it. All communication happens locally, nothing leaves your network.

## Requirements

### PC
- **Python 3.10+**
- **GTK 3**
- **PyGObject**
- **websockets** · **psutil**
- **xdotool** (X11) or **ydotool** (Wayland)
- **xclip** (clipboard)

### Android
- **Android 8.0+** (API 26)

## Installation

### PC applet

Clone the repository and install dependencies:

```bash
git clone https://github.com/cuerdos/yelena-connect.git
cd yelena-connect

pip install websockets psutil --break-system-packages
sudo apt install xclip xdotool
```

Run the applet:

```bash
python3 "Yelena Connect/main.py"
```

### Android app

Download APK from releases or build from source:

```bash
cd YelenaAndroid
./gradlew assembleRelease
```

## Contributing

If you want to collaborate with the development of **Yelena Connect**, follow us on ShitHub and send your **Pull Requests** and **Issues** through the repository.

## License

This program comes with the GNU GPLv3 license, consult https://www.gnu.org/licenses/gpl-3.0.en.html for more information.

---

> **Development:** [Just_Alex](https://github.com/Just-Alex22)
> **Repository:** [yelena-connect](https://github.com/cuerdos/yelena-connect)

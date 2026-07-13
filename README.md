# <img src=logo.svg height="31" valign="middle"> Y-Connect

<p align="center">
  <img src="previews/phone3.jpg" width="30%">
  <img src="previews/phone.jpg" width="30%">
  <img src="previews/phone2.jpg" width="30%">
</p>

<p align="center">
  <img src="previews/pc.jpg" width="91%">
</p>

## What is Y-Connect?

**Y-Connect** is a free and open source app that lets you control your Linux PC from your Android phone over Wi-Fi. No USB cable, no cloud account, no proprietary services, just your local network.

## Features

- **Remote keyboard**: type text and send special keys (Ctrl+C, arrows, Esc...) directly to your PC
- **Clipboard sync**: bidirectional clipboard between phone and PC in real time
- **Media controls**: play, pause, skip tracks and adjust volume
- **System monitor**: real-time CPU, RAM, disk usage and uptime
- **Process manager**: view all running processes and kill them
- **App launcher**: open installed applications remotely
- **Notifications**: view PC notifications on your phone
- **File transfer**: send files between devices
- **QR code pairing**: scan to connect instantly, no manual setup

## How does it work?

The PC runs a Python backend (engine + bridge) with a Flutter dashboard UI. The engine opens a WebSocket server for device communication, while the bridge exposes a separate WebSocket API for the Flutter frontend. An Android app discovers the PC automatically via UDP broadcast and connects to it. The desktop companion also shows a system tray icon with connection status, signal strength and quick media/volume actions. All communication happens locally, nothing leaves your network.

## Requirements

### PC (Desktop Companion)

**Backend:**
- **Python 3.10+**
- **PySide6** (system tray)
- **websockets**
- **engine module** (must be in the same directory or PYTHONPATH)

**Frontend:**
- **Flutter 3.0+** (Linux desktop enabled)
- **Noto Sans CJK fonts** for Japanese/Korean text support

### Android
- **Android 8.0+** (API 26)

## Installation

### PC Desktop Companion

Clone the repository:

```bash
git clone https://github.com/Just-Alex22/Y-Connect.git
cd Y-Connect
```

Install Python dependencies:

```bash
pip install websockets PySide6 --break-system-packages
```

Install CJK fonts (optional, needed for Japanese/Korean UI):

Download and place these fonts in the `fonts/` folder:
- [Noto Sans SC](https://fonts.google.com/noto/specimen/Noto+Sans+SC) (Chinese)
- [Noto Sans KR](https://fonts.google.com/noto/specimen/Noto+Sans+KR) (Korean)
- [Noto Sans JP](https://fonts.google.com/noto/specimen/Noto+Sans+JP) (Japanese)

Then install Flutter dependencies and build:

```bash
cd Yelena\ Connect/
flutter pub get
flutter build linux
```

Or run directly in debug mode:

```bash
flutter run -d linux
```

Run the full app (backend + Flutter + system tray):

```bash
python3 start.py
```

This will launch the bridge, start the engine, open the Flutter dashboard and show the system tray icon automatically. Use the tray menu to control media, adjust volume, or quit (kills both processes).

### Android app

Download APK from releases or build from source:

```bash
cd Y-Connect
./gradlew assembleRelease
```

## Contributing

If you want to collaborate with the development of **Y-Connect**, follow us on ShitHub and send your **Pull Requests** and **Issues** through the repository.

## License

This program comes with the GNU GPLv3 license, consult https://www.gnu.org/licenses/gpl-3.0.en.html for more information.

---

> **Development:** [Just_Alex](https://github.com/Just-Alex22)
> **Repository:** [yelena-connect](https://github.com/cuerdos-project/Y-Connect)

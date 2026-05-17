# PyQt Camera Dashboard

A multi-camera RTSP dashboard built with Python, OpenCV, and PyQt5.

This application allows you to:

- View multiple RTSP camera feeds
- Record camera streams
- Automatically reconnect disconnected cameras
- Store camera settings in a JSON configuration file
- Add new cameras directly from the GUI
- Automatically organize recordings by date and hour
- Automatically clean up old recordings when disk usage becomes too high

--- 

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green)
![OpenCV](https://img.shields.io/badge/OpenCV-Video-red)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Main Dashboard

![Dashboard](screenshots/camera_dashboard_interface.png)

---

## First-Time Setup

![Setup Dialog](screenshots/first_launch.png)

---

## Add Camera Dialog

![Add Camera](screenshots/adding_new_camera.png)

---

# Features

## First-Time Setup Wizard

When the application launches for the first time:

- A PyQt setup dialog appears
- You enter:
  - Camera IP
  - Camera name
  - Username
  - Password
- The application automatically creates `camera_config.json`

Passwords are masked during entry.

---

# GUI Features

- Live camera dashboard
- Individual recording controls
- Start/Stop all recording buttons
- Dynamic camera addition using the `+` button
- Dark theme UI
- Automatic camera tile removal on repeated failures

---

# Installation

## Linux / Ubuntu

Install system dependencies:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

Clone the repository:

```bash
git clone https://github.com/BleedingCodes/pyqt-camera-dashboard.git
cd pyqt-camera-dashboard
```

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
python camera_dashboard.py
```

---

## Windows

Clone the repository:

```powershell
git clone https://github.com/BleedingCodes/pyqt-camera-dashboard.git
cd pyqt-camera-dashboard
```

Create and activate a virtual environment:

```powershell
py -m venv venv
venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the app:

```powershell
python camera_dashboard.py
```

---

## First-Time Launch

On first launch, the app creates:

```text
camera_config.json
```

You will be prompted to enter:

- Number of cameras
- Camera IP address
- Camera display name
- Username
- Password

Passwords are masked in the setup dialog.

Do not upload `camera_config.json` to GitHub.

---

# Configuration File

The application stores camera settings in:

```text
camera_config.json
```

Example structure:

```json
[
  {
    "name": "Front Door",
    "ip": "192.168.1.100",
    "username": "admin",
    "password": "password123"
  }
]
```

---

# Recording Storage

Recordings are automatically organized like this:

```text
recordings/
└── YYYY-MM-DD/
    └── HH/
```

Example:

```text
recordings/
└── 2026-05-17/
    └── 14/
```

---

# Security Notice

Do NOT upload `camera_config.json` to GitHub.

The `.gitignore` file is configured to prevent accidental uploads of credentials and recordings.

---

# Future Improvements

Ideas for future versions:

- Motion detection
- GPU acceleration
- H.265 support
- PTZ controls
- Web dashboard
- Docker support
- Encrypted credential storage
- Multi-monitor support

---

# License

MIT License

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

# Requirements

- Python 3.10+
- OpenCV
- PyQt5

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# Running the Application

```bash
python camera_dashboard.py
```

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

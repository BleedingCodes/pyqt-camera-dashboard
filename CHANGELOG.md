# Changelog

All notable changes to the PyQt Camera Dashboard are documented here.

---

## [v3.0.0] — 2026-09-05

### Added
- Fernet encryption for camera credentials — config is never stored in plaintext
- Automatic encryption key generation on first run (`secret.key`)
- Config file is encrypted immediately after every save operation
- Session-only tile Remove button — dismiss any camera from the dashboard without affecting the config
- Duplicate camera name handling — unique filename prefixes guaranteed across all cameras

### Fixed
- `save_camera_details()` previously called undefined variables — security functions now wired correctly throughout the app
- Duplicate camera names previously caused recording files to overwrite each other silently

### Security
- `secret.key` and `camera_config.json` added to `.gitignore`
- LICENSE updated to Michael Rivera | MainByte Labs

---

## [v2.0.0] — 2026

### Added
- JSON-based camera configuration (`camera_config.json`)
- First-time setup wizard using PyQt dialogs — no manual file editing required
- Add camera at runtime using the `+` button without restarting the app
- Manual Reconnect button per camera tile — non-blocking, does not freeze the dashboard
- Camera tile stays visible after connection failure and shows Camera Offline status
- `reconnect_requested` flag allows GUI to trigger reconnect without blocking the main thread

### Removed
- Hardcoded camera list replaced by JSON config system

---

## [v1.0.0] — 2026

### Initial Release
- Multi-camera RTSP live monitoring using PyQt5 and OpenCV
- Per-camera recording with 10-minute segment splitting
- Start All / Stop All recording controls
- Automatic disk cleanup when usage exceeds threshold
- Recordings organized by date and hour
- Dark theme GUI
- Camera tile removed from dashboard after 3 consecutive connection failures

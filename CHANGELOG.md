# Changelog

All notable changes to the PyQt Camera Dashboard are documented here.

---

## [v3.0.1] — 2026-09-14

### Fixed
- `CameraWorker.run()`: early return on permanent camera failure now calls `stop_recording()` before returning — previously leaked an open `VideoWriter` if the camera failed while recording
- `secret.key` is now created with `0o600` permissions (owner read/write only) — previously created with process umask, which is typically world-readable on Linux
- `closeEvent` now explicitly calls `stop_recording()` on all tiles before stopping worker threads — ensures `VideoWriter` flushes before `wait(3000)` timeout
- `QApplication(sys.argv)` replaces `QApplication([])` — required for correct platform plugin initialization on X11 and Wayland
- `cleanup_by_disk_usage()` moved inside `main()` — previously ran at module import level, outside the `__name__` guard

### Added
- `__version__ = "3.0.1"` string added to `camera_dashboard.py`
- `numpy` added explicitly to `requirements.txt` (previously an implicit transitive dependency of `opencv-python`)
- `Optional[QWidget]` type annotations added to `parent` parameters on `prompt_for_camera_details`, `load_camera_details`, and `prompt_for_first_time_setup`
- `np.ndarray` type annotation added to `update_frame` `frame` parameter

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

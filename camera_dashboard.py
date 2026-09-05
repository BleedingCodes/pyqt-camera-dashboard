from __future__ import annotations  # Allows newer type-hint behavior.

import os
import glob
import json
import re
import shutil
import cv2
import time

from cryptography.fernet import Fernet
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote
from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QInputDialog, QVBoxLayout, QWidget,
)
from PyQt5 import QtCore

os.environ.pop("QT_PLUGIN_PATH", None)  # Removes bad Qt plugin paths that OpenCV may set.
os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)  # Removes bad Qt platform plugin paths.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"  # Forces RTSP over TCP with a 5-second timeout.
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(
    os.path.dirname(QtCore.__file__), "Qt5", "plugins"
)  # Forces PyQt5 Qt plugins.


# ── Constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # Stores the folder where this script lives.
CONFIG_FILE = os.path.join(SCRIPT_DIR, "camera_config.json")  # Stores camera setup beside the script.
KEY_FILE = os.path.join(SCRIPT_DIR, "secret.key")  # Stores encryption key beside the script.
RECORDINGS_ROOT = os.path.join(SCRIPT_DIR, "recordings")  # Sets recordings folder beside script.
RECORD_DURATION_SECONDS = 15 * 60  # Sets each recording file to 15 minutes.
DEFAULT_FPS = 15.0  # Sets fallback FPS.
RECONNECT_DELAY_SECONDS = 3  # Sets delay between reconnect attempts.
MAX_CONNECT_FAILURES = 3  # Stops trying after 3 failed camera connections.
MAX_DISK_USAGE = 75  # Deletes oldest recordings when disk usage goes above 75 percent.
RTSP_PATH = "/cam/realmonitor?channel=1&subtype=0"  # Uses the same RTSP path format the original script used.


# ── Camera config ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)  # Makes camera config read-only.
class CameraConfig:  # Defines camera settings.
    name: str  # Stores camera display name.
    url: str  # Stores camera RTSP URL.
    file_prefix: str  # Stores recording filename prefix.


# ── Encryption helpers ────────────────────────────────────────────────────────

def load_or_create_key() -> bytes:  # Loads existing key or generates a new one.
    if os.path.exists(KEY_FILE):  # Checks whether the key file already exists.
        with open(KEY_FILE, "rb") as key_file:  # Opens existing key file.
            return key_file.read()  # Returns stored key bytes.
    key = Fernet.generate_key()  # Generates a new secure key.
    with open(KEY_FILE, "wb") as key_file:  # Saves new key to disk.
        key_file.write(key)  # Writes key bytes.
    return key  # Returns new key.


def get_fernet(key: bytes) -> Fernet:  # Returns a Fernet instance for the given key.
    return Fernet(key)  # Creates Fernet object.


def encrypt_config(key: bytes) -> None:  # Encrypts the JSON config file in place.
    fernet = get_fernet(key)  # Gets Fernet instance.
    with open(CONFIG_FILE, "rb") as file:  # Opens plaintext config.
        data = file.read()  # Reads plaintext bytes.
    with open(CONFIG_FILE, "wb") as file:  # Overwrites config file.
        file.write(fernet.encrypt(data))  # Writes encrypted bytes.


def decrypt_config(key: bytes) -> dict:  # Decrypts and returns parsed JSON config.
    fernet = get_fernet(key)  # Gets Fernet instance.
    with open(CONFIG_FILE, "rb") as file:  # Opens encrypted config.
        encrypted_data = file.read()  # Reads encrypted bytes.
    decrypted_data = fernet.decrypt(encrypted_data)  # Decrypts bytes.
    return json.loads(decrypted_data.decode("utf-8"))  # Returns parsed dict.


# ── Filename helpers ──────────────────────────────────────────────────────────

def make_file_prefix(name: str) -> str:  # Creates safe recording filename prefixes from camera names.
    prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip().lower()).strip("_")  # Replaces unsafe filename characters.
    return prefix or "camera"  # Uses a fallback when the name has no usable characters.


def unique_file_prefix(name: str, existing_prefixes: list[str]) -> str:  # Returns a prefix that does not collide with existing ones.
    base = make_file_prefix(name)  # Generates base prefix from name.
    prefix = base  # Starts with base prefix.
    counter = 2  # Starts duplicate counter at 2.
    while prefix in existing_prefixes:  # Loops until prefix is unique.
        prefix = f"{base}_{counter}"  # Appends counter to base.
        counter += 1  # Increments counter.
    return prefix  # Returns unique prefix.


# ── URL builder ───────────────────────────────────────────────────────────────

def build_rtsp_url(ip_address: str, username: str, password: str) -> str:  # Builds a camera RTSP URL from saved fields.
    safe_username = quote(username, safe="")  # Escapes special characters in the username.
    safe_password = quote(password, safe="")  # Escapes special characters in the password.
    return f"rtsp://{safe_username}:{safe_password}@{ip_address}:554{RTSP_PATH}"  # Returns RTSP stream URL.


# ── Camera detail dialogs ─────────────────────────────────────────────────────

def prompt_for_camera_details(parent=None, camera_number: int | None = None) -> dict | None:  # Gets one camera through PyQt dialogs.
    title_suffix = f" Camera {camera_number}" if camera_number is not None else " New Camera"  # Builds dialog title suffix.
    ip_address, ok = QInputDialog.getText(parent, f"Setup{title_suffix}", "Camera IP address:")  # Asks for IP address.
    if not ok:
        return None  # User cancelled.
    ip_address = ip_address.strip()  # Removes accidental spaces.

    name, ok = QInputDialog.getText(parent, f"Setup{title_suffix}", "User-friendly camera name:")  # Asks for camera display name.
    if not ok:
        return None  # User cancelled.
    name = name.strip()  # Removes accidental spaces.

    username, ok = QInputDialog.getText(parent, f"Setup{title_suffix}", "Username:")  # Asks for username.
    if not ok:
        return None  # User cancelled.
    username = username.strip()  # Removes accidental spaces.

    password, ok = QInputDialog.getText(parent, f"Setup{title_suffix}", "Password:", QLineEdit.Password)  # Asks for masked password.
    if not ok:
        return None  # User cancelled.

    if not ip_address or not name or not username:
        QMessageBox.warning(parent, "Missing camera details", "IP address, camera name, and username are required.")  # Explains missing fields.
        return prompt_for_camera_details(parent, camera_number)  # Repeats the same camera setup.

    return {
        "ip_address": ip_address,
        "name": name,
        "username": username,
        "password": password,
    }  # Returns serializable camera settings without file_prefix — assigned later to guarantee uniqueness.


# ── Config save / load ────────────────────────────────────────────────────────

def save_camera_details(camera_details: list[dict], key: bytes) -> None:  # Writes and encrypts camera settings.
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:  # Writes plaintext JSON.
        json.dump({"cameras": camera_details}, file, indent=4)  # Saves readable JSON.
    encrypt_config(key)  # Encrypts the file immediately after writing.


def load_camera_details(key: bytes, parent=None) -> list[dict]:  # Decrypts and loads config, or runs first-time setup.
    if not os.path.exists(CONFIG_FILE):  # Checks whether setup has already happened.
        return prompt_for_first_time_setup(key, parent)  # Runs first-time setup dialogs.

    try:
        data = decrypt_config(key)  # Decrypts and parses existing config.
    except Exception as exc:  # Catches bad key or corrupted file.
        QMessageBox.critical(parent, "Camera config error", f"Could not decrypt {CONFIG_FILE}:\n{exc}")  # Shows readable error.
        return []  # Prevents starting with unknown settings.

    camera_details = data.get("cameras", [])  # Reads saved camera list.
    if not isinstance(camera_details, list):
        QMessageBox.critical(parent, "Camera config error", "camera_config.json must contain a 'cameras' list.")  # Shows schema error.
        return []  # Prevents startup with bad config.
    return camera_details  # Returns saved settings.


def prompt_for_first_time_setup(key: bytes, parent=None) -> list[dict]:  # Creates first camera JSON using PyQt dialogs.
    camera_count, ok = QInputDialog.getInt(
        parent, "First-time camera setup",
        "How many cameras do you want to monitor?", 1, 1, 64, 1
    )  # Asks count.
    if not ok:
        return []  # User cancelled setup.

    camera_details = []  # Stores all entered cameras.
    existing_prefixes: list[str] = []  # Tracks assigned prefixes to prevent collisions.

    for index in range(1, camera_count + 1):  # Loops through requested cameras.
        details = prompt_for_camera_details(parent, index)  # Gets one camera.
        if details is None:
            return []  # User cancelled setup.
        prefix = unique_file_prefix(details["name"], existing_prefixes)  # Assigns unique prefix.
        details["file_prefix"] = prefix  # Stores prefix in details.
        existing_prefixes.append(prefix)  # Tracks used prefix.
        camera_details.append(details)  # Saves the camera details.

    save_camera_details(camera_details, key)  # Writes and encrypts JSON after successful setup.
    return camera_details  # Returns all configured cameras.


# ── Config → CameraConfig ─────────────────────────────────────────────────────

def camera_details_to_config(details: dict) -> CameraConfig:  # Converts JSON camera data into the worker config.
    name = str(details.get("name", "Camera")).strip() or "Camera"  # Reads display name.
    url = details.get("url")  # Allows older/future configs to store a full URL.
    if not url:
        url = build_rtsp_url(
            str(details.get("ip_address", "")).strip(),
            str(details.get("username", "")).strip(),
            str(details.get("password", "")),
        )  # Builds URL from fields.
    file_prefix = str(details.get("file_prefix", make_file_prefix(name))).strip() or make_file_prefix(name)  # Reads recording prefix.
    return CameraConfig(name=name, url=url, file_prefix=file_prefix)  # Returns immutable camera config.


# ── Recording helpers ─────────────────────────────────────────────────────────

def hour_folder() -> str:  # Creates/returns current recording folder.
    now = datetime.now()  # Gets current date and time.
    folder = os.path.join(RECORDINGS_ROOT, now.strftime("%Y-%m-%d"), now.strftime("%H"))  # Builds recordings/date/hour folder.
    os.makedirs(folder, exist_ok=True)  # Creates folder if missing.
    return folder  # Returns folder path.


def cleanup_by_disk_usage() -> None:  # Deletes oldest recordings only when disk usage is too high.
    os.makedirs(RECORDINGS_ROOT, exist_ok=True)  # Ensures recordings folder exists.
    total, used, _ = shutil.disk_usage(RECORDINGS_ROOT)  # Reads disk usage for recordings drive.
    used_percent = (used / total) * 100  # Calculates disk used percentage.
    if used_percent < MAX_DISK_USAGE:  # Checks whether disk usage is still safe.
        return  # Stops because cleanup is not needed.
    print(f"Disk usage high: {used_percent:.1f}% - deleting oldest recordings...")  # Prints cleanup notice.
    files = glob.glob(os.path.join(RECORDINGS_ROOT, "**", "*.mp4"), recursive=True)  # Finds all recording files.
    files.sort(key=lambda path: os.path.getmtime(path))  # Sorts files oldest first.
    for file in files:  # Loops through recordings from oldest to newest.
        try:
            os.remove(file)  # Deletes the oldest recording file.
            print(f"Deleted oldest recording: {file}")  # Prints deleted file.
            total, used, _ = shutil.disk_usage(RECORDINGS_ROOT)  # Rechecks disk usage.
            used_percent = (used / total) * 100  # Recalculates used percentage.
            if used_percent < MAX_DISK_USAGE:  # Checks whether usage is safe again.
                print("Disk usage back to safe level.")  # Prints safe message.
                break  # Stops deleting files.
        except OSError as exc:  # Catches delete errors.
            print(f"Could not delete {file}: {exc}")  # Prints delete error.


# ── Camera worker ─────────────────────────────────────────────────────────────

class CameraWorker(QThread):  # Background camera thread.
    frame_ready = pyqtSignal(object)  # Sends frames to GUI.
    status_changed = pyqtSignal(str)  # Sends status text to GUI.
    recording_changed = pyqtSignal(bool)  # Sends recording state to GUI.
    failed_permanently = pyqtSignal()  # Tells GUI camera has gone offline.

    def __init__(self, camera: CameraConfig):  # Initializes camera worker.
        super().__init__()  # Initializes QThread.
        self.camera = camera  # Stores camera config.
        self.running = True  # Controls thread loop.
        self.recording = False  # Tracks recording state.
        self.writer = None  # Stores active VideoWriter.
        self.record_start = None  # Stores current recording start time.
        self.writer_size = None  # Stores recording frame size.
        self.fps = DEFAULT_FPS  # Stores recording FPS.
        self.cap = None  # Stores VideoCapture object.
        self.connect_failures = 0  # Counts failed camera connections.
        self.reconnect_requested = False  # Requests a manual reconnect without blocking the GUI.

    def run(self) -> None:  # Runs thread loop.
        while self.running:
            self.status_changed.emit(
                f"Connecting... attempt {self.connect_failures + 1}/{MAX_CONNECT_FAILURES}"
            )  # Updates GUI status.
            self.cap = cv2.VideoCapture(self.camera.url, cv2.CAP_FFMPEG)  # Opens camera stream.
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)  # Reduces camera buffer lag.

            if not self.cap.isOpened():
                self.connect_failures += 1
                self._release_capture()
                if self.connect_failures >= MAX_CONNECT_FAILURES:
                    self.status_changed.emit("Offline")
                    self.failed_permanently.emit()
                    self.running = False
                    return
                self.status_changed.emit("Connection failed. Retrying...")
                time.sleep(RECONNECT_DELAY_SECONDS)
                continue

            self.connect_failures = 0
            self.status_changed.emit("Live")
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            if not self.fps or self.fps <= 1 or self.fps > 60:
                self.fps = DEFAULT_FPS

            manual_reconnect = False

            while self.running and self.cap.isOpened():
                if self.reconnect_requested:
                    self.reconnect_requested = False
                    manual_reconnect = True
                    self.status_changed.emit("Reconnecting...")
                    break
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    self.status_changed.emit("Frame lost. Reconnecting...")
                    break
                self.frame_ready.emit(frame)
                if self.recording:
                    self._write_frame(frame)

            self._release_capture()
            if self.running and not manual_reconnect:
                time.sleep(RECONNECT_DELAY_SECONDS)

        self.stop_recording()
        self._release_capture()
        self.status_changed.emit("Stopped")

    def start_recording(self) -> None:  # Starts recording.
        if not self.running:
            return
        self.recording = True
        self.recording_changed.emit(True)
        self.status_changed.emit("Recording")

    def stop_recording(self) -> None:  # Stops recording.
        self.recording = False
        self.recording_changed.emit(False)
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            self.writer_size = None
        self.status_changed.emit("Live" if self.running else "Stopped")

    def request_reconnect(self) -> None:  # Requests a reconnect without blocking the GUI.
        self.connect_failures = 0
        if self.isRunning():
            self.reconnect_requested = True
            return
        self.running = True
        self.reconnect_requested = False
        self.start()

    def stop_worker(self) -> None:  # Stops worker thread.
        self.running = False
        self.reconnect_requested = False

    def _write_frame(self, frame) -> None:  # Writes frame to active recording.
        if self.writer is None:
            self._open_new_writer(frame)
        if self.writer is None:
            return
        if self.writer_size is not None:
            width, height = self.writer_size
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        self.writer.write(frame)
        if self.record_start and (
            datetime.now() - self.record_start
        ).total_seconds() >= RECORD_DURATION_SECONDS:
            self.writer.release()
            self.writer = None
            self.writer_size = None
            self._open_new_writer(frame)

    def _open_new_writer(self, frame) -> None:  # Opens new video file.
        self.record_start = datetime.now()
        filename = (
            f"{self.camera.file_prefix}_{self.record_start.strftime('%Y-%m-%d_%H-%M-%S')}.mp4"
        )  # Creates filename.
        path = os.path.join(hour_folder(), filename)
        height, width = frame.shape[:2]
        self.writer_size = (width, height)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(path, fourcc, self.fps, self.writer_size)
        if not self.writer.isOpened():
            self.status_changed.emit("Recording failed: VideoWriter did not open")
            self.writer = None
            self.writer_size = None
            return
        self.status_changed.emit(f"Recording: {os.path.basename(path)}")
        print(f"Recording started: {path}")

    def _release_capture(self) -> None:  # Releases camera stream.
        if self.cap is not None:
            self.cap.release()
            self.cap = None


# ── Camera tile ───────────────────────────────────────────────────────────────

class CameraTile(QWidget):  # GUI tile for one camera.
    remove_requested = pyqtSignal(object)  # Signal to remove this tile from the dashboard.

    def __init__(self, camera: CameraConfig):  # Initializes tile.
        super().__init__()
        self.camera = camera

        self.title = QLabel(camera.name)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-weight: bold; font-size: 16px;")

        self.video = QLabel("Waiting for camera...")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(420, 260)
        self.video.setStyleSheet("background: #111; color: white; border: 1px solid #333;")

        self.status = QLabel("Starting...")
        self.status.setAlignment(Qt.AlignCenter)

        self.record_button = QPushButton("Start Recording")
        self.record_button.clicked.connect(self.toggle_recording)

        self.reconnect_button = QPushButton("Reconnect")
        self.reconnect_button.clicked.connect(self.reconnect_camera)

        self.remove_button = QPushButton("Remove")  # Removes this tile from the session.
        self.remove_button.clicked.connect(self.request_remove)  # Connects remove button.
        self.remove_button.setStyleSheet("color: #ff6666;")  # Styles remove button red to distinguish it.

        layout = QVBoxLayout()
        layout.addWidget(self.title)
        layout.addWidget(self.video)
        layout.addWidget(self.status)
        layout.addWidget(self.record_button)
        layout.addWidget(self.reconnect_button)
        layout.addWidget(self.remove_button)  # Adds remove button below reconnect.
        self.setLayout(layout)

        self.worker = CameraWorker(camera)
        self.worker.frame_ready.connect(self.update_frame)
        self.worker.status_changed.connect(self.handle_status)
        self.worker.recording_changed.connect(self.update_record_button)
        self.worker.failed_permanently.connect(self.camera_failed)
        self.worker.start()

    def request_remove(self) -> None:  # Emits signal to remove this tile for the session.
        self.remove_requested.emit(self)  # Tells MainWindow to remove this tile.

    def reconnect_camera(self) -> None:  # Reconnects only this camera without freezing the dashboard.
        self.reconnect_button.setEnabled(False)
        self.reconnect_button.setText("Reconnecting...")
        self.status.setText("Reconnecting...")
        self.video.clear()
        self.video.setText("Reconnecting...")
        self.worker.request_reconnect()

    def handle_status(self, message: str) -> None:  # Updates status label and button states.
        self.status.setText(message)
        if message == "Live":
            self.record_button.setEnabled(True)
            self.reconnect_button.setEnabled(True)
            self.reconnect_button.setText("Reconnect")
        elif message == "Offline":
            self.reconnect_button.setEnabled(True)
            self.reconnect_button.setText("Reconnect")

    def camera_failed(self) -> None:  # Keeps tile visible after connection attempts fail.
        self.video.clear()
        self.video.setText("Camera Offline")
        self.record_button.setEnabled(False)
        self.reconnect_button.setEnabled(True)
        self.reconnect_button.setText("Reconnect")

    def toggle_recording(self) -> None:  # Toggles recording on this tile.
        if self.worker.recording:
            self.worker.stop_recording()
        else:
            self.worker.start_recording()

    def update_record_button(self, recording: bool) -> None:  # Updates record button text.
        self.record_button.setText("Stop Recording" if recording else "Start Recording")

    def update_frame(self, frame) -> None:  # Updates displayed frame.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, channels = rgb.shape
        bytes_per_line = channels * w
        image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        self.video.setPixmap(
            pixmap.scaled(self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def shutdown(self) -> None:  # Safely shuts down tile worker.
        self.worker.stop_worker()
        self.worker.wait(3000)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):  # Main dashboard window.
    def __init__(self, camera_details: list[dict], key: bytes):  # Initializes dashboard.
        super().__init__()
        self.camera_details = camera_details  # Stores JSON-backed camera details.
        self.key = key  # Stores encryption key for save operations.
        self.setWindowTitle("Camera Dashboard")
        self.resize(1400, 850)
        self.tiles: list[CameraTile] = []
        self.grid = QGridLayout()

        for details in self.camera_details:
            self.add_camera_tile(camera_details_to_config(details))
        self.rebuild_grid()

        controls = QHBoxLayout()
        self.add_camera_button = QPushButton("+")
        self.add_camera_button.setFixedWidth(40)
        self.record_all = QPushButton("Start All")
        self.stop_all_button = QPushButton("Stop All")
        self.add_camera_button.clicked.connect(self.add_camera_from_dialog)
        self.record_all.clicked.connect(self.start_all)
        self.stop_all_button.clicked.connect(self.stop_all)
        controls.addWidget(self.add_camera_button)
        controls.addWidget(self.record_all)
        controls.addWidget(self.stop_all_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(self.grid)
        main_layout.addLayout(controls)
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.cleanup_timer = QtCore.QTimer(self)
        self.cleanup_timer.timeout.connect(cleanup_by_disk_usage)
        self.cleanup_timer.start(60 * 60 * 1000)  # Runs disk cleanup every hour.

    def add_camera_tile(self, camera: CameraConfig) -> None:  # Adds a camera tile to the dashboard.
        tile = CameraTile(camera)
        tile.remove_requested.connect(self.remove_tile)  # Connects both failure and manual remove to same handler.
        self.tiles.append(tile)

    def add_camera_from_dialog(self) -> None:  # Adds one new camera while the app is running.
        existing_prefixes = [
            str(d.get("file_prefix", "")) for d in self.camera_details
        ]  # Collects existing prefixes to prevent collisions.
        details = prompt_for_camera_details(self)
        if details is None:
            return
        prefix = unique_file_prefix(details["name"], existing_prefixes)  # Assigns unique prefix.
        details["file_prefix"] = prefix  # Stores unique prefix in details.
        self.camera_details.append(details)
        save_camera_details(self.camera_details, self.key)  # Saves and encrypts updated config.
        self.add_camera_tile(camera_details_to_config(details))
        self.record_all.setEnabled(True)
        self.stop_all_button.setEnabled(True)
        self.rebuild_grid()

    def rebuild_grid(self) -> None:  # Rebuilds camera layout after any tile change.
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                self.grid.removeWidget(widget)
        for index, tile in enumerate(self.tiles):
            row = index // 2
            col = index % 2
            self.grid.addWidget(tile, row, col)

    def remove_tile(self, tile: CameraTile) -> None:  # Removes a tile from the session without touching the config.
        if tile in self.tiles:
            tile.shutdown()  # Stops the worker thread safely.
            self.tiles.remove(tile)
            self.grid.removeWidget(tile)
            tile.setParent(None)
            tile.deleteLater()
            self.rebuild_grid()
        if not self.tiles:
            self.record_all.setEnabled(False)
            self.stop_all_button.setEnabled(False)

    def start_all(self) -> None:  # Starts all recordings.
        for tile in self.tiles:
            if not tile.worker.recording:
                tile.worker.start_recording()

    def stop_all(self) -> None:  # Stops all recordings.
        for tile in self.tiles:
            if tile.worker.recording:
                tile.worker.stop_recording()

    def closeEvent(self, event) -> None:  # Handles window close.
        for tile in self.tiles:
            tile.worker.stop_worker()
        for tile in self.tiles:
            tile.worker.wait(3000)
        event.accept()


# ── Entry point ───────────────────────────────────────────────────────────────

cleanup_by_disk_usage()  # Runs disk cleanup before GUI starts.

def main() -> None:  # Program entry point.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication([])
    app.setStyleSheet("""
QMainWindow { background-color: #121212; }
QWidget { background-color: #121212; color: #eeeeee; font-size: 14px; }
QLabel { color: #eeeeee; }
QPushButton {
    background-color: #2b2b2b; color: #eeeeee;
    border: 1px solid #555555; padding: 8px; border-radius: 6px;
}
QPushButton:hover { background-color: #3a3a3a; }
QPushButton:pressed { background-color: #1f1f1f; }
""")

    key = load_or_create_key()  # Loads or generates encryption key at startup.
    camera_details = load_camera_details(key)  # Decrypts and loads config, or runs first-time setup.

    if not camera_details:
        QMessageBox.information(None, "Camera Dashboard", "No cameras were configured. The app will close.")
        return

    cleanup_by_disk_usage()
    window = MainWindow(camera_details, key)  # Passes key into window for save operations.
    window.showMaximized()
    app.exec_()


if __name__ == "__main__":
    main()

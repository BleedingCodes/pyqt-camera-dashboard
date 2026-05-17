
from __future__ import annotations  # Allows newer type-hint behavior.

import os  
import glob  
import json
import re
import shutil 
import cv2  
import time  
from dataclasses import dataclass 
from datetime import datetime 
from urllib.parse import quote
from PyQt5.QtCore import QThread, Qt, pyqtSignal  
from PyQt5.QtGui import QImage, QPixmap 
from PyQt5.QtWidgets import QApplication, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QInputDialog, QVBoxLayout, QWidget  
from PyQt5 import QtCore  

os.environ.pop("QT_PLUGIN_PATH", None)  # Removes bad Qt plugin paths that OpenCV may set.
os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)  # Removes bad Qt platform plugin paths.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"  # Forces RTSP over TCP with a 5-second timeout.
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(os.path.dirname(QtCore.__file__), "Qt5", "plugins")  # Forces PyQt5 Qt plugins.


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # Stores the folder where this script lives.
CONFIG_FILE = os.path.join(SCRIPT_DIR, "camera_config.json")  # Stores camera setup beside the script.
RECORDINGS_ROOT = os.path.join(SCRIPT_DIR, "recordings")  # Sets recordings folder beside script.
RECORD_DURATION_SECONDS = 10 * 60  # Sets each recording file to 10 minutes.
DEFAULT_FPS = 15.0  # Sets fallback FPS.
RECONNECT_DELAY_SECONDS = 3  # Sets delay between reconnect attempts.
MAX_CONNECT_FAILURES = 3  # Stops trying after 3 failed camera connections.
MAX_DISK_USAGE = 80  # Deletes oldest recordings when disk usage goes above 80 percent.
RTSP_PATH = "/cam/realmonitor?channel=1&subtype=0"  # Uses the same RTSP path format the original script used.


@dataclass(frozen=True)  # Makes camera config read-only.
class CameraConfig:  # Defines camera settings.
    name: str  # Stores camera display name.
    url: str  # Stores camera RTSP URL.
    file_prefix: str  # Stores recording filename prefix.


CAMERAS = []  # Filled from camera_config.json when the app starts.


def make_file_prefix(name: str) -> str:  # Creates safe recording filename prefixes from camera names.
    prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip().lower()).strip("_")  # Replaces unsafe filename characters.
    return prefix or "camera"  # Uses a fallback when the name has no usable characters.


def build_rtsp_url(ip_address: str, username: str, password: str) -> str:  # Builds a camera RTSP URL from saved fields.
    safe_username = quote(username, safe="")  # Escapes special characters in the username.
    safe_password = quote(password, safe="")  # Escapes special characters in the password.
    return f"rtsp://{safe_username}:{safe_password}@{ip_address}:554{RTSP_PATH}"  # Returns RTSP stream URL.


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
        "file_prefix": make_file_prefix(name),
    }  # Returns serializable camera settings.


def prompt_for_first_time_setup(parent=None) -> list[dict]:  # Creates first camera JSON using PyQt dialogs.
    camera_count, ok = QInputDialog.getInt(parent, "First-time camera setup", "How many cameras do you want to monitor?", 1, 1, 64, 1)  # Asks count.
    if not ok:
        return []  # User cancelled setup.

    camera_details = []  # Stores all entered cameras.
    for index in range(1, camera_count + 1):  # Loops through requested cameras.
        details = prompt_for_camera_details(parent, index)  # Gets one camera.
        if details is None:
            return []  # User cancelled setup.
        camera_details.append(details)  # Saves the camera details.
    save_camera_details(camera_details)  # Writes JSON file after successful setup.
    return camera_details  # Returns all configured cameras.


def save_camera_details(camera_details: list[dict]) -> None:  # Writes camera settings to JSON.
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump({"cameras": camera_details}, file, indent=4)  # Saves readable JSON.


def load_camera_details(parent=None) -> list[dict]:  # Loads existing JSON or launches first-time setup.
    if not os.path.exists(CONFIG_FILE):  # Checks whether setup has already happened.
        return prompt_for_first_time_setup(parent)  # Runs first-time setup dialogs.

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)  # Reads camera JSON.
    except (OSError, json.JSONDecodeError) as exc:
        QMessageBox.critical(parent, "Camera config error", f"Could not load {CONFIG_FILE}:\n{exc}")  # Shows readable error.
        return []  # Prevents starting with unknown settings.

    camera_details = data.get("cameras", [])  # Reads saved camera list.
    if not isinstance(camera_details, list):
        QMessageBox.critical(parent, "Camera config error", "camera_config.json must contain a 'cameras' list.")  # Shows schema error.
        return []  # Prevents startup with bad config.
    return camera_details  # Returns saved settings.


def camera_details_to_config(details: dict) -> CameraConfig:  # Converts JSON camera data into the worker config.
    name = str(details.get("name", "Camera")).strip() or "Camera"  # Reads display name.
    url = details.get("url")  # Allows older/future configs to store a full URL.
    if not url:
        url = build_rtsp_url(str(details.get("ip_address", "")).strip(), str(details.get("username", "")).strip(), str(details.get("password", "")))  # Builds URL from fields.
    file_prefix = str(details.get("file_prefix", make_file_prefix(name))).strip() or make_file_prefix(name)  # Reads recording prefix.
    return CameraConfig(name=name, url=url, file_prefix=file_prefix)  # Returns immutable camera config.


def hour_folder() -> str:  # Creates/returns current recording folder.
    now = datetime.now()  # Gets current date and time.
    folder = os.path.join(RECORDINGS_ROOT, now.strftime("%Y-%m-%d"), now.strftime("%H"))  # Builds recordings/date/hour folder.
    os.makedirs(folder, exist_ok=True)  # Creates folder if missing.
    return folder  # Returns folder path.


def cleanup_by_disk_usage() -> None:  # Deletes oldest recordings only when disk usage is too high.
    os.makedirs(RECORDINGS_ROOT, exist_ok=True)  # Ensures recordings folder exists.
    total, used, free = shutil.disk_usage(RECORDINGS_ROOT)  # Reads disk usage for recordings drive.
    used_percent = (used / total) * 100  # Calculates disk used percentage.
    if used_percent < MAX_DISK_USAGE:  # Checks whether disk usage is still safe.
        return  # Stops because cleanup is not needed.
    print(f"Disk usage high: {used_percent:.1f}% - deleting oldest recordings...")  # Prints cleanup notice.
    files = glob.glob(os.path.join(RECORDINGS_ROOT, "**", "*.mp4"), recursive=True)  # Finds all recording files.
    files.sort(key=lambda path: os.path.getmtime(path))  # Sorts files oldest first.
    for file in files:  # Loops through recordings from oldest to newest.
        try:  # Starts safe delete block.
            os.remove(file)  # Deletes the oldest recording file.
            print(f"Deleted oldest recording: {file}")  # Prints deleted file.
            total, used, free = shutil.disk_usage(RECORDINGS_ROOT)  # Rechecks disk usage.
            used_percent = (used / total) * 100  # Recalculates used percentage.
            if used_percent < MAX_DISK_USAGE:  # Checks whether usage is safe again.
                print("Disk usage back to safe level.")  # Prints safe message.
                break  # Stops deleting files.
        except OSError as exc:  # Catches delete errors.
            print(f"Could not delete {file}: {exc}")  # Prints delete error.


class CameraWorker(QThread):  # Background camera thread.
    frame_ready = pyqtSignal(object)  # Sends frames to GUI.
    status_changed = pyqtSignal(str)  # Sends status text to GUI.
    recording_changed = pyqtSignal(bool)  # Sends recording state to GUI.
    failed_permanently = pyqtSignal()  # Tells GUI to remove failed camera tile.

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
        

    def run(self) -> None:  # Runs thread loop.
        while self.running:  # Keeps worker alive until stopped.
            self.status_changed.emit(f"Connecting... attempt {self.connect_failures + 1}/{MAX_CONNECT_FAILURES}")  # Updates GUI status.
            self.cap = cv2.VideoCapture(self.camera.url, cv2.CAP_FFMPEG)  # Opens camera stream.
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)  # Reduces camera buffer lag.
            if not self.cap.isOpened():  # Checks failed connection.
                self.connect_failures += 1  # Adds failed attempt.
                self._release_capture()  # Releases failed capture.
                if self.connect_failures >= MAX_CONNECT_FAILURES:  # Checks failure limit.
                    self.status_changed.emit("Failed 3 times. Removing camera.")  # Shows final failure.
                    self.failed_permanently.emit()  # Requests tile removal.
                    self.running = False  # Stops worker.
                    break  # Exits loop.
                self.status_changed.emit("Connection failed. Retrying...")  # Shows retry message.
                time.sleep(RECONNECT_DELAY_SECONDS)  # Waits before retry.
                continue  # Tries again.
            self.connect_failures = 0  # Resets failures after success.
            self.status_changed.emit("Live")  # Shows live status.
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)  # Gets camera FPS.
            
            if not self.fps or self.fps <= 1 or self.fps > 60:  # Checks bad FPS value.
                self.fps = DEFAULT_FPS  # Uses fallback FPS.
            while self.running and self.cap.isOpened():  # Reads frames while connected.
                ok, frame = self.cap.read()  # Reads one frame.
                if not ok or frame is None:  # Checks frame failure.
                    self.status_changed.emit("Frame lost. Reconnecting...")  # Shows reconnect message.
                    break  # Reconnects.
                self.frame_ready.emit(frame)  # Sends frame to GUI.
                if self.recording:  # Checks recording state.
                    self._write_frame(frame)  # Writes frame to disk.
            self._release_capture()  # Releases stream.
            if self.running:  # Checks if not stopped manually.
                time.sleep(RECONNECT_DELAY_SECONDS)  # Waits before reconnect.
        self.stop_recording()  # Stops recording.
        self._release_capture()  # Releases capture.
        self.status_changed.emit("Stopped")  # Shows stopped status.
        
    def start_recording(self) -> None:  # Starts recording.
        if not self.running:  # Checks if worker stopped.
            return  # Does nothing.
        self.recording = True  # Enables recording.
        self.recording_changed.emit(True)  # Updates GUI.
        self.status_changed.emit("Recording")  # Shows recording status.
        

    def stop_recording(self) -> None:  # Stops recording.
        self.recording = False  # Disables recording.
        self.recording_changed.emit(False)  # Updates GUI.
        if self.writer is not None:  # Checks if writer exists.
            self.writer.release()  # Closes video file.
            self.writer = None  # Clears writer.
            self.writer_size = None  # Clears writer size.
        self.status_changed.emit("Live" if self.running else "Stopped")  # Shows status.

    def stop_worker(self) -> None:  # Stops worker thread.
        self.running = False  # Tells loop to stop.

    def _write_frame(self, frame) -> None:  # Writes frame to active recording.
        if self.writer is None:  # Checks if new file needed.
            self._open_new_writer(frame)  # Opens new recording file.
        if self.writer is None:  # Checks if writer failed.
            return  # Skips write.
        if self.writer_size is not None:  # Checks writer size.
            width, height = self.writer_size  # Gets target size.
            if frame.shape[1] != width or frame.shape[0] != height:  # Checks size mismatch.
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)  # Resizes frame.
        self.writer.write(frame)  # Writes frame.
        if self.record_start and (datetime.now() - self.record_start).total_seconds() >= RECORD_DURATION_SECONDS:  # Checks segment length.
            self.writer.release()  # Closes current segment.
            self.writer = None  # Clears writer.
            self.writer_size = None  # Clears size.
            self._open_new_writer(frame)  # Opens next segment.


    def _open_new_writer(self, frame) -> None:  # Opens new video file.
        self.record_start = datetime.now()  # Stores start time.
        filename = f"{self.camera.file_prefix}_{self.record_start.strftime('%Y-%m-%d_%H-%M-%S')}.mp4"  # Creates filename.
        path = os.path.join(hour_folder(), filename)  # Creates full path.
        height, width = frame.shape[:2]  # Gets frame size.
        self.writer_size = (width, height)  # Stores writer size.
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # Sets MP4 codec.
        self.writer = cv2.VideoWriter(path, fourcc, self.fps, self.writer_size)  # Creates writer.
        if not self.writer.isOpened():  # Checks writer failure.
            self.status_changed.emit("Recording failed: VideoWriter did not open")  # Shows error.
            self.writer = None  # Clears failed writer.
            self.writer_size = None  # Clears size.
            return  # Stops.
        self.status_changed.emit(f"Recording: {os.path.basename(path)}")  # Shows filename.
        print(f"Recording started: {path}")  # Prints path.

    def _release_capture(self) -> None:  # Releases camera stream.
        if self.cap is not None:  # Checks if capture exists.
            self.cap.release()  # Releases capture.
            self.cap = None  # Clears capture.


class CameraTile(QWidget):  # GUI tile for one camera.
    remove_requested = pyqtSignal(object)  # Signal to remove this tile.

    def __init__(self, camera: CameraConfig):  # Initializes tile.
        super().__init__()  # Initializes QWidget.
        self.camera = camera  # Stores camera config.
        self.title = QLabel(camera.name)  # Creates title label.
        self.title.setAlignment(Qt.AlignCenter)  # Centers title.
        self.title.setStyleSheet("font-weight: bold; font-size: 16px;")  # Styles title.
        self.video = QLabel("Waiting for camera...")  # Creates video label.
        self.video.setAlignment(Qt.AlignCenter)  # Centers video text.
        self.video.setMinimumSize(420, 260)  # Sets minimum video size.
        self.video.setStyleSheet("background: #111; color: white; border: 1px solid #333;")  # Styles video area.
        self.status = QLabel("Starting...")  # Creates status label.
        self.status.setAlignment(Qt.AlignCenter)  # Centers status.
        self.record_button = QPushButton("Start Recording")  # Creates record button.
        self.record_button.clicked.connect(self.toggle_recording)  # Connects button.
        layout = QVBoxLayout()  # Creates vertical layout.
        layout.addWidget(self.title)  # Adds title.
        layout.addWidget(self.video)  # Adds video.
        layout.addWidget(self.status)  # Adds status.
        layout.addWidget(self.record_button)  # Adds button.
        self.setLayout(layout)  # Applies layout.
        self.worker = CameraWorker(camera)  # Creates worker.
        self.worker.frame_ready.connect(self.update_frame)  # Connects frame signal.
        self.worker.status_changed.connect(self.status.setText)  # Connects status signal.
        self.worker.recording_changed.connect(self.update_record_button)  # Connects recording signal.
        self.worker.failed_permanently.connect(self.remove_self)  # Connects failure signal.
        self.worker.start()  # Starts worker thread.

    def toggle_recording(self) -> None:  # Toggles recording.
        if self.worker.recording:  # Checks if recording.
            self.worker.stop_recording()  # Stops recording.
        else:  # Handles not recording.
            self.worker.start_recording()  # Starts recording.

    def update_record_button(self, recording: bool) -> None:  # Updates button text.
        self.record_button.setText("Stop Recording" if recording else "Start Recording")  # Sets button text.

    def update_frame(self, frame) -> None:  # Updates displayed frame.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Converts BGR to RGB.
        h, w, channels = rgb.shape  # Gets frame dimensions.
        bytes_per_line = channels * w  # Calculates row size.
        image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)  # Creates Qt image.
        pixmap = QPixmap.fromImage(image)  # Creates pixmap.
        self.video.setPixmap(pixmap.scaled(self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))  # Shows scaled frame.

    def remove_self(self) -> None:  # Removes failed camera tile.
        self.record_button.setEnabled(False)  # Disables record button.
        self.video.setText("Camera unavailable")  # Shows unavailable text.
        self.remove_requested.emit(self)  # Requests removal.

    def shutdown(self) -> None:  # Safely shuts down tile.
        self.worker.stop_worker()  # Stops worker.
        self.worker.wait(3000)  # Waits for worker.


class MainWindow(QMainWindow):  # Main dashboard window.
    def __init__(self, camera_details: list[dict]):  # Initializes dashboard.
        super().__init__()  # Initializes QMainWindow.
        self.camera_details = camera_details  # Stores JSON-backed camera details.
        self.setWindowTitle("Camera Dashboard")  # Sets window title.
        self.resize(1400, 850)  # Sets starting size.
        self.tiles = []  # Stores active camera tiles.
        self.grid = QGridLayout()  # Creates camera grid.
        for details in self.camera_details:  # Loops through saved cameras.
            self.add_camera_tile(camera_details_to_config(details))  # Creates and stores each saved camera tile.
        self.rebuild_grid()  # Builds grid.
        controls = QHBoxLayout()  # Creates control row.
        self.add_camera_button = QPushButton("+")  # Creates add-camera button.
        self.add_camera_button.setFixedWidth(40)  # Keeps the plus button small.
        self.record_all = QPushButton("Start All")  # Creates Start All button.
        self.stop_all_button = QPushButton("Stop All")  # Creates Stop All button.
        self.add_camera_button.clicked.connect(self.add_camera_from_dialog)  # Connects add-camera button.
        self.record_all.clicked.connect(self.start_all)  # Connects Start All.
        self.stop_all_button.clicked.connect(self.stop_all)  # Connects Stop All.
        controls.addWidget(self.add_camera_button)  # Adds plus button.
        controls.addWidget(self.record_all)  # Adds Start All.
        controls.addWidget(self.stop_all_button)  # Adds Stop All.
        main_layout = QVBoxLayout()  # Creates main layout.
        main_layout.addLayout(self.grid)  # Adds grid.
        main_layout.addLayout(controls)  # Adds controls.
        container = QWidget()  # Creates central widget.
        container.setLayout(main_layout)  # Sets main layout.
        self.setCentralWidget(container)  # Sets central widget.
        self.cleanup_timer = QtCore.QTimer(self)  # Creates cleanup timer.
        self.cleanup_timer.timeout.connect(cleanup_by_disk_usage)  # Connects timer to disk cleanup.
        self.cleanup_timer.start(60 * 60 * 1000)  # Runs disk cleanup every hour.

    def add_camera_tile(self, camera: CameraConfig) -> None:  # Adds a camera tile and starts its worker.
        tile = CameraTile(camera)  # Creates camera tile.
        tile.remove_requested.connect(self.remove_tile)  # Connects removal signal.
        self.tiles.append(tile)  # Stores tile.

    def add_camera_from_dialog(self) -> None:  # Adds one new camera while the app is running.
        details = prompt_for_camera_details(self)  # Gets camera details from PyQt dialogs.
        if details is None:
            return  # User cancelled.
        self.camera_details.append(details)  # Adds new camera to in-memory JSON data.
        save_camera_details(self.camera_details)  # Persists the new camera immediately.
        self.add_camera_tile(camera_details_to_config(details))  # Starts the new camera worker.
        self.record_all.setEnabled(True)  # Ensures controls are enabled after adding a camera.
        self.stop_all_button.setEnabled(True)  # Ensures controls are enabled after adding a camera.
        self.rebuild_grid()  # Displays the new camera without restarting.

    def rebuild_grid(self) -> None:  # Rebuilds camera layout.
        while self.grid.count():  # Removes existing layout items.
            item = self.grid.takeAt(0)  # Takes one item.
            widget = item.widget()  # Gets widget.
            if widget is not None:  # Checks widget exists.
                self.grid.removeWidget(widget)  # Removes widget.
        for index, tile in enumerate(self.tiles):  # Loops through active tiles.
            row = index // 2  # Calculates row.
            col = index % 2  # Calculates column.
            self.grid.addWidget(tile, row, col)  # Adds tile.

    def remove_tile(self, tile: CameraTile) -> None:  # Removes failed tile.
        if tile in self.tiles:  # Checks if active.
            tile.shutdown()  # Stops tile worker.
            self.tiles.remove(tile)  # Removes from list.
            self.grid.removeWidget(tile)  # Removes from grid.
            tile.setParent(None)  # Detaches tile.
            tile.deleteLater()  # Schedules deletion.
            self.rebuild_grid()  # Rebuilds grid.
        if not self.tiles:  # Checks if no cameras left.
            self.record_all.setEnabled(False)  # Disables Start All.
            self.stop_all_button.setEnabled(False)  # Disables Stop All.

    def start_all(self) -> None:  # Starts all recordings.
        for tile in self.tiles:  # Loops through tiles.
            if not tile.worker.recording:  # Checks if not recording.
                tile.worker.start_recording()  # Starts recording.
        

    def stop_all(self) -> None:  # Stops all recordings.
        for tile in self.tiles:  # Loops through tiles.
            if tile.worker.recording:  # Checks if recording.
                tile.worker.stop_recording()  # Stops recording.

    def closeEvent(self, event) -> None:  # Handles window close.
        for tile in self.tiles:  # Loops through tiles.
            tile.worker.stop_worker()  # Stops workers.
        for tile in self.tiles:  # Loops again.
            tile.worker.wait(3000)  # Waits for workers.
        event.accept()  # Allows close.

cleanup_by_disk_usage()
def main() -> None:  # Program entry point.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)  # Enables high-DPI scaling.
    app = QApplication([])  # Creates Qt app.
    app.setStyleSheet(""" 
QMainWindow {
    background-color: #121212;
}

QWidget {
    background-color: #121212;
    color: #eeeeee;
    font-size: 14px;
}

QLabel {
    color: #eeeeee;
}

QPushButton {
    background-color: #2b2b2b;
    color: #eeeeee;
    border: 1px solid #555555;
    padding: 8px;
    border-radius: 6px;
}

QPushButton:hover {
    background-color: #3a3a3a;
}

QPushButton:pressed {
    background-color: #1f1f1f;
}
""")  # Applies dark GUI theme.
    camera_details = load_camera_details()  # Loads JSON config or runs first-time PyQt setup.
    if not camera_details:
        QMessageBox.information(None, "Camera Dashboard", "No cameras were configured. The app will close.")  # Explains why app exits.
        return  # Stops when setup is cancelled or invalid.
    cleanup_by_disk_usage()  # Runs disk cleanup once at startup.
    window = MainWindow(camera_details)  # Creates dashboard using JSON-backed camera settings.
    window.showMaximized()  # Shows dashboard.
    app.exec_()  # Starts GUI loop.


if __name__ == "__main__":  # Checks direct script run.
    main()  # Starts app.

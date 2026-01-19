import os
import sys
import re
import json
import subprocess
import threading
import shutil
import webbrowser
from datetime import datetime
from enum import Enum

from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
                               QLabel, QFrame, QWidget, QComboBox, QCheckBox, 
                               QProgressBar, QTabWidget, QTextBrowser, QFileDialog,
                               QScrollArea, QSplitter, QMessageBox, QGroupBox, QTableWidget, 
                               QTableWidgetItem, QHeaderView, QMenu, QAbstractItemView, QTimeEdit, QDialog)
from PySide6.QtCore import Qt, Signal, QThread, QSettings, QStandardPaths, QUrl, QTimer, QTime
from PySide6.QtGui import QDesktopServices, QIcon, QAction, QColor, QBrush

from .base import BaseApp

# ============================================================================
# 1. CONFIG & UTILS
# ============================================================================

PRESETS = {
    "Custom": {},
    "Best Video (MP4)": {"format": "mp4", "quality": "best", "merge": True, "meta": True, "thumb": True},
    "Audio Only (MP3)": {"format": "mp3", "quality": "192k", "meta": True, "thumb": True},
    "Archivist (MKV)": {"format": "mkv", "quality": "best", "merge": True, "subs": True, "meta": True, "thumb": True},
    "Low Data (480p)": {"format": "mp4", "quality": "480", "merge": True}
}

class DownloadState(Enum):
    IDLE = 0
    PREPARING = 1
    DOWNLOADING = 2
    FINISHED = 3
    ERROR = 4

class DataManager:
    """Handles persistence for History AND Queue."""
    def __init__(self):
        self.base_dir = os.path.join(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation), "Mio_v3")
        os.makedirs(self.base_dir, exist_ok=True)
        self.history_path = os.path.join(self.base_dir, "download_history.json")
        self.queue_path = os.path.join(self.base_dir, "download_queue.json")
        
        self.history = self._load(self.history_path)
        self.queue = self._load(self.queue_path)

    def _load(self, path):
        if os.path.exists(path):
            try:
                with open(path, 'r') as f: return json.load(f)
            except: return []
        return []

    def _save(self, path, data):
        with open(path, 'w') as f: json.dump(data, f, indent=2)

    def add_history(self, url, title, status, path):
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "url": url,
            "title": title or "Unknown",
            "status": status,
            "path": path
        }
        self.history.insert(0, entry)
        self.history = self.history[:200]
        self._save(self.history_path, self.history)

    def save_queue(self, queue_data):
        self.queue = queue_data
        self._save(self.queue_path, self.queue)

    def clear_history(self):
        self.history = []
        self._save(self.history_path, self.history)

# ============================================================================
# 2. WORKERS
# ============================================================================

def get_ytdlp_cmd():
    """Smartly returns the command to run yt-dlp (exe or python module)."""
    # 1. Check for standalone executable in PATH
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    
    # 2. Check for standalone executable in current dir
    local = os.path.join(os.getcwd(), "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
    if os.path.exists(local):
        return [local]
        
    # 3. Fallback: Run as Python Module (since user pip installed it)
    return [sys.executable, "-m", "yt_dlp"]

class UpdateWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, cmd_prefix):
        super().__init__()
        self.cmd_prefix = cmd_prefix

    def run(self):
        try:
            # Check if running as python module or exe
            if self.cmd_prefix[0] == sys.executable:
                # PIP UPDATE
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
            else:
                # EXE SELF-UPDATE
                cmd = self.cmd_prefix + ["-U"]
                
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
            
            if proc.returncode == 0:
                self.finished.emit(True, f"Update Result:\n{proc.stdout}")
            else:
                self.finished.emit(False, f"Update Failed:\n{proc.stderr}")
        except Exception as e:
            self.finished.emit(False, str(e))

class TestWorker(QThread):
    finished = Signal(bool, str, dict)

    def __init__(self, cmd_prefix, url, config):
        super().__init__()
        self.cmd_prefix = cmd_prefix
        self.url = url
        self.config = config

    def run(self):
        # V7: Use prefix list instead of single exe string
        cmd = self.cmd_prefix + ["--simulate", "--no-warnings", "--dump-json", self.url]
        
        if self.config.get('cookies') and self.config.get('cookies_file'):
            cmd += ["--cookies", self.config['cookies_file']]
        
        src = self.config.get('source', 'Normal')
        if src == "SPWN":
            cmd += ["--user-agent", "Mozilla/5.0... Firefox/142.0", "--referer", "https://spwn.jp/"]
        elif src == "YouTube":
            cmd += ["--user-agent", "Mozilla/5.0... AppleWebKit/537.36"]
        elif src == "Twitter":
            cmd += ["--add-header", "Referer:https://twitter.com/"]
        
        if self.config.get('proxy'): cmd += ["--proxy", self.config['proxy']]

        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            process = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
            if process.returncode == 0:
                self.finished.emit(True, "Access Granted", json.loads(process.stdout))
            else:
                self.finished.emit(False, f"Access Denied: {process.stderr[:200]}...", {})
        except Exception as e:
            self.finished.emit(False, str(e), {})

class DownloadWorker(QThread):
    progress_updated = Signal(float, str) 
    log_updated = Signal(str)
    status_changed = Signal(DownloadState)
    finished = Signal(bool, str, str) # success, msg, file_title

    def __init__(self, url, config):
        super().__init__()
        self.url = url 
        self.config = config
        self._is_running = True
        self.process = None

    def stop(self):
        self._is_running = False
        if self.process:
            if sys.platform == "win32": self.process.terminate()
            else: self.process.kill()
        self.wait()

    def run(self):
        self.status_changed.emit(DownloadState.PREPARING)
        
        # V7: Get robust command prefix
        yt_cmd = get_ytdlp_cmd()
        self.log_updated.emit(f"Using engine: {' '.join(yt_cmd)}")

        self.status_changed.emit(DownloadState.DOWNLOADING)
        cmd = self._build_command(yt_cmd, self.url)
        current_title = "Unknown"
        success = False

        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True,
                creationflags=creation_flags
            )

            for line in iter(self.process.stdout.readline, ''):
                if not self._is_running: 
                    self.process.terminate(); break
                line = line.strip()
                if not line: continue
                
                self.log_updated.emit(line)
                self._parse_progress(line)
                
                if "[download] Destination:" in line:
                    current_title = os.path.basename(line.split(":", 1)[1].strip())

            self.process.wait()
            success = (self.process.returncode == 0)
            
        except Exception as e:
            self.log_updated.emit(f"Error: {str(e)}")

        self.status_changed.emit(DownloadState.FINISHED if success else DownloadState.ERROR)
        self.finished.emit(success, "Completed" if success else "Failed", current_title)

    def _build_command(self, prefix, url):
        c = self.config
        cmd = prefix.copy() # Start with [python, -m, yt_dlp] or [yt-dlp]

        # Template
        tmpl = c.get('template', '%(title)s.%(ext)s')
        out_tmpl = os.path.join(c['path'], tmpl)
        cmd += ["-o", out_tmpl]
        
        # Archive & Recovery
        archive_file = os.path.join(c['path'], "archive.txt")
        cmd += ["--download-archive", archive_file]
        cmd += ["--ignore-errors", "--no-abort-on-error"]

        # Auth
        if c['cookies'] and c['cookies_file']:
            cmd += ["--cookies", c['cookies_file']]

        # Sources
        if c['source'] == "SPWN":
            cmd += ["--user-agent", "Mozilla/5.0...", "--referer", "https://spwn.jp/", "--hls-prefer-ffmpeg"]
        elif c['source'] == "YouTube":
            cmd += ["--user-agent", "Mozilla/5.0... AppleWebKit/537.36", "--extractor-args", "youtube:player_client=web"]
        elif c['source'] == "Twitter":
            cmd += ["--add-header", "Referer:https://twitter.com/"]
        elif c['source'] == "Bilibili":
            cmd += ["--referer", "https://www.bilibili.com/"]

        # Network
        if c.get('proxy'): cmd += ["--proxy", c['proxy']]
        if c.get('rate_limit'): cmd += ["--limit-rate", c['rate_limit']]

        # Format
        if c['format'] == 'mp3':
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", c['quality'].replace("k", "K")]
        else:
            if c['whole_file']: cmd += ["-f", "best"]
            else:
                if c['quality'] == 'best': cmd += ["-f", "bestvideo+bestaudio/best"]
                else: cmd += ["-f", f"bestvideo[height<={c['quality']}]+bestaudio/best"]
                if c['merge']: cmd += ["--merge-output-format", c['format']]

        if c['whole_file']: cmd += ["--no-part"]
        else: cmd += ["--buffer-size", "16K"]

        if c.get('playlist', False): cmd += ["--yes-playlist"]
        else: cmd += ["--no-playlist"]

        # Metadata & Subs
        if c['metadata']: cmd.append("--add-metadata")
        if c['thumbnail']: cmd.append("--embed-thumbnail")
        if c['subtitles']: 
            cmd.append("--embed-subs")
            if c.get('sub_langs'): cmd += ["--sub-langs", c['sub_langs']]
            else: cmd.append("--write-auto-sub")

        cmd += ["--concurrent-fragments", "4", "--retries", "10"]
        cmd.append(url)
        return cmd

    def _parse_progress(self, line):
        # Parses [download] 45.0% of 10.00MiB at 2.50MiB/s ETA 00:05
        match = re.search(r'\[download\]\s+(\d+\.\d+)%', line)
        if match:
            percent = float(match.group(1))
            speed = re.search(r'at\s+([0-9.]+\w+/s)', line)
            eta = re.search(r'ETA\s+([0-9:]+)', line)
            
            info = f"{percent}%"
            if speed: info += f" | {speed.group(1)}"
            if eta: info += f" | ETA {eta.group(1)}"
            
            self.progress_updated.emit(percent, info)

# ============================================================================
# 3. MAIN APP
# ============================================================================

class DownloaderApp(BaseApp):
    def __init__(self):
        super().__init__("Media Archiver", "download.png", "#FF5722")
        self.settings = QSettings("Ookami", "Downloader")
        self.data_manager = DataManager()
        self.worker = None
        self.test_worker = None
        self.update_worker = None
        
        # Queue System
        self.queue = self.data_manager.queue
        self.is_processing_queue = False
        self.queue_paused = False
        
        self._init_ui()
        self._load_settings()
        self._refresh_queue_table() 

    def _init_ui(self):
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 0; background: #1e1e2e; } 
            QTabBar::tab { background: #2b2b3b; color: #aaa; padding: 8px 15px; } 
            QTabBar::tab:selected { background: #FF5722; color: white; font-weight: bold; }
        """)
        
        self.tabs.addTab(self._create_download_tab(), "Single Download")
        self.tabs.addTab(self._create_queue_tab(), "Queue Manager")
        self.tabs.addTab(self._create_history_tab(), "History")
        self.tabs.addTab(self._create_settings_tab(), "Settings")
        self.content_layout.addWidget(self.tabs)

    def _create_download_tab(self):
        w = QWidget(); l = QVBoxLayout(w)
        
        # URL
        url_frame = QFrame(); url_frame.setStyleSheet("background: #252530; border-radius: 8px; padding: 10px;")
        ul = QVBoxLayout(url_frame)
        r1 = QHBoxLayout()
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText("Paste Video URL...")
        self.url_input.setStyleSheet("background: #111; color: white; border: 1px solid #444; padding: 8px;")
        btn_paste = QPushButton("Paste"); btn_paste.clicked.connect(self._paste_url)
        r1.addWidget(self.url_input); r1.addWidget(btn_paste)
        
        r2 = QHBoxLayout()
        self.combo_source = QComboBox(); self.combo_source.addItems(["Normal", "YouTube", "SPWN", "Twitter", "Bilibili"])
        self.chk_playlist = QCheckBox("Playlist"); self.chk_playlist.setToolTip("Process entire playlist")
        
        self.combo_preset = QComboBox(); self.combo_preset.addItems(PRESETS.keys())
        self.combo_preset.currentTextChanged.connect(self._apply_preset)
        
        btn_test = QPushButton("Test Access"); btn_test.clicked.connect(self.test_access)
        
        r2.addWidget(QLabel("Preset:")); r2.addWidget(self.combo_preset)
        r2.addWidget(QLabel("Source:")); r2.addWidget(self.combo_source)
        r2.addWidget(self.chk_playlist)
        r2.addStretch()
        r2.addWidget(btn_test)
        ul.addLayout(r1); ul.addLayout(r2)
        l.addWidget(url_frame)
        
        # Auth
        auth_grp = QGroupBox("Authentication"); auth_grp.setStyleSheet("color: #aaa; border: 1px solid #444; margin-top: 5px;")
        al = QHBoxLayout(auth_grp)
        self.chk_cookies = QCheckBox("Use Cookies"); self.chk_cookies.toggled.connect(lambda c: self.path_cookies.setEnabled(c))
        self.path_cookies = QLineEdit(); self.path_cookies.setPlaceholderText("cookies.txt path..."); self.path_cookies.setEnabled(False)
        btn_bc = QPushButton("Browse"); btn_bc.clicked.connect(self._browse_cookies)
        btn_help = QPushButton("Get Cookies"); btn_help.clicked.connect(self._open_cookie_help)
        al.addWidget(self.chk_cookies); al.addWidget(self.path_cookies); al.addWidget(btn_bc); al.addWidget(btn_help)
        l.addWidget(auth_grp)
        
        # Path & Opts
        pl = QHBoxLayout()
        self.path_input = QLineEdit(); self.path_input.setPlaceholderText("Output Folder...")
        btn_bp = QPushButton("📂"); btn_bp.clicked.connect(self._browse_folder)
        btn_open = QPushButton("Open"); btn_open.clicked.connect(self._open_folder)
        pl.addWidget(self.path_input); pl.addWidget(btn_bp); pl.addWidget(btn_open)
        l.addLayout(pl)
        
        opts = QFrame(); opts.setStyleSheet("background: #252530; border-radius: 8px; padding: 5px;")
        ol = QHBoxLayout(opts)
        self.combo_format = QComboBox(); self.combo_format.addItems(["mp4", "mp3", "m4a", "mkv"])
        self.combo_quality = QComboBox(); self.combo_quality.addItems(["best", "1080", "720", "480"])
        self.chk_meta = QCheckBox("Meta"); self.chk_meta.setChecked(True)
        self.chk_thumb = QCheckBox("Thumb"); self.chk_thumb.setChecked(True)
        self.chk_subs = QCheckBox("Subs") 
        ol.addWidget(QLabel("Fmt:")); ol.addWidget(self.combo_format)
        ol.addWidget(QLabel("Qual:")); ol.addWidget(self.combo_quality)
        ol.addWidget(self.chk_meta); ol.addWidget(self.chk_thumb); ol.addWidget(self.chk_subs)
        l.addWidget(opts)
        
        # Advanced (V6)
        adv_layout = QHBoxLayout()
        self.sub_lang = QLineEdit(); self.sub_lang.setPlaceholderText("Sub Langs (e.g. en,ja)...")
        adv_layout.addWidget(QLabel("Subs:"))
        adv_layout.addWidget(self.sub_lang)
        l.addLayout(adv_layout)
        
        # Actions
        al = QHBoxLayout()
        self.btn_dl = QPushButton("Start Download"); self.btn_dl.clicked.connect(self.start_download)
        self.btn_dl.setStyleSheet("background: #FF5722; color: white; padding: 10px; font-weight: bold;")
        self.btn_queue = QPushButton("Add to Queue"); self.btn_queue.clicked.connect(self.add_to_queue)
        
        self.btn_stop = QPushButton("Stop"); self.btn_stop.clicked.connect(self.stop_download); self.btn_stop.setEnabled(False)
        al.addWidget(self.btn_dl); al.addWidget(self.btn_queue); al.addWidget(self.btn_stop)
        l.addLayout(al)
        
        # Status
        self.pbar = QProgressBar(); self.pbar.setTextVisible(False); self.pbar.setStyleSheet("QProgressBar::chunk { background: #FF5722; }")
        self.status_lbl = QLabel("Ready")
        self.log_view = QTextBrowser(); self.log_view.setStyleSheet("background: #111; color: #0f0; font-family: Consolas; font-size: 10px;")
        l.addWidget(self.pbar); l.addWidget(self.status_lbl); l.addWidget(self.log_view)
        
        return w

    def _create_queue_tab(self):
        w = QWidget(); l = QVBoxLayout(w)
        
        # Controls
        ctrl_layout = QHBoxLayout()
        self.btn_startq = QPushButton("▶ Start Queue"); self.btn_startq.clicked.connect(self.process_queue)
        self.btn_startq.setStyleSheet("background: #FF5722; color: white; font-weight: bold;")
        self.btn_pauseq = QPushButton("⏸ Pause Queue"); self.btn_pauseq.clicked.connect(self.pause_queue); self.btn_pauseq.setEnabled(False)
        btn_clear = QPushButton("🗑️ Clear"); btn_clear.clicked.connect(self.clear_queue)
        
        # Scheduling (V6)
        self.time_edit = QTimeEdit(); self.time_edit.setDisplayFormat("HH:mm")
        btn_sched = QPushButton("⏰ Schedule"); btn_sched.clicked.connect(self.schedule_queue)
        
        # Import/Export (V6)
        btn_imp = QPushButton("Import"); btn_imp.clicked.connect(self.import_queue)
        btn_exp = QPushButton("Export"); btn_exp.clicked.connect(self.export_queue)
        
        ctrl_layout.addWidget(self.btn_startq); ctrl_layout.addWidget(self.btn_pauseq); ctrl_layout.addWidget(btn_clear)
        ctrl_layout.addSpacing(10)
        ctrl_layout.addWidget(self.time_edit); ctrl_layout.addWidget(btn_sched)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(btn_imp); ctrl_layout.addWidget(btn_exp)
        l.addLayout(ctrl_layout)
        
        # Table
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(3)
        self.queue_table.setHorizontalHeaderLabels(["URL", "Status", "Config"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.queue_table.setStyleSheet("QTableWidget { background: #222; color: #ddd; selection-background-color: #444; }")
        
        # Drag & Drop Reordering (V6)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.setDragEnabled(True)
        self.queue_table.setAcceptDrops(True)
        self.queue_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue_table.dropEvent = self._on_queue_drop # Hook for sync
        
        self.queue_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self._queue_menu)
        
        l.addWidget(self.queue_table)
        self.queue_status_lbl = QLabel("Queue Idle")
        l.addWidget(self.queue_status_lbl)
        
        # Timer for scheduler
        self.sched_timer = QTimer(self)
        self.sched_timer.timeout.connect(self._check_schedule)
        
        return w

    def _create_history_tab(self):
        w = QWidget(); l = QVBoxLayout(w)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Date", "Title", "Status", "Path"])
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self._history_menu)
        self.history_table.setStyleSheet("QTableWidget { background: #222; color: #ddd; }")
        
        btn_refresh = QPushButton("Refresh"); btn_refresh.clicked.connect(self._load_history)
        btn_clear = QPushButton("Clear History"); btn_clear.clicked.connect(self._clear_history)
        
        hl = QHBoxLayout(); hl.addWidget(btn_refresh); hl.addWidget(btn_clear)
        l.addWidget(self.history_table); l.addLayout(hl)
        return w

    def _create_settings_tab(self):
        w = QWidget(); l = QVBoxLayout(w)
        grp = QGroupBox("Network"); grp.setStyleSheet("color: white; border: 1px solid #444; margin-top: 10px;")
        gl = QVBoxLayout(grp)
        self.proxy_input = QLineEdit(); self.proxy_input.setPlaceholderText("http://user:pass@host:port")
        self.rate_input = QLineEdit(); self.rate_input.setPlaceholderText("e.g. 5M, 500K")
        gl.addWidget(QLabel("Proxy:")); gl.addWidget(self.proxy_input)
        gl.addWidget(QLabel("Speed Limit:")); gl.addWidget(self.rate_input)
        l.addWidget(grp)
        
        grp2 = QGroupBox("Advanced"); grp2.setStyleSheet("color: white; border: 1px solid #444;")
        gl2 = QVBoxLayout(grp2)
        self.chk_whole = QCheckBox("Force Whole File (No Fragments)")
        self.chk_merge = QCheckBox("Force Merge (MP4/MKV)"); self.chk_merge.setChecked(True)
        self.tpl_input = QLineEdit(); self.tpl_input.setText("%(title)s.%(ext)s"); self.tpl_input.setPlaceholderText("Output Template...")
        gl2.addWidget(self.chk_whole); gl2.addWidget(self.chk_merge)
        gl2.addWidget(QLabel("Filename Template:")); gl2.addWidget(self.tpl_input)
        
        # Update Button (V6)
        btn_upd = QPushButton("Check for Updates (yt-dlp)"); btn_upd.clicked.connect(self.update_ytdlp)
        gl2.addWidget(btn_upd)
        
        l.addWidget(grp2); l.addStretch()
        return w

    # --- QUEUE & SYNC (V6) ---
    def _on_queue_drop(self, event):
        """Syncs the internal queue list after a drag & drop reorder."""
        super(QTableWidget, self.queue_table).dropEvent(event)
        
        # Rebuild list from visual table
        new_queue = []
        for row in range(self.queue_table.rowCount()):
            # Recover data from UserRole
            item = self.queue_table.item(row, 0)
            data = item.data(Qt.UserRole)
            if data: new_queue.append(data)
            
        self.queue = new_queue
        self.data_manager.save_queue(self.queue)

    def import_queue(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import Queue", "", "JSON (*.json)")
        if f:
            try:
                with open(f, 'r') as file: new_q = json.load(file)
                self.queue.extend(new_q)
                self.data_manager.save_queue(self.queue)
                self._refresh_queue_table()
                QMessageBox.information(self, "Imported", f"Imported {len(new_q)} items.")
            except: QMessageBox.warning(self, "Error", "Invalid Queue File")

    def export_queue(self):
        f, _ = QFileDialog.getSaveFileName(self, "Export Queue", "", "JSON (*.json)")
        if f:
            with open(f, 'w') as file: json.dump(self.queue, file, indent=2)

    def schedule_queue(self):
        self.target_time = self.time_edit.time()
        self.sched_timer.start(1000)
        self.queue_status_lbl.setText(f"Scheduled for {self.target_time.toString()}")

    def _check_schedule(self):
        if QTime.currentTime().minute() == self.target_time.minute() and QTime.currentTime().hour() == self.target_time.hour():
            self.sched_timer.stop()
            self.process_queue()

    def update_ytdlp(self):
        # V7: Use smart command detection for updates too
        cmd = get_ytdlp_cmd()
        self.status_lbl.setText(f"Updating using: {' '.join(cmd)}...")
        self.update_worker = UpdateWorker(cmd)
        self.update_worker.finished.connect(lambda s, m: QMessageBox.information(self, "Update", m))
        self.update_worker.start()

    # --- STANDARD QUEUE LOGIC ---
    def add_to_queue(self):
        url = self.url_input.text().strip()
        if not url: return
        config = self._get_current_config()
        self.queue.append({'url': url, 'config': config, 'status': 'Pending'})
        self.data_manager.save_queue(self.queue)
        self._refresh_queue_table()
        self.url_input.clear()

    def process_queue(self):
        if self.is_processing_queue: return
        self.is_processing_queue = True
        self.queue_paused = False
        self.btn_startq.setEnabled(False)
        self.btn_pauseq.setEnabled(True)
        self.queue_status_lbl.setText("Queue Started...")
        self._process_next_queue_item()

    def pause_queue(self):
        self.queue_paused = True
        self.is_processing_queue = False
        self.btn_startq.setEnabled(True)
        self.btn_pauseq.setEnabled(False)
        self.queue_status_lbl.setText("Queue Paused")

    def _process_next_queue_item(self):
        if self.queue_paused: return

        idx = -1
        for i, item in enumerate(self.queue):
            if item['status'] == 'Pending':
                idx = i
                break
        
        if idx == -1:
            self.is_processing_queue = False
            self.btn_startq.setEnabled(True)
            self.btn_pauseq.setEnabled(False)
            self.queue_status_lbl.setText("Queue Finished")
            return

        self.queue[idx]['status'] = 'Processing...'
        self._refresh_queue_table()
        
        item = self.queue[idx]
        self.worker = DownloadWorker(item['url'], item['config'])
        self.worker.log_updated.connect(self.log_view.append)
        self.worker.progress_updated.connect(lambda p, m: (self.pbar.setValue(int(p)), self.status_lbl.setText(m)))
        
        def on_item_finish(success, msg, title):
            self.queue[idx]['status'] = 'Done' if success else 'Failed'
            self.data_manager.save_queue(self.queue)
            self._refresh_queue_table()
            self.data_manager.add_history(item['url'], title, "Success" if success else "Fail", item['config']['path'])
            self._load_history()
            self._process_next_queue_item()

        self.worker.finished.connect(on_item_finish)
        self.worker.start()

    def _refresh_queue_table(self):
        self.queue_table.setRowCount(len(self.queue))
        for r, item in enumerate(self.queue):
            # Store Full Data in UserRole for Drag/Drop Sync
            url_item = QTableWidgetItem(item['url'])
            url_item.setData(Qt.UserRole, item)
            self.queue_table.setItem(r, 0, url_item)
            
            status_item = QTableWidgetItem(item['status'])
            if item['status'] == "Done": status_item.setForeground(QBrush(QColor("#4CAF50")))
            elif item['status'] == "Failed": status_item.setForeground(QBrush(QColor("#F44336")))
            elif item['status'] == "Processing...": status_item.setForeground(QBrush(QColor("#2196F3")))
            
            self.queue_table.setItem(r, 1, status_item)
            self.queue_table.setItem(r, 2, QTableWidgetItem(f"{item['config']['format']}"))

    def clear_queue(self):
        self.queue = []
        self.data_manager.save_queue(self.queue)
        self._refresh_queue_table()

    def _queue_menu(self, pos):
        item = self.queue_table.itemAt(pos)
        if not item: return
        row = item.row()
        menu = QMenu()
        menu.setStyleSheet("QMenu { background: #222; color: white; }")
        act_remove = menu.addAction("❌ Remove from Queue")
        res = menu.exec(self.queue_table.mapToGlobal(pos))
        if res == act_remove:
            self.queue.pop(row)
            self.data_manager.save_queue(self.queue)
            self._refresh_queue_table()

    # --- SHARED LOGIC ---
    def _apply_preset(self, preset_name):
        if preset_name not in PRESETS: return
        p = PRESETS[preset_name]
        if 'format' in p: self.combo_format.setCurrentText(p['format'])
        if 'quality' in p: self.combo_quality.setCurrentText(p['quality'])
        if 'merge' in p: self.chk_merge.setChecked(p['merge'])
        if 'subs' in p: self.chk_subs.setChecked(p['subs'])
        if 'meta' in p: self.chk_meta.setChecked(p['meta'])
        if 'thumb' in p: self.chk_thumb.setChecked(p['thumb'])

    def _get_current_config(self):
        return {
            'path': self.path_input.text(),
            'format': self.combo_format.currentText(),
            'quality': self.combo_quality.currentText(),
            'metadata': self.chk_meta.isChecked(),
            'thumbnail': self.chk_thumb.isChecked(),
            'subtitles': self.chk_subs.isChecked(),
            'sub_langs': self.sub_lang.text(),
            'whole_file': self.chk_whole.isChecked(),
            'merge': self.chk_merge.isChecked(),
            'source': self.combo_source.currentText(),
            'cookies': self.chk_cookies.isChecked(),
            'cookies_file': self.path_cookies.text(),
            'playlist': self.chk_playlist.isChecked(),
            'proxy': self.proxy_input.text(),
            'rate_limit': self.rate_input.text(),
            'template': self.tpl_input.text()
        }

    def start_download(self):
        url = self.url_input.text().strip()
        if not url: return
        self._initiate_download(url)

    def _initiate_download(self, url):
        config = self._get_current_config()
        
        # LOGIC CHANGE: Auto-create path if missing
        if config['path'] and not os.path.exists(config['path']):
            try:
                os.makedirs(config['path'], exist_ok=True)
            except:
                QMessageBox.warning(self, "Error", "Invalid download folder.")
                return

        self.worker = DownloadWorker(url, config)
        self.worker.log_updated.connect(self.log_view.append)
        self.worker.progress_updated.connect(lambda p, m: (self.pbar.setValue(int(p)), self.status_lbl.setText(m)))
        self.worker.finished.connect(self._on_single_finish)
        
        self.btn_dl.setEnabled(False); self.btn_stop.setEnabled(True)
        self.log_view.clear()
        self.worker.start()

    def _on_single_finish(self, success, msg, title):
        self.btn_dl.setEnabled(True); self.btn_stop.setEnabled(False)
        self.pbar.setValue(100 if success else 0)
        self.status_lbl.setText(msg)
        self.data_manager.add_history(self.url_input.text(), title, "Success" if success else "Fail", self.path_input.text())
        self._load_history()
        QMessageBox.information(self, "Result", msg)

    # --- UTILS ---
    def _history_menu(self, pos):
        item = self.history_table.itemAt(pos)
        if not item: return
        row = item.row()
        if row < len(self.data_manager.history):
            h = self.data_manager.history[row]
            menu = QMenu()
            menu.setStyleSheet("QMenu { background: #222; color: white; }")
            act_open = menu.addAction("📂 Open Folder")
            act_copy = menu.addAction("🔗 Copy URL")
            res = menu.exec(self.history_table.mapToGlobal(pos))
            if res == act_open: QDesktopServices.openUrl(QUrl.fromLocalFile(h['path']))
            if res == act_copy: 
                from PySide6.QtGui import QGuiApplication
                QGuiApplication.clipboard().setText(h['url'])

    def _validate_cookie_file(self, path):
        if not os.path.exists(path): return False
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                header = f.read(512)
                return "# Netscape" in header or ".google.com" in header or ".youtube.com" in header
        except: return False

    def test_access(self):
        url = self.url_input.text().strip()
        if not url: return
        
        if self.chk_cookies.isChecked():
            cpath = self.path_cookies.text()
            if not self._validate_cookie_file(cpath):
                QMessageBox.warning(self, "Invalid Cookies", "File does not appear to be Netscape format.")
                return
        
        # Use Smart Cmd Logic
        cmd = get_ytdlp_cmd()
        
        config = self._get_current_config()
        self.test_worker = TestWorker(cmd, url, config)
        self.test_worker.finished.connect(lambda s, m, i: QMessageBox.information(self, "Access", f"{m}\n{i.get('title','')}") if s else QMessageBox.warning(self, "Fail", m))
        self.status_lbl.setText("Testing...")
        self.test_worker.start()

    def stop_download(self):
        if self.worker: self.worker.stop()
        self.log_view.append("🛑 Stopped.")
        self.btn_dl.setEnabled(True); self.btn_stop.setEnabled(False)

    def _browse_cookies(self):
        f, _ = QFileDialog.getOpenFileName(self, "Cookies", "", "Text (*.txt)")
        if f: self.path_cookies.setText(f)

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Folder")
        if d: self.path_input.setText(d)

    def _paste_url(self):
        from PySide6.QtGui import QGuiApplication
        self.url_input.setText(QGuiApplication.clipboard().text())

    def _open_folder(self):
        if os.path.isdir(self.path_input.text()):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path_input.text()))

    def _open_cookie_help(self):
        webbrowser.open("https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")

    def _load_history(self):
        data = self.data_manager.history
        self.history_table.setRowCount(len(data))
        for r, item in enumerate(data):
            self.history_table.setItem(r, 0, QTableWidgetItem(item['date']))
            self.history_table.setItem(r, 1, QTableWidgetItem(item['title']))
            self.history_table.setItem(r, 2, QTableWidgetItem(item['status']))
            self.history_table.setItem(r, 3, QTableWidgetItem(item['path']))

    def _clear_history(self):
        self.data_manager.clear_history()
        self._load_history()

    def _load_settings(self):
        lp = self.settings.value("last_path")
        
        # LOGIC CHANGE: Default to Mio_Downloads on Desktop
        if not lp: 
            desktop = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
            mio_dl = os.path.join(desktop, "Mio_Downloads")
            try:
                os.makedirs(mio_dl, exist_ok=True)
                lp = mio_dl
            except:
                lp = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        
        self.path_input.setText(lp)
        self.proxy_input.setText(self.settings.value("proxy", ""))
        self.rate_input.setText(self.settings.value("rate", ""))
        self._load_history()

    def closeEvent(self, event):
        self.settings.setValue("last_path", self.path_input.text())
        self.settings.setValue("proxy", self.proxy_input.text())
        self.settings.setValue("rate", self.rate_input.text())
        super().closeEvent(event)
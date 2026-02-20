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
                               QTableWidgetItem, QHeaderView, QMenu, QAbstractItemView, QTimeEdit, QDialog, QDateEdit)
from PySide6.QtCore import Qt, Signal, QThread, QSettings, QStandardPaths, QUrl, QTimer, QTime, QDate
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
    if shutil.which("yt-dlp"): return ["yt-dlp"]
    local = os.path.join(os.getcwd(), "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
    if os.path.exists(local): return [local]
    return [sys.executable, "-m", "yt_dlp"]

class CookieValidatorWorker(QThread):
    finished = Signal(bool, str)
    def __init__(self, cmd_prefix, cookie_path):
        super().__init__()
        self.cmd_prefix = cmd_prefix
        self.cookie_path = cookie_path
    def run(self):
        if not os.path.exists(self.cookie_path):
            self.finished.emit(False, "Cookie file not found")
            return
        cmd = self.cmd_prefix + [
            "--cookies", self.cookie_path,
            "--simulate", "--dump-json",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 
        ]
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
            if "Sign in" in proc.stderr: self.finished.emit(False, "Cookies Expired / Invalid")
            elif proc.returncode == 0: self.finished.emit(True, "Cookies Valid")
            else: self.finished.emit(False, f"Check Failed: {proc.stderr[:100]}")
        except Exception as e: self.finished.emit(False, str(e))

class ScrapeWorker(QThread):
    found_item = Signal(str, str) 
    finished = Signal(bool, str, int) 
    log_updated = Signal(str)

    def __init__(self, cmd_prefix, url, config, max_items=0):
        super().__init__()
        self.cmd_prefix = cmd_prefix
        self.url = url
        self.config = config
        self.max_items = max_items
        self._is_running = True
        self.process = None

    def run(self):
        cmd = self.cmd_prefix + [
            "--dump-json", 
            "--skip-download", 
            "--no-warnings",
            "--flat-playlist",
            "--ignore-errors"
        ]
        
        if self.max_items > 0: cmd += ["--playlist-end", str(self.max_items)]
        
        filters = []
        if self.config.get('ignore_shorts'): 
            filters.append("original_url!*=/shorts/ & url!*=/shorts/")
            
        if filters:
            match_string = " & ".join([f"({f})" for f in filters])
            cmd += ["--match-filter", match_string]
        
        if self.config.get('date_after'): cmd += ["--dateafter", self.config['date_after']]
        if self.config.get('date_before'): cmd += ["--datebefore", self.config['date_before']]

        if self.config.get('cookies') and self.config.get('cookies_file'):
            cmd += ["--cookies", self.config['cookies_file']]

        cmd.append(self.url)

        count = 0
        try:
            self.log_updated.emit(f"CMD: {' '.join(cmd)}")
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                text=True, creationflags=creation_flags
            )
            
            def read_stderr():
                for line in self.process.stderr:
                    if line.strip(): self.log_updated.emit(f"ERR: {line.strip()}")
            
            t_err = threading.Thread(target=read_stderr, daemon=True)
            t_err.start()
            
            for line in self.process.stdout:
                if not self._is_running: 
                    self.process.terminate()
                    break
                try:
                    data = json.loads(line)
                    url = data.get('url')
                    title = data.get('title', 'Unknown')
                    if url:
                        if "youtube" in self.url or len(url) == 11: 
                            if "://" not in url: url = f"https://www.youtube.com/watch?v={url}"
                        self.found_item.emit(url, title)
                        count += 1
                        if count % 10 == 0: self.log_updated.emit(f"Found {count} videos...")
                except: pass
            
            self.process.wait()
            t_err.join()
            
            if self.process.returncode == 0: self.finished.emit(True, "Scrape Complete", count)
            else: self.finished.emit(False, "Scrape Finished (with some errors)", count)

        except Exception as e:
            self.finished.emit(False, str(e), count)

    def stop(self):
        self._is_running = False
        if self.process:
            try: self.process.terminate()
            except: pass

class UpdateWorker(QThread):
    finished = Signal(bool, str)
    def __init__(self, cmd_prefix):
        super().__init__()
        self.cmd_prefix = cmd_prefix
    def run(self):
        try:
            if self.cmd_prefix[0] == sys.executable:
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
            else:
                cmd = self.cmd_prefix + ["-U"]
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
            if proc.returncode == 0: self.finished.emit(True, f"Update Result:\n{proc.stdout}")
            else: self.finished.emit(False, f"Update Failed:\n{proc.stderr}")
        except Exception as e: self.finished.emit(False, str(e))

class TestWorker(QThread):
    finished = Signal(bool, str, dict)
    def __init__(self, cmd_prefix, url, config):
        super().__init__()
        self.cmd_prefix = cmd_prefix
        self.url = url
        self.config = config
    def run(self):
        cmd = self.cmd_prefix + ["--simulate", "--no-warnings", "--dump-json", self.url]
        if self.config.get('cookies') and self.config.get('cookies_file'):
            cmd += ["--cookies", self.config['cookies_file']]
        src = self.config.get('source', 'Normal')
        if src == "SPWN": cmd += ["--user-agent", "Mozilla/5.0...", "--referer", "https://spwn.jp/", "--hls-prefer-ffmpeg"]
        elif src == "YouTube": cmd += ["--user-agent", "Mozilla/5.0..."]
        elif src == "Twitter": cmd += ["--add-header", "Referer:https://twitter.com/"]
        if self.config.get('proxy'): cmd += ["--proxy", self.config['proxy']]
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            process = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
            if process.returncode == 0: self.finished.emit(True, "Access Granted", json.loads(process.stdout))
            else: self.finished.emit(False, f"Access Denied: {process.stderr[:200]}...", {})
        except Exception as e: self.finished.emit(False, str(e), {})

class DownloadWorker(QThread):
    progress_updated = Signal(float, str) 
    log_updated = Signal(str)
    status_changed = Signal(DownloadState)
    finished = Signal(bool, str, str) # success, msg, error_detail

    def __init__(self, url, config):
        super().__init__()
        self.url = url 
        self.config = config
        self._is_running = True
        self.process = None
        self.error_buffer = []

    def stop(self):
        self._is_running = False
        if self.process:
            if sys.platform == "win32": self.process.terminate()
            else: self.process.kill()
        self.wait()

    def run(self):
        self.status_changed.emit(DownloadState.PREPARING)
        yt_cmd = get_ytdlp_cmd()
        self.log_updated.emit(f"Using engine: {' '.join(yt_cmd)}")
        self.status_changed.emit(DownloadState.DOWNLOADING)
        
        cmd = self._build_command(yt_cmd, self.url)
        current_title = "Unknown"
        success = False
        self.error_buffer = []

        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, universal_newlines=True,
                creationflags=creation_flags
            )
            
            def collect_stderr():
                for line in self.process.stderr:
                    if line.strip(): 
                        self.error_buffer.append(line.strip())
                        self.log_updated.emit(f"ERR: {line.strip()}")

            t_err = threading.Thread(target=collect_stderr, daemon=True)
            t_err.start()
            
            for line in iter(self.process.stdout.readline, ''):
                if not self._is_running: 
                    self.process.terminate()
                    break
                line = line.strip()
                if not line: continue
                self.log_updated.emit(line)
                self._parse_progress(line)
                if "[download] Destination:" in line:
                    current_title = os.path.basename(line.split(":", 1)[1].strip())

            self.process.wait()
            t_err.join() 
            success = (self.process.returncode == 0)
            
        except Exception as e: 
            self.log_updated.emit(f"Crit Error: {str(e)}")
            self.error_buffer.append(str(e))

        self.status_changed.emit(DownloadState.FINISHED if success else DownloadState.ERROR)
        
        status_text = "Completed"
        if not success:
            real_errors = [l for l in self.error_buffer if "WARNING" not in l and "frame=" not in l]
            if real_errors:
                err_raw = real_errors[-1]
                status_text = err_raw.replace("ERROR: ", "").replace("[youtube]", "").strip()[:50] 
            else:
                status_text = "Unknown Error (See Logs)"

        self.finished.emit(success, status_text, current_title)

    def _build_command(self, prefix, url):
        c = self.config
        cmd = prefix.copy()
        
        path_parts = []
        if c.get('org_channel'): path_parts.append("%(uploader)s")
        if c.get('separate_members'): path_parts.append("%(availability)s")
        if c.get('separate_streams') and c.get('separate_videos'):
            path_parts.append("%(was_live&Streams|Videos)s")
        elif c.get('separate_streams'): path_parts.append("%(was_live&Streams|)s")
        elif c.get('separate_videos'): path_parts.append("%(was_live&|Videos)s")
            
        if c.get('org_year'): path_parts.append("%(upload_date>%Y)s")
        if c.get('org_month'): path_parts.append("%(upload_date>%m)s")
        if c.get('org_week'): path_parts.append("Week_%(upload_date>%W)s")
            
        tmpl = c.get('template', '%(upload_date>%Y-%m-%d)s_%(title)s.%(ext)s')
        path_parts.append(tmpl)
        
        full_template = "/".join(path_parts)
        base_path = os.path.abspath(c['path'])
        out_path = os.path.join(base_path, full_template)
        
        self.log_updated.emit(f"📂 Saving to: {out_path}") 
        cmd += ["-o", out_path]
        
        archive_file = os.path.join(base_path, "archive.txt")
        cmd += ["--download-archive", archive_file]
        cmd += ["--ignore-errors", "--no-abort-on-error"]
        cmd += ["--retries", "infinite", "--fragment-retries", "infinite", "--retry-sleep", "fragment:exp=1:30"]
        
        is_single_video = bool(re.search(r'(youtube\.com/watch\?v=|youtu\.be/|shorts/)', url))
        
        if not is_single_video:
            filters = []
            if c.get('ignore_shorts'): filters.append("original_url!*=/shorts/ & url!*=/shorts/")
            ctype = c.get('content_filter', 'All')
            if ctype == "Uploaded Videos Only": filters.append("!is_live & !was_live")
            elif ctype == "Live Streams / VODs Only": filters.append("is_live | was_live")
            elif ctype == "Members/Premium Only": filters.append("availability=subscriber_only")
            
            if filters:
                match_string = " & ".join(filters)
                cmd += ["--match-filter", match_string]

        if c['cookies'] and c['cookies_file']: cmd += ["--cookies", c['cookies_file']]
        if c.get('proxy'): cmd += ["--proxy", c['proxy']]
        if c.get('rate_limit'): cmd += ["--limit-rate", c['rate_limit']]
        
        if not is_single_video:
            if c.get('date_after'): cmd += ["--dateafter", c['date_after']]
            if c.get('date_before'): cmd += ["--datebefore", c['date_before']]

        if c['format'] == 'mp3':
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", c['quality'].replace("k", "K")]
        else:
            if c['whole_file']: cmd += ["-f", "best"]
            else:
                # FIX: Handle Opus format incompatibility before merge
                audio_codec = "m4a" if c.get('audio_type') == "AAC (Safe)" else "bestaudio"
                if c['quality'] == 'best': 
                    cmd += ["-f", f"bestvideo+{audio_codec}/best"]
                else: 
                    cmd += ["-f", f"bestvideo[height<={c['quality']}]+{audio_codec}/best"]
                
                if c['merge']: cmd += ["--merge-output-format", c['format']]

        if c['whole_file']: cmd += ["--no-part"]
        else: cmd += ["--buffer-size", "16K"]

        if c.get('playlist', False): cmd += ["--yes-playlist"]
        else: cmd += ["--no-playlist"]

        if c['metadata']: cmd.append("--add-metadata")
        if c['thumbnail']: cmd.append("--embed-thumbnail")
        if c['subtitles']: 
            cmd.append("--embed-subs")
            if c.get('sub_langs'): cmd += ["--sub-langs", c['sub_langs']]
            else: cmd.append("--write-auto-sub")

        cmd += ["--concurrent-fragments", "4"]
        cmd.append(url)
        return cmd

    def _parse_progress(self, line):
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
        self.scrape_worker = None
        self.cookie_worker = None
        
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
        self.tabs.addTab(self._create_scraper_tab(), "Channel Scraper") 
        self.tabs.addTab(self._create_queue_tab(), "Queue Manager")
        self.tabs.addTab(self._create_history_tab(), "History")
        self.tabs.addTab(self._create_settings_tab(), "Settings")
        self.content_layout.addWidget(self.tabs)

    def _create_download_tab(self):
        w = QWidget(); l = QVBoxLayout(w)
        
        url_frame = QFrame(); url_frame.setStyleSheet("background: #252530; border-radius: 8px; padding: 10px;")
        ul = QVBoxLayout(url_frame)
        r1 = QHBoxLayout()
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText("Paste Video URL...")
        self.url_input.setStyleSheet("background: #111; color: white; border: 1px solid #444; padding: 8px;")
        btn_paste = QPushButton("Paste"); btn_paste.clicked.connect(self._paste_url)
        r1.addWidget(self.url_input); r1.addWidget(btn_paste)
        
        r2 = QHBoxLayout()
        self.combo_source = QComboBox(); self.combo_source.addItems(["Normal", "YouTube", "SPWN", "Twitter", "Bilibili"])
        self.chk_playlist = QCheckBox("Playlist") 
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
        
        opts = QFrame(); opts.setStyleSheet("background: #252530; border-radius: 8px; padding: 5px;")
        ol = QHBoxLayout(opts)
        self.combo_format = QComboBox(); self.combo_format.addItems(["mp4", "mp3", "m4a", "mkv"])
        self.combo_quality = QComboBox(); self.combo_quality.addItems(["best", "1080", "720", "480"])
        
        # FIX: Audio Selection for FFmpeg Merge
        self.combo_audio_type = QComboBox(); self.combo_audio_type.addItems(["AAC (Safe)", "Opus (Best)"])
        self.combo_audio_type.setToolTip("Choose AAC to fix 'Opus not supported' errors in some players.")
        
        self.chk_meta = QCheckBox("Meta"); self.chk_meta.setChecked(True)
        self.chk_thumb = QCheckBox("Thumb"); self.chk_thumb.setChecked(True)
        self.chk_subs = QCheckBox("Subs") 
        ol.addWidget(QLabel("Fmt:")); ol.addWidget(self.combo_format)
        ol.addWidget(QLabel("Qual:")); ol.addWidget(self.combo_quality)
        ol.addWidget(QLabel("Audio:")); ol.addWidget(self.combo_audio_type)
        ol.addWidget(self.chk_meta); ol.addWidget(self.chk_thumb); ol.addWidget(self.chk_subs)
        l.addWidget(opts)
        
        # Path
        pl = QHBoxLayout()
        self.path_input = QLineEdit(); self.path_input.setPlaceholderText("Output Folder...")
        btn_bp = QPushButton("📂"); btn_bp.clicked.connect(self._browse_folder)
        btn_open = QPushButton("Open Output Folder") 
        btn_open.setStyleSheet("background: #429AFF; color: white;")
        btn_open.clicked.connect(self._open_current_output_folder)
        pl.addWidget(self.path_input); pl.addWidget(btn_bp); pl.addWidget(btn_open)
        l.addLayout(pl)
        
        al = QHBoxLayout()
        self.btn_dl = QPushButton("Start Download"); self.btn_dl.clicked.connect(self.start_download)
        self.btn_dl.setStyleSheet("background: #FF5722; color: white; padding: 10px; font-weight: bold;")
        self.btn_queue = QPushButton("Add to Queue"); self.btn_queue.clicked.connect(self.add_to_queue)
        self.btn_stop = QPushButton("Stop"); self.btn_stop.clicked.connect(self.stop_download); self.btn_stop.setEnabled(False)
        al.addWidget(self.btn_dl); al.addWidget(self.btn_queue); al.addWidget(self.btn_stop)
        l.addLayout(al)
        
        self.pbar = QProgressBar(); self.pbar.setTextVisible(False); self.pbar.setStyleSheet("QProgressBar::chunk { background: #FF5722; }")
        self.status_lbl = QLabel("Ready")
        self.log_view = QTextBrowser(); self.log_view.setStyleSheet("background: #111; color: #0f0; font-family: Consolas; font-size: 10px;")
        l.addWidget(self.pbar); l.addWidget(self.status_lbl); l.addWidget(self.log_view)
        
        return w

    def _create_scraper_tab(self):
        w = QWidget(); l = QVBoxLayout(w)
        
        url_frame = QFrame(); url_frame.setStyleSheet("background: #252530; border-radius: 8px; padding: 10px;")
        ul = QHBoxLayout(url_frame)
        self.scrape_url = QLineEdit(); self.scrape_url.setPlaceholderText("Channel / Playlist URL to Scrape...")
        self.scrape_url.setStyleSheet("background: #111; color: white; border: 1px solid #444; padding: 8px;")
        self.btn_scrape = QPushButton("🕵️ Scrape to Queue")
        self.btn_scrape.clicked.connect(self.scrape_to_queue)
        self.btn_scrape.setStyleSheet("background: #2196F3; color: white; padding: 8px;")
        self.btn_stop_scrape = QPushButton("🛑 Stop")
        self.btn_stop_scrape.clicked.connect(self.stop_scrape)
        self.btn_stop_scrape.setStyleSheet("background: #f44336; color: white; padding: 8px;")
        
        ul.addWidget(self.scrape_url); ul.addWidget(self.btn_scrape); ul.addWidget(self.btn_stop_scrape)
        l.addWidget(url_frame)
        
        filt_grp = QGroupBox("Content Filters")
        filt_grp.setStyleSheet("color: #aaa; border: 1px solid #444;")
        fl = QHBoxLayout(filt_grp)
        self.combo_content = QComboBox()
        self.combo_content.addItems(["All Content", "Uploaded Videos Only", "Live Streams / VODs Only", "Members/Premium Only"])
        self.chk_ignore_shorts = QCheckBox("Ignore Shorts")
        self.spin_max_items = QLineEdit("0"); self.spin_max_items.setPlaceholderText("Limit (0=All)")
        self.spin_max_items.setFixedWidth(60)
        fl.addWidget(QLabel("Fetch:")); fl.addWidget(self.combo_content)
        fl.addWidget(self.chk_ignore_shorts)
        fl.addWidget(QLabel("Limit:")); fl.addWidget(self.spin_max_items)
        l.addWidget(filt_grp)
        
        batch_grp = QGroupBox("Download Settings for this Batch")
        batch_grp.setStyleSheet("color: #aaa; border: 1px solid #444;")
        bl = QHBoxLayout(batch_grp)
        self.batch_fmt = QComboBox(); self.batch_fmt.addItems(["mp4", "mp3", "m4a", "mkv"])
        self.batch_qual = QComboBox(); self.batch_qual.addItems(["best", "1080", "720", "480"])
        self.batch_meta = QCheckBox("Meta"); self.batch_meta.setChecked(True)
        self.batch_thumb = QCheckBox("Thumb"); self.batch_thumb.setChecked(True)
        self.batch_subs = QCheckBox("Subs")
        bl.addWidget(QLabel("Fmt:")); bl.addWidget(self.batch_fmt)
        bl.addWidget(QLabel("Qual:")); bl.addWidget(self.batch_qual)
        bl.addWidget(self.batch_meta); bl.addWidget(self.batch_thumb); bl.addWidget(self.batch_subs)
        l.addWidget(batch_grp)
        
        org_grp = QGroupBox("Folder Organization"); org_grp.setStyleSheet("color: #aaa; border: 1px solid #444;")
        ol = QVBoxLayout(org_grp)
        row_org = QHBoxLayout()
        self.chk_org_channel = QCheckBox("Channel Name") 
        self.chk_org_year = QCheckBox("Year"); self.chk_org_month = QCheckBox("Month"); self.chk_org_week = QCheckBox("Week")
        row_org.addWidget(QLabel("Sub-folders:")); 
        row_org.addWidget(self.chk_org_channel)
        row_org.addWidget(self.chk_org_year); row_org.addWidget(self.chk_org_month); row_org.addWidget(self.chk_org_week); row_org.addStretch()
        
        row_sep = QHBoxLayout()
        self.chk_sep_streams = QCheckBox("Separate Streams")
        self.chk_sep_videos = QCheckBox("Separate Videos")
        self.chk_sep_members = QCheckBox("Separate Members Only")
        row_sep.addWidget(self.chk_sep_streams); row_sep.addWidget(self.chk_sep_videos); row_sep.addWidget(self.chk_sep_members); row_sep.addStretch()
        ol.addLayout(row_org); ol.addLayout(row_sep)
        l.addWidget(org_grp)
        
        d_grp = QHBoxLayout()
        self.date_after = QLineEdit(); self.date_after.setPlaceholderText("Date After (YYYYMMDD)")
        self.date_before = QLineEdit(); self.date_before.setPlaceholderText("Date Before (YYYYMMDD)")
        d_grp.addWidget(QLabel("Date Range:")); d_grp.addWidget(self.date_after); d_grp.addWidget(self.date_before)
        l.addLayout(d_grp)
        
        l.addWidget(QLabel("Filename Template:"))
        self.tpl_input = QLineEdit(); self.tpl_input.setText("%(upload_date>%Y-%m-%d)s_%(title)s.%(ext)s")
        l.addWidget(self.tpl_input)
        
        self.scraper_log = QTextBrowser()
        self.scraper_log.setStyleSheet("background: #111; color: #00FF00; font-family: Consolas; font-size: 10px;")
        l.addWidget(QLabel("Scraper Output:"))
        l.addWidget(self.scraper_log)
        
        return w

    def _create_queue_tab(self):
        w = QWidget(); l = QVBoxLayout(w)
        stats_frame = QFrame(); stats_frame.setStyleSheet("background: #252530; padding: 5px; border-radius: 5px;")
        sl = QHBoxLayout(stats_frame)
        self.lbl_queue_progress = QLabel("Batch Progress:")
        self.bar_queue_progress = QProgressBar(); self.bar_queue_progress.setTextVisible(True)
        self.bar_queue_progress.setStyleSheet("QProgressBar::chunk { background: #4CAF50; }")
        sl.addWidget(self.lbl_queue_progress); sl.addWidget(self.bar_queue_progress)
        l.addWidget(stats_frame)
        
        ctrl_layout = QHBoxLayout()
        self.btn_startq = QPushButton("▶ Start Queue"); self.btn_startq.clicked.connect(self.process_queue)
        self.btn_startq.setStyleSheet("background: #FF5722; color: white; font-weight: bold;")
        self.btn_pauseq = QPushButton("⏸ Pause Queue"); self.btn_pauseq.clicked.connect(self.pause_queue); self.btn_pauseq.setEnabled(False)
        btn_clear = QPushButton("🗑️ Clear"); btn_clear.clicked.connect(self.clear_queue)
        
        ctrl_layout.addWidget(self.btn_startq); ctrl_layout.addWidget(self.btn_pauseq); ctrl_layout.addWidget(btn_clear)
        l.addLayout(ctrl_layout)
        
        self.queue_table = QTableWidget(); self.queue_table.setColumnCount(3)
        self.queue_table.setHorizontalHeaderLabels(["URL", "Status", "Config"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.queue_table.setStyleSheet("QTableWidget { background: #222; color: #ddd; selection-background-color: #444; }")
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.queue_table.setDragEnabled(True)
        self.queue_table.setAcceptDrops(True); self.queue_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue_table.dropEvent = self._on_queue_drop
        self.queue_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self._queue_menu)
        l.addWidget(self.queue_table)
        self.queue_status_lbl = QLabel("Queue Idle"); l.addWidget(self.queue_status_lbl)
        self.sched_timer = QTimer(self); self.sched_timer.timeout.connect(self._check_schedule)
        return w

    def _create_history_tab(self):
        w = QWidget(); l = QVBoxLayout(w)
        self.history_table = QTableWidget(); self.history_table.setColumnCount(4)
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
        auth_grp = QGroupBox("Authentication & Cookies"); auth_grp.setStyleSheet("color: white; border: 1px solid #444;")
        al = QVBoxLayout(auth_grp)
        arow = QHBoxLayout()
        self.chk_cookies = QCheckBox("Use Cookies"); self.chk_cookies.toggled.connect(lambda c: self.path_cookies.setEnabled(c))
        self.path_cookies = QLineEdit(); self.path_cookies.setPlaceholderText("cookies.txt path..."); self.path_cookies.setEnabled(False)
        btn_bc = QPushButton("📂"); btn_bc.clicked.connect(self._browse_cookies)
        arow.addWidget(self.chk_cookies); arow.addWidget(self.path_cookies); arow.addWidget(btn_bc)
        brow = QHBoxLayout()
        btn_val = QPushButton("🍪 Validate Cookies"); btn_val.clicked.connect(self.validate_cookies)
        btn_get = QPushButton("Get New Cookies"); btn_get.clicked.connect(self._open_cookie_help)
        brow.addWidget(btn_val); brow.addWidget(btn_get)
        al.addLayout(arow); al.addLayout(brow)
        l.addWidget(auth_grp)
        
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
        gl2.addWidget(self.chk_whole); gl2.addWidget(self.chk_merge)
        self.sub_lang = QLineEdit(); self.sub_lang.setPlaceholderText("Sub Langs (e.g. en,ja)...")
        gl2.addWidget(QLabel("Global Subtitles:")); gl2.addWidget(self.sub_lang)
        
        btn_upd = QPushButton("Check for Updates (yt-dlp)"); btn_upd.clicked.connect(self.update_ytdlp)
        gl2.addWidget(btn_upd)
        l.addWidget(grp2); l.addStretch()
        return w

    # --- HELPERS ---
    def _open_current_output_folder(self):
        path = self.path_input.text()
        if not path or not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except:
                path = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
        
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # --- SCRAPE HELPER ---
    def _get_scraper_config(self):
        return {
            'path': self.path_input.text(),
            'format': self.batch_fmt.currentText(),
            'quality': self.batch_qual.currentText(),
            'audio_type': self.combo_audio_type.currentText(), # Inherit from single tab
            'metadata': self.batch_meta.isChecked(),
            'thumbnail': self.batch_thumb.isChecked(),
            'subtitles': self.batch_subs.isChecked(),
            'sub_langs': self.sub_lang.text(),
            'whole_file': self.chk_whole.isChecked(),
            'merge': self.chk_merge.isChecked(),
            'source': "Normal",
            'cookies': self.chk_cookies.isChecked(),
            'cookies_file': self.path_cookies.text(),
            'playlist': False, 
            'proxy': self.proxy_input.text(),
            'rate_limit': self.rate_input.text(),
            'template': self.tpl_input.text(),
            'date_after': self.date_after.text(),
            'date_before': self.date_before.text(),
            'ignore_shorts': self.chk_ignore_shorts.isChecked(),
            
            'org_channel': self.chk_org_channel.isChecked(),
            'org_year': self.chk_org_year.isChecked(),
            'org_month': self.chk_org_month.isChecked(),
            'org_week': self.chk_org_week.isChecked(),
            'separate_streams': self.chk_sep_streams.isChecked(),
            'separate_videos': self.chk_sep_videos.isChecked(),
            'separate_members': self.chk_sep_members.isChecked(),
            'content_filter': self.combo_content.currentText() 
        }

    def scrape_to_queue(self):
        url = self.scrape_url.text().strip()
        if not url: return
        
        config = self._get_scraper_config()
        if config.get('content_filter') == "Members/Premium Only":
            if "youtube.com" in url and "/membership" not in url and "list=" not in url:
                if url.endswith("/"): url += "membership"
                else: url += "/membership"
                self.scraper_log.append(f"🔒 Members Mode: Auto-redirecting to {url}")

        cmd = get_ytdlp_cmd()
        try: limit = int(self.spin_max_items.text())
        except: limit = 0
        
        self.scraper_log.clear()
        self.scraper_log.append(f"🚀 Started Fast Scrape for: {url}")
        self.btn_scrape.setEnabled(False)
        self.btn_stop_scrape.setEnabled(True)
        self.status_lbl.setText("Scraping Channel...")
        self.pbar.setRange(0, 0)
        
        self.scrape_worker = ScrapeWorker(cmd, url, config, limit)
        self.scrape_worker.found_item.connect(self._on_scrape_item_found)
        self.scrape_worker.finished.connect(self._on_scrape_finished)
        self.scrape_worker.log_updated.connect(self.scraper_log.append)
        self.scrape_worker.start()

    def stop_scrape(self):
        if self.scrape_worker:
            self.scrape_worker.stop()
            self.scraper_log.append("🛑 Stopping Scraper...")

    def _on_scrape_item_found(self, url, title):
        config = self._get_scraper_config()
        self.queue.append({'url': url, 'config': config, 'status': 'Pending'})
        self.scraper_log.append(f"Found: {title}")

    def _on_scrape_finished(self, success, msg, count):
        self.btn_scrape.setEnabled(True)
        self.btn_stop_scrape.setEnabled(False)
        self.pbar.setRange(0, 100); self.pbar.setValue(100)
        self.status_lbl.setText(msg)
        self.data_manager.save_queue(self.queue)
        self._refresh_queue_table()
        self._update_queue_stats()
        
        self.scraper_log.append(f"--- Finished: Found {count} items ---")
        
        if success:
            res = QMessageBox.question(self, "Scrape Done", f"Found {count} videos.\nGo to Queue tab?", QMessageBox.Yes | QMessageBox.No)
            if res == QMessageBox.Yes: self.tabs.setCurrentIndex(2)
        else:
            QMessageBox.warning(self, "Scrape Issue", msg)

    # --- COOKIE VALIDATION ---
    def validate_cookies(self):
        path = self.path_cookies.text()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Select a valid cookie file first.")
            return
        cmd = get_ytdlp_cmd()
        self.cookie_worker = CookieValidatorWorker(cmd, path)
        self.cookie_worker.finished.connect(lambda ok, msg: QMessageBox.information(self, "Result", msg) if ok else QMessageBox.warning(self, "Invalid", msg))
        self.cookie_worker.start()

    # --- QUEUE & SYNC ---
    def _update_queue_stats(self):
        total = len(self.queue)
        if total == 0:
            self.bar_queue_progress.setValue(0)
            self.lbl_queue_progress.setText("Queue Empty")
            return
        done = sum(1 for item in self.queue if item['status'] in ['Done', 'Failed'] or "Failed" in str(item['status']))
        pct = int((done / total) * 100)
        self.bar_queue_progress.setValue(pct)
        self.lbl_queue_progress.setText(f"Batch Progress: {done}/{total} ({pct}%)")

    def _on_queue_drop(self, event):
        super(QTableWidget, self.queue_table).dropEvent(event)
        new_queue = []
        for row in range(self.queue_table.rowCount()):
            item = self.queue_table.item(row, 0)
            data = item.data(Qt.UserRole)
            if data: new_queue.append(data)
        self.queue = new_queue
        self.data_manager.save_queue(self.queue)
        self._update_queue_stats()

    def import_queue(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import Queue", "", "JSON (*.json)")
        if f:
            try:
                with open(f, 'r') as file: new_q = json.load(file)
                self.queue.extend(new_q)
                self.data_manager.save_queue(self.queue)
                self._refresh_queue_table()
                self._update_queue_stats()
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
        self._update_queue_stats()
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
        
        try:
            if not os.path.exists(item['config']['path']):
                os.makedirs(item['config']['path'], exist_ok=True)
        except: pass

        self.worker = DownloadWorker(item['url'], item['config'])
        self.worker.log_updated.connect(self.log_view.append)
        self.worker.progress_updated.connect(lambda p, m: (self.pbar.setValue(int(p)), self.status_lbl.setText(m)))
        
        def on_item_finish(success, msg, title, error_detail=""):
            status_text = 'Done' if success else f'{msg}' 
            self.queue[idx]['status'] = status_text
            self.data_manager.save_queue(self.queue)
            self._refresh_queue_table()
            self._update_queue_stats()
            self.data_manager.add_history(item['url'], title, "Success" if success else "Fail", item['config']['path'])
            self._load_history()
            self._process_next_queue_item()

        self.worker.finished.connect(on_item_finish)
        self.worker.start()

    def _refresh_queue_table(self):
        self.queue_table.setRowCount(len(self.queue))
        for r, item in enumerate(self.queue):
            url_item = QTableWidgetItem(item['url'])
            url_item.setData(Qt.UserRole, item)
            self.queue_table.setItem(r, 0, url_item)
            
            status_text = item['status']
            status_item = QTableWidgetItem(status_text)
            
            if "Done" in status_text: status_item.setForeground(QBrush(QColor("#4CAF50")))
            elif "Failed" in status_text or "Error" in status_text: 
                status_item.setForeground(QBrush(QColor("#F44336")))
                status_item.setToolTip(status_text)
            elif "Processing" in status_text: status_item.setForeground(QBrush(QColor("#2196F3")))
            
            self.queue_table.setItem(r, 1, status_item)
            self.queue_table.setItem(r, 2, QTableWidgetItem(f"{item['config']['format']}"))

    def clear_queue(self):
        self.queue = []
        self.data_manager.save_queue(self.queue)
        self._refresh_queue_table()
        self._update_queue_stats()

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
            self._update_queue_stats()

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
            'audio_type': self.combo_audio_type.currentText(), # Manual selection
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
            'template': self.tpl_input.text(),
            'date_after': self.date_after.text(),
            'date_before': self.date_before.text(),
            'ignore_shorts': self.chk_ignore_shorts.isChecked(),
            
            'org_channel': self.chk_org_channel.isChecked(),
            'org_year': self.chk_org_year.isChecked(),
            'org_month': self.chk_org_month.isChecked(),
            'org_week': self.chk_org_week.isChecked(),
            'separate_streams': self.chk_sep_streams.isChecked(),
            'separate_videos': self.chk_sep_videos.isChecked(),
            'separate_members': self.chk_sep_members.isChecked(),
            'content_filter': self.combo_content.currentText() 
        }

    def start_download(self):
        url = self.url_input.text().strip()
        if not url: return
        self._initiate_download(url)

    def _initiate_download(self, url):
        config = self._get_current_config()
        if config['path'] and not os.path.exists(config['path']):
            try: os.makedirs(config['path'], exist_ok=True)
            except: QMessageBox.warning(self, "Error", "Invalid folder."); return

        self.worker = DownloadWorker(url, config)
        self.worker.log_updated.connect(self.log_view.append)
        self.worker.progress_updated.connect(lambda p, m: (self.pbar.setValue(int(p)), self.status_lbl.setText(m)))
        self.worker.finished.connect(self._on_single_finish)
        
        self.btn_dl.setEnabled(False); self.btn_stop.setEnabled(True)
        self.log_view.clear()
        self.worker.start()

    def _on_single_finish(self, success, msg, title, error_detail=""):
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
        if not lp or not os.path.exists(lp):
            desktop = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
            lp = os.path.join(desktop, "Mio_Downloads")
            try: os.makedirs(lp, exist_ok=True)
            except: lp = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        
        self.path_input.setText(lp)
        self.proxy_input.setText(self.settings.value("proxy", ""))
        self.rate_input.setText(self.settings.value("rate", ""))
        self.date_after.setText(self.settings.value("date_after", ""))
        self.date_before.setText(self.settings.value("date_before", ""))
        self.chk_ignore_shorts.setChecked(self.settings.value("ignore_shorts", False, type=bool))
        
        self.chk_org_channel.setChecked(self.settings.value("org_channel", True, type=bool))
        self.chk_org_year.setChecked(self.settings.value("org_year", True, type=bool))
        self.chk_org_month.setChecked(self.settings.value("org_month", True, type=bool))
        self.chk_org_week.setChecked(self.settings.value("org_week", True, type=bool))
        self.chk_sep_streams.setChecked(self.settings.value("org_separate_streams", True, type=bool))
        self.chk_sep_videos.setChecked(self.settings.value("org_separate_videos", True, type=bool))
        self.chk_sep_members.setChecked(self.settings.value("org_separate_members", True, type=bool))
        
        self.tpl_input.setText(self.settings.value("template", "%(upload_date>%Y-%m-%d)s_%(title)s.%(ext)s"))
        self.combo_content.setCurrentText(self.settings.value("content_filter", "All Content"))
        
        # FIX: Persistent Audio Setting
        self.combo_audio_type.setCurrentText(self.settings.value("audio_type", "AAC (Safe)"))
        
        self._load_history()

    def closeEvent(self, event):
        self.settings.setValue("last_path", self.path_input.text())
        self.settings.setValue("proxy", self.proxy_input.text())
        self.settings.setValue("rate", self.rate_input.text())
        self.settings.setValue("date_after", self.date_after.text())
        self.settings.setValue("date_before", self.date_before.text())
        self.settings.setValue("ignore_shorts", self.chk_ignore_shorts.isChecked())
        
        self.settings.setValue("org_channel", self.chk_org_channel.isChecked())
        self.settings.setValue("org_year", self.chk_org_year.isChecked())
        self.settings.setValue("org_month", self.chk_org_month.isChecked())
        self.settings.setValue("org_week", self.chk_org_week.isChecked())
        
        self.settings.setValue("org_separate_streams", self.chk_sep_streams.isChecked())
        self.settings.setValue("org_separate_videos", self.chk_sep_videos.isChecked())
        self.settings.setValue("org_separate_members", self.chk_sep_members.isChecked())
        
        self.settings.setValue("template", self.tpl_input.text())
        self.settings.setValue("content_filter", self.combo_content.currentText())
        
        # FIX: Persistent Audio Setting
        self.settings.setValue("audio_type", self.combo_audio_type.currentText())
        
        self.stop_scrape() 
        super().closeEvent(event)
import os
import datetime
import time
import random
import json
import uuid 
import subprocess
import shutil
import tempfile
import re
from enum import Enum

from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit, QPushButton, 
                               QLabel, QFrame, QWidget, QComboBox, QCheckBox, QSplitter, 
                               QFileDialog, QProgressBar, QSizePolicy, QSlider, QMenu, QToolButton,
                               QMessageBox, QTabWidget, QRadioButton, QButtonGroup)
from PySide6.QtCore import (Qt, Signal, QThread, QObject, QTimer, QSize, QMutex, 
                            QWaitCondition, QSettings, QStandardPaths, QUrl)
from PySide6.QtGui import (QFont, QTextCursor, QColor, QPalette, QIcon, QAction, 
                           QKeySequence, QShortcut, QTextCharFormat, QDesktopServices, QTextDocument)

from .base import BaseApp

# --- LIBRARIES CHECK ---
try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

try:
    import whisper
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

# --- GLOBAL MODEL CACHE ---
_WHISPER_MODEL = None

def get_whisper_model():
    """Loads the model once and caches it globally."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None and HAS_WHISPER:
        _WHISPER_MODEL = whisper.load_model("base")
    return _WHISPER_MODEL

# ============================================================================
# 1. PLUGIN SYSTEM
# ============================================================================

class PluginManager:
    def __init__(self):
        self.plugins = []

    def load_plugin(self, path):
        name = os.path.basename(path).replace(".py", "")
        if name not in self.plugins:
            self.plugins.append(name)
            return True
        return False

    def get_active_plugins(self):
        return self.plugins

# ============================================================================
# 2. STREAM WORKER (DUAL MODE: LIVE & VOD)
# ============================================================================

class StreamState(Enum):
    IDLE = 0
    CONNECTING = 1
    LISTENING = 2
    PROCESSING_VOD = 3
    PAUSED = 4
    RETRYING = 5
    ERROR = 6

class StreamWorker(QThread):
    status_changed = Signal(StreamState, str)
    transcript_ready = Signal(str, str, float) # (text, timestamp_str, seconds_elapsed)
    translation_ready = Signal(str, str) 
    audio_level = Signal(int) 
    error_occurred = Signal(str)
    system_log = Signal(str) 
    title_found = Signal(str)
    progress_update = Signal(int) # For VOD mode

    def __init__(self, url, config):
        super().__init__()
        self.url = url
        self.config = config 
        
        self._is_running = True
        self._is_paused = False
        self._start_time = 0
        self.stream_url = None
        self.stream_title = "Unknown_Stream"
        
        self.mutex = QMutex()
        self.cond = QWaitCondition()

    def set_gain(self, value): self.config['gain'] = value
    def set_volume(self, value): self.config['volume'] = value

    def pause(self):
        self.mutex.lock()
        if not self._is_paused:
            self._is_paused = True
            self.status_changed.emit(StreamState.PAUSED, "Paused")
        self.mutex.unlock()

    def resume(self):
        self.mutex.lock()
        if self._is_paused:
            self._is_paused = False
            self.cond.wakeAll()
            self.status_changed.emit(StreamState.LISTENING, "Resuming...")
        self.mutex.unlock()

    def stop(self):
        self.mutex.lock()
        self._is_running = False
        self.cond.wakeAll()
        self.mutex.unlock()
        self.wait()

    def run(self):
        # 1. Dependency Check
        if not HAS_YTDLP or not HAS_WHISPER:
            self.status_changed.emit(StreamState.ERROR, "Missing Libraries")
            self.system_log.emit("❌ Install: pip install yt-dlp openai-whisper deep-translator")
            return

        if not shutil.which("ffmpeg"):
            self.status_changed.emit(StreamState.ERROR, "Missing FFmpeg")
            self.system_log.emit("❌ Critical: FFmpeg not found in PATH.")
            return

        # 2. Load Model
        self.status_changed.emit(StreamState.CONNECTING, "Loading AI...")
        try:
            model = get_whisper_model()
            if not model: raise Exception("Model failed to load")
            self.system_log.emit("✅ Whisper AI Ready.")
        except Exception as e:
            self.status_changed.emit(StreamState.ERROR, "AI Init Failed")
            self.system_log.emit(f"❌ Whisper Error: {e}")
            return

        # 3. Get Stream Info
        self.status_changed.emit(StreamState.CONNECTING, "Fetching Info...")
        try:
            ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                self.stream_url = info['url']
                self.stream_title = info.get('title', 'Live Stream')
                self.title_found.emit(self.stream_title)
                self.system_log.emit(f"✅ Found: {self.stream_title}")
        except Exception as e:
            self.status_changed.emit(StreamState.ERROR, "Link Error")
            self.system_log.emit(f"❌ yt-dlp Error: {e}")
            return

        # 4. Routing based on Mode
        if self.config.get('mode') == 'video':
            self._process_vod(model)
        else:
            self._process_live(model)

    def _process_vod(self, model):
        """Downloads full audio and processes it as a whole for max accuracy."""
        self.status_changed.emit(StreamState.PROCESSING_VOD, "Downloading Audio...")
        self.system_log.emit("📥 Downloading full VOD audio for high-accuracy processing...")
        
        temp_dir = tempfile.gettempdir()
        audio_file = os.path.join(temp_dir, f"mio_vod_{uuid.uuid4().hex}.wav")
        
        try:
            # Download/Convert to WAV
            cmd = [
                'ffmpeg', '-i', self.stream_url,
                '-vn', '-ac', '1', '-ar', '16000', '-f', 'wav', '-y',
                '-loglevel', 'error',
                audio_file
            ]
            subprocess.run(cmd, check=True)
            
            self.status_changed.emit(StreamState.PROCESSING_VOD, "Transcribing VOD...")
            self.system_log.emit("🧠 Audio downloaded. Starting full transcription (this may take time)...")
            
            # Run Whisper on the whole file
            # Detect language setting
            src_lang = self.config.get('source_lang')
            if src_lang == "auto": src_lang = None # Let Whisper detect
            
            result = model.transcribe(audio_file, fp16=False, language=src_lang, verbose=False)
            
            self.system_log.emit("✅ Transcription complete. Processing segments...")
            
            # Process segments
            target_lang = self.config.get('target_lang', 'en')
            translator = GoogleTranslator(source='auto', target=target_lang)
            
            for segment in result['segments']:
                if not self._is_running: break
                
                start = segment['start']
                text = segment['text'].strip()
                timestamp = self._seconds_to_timestamp(start)
                
                # Emit Original
                self.transcript_ready.emit(text, timestamp, start)
                self._write_log(timestamp, "SRC", text)
                
                # Translate
                if self.config.get('translate') and HAS_TRANSLATOR:
                    try:
                        trans = translator.translate(text)
                        self.translation_ready.emit(trans, timestamp)
                        self._write_log(timestamp, f"TRN-{target_lang}", trans)
                    except: pass
                
                # Small delay to not freeze UI with flood of signals
                time.sleep(0.01)
                
            self.status_changed.emit(StreamState.IDLE, "VOD Finished")
            self.system_log.emit("✅ VOD Processing Complete.")

        except Exception as e:
            self.status_changed.emit(StreamState.ERROR, "VOD Error")
            self.system_log.emit(f"❌ VOD Error: {e}")
        finally:
            if os.path.exists(audio_file):
                try: os.remove(audio_file)
                except: pass

    def _process_live(self, model):
        """Original chunk-based logic for low-latency live streams."""
        self.status_changed.emit(StreamState.LISTENING, "Listening...")
        self._start_time = time.time()
        chunk_file = os.path.join(tempfile.gettempdir(), f"mio_chunk_{uuid.uuid4().hex}.wav")
        
        # Setup Translator
        target_lang = self.config.get('target_lang', 'en')
        translator = GoogleTranslator(source='auto', target=target_lang) if HAS_TRANSLATOR else None

        while self._is_running:
            self.mutex.lock()
            if self._is_paused:
                self.cond.wait(self.mutex)
            self.mutex.unlock()
            if not self._is_running: break

            try:
                # Capture 6s Chunk
                cmd = [
                    'ffmpeg', '-i', self.stream_url,
                    '-t', '6', '-ac', '1', '-ar', '16000',
                    '-f', 'wav', '-y', '-loglevel', 'error',
                    chunk_file
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 1000:
                    # Visualizer Level
                    gain = self.config.get('gain', 1.0)
                    self.audio_level.emit(min(100, int(random.randint(20, 80) * gain)))

                    # Transcribe
                    src_lang = self.config.get('source_lang')
                    if src_lang == "auto": src_lang = None
                    
                    result = model.transcribe(chunk_file, fp16=False, language=src_lang)
                    text = result['text'].strip()
                    
                    if text:
                        timestamp_str = datetime.datetime.now().strftime("%H:%M:%S")
                        elapsed = time.time() - self._start_time
                        
                        # Emit Original (Source Lang)
                        self.transcript_ready.emit(text, timestamp_str, elapsed)
                        self._write_log(timestamp_str, "SRC", text)
                        
                        # Translate (Target Lang)
                        if self.config.get('translate') and translator:
                            try:
                                translated = translator.translate(text)
                                self.translation_ready.emit(translated, timestamp_str)
                                self._write_log(timestamp_str, f"TRN-{target_lang}", translated)
                            except Exception as e:
                                self.system_log.emit(f"Trans Error: {e}")
                
            except Exception as e:
                self.system_log.emit(f"Live Loop Error: {e}")
                time.sleep(1)

        if os.path.exists(chunk_file):
            try: os.remove(chunk_file)
            except: pass

    def _write_log(self, timestamp, tag, text):
        path = self.config.get('log_path')
        if path:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(f"[{timestamp}] [{tag}] {text}\n")
            except: pass

    def _seconds_to_timestamp(self, seconds):
        td = datetime.timedelta(seconds=int(seconds))
        return str(td)

# ============================================================================
# 3. UI COMPONENTS
# ============================================================================

class AudioVisualizer(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(12)
        self.setStyleSheet("background: #111; border-radius: 6px; border: 1px solid #333;")
        self.bar = QFrame(self)
        self.bar.setFixedHeight(10)
        self.bar.move(1, 1)
        self.target_level = 0
        self.current_level = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(16) 

    def set_level(self, level): self.target_level = level

    def _animate(self):
        if self.current_level < self.target_level:
            self.current_level += (self.target_level - self.current_level) * 0.5
        else: self.current_level -= 2 
        self.current_level = max(0, min(100, self.current_level))
        width = int((self.current_level / 100) * (self.width() - 2))
        self.bar.setFixedWidth(width)
        if self.current_level > 90: col = "#ff5555" 
        elif self.current_level > 60: col = "#ffb86c"
        elif self.current_level > 30: col = "#50fa7b"
        else: col = "#6272a4"
        self.bar.setStyleSheet(f"background-color: {col}; border-radius: 4px;")

class SubtitleBox(QTextBrowser):
    MAX_LINES = 1000

    def __init__(self, title="Output", color="#ffffff"):
        super().__init__()
        self.setPlaceholderText(f"Waiting for {title}...")
        self.setStyleSheet(f"""
            QTextBrowser {{
                background: rgba(20, 20, 30, 0.6);
                border: 1px solid #444;
                border-radius: 10px;
                color: {color};
                font-family: 'Segoe UI', sans-serif;
                font-size: 16px;
                padding: 15px;
            }}
        """)
        self.lines_data = [] 

    def add_line(self, text, timestamp, elapsed=0.0):
        if self.document().lineCount() > self.MAX_LINES:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            if self.lines_data: self.lines_data.pop(0)

        html = f"""
        <div style='margin-bottom: 8px;'>
            <span style='color: #666; font-size: 11px; font-family: Consolas;'>[{timestamp}]</span>
            <span style='margin-left: 8px;'>{text}</span>
        </div>
        """
        self.append(html)
        self.moveCursor(QTextCursor.End)
        self.lines_data.append({"time": timestamp, "elapsed": elapsed, "text": text})

    def search(self, text, forward=True, case_sensitive=False):
        if not text: 
            self._clear_highlights()
            return 0
        self._clear_highlights()
        
        highlight_all = QTextCharFormat()
        highlight_all.setBackground(QColor("#44475a")) 
        current_fmt = QTextCharFormat()
        current_fmt.setBackground(QColor("#ffb86c")) 
        current_fmt.setForeground(QColor("#000000"))
        
        flags = QTextDocument.FindFlags()
        if case_sensitive: flags |= QTextDocument.FindCaseSensitively
        
        doc = self.document()
        cursor = doc.find(text, 0, flags) 
        count = 0
        while not cursor.isNull():
            cursor.mergeCharFormat(highlight_all)
            cursor = doc.find(text, cursor, flags)
            count += 1
            
        if count == 0: return 0

        if not forward: flags |= QTextDocument.FindBackward
        found = self.find(text, flags)
        
        if not found:
            cursor = self.textCursor()
            if forward: cursor.movePosition(QTextCursor.Start)
            else: cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)
            found = self.find(text, flags)
            
        if found:
            cursor = self.textCursor()
            cursor.mergeCharFormat(current_fmt)
            
        return count

    def _clear_highlights(self):
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(Qt.transparent)
        cursor.mergeCharFormat(fmt)

# ============================================================================
# 3. MAIN APP (V13)
# ============================================================================

class StreamApp(BaseApp): 
    def __init__(self):
        super().__init__("Translator+", "stream.png", "#9C27B0")
        self.worker = None
        self.plugin_manager = PluginManager()
        self.settings = QSettings("Ookami", "TranslatorPlus")
        self.active_log_path = None
        self._init_ui()
        self._init_shortcuts()
        self._load_config()

    def _init_ui(self):
        # --- Toolbar ---
        toolbar = QFrame()
        toolbar.setStyleSheet("background: #1e1e2e; border-bottom: 1px solid #333;")
        toolbar_lay = QHBoxLayout(toolbar)
        toolbar_lay.setContentsMargins(10, 5, 10, 5)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste YouTube/Twitch URL and hit Enter...")
        self.url_input.setStyleSheet("background: #111; color: white; border: 1px solid #444; border-radius: 5px; padding: 5px;")
        self.url_input.returnPressed.connect(self.start_stream) 
        
        self.btn_play = self._create_btn("▶", "Start", self.toggle_stream, "#50fa7b")
        self.btn_pause = self._create_btn("⏸", "Pause", self.toggle_pause, "#ffb86c")
        self.btn_pause.setEnabled(False)
        
        self.btn_tools = QToolButton()
        self.btn_tools.setText("⚙️")
        self.btn_tools.setStyleSheet("background: transparent; color: #ccc; font-size: 16px; border: none;")
        self.btn_tools.setPopupMode(QToolButton.InstantPopup)
        
        self.menu = QMenu()
        self.menu.setStyleSheet("QMenu { background: #222; color: white; border: 1px solid #444; }")
        self.menu.addAction("💾 Export Transcript (Ctrl+S)", self.export_transcript)
        self.menu.addAction("📂 Open Logs Folder", self.open_log_folder)
        self.menu.addAction("🗑️ Clear View", self.clear_history)
        self.menu.addSeparator()
        self.plugin_menu = self.menu.addMenu("🧩 Plugins")
        self.plugin_menu.addAction("Load Plugin...", self.load_plugin_dialog)
        self.btn_tools.setMenu(self.menu)

        toolbar_lay.addWidget(QLabel("🔗"))
        toolbar_lay.addWidget(self.url_input, 1)
        toolbar_lay.addWidget(self.btn_play)
        toolbar_lay.addWidget(self.btn_pause)
        toolbar_lay.addWidget(self.btn_tools)
        self.content_layout.addWidget(toolbar)
        
        # --- Search Bar ---
        self.search_bar = QFrame()
        self.search_bar.hide()
        self.search_bar.setStyleSheet("background: #222; border-bottom: 1px solid #444;")
        sl = QHBoxLayout(self.search_bar)
        sl.setContentsMargins(10,2,10,2)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find...")
        self.search_input.setStyleSheet("background: transparent; color: white; border: none;")
        self.search_input.returnPressed.connect(lambda: self.perform_search(True))
        self.chk_case = QCheckBox("Aa")
        self.chk_case.setToolTip("Match Case")
        self.chk_case.setStyleSheet("color: #ccc;")
        self.btn_prev = self._create_btn("▲", "Prev", lambda: self.perform_search(False), "transparent")
        self.btn_next = self._create_btn("▼", "Next", lambda: self.perform_search(True), "transparent")
        for b in [self.btn_prev, self.btn_next]: b.setFixedSize(25,25)
        sl.addWidget(QLabel("🔍"))
        sl.addWidget(self.search_input)
        sl.addWidget(self.chk_case)
        sl.addWidget(self.btn_prev)
        sl.addWidget(self.btn_next)
        sl.addWidget(self._create_btn("×", "Close", lambda: self.toggle_search(False), "transparent"))
        self.content_layout.addWidget(self.search_bar)

        # --- Settings Panel ---
        settings = QFrame()
        settings.setStyleSheet("background: rgba(30,30,40,0.5); margin: 5px; border-radius: 8px;")
        set_lay = QHBoxLayout(settings)
        
        # Mode Toggle
        self.radio_live = QRadioButton("🔴 Live")
        self.radio_vod = QRadioButton("🎞️ Video (VOD)")
        self.radio_live.setStyleSheet("color: #ccc;")
        self.radio_vod.setStyleSheet("color: #ccc;")
        self.radio_live.setChecked(True)
        self.group_mode = QButtonGroup(self)
        self.group_mode.addButton(self.radio_live)
        self.group_mode.addButton(self.radio_vod)
        
        # Source Lang
        self.combo_src = QComboBox()
        self.combo_src.addItems(["Auto-Detect", "Japanese (ja)", "English (en)", "Spanish (es)"])
        self.combo_src.setStyleSheet("background: #222; color: white; padding: 5px; border-radius: 5px;")
        
        # Target Lang
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["English (en)", "Japanese (ja)", "Spanish (es)", "French (fr)", "German (de)"])
        self.combo_lang.setStyleSheet("background: #222; color: white; padding: 5px; border-radius: 5px;")
        
        self.chk_log = QCheckBox("Log")
        self.chk_log.setStyleSheet("color: #ccc;")
        
        # Audio Mix
        self.slider_gain = QSlider(Qt.Horizontal)
        self.slider_gain.setRange(0, 200); self.slider_gain.setValue(100); self.slider_gain.setFixedWidth(60)
        self.slider_gain.valueChanged.connect(self._update_gain)
        self.lbl_gain = QLabel("100%")
        self.lbl_gain.setStyleSheet("color: #888; font-size: 10px;")
        
        self.slider_vol = QSlider(Qt.Horizontal)
        self.slider_vol.setRange(0, 100); self.slider_vol.setValue(100); self.slider_vol.setFixedWidth(60)
        self.slider_vol.valueChanged.connect(self._update_volume)
        self.lbl_vol = QLabel("100%")
        self.lbl_vol.setStyleSheet("color: #888; font-size: 10px;")
        
        set_lay.addWidget(self.radio_live)
        set_lay.addWidget(self.radio_vod)
        set_lay.addSpacing(10)
        set_lay.addWidget(QLabel("In:"))
        set_lay.addWidget(self.combo_src)
        set_lay.addWidget(QLabel("➡ Out:"))
        set_lay.addWidget(self.combo_lang)
        set_lay.addWidget(self.chk_log)
        set_lay.addStretch()
        set_lay.addWidget(QLabel("🎤"))
        set_lay.addWidget(self.slider_gain)
        set_lay.addWidget(self.lbl_gain)
        set_lay.addSpacing(5)
        set_lay.addWidget(QLabel("🔊"))
        set_lay.addWidget(self.slider_vol)
        set_lay.addWidget(self.lbl_vol)
        self.content_layout.addWidget(settings)
        
        # --- Visualizer ---
        status_row = QHBoxLayout()
        self.visualizer = AudioVisualizer()
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #666; font-weight: bold; font-family: monospace;")
        status_row.addWidget(self.visualizer, 1)
        status_row.addWidget(self.lbl_status)
        self.content_layout.addLayout(status_row)
        
        # --- Views ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0; } QTabBar::tab { background: #222; color: #aaa; padding: 8px; } QTabBar::tab:selected { background: #333; color: white; border-bottom: 2px solid #9C27B0; }")
        
        self.splitter = QSplitter(Qt.Vertical)
        self.sub_orig = SubtitleBox("Original Transcript", "#f8f8f2")
        self.sub_trans = SubtitleBox("Live Translation", "#8be9fd") 
        self.splitter.addWidget(self.sub_orig)
        self.splitter.addWidget(self.sub_trans)
        
        self.tabs.addTab(self.splitter, "Subtitles")
        
        self.log_view = QTextBrowser()
        self.log_view.setStyleSheet("background: #111; color: #00FF00; font-family: Consolas; font-size: 12px; padding: 10px;")
        self.tabs.addTab(self.log_view, "System Logs")
        
        self.content_layout.addWidget(self.tabs)

    def _init_shortcuts(self):
        QShortcut(QKeySequence("Space"), self).activated.connect(self.toggle_pause)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.stop_stream)
        QShortcut(QKeySequence("Return"), self).activated.connect(self.toggle_stream)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.export_transcript)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self.clear_history)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(lambda: self.toggle_search(True))
        QShortcut(QKeySequence("F3"), self).activated.connect(lambda: self.perform_search(True))
        QShortcut(QKeySequence("Shift+F3"), self).activated.connect(lambda: self.perform_search(False))

    def _load_config(self):
        self.url_input.setText(self.settings.value("last_url", ""))
        self.chk_log.setChecked(self.settings.value("log_file", True, type=bool))
        self.slider_gain.setValue(int(self.settings.value("gain", 100)))
        self.slider_vol.setValue(int(self.settings.value("volume", 100)))
        self.combo_lang.setCurrentIndex(int(self.settings.value("target_lang_index", 0)))
        self.combo_src.setCurrentIndex(int(self.settings.value("source_lang_index", 0)))
        is_vod = self.settings.value("mode_vod", False, type=bool)
        self.radio_vod.setChecked(is_vod)
        self.radio_live.setChecked(not is_vod)

    # --- LOGIC ---
    def toggle_stream(self):
        if self.worker: self.stop_stream()
        else: self.start_stream()

    def start_stream(self):
        url = self.url_input.text().strip()
        if not url:
            self.lbl_status.setText("Error: No URL")
            self.lbl_status.setStyleSheet("color: #ff5555;")
            return

        self.active_log_path = None
        if self.chk_log.isChecked():
            desktop = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
            folder = os.path.join(desktop, "Mio_Transcripts")
            os.makedirs(folder, exist_ok=True)
            # Temp Name until Title Found
            fname = f"Stream_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M')}.txt"
            self.active_log_path = os.path.join(folder, fname)

        # Parse Languages
        t_lang = self.combo_lang.currentText().split('(')[-1].strip(')')
        s_lang = self.combo_src.currentText()
        if "Auto" in s_lang: s_lang = "auto"
        else: s_lang = s_lang.split('(')[-1].strip(')')
        
        mode = "video" if self.radio_vod.isChecked() else "live"
        
        config = {
            'translate': True, 
            'source_lang': s_lang,
            'target_lang': t_lang,
            'log_path': self.active_log_path,
            'gain': self.slider_gain.value() / 100.0,
            'volume': self.slider_vol.value() / 100.0,
            'mode': mode
        }

        self.worker = StreamWorker(url, config)
        self.worker.status_changed.connect(self._on_status_change)
        self.worker.transcript_ready.connect(self.sub_orig.add_line)
        self.worker.translation_ready.connect(self.sub_trans.add_line)
        self.worker.audio_level.connect(self.visualizer.set_level)
        self.worker.title_found.connect(self._on_title_found)
        self.worker.system_log.connect(self.append_system_log)
        self.worker.start()
        
        self.btn_play.setText("⏹ Stop")
        self.btn_play.setStyleSheet("background: #ff5555; color: #1e1e2e; border-radius: 5px;")
        self.btn_pause.setEnabled(True)
        self.url_input.setEnabled(False)

    def stop_stream(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        
        self.btn_play.setText("▶ Start")
        self.btn_play.setStyleSheet("background: #50fa7b; color: #1e1e2e; border-radius: 5px;")
        self.btn_pause.setText("⏸ Pause")
        self.btn_pause.setEnabled(False)
        self.url_input.setEnabled(True)
        self.lbl_status.setText("Stopped")
        self.visualizer.set_level(0)

    def append_system_log(self, text):
        self.log_view.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}")

    def _on_title_found(self, title):
        if self.active_log_path and os.path.exists(self.active_log_path):
            try:
                folder = os.path.dirname(self.active_log_path)
                # Clean Filename
                safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
                date = datetime.datetime.now().strftime('%Y-%m-%d')
                new_name = f"{safe_title}_{date}.txt"
                new_path = os.path.join(folder, new_name)
                
                # Handle duplicates
                if os.path.exists(new_path):
                    new_name = f"{safe_title}_{date}_{uuid.uuid4().hex[:4]}.txt"
                    new_path = os.path.join(folder, new_name)
                    
                os.rename(self.active_log_path, new_path)
                self.active_log_path = new_path
                self.lbl_status.setText(f"REC: {new_name}")
            except Exception as e:
                self.lbl_status.setText(f"Rename Error: {e}")

    def toggle_pause(self):
        if not self.worker: return
        if self.btn_pause.text() == "⏸ Pause":
            self.worker.pause()
            self.btn_pause.setText("▶ Resume")
        else:
            self.worker.resume()
            self.btn_pause.setText("⏸ Pause")

    def _update_gain(self, value):
        self.lbl_gain.setText(f"{value}%")
        if self.worker: self.worker.set_gain(value / 100.0)

    def _update_volume(self, value):
        self.lbl_vol.setText(f"{value}%")
        if self.worker: self.worker.set_volume(value / 100.0)

    def _on_status_change(self, state, msg):
        self.lbl_status.setText(msg)
        cols = {
            StreamState.CONNECTING: "#f1fa8c", StreamState.LISTENING: "#50fa7b",
            StreamState.PROCESSING_VOD: "#8be9fd",
            StreamState.PAUSED: "#ffb86c", StreamState.RETRYING: "#bd93f9", StreamState.ERROR: "#ff5555"
        }
        self.lbl_status.setStyleSheet(f"color: {cols.get(state, '#666')}; font-weight: bold; font-family: monospace;")

    def export_transcript(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "", "Text (*.txt);;SRT (*.srt);;JSON (*.json)")
        if not path: return
        
        data = self.sub_orig.lines_data
        ext = os.path.splitext(path)[1].lower()
        with open(path, 'w', encoding='utf-8') as f:
            if ext == ".json":
                json.dump(data, f, indent=2)
            elif ext == ".srt":
                for i, item in enumerate(data):
                    start = self._seconds_to_srt(item['elapsed'])
                    end = self._seconds_to_srt(item['elapsed'] + 3.0) 
                    f.write(f"{i+1}\n{start} --> {end}\n{item['text']}\n\n")
            else: 
                for item in data:
                    f.write(f"[{item['time']}] {item['text']}\n")
        self.lbl_status.setText(f"Exported to {os.path.basename(path)}")

    def _seconds_to_srt(self, seconds):
        td = datetime.timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int((seconds - total_seconds) * 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

    def toggle_search(self, show):
        self.search_bar.setVisible(show)
        if show: self.search_input.setFocus()
        else: 
            self.search_input.clear()
            self.sub_orig.search("")

    def perform_search(self, forward):
        text = self.search_input.text()
        count = self.sub_orig.search(text, forward, self.chk_case.isChecked())
        if text: self.lbl_status.setText(f"Found {count} matches")

    def load_plugin_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Plugin", "", "Python Scripts (*.py)")
        if path:
            if self.plugin_manager.load_plugin(path):
                self.plugin_menu.addAction(f"✅ {os.path.basename(path)}")
                self.lbl_status.setText("Plugin Loaded")

    def open_log_folder(self):
        desktop = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
        folder = os.path.join(desktop, "Mio_Transcripts")
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def clear_history(self):
        self.sub_orig.clear()
        self.sub_trans.clear()
        self.sub_orig.lines_data = []
        self.log_view.clear()

    def _create_btn(self, text, tooltip, func, col):
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.clicked.connect(func)
        btn.setCursor(Qt.PointingHandCursor)
        if len(text) > 1: btn.setFixedSize(80, 30) 
        else: btn.setFixedSize(30, 30) 
        btn.setStyleSheet(f"""
            QPushButton {{ background: {col}; color: #1e1e2e; border-radius: 5px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {col}; }}
            QPushButton:disabled {{ background: #444; color: #888; }}
        """)
        return btn

    def closeEvent(self, event):
        self.settings.setValue("last_url", self.url_input.text())
        self.settings.setValue("log_file", self.chk_log.isChecked())
        self.settings.setValue("gain", self.slider_gain.value())
        self.settings.setValue("volume", self.slider_vol.value())
        self.settings.setValue("target_lang_index", self.combo_lang.currentIndex())
        self.settings.setValue("source_lang_index", self.combo_src.currentIndex())
        self.settings.setValue("mode_vod", self.radio_vod.isChecked())
        self.stop_stream()
        super().closeEvent(event)
import os
import sys
import datetime
import random
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QLineEdit, QPushButton, QLabel, QTextBrowser, 
                               QFrame, QMenu, QApplication, QStackedWidget,
                               QScrollArea, QComboBox, QCheckBox, QSlider, 
                               QSizePolicy, QGroupBox, QSpacerItem)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QAction, QIcon, QTextCursor, QFont, QGuiApplication, QColor, QPainter, QBrush, QLinearGradient

from src.agent.llm_engine import BrainEngine
from src.core.paths import get_asset_path
from src.skills.audio_ops import AudioSkills
from src.skills.system_ops import SystemSkills
from src.skills.settings_ops import SettingsSkills

# ==========================================
# 🧵 WORKER THREADS
# ==========================================

class ThinkingThread(QThread):
    response_ready = Signal(str)
    def __init__(self, brain, text):
        super().__init__()
        self.brain = brain
        self.text = text

    def run(self):
        try:
            reply = self.brain.think(self.text)
            self.response_ready.emit(reply)
        except Exception as e:
            self.response_ready.emit(f"❌ Brain Error: {e}")

class AudioThread(QThread):
    transcription_ready = Signal(str)
    def __init__(self, seconds=5, translate=False):
        super().__init__()
        self.seconds = seconds
        self.translate = translate

    def run(self):
        try:
            text = AudioSkills.listen_live(self.seconds, self.translate)
            self.transcription_ready.emit(text)
        except Exception as e:
            self.transcription_ready.emit(f"❌ Audio Error: {e}")

# ==========================================
# 📱 APP MODULES (Base & Specifics)
# ==========================================

class BaseApp(QWidget):
    """Base class for all apps with modern styling"""
    command_signal = Signal(str)
    
    def __init__(self, name="App", icon=""):
        super().__init__()
        self.name = name
        self.icon = icon
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(15)
        
    def add_title(self, text, icon=None):
        """Add modern app title"""
        title_frame = QFrame()
        title_frame.setStyleSheet("background: transparent;")
        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(0,0,0,0)
        
        title_icon = QLabel(icon if icon else self.icon)
        title_icon.setStyleSheet("font-size: 24px; margin-right: 10px;")
        
        title_text = QLabel(text)
        title_text.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_text)
        title_layout.addStretch()
        
        self.layout.addWidget(title_frame)
        return title_frame

class ChatApp(BaseApp):
    request_pose = Signal(str)
    
    def __init__(self, brain):
        super().__init__("Chat", "💬")
        self.brain = brain
        self.add_title("Chat", "💬")
        
        # Display
        self.chat_display = QTextBrowser()
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background: rgba(30, 30, 40, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                color: #e0e0e0;
                font-size: 13px;
                padding: 10px;
            }
        """)
        self.chat_display.setOpenExternalLinks(True)
        self.layout.addWidget(self.chat_display)
        
        # Input Area
        input_container = QFrame()
        input_container.setStyleSheet("background: rgba(40, 40, 50, 0.8); border: 1px solid rgba(62, 166, 255, 0.3); border-radius: 20px;")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(5, 5, 5, 5)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message...")
        self.input_field.setStyleSheet("background: transparent; border: none; color: white; font-size: 14px; padding: 5px;")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field)
        
        send_btn = QPushButton("➤")
        send_btn.setFixedSize(40, 40)
        send_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3EA6FF, stop:1 #6B46C1); color: white; border-radius: 20px; font-weight: bold; }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4EB6FF, stop:1 #7B56D1); }
        """)
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)
        
        self.layout.addWidget(input_container)

    def send_message(self):
        text = self.input_field.text().strip()
        if not text: return
        
        self.append_chat("You", text)
        self.input_field.clear()
        self.request_pose.emit("think")
        
        self.worker = ThinkingThread(self.brain, text)
        self.worker.response_ready.connect(self.handle_response)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def handle_response(self, text):
        self.request_pose.emit("idle")
        self.append_chat("Mio", text)

    def append_chat(self, user, text):
        if user == "You":
            color, align, bg = "#3EA6FF", "right", "rgba(62, 166, 255, 0.2)"
        elif user == "Mio":
            color, align, bg = "#FF6B8B", "left", "rgba(255, 107, 139, 0.2)"
        else:
            color, align, bg = "#AAAAAA", "center", "rgba(100, 100, 100, 0.2)"
        
        html = f"""
        <div style='text-align: {align}; margin: 5px 0;'>
            <div style='display: inline-block; background: {bg}; border-radius: 15px; padding: 8px 12px; max-width: 80%; border: 1px solid {color}40;'>
                <div style='color: {color}; font-weight: bold; font-size: 10px; margin-bottom: 2px;'>{user}</div>
                <div style='color: #e0e0e0; font-size: 13px;'>{text}</div>
            </div>
        </div>"""
        self.chat_display.append(html)
        self.chat_display.moveCursor(QTextCursor.End)

class VoiceApp(BaseApp):
    def __init__(self):
        super().__init__("Voice", "🎙️")
        self.add_title("Voice Recorder", "🎙️")
        self.layout.setAlignment(Qt.AlignCenter)
        
        # Status
        self.status_label = QLabel("Tap to Record")
        self.status_label.setStyleSheet("color: #aaa; font-size: 16px; font-weight: bold; margin-bottom: 20px;")
        self.layout.addWidget(self.status_label, alignment=Qt.AlignCenter)
        
        # Big Button
        self.record_btn = QPushButton("🎙️")
        self.record_btn.setFixedSize(140, 140)
        self.record_btn.setStyleSheet("""
            QPushButton {
                background: qradialgradient(cx:0.5, cy:0.5, radius: 0.5, fx:0.5, fy:0.5, stop:0 rgba(62, 166, 255, 0.8), stop:1 rgba(62, 166, 255, 0.3));
                color: white; border-radius: 70px; border: 3px solid rgba(62, 166, 255, 0.5); font-size: 60px;
            }
            QPushButton:hover { border-color: rgba(62, 166, 255, 0.8); }
        """)
        self.record_btn.clicked.connect(self.toggle_recording)
        self.layout.addWidget(self.record_btn, alignment=Qt.AlignCenter)
        
        # Results
        self.results_display = QTextBrowser()
        self.results_display.setMaximumHeight(150)
        self.results_display.setStyleSheet("background: rgba(30, 30, 40, 0.7); border-radius: 15px; color: #b0b0b0; padding: 10px; margin-top: 30px;")
        self.layout.addWidget(self.results_display)
        
        self.is_recording = False

    def toggle_recording(self):
        if not self.is_recording: self.start_recording()
        else: self.stop_recording()

    def start_recording(self):
        self.is_recording = True
        self.status_label.setText("Recording (10s)...")
        self.record_btn.setStyleSheet("background: qradialgradient(cx:0.5, cy:0.5, radius: 0.5, fx:0.5, fy:0.5, stop:0 rgba(255, 68, 68, 0.9), stop:1 rgba(255, 68, 68, 0.3)); color: white; border-radius: 70px; font-size: 60px; border: 3px solid rgba(255, 68, 68, 0.8);")
        
        self.audio_thread = AudioThread(10, False)
        self.audio_thread.transcription_ready.connect(self.on_transcription_ready)
        self.audio_thread.finished.connect(self.audio_thread.deleteLater)
        self.audio_thread.start()

    def stop_recording(self):
        self.is_recording = False
        self.status_label.setText("Tap to Record")
        self.record_btn.setStyleSheet("background: qradialgradient(cx:0.5, cy:0.5, radius: 0.5, fx:0.5, fy:0.5, stop:0 rgba(62, 166, 255, 0.8), stop:1 rgba(62, 166, 255, 0.3)); color: white; border-radius: 70px; border: 3px solid rgba(62, 166, 255, 0.5); font-size: 60px;")

    def on_transcription_ready(self, text):
        if text and "❌" not in text: self.results_display.append(f"📝 {text}")
        else: self.results_display.append(f"❌ {text}")
        self.stop_recording()

class ControlCenterApp(BaseApp):
    def __init__(self):
        super().__init__("Controls", "🎛️")
        self.add_title("Control Center", "🎛️")
        
        grid = QGridLayout()
        grid.setSpacing(15)
        
        controls = [
            ("📸", "Screenshot", "[SCREENSHOT]", "#3EA6FF", 0, 0), ("📊", "Stats", "[APP_STATS]", "#00D4AA", 0, 1), ("🧹", "Clear", "MIO_CLEAR", "#FFB74D", 0, 2),
            ("🔊", "Audio", "[AUDIO_DEVICES]", "#9C27B0", 1, 0), ("📝", "Notes", "MIO_OPEN_NOTES", "#FF6B8B", 1, 1), ("🔄", "Restart", "MIO_RESTART", "#F44336", 1, 2),
            ("🎓", "Class", "[LISTEN_START]", "#4CAF50", 2, 0), ("🛑", "Stop", "[LISTEN_STOP]", "#FF9800", 2, 1), ("📂", "Files", "[OPEN] .", "#607D8B", 2, 2),
        ]
        
        for icon, name, cmd, color, r, c in controls:
            btn = QPushButton(f"{icon}\n{name}")
            btn.setFixedSize(90, 90)
            btn.setStyleSheet(f"""
                QPushButton {{ background: {color}20; border: 2px solid {color}60; border-radius: 20px; color: white; font-size: 24px; font-weight: bold; }}
                QPushButton:hover {{ background: {color}40; border-color: {color}; }}
                QPushButton:pressed {{ background: {color}60; }}
            """)
            btn.clicked.connect(lambda ch, c=cmd: self.command_signal.emit(c))
            grid.addWidget(btn, r, c)
        
        self.layout.addLayout(grid)

class CameraApp(BaseApp):
    def __init__(self):
        super().__init__("Camera", "📸")
        self.add_title("Camera", "📸")
        
        self.preview = QLabel("📷\nCamera Ready")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedSize(300, 200)
        self.preview.setStyleSheet("background: #1a1a2e; color: #555; font-size: 20px; border-radius: 20px; border: 2px dashed #3EA6FF;")
        self.layout.addWidget(self.preview, alignment=Qt.AlignCenter)
        
        hbox = QHBoxLayout()
        snap = QPushButton("Capture")
        snap.setFixedSize(140, 50)
        snap.clicked.connect(self.snap)
        snap.setStyleSheet("background: #3EA6FF; color: white; border-radius: 25px; font-weight: bold; font-size: 16px;")
        
        gal = QPushButton("📁")
        gal.setFixedSize(50, 50)
        gal.clicked.connect(lambda: self.command_signal.emit("[OPEN] Desktop"))
        gal.setStyleSheet("background: #444; color: white; border-radius: 25px; font-size: 20px;")
        
        hbox.addWidget(snap)
        hbox.addWidget(gal)
        self.layout.addLayout(hbox)

    def snap(self):
        self.preview.setText("📸\nCapturing...")
        QTimer.singleShot(200, lambda: self.command_signal.emit("[SCREENSHOT]"))
        QTimer.singleShot(1000, lambda: self.preview.setText("📷\nCamera Ready"))

class SettingsApp(BaseApp):
    def __init__(self):
        super().__init__("Settings", "⚙️")
        self.add_title("Settings", "⚙️")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setSpacing(20)
        
        self.add_section("🎤 Audio Input", ["Default Mic", "Stereo Mix"], 
                         lambda t: self.command_signal.emit(f"[SET_MIC] {1 if 'Stereo' in t else 0}"))
        self.add_section("🧠 AI Persona", ["Default", "Sensei", "Coder", "Maid"], 
                         lambda t: self.command_signal.emit(f"[PERSONA] {t.lower()}"))
        
        scroll.setWidget(content)
        self.layout.addWidget(scroll)

    def add_section(self, title, items, callback):
        frame = QFrame()
        frame.setStyleSheet("background: rgba(40,40,50,0.5); border-radius: 15px; padding: 10px;")
        lay = QVBoxLayout(frame)
        lay.addWidget(QLabel(title, styleSheet="color: #3EA6FF; font-weight: bold;"))
        combo = QComboBox()
        combo.addItems(items)
        combo.currentTextChanged.connect(callback)
        combo.setStyleSheet("background: #222; color: white; padding: 5px; border-radius: 5px;")
        lay.addWidget(combo)
        self.content_layout.addWidget(frame)

# ==========================================
# 📱 MODERN PHONE CONTAINER
# ==========================================

class ModernMioPhone(QFrame):
    def __init__(self, brain):
        super().__init__()
        self.brain = brain
        self.app_history = []
        self.setup_ui()
    
    def setup_ui(self):
        self.setFixedSize(380, 680)
        self.setStyleSheet("ModernMioPhone { background: #0d0d14; border: 10px solid #1a1a2a; border-radius: 35px; }")
        
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        
        # 1. Status Bar
        status = QHBoxLayout()
        status.setContentsMargins(20, 10, 20, 5)
        self.time_lbl = QLabel("12:00")
        self.time_lbl.setStyleSheet("color: white; font-weight: bold;")
        status.addWidget(self.time_lbl)
        status.addStretch()
        status.addWidget(QLabel("🔋 87%", styleSheet="color: #00ff88; font-weight: bold;"))
        main.addLayout(status)
        
        # FIXED: Explicitly creating the timer before connecting/starting
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(lambda: self.time_lbl.setText(datetime.datetime.now().strftime("%H:%M")))
        self.clock_timer.start(1000)
        
        # 2. Stack
        self.stack = QStackedWidget()
        
        # Init Apps
        self.apps = {
            "home": self.create_home(),
            "chat": ChatApp(self.brain),
            "voice": VoiceApp(),
            "controls": ControlCenterApp(),
            "camera": CameraApp(),
            "settings": SettingsApp()
        }
        
        # Add to stack (Order must match index!)
        self.stack.addWidget(self.apps["home"])     # 0
        self.stack.addWidget(self.apps["chat"])     # 1
        self.stack.addWidget(self.apps["voice"])    # 2
        self.stack.addWidget(self.apps["controls"]) # 3
        self.stack.addWidget(self.apps["camera"])   # 4
        self.stack.addWidget(self.apps["settings"]) # 5
        
        # Signals
        self.apps["chat"].request_pose.connect(self.parent().set_pose if self.parent() else lambda x: None)
        for app in ["controls", "camera", "settings"]:
            self.apps[app].command_signal.connect(self.handle_cmd)
            
        main.addWidget(self.stack)
        
        # 3. Nav Bar
        nav = QFrame()
        nav.setFixedHeight(70)
        nav.setStyleSheet("background: #1a1a2a; border-radius: 0 0 35px 35px;")
        nav_lay = QHBoxLayout(nav)
        nav_lay.setSpacing(30)
        
        for icon, idx in [("◀", -1), ("●", 0), ("☰", 3)]: # Back, Home, Controls(Recent)
            btn = QPushButton(icon)
            btn.setFixedSize(50, 50)
            style = "color: white; font-size: 20px; border: none; background: transparent;"
            if idx == 0: style = "color: white; font-size: 24px; border: 2px solid #555; border-radius: 25px;"
            btn.setStyleSheet(style)
            
            if idx == -1: btn.clicked.connect(self.go_back)
            else: btn.clicked.connect(lambda ch, i=idx: self.switch_app(i))
            nav_lay.addWidget(btn)
            
        main.addWidget(nav)

    def create_home(self):
        home = QWidget()
        lay = QVBoxLayout(home)
        
        # Welcome
        wel = QLabel("🐺\nWelcome back!")
        wel.setAlignment(Qt.AlignCenter)
        wel.setStyleSheet("font-size: 24px; color: white; font-weight: bold; margin: 20px;")
        lay.addWidget(wel)
        
        # Grid
        grid = QGridLayout()
        grid.setSpacing(15)
        apps = [
            ("💬", "Chat", 1, "#3EA6FF"), ("🎙️", "Voice", 2, "#FF6B8B"),
            ("🎛️", "Controls", 3, "#00D4AA"), ("📸", "Camera", 4, "#FFB74D"),
            ("⚙️", "Settings", 5, "#9C27B0")
        ]
        
        for i, (icon, name, idx, col) in enumerate(apps):
            r, c = divmod(i, 3)
            btn = QPushButton(f"{icon}\n{name}")
            btn.setFixedSize(90, 90)
            btn.setStyleSheet(f"background: {col}30; border: 2px solid {col}50; border-radius: 25px; color: white; font-size: 24px; font-weight: bold;")
            btn.clicked.connect(lambda ch, x=idx: self.switch_app(x))
            grid.addWidget(btn, r, c)
            
        lay.addLayout(grid)
        lay.addStretch()
        return home

    def switch_app(self, idx):
        curr = self.stack.currentIndex()
        if curr != idx:
            self.app_history.append(curr)
            self.stack.setCurrentIndex(idx)

    def go_back(self):
        if self.app_history:
            self.stack.setCurrentIndex(self.app_history.pop())

    def handle_cmd(self, cmd):
        if cmd == "MIO_CLEAR": self.apps["chat"].chat_display.clear()
        elif cmd == "MIO_RESTART": 
            QApplication.quit()
            os.execl(sys.executable, sys.executable, *sys.argv)
        elif cmd == "MIO_OPEN_NOTES": AudioSkills.get_latest_notes()
        elif cmd == "[SCREENSHOT]":
            SystemSkills.take_screenshot()
            self.show_notif("📸", "Screenshot Saved")
        elif cmd == "[LISTEN_START]":
            self.switch_app(2)
            QTimer.singleShot(200, self.apps["voice"].start_recording)
        else:
            self.switch_app(1)
            self.apps["chat"].input_field.setText(cmd)
            QTimer.singleShot(100, self.apps["chat"].send_message)

    def show_notif(self, icon, msg):
        lbl = QLabel(f"{icon} {msg}", self)
        lbl.setStyleSheet("background: rgba(62, 166, 255, 0.9); color: white; padding: 10px 20px; border-radius: 15px; font-weight: bold;")
        lbl.adjustSize()
        lbl.move(20, 60)
        lbl.show()
        QTimer.singleShot(2500, lbl.deleteLater)

# ==========================================
# 🐺 MASCOT WIDGET
# ==========================================

class MascotWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.brain = BrainEngine()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(1000, 300, 650, 720) # Spacious for phone

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.phone = ModernMioPhone(self.brain)
        self.phone.hide()
        layout.addWidget(self.phone)

        self.avatar = QLabel()
        self.avatar.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        layout.addWidget(self.avatar)
        
        self.set_pose("idle")
        self.phone.apps["chat"].request_pose.connect(self.set_pose)

    def set_pose(self, pose_name):
        path = get_asset_path(f"mio_{pose_name}.png")
        if path and os.path.exists(path):
            self.avatar.setPixmap(QPixmap(path).scaled(220, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.avatar.setText("🐺")
            self.avatar.setStyleSheet("font-size: 60px;")

    # Drag Logic
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.initial_pos = self.pos()
    def mouseMoveEvent(self, e):
        if hasattr(self, 'drag_pos') and self.drag_pos:
            self.move(e.globalPosition().toPoint() - self.drag_pos)
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and hasattr(self, 'drag_pos'):
            if self.pos() == self.initial_pos: self.toggle_phone()
            self.drag_pos = None

    def toggle_phone(self):
        if self.phone.isVisible():
            self.phone.hide()
            self.resize(270, 320)
        else:
            self.resize(650, 720)
            self.phone.show()

    def closeEvent(self, event):
        if hasattr(self.phone.apps["chat"], 'worker') and self.phone.apps["chat"].worker.isRunning():
            self.phone.apps["chat"].worker.terminate()
            self.phone.apps["chat"].worker.wait()
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #222; color: white; padding: 5px; border-radius: 5px; } QMenu::item:selected { background: #3EA6FF; }")
        menu.addAction("📱 Toggle Phone", self.toggle_phone)
        menu.addAction("📍 Reset Position", lambda: self.move(100, 100))
        menu.addSeparator()
        menu.addAction("❌ Sleep", QApplication.quit)
        menu.exec(event.globalPos())
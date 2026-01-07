import sys
import os
import datetime
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QGridLayout, QStackedWidget, QFrame, QLabel, 
                               QPushButton, QScrollArea, QMenu)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap, QAction

from src.agent.llm_engine import BrainEngine
from src.core.paths import get_asset_path, get_project_root
from src.skills.system_ops import SystemSkills
from src.skills.audio_ops import AudioSkills

# --- IMPORT ALL APPS ---
# Ensure you have created these files in src/ui/apps/
from src.ui.apps.chat import ChatApp
from src.ui.apps.files import FilesApp
from src.ui.apps.system import SystemApp
from src.ui.apps.dev import DevApp
from src.ui.apps.git import GitApp
from src.ui.apps.database import DbApp
from src.ui.apps.audio_recorder import VoiceApp
from src.ui.apps.stream_listener import StreamApp
from src.ui.apps.transcriber import TranscriberApp
from src.ui.apps.web import WebApp
from src.ui.apps.clock import ClockApp
from src.ui.apps.settings import SettingsApp

# ==========================================
# 🧵 WORKER THREAD (Keeps UI Smooth)
# ==========================================

class ThinkingThread(QThread):
    response_ready = Signal(str)
    
    def __init__(self, brain, text):
        super().__init__()
        self.brain = brain
        self.text = text

    def run(self):
        try:
            # The Brain thinks here, blocking this thread but not the UI
            reply = self.brain.think(self.text)
            self.response_ready.emit(reply)
        except Exception as e:
            self.response_ready.emit(f"❌ Brain Error: {e}")

# ==========================================
# 📱 MODERN PHONE OS (The Handler)
# ==========================================

class ModernMioPhone(QFrame):
    def __init__(self, brain_engine):
        super().__init__()
        self.brain = brain_engine
        self.app_history = []  # To track navigation (Back button logic)
        
        self.setup_ui()
        self.init_apps()
        
    def setup_ui(self):
        """Builds the Phone Frame, Status Bar, and Navigation Bar."""
        self.setFixedSize(380, 750) # Slightly taller for modern apps
        self.setStyleSheet("""
            ModernMioPhone { 
                background: #0d0d14; 
                border: 8px solid #1a1a2a; 
                border-radius: 35px; 
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # --- 1. Status Bar (Top) ---
        status_bar = QHBoxLayout()
        status_bar.setContentsMargins(20, 10, 20, 5)
        
        self.time_lbl = QLabel("00:00")
        self.time_lbl.setStyleSheet("color: white; font-weight: bold; font-family: monospace;")
        
        status_bar.addWidget(self.time_lbl)
        status_bar.addStretch()
        status_bar.addWidget(QLabel("🐺 5G", styleSheet="color: #00ff88; font-weight: bold; font-size: 10px;"))
        
        self.main_layout.addLayout(status_bar)
        
        # Clock Tick
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(lambda: self.time_lbl.setText(datetime.datetime.now().strftime("%H:%M")))
        self.clock_timer.start(1000)
        
        # --- 2. Main Content Stack ---
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)
        
        # --- 3. Navigation Bar (Bottom) ---
        nav_bar = QFrame()
        nav_bar.setFixedHeight(70)
        nav_bar.setStyleSheet("background: #151520; border-radius: 0 0 30px 30px; border-top: 1px solid #222;")
        nav_lay = QHBoxLayout(nav_bar)
        nav_lay.setSpacing(40)
        nav_lay.setAlignment(Qt.AlignCenter)
        
        # Nav Buttons: Back | Home | Recent(Chat)
        btn_back = self.create_nav_btn("◀")
        btn_home = self.create_nav_btn("●", is_home=True)
        btn_chat = self.create_nav_btn("💬")
        
        btn_back.clicked.connect(self.go_back)
        btn_home.clicked.connect(self.go_home)
        btn_chat.clicked.connect(lambda: self.switch_app_by_name("Chat"))
        
        nav_lay.addWidget(btn_back)
        nav_lay.addWidget(btn_home)
        nav_lay.addWidget(btn_chat)
        
        self.main_layout.addWidget(nav_bar)

    def create_nav_btn(self, text, is_home=False):
        btn = QPushButton(text)
        size = 50 if is_home else 40
        btn.setFixedSize(size, size)
        border = "2px solid #555" if is_home else "none"
        btn.setStyleSheet(f"""
            QPushButton {{ color: white; font-size: 20px; background: transparent; border: {border}; border-radius: {size//2}px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.1); }}
        """)
        return btn

    def init_apps(self):
        """Initializes all App Modules and registers them."""
        # Dictionary to store app instances
        self.apps = {}
        
        # 0. The Home Screen (Grid)
        self.home_screen = self.create_home_screen()
        self.stack.addWidget(self.home_screen) # Index 0
        
        # List of App Classes to instantiate
        # (Name, Class)
        app_classes = [
            ("Chat", ChatApp),
            ("Files", FilesApp),
            ("System", SystemApp),
            ("Dev", DevApp),
            ("Git", GitApp),
            ("Database", DbApp),
            ("Voice", VoiceApp),
            ("Stream", StreamApp),
            ("Transcriber", TranscriberApp),
            ("Web", WebApp),
            ("Clock", ClockApp),
            ("Settings", SettingsApp)
        ]
        
        # Instantiate and Register
        for name, Cls in app_classes:
            try:
                # Initialize
                if name == "Chat":
                    instance = Cls(self.brain) # Chat needs brain ref for avatar logic sometimes
                else:
                    instance = Cls()
                
                # Connect Signals (The Core OS Logic)
                instance.command_signal.connect(self.handle_global_command)
                instance.navigation_signal.connect(self.handle_navigation)
                
                # Add to Stack
                self.stack.addWidget(instance)
                self.apps[name] = instance
                
            except Exception as e:
                print(f"❌ Failed to load app {name}: {e}")

    def create_home_screen(self):
        """Generates the App Grid."""
        widget = QWidget()
        lay = QVBoxLayout(widget)
        
        # Header
        wel = QLabel("🐺\nOOKAMI OS")
        wel.setAlignment(Qt.AlignCenter)
        wel.setStyleSheet("font-size: 20px; color: white; font-weight: bold; margin: 20px;")
        lay.addWidget(wel)
        
        # Scroll Area for App Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(15)
        grid.setContentsMargins(10, 0, 10, 0)
        
        # Define Apps for Grid Layout
        # (Name, IconFile, Color) - Must match self.apps keys
        grid_items = [
            ("Chat", "chat.png", "#3EA6FF"),
            ("Files", "folder.png", "#FFC107"),
            ("System", "cpu.png", "#4CAF50"),
            ("Dev", "code.png", "#2196F3"),
            ("Git", "git.png", "#F4511E"),
            ("Database", "database.png", "#009688"),
            ("Voice", "mic.png", "#E91E63"),
            ("Stream", "stream.png", "#9C27B0"),
            ("Transcriber", "transcribe.png", "#673AB7"),
            ("Web", "globe.png", "#03A9F4"),
            ("Clock", "clock.png", "#FF9800"),
            ("Settings", "settings.png", "#607D8B"),
        ]
        
        for i, (name, icon_file, col) in enumerate(grid_items):
            r, c = divmod(i, 3) # 3 columns
            
            btn = QPushButton()
            btn.setFixedSize(90, 90)
            
            # Icon Setup
            root = get_project_root()
            icon_path = os.path.join(root, "assets", "icons", icon_file)
            if os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(40, 40))
                btn.setText(f"\n{name}")
            else:
                # Fallback if icon missing
                btn.setText(f"📱\n{name}")

            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col}20;
                    border: 1px solid {col}40;
                    border-radius: 20px;
                    color: white;
                    font-weight: bold;
                    text-align: center;
                }}
                QPushButton:hover {{ background-color: {col}40; border: 2px solid {col}; }}
                QPushButton:pressed {{ background-color: {col}60; }}
            """)
            
            # Connect Click
            btn.clicked.connect(lambda ch, n=name: self.switch_app_by_name(n))
            grid.addWidget(btn, r, c)

        scroll.setWidget(grid_container)
        lay.addWidget(scroll)
        return widget

    # --- NAVIGATION LOGIC ---

    def switch_app_by_name(self, name):
        """Switches the stack to the requested app."""
        if name in self.apps:
            # Save current index for 'Back' button, unless we are at Home (0)
            current = self.stack.currentIndex()
            if current != 0:
                self.app_history.append(current)
            
            widget = self.apps[name]
            self.stack.setCurrentWidget(widget)
        else:
            print(f"⚠️ App '{name}' not found.")

    def go_home(self):
        """Returns to the grid."""
        self.app_history.clear() # Reset history on Home
        self.stack.setCurrentIndex(0)

    def go_back(self):
        """Goes to previous screen."""
        if self.app_history:
            prev_idx = self.app_history.pop()
            self.stack.setCurrentIndex(prev_idx)
        else:
            self.stack.setCurrentIndex(0) # Default to home

    def handle_navigation(self, action):
        """Handles navigation signals from apps."""
        if action == "back":
            self.go_back()
        elif action == "home":
            self.go_home()

    # --- CENTRAL COMMAND DISPATCH ---

    def handle_global_command(self, cmd_text):
        """
        Receives text/commands from ANY app (Chat, Voice, System).
        Decides whether to execute it as a tool or send it to the LLM.
        """
        if not cmd_text: return

        # 1. Check for Internal System Commands
        if cmd_text.startswith("[") and "]" in cmd_text:
            # It's a tool command (e.g. [SCREENSHOT], [LISTEN] 10)
            # We can execute it directly or pass to brain to route
            print(f"🔧 System Command Received: {cmd_text}")
            
            # Handling specific UI-related commands directly
            if "[SCREENSHOT]" in cmd_text:
                SystemSkills.take_screenshot()
                self.show_notif("📸", "Screenshot Captured")
                return

            # Pass complex commands (like [SEARCH] x) through the Chat App logic
            # so the user sees the output in the chat window
            self.switch_app_by_name("Chat")
            self.apps["Chat"].append_chat("You", cmd_text)
            self.process_with_brain(cmd_text)
            
        else:
            # 2. It's a conversational message
            # Switch to Chat App to show the interaction
            self.switch_app_by_name("Chat")
            self.apps["Chat"].append_chat("You", cmd_text)
            self.process_with_brain(cmd_text)

    def process_with_brain(self, text):
        """Spins up a thread to let Mio think without freezing UI."""
        # Set Avatar to Thinking (Signal to MascotWidget)
        if self.parent():
            self.parent().set_pose("think")

        self.worker = ThinkingThread(self.brain, text)
        self.worker.response_ready.connect(self.on_brain_response)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def on_brain_response(self, response_text):
        """Called when LLM finishes generating."""
        if self.parent():
            self.parent().set_pose("idle")
            
        # Send response to Chat App
        if "Chat" in self.apps:
            self.apps["Chat"].append_chat("Mio", response_text)

    def show_notif(self, icon, msg):
        """Overlay notification."""
        lbl = QLabel(f"{icon} {msg}", self)
        lbl.setStyleSheet("background: rgba(62, 166, 255, 0.9); color: white; padding: 10px 20px; border-radius: 15px; font-weight: bold;")
        lbl.adjustSize()
        lbl.move(20, 60)
        lbl.show()
        QTimer.singleShot(2500, lbl.deleteLater)

# ==========================================
# 🐺 MASCOT DESKTOP WIDGET (The Container)
# ==========================================

class MascotWidget(QWidget):
    def __init__(self):
        super().__init__()
        # Initialize the Brain Engine here
        print("🧠 initializing Brain Engine...")
        self.brain = BrainEngine()
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(100, 100, 700, 800) 

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. The Phone (Hidden by default or shown)
        self.phone = ModernMioPhone(self.brain)
        # self.phone.hide() # Uncomment to start hidden
        layout.addWidget(self.phone)

        # 2. The Avatar
        self.avatar = QLabel()
        self.avatar.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        layout.addWidget(self.avatar)
        
        self.set_pose("idle")

        # 3. Connection: Let Chat app request pose changes directly if needed
        # (Though we handle it in handle_global_command usually)
        if "Chat" in self.phone.apps:
            self.phone.apps["Chat"].request_pose.connect(self.set_pose)

    def set_pose(self, pose_name):
        path = get_asset_path(f"mio_{pose_name}.png")
        if path and os.path.exists(path):
            self.avatar.setPixmap(QPixmap(path).scaled(250, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.avatar.setText("🐺") # Fallback
            self.avatar.setStyleSheet("font-size: 60px;")

    # --- DRAG & DROP LOGIC ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.initial_pos = self.pos()
    def mouseMoveEvent(self, e):
        if hasattr(self, 'drag_pos') and self.drag_pos:
            self.move(e.globalPosition().toPoint() - self.drag_pos)
    def mouseReleaseEvent(self, e):
        self.drag_pos = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #222; color: white; padding: 5px; } QMenu::item:selected { background: #3EA6FF; }")
        menu.addAction("📱 Toggle Phone", self.toggle_phone)
        menu.addAction("📍 Reset Position", lambda: self.move(100, 100))
        menu.addSeparator()
        menu.addAction("❌ Sleep (Exit)", QApplication.quit)
        menu.exec(event.globalPos())

    def toggle_phone(self):
        if self.phone.isVisible():
            self.phone.hide()
            self.resize(300, 350) # Shrink to just avatar
        else:
            self.resize(700, 800) # Expand for phone
            self.phone.show()
import datetime
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, 
                               QStackedWidget, QPushButton, QScrollArea, QWidget, QGridLayout)
from PySide6.QtCore import Qt, QTimer
from src.ui.utils.overlay import LoadingOverlay

class ModernMioPhone(QFrame):
    def __init__(self, app_manager):
        super().__init__()
        self.app_manager = app_manager
        self.app_history = [] 
        self.setup_ui()
        self.init_home()
        
        # Overlay
        self.overlay = LoadingOverlay(self)
        
    def setup_ui(self):
        self.setFixedSize(380, 750)
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
        
        status_bar = QHBoxLayout()
        status_bar.setContentsMargins(20, 10, 20, 5)
        self.time_lbl = QLabel("00:00")
        self.time_lbl.setStyleSheet("color: white; font-weight: bold; font-family: monospace;")
        status_bar.addWidget(self.time_lbl)
        status_bar.addStretch()
        status_bar.addWidget(QLabel("🐺 5G", styleSheet="color: #00ff88; font-weight: bold; font-size: 10px;"))
        self.main_layout.addLayout(status_bar)
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(lambda: self.time_lbl.setText(datetime.datetime.now().strftime("%H:%M")))
        self.clock_timer.start(1000)
        
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)
        
        nav_bar = QFrame()
        nav_bar.setFixedHeight(70)
        nav_bar.setStyleSheet("background: #151520; border-radius: 0 0 30px 30px; border-top: 1px solid #222;")
        nav_lay = QHBoxLayout(nav_bar)
        nav_lay.setSpacing(40)
        nav_lay.setAlignment(Qt.AlignCenter)
        
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
        btn.setStyleSheet(f"QPushButton {{ color: white; font-size: 20px; background: transparent; border: {border}; border-radius: {size//2}px; }}")
        return btn

    def init_home(self):
        self.home_screen = self.create_home_screen()
        self.stack.addWidget(self.home_screen) 
        for app in self.app_manager.apps.values():
            if hasattr(app, 'navigation_signal'):
                app.navigation_signal.connect(self.handle_navigation)

    def create_home_screen(self):
        widget = QWidget()
        lay = QVBoxLayout(widget)
        wel = QLabel("🐺\nOOKAMI OS")
        wel.setAlignment(Qt.AlignCenter)
        wel.setStyleSheet("font-size: 20px; color: white; font-weight: bold; margin: 20px;")
        lay.addWidget(wel)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(15)
        
        grid_items = [
            ("Chat", "chat.png", "#3EA6FF"), ("Files", "folder.png", "#FFC107"),
            ("System", "cpu.png", "#4CAF50"), ("Dev", "code.png", "#2196F3"),
            ("Git", "git.png", "#F4511E"), ("Database", "database.png", "#009688"),
            ("Voice", "mic.png", "#E91E63"), ("Stream", "stream.png", "#9C27B0"),
            ("Transcriber", "transcribe.png", "#673AB7"), ("Web", "globe.png", "#03A9F4"),
            ("Clock", "clock.png", "#FF9800"), ("Settings", "settings.png", "#607D8B"),
        ]
        
        for i, (name, icon, col) in enumerate(grid_items):
            r, c = divmod(i, 3)
            btn = QPushButton(f"\n{name}")
            btn.setFixedSize(90, 90)
            btn.setStyleSheet(f"background-color: {col}20; border: 1px solid {col}40; border-radius: 20px; color: white;")
            btn.clicked.connect(lambda ch, n=name: self.switch_app_by_name(n))
            grid.addWidget(btn, r, c)

        scroll.setWidget(grid_container)
        lay.addWidget(scroll)
        return widget

    def switch_app_by_name(self, name):
        if self.stack.currentIndex() != 0: 
            self.app_history.append(self.stack.currentIndex())
        self.app_manager.dock_to_stack(name, self.stack)

    def get_active_app_name(self):
        curr = self.stack.currentWidget()
        if curr == self.home_screen: return "Home"
        if hasattr(curr, '_app_name'): return curr._app_name
        return "Home"

    def go_home(self):
        self.app_history.clear()
        self.stack.setCurrentIndex(0)

    def go_back(self):
        if self.app_history: self.stack.setCurrentIndex(self.app_history.pop())
        else: self.stack.setCurrentIndex(0)

    def handle_navigation(self, action):
        if action == "back": self.go_back()
        elif action == "home": self.go_home()
        
    def resizeEvent(self, event):
        if self.overlay.isVisible(): self.overlay.resize(self.size())
        super().resizeEvent(event)
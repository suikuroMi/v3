import datetime
import os
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, 
                               QStackedWidget, QPushButton, QScrollArea, QWidget, QGridLayout)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap
from src.ui.utils.overlay import LoadingOverlay
from src.core.paths import get_asset_path

class ModernMioPhone(QFrame):
    def __init__(self, app_manager):
        super().__init__()
        self.app_manager = app_manager
        self.app_history = [] 
        self.setup_ui()
        self.init_home() 
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
        
        # --- STATUS BAR ---
        status_bar = QHBoxLayout()
        status_bar.setContentsMargins(20, 10, 20, 5)
        self.time_lbl = QLabel("00:00")
        self.time_lbl.setStyleSheet("color: white; font-weight: bold; font-family: monospace;")
        status_bar.addWidget(self.time_lbl)
        status_bar.addStretch()
        status_bar.addWidget(QLabel("🐺 5G", styleSheet="color: #429AFF; font-weight: bold; font-size: 10px;"))
        self.main_layout.addLayout(status_bar)
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(lambda: self.time_lbl.setText(datetime.datetime.now().strftime("%H:%M")))
        self.clock_timer.start(1000)
        
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)
        
        # --- NAVIGATION BAR ---
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
        border = "2px solid #429AFF" if is_home else "none"
        btn.setStyleSheet(f"QPushButton {{ color: white; font-size: 20px; background: transparent; border: {border}; border-radius: {size//2}px; }}")
        return btn

    def init_home(self):
        """Standardizes home screen initialization."""
        self.home_screen = self.create_home_screen()
        self.stack.addWidget(self.home_screen)

    def create_home_screen(self):
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(0)
        
        # --- HEADER SECTION (MASCOT + TEXT) ---
        header_container = QWidget()
        header_lay = QHBoxLayout(header_container)
        header_lay.setContentsMargins(30, 20, 30, 10)
        header_lay.setSpacing(10) 
        
        logo = QLabel()
        logo_path = get_asset_path("mio_logo.png")
        logo_icon = QIcon(logo_path) if logo_path else QIcon()
        logo.setPixmap(logo_icon.pixmap(QSize(40, 40)))
        logo.setStyleSheet("background: transparent;")
        
        wel = QLabel("Mio-fam")
        wel.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: 800;
                color: #429AFF;
                letter-spacing: 3px;
                background: transparent;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
        
        header_lay.addWidget(logo)
        header_lay.addWidget(wel)
        header_lay.addStretch() 
        lay.addWidget(header_container)

        # --- SEPARATOR LINE ---
        line = QFrame()
        line.setFixedHeight(2)
        line.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                                        stop:0 #429AFF, stop:0.5 rgba(66, 154, 255, 50), stop:1 transparent);
            border: none;
            margin-left: 30px;
        """)
        lay.addWidget(line)
        
        # --- APP GRID (MOBILE STYLE) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setSpacing(20)
        
        grid_items = [
            ("Chat", "chat.png"), ("Files", "Explorer.png"),
            ("System", "system.png"), ("Dev", "code.png"),
            ("Git", "git.png"), ("Database", "database.png"),
            ("Voice", "mic.png"), ("Stream", "stream.png"),
            ("Transcriber", "transcribe.png"), ("Web", "web.png"),
            ("Clock", "clock.png"), ("Settings", "settings.png"),
        ]
        
        for i, (name, icon_file) in enumerate(grid_items):
            r, c = divmod(i, 3)
            
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(5)
            
            btn = QPushButton()
            icon_path = get_asset_path(icon_file)
            if icon_path:
                btn.setIcon(QIcon(icon_path))
            
            btn.setIconSize(QSize(60, 60))
            btn.setFixedSize(70, 70)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                }
                QPushButton:hover {
                    background-color: rgba(66, 154, 255, 20);
                    border-radius: 15px;
                }
            """)
            btn.clicked.connect(lambda ch, n=name: self.switch_app_by_name(n))
            
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: white; font-size: 11px; background: transparent;")
            
            item_layout.addWidget(btn, alignment=Qt.AlignCenter)
            item_layout.addWidget(lbl, alignment=Qt.AlignCenter)
            
            grid.addWidget(item_widget, r, c)

        scroll.setWidget(grid_container)
        lay.addWidget(scroll)
        
        return widget

    def switch_app_by_name(self, name):
        if self.stack.currentIndex() != 0: self.app_history.append(self.stack.currentIndex())
        self.app_manager.dock_to_stack(name, self.stack)

    def go_home(self):
        self.app_history.clear()
        self.stack.setCurrentIndex(0)

    def go_back(self):
        if self.app_history: self.stack.setCurrentIndex(self.app_history.pop())
        else: self.stack.setCurrentIndex(0)

    def resizeEvent(self, event):
        if self.overlay.isVisible(): self.overlay.resize(self.size())
        super().resizeEvent(event)

import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QFrame, QScrollArea)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from src.core.paths import get_project_root

class BaseApp(QWidget):
    """
    Standard template for all Mio Apps.
    Handles Titles, Image Icons, and Navigation signals.
    """
    command_signal = Signal(str)      # Send command to AI
    navigation_signal = Signal(str)   # Navigate (e.g., "back", "home")

    def __init__(self, title, icon_name=None, theme_color="#3EA6FF"):
        super().__init__()
        self.theme_color = theme_color
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # --- 1. Header Bar ---
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"background: {theme_color}; border-radius: 15px 15px 0 0;")
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(10, 0, 10, 0)

        # Icon Logic (Image > Emoji)
        lbl_icon = QLabel()
        icon_path = self.get_icon_path(icon_name)
        if icon_path:
            pix = QPixmap(icon_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_icon.setPixmap(pix)
        else:
            lbl_icon.setText("📱") # Fallback

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: white; font-weight: bold; font-size: 18px;")

        # Back Button
        btn_back = QPushButton("◀")
        btn_back.setFixedSize(30, 30)
        btn_back.clicked.connect(lambda: self.navigation_signal.emit("back"))
        btn_back.setStyleSheet("color: white; background: rgba(0,0,0,0.2); border-radius: 15px; font-weight: bold;")

        header_lay.addWidget(btn_back)
        header_lay.addWidget(lbl_icon)
        header_lay.addWidget(lbl_title)
        header_lay.addStretch()

        self.layout.addWidget(header)

        # --- 2. Content Area ---
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(15, 15, 15, 15)
        self.content_layout.setSpacing(10)
        
        # Scroll support for long content
        scroll = QScrollArea()
        scroll.setWidget(self.content_area)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        self.layout.addWidget(scroll)

    def get_icon_path(self, name):
        """Resolves src/assets/icons/{name}.png"""
        if not name: return None
        root = get_project_root()
        # You need to create assets/icons folder
        path = os.path.join(root, "assets", "icons", name)
        if os.path.exists(path): return path
        return None

    def add_card_button(self, text, subtitle, cmd_or_func):
        """Helper to create nice list buttons."""
        btn = QPushButton()
        btn.setFixedHeight(70)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(30, 30, 40, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                text-align: left;
                padding: 10px;
            }}
            QPushButton:hover {{ border: 1px solid {self.theme_color}; background: rgba(40,40,50,0.9); }}
        """)
        
        # Layout inside button
        lay = QVBoxLayout(btn)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(2)
        
        l_title = QLabel(text)
        l_title.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
        l_sub = QLabel(subtitle)
        l_sub.setStyleSheet("font-size: 12px; color: #aaa; background: transparent;")
        
        lay.addWidget(l_title)
        lay.addWidget(l_sub)
        
        if isinstance(cmd_or_func, str):
            btn.clicked.connect(lambda: self.command_signal.emit(cmd_or_func))
        else:
            btn.clicked.connect(cmd_or_func)
            
        self.content_layout.addWidget(btn)
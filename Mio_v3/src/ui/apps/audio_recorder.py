from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QPushButton
from .base_app import BaseApp
from src.skills.audio_ops import AudioSkills

class VoiceApp(BaseApp):
    def __init__(self):
        super().__init__("Voice Recorder", "mic.png", "#E91E63") # Pink
        
        self.status_lbl = QLabel("Tap to Record (10s)")
        self.status_lbl.setStyleSheet("color: #aaa; font-size: 16px; margin: 20px;")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.status_lbl)
        
        self.btn_rec = QPushButton("🎙️")
        self.btn_rec.setFixedSize(120, 120)
        self.btn_rec.setStyleSheet("""
            QPushButton { background: #E91E63; border-radius: 60px; font-size: 50px; }
            QPushButton:hover { background: #C2185B; border: 4px solid white; }
            QPushButton:pressed { background: #880E4F; }
        """)
        # Center button
        self.content_layout.addWidget(self.btn_rec, alignment=Qt.AlignCenter)
        self.btn_rec.clicked.connect(self.toggle_rec)

    def toggle_rec(self):
        self.status_lbl.setText("👂 Listening... (Check Console/Chat)")
        self.btn_rec.setStyleSheet("background: #F44336; border-radius: 60px; font-size: 50px; border: 4px solid red;")
        # Send command to main window to handle threading safely
        self.command_signal.emit("[LISTEN] 10")
        QTimer.singleShot(2000, lambda: self.reset_ui())

    def reset_ui(self):
        self.status_lbl.setText("Tap to Record")
        self.btn_rec.setStyleSheet("QPushButton { background: #E91E63; border-radius: 60px; font-size: 50px; }")
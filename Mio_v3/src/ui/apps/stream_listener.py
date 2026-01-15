from PySide6.QtWidgets import QTextBrowser, QLineEdit, QPushButton, QLabel
from PySide6.QtCore import Qt
from .base import BaseApp  # <--- FIXED
from src.skills.audio_ops import AudioSkills

class StreamApp(BaseApp):
    def __init__(self):
        super().__init__("Stream Monitor", "stream.png", "#9C27B0") # Purple
        
        self.content_layout.addWidget(QLabel("YouTube/Twitch URL:", styleSheet="color:white; font-weight:bold;"))
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://youtube.com/watch?v=...")
        self.url_input.setStyleSheet("background: #222; color: white; padding: 10px; border-radius: 10px; border: 1px solid #444;")
        self.content_layout.addWidget(self.url_input)
        
        self.btn_toggle = QPushButton("START LISTENING")
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setStyleSheet("background: #3EA6FF; color: white; padding: 12px; border-radius: 10px; font-weight: bold;")
        self.btn_toggle.clicked.connect(self.toggle_stream)
        self.content_layout.addWidget(self.btn_toggle)
        
        self.logs = QTextBrowser()
        self.logs.setStyleSheet("background: #111; color: #00FF00; font-family: Consolas; font-size: 12px; border-radius: 10px; margin-top: 10px;")
        self.content_layout.addWidget(self.logs)

    def toggle_stream(self):
        if "START" in self.btn_toggle.text():
            url = self.url_input.text().strip()
            if not url: return
            
            self.logs.append("⏳ Initializing stream connection...")
            msg = AudioSkills.start_livestream_mode(url, self.append_log)
            self.logs.append(msg)
            
            if "Active" in msg:
                self.btn_toggle.setText("STOP LISTENING")
                self.btn_toggle.setStyleSheet("background: #F44336; color: white; padding: 12px; border-radius: 10px; font-weight: bold;")
        else:
            AudioSkills.stop_continuous_mode()
            self.btn_toggle.setText("START LISTENING")
            self.btn_toggle.setStyleSheet("background: #3EA6FF; color: white; padding: 12px; border-radius: 10px; font-weight: bold;")
            self.logs.append("🛑 Stream stopped.")

    def append_log(self, text):
        self.logs.append(text)
        # Auto scroll
        self.logs.verticalScrollBar().setValue(self.logs.verticalScrollBar().maximum())
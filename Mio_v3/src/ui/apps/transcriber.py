from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton
from .base_app import BaseApp
from src.skills.audio_ops import AudioSkills

class TranscriberApp(BaseApp):
    def __init__(self):
        super().__init__("Transcriber", "transcribe.png", "#673AB7") # Deep Purple
        
        self.lbl_status = QLabel("Select an audio or video file to generate a text transcript.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #ccc; font-size: 14px; margin: 20px;")
        self.content_layout.addWidget(self.lbl_status)
        
        btn = QPushButton("📂 Select File")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("background: #673AB7; color: white; padding: 20px; border-radius: 15px; font-size: 18px; font-weight: bold;")
        btn.clicked.connect(self.select_file)
        self.content_layout.addWidget(btn)

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Media", "", "Audio/Video (*.mp3 *.wav *.mp4 *.mkv *.m4a)")
        if path:
            self.lbl_status.setText(f"⏳ Transcribing...\n{path}\n\n(This may take a moment)")
            # In a real app, threading is better, but this triggers the skill
            self.command_signal.emit(f"[TRANSCRIBE] {path}")
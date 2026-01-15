from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QGridLayout, QFrame, QLabel
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QCursor

class ControlPanel(QWidget):
    # Signals to tell the Main Window what to do
    command_signal = Signal(str)  # Sends "[COMMAND]" to Brain
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        # Background Frame (Glass look)
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 200);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 10px;
                font-size: 24px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 50);
            }
            QLabel {
                color: rgba(255, 255, 255, 150);
                font-size: 10px;
                font-weight: bold;
                margin-bottom: 5px;
            }
        """)
        self.layout.addWidget(self.frame)
        
        # Grid for Buttons
        self.grid = QGridLayout(self.frame)
        self.grid.setSpacing(10)
        
        # --- BUTTONS ---
        
        # 1. Microphone (The Big Button)
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setToolTip("Listen (10s)")
        self.mic_btn.clicked.connect(lambda: self.command_signal.emit("[LISTEN]"))
        self.grid.addWidget(self.mic_btn, 0, 0, 1, 2) # Spans 2 columns
        
        # 2. Utilities
        self.add_btn("📸", "Screenshot", "[SCREENSHOT]", 1, 0)
        self.add_btn("📂", "Files", "[OPEN] .", 1, 1)
        
        # 3. Dev / Settings
        self.add_btn("⚙️", "Settings", "[SETTINGS] list", 2, 0)
        self.add_btn("🏥", "Health", "[DB_INFO] data/memory.db", 2, 1) # Example usage
        
        # 4. Translation Toggle (Placeholder for now)
        self.add_btn("🌐", "Translate Mode", "[PERSONA] sensei", 3, 0)
        self.add_btn("🧹", "Clear Chat", "CLEAR", 3, 1)

    def add_btn(self, icon, tooltip, command, row, col):
        btn = QPushButton(icon)
        btn.setToolTip(tooltip)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.clicked.connect(lambda: self.command_signal.emit(command))
        self.grid.addWidget(btn, row, col)

    def set_mic_active(self, active):
        """Visual feedback for recording"""
        if active:
            self.mic_btn.setStyleSheet("background-color: rgba(255, 50, 50, 150); border: 2px solid red;")
        else:
            self.mic_btn.setStyleSheet("")
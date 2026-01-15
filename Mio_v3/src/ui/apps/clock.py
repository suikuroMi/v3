from PySide6.QtCore import QTimer, QTime, Qt
from PySide6.QtWidgets import QLabel, QTimeEdit, QPushButton, QMessageBox
from .base import BaseApp  # <--- FIXED
from src.skills.productivity import ProductivitySkills

class ClockApp(BaseApp):
    def __init__(self):
        super().__init__("Focus Timer", "clock.png", "#FF9800") # Orange
        
        # Big Digital Display
        self.lbl_display = QLabel("00:00")
        self.lbl_display.setStyleSheet("font-size: 60px; color: white; font-weight: bold; font-family: monospace;")
        self.lbl_display.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.lbl_display)
        
        self.content_layout.addSpacing(20)
        
        # Input
        self.content_layout.addWidget(QLabel("Set Duration (Min:Sec):", styleSheet="color:#aaa;"))
        self.time_input = QTimeEdit()
        self.time_input.setDisplayFormat("mm:ss")
        self.time_input.setTime(QTime(0, 25, 0)) # Default 25m
        self.time_input.setStyleSheet("font-size: 20px; color: white; background: #333; padding: 10px; border-radius: 10px;")
        self.content_layout.addWidget(self.time_input)
        
        self.content_layout.addSpacing(20)

        # Start Button
        self.btn_start = QPushButton("Start Focus Session")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet("background: #4CAF50; color: white; padding: 15px; border-radius: 10px; font-weight: bold; font-size: 16px;")
        self.btn_start.clicked.connect(self.start_timer)
        self.content_layout.addWidget(self.btn_start)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tick)
        self.remaining_seconds = 0

    def start_timer(self):
        t = self.time_input.time()
        self.remaining_seconds = (t.minute() * 60) + t.second()
        if self.remaining_seconds <= 0: return

        self.timer.start(1000)
        
        self.btn_start.setText("Stop Timer")
        self.btn_start.clicked.disconnect()
        self.btn_start.clicked.connect(self.stop_timer)
        self.btn_start.setStyleSheet("background: #F44336; color: white; padding: 15px; border-radius: 10px; font-weight: bold;")
        
        # Trigger backend for logging
        ProductivitySkills.start_focus_timer(str(t.minute()))

    def stop_timer(self):
        self.timer.stop()
        self.lbl_display.setText("00:00")
        
        self.btn_start.setText("Start Focus Session")
        self.btn_start.clicked.disconnect()
        self.btn_start.clicked.connect(self.start_timer)
        self.btn_start.setStyleSheet("background: #4CAF50; color: white; padding: 15px; border-radius: 10px; font-weight: bold;")

    def update_tick(self):
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            m, s = divmod(self.remaining_seconds, 60)
            self.lbl_display.setText(f"{m:02d}:{s:02d}")
        else:
            self.stop_timer()
            self.command_signal.emit("Timer finished!") # Let brain know
            
            msg = QMessageBox()
            msg.setWindowTitle("Time's Up!")
            msg.setText("Focus session complete! Take a break. 🐺")
            msg.setStyleSheet("QMessageBox { background: #222; color: white; } QLabel { color: white; }")
            msg.exec()
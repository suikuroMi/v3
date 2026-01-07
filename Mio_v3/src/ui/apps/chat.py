from PySide6.QtWidgets import QTextBrowser, QLineEdit, QPushButton, QFrame, QHBoxLayout
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import Qt, Signal
from .base_app import BaseApp

class ChatApp(BaseApp):
    request_pose = Signal(str) # To change avatar

    def __init__(self, brain_engine):
        super().__init__("Mio Chat", "chat.png", "#3EA6FF")
        self.brain = brain_engine
        
        # Chat Display
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background: rgba(30, 30, 40, 0.5);
                border: none;
                border-radius: 15px;
                color: #e0e0e0;
                font-size: 14px;
                padding: 10px;
            }
        """)
        self.content_layout.addWidget(self.chat_display)
        
        # Input Area
        input_container = QFrame()
        input_container.setFixedHeight(60)
        input_container.setStyleSheet("background: rgba(40, 40, 50, 0.9); border-radius: 30px; margin-bottom: 5px;")
        input_lay = QHBoxLayout(input_container)
        input_lay.setContentsMargins(10, 5, 5, 5)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.setStyleSheet("background: transparent; border: none; color: white; font-size: 14px;")
        self.input_field.returnPressed.connect(self.send_message)
        
        btn_send = QPushButton("➤")
        btn_send.setFixedSize(40, 40)
        btn_send.setCursor(Qt.PointingHandCursor)
        btn_send.clicked.connect(self.send_message)
        btn_send.setStyleSheet("""
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3EA6FF, stop:1 #6B46C1); 
                color: white; border-radius: 20px; font-weight: bold; 
            }
            QPushButton:hover { background: #4EB6FF; }
        """)
        
        input_lay.addWidget(self.input_field)
        input_lay.addWidget(btn_send)
        
        self.content_layout.addWidget(input_container)

    def send_message(self):
        text = self.input_field.text().strip()
        if not text: return
        
        self.append_chat("You", text)
        self.input_field.clear()
        
        # Send to main window handler via signal, or handle here if threading passed
        self.command_signal.emit(text) 
        
    def append_chat(self, user, text):
        if user == "You":
            align, bg, col = "right", "rgba(62, 166, 255, 0.2)", "#3EA6FF"
        elif user == "Mio":
            align, bg, col = "left", "rgba(255, 107, 139, 0.2)", "#FF6B8B"
        else:
            align, bg, col = "center", "rgba(100, 100, 100, 0.2)", "#AAAAAA"
        
        html = f"""
        <div style='text-align: {align}; margin: 8px 0;'>
            <div style='display: inline-block; background: {bg}; border-radius: 15px; padding: 10px 15px; max-width: 85%; border: 1px solid {col}40;'>
                <div style='color: {col}; font-weight: bold; font-size: 10px; margin-bottom: 4px;'>{user}</div>
                <div style='color: #e0e0e0; font-size: 14px;'>{text}</div>
            </div>
        </div>"""
        self.chat_display.append(html)
        self.chat_display.moveCursor(QTextCursor.End)
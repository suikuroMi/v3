from PySide6.QtWidgets import QLineEdit, QPushButton, QLabel
from .base import BaseApp  # <--- FIXED

class WebApp(BaseApp):
    def __init__(self):
        super().__init__("Web & Search", "globe.png", "#03A9F4") # Light Blue
        
        self.content_layout.addWidget(QLabel("Google Search:", styleSheet="color:#aaa;"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search query...")
        self.search_input.setStyleSheet("background: #333; color: white; padding: 10px; border-radius: 10px;")
        self.search_input.returnPressed.connect(self.do_search)
        self.content_layout.addWidget(self.search_input)
        
        btn_search = QPushButton("Search")
        btn_search.setStyleSheet("background: #03A9F4; color: white; padding: 8px; border-radius: 8px;")
        btn_search.clicked.connect(self.do_search)
        self.content_layout.addWidget(btn_search)
        
        self.content_layout.addSpacing(20)
        
        self.content_layout.addWidget(QLabel("Media Downloader:", styleSheet="color:#aaa;"))
        self.dl_input = QLineEdit()
        self.dl_input.setPlaceholderText("Video URL...")
        self.dl_input.setStyleSheet("background: #333; color: white; padding: 10px; border-radius: 10px;")
        self.content_layout.addWidget(self.dl_input)
        
        btn_dl = QPushButton("Download")
        btn_dl.setStyleSheet("background: #FF5722; color: white; padding: 8px; border-radius: 8px;")
        btn_dl.clicked.connect(self.do_download)
        self.content_layout.addWidget(btn_dl)

    def do_search(self):
        q = self.search_input.text()
        if q: self.command_signal.emit(f"[SEARCH] {q}")

    def do_download(self):
        url = self.dl_input.text()
        if url: self.command_signal.emit(f"[DOWNLOAD] {url}")
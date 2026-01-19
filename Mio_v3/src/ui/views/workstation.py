from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QFrame, 
                               QPushButton, QSplitter, QTabWidget, QTextEdit, QLabel)
from PySide6.QtCore import Qt
from src.ui.utils.overlay import LoadingOverlay

class WorkstationWindow(QWidget):
    def __init__(self, app_manager):
        super().__init__()
        self.app_manager = app_manager
        self.current_app_name = None 
        
        self.resize(1300, 850)
        self.setStyleSheet("background: #1e1e2e; color: #cdd6f4;")
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = self.create_sidebar()
        main_layout.addWidget(self.sidebar)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(2)
        
        self.left_pane = QFrame()
        self.left_layout = QVBoxLayout(self.left_pane)
        self.left_layout.setContentsMargins(0,0,0,0)
        
        self.right_pane = QTabWidget()
        self.right_pane.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; }
            QTabBar::tab { background: #2b2b3b; color: #aaa; padding: 8px; }
            QTabBar::tab:selected { background: #3EA6FF; color: white; }
        """)
        
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("font-family: Consolas; font-size: 12px; background: #111; color: #0f0;")
        self.right_pane.addTab(self.console, "🖥️ System Output")
        
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("File content...")
        self.editor.setStyleSheet("font-family: Consolas; font-size: 13px; background: #222; color: #fff;")
        self.right_pane.addTab(self.editor, "📝 Editor")

        self.splitter.addWidget(self.left_pane)
        self.splitter.addWidget(self.right_pane)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(self.splitter)
        
        # Overlay
        self.overlay = LoadingOverlay(self)

    def resizeEvent(self, event):
        if self.overlay.isVisible():
            self.overlay.resize(self.size())
        super().resizeEvent(event)

    def create_sidebar(self):
        bar = QFrame()
        bar.setFixedWidth(60)
        bar.setStyleSheet("background: #11111b;")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(5, 10, 5, 10)
        lay.setAlignment(Qt.AlignTop)
        
        # UPDATED BUTTON LIST
        # Included core apps + new tools
        btns = [
            ("💬", "Chat"), 
            ("📂", "Files"), 
            ("🌐", "Web"),          # New
            ("🗣️", "Translator"),   # New (Points to StreamApp)
            ("⬇️", "Downloader"),   # New
            ("👩‍💻", "Dev"),
            ("🐙", "Git"), 
            ("📊", "Database"), 
            ("⚙️", "Settings")
        ]
        
        for icon, name in btns:
            b = QPushButton(icon)
            b.setFixedSize(50, 50)
            b.setToolTip(name)
            b.setStyleSheet("""
                QPushButton { background: transparent; border: none; font-size: 24px; border-radius: 10px; }
                QPushButton:hover { background: #333; }
            """)
            b.clicked.connect(lambda c, n=name: self.switch_view(n))
            lay.addWidget(b)
            
        lay.addStretch()
        return bar

    def switch_view(self, app_name):
        # Clear existing view
        if self.left_layout.count():
            child = self.left_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        # Dock new app
        if self.app_manager.dock_to_layout(app_name, self.left_layout):
            self.current_app_name = app_name
            self.log(f"Switched to {app_name}")
        else:
            self.log(f"Error: Could not load {app_name}")

    def log(self, text):
        self.console.append(text.strip())
        if self.console.document().lineCount() > 1000:
             cursor = self.console.textCursor()
             cursor.movePosition(cursor.Start)
             cursor.movePosition(cursor.Down, cursor.KeepAnchor, 100)
             cursor.removeSelectedText()
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class LoadingOverlay(QWidget):
    """Semi-transparent overlay to show processing state."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        self.label = QLabel("🧠 Thinking...")
        self.label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 180);
            color: white;
            padding: 10px 20px;
            border-radius: 15px;
            font-weight: bold;
            font-size: 14px;
        """)
        layout.addWidget(self.label)
        self.hide()

    def show_msg(self, msg="Thinking..."):
        self.label.setText(f"🧠 {msg}")
        self.resize(self.parent().size())
        self.show()
        self.raise_()
import os
import re
import json
import sys
import markdown2
from datetime import datetime
from functools import lru_cache

from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit, QPushButton, 
                               QFrame, QWidget, QLabel, QScrollArea, QSizePolicy, QFileDialog, 
                               QLayout, QMenu, QToolButton, QApplication, QDialog, QComboBox, QProgressBar)
from PySide6.QtCore import (Qt, Signal, QSize, QTimer, QUrl, QEvent, QRegularExpression, 
                            QProcess, QObject)
from PySide6.QtGui import (QTextCursor, QDesktopServices, QColor, QPalette, QIcon, 
                           QDragEnterEvent, QDropEvent, QAction, QPixmap, QTextCharFormat, QTextDocument)

from .base import BaseApp

# --- SAFE IMPORT FOR SERVICE MANAGER ---
try:
    from .files import ServiceManager
except ImportError:
    class ServiceManager:
        _instance = None
        def __new__(cls):
            if cls._instance is None: cls._instance = super().__new__(cls)
            return cls._instance
        def __init__(self): self.highlighter_pool = None

# ============================================================================
# 1. THEME MANAGER
# ============================================================================

class ThemeManager(QObject):
    theme_changed = Signal()

    THEMES = {
        "mocha": {
            "bg": "#1e1e2e", "text": "#cdd6f4",
            "user_bg": "rgba(137, 180, 250, 0.15)", "user_col": "#89b4fa",
            "mio_bg": "rgba(243, 139, 168, 0.15)", "mio_col": "#f38ba8",
            "sys_bg": "rgba(166, 173, 200, 0.1)", "sys_col": "#a6adc8",
            "tool_bg": "rgba(166, 227, 161, 0.15)", "tool_col": "#a6e3a1",
            "code_bg": "#11111b", "console_bg": "#181825",
            "chip_bg": "#313244", "chip_border": "#45475a", "input_bg": "rgba(30, 30, 46, 0.9)"
        },
        "latte": {
            "bg": "#eff1f5", "text": "#4c4f69",
            "user_bg": "rgba(30, 102, 245, 0.1)", "user_col": "#1e66f5",
            "mio_bg": "rgba(234, 118, 203, 0.1)", "mio_col": "#ea76cb",
            "sys_bg": "rgba(156, 160, 176, 0.1)", "sys_col": "#9ca0b0",
            "tool_bg": "rgba(64, 160, 43, 0.1)", "tool_col": "#40a02b",
            "code_bg": "#e6e9ef", "console_bg": "#dce0e8",
            "chip_bg": "#e6e9ef", "chip_border": "#dce0e8", "input_bg": "rgba(255, 255, 255, 0.9)"
        }
    }
    
    def __init__(self):
        super().__init__()
        self.current_theme = "mocha"

    @property
    def current(self):
        return self.THEMES[self.current_theme]

    def toggle_theme(self):
        self.current_theme = "latte" if self.current_theme == "mocha" else "mocha"
        self.theme_changed.emit()

theme_manager = ThemeManager()

# ============================================================================
# 2. UI COMPONENTS
# ============================================================================

class ThinkingWidget(QFrame):
    """Collapsible widget showing AI thought process logs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_collapsed = True
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)
        
        header = QHBoxLayout()
        self.icon_lbl = QLabel("⚙️")
        self.status_lbl = QLabel("Thinking...")
        
        self.toggle_btn = QPushButton("▼")
        self.toggle_btn.setFixedSize(20, 20)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.clicked.connect(self.toggle_details)
        self.toggle_btn.setStyleSheet("background: transparent; border: none;")
        
        header.addWidget(self.icon_lbl)
        header.addWidget(self.status_lbl)
        header.addStretch()
        header.addWidget(self.toggle_btn)
        self.layout.addLayout(header)
        
        self.log_view = QTextBrowser()
        self.log_view.setVisible(False)
        self.log_view.setFixedHeight(100)
        self.log_view.setStyleSheet("background: transparent; border: none; font-family: Consolas; font-size: 11px;")
        self.layout.addWidget(self.log_view)
        
        theme_manager.theme_changed.connect(self.update_style)
        self.update_style() # Call last

    def update_style(self):
        t = theme_manager.current
        self.setStyleSheet(f"background: rgba(30, 30, 40, 0.3); border-radius: 10px; border: 1px dashed {t['sys_col']}40;")
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setStyleSheet(f"color: {t['sys_col']}; font-style: italic;")
            self.log_view.setStyleSheet(f"color: {t['sys_col']}; background: transparent; border: none; font-family: Consolas; font-size: 11px;")

    def add_log(self, text):
        self.status_lbl.setText(text)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{timestamp}] {text}")
        self.log_view.moveCursor(QTextCursor.End)

    def toggle_details(self):
        self.is_collapsed = not self.is_collapsed
        self.log_view.setVisible(not self.is_collapsed)
        self.toggle_btn.setText("▼" if self.is_collapsed else "▲")

    def mark_done(self):
        self.status_lbl.setText("Finished thinking.")
        self.icon_lbl.setText("✅")
        if not self.is_collapsed: self.toggle_details()

class AIContextBar(QFrame):
    """Top bar with Model Switcher and Token Tracking."""
    clear_requested = Signal()
    model_changed = Signal(str)
    export_requested = Signal()
    import_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(35)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        # Model Switcher
        self.model_combo = QComboBox()
        self.model_combo.addItems(["Mio-v3 (Fast)", "Mio-v3 (Pro)", "Mio-v3 (Reasoning)"])
        self.model_combo.currentTextChanged.connect(self.model_changed.emit)
        self.model_combo.setFixedWidth(150)
        
        # Token Usage
        self.token_bar = QProgressBar()
        self.token_bar.setRange(0, 8192) # Max context
        self.token_bar.setValue(0)
        self.token_bar.setFixedWidth(100)
        self.token_bar.setTextVisible(False)
        self.token_bar.setStyleSheet("QProgressBar::chunk { background-color: #89b4fa; border-radius: 2px; }")
        
        self.token_lbl = QLabel("0 / 8k")
        
        # Tools
        btn_export = QPushButton("💾")
        btn_export.setToolTip("Export Conversation")
        btn_export.clicked.connect(self.export_requested.emit)
        
        btn_import = QPushButton("📂")
        btn_import.setToolTip("Import Conversation")
        btn_import.clicked.connect(self.import_requested.emit)
        
        btn_clear = QPushButton("🧹")
        btn_clear.setToolTip("Clear Context")
        btn_clear.clicked.connect(self.clear_requested.emit)
        
        for b in [btn_export, btn_import, btn_clear]:
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("background: transparent; border: none; font-size: 14px;")
            b.setFixedSize(30, 30)
        
        layout.addWidget(QLabel("🧠"))
        layout.addWidget(self.model_combo)
        layout.addSpacing(15)
        layout.addWidget(QLabel("🎫"))
        layout.addWidget(self.token_bar)
        layout.addWidget(self.token_lbl)
        layout.addStretch()
        layout.addWidget(btn_export)
        layout.addWidget(btn_import)
        layout.addWidget(btn_clear)
        
        theme_manager.theme_changed.connect(self.update_style)
        self.update_style() # Call AFTER creating widgets

    def update_style(self):
        t = theme_manager.current
        self.setStyleSheet(f"background: {t['bg']}; border-bottom: 1px solid {t['chip_border']};")
        self.model_combo.setStyleSheet(f"background: {t['chip_bg']}; color: {t['text']}; border: 1px solid {t['chip_border']}; border-radius: 5px;")
        self.token_lbl.setStyleSheet(f"color: {t['sys_col']}; font-size: 11px;")

    def update_tokens(self, count):
        self.token_bar.setValue(count)
        self.token_lbl.setText(f"{count} / 8k")
        if count > 6000: col = "#f38ba8" 
        elif count > 4000: col = "#fab387" 
        else: col = "#89b4fa" 
        self.token_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {col}; border-radius: 2px; }}")

class CodeExecutionWidget(QFrame):
    """
    V8: Executable Code Block with Console Output.
    """
    def __init__(self, code, lang="python", parent=None):
        super().__init__(parent)
        self.code = code
        self.lang = lang
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setStyleSheet(f"background: {theme_manager.current['chip_bg']}; border-top-left-radius: 5px; border-top-right-radius: 5px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 5, 10, 5)
        
        h_layout.addWidget(QLabel(f"🐍 {lang}"))
        h_layout.addStretch()
        
        self.btn_run = QPushButton("▶ Run")
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.clicked.connect(self.run_code)
        self.btn_run.setStyleSheet("background: #a6e3a1; color: #1e1e2e; border-radius: 3px; padding: 2px 8px; font-weight: bold;")
        
        h_layout.addWidget(self.btn_run)
        self.layout.addWidget(header)
        
        # Code View
        self.code_view = QTextBrowser()
        self.code_view.setPlainText(code)
        self.code_view.setStyleSheet(f"background: {theme_manager.current['code_bg']}; color: #cdd6f4; font-family: Consolas; border: none; padding: 10px;")
        self.code_view.setFixedHeight(min(200, self.code_view.document().size().height() + 20))
        self.layout.addWidget(self.code_view)
        
        # Console Output
        self.console = QTextBrowser()
        self.console.setVisible(False)
        self.console.setStyleSheet(f"background: {theme_manager.current['console_bg']}; color: #a6adc8; font-family: Consolas; border-top: 1px solid #45475a; padding: 10px;")
        self.layout.addWidget(self.console)

    def run_code(self):
        if self.lang != "python": 
            self.show_output("Error: Only Python execution is supported currently.")
            return
            
        self.btn_run.setText("Running...")
        self.btn_run.setEnabled(False)
        self.console.clear()
        self.console.setVisible(True)
        
        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._handle_finished)
        
        self.process.start("python", ["-c", self.code])

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.console.append(data)

    def _handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.console.append(f"<span style='color: #f38ba8;'>{data}</span>")

    def _handle_finished(self):
        self.btn_run.setText("▶ Run")
        self.btn_run.setEnabled(True)
        self.console.append(f"<span style='color: #a6e3a1;'>Process finished with code {self.process.exitCode()}</span>")

    def show_output(self, text):
        self.console.setVisible(True)
        self.console.setText(text)

class ImagePreviewDialog(QDialog):
    """Lightbox for viewing full-size images."""
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(path))
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setStyleSheet("background: rgba(0,0,0,0.9);")
        
        layout = QVBoxLayout(self)
        lbl = QLabel()
        pix = QPixmap(path)
        screen_size = QApplication.primaryScreen().size()
        if pix.width() > screen_size.width() * 0.8 or pix.height() > screen_size.height() * 0.8:
            pix = pix.scaled(screen_size * 0.8, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        lbl.setPixmap(pix)
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        
        lbl.mousePressEvent = lambda e: self.close()

class ChatBubble(QFrame):
    _DANGEROUS_TAG_REGEX = re.compile(r'<(script|iframe|object|embed|style|meta|link)[^>]*>.*?</\1>', re.DOTALL)
    _EVENT_HANDLER_REGEX = re.compile(r'\son\w+="[^"]*"')
    _DANGEROUS_HREF_REGEX = re.compile(r'href="(javascript:|file:|data:)[^"]*"')
    _CODE_BLOCK_REGEX = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)

    regenerate_requested = Signal()

    def __init__(self, user, text, is_markdown=False, is_image=False, is_tool=False):
        super().__init__()
        self.user = user
        self.full_text = text
        self.is_image = is_image
        self.is_tool = is_tool
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        self.lbl_user = QLabel(user)
        layout.addWidget(self.lbl_user)
        
        if is_image and os.path.exists(text):
            self.content_widget = QLabel()
            pix = QPixmap(text).scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.content_widget.setPixmap(pix)
            self.content_widget.setCursor(Qt.PointingHandCursor)
            self.content_widget.mousePressEvent = lambda e: ImagePreviewDialog(text, self.window()).show()
            layout.addWidget(self.content_widget)
        elif self._has_code_block(text) and user == "Mio" and not is_tool:
            self._render_mixed_content(text, layout)
        else:
            self.content_widget = QTextBrowser()
            self.content_widget.setOpenExternalLinks(True)
            self.content_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.update_content(text, is_markdown)
            layout.addWidget(self.content_widget)
        
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        theme_manager.theme_changed.connect(self.update_style)
        self.update_style() # Call last

    def _has_code_block(self, text):
        return "```" in text

    def _render_mixed_content(self, text, layout):
        parts = self._CODE_BLOCK_REGEX.split(text)
        if parts[0].strip():
            tb = self._create_text_browser(parts[0])
            layout.addWidget(tb)
            
        i = 1
        while i < len(parts):
            lang = parts[i] or "text"
            code = parts[i+1]
            next_text = parts[i+2] if i+2 < len(parts) else ""
            
            code_widget = CodeExecutionWidget(code, lang)
            layout.addWidget(code_widget)
            
            if next_text.strip():
                tb = self._create_text_browser(next_text)
                layout.addWidget(tb)
            i += 3

    def _create_text_browser(self, text):
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tb.setStyleSheet("background: transparent; border: none; color: #cdd6f4; font-size: 14px;")
        content = self._render_markdown(text)
        tb.setHtml(self._sanitize_html(content))
        doc_h = tb.document().size().height()
        tb.setFixedHeight(int(doc_h + 10))
        return tb

    def update_style(self):
        t = theme_manager.current
        if self.user == "You":
            bg, col = t["user_bg"], t["user_col"]
        elif self.user == "Mio":
            bg, col = t["mio_bg"], t["mio_col"]
        elif self.is_tool:
            bg, col = t["tool_bg"], t["tool_col"]
        else:
            bg, col = t["sys_bg"], t["sys_col"]
            
        self.setStyleSheet(f"background: {bg}; border-radius: 15px; border: 1px solid {col}40;")
        self.lbl_user.setStyleSheet(f"color: {col}; font-weight: bold; font-size: 11px; margin-bottom: 4px; background: transparent; border: none;")
        
        if isinstance(getattr(self, 'content_widget', None), QTextBrowser):
            self.content_widget.setStyleSheet(f"background: transparent; border: none; color: {t['text']}; font-size: 14px;")

    def update_content(self, text, is_markdown):
        if self.is_image: return
        if hasattr(self, 'content_widget') and isinstance(self.content_widget, QTextBrowser):
            self.full_text = text
            content = self._render_markdown(text) if is_markdown else text.replace("\n", "<br>")
            content = self._sanitize_html(content)
            self.content_widget.setHtml(content)
            self.content_widget.document().adjustSize()
            doc_h = self.content_widget.document().size().height()
            self.content_widget.setFixedHeight(int(doc_h + 20))
            self.setFixedHeight(int(doc_h + 60))

    def show_context_menu(self, pos):
        menu = QMenu(self)
        t = theme_manager.current
        menu.setStyleSheet(f"QMenu {{ background: {t['chip_bg']}; color: {t['text']}; border: 1px solid {t['chip_border']}; }}")
        
        act_copy = QAction("📋 Copy Text", self)
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(self.full_text))
        menu.addAction(act_copy)
        
        if self.user == "Mio":
            act_regen = QAction("🔄 Regenerate", self)
            act_regen.triggered.connect(self.regenerate_requested.emit)
            menu.addAction(act_regen)
        
        menu.exec(self.mapToGlobal(pos))

    @classmethod
    def _sanitize_html(cls, html):
        html = cls._DANGEROUS_TAG_REGEX.sub('', html)
        html = cls._EVENT_HANDLER_REGEX.sub('', html)
        html = cls._DANGEROUS_HREF_REGEX.sub('href="#"', html)
        return html

    @staticmethod
    @lru_cache(maxsize=100)
    def _render_markdown(text):
        return markdown2.markdown(text, extras=["fenced-code-blocks", "tables"])

# ============================================================================
# 3. CHAT DISPLAY AREA
# ============================================================================

class ChatDisplayArea(QScrollArea):
    MAX_MESSAGES = 500
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setStyleSheet("background: transparent; border: none;")
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(15)
        self.layout.addStretch()
        self.setWidget(self.container)

    def add_message(self, user, text, is_markdown=False, is_image=False, is_tool=False):
        if self.layout.count() > self.MAX_MESSAGES: self._cleanup_old_messages()
        bubble = ChatBubble(user, text, is_markdown, is_image, is_tool)
        self._insert_widget(bubble, user)
        return bubble

    def add_widget(self, widget):
        self.layout.insertWidget(self.layout.count()-1, widget)
        self._scroll_to_bottom()

    def _cleanup_old_messages(self):
        for _ in range(50):
            if self.layout.count() <= 1: break
            item = self.layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def _insert_widget(self, widget, user):
        wrapper = QWidget()
        w_layout = QHBoxLayout(wrapper)
        w_layout.setContentsMargins(0,0,0,0)
        if user == "You": 
            w_layout.addStretch(); w_layout.addWidget(widget)
        elif user == "Mio": 
            w_layout.addWidget(widget); w_layout.addStretch()
        else: 
            w_layout.addStretch(); w_layout.addWidget(widget); w_layout.addStretch()
        self.layout.insertWidget(self.layout.count()-1, wrapper)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        QTimer.singleShot(10, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))

    def highlight_text(self, text):
        count = 0
        for i in range(self.layout.count()):
            item = self.layout.itemAt(i)
            if not item or not item.widget(): continue
            wrapper = item.widget()
            bubble = wrapper.findChild(ChatBubble)
            if bubble and not bubble.is_image and hasattr(bubble, 'content_widget') and isinstance(bubble.content_widget, QTextBrowser):
                doc = bubble.content_widget.document()
                cursor = QTextCursor(doc)
                cursor.select(QTextCursor.Document)
                fmt = QTextCharFormat()
                fmt.setBackground(Qt.transparent)
                cursor.mergeCharFormat(fmt)
                if not text: continue
                highlight_fmt = QTextCharFormat()
                highlight_fmt.setBackground(QColor("#f1fa8c"))
                highlight_fmt.setForeground(QColor("#000000"))
                cursor = doc.find(text)
                while not cursor.isNull():
                    cursor.mergeCharFormat(highlight_fmt)
                    cursor = doc.find(text, cursor)
                    count += 1
        return count

class ChatSearchBar(QFrame):
    search_requested = Signal(str)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.hide()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.input = QLineEdit()
        self.input.setPlaceholderText("Find in chat...")
        self.input.setStyleSheet("background: transparent; border: none; color: white;")
        self.input.returnPressed.connect(lambda: self.search_requested.emit(self.input.text()))
        
        btn_close = QPushButton("×")
        btn_close.setFixedSize(30, 30)
        btn_close.clicked.connect(self.hide_bar)
        btn_close.setStyleSheet("background: transparent; color: #f38ba8; font-weight: bold; border: none;")
        
        layout.addWidget(QLabel("🔍"))
        layout.addWidget(self.input)
        layout.addWidget(btn_close)
        
        theme_manager.theme_changed.connect(self.update_style)
        self.update_style() # Call after setup

    def update_style(self):
        t = theme_manager.current
        self.setStyleSheet(f"background: {t['input_bg']}; border-bottom: 1px solid {t['chip_border']};")
        self.input.setStyleSheet(f"background: transparent; border: none; color: {t['text']};")

    def show_bar(self):
        self.show()
        self.input.setFocus()

    def hide_bar(self):
        self.hide()
        self.input.clear()
        self.closed.emit()

class DropContainer(QFrame):
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [f for f in files if os.path.exists(f)]
        if valid_files: self.files_dropped.emit(valid_files)
        event.acceptProposedAction()

class AttachmentChip(QFrame):
    removed = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.setFixedHeight(30)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 5, 0)
        
        name = os.path.basename(path)
        if len(name) > 15: name = name[:12] + "..."
        
        lbl = QLabel(f"📎 {name}")
        self.lbl = lbl
        
        btn_close = QPushButton("×")
        btn_close.setFixedSize(20, 20)
        btn_close.clicked.connect(lambda: self.removed.emit(self.path))
        btn_close.setStyleSheet("background: transparent; color: #f38ba8; font-weight: bold; border: none;")
        
        layout.addWidget(lbl)
        layout.addWidget(btn_close)
        
        theme_manager.theme_changed.connect(self.update_style)
        self.update_style()

    def update_style(self):
        t = theme_manager.current
        self.setStyleSheet(f"background: {t['chip_bg']}; border-radius: 15px; margin-right: 5px; border: 1px solid {t['chip_border']};")
        self.lbl.setStyleSheet(f"color: {t['text']}; border: none; background: transparent;")

class ChatApp(BaseApp):
    request_pose = Signal(str) 

    def __init__(self, brain_engine):
        super().__init__("Mio Chat", "chat.png", "#3EA6FF")
        self.brain = brain_engine
        try: self.services = ServiceManager()
        except: self.services = None
        self.attachments = []
        self.current_thinking_widget = None
        self.current_streaming_bubble = None
        self._stream_buffer = ""
        self.token_usage = 0
        self.MAX_FILE_SIZE = 10 * 1024 * 1024 
        self.ALLOWED_EXT = {'.txt', '.py', '.js', '.md', '.json', '.png', '.jpg', '.pdf', '.log'}
        self.messages = [] 
        self._init_ui()

    def _init_ui(self):
        self.context_bar = AIContextBar()
        self.context_bar.clear_requested.connect(self.clear_context)
        self.context_bar.export_requested.connect(self.export_chat)
        self.context_bar.import_requested.connect(self.import_chat)
        self.content_layout.addWidget(self.context_bar)
        
        self.search_bar = ChatSearchBar()
        self.search_bar.search_requested.connect(self.find_in_chat)
        self.search_bar.closed.connect(lambda: self.find_in_chat("")) 
        self.content_layout.addWidget(self.search_bar)
        
        self.chat_area = ChatDisplayArea()
        self.content_layout.addWidget(self.chat_area)
        
        self.input_container = DropContainer() 
        t = theme_manager.current
        self.input_container.setStyleSheet(f"background: {t['input_bg']}; border-radius: 20px; border: 1px solid {t['chip_border']};")
        self.input_container.files_dropped.connect(self._handle_dropped_files)
        
        input_lay = QVBoxLayout(self.input_container)
        input_lay.setContentsMargins(10, 10, 10, 10)
        
        self.attach_area = QWidget()
        self.attach_layout = QHBoxLayout(self.attach_area)
        self.attach_layout.setContentsMargins(0,0,0,0)
        self.attach_layout.addStretch()
        self.attach_area.setVisible(False)
        input_lay.addWidget(self.attach_area)
        
        row = QHBoxLayout()
        self.btn_attach = QPushButton("📎")
        self.btn_attach.setFixedSize(30, 30)
        self.btn_attach.setCursor(Qt.PointingHandCursor)
        self.btn_attach.clicked.connect(self.browse_file)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Message Mio... (Drag files here)")
        self.input_field.setStyleSheet("background: transparent; border: none; color: white; font-size: 14px;")
        self.input_field.returnPressed.connect(self.send_message)
        
        self.btn_send = QPushButton("➤")
        self.btn_send.setFixedSize(35, 35)
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.clicked.connect(self.send_message)
        
        self.btn_stop = QPushButton("⏹") 
        self.btn_stop.setFixedSize(35, 35)
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(self.stop_generation)
        self.btn_stop.setVisible(False)
        self.btn_stop.setStyleSheet("background: #f38ba8; color: #1e1e2e; border-radius: 17px; font-weight: bold; border: none;")
        
        btn_theme = QPushButton("🌗")
        btn_theme.setFixedSize(30, 30)
        btn_theme.clicked.connect(theme_manager.toggle_theme)
        btn_theme.setStyleSheet("background: transparent; border: none; font-size: 16px;")
        
        row.addWidget(btn_theme)
        row.addWidget(self.btn_attach)
        row.addWidget(self.input_field)
        row.addWidget(self.btn_send)
        row.addWidget(self.btn_stop)
        
        input_lay.addLayout(row)
        self.content_layout.addWidget(self.input_container)
        
        find_action = QAction("Find", self)
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self.search_bar.show_bar)
        self.addAction(find_action)
        
        theme_manager.theme_changed.connect(self.update_style)
        self.update_style()

    def update_style(self):
        t = theme_manager.current
        self.input_container.setStyleSheet(f"background: {t['input_bg']}; border-radius: 20px; border: 1px solid {t['chip_border']};")
        self.input_field.setStyleSheet(f"background: transparent; border: none; color: {t['text']}; font-size: 14px;")
        self.btn_attach.setStyleSheet(f"background: transparent; color: {t['sys_col']}; border: none; font-size: 16px;")
        self.btn_send.setStyleSheet(f"""
            QPushButton {{ 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t['user_col']}, stop:1 #b4befe); 
                color: #1e1e2e; border-radius: 17px; font-weight: bold; border: none;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
        """)

    # --- ACTIONS ---
    def send_message(self):
        text = self.input_field.text().strip()
        if not text and not self.attachments: return
        
        self.toggle_input_state(False) 
        
        images = [p for p in self.attachments if p.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        others = [p for p in self.attachments if p not in images]
        
        if images:
            for img in images: self.add_msg("You", img, is_image=True)
        
        full_msg = text
        if others:
            full_msg += "\n\n[Attachments]:\n" + "\n".join([f"- {p}" for p in others])
            self.add_msg("System", f"Uploaded {len(others)} files.")

        if text: self.add_msg("You", text)
        
        self.input_field.clear()
        self._clear_attachments()
        self.reset_stream()
        
        self._start_thinking()
        self.command_signal.emit(full_msg) 

    def add_msg(self, user, text, is_markdown=False, is_image=False, is_tool=False):
        self.messages.append({"user": user, "text": text, "time": datetime.now().isoformat()})
        return self.chat_area.add_message(user, text, is_markdown, is_image, is_tool)

    def toggle_input_state(self, enabled):
        self.input_field.setEnabled(enabled)
        self.btn_send.setVisible(enabled)
        self.btn_stop.setVisible(not enabled)

    def stop_generation(self):
        self.on_brain_finished("Stopped.") 

    def clear_context(self):
        self.add_msg("System", "Memory cleared.", is_markdown=False)
        self.token_usage = 0
        self.context_bar.update_tokens(0)
        self.messages.clear()

    def export_chat(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Chat", "", "JSON Lines (*.jsonl)")
        if path:
            with open(path, 'w') as f:
                for msg in self.messages:
                    f.write(json.dumps(msg) + "\n")
            self.add_msg("System", f"Chat exported to {os.path.basename(path)}")

    def import_chat(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Chat", "", "JSON Lines (*.jsonl)")
        if path:
            with open(path, 'r') as f:
                for line in f:
                    try:
                        msg = json.loads(line)
                        self.add_msg(msg['user'], msg['text'], is_markdown=True)
                    except: pass
            self.add_msg("System", "Chat loaded.")

    def find_in_chat(self, text):
        count = self.chat_area.highlight_text(text)

    # --- FILE HANDLING ---
    def _validate_file(self, path):
        if not os.path.exists(path): return False
        if os.path.getsize(path) > self.MAX_FILE_SIZE: return False
        if os.path.splitext(path)[1].lower() not in self.ALLOWED_EXT: return False
        return True

    def _handle_dropped_files(self, files):
        for path in files:
            if self._validate_file(path): self._add_attachment(path)

    def browse_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", "All Files (*)")
        for f in files:
            if self._validate_file(f): self._add_attachment(f)

    def _add_attachment(self, path):
        if path in self.attachments: return
        self.attachments.append(path)
        chip = AttachmentChip(path)
        chip.removed.connect(self._remove_attachment)
        self.attach_layout.insertWidget(self.attach_layout.count()-1, chip)
        self.attach_area.setVisible(True)

    def _remove_attachment(self, path):
        if path in self.attachments:
            self.attachments.remove(path)
            for i in range(self.attach_layout.count()):
                w = self.attach_layout.itemAt(i).widget()
                if isinstance(w, AttachmentChip) and w.path == path:
                    w.deleteLater()
                    break
            if not self.attachments: self.attach_area.setVisible(False)

    def _clear_attachments(self):
        self.attachments.clear()
        while self.attach_layout.count() > 1:
            item = self.attach_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.attach_area.setVisible(False)

    # --- STREAMING & TOOLS ---
    def _start_thinking(self):
        self.current_thinking_widget = ThinkingWidget()
        self.chat_area.add_widget(self.current_thinking_widget)

    def reset_stream(self):
        self.current_streaming_bubble = None
        self._stream_buffer = ""

    def on_brain_update(self, token):
        if token.startswith("[LOG]"):
            if self.current_thinking_widget:
                self.current_thinking_widget.add_log(token.replace("[LOG]", "").strip())
            return
        
        if token.startswith("[TOOL]"):
            tool_name = token.replace("[TOOL]", "").strip()
            self.add_msg("Mio", f"🔧 Executing: {tool_name}", is_tool=True)
            return

        if not self.current_streaming_bubble:
            if self.current_thinking_widget:
                self.current_thinking_widget.status_lbl.setText("Replying...")
            self.current_streaming_bubble = self.chat_area.add_message("Mio", "", is_markdown=True)
            self.current_streaming_bubble.regenerate_requested.connect(lambda: self.command_signal.emit("regenerate"))
        
        self._stream_buffer += token
        self.current_streaming_bubble.update_content(self._stream_buffer, is_markdown=True)
        
        self.token_usage += 1
        if self.token_usage % 5 == 0:
            self.context_bar.update_tokens(self.token_usage)

    def on_brain_finished(self, response):
        # Save complete message
        if self.current_streaming_bubble:
            self.messages.append({"user": "Mio", "text": self._stream_buffer, "time": datetime.now().isoformat()})
            
        if self.current_thinking_widget:
            self.current_thinking_widget.mark_done()
        
        self.toggle_input_state(True)
        self.reset_stream()
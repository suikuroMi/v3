import os
import shutil
import datetime
import subprocess
import mimetypes
import ast
import math
import uuid
import mmap
import threading
import weakref
import difflib
from collections import Counter, OrderedDict
from functools import lru_cache

from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, 
                               QLineEdit, QPushButton, QMenu, QMessageBox, QLabel, 
                               QAbstractItemView, QProgressBar, QApplication, QInputDialog,
                               QSplitter, QTextEdit, QFrame, QWidget, QTabWidget, QGraphicsView, 
                               QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem,
                               QScrollArea, QSizePolicy, QDialog, QStackedWidget)
from PySide6.QtCore import (Qt, QThread, Signal, QMimeData, QUrl, QTimer, QSize, QObject,
                            QPointF, QRectF, QFileSystemWatcher, QRunnable, QThreadPool, Slot,
                            QRegularExpression, QEvent, QPoint, QMutex, QMutexLocker)
from PySide6.QtGui import (QAction, QKeySequence, QColor, QBrush, QPixmap, QFont, 
                           QTextCursor, QPen, QPainter, QDrag, QSyntaxHighlighter, QTextCharFormat,
                           QWheelEvent, QMouseEvent, QTransform)

from .base import BaseApp
from src.skills.file_ops import FileSkills

# ============================================================================
# 1. CORE SERVICES (THREAD-SAFE SINGLETON)
# ============================================================================

class ServiceManager:
    """
    V8: Fully Thread-Safe Singleton using QMutex.
    """
    _instance = None
    _lock = QMutex()

    def __new__(cls):
        with QMutexLocker(cls._lock):
            if cls._instance is None:
                cls._instance = super(ServiceManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        with QMutexLocker(self._lock):
            if self._initialized: return
            self.init_services()
            self._initialized = True

    def init_services(self):
        self.highlighter_pool = HighlighterPool()
        self.git_cache = OrderedDict() 
        self.analysis_cache = OrderedDict()
        self.threadpool = QThreadPool.globalInstance()

    def get_git_cache(self, path):
        return self.git_cache.get(path)

    def set_git_cache(self, path, data):
        if len(self.git_cache) > 100: self.git_cache.popitem(last=False)
        self.git_cache[path] = data

    def get_analysis_cache(self, path, mtime):
        if path in self.analysis_cache:
            cached_mtime, data = self.analysis_cache[path]
            if cached_mtime == mtime: return data
        return None

    def set_analysis_cache(self, path, mtime, data):
        if len(self.analysis_cache) > 50: self.analysis_cache.popitem(last=False)
        self.analysis_cache[path] = (mtime, data)

class CancellationToken:
    """Thread-safe cancellation token."""
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    @property
    def is_cancelled(self):
        return self._event.is_set()

# ============================================================================
# 2. CUSTOM WIDGETS
# ============================================================================

class MioFileTree(QTreeWidget):
    """
    Custom TreeWidget for correct Drag & Drop.
    """
    def __init__(self):
        super().__init__()
        self.setHeaderLabels(["Name", "Size", "Type", "Modified"])
        self.setColumnWidth(0, 250)
        self.setStyleSheet("QTreeWidget { background: #1e1e2e; color: #cdd6f4; border: none; }")
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)

    def startDrag(self, actions):
        items = self.selectedItems()
        if not items: return
        drag = QDrag(self)
        mime = QMimeData()
        urls = []
        for i in items:
            path = i.data(0, Qt.UserRole)
            if path: urls.append(QUrl.fromLocalFile(path))
        if urls:
            mime.setUrls(urls)
            drag.setMimeData(mime)
            drag.exec(actions)

class ZoomableImageLabel(QWidget):
    """
    V8.2: GPU Rendering.
    Fixed: QSizePolicy.Ignored (was Ignoring)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._last_mouse_pos = QPointF()
        self._panning = False
        
        # Optimization
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        # FIX: Correct constant is Ignored
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMouseTracking(True)

    def set_image(self, path):
        self._pixmap = QPixmap(path)
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#11111b"))
        
        if not self._pixmap:
            painter.setPen(QColor("#6c7086"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No Image")
            return

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        win_w, win_h = self.width(), self.height()
        pix_w, pix_h = self._pixmap.width(), self._pixmap.height()

        transform = QTransform()
        transform.translate(win_w / 2, win_h / 2) 
        transform.translate(self._offset.x(), self._offset.y()) 
        transform.scale(self._scale, self._scale) 
        transform.translate(-pix_w / 2, -pix_h / 2) 

        painter.setTransform(transform)
        painter.drawPixmap(0, 0, self._pixmap)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        new_scale = self._scale * factor
        if 0.05 <= new_scale <= 20.0:
            self._scale = new_scale
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._panning = True
            self._last_mouse_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = event.position() - self._last_mouse_pos
            self._offset += delta
            self._last_mouse_pos = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)

class DependencyGraph(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setStyleSheet("background: #11111b; border: none;")

    def build_graph(self, center_name, neighbors):
        self.scene.clear()
        self._add_node(0, 0, center_name, "#fab387", True)
        count = len(neighbors)
        if count == 0: return
        radius = 150
        angle_step = (2 * math.pi) / count
        for i, name in enumerate(neighbors):
            angle = i * angle_step
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            line = QGraphicsLineItem(0, 0, x, y)
            line.setPen(QPen(QColor("#45475a"), 2))
            self.scene.addItem(line)
            line.setZValue(-1)
            self._add_node(x, y, name, "#89b4fa")

    def _add_node(self, x, y, text, color, is_center=False):
        size = 50 if is_center else 30
        ellipse = QGraphicsEllipseItem(x - size/2, y - size/2, size, size)
        ellipse.setBrush(QBrush(QColor(color)))
        ellipse.setPen(QPen(Qt.NoPen))
        self.scene.addItem(ellipse)
        lbl = QGraphicsTextItem(text)
        lbl.setDefaultTextColor(QColor("#cdd6f4"))
        lbl.setPos(x - lbl.boundingRect().width()/2, y + size/2)
        self.scene.addItem(lbl)

# ============================================================================
# 3. SYNTAX HIGHLIGHTING
# ============================================================================

class HighlighterPool:
    def __init__(self):
        self._pool = weakref.WeakKeyDictionary() 

    def get_highlighter(self, document, file_type="py"):
        if document not in self._pool:
            self._pool[document] = OptimizedHighlighter(document, file_type)
        else:
            hl = self._pool[document]
            if hl.file_type != file_type:
                hl.reconfigure(file_type)
        return self._pool[document]

class OptimizedHighlighter(QSyntaxHighlighter):
    def __init__(self, document, file_type="py"):
        super().__init__(document)
        self.file_type = file_type
        self._init_formats()
        self.reconfigure(file_type)

    def _init_formats(self):
        self.fmt_keyword = QTextCharFormat()
        self.fmt_keyword.setForeground(QColor("#ff79c6"))
        self.fmt_keyword.setFontWeight(QFont.Bold)
        self.fmt_class = QTextCharFormat()
        self.fmt_class.setForeground(QColor("#8be9fd"))
        self.fmt_string = QTextCharFormat()
        self.fmt_string.setForeground(QColor("#f1fa8c"))
        self.fmt_comment = QTextCharFormat()
        self.fmt_comment.setForeground(QColor("#6272a4"))
        self.fmt_header = QTextCharFormat()
        self.fmt_header.setForeground(QColor("#bd93f9"))
        self.fmt_header.setFontWeight(QFont.Bold)

    def reconfigure(self, file_type):
        self.file_type = file_type
        self.rules = []
        rules_data = []
        
        if file_type == "py":
            keywords = ["def", "class", "import", "from", "return", "if", "else", "elif",
                        "while", "for", "in", "try", "except", "with", "as", "pass", "lambda",
                        "async", "await", "None", "True", "False"]
            for w in keywords: rules_data.append((f"\\b{w}\\b", self.fmt_keyword))
            rules_data.append(("class\\s+\\w+", self.fmt_class))
            rules_data.append(("def\\s+\\w+", self.fmt_class))
            rules_data.append(("\".*?\"", self.fmt_string))
            rules_data.append(("\'.*?\'", self.fmt_string))
            rules_data.append(("#[^\n]*", self.fmt_comment))
            
        elif file_type == "md":
            rules_data.append(("^#{1,6}\\s.*", self.fmt_header))
            rules_data.append(("\\*\\*.*?\\*\\*", self.fmt_keyword))
            rules_data.append(("\\[.*?\\]", self.fmt_class))

        for p, f in rules_data:
            self.rules.append((QRegularExpression(p), f))
        
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            match_iter = pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

# ============================================================================
# 4. DIALOGS
# ============================================================================

class QuickLookWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Look")
        self.resize(800, 600)
        self.setWindowFlags(Qt.Window) 
        self.setStyleSheet("background: #1e1e2e;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        self.stack = QStackedWidget()
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none; font-family: Consolas; font-size: 14px; padding: 10px;")
        
        self.image_view = ZoomableImageLabel()
        
        self.stack.addWidget(self.text_view)
        self.stack.addWidget(self.image_view)
        layout.addWidget(self.stack)

    def show_preview(self, path, content=None, is_image=False):
        if is_image:
            self.image_view.set_image(path)
            self.stack.setCurrentIndex(1)
        else:
            self.text_view.setText(content if content else "Loading...")
            self.stack.setCurrentIndex(0)
        self.show()
        self.activateWindow()

class DiffViewer(QDialog):
    def __init__(self, file_a, file_b, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Diff: {os.path.basename(file_a)} vs {os.path.basename(file_b)}")
        self.resize(1200, 700)
        self.setStyleSheet("background: #1e1e2e; color: #cdd6f4;")
        
        layout = QHBoxLayout(self)
        self.left = QTextEdit()
        self.right = QTextEdit()
        
        ext = os.path.splitext(file_a)[1].replace('.', '')
        self.hl_left = OptimizedHighlighter(self.left.document(), ext)
        self.hl_right = OptimizedHighlighter(self.right.document(), ext)
        
        for t in [self.left, self.right]:
            t.setReadOnly(True)
            t.setStyleSheet("font-family: Consolas; font-size: 13px; background: #11111b; border: 1px solid #333;")
            t.setLineWrapMode(QTextEdit.NoWrap)
        
        self.left.verticalScrollBar().valueChanged.connect(self.right.verticalScrollBar().setValue)
        self.right.verticalScrollBar().valueChanged.connect(self.left.verticalScrollBar().setValue)
        
        layout.addWidget(self.left)
        layout.addWidget(self.right)
        
        self._compute_diff(file_a, file_b)

    def _compute_diff(self, a, b):
        try:
            with open(a, 'r', encoding='utf-8', errors='ignore') as f: lines_a = f.readlines()
            with open(b, 'r', encoding='utf-8', errors='ignore') as f: lines_b = f.readlines()
            
            self.left.setPlainText("".join(lines_a))
            self.right.setPlainText("".join(lines_b))
        except Exception as e:
            self.left.setText(f"Error reading files: {e}")

# ============================================================================
# 5. WORKERS
# ============================================================================

class WorkerSignals(QObject):
    files_loaded = Signal(list, dict, dict)
    error = Signal(str)
    analysis_ready = Signal(str, dict)
    text_preview_ready = Signal(str, str, str) # req_id, path, content
    git_ready = Signal(str, dict)

class FileLoaderTask(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = WorkerSignals()
        self.token = CancellationToken()

    def cancel(self): self.token.cancel()

    def run(self):
        try:
            if not os.path.exists(self.path):
                self.signals.error.emit("Path not found")
                return

            results = []
            extensions = []
            
            with os.scandir(self.path) as entries:
                for entry in entries:
                    if self.token.is_cancelled: return
                    try:
                        stat = entry.stat()
                        is_dir = entry.is_dir()
                        size_val = stat.st_size
                        date = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                        kind = "Folder" if is_dir else os.path.splitext(entry.name)[1].upper().replace(".", "")
                        if not is_dir: extensions.append(kind)
                        results.append({
                            "name": entry.name, "path": entry.path, "is_dir": is_dir,
                            "size_val": size_val, "date": date, "kind": kind
                        })
                    except OSError: continue 
            
            if self.token.is_cancelled: return

            lang_stats = {}
            if extensions:
                counts = Counter(extensions)
                total = len(extensions)
                for ext, count in counts.most_common(5):
                    lang_stats[ext] = (count / total) * 100

            git_map = {}
            if not self.token.is_cancelled:
                has_git = False
                curr = self.path
                for _ in range(4):
                    if os.path.exists(os.path.join(curr, ".git")):
                        has_git = True; break
                    curr = os.path.dirname(curr)
                    if not curr or curr == os.path.dirname(curr): break
                
                if has_git:
                    try:
                        p = subprocess.run(["git", "status", "--porcelain"], cwd=self.path, capture_output=True, text=True, timeout=1)
                        for line in p.stdout.splitlines():
                            if len(line) > 3: git_map[line[3:].strip().strip('"')] = line[:2]
                    except: pass

            if self.token.is_cancelled: return
            
            results.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            self.signals.files_loaded.emit(results, git_map, lang_stats)

        except Exception as e:
            if not self.token.is_cancelled: self.signals.error.emit(str(e))

class PreviewTask(QRunnable):
    def __init__(self, path, req_id):
        super().__init__()
        self.path = path
        self.req_id = req_id
        self.signals = WorkerSignals()

    def run(self):
        try:
            if not os.path.exists(self.path): return
            size = os.path.getsize(self.path)
            
            is_binary = False
            try:
                with open(self.path, 'rb') as f:
                    header = f.read(1024)
                    if b'\0' in header: is_binary = True
                    else:
                        text_chars = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)) - {0x7f})
                        if not all(b in text_chars for b in header): is_binary = True
            except: is_binary = True
            
            if is_binary:
                self.signals.text_preview_ready.emit(self.req_id, self.path, "[Binary File - Preview Unavailable]")
                return

            limit = 50 * 1024 
            text = ""
            with open(self.path, 'rb') as f:
                if size == 0: text = ""
                else:
                    try:
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            chunk = mm.read(min(size, limit))
                            text = chunk.decode('utf-8', errors='ignore')
                    except:
                        f.seek(0)
                        text = f.read(limit).decode('utf-8', errors='ignore')
            
            self.signals.text_preview_ready.emit(self.req_id, self.path, text)
        except Exception: pass 

class GitTask(QRunnable):
    def __init__(self, path, req_id):
        super().__init__()
        self.path = path
        self.req_id = req_id
        self.signals = WorkerSignals()

    def run(self):
        data = {"blame": "No Git info", "branch": ""}
        try:
            dir_path = os.path.dirname(self.path)
            p = subprocess.run(["git", "branch", "--show-current"], cwd=dir_path, capture_output=True, text=True, timeout=1)
            if p.returncode == 0: data["branch"] = p.stdout.strip()
            p = subprocess.run(["git", "log", "-1", "--format=%an (%cr): %s", self.path], cwd=dir_path, capture_output=True, text=True, timeout=1)
            if p.stdout.strip(): data["blame"] = p.stdout.strip()
            else: data["blame"] = "Not tracked"
        except: pass
        self.signals.git_ready.emit(self.req_id, data)

class AnalysisTask(QRunnable):
    def __init__(self, path, request_id):
        super().__init__()
        self.path = path
        self.request_id = request_id
        self.signals = WorkerSignals()

    def run(self):
        try:
            stat1 = os.stat(self.path)
            with open(self.path, "r", encoding="utf-8") as f: source = f.read()
            try: tree = ast.parse(source)
            except SyntaxError:
                self.signals.analysis_ready.emit(self.request_id, {"error": "Syntax Error", "mtime": stat1.st_mtime})
                return

            imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]
            imports += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) if n.module]
            
            structure = []
            score = 1
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    structure.append((node.name, "class", node.lineno))
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            structure.append((child.name, "method", child.lineno))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    structure.append((node.name, "function", node.lineno))

            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler, ast.BoolOp)):
                    score += 1

            loc = len(source.splitlines())
            avg = score / (len(structure) or 1)
            grade = "A" if avg < 5 else ("B" if avg < 10 else ("C" if avg < 20 else "F"))

            try:
                stat2 = os.stat(self.path)
                if stat1.st_mtime == stat2.st_mtime and stat1.st_size == stat2.st_size:
                    self.signals.analysis_ready.emit(self.request_id, {
                        "imports": list(set(imports)), "structure": structure, "grade": grade,
                        "score": int(avg), "loc": loc, "mtime": stat1.st_mtime
                    })
            except OSError: pass
        except: self.signals.analysis_ready.emit(self.request_id, {})

# ============================================================================
# 6. MAIN APPLICATION
# ============================================================================

class FilesApp(BaseApp):
    def __init__(self, brain=None):
        super().__init__("Mio Files", "folder.png", "#FFC107")
        self.brain = brain
        self.current_path = os.path.expanduser("~")
        self.services = ServiceManager() 
        
        self.active_loader = None 
        self.req_preview_id = None
        self.req_git_id = None
        self.req_analysis_id = None
        
        self._pending_items = []
        
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.on_fs_change)
        
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(500)
        self.debounce_timer.timeout.connect(self.refresh_tree)

        self.quick_look = QuickLookWindow(self)

        self.undo_stack = []
        self.history_back = []
        self.history_fwd = []
        self.cut_mode = False
        self.cut_items = []

        self._init_ui()
        self.tree.installEventFilter(self)

    def _init_ui(self):
        main = QVBoxLayout()
        
        top = QHBoxLayout()
        self.btn_back = self._mk_btn("⬅", self.go_back)
        self.btn_fwd = self._mk_btn("➡", self.go_fwd)
        self.btn_up = self._mk_btn("⬆", self.go_up)
        
        self.path_input = QLineEdit()
        self.path_input.returnPressed.connect(lambda: self.navigate(self.path_input.text()))
        self.path_input.setStyleSheet("background: #222; color: #fff; border: 1px solid #444; border-radius: 5px; padding: 4px;")
        
        self.btn_go = QPushButton("Go")
        self.btn_go.clicked.connect(lambda: self.navigate(self.path_input.text()))
        
        top.addWidget(self.btn_back)
        top.addWidget(self.btn_fwd)
        top.addWidget(self.btn_up)
        top.addWidget(self.path_input)
        top.addWidget(self.btn_go)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Filter files... (Space to Quick Look)")
        self.search_bar.textChanged.connect(self.execute_filter)
        self.search_bar.setStyleSheet("background: #1a1a1a; color: #ccc; border: 1px solid #333; border-radius: 10px;")

        main.addLayout(top)
        main.addWidget(self.search_bar)
        
        self.splitter = QSplitter(Qt.Horizontal)
        
        self.tree = MioFileTree()
        self.tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.tree.itemDoubleClicked.connect(self.on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_context_menu)
        self.splitter.addWidget(self.tree)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; background: #181825; } QTabBar::tab { background: #11111b; color: #aaa; padding: 6px; } QTabBar::tab:selected { color: #fff; border-bottom: 2px solid #89b4fa; }")
        
        self.preview_widget = QWidget()
        p_layout = QVBoxLayout(self.preview_widget)
        p_layout.setContentsMargins(0,0,0,0)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("background: #11111b; color: #a6adc8; border: none; font-family: Consolas;")
        
        self.current_highlighter = self.services.highlighter_pool.get_highlighter(self.preview_text.document(), "py")
        
        self.preview_img = ZoomableImageLabel()
        self.preview_img.setVisible(False)
        
        self.btn_ai = QPushButton("🧠 Analyze with Mio")
        self.btn_ai.setStyleSheet("background: #89b4fa; color: #1e1e2e; font-weight: bold; margin: 5px;")
        self.btn_ai.clicked.connect(self.analyze_with_brain)
        
        p_layout.addWidget(self.preview_text)
        p_layout.addWidget(self.preview_img)
        p_layout.addWidget(self.btn_ai)
        self.tabs.addTab(self.preview_widget, "👁️ View")
        
        self.structure_tree = QTreeWidget()
        self.structure_tree.setHeaderHidden(True)
        self.structure_tree.setStyleSheet("background: #11111b; color: #cdd6f4; border: none;")
        self.tabs.addTab(self.structure_tree, "🧠 Code")
        
        self.graph_view_widget = DependencyGraph()
        self.tabs.addTab(self.graph_view_widget, "🕸️ Graph")
        
        self.health_widget = QWidget()
        h_layout = QVBoxLayout(self.health_widget)
        self.lbl_grade = QLabel("A")
        self.lbl_grade.setStyleSheet("font-size: 48px; font-weight: bold; color: #a6e3a1;")
        self.lbl_grade.setAlignment(Qt.AlignCenter)
        self.lbl_score = QLabel("Score: -")
        self.lbl_score.setAlignment(Qt.AlignCenter)
        h_layout.addWidget(QLabel("CODE HEALTH"))
        h_layout.addWidget(self.lbl_grade)
        h_layout.addWidget(self.lbl_score)
        
        self.lbl_git_blame = QLabel("Select a file...")
        self.lbl_git_blame.setWordWrap(True)
        self.lbl_git_blame.setStyleSheet("color: #fab387; font-style: italic;")
        h_layout.addSpacing(20)
        h_layout.addWidget(QLabel("GIT CONTEXT"))
        h_layout.addWidget(self.lbl_git_blame)
        
        self.lbl_lang_stats = QLabel("")
        self.lbl_lang_stats.setStyleSheet("color: #aaa;")
        h_layout.addSpacing(20)
        h_layout.addWidget(QLabel("FOLDER STATS"))
        h_layout.addWidget(self.lbl_lang_stats)
        h_layout.addStretch()
        self.tabs.addTab(self.health_widget, "❤️ Health")
        
        self.splitter.addWidget(self.tabs)
        self.splitter.setSizes([500, 350])
        main.addWidget(self.splitter)
        
        stat_bar = QHBoxLayout()
        self.status_lbl = QLabel("Ready")
        self.git_branch_lbl = QLabel("")
        self.git_branch_lbl.setStyleSheet("color: #fab387; font-weight: bold;")
        self.loading_bar = QProgressBar()
        self.loading_bar.setFixedHeight(5)
        self.loading_bar.setVisible(False)
        stat_bar.addWidget(self.status_lbl)
        stat_bar.addStretch()
        stat_bar.addWidget(self.git_branch_lbl)
        stat_bar.addWidget(self.loading_bar)
        main.addLayout(stat_bar)
        
        self.content_layout.addLayout(main)
        
        self.setup_shortcuts()
        self.update_nav_buttons()
        QTimer.singleShot(100, lambda: self.navigate(self.current_path))

    def eventFilter(self, source, event):
        if source == self.tree and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Space:
                self.toggle_quick_look()
                return True
        return super().eventFilter(source, event)

    def toggle_quick_look(self):
        if self.quick_look.isVisible():
            self.quick_look.hide()
        else:
            items = self.tree.selectedItems()
            if items:
                path = items[0].data(0, Qt.UserRole)
                mime, _ = mimetypes.guess_type(path)
                is_img = mime and "image" in mime
                content = self.preview_text.toPlainText() if not is_img else None
                self.quick_look.show_preview(path, content, is_img)

    def connect_manager(self, manager):
        if hasattr(manager, 'bus'):
            manager.bus.file_system_changed.connect(self.on_fs_change)

    def on_fs_change(self, path=None):
        self.debounce_timer.start()

    def navigate(self, path, save_hist=True):
        res = os.path.abspath(os.path.expanduser(path))
        if not FileSkills._is_safe_path(res): 
            self.status_lbl.setText("⛔ Access Denied")
            return
            
        if save_hist and res != self.current_path:
            self.history_back.append(self.current_path)
            self.history_fwd.clear()
            self.update_nav_buttons()
            
        self.current_path = res
        self.path_input.setText(res)
        
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        if os.path.exists(res):
            self.watcher.addPath(res)
            
        self.refresh_tree()

    def refresh_tree(self):
        if self.active_loader:
            self.active_loader.cancel()
            self.active_loader = None
            
        self._pending_items = []
        self.tree.clear()
        self.loading_bar.setVisible(True)
        self.loading_bar.setRange(0, 0)
        
        loader = FileLoaderTask(self.current_path)
        loader.signals.files_loaded.connect(self.on_files_scanned)
        loader.signals.error.connect(lambda e: self.status_lbl.setText(f"❌ {e}"))
        
        self.active_loader = loader
        self.services.threadpool.start(loader)

    def on_files_scanned(self, items, git_map, lang_stats):
        self.active_loader = None 
        self.loading_bar.setVisible(False)
        self.status_lbl.setText(f"Loaded {len(items)} items")
        
        txt = ""
        for ext, pct in lang_stats.items(): txt += f"• {ext}: {pct:.1f}%\n"
        self.lbl_lang_stats.setText(txt if txt else "Empty folder")
        
        self._pending_items = items
        self._cached_git_map = git_map
        QTimer.singleShot(0, self._populate_next_batch)

    def _populate_next_batch(self):
        if not self._pending_items: return
            
        chunk = self._pending_items[:50]
        self._pending_items = self._pending_items[50:]
        
        items_to_add = []
        for d in chunk:
            icon = "📁" if d['is_dir'] else "📄"
            if d['kind'] in ["PY", "JS", "HTML", "CSS", "CPP", "MD"]: icon = "👨‍💻"
            elif d['kind'] in ["PNG", "JPG", "GIF"]: icon = "🖼️"
            
            item = QTreeWidgetItem([f"{icon} {d['name']}", self._format_size(d['size_val']), d['kind'], d['date']])
            item.setData(0, Qt.UserRole, d['path'])
            item.setData(0, Qt.UserRole + 1, d['is_dir'])
            
            if self._cached_git_map:
                s = self._cached_git_map.get(d['name'], "")
                if "M" in s: item.setForeground(0, QBrush(QColor("#fab387")))
                elif "?" in s: item.setForeground(0, QBrush(QColor("#6c7086")))
                elif "A" in s: item.setForeground(0, QBrush(QColor("#a6e3a1")))
            
            items_to_add.append(item)
            
        self.tree.addTopLevelItems(items_to_add)
        
        if self._pending_items:
            QTimer.singleShot(0, self._populate_next_batch)

    def _format_size(self, size):
        for u in ['B', 'KB', 'MB', 'GB']:
            if size < 1024: return f"{size:.1f} {u}"
            size /= 1024
        return f"{size:.1f} TB"

    def on_selection_changed(self):
        items = self.tree.selectedItems()
        if not items: return
        path = items[0].data(0, Qt.UserRole)
        is_dir = items[0].data(0, Qt.UserRole + 1)
        
        if is_dir: return

        self.req_preview_id = str(uuid.uuid4())
        mime, _ = mimetypes.guess_type(path)
        
        if mime and "image" in mime:
            self.preview_text.setVisible(False)
            self.preview_img.setVisible(True)
            self.preview_img.set_image(path)
        else:
            self.preview_img.setVisible(False)
            self.preview_text.setVisible(True)
            self.preview_text.setText("Loading...")
            
            ext = os.path.splitext(path)[1].lower()
            h_type = "md" if ext == ".md" else "py"
            self.services.highlighter_pool.get_highlighter(self.preview_text.document(), h_type)
            
            task = PreviewTask(path, self.req_preview_id)
            task.signals.text_preview_ready.connect(self._on_preview_loaded)
            self.services.threadpool.start(task)

        self.lbl_git_blame.setText("Checking git...")
        self.req_git_id = str(uuid.uuid4())
        
        cached_git = self.services.get_git_cache(path)
        if cached_git:
            self._on_git_loaded(self.req_git_id, cached_git)
        else:
            gtask = GitTask(path, self.req_git_id)
            gtask.signals.git_ready.connect(self._on_git_loaded)
            self.services.threadpool.start(gtask)
        
        if path.endswith(".py"):
            self._trigger_analysis(path)
        else:
            self.structure_tree.clear()
            self.graph_view_widget.scene.clear()
            self.lbl_grade.setText("-")

    def _on_preview_loaded(self, req_id, path, content):
        if req_id != self.req_preview_id: return
        self.preview_text.setText(content)
        if path.endswith(".md"):
            self.preview_text.setMarkdown(content)

    def _on_git_loaded(self, req_id, data):
        if req_id != self.req_git_id: return
        
        path = self.tree.selectedItems()[0].data(0, Qt.UserRole)
        self.services.set_git_cache(path, data)
        
        self.lbl_git_blame.setText(data.get("blame", "No info"))
        self.git_branch_lbl.setText(f" {data.get('branch', '')}")

    def _trigger_analysis(self, path):
        try:
            mtime = os.stat(path).st_mtime
        except OSError: return

        cached_data = self.services.get_analysis_cache(path, mtime)
        if cached_data:
            self.update_intelligence(cached_data)
            return

        req_id = str(uuid.uuid4())
        self.req_analysis_id = req_id
        
        task = AnalysisTask(path, req_id)
        task.signals.analysis_ready.connect(self._handle_analysis_result)
        self.services.threadpool.start(task)

    def _handle_analysis_result(self, req_id, data):
        if req_id != self.req_analysis_id: return
            
        path = self.tree.selectedItems()[0].data(0, Qt.UserRole)
        if "mtime" in data:
            self.services.set_analysis_cache(path, data['mtime'], data)
            self.update_intelligence(data)
        elif "error" in data:
            self.lbl_grade.setText("?")

    def update_intelligence(self, data):
        if not data or "error" in data: 
            self.lbl_grade.setText("?")
            return
        
        self.structure_tree.clear()
        if 'structure' in data:
            root = self.structure_tree.invisibleRootItem()
            for name, kind, line in data['structure']:
                icon = "C" if kind == "class" else ("M" if kind == "method" else "F")
                color = "#f38ba8" if icon == "C" else "#89b4fa"
                item = QTreeWidgetItem([f" {icon} {name}"])
                item.setForeground(0, QBrush(QColor(color)))
                root.addChild(item)
        
        self.graph_view_widget.build_graph("Current", data.get('imports', []))
        
        self.lbl_grade.setText(data.get('grade', '-'))
        colors = {"A": "#a6e3a1", "B": "#89b4fa", "C": "#fab387", "F": "#f38ba8"}
        self.lbl_grade.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {colors.get(data.get('grade'), '#fff')};")
        self.lbl_score.setText(f"Avg Complexity: {data.get('score', 0)}")

    def analyze_with_brain(self):
        items = self.tree.selectedItems()
        if items: self.command_signal.emit(f"Analyze this file: {items[0].data(0, Qt.UserRole)}")

    def _mk_btn(self, txt, func):
        b = QPushButton(txt)
        b.setFixedSize(30,30)
        b.clicked.connect(func)
        return b

    def setup_shortcuts(self):
        QAction("Up", self, shortcut=QKeySequence.Back, triggered=self.go_up)
        QAction("Refresh", self, shortcut=QKeySequence.Refresh, triggered=lambda: self.navigate(self.current_path))
        self.act_copy = QAction("Copy", self, shortcut=QKeySequence.Copy, triggered=self.copy_selection)
        self.addAction(self.act_copy)
        self.act_paste = QAction("Paste", self, shortcut=QKeySequence.Paste, triggered=self.paste_from_clipboard)
        self.addAction(self.act_paste)
        self.act_cut = QAction("Cut", self, shortcut=QKeySequence.Cut, triggered=self.cut_selection)
        self.addAction(self.act_cut)
        self.act_del = QAction("Delete", self, shortcut=QKeySequence.Delete, triggered=self.request_delete)
        self.addAction(self.act_del)
        self.act_rename = QAction("Rename", self, shortcut="F2", triggered=self.rename_item)
        self.addAction(self.act_rename)
        self.act_new_folder = QAction("New Folder", self, shortcut="Ctrl+Shift+N", triggered=self.create_folder)
        self.addAction(self.act_new_folder)
        self.act_undo = QAction("Undo", self, shortcut=QKeySequence.Undo, triggered=self.undo_last_op)
        self.addAction(self.act_undo)

    def execute_filter(self):
        t = self.search_bar.text().lower()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setHidden(t not in item.text(0).lower())

    def update_nav_buttons(self):
        self.btn_back.setEnabled(bool(self.history_back))
        self.btn_fwd.setEnabled(bool(self.history_fwd))

    def go_back(self):
        if self.history_back:
            self.history_fwd.append(self.current_path)
            self.navigate(self.history_back.pop(), False)
    
    def go_fwd(self):
        if self.history_fwd:
            self.history_back.append(self.current_path)
            self.navigate(self.history_fwd.pop(), False)

    def go_up(self): self.navigate(os.path.dirname(self.current_path))
    
    def on_double_click(self, item, _):
        if item.data(0, Qt.UserRole + 1): self.navigate(item.data(0, Qt.UserRole))
        else: self.command_signal.emit(f"[OPEN] {item.data(0, Qt.UserRole)}")

    def open_context_menu(self, pos):
        menu = QMenu()
        menu.setStyleSheet("QMenu { background: #333; color: white; border: 1px solid #555; }")
        items = self.tree.selectedItems()
        if items:
            menu.addAction(self.act_copy)
            menu.addAction(self.act_cut)
            menu.addAction(self.act_rename)
            menu.addSeparator()
            path = items[0].data(0, Qt.UserRole)
            act_git = QAction("➕ Git Add", self)
            act_git.triggered.connect(lambda: self.command_signal.emit(f"[GITHUB] add | {path}"))
            menu.addAction(act_git)
            act_ai = QAction("🧠 Analyze", self)
            act_ai.triggered.connect(self.analyze_with_brain)
            menu.addAction(act_ai)
            
            if len(items) == 2:
                act_diff = QAction("🆚 Compare", self)
                p1 = items[0].data(0, Qt.UserRole)
                p2 = items[1].data(0, Qt.UserRole)
                act_diff.triggered.connect(lambda: DiffViewer(p1, p2, self).show())
                menu.addAction(act_diff)
                
            menu.addSeparator()
            menu.addAction(self.act_del)
        else:
            menu.addAction(self.act_new_folder)
            menu.addAction(self.act_paste)
            menu.addAction(self.act_undo)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def copy_selection(self): self._set_clipboard(False)
    def cut_selection(self): self._set_clipboard(True)
    def _set_clipboard(self, cut):
        items = self.tree.selectedItems()
        if not items: return
        self.cut_mode = cut
        if cut:
             self.cut_items = items
             for i in items: i.setForeground(0, QBrush(QColor("#666")))
        urls = [QUrl.fromLocalFile(i.data(0, Qt.UserRole)) for i in items]
        mime = QMimeData()
        mime.setUrls(urls)
        QApplication.clipboard().setMimeData(mime)

    def paste_from_clipboard(self):
        md = QApplication.clipboard().mimeData()
        if not md.hasUrls(): return
        count = 0
        for url in md.urls():
            src = url.toLocalFile()
            dst = os.path.join(self.current_path, os.path.basename(src))
            try:
                if self.cut_mode:
                    shutil.move(src, dst)
                    self.undo_stack.append(("move", dst, src))
                else:
                    if os.path.isdir(src): shutil.copytree(src, dst)
                    else: shutil.copy2(src, dst)
                    self.undo_stack.append(("copy", dst, None))
                count += 1
            except: pass
        if self.cut_mode:
            for i in self.cut_items: i.setForeground(0, QBrush(QColor("#cdd6f4")))
            self.cut_mode = False
            QApplication.clipboard().clear()
        self.status_lbl.setText(f"Pasted {count} items")
        self.refresh_tree()

    def request_delete(self):
        items = self.tree.selectedItems()
        if not items: return
        if QMessageBox.question(self, "Delete", f"Delete {len(items)} items?") == QMessageBox.Yes:
            paths = [i.data(0, Qt.UserRole) for i in items]
            self.command_signal.emit(f"Delete these files:\n" + "\n".join(paths))

    def rename_item(self):
        items = self.tree.selectedItems()
        if not items: return
        old = items[0].data(0, Qt.UserRole)
        new, ok = QInputDialog.getText(self, "Rename", "Name:", text=os.path.basename(old))
        if ok and new:
            try: os.rename(old, os.path.join(os.path.dirname(old), new))
            except Exception as e: self.status_lbl.setText(f"Error: {e}")

    def create_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Name:")
        if ok and name:
            FileSkills.make_directory(os.path.join(self.current_path, name))

    def undo_last_op(self):
        if not self.undo_stack: return
        op, a, b = self.undo_stack.pop()
        try:
            if op == "move": shutil.move(a, b)
            elif op == "copy": 
                if os.path.isdir(a): shutil.rmtree(a)
                else: os.remove(a)
            self.status_lbl.setText("Undone.")
        except: self.status_lbl.setText("Undo Failed.")
import os
import shutil
import datetime
import subprocess
import mimetypes
import ast
import math
from collections import Counter

from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, 
                               QLineEdit, QPushButton, QMenu, QMessageBox, QLabel, 
                               QAbstractItemView, QProgressBar, QApplication, QInputDialog,
                               QSplitter, QTextEdit, QFrame, QWidget, QTabWidget, QGraphicsView, 
                               QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem)
from PySide6.QtCore import Qt, QThread, Signal, QMimeData, QUrl, QTimer, QSize, QPointF, QRectF
from PySide6.QtGui import QAction, QKeySequence, QColor, QBrush, QPixmap, QFont, QTextCursor, QPen, QPainter

from .base import BaseApp
from src.skills.file_ops import FileSkills

# --- 1. WORKER: FILE SYSTEM & GIT SCANNER ---
class FileLoader(QThread):
    """Scans files, gets Git status colors, and calculates directory stats."""
    files_loaded = Signal(list, dict, str, dict) # items, git_map, branch, lang_stats
    error_occurred = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self._cancelled = False

    def cancel(self): self._cancelled = True

    def _get_git_info(self):
        git_map = {}
        branch = ""
        if not os.path.exists(os.path.join(self.path, ".git")) and not os.path.exists(os.path.join(os.path.dirname(self.path), ".git")):
             return {}, "" # Quick exit if likely not a repo

        try:
            # Get Branch
            p = subprocess.run(["git", "branch", "--show-current"], cwd=self.path, capture_output=True, text=True)
            if p.returncode == 0: branch = p.stdout.strip()
            
            # Get Status (Porcelain)
            p = subprocess.run(["git", "status", "--porcelain"], cwd=self.path, capture_output=True, text=True)
            for line in p.stdout.splitlines():
                if len(line) > 3:
                    code = line[:2]
                    fname = line[3:].strip().strip('"')
                    git_map[fname] = code
        except: pass
        return git_map, branch

    def run(self):
        try:
            if not os.path.exists(self.path):
                self.error_occurred.emit("Path not found")
                return

            results = []
            extensions = []
            
            with os.scandir(self.path) as entries:
                for entry in entries:
                    if self._cancelled: return
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
                    except: continue 
            
            # Language Stats
            lang_stats = {}
            if extensions:
                counts = Counter(extensions)
                total = len(extensions)
                for ext, count in counts.most_common(5):
                    lang_stats[ext] = (count / total) * 100

            git_map, branch = self._get_git_info()
            
            if self._cancelled: return
            results.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            self.files_loaded.emit(results, git_map, branch, lang_stats)

        except Exception as e:
            if not self._cancelled: self.error_occurred.emit(str(e))

    def format_size(self, size):
        for u in ['B', 'KB', 'MB', 'GB']:
            if size < 1024: return f"{size:.1f} {u}"
            size /= 1024
        return f"{size:.1f} TB"

# --- 2. WORKER: DEEP CODE ANALYSIS ---
class CodeAnalyzer(QThread):
    """Parses AST for Structure, Imports Graph, and Complexity Audit."""
    analysis_ready = Signal(dict) 

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        if not self.path.endswith(".py"): 
            self.analysis_ready.emit({})
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
            
            # 1. Imports (Graph Data)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names: imports.append(n.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports.append(f"{module}")

            # 2. Complexity & Structure
            complexity = {}
            structure = [] # List of (name, type, lineno)
            total_complexity = 0
            func_count = 0
            
            for node in ast.iter_fields(tree): # High level scan
                pass 

            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    structure.append((node.name, "class", node.lineno))
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            structure.append((child.name, "method", child.lineno))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    structure.append((node.name, "function", node.lineno))

            # Deep Scan for Audit
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    score = 1
                    for child in ast.walk(node):
                        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.BoolOp)):
                            score += 1
                    complexity[node.name] = score
                    total_complexity += score
                    func_count += 1
            
            avg = (total_complexity / func_count) if func_count > 0 else 1
            if avg <= 5: grade = "A"
            elif avg <= 10: grade = "B"
            elif avg <= 20: grade = "C"
            else: grade = "F"

            self.analysis_ready.emit({
                "imports": list(set(imports)),
                "complexity": complexity,
                "structure": structure,
                "grade": grade,
                "score": int(avg),
                "loc": len(source.splitlines())
            })
        except:
            self.analysis_ready.emit({})

# --- 3. UI COMPONENTS ---

class DependencyGraph(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setStyleSheet("background: #11111b; border: none;")

    def build_graph(self, center_name, neighbors):
        self.scene.clear()
        center = self._add_node(0, 0, center_name, "#fab387", True)
        
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

class CodeStructureTree(QTreeWidget):
    jump_to_line = Signal(int)
    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setStyleSheet("background: #11111b; color: #cdd6f4; border: none;")
        self.itemClicked.connect(lambda i, c: self.jump_to_line.emit(i.data(0, Qt.UserRole)))

    def populate(self, structure_data):
        self.clear()
        if not structure_data: return
        
        # Simple flat list for robustness, could be nested
        parents = {} # name -> item
        root = self.invisibleRootItem()
        
        for name, kind, line in structure_data:
            icon = "C" if kind == "class" else ("M" if kind == "method" else "F")
            color = "#f38ba8" if icon == "C" else "#89b4fa"
            
            item = QTreeWidgetItem([f" {icon} {name}"])
            item.setForeground(0, QBrush(QColor(color)))
            item.setData(0, Qt.UserRole, line)
            
            # Simple nesting logic: Methods follow classes? 
            # For robustness in flat list, we just add to root 
            # (Real nesting requires tree recursion which we did in v7, keeping it simple here)
            root.addChild(item)

# --- 4. MAIN APPLICATION ---
class FilesApp(BaseApp):
    def __init__(self, brain=None):
        super().__init__("Mio Files", "folder.png", "#FFC107")
        self.brain = brain
        self.current_path = os.path.expanduser("~")
        
        # Threads
        self.loader_thread = None
        self.analyzer_thread = None
        
        # State
        self.undo_stack = []
        self.history_back = []
        self.history_fwd = []
        self.cut_mode = False
        self.cut_items = []

        # --- LAYOUT CONSTRUCTION ---
        main = QVBoxLayout()
        
        # 1. Top Bar
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
        self.search_bar.setPlaceholderText("🔍 Filter files...")
        self.search_timer = QTimer()
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.execute_filter)
        self.search_bar.textChanged.connect(self.search_timer.start)
        self.search_bar.setStyleSheet("background: #1a1a1a; color: #ccc; border: 1px solid #333; border-radius: 10px;")

        main.addLayout(top)
        main.addWidget(self.search_bar)
        
        # 2. Splitter Area
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Left: File Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size", "Type", "Modified"])
        self.tree.setColumnWidth(0, 250)
        self.tree.setStyleSheet("QTreeWidget { background: #1e1e2e; color: #cdd6f4; border: none; }")
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDrop)
        self.tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.tree.itemDoubleClicked.connect(self.on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_context_menu)
        self.splitter.addWidget(self.tree)
        
        # Right: Intelligence Hub
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; background: #181825; } QTabBar::tab { background: #11111b; color: #aaa; padding: 6px; } QTabBar::tab:selected { color: #fff; border-bottom: 2px solid #89b4fa; }")
        
        # Tab 1: Preview
        self.preview_widget = QWidget()
        p_layout = QVBoxLayout(self.preview_widget)
        p_layout.setContentsMargins(0,0,0,0)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("background: #11111b; color: #a6adc8; border: none; font-family: Consolas;")
        self.preview_img = QLabel()
        self.preview_img.setAlignment(Qt.AlignCenter)
        self.preview_img.setVisible(False)
        self.btn_ai = QPushButton("🧠 Analyze with Mio")
        self.btn_ai.setStyleSheet("background: #89b4fa; color: #1e1e2e; font-weight: bold; margin: 5px;")
        self.btn_ai.clicked.connect(self.analyze_with_brain)
        p_layout.addWidget(self.preview_text)
        p_layout.addWidget(self.preview_img)
        p_layout.addWidget(self.btn_ai)
        self.tabs.addTab(self.preview_widget, "👁️ View")
        
        # Tab 2: Structure
        self.structure_tree = CodeStructureTree()
        self.structure_tree.jump_to_line.connect(self.scroll_to_line)
        self.tabs.addTab(self.structure_tree, "🧠 Code")
        
        # Tab 3: Graph
        self.graph_view = DependencyGraph()
        self.tabs.addTab(self.graph_view, "🕸️ Graph")
        
        # Tab 4: Health (Audit + Git Blame)
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
        
        # 3. Status Bar
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
        
        # Init
        self.setup_shortcuts()
        self.update_nav_buttons()
        self.navigate(os.path.join(os.path.expanduser("~"), "Desktop"))

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

    # --- NAVIGATION & THREADING ---
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
        self.refresh_tree_threaded()

    def refresh_tree_threaded(self):
        self.tree.clear()
        self.loading_bar.setVisible(True)
        self.loading_bar.setRange(0,0)
        
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.cancel()
            self.loader_thread.wait()
            
        self.loader_thread = FileLoader(self.current_path)
        self.loader_thread.files_loaded.connect(self.on_files_loaded)
        self.loader_thread.error_occurred.connect(lambda e: self.status_lbl.setText(f"❌ {e}"))
        self.loader_thread.start()

    def on_files_loaded(self, items, git_map, branch, lang_stats):
        self.loading_bar.setVisible(False)
        self.status_lbl.setText(f"Loaded {len(items)} items")
        self.git_branch_lbl.setText(f" {branch}" if branch else "")
        
        # Populate Tree
        for d in items:
            icon = "📁" if d['is_dir'] else "📄"
            if d['kind'] in ["PY", "JS", "HTML", "CSS"]: icon = "👨‍💻"
            elif d['kind'] in ["PNG", "JPG"]: icon = "🖼️"
            
            item = QTreeWidgetItem([f"{icon} {d['name']}", self.loader_thread.format_size(d['size_val']), d['kind'], d['date']])
            item.setData(0, Qt.UserRole, d['path'])
            item.setData(0, Qt.UserRole + 1, d['is_dir'])
            
            # Git Colors
            if git_map:
                s = git_map.get(d['name'], "")
                if "M" in s: item.setForeground(0, QBrush(QColor("#fab387"))) # Orange
                elif "?" in s: item.setForeground(0, QBrush(QColor("#6c7086"))) # Grey
                elif "A" in s: item.setForeground(0, QBrush(QColor("#a6e3a1"))) # Green
                
            self.tree.addTopLevelItem(item)

        # Update Health Tab Stats
        txt = ""
        for ext, pct in lang_stats.items(): txt += f"• {ext}: {pct:.1f}%\n"
        self.lbl_lang_stats.setText(txt if txt else "Empty folder")

    # --- SELECTION & INTELLIGENCE ---
    def on_selection_changed(self):
        items = self.tree.selectedItems()
        if not items: return
        path = items[0].data(0, Qt.UserRole)
        is_dir = items[0].data(0, Qt.UserRole + 1)
        
        if is_dir: return

        # 1. Preview (Text/Image)
        mime, _ = mimetypes.guess_type(path)
        if mime and "image" in mime:
            self.preview_img.setPixmap(QPixmap(path).scaled(300, 300, Qt.KeepAspectRatio))
            self.preview_img.setVisible(True)
            self.preview_text.setVisible(False)
        else:
            try:
                with open(path, 'r', errors='ignore') as f:
                    self.preview_text.setText(f.read(8192))
                self.preview_text.setVisible(True)
                self.preview_img.setVisible(False)
            except: pass

        # 2. Git Blame
        self.update_git_blame(path)
        
        # 3. Deep Analysis (If Python)
        if path.endswith(".py"):
            self.analyzer_thread = CodeAnalyzer(path)
            self.analyzer_thread.analysis_ready.connect(self.update_intelligence)
            self.analyzer_thread.start()
        else:
            # Clear tabs if not code
            self.structure_tree.clear()
            self.graph_view.scene.clear()
            self.lbl_grade.setText("-")

    def update_intelligence(self, data):
        if not data: return
        
        # Structure
        self.structure_tree.populate(data['structure'])
        
        # Graph
        self.graph_view.build_graph("Current", data['imports'])
        
        # Audit
        self.lbl_grade.setText(data['grade'])
        colors = {"A": "#a6e3a1", "B": "#89b4fa", "C": "#fab387", "F": "#f38ba8"}
        self.lbl_grade.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {colors.get(data['grade'], '#fff')};")
        self.lbl_score.setText(f"Avg Complexity: {data['score']}")

    def update_git_blame(self, path):
        try:
            p = subprocess.run(["git", "log", "-1", "--format=%an (%cr): %s", path], 
                             cwd=os.path.dirname(path), capture_output=True, text=True)
            self.lbl_git_blame.setText(p.stdout.strip() if p.stdout.strip() else "Not tracked.")
        except: self.lbl_git_blame.setText("No Git info.")

    def analyze_with_brain(self):
        items = self.tree.selectedItems()
        if items: self.command_signal.emit(f"Analyze this file: {items[0].data(0, Qt.UserRole)}")

    def scroll_to_line(self, line):
        self.tabs.setCurrentIndex(0)
        doc = self.preview_text.document()
        blk = doc.findBlockByLineNumber(line - 1)
        cursor = QTextCursor(blk)
        self.preview_text.setTextCursor(cursor)
        self.preview_text.centerCursor()

    # --- OPERATIONS & NAV UTILS ---
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
            
            # Git / AI Ops
            path = items[0].data(0, Qt.UserRole)
            act_git = QAction("➕ Git Add", self)
            act_git.triggered.connect(lambda: self.command_signal.emit(f"[GITHUB] add | {path}"))
            menu.addAction(act_git)
            
            act_ai = QAction("🧠 Analyze", self)
            act_ai.triggered.connect(self.analyze_with_brain)
            menu.addAction(act_ai)
            
            menu.addSeparator()
            menu.addAction(self.act_del)
        else:
            menu.addAction(self.act_new_folder)
            menu.addAction(self.act_paste)
            menu.addAction(self.act_undo)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # --- FILE OPS (Copy/Paste/Etc) ---
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
        self.refresh_tree_threaded()

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
            try:
                os.rename(old, os.path.join(os.path.dirname(old), new))
                self.refresh_tree_threaded()
            except Exception as e: self.status_lbl.setText(f"Error: {e}")

    def create_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Name:")
        if ok and name:
            FileSkills.make_directory(os.path.join(self.current_path, name))
            self.refresh_tree_threaded()

    def undo_last_op(self):
        if not self.undo_stack: return
        op, a, b = self.undo_stack.pop()
        try:
            if op == "move": shutil.move(a, b)
            elif op == "copy": 
                if os.path.isdir(a): shutil.rmtree(a)
                else: os.remove(a)
            self.refresh_tree_threaded()
            self.status_lbl.setText("Undone.")
        except: self.status_lbl.setText("Undo Failed.")
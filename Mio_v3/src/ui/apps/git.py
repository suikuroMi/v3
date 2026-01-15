import os
import subprocess
import datetime
import re
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, 
                               QLineEdit, QPushButton, QMenu, QMessageBox, QLabel, 
                               QAbstractItemView, QProgressBar, QSplitter, QTextEdit, 
                               QWidget, QTabWidget, QComboBox, QInputDialog, QCheckBox,
                               QGroupBox, QListWidget, QListWidgetItem, QToolBar, QTableWidget, QTableWidgetItem)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QBrush, QFont, QSyntaxHighlighter, QTextCharFormat, QKeySequence

from .base import BaseApp

# --- 1. SECURITY & UTILS ---
def is_safe_branch_name(name):
    """Strict validation for git branch names."""
    if not name or len(name) > 255: return False
    # Check against Git's actual check-ref-format rules
    if any(ord(c) < 32 for c in name): return False # No control chars
    pattern = r'^(?!.*\.\.)(?!.*\/\/)(?!.*[@\\])(?!.*\/\.)(?!.*\.\.\.)[^\s~^:?*[\\]+$'
    return bool(re.match(pattern, name))

def is_safe_path(path):
    """Prevent path traversal."""
    if ".." in path or path.startswith("/") or "\\" in path: return False
    return True

def find_git_root(path):
    """Walks up to find the .git directory."""
    current = os.path.abspath(path)
    while current:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current: return None
        current = parent
    return None

# --- 2. HIGHLIGHTER ---
class DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.add_fmt = QTextCharFormat()
        self.add_fmt.setForeground(QColor("#a6e3a1"))
        self.add_fmt.setBackground(QColor("#1e2e2e"))
        self.del_fmt = QTextCharFormat()
        self.del_fmt.setForeground(QColor("#f38ba8"))
        self.del_fmt.setBackground(QColor("#2e1e1e"))
        self.head_fmt = QTextCharFormat()
        self.head_fmt.setForeground(QColor("#89b4fa"))
        self.head_fmt.setFontWeight(QFont.Bold)

    def highlightBlock(self, text):
        if text.startswith("+") and not text.startswith("+++"):
            self.setFormat(0, len(text), self.add_fmt)
        elif text.startswith("-") and not text.startswith("---"):
            self.setFormat(0, len(text), self.del_fmt)
        elif text.startswith("diff") or text.startswith("index"):
            self.setFormat(0, len(text), self.head_fmt)

# --- 3. WORKER ---
class GitWorker(QThread):
    status_ready = Signal(dict, list) 
    diff_ready = Signal(str, str) # content, stats
    log_ready = Signal(list, int) # logs, offset
    stash_ready = Signal(list)
    blame_ready = Signal(list)
    op_finished = Signal(bool, str)

    def __init__(self, repo_path):
        super().__init__()
        self.repo_path = repo_path
        self.mode = None
        self.args = []

    def refresh_status(self):
        self.mode = "status"
        self.start()

    def get_diff(self, filename, staged=False):
        self.mode = "diff"
        self.args = [filename, staged]
        self.start()

    def get_log(self, limit=50, offset=0, filter_txt=""):
        self.mode = "log"
        self.args = [limit, offset, filter_txt]
        self.start()

    def get_stash(self):
        self.mode = "stash_list"
        self.start()
        
    def get_blame(self, filename):
        self.mode = "blame"
        self.args = [filename]
        self.start()

    def run_cmd(self, cmd_args, msg_on_success):
        self.mode = "cmd"
        self.args = [cmd_args, msg_on_success]
        self.start()

    def _run_git(self, args):
        return subprocess.run(
            ["git"] + args, 
            cwd=self.repo_path, 
            capture_output=True, 
            text=True, 
            encoding='utf-8', 
            errors='ignore'
        )

    def run(self):
        if not self.repo_path or not os.path.exists(os.path.join(self.repo_path, ".git")):
            self.op_finished.emit(False, "Not a git repository")
            return

        try:
            if self.mode == "status":
                # Branches
                res = self._run_git(["branch", "--list"])
                branches = [l[2:].strip() for l in res.stdout.splitlines()]
                current = next((l[2:].strip() for l in res.stdout.splitlines() if l.startswith("*")), "main")
                
                # Status
                res = self._run_git(["status", "--porcelain"])
                changes = []
                for line in res.stdout.splitlines():
                    if len(line) > 3:
                        x, y = line[0], line[1]
                        path = line[3:].strip('"')
                        changes.append({"x": x, "y": y, "path": path})
                
                self.status_ready.emit({"changes": changes, "current": current}, branches)

            elif self.mode == "diff":
                path, staged = self.args
                cmd = ["diff"]
                if staged: cmd.append("--cached")
                cmd.append("--")
                cmd.append(path)
                res = self._run_git(cmd)
                
                # Stats
                adds = res.stdout.count('\n+')
                dels = res.stdout.count('\n-')
                self.diff_ready.emit(res.stdout, f"Stats: +{adds} / -{dels}")

            elif self.mode == "blame":
                path = self.args[0]
                res = self._run_git(["blame", "--date=short", path])
                lines = []
                for line in res.stdout.splitlines():
                    # Parse: hash (Author Date) Content
                    parts = line.split(")", 1)
                    if len(parts) == 2:
                        meta = parts[0].split()
                        commit = meta[0]
                        date = meta[-2]
                        author = " ".join(meta[1:-2]).strip("(")
                        content = parts[1]
                        lines.append((commit, author, date, content))
                self.blame_ready.emit(lines)

            elif self.mode == "log":
                limit, offset, flt = self.args
                # Format: Hash|Author|RelDate|Refs|Subject
                cmd = ["log", f"--skip={offset}", f"-{limit}", "--pretty=format:%h|%an|%ar|%d|%s"]
                if flt: 
                    # Search msg OR author
                    cmd.extend([f"--grep={flt}", f"--author={flt}", "--all"])
                
                res = self._run_git(cmd)
                logs = []
                if res.stdout:
                    logs = [line.split("|") for line in res.stdout.splitlines()]
                self.log_ready.emit(logs, offset)

            elif self.mode == "stash_list":
                res = self._run_git(["stash", "list"])
                self.stash_ready.emit(res.stdout.splitlines())

            elif self.mode == "cmd":
                args, msg = self.args
                res = self._run_git(args)
                if res.returncode == 0:
                    self.op_finished.emit(True, msg)
                else:
                    self.op_finished.emit(False, f"Error: {res.stderr}")

        except Exception as e:
            self.op_finished.emit(False, str(e))

# --- 4. UI COMPONENTS ---

class BlameViewer(QTableWidget):
    def __init__(self):
        super().__init__()
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Commit", "Author", "Date", "Content"])
        self.setStyleSheet("QTableWidget { background: #11111b; color: #cdd6f4; border: none; } QHeaderView::section { background: #1e1e2e; color: #aaa; }")
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def load_data(self, data):
        self.setRowCount(len(data))
        for r, (h, a, d, c) in enumerate(data):
            self.setItem(r, 0, QTableWidgetItem(h))
            self.setItem(r, 1, QTableWidgetItem(a))
            self.setItem(r, 2, QTableWidgetItem(d))
            self.setItem(r, 3, QTableWidgetItem(c))
        self.resizeColumnsToContents()

class CommitPanel(QWidget):
    commit_requested = Signal(str)
    def __init__(self):
        super().__init__()
        l = QVBoxLayout(self)
        l.setContentsMargins(0,0,0,0)
        self.input = QTextEdit()
        self.input.setPlaceholderText("Commit message... (Ctrl+Enter to commit)")
        self.input.setFixedHeight(60)
        self.input.setStyleSheet("background:#222;color:#fff;border:1px solid #444;")
        b = QPushButton("Commit")
        b.clicked.connect(self.on_commit)
        b.setStyleSheet("background:#a6e3a1;color:#1e1e2e;font-weight:bold;")
        l.addWidget(self.input)
        l.addWidget(b)
        
    def keyPressEvent(self, e):
        if (e.modifiers() & Qt.ControlModifier) and e.key() in (Qt.Key_Enter, Qt.Key_Return): self.on_commit()
        else: super().keyPressEvent(e)
        
    def on_commit(self):
        if t:=self.input.toPlainText().strip(): 
            self.commit_requested.emit(t)
            self.input.clear()

class StashPanel(QWidget):
    action_requested = Signal(str, str)
    def __init__(self):
        super().__init__()
        l = QVBoxLayout(self)
        l.setContentsMargins(0,0,0,0)
        h = QHBoxLayout()
        for txt, act in [("💾 Save", "save"), ("📤 Pop", "pop"), ("❌ Drop", "drop")]:
            b = QPushButton(txt)
            b.clicked.connect(lambda _, a=act: self.req(a))
            h.addWidget(b)
        l.addLayout(h)
        self.list = QListWidget()
        self.list.setStyleSheet("background:#1e1e2e;color:#cdd6f4;border:none;")
        l.addWidget(self.list)
        
    def req(self, act):
        if act=="save": 
            t,ok = QInputDialog.getText(self,"Stash","Msg:")
            if ok: self.action_requested.emit("save", t)
        elif i:=self.list.currentItem(): 
            self.action_requested.emit(act, i.text().split(":")[0])
            
    def update_list(self, lst): 
        self.list.clear()
        self.list.addItems(lst)

# --- 5. MAIN APPLICATION ---
class GitApp(BaseApp):
    def __init__(self, brain=None):
        super().__init__("Git God Mode", "git.png", "#F4511E")
        self.brain = brain
        self.repo_path = find_git_root(os.getcwd()) or os.getcwd()
        self.worker = GitWorker(self.repo_path)
        self.log_offset = 0
        
        main = QVBoxLayout()
        
        # 1. Top Bar
        top = QHBoxLayout()
        self.btn_repo = QPushButton(f"📂 {os.path.basename(self.repo_path)}")
        self.btn_repo.clicked.connect(self.change_repo)
        self.btn_repo.setStyleSheet("text-align: left; padding: 5px; background: #333; color: white;")
        
        self.combo_branch = QComboBox()
        self.combo_branch.setStyleSheet("background: #222; color: #fab387;")
        self.combo_branch.activated.connect(self.switch_branch)
        
        top.addWidget(self.btn_repo)
        top.addWidget(QLabel("Branch:"))
        top.addWidget(self.combo_branch)
        top.addWidget(QPushButton("➕", clicked=self.create_branch))
        top.addStretch()
        
        for lbl, cmd in [("🔄 Fetch", "fetch"), ("⬇ Pull", "pull"), ("⬆ Push", "push")]:
            btn = QPushButton(lbl)
            btn.clicked.connect(lambda _, c=cmd: self.run_git_cmd([c], f"{c} done"))
            top.addWidget(btn)
        main.addLayout(top)
        
        # 2. Splitter (Staging | Work Area)
        split = QSplitter(Qt.Horizontal)
        
        # Left Panel
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0,0,0,0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Filter files...")
        self.search.textChanged.connect(self.filter_tree)
        self.search.setStyleSheet("background:#222;color:#aaa;border:1px solid #444;")
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Working Tree")
        self.tree.setStyleSheet("QTreeWidget{background:#1e1e2e;color:#cdd6f4;border:none;} QTreeWidget::item:hover{background:#313244;}")
        self.tree.itemClicked.connect(self.on_file_click)
        self.tree.itemChanged.connect(self.on_check)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.ctx_menu)
        
        self.commit_panel = CommitPanel()
        self.commit_panel.commit_requested.connect(lambda m: self.run_git_cmd(["commit", "-m", m], "Committed"))
        
        ll.addWidget(self.search)
        ll.addWidget(self.tree)
        ll.addWidget(self.commit_panel)
        split.addWidget(left)
        
        # Right Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane{border:none;} QTabBar::tab{background:#11111b;color:#aaa;} QTabBar::tab:selected{color:#fff;border-bottom:2px solid #fab387;}")
        
        # Tab 1: Diff
        diff_w = QWidget()
        dl = QVBoxLayout(diff_w)
        dl.setContentsMargins(0,0,0,0)
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color:#aaa;font-size:10px;")
        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Consolas", 10))
        self.diff_view.setStyleSheet("background:#11111b;color:#cdd6f4;border:none;")
        self.hl = DiffHighlighter(self.diff_view.document())
        dl.addWidget(self.lbl_stats)
        dl.addWidget(self.diff_view)
        self.tabs.addTab(diff_w, "📝 Diff")
        
        # Tab 2: History (Time Lord)
        hist_w = QWidget()
        hl = QVBoxLayout(hist_w)
        hl.setContentsMargins(0,0,0,0)
        
        htb = QHBoxLayout()
        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText("🔍 Msg / Author")
        self.log_search.returnPressed.connect(lambda: self.load_log(True))
        self.log_search.setStyleSheet("background:#222;color:#fff;border:1px solid #444;")
        htb.addWidget(self.log_search)
        htb.addWidget(QPushButton("Go", clicked=lambda: self.load_log(True)))
        
        self.log_list = QTreeWidget()
        self.log_list.setHeaderLabels(["Graph/Msg", "Author", "Time"])
        self.log_list.setStyleSheet("background:#1e1e2e;color:#cdd6f4;border:none;")
        self.log_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log_list.customContextMenuRequested.connect(self.log_menu)
        self.log_list.setColumnWidth(0, 350)
        
        hl.addLayout(htb)
        hl.addWidget(self.log_list)
        hl.addWidget(QPushButton("Load More...", clicked=lambda: self.load_log(False)))
        self.tabs.addTab(hist_w, "📜 History")
        
        # Tab 3: Blame
        self.blame_view = BlameViewer()
        self.tabs.addTab(self.blame_view, "🕵️ Blame")
        
        # Tab 4: Stash
        self.stash_p = StashPanel()
        self.stash_p.action_requested.connect(self.handle_stash)
        self.tabs.addTab(self.stash_p, "📦 Stash")
        
        split.addWidget(self.tabs)
        split.setSizes([300, 600])
        main.addWidget(split)
        
        # 3. Status
        self.status = QLabel("Ready")
        self.status.setStyleSheet("color:#aaa;")
        main.addWidget(self.status)
        self.content_layout.addLayout(main)
        
        # Connect
        self.worker.status_ready.connect(self.on_status)
        self.worker.diff_ready.connect(self.on_diff)
        self.worker.log_ready.connect(self.on_log)
        self.worker.stash_ready.connect(self.stash_p.update_list)
        self.worker.blame_ready.connect(self.blame_view.load_data)
        self.worker.op_finished.connect(self.on_done)
        
        self.refresh()

    def refresh(self):
        self.status.setText("Scanning...")
        self.worker.refresh_status()
        self.load_log(True)
        self.worker.get_stash()

    def change_repo(self):
        if p:=QFileDialog.getExistingDirectory(self, "Select Repo"):
            if r:=find_git_root(p):
                self.repo_path = r
                self.worker.repo_path = r
                self.btn_repo.setText(f"📂 {os.path.basename(r)}")
                self.refresh()

    def load_log(self, reset=False):
        if reset: self.log_offset = 0
        self.worker.get_log(limit=50, offset=self.log_offset, filter_txt=self.log_search.text())

    def run_git_cmd(self, args, msg):
        self.status.setText(f"Running {args[0]}...")
        self.worker.run_cmd(args, msg)

    # --- UI SLOTS ---
    def switch_branch(self):
        b = self.combo_branch.currentText()
        if is_safe_branch_name(b): self.run_git_cmd(["checkout", b], f"Switched {b}")

    def create_branch(self):
        n, ok = QInputDialog.getText(self, "New Branch", "Name:")
        if ok and is_safe_branch_name(n): self.run_git_cmd(["checkout", "-b", n], f"Created {n}")

    def filter_tree(self, txt):
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            cat = root.child(i)
            for j in range(cat.childCount()):
                cat.child(j).setHidden(txt.lower() not in cat.child(j).text(0).lower())

    def on_status(self, data, branches):
        self.combo_branch.blockSignals(True)
        self.combo_branch.clear()
        self.combo_branch.addItems(branches)
        self.combo_branch.setCurrentText(data.get("current",""))
        self.combo_branch.blockSignals(False)
        
        self.tree.blockSignals(True)
        self.tree.clear()
        
        s_root = QTreeWidgetItem(["Staged"]); s_root.setForeground(0, QBrush(QColor("#a6e3a1"))); s_root.setExpanded(True)
        u_root = QTreeWidgetItem(["Unstaged"]); u_root.setForeground(0, QBrush(QColor("#fab387"))); u_root.setExpanded(True)
        c_root = QTreeWidgetItem(["Conflicts"]); c_root.setForeground(0, QBrush(QColor("#f38ba8"))); c_root.setExpanded(True)
        
        for c in data.get("changes", []):
            x, y, p = c['x'], c['y'], c['path']
            # Conflicts
            if x in ['U', 'A'] and y in ['U', 'A']:
                i = QTreeWidgetItem([f"⚠️ {p}"]); i.setData(0, Qt.UserRole, p); i.setData(0, Qt.UserRole+2, True)
                c_root.addChild(i)
                continue
            # Staged
            if x not in [' ', '?']:
                i = QTreeWidgetItem([f"{x}  {p}"]); i.setData(0, Qt.UserRole, p); i.setData(0, Qt.UserRole+1, True); i.setCheckState(0, Qt.Checked)
                s_root.addChild(i)
            # Unstaged
            if y != ' ':
                icon = "📝" if y=='M' else ("🗑️" if y=='D' else "❓")
                i = QTreeWidgetItem([f"{icon} {p}"]); i.setData(0, Qt.UserRole, p); i.setData(0, Qt.UserRole+1, False); i.setCheckState(0, Qt.Unchecked)
                u_root.addChild(i)

        for r in [c_root, s_root, u_root]: 
            if r.childCount(): self.tree.addTopLevelItem(r)
        self.tree.blockSignals(False)
        self.status.setText("Ready")

    def on_check(self, item, _):
        path = item.data(0, Qt.UserRole)
        if not path or not is_safe_path(path): return
        checked = item.checkState(0) == Qt.Checked
        is_staged = item.data(0, Qt.UserRole+1)
        if is_staged and not checked: self.run_git_cmd(["restore", "--staged", path], f"Unstaged {path}")
        elif not is_staged and checked: self.run_git_cmd(["add", path], f"Staged {path}")

    def on_file_click(self, item, _):
        path = item.data(0, Qt.UserRole)
        is_staged = item.data(0, Qt.UserRole+1)
        if path and is_safe_path(path):
            self.worker.get_diff(path, staged=is_staged)
            self.tabs.setCurrentIndex(0)

    def on_diff(self, txt, stats):
        self.diff_view.setText(txt)
        self.lbl_stats.setText(stats)

    def on_log(self, logs, offset):
        if offset == 0: self.log_list.clear()
        self.log_offset = offset + len(logs)
        for row in logs:
            if len(row) < 5: continue
            h, a, t, ref, m = row
            if ref:
                ref = ref.strip("()")
                # Decorate refs
                ref = ref.replace("tag:", "🏷️").replace("HEAD", "📍").replace("origin", "☁️")
                m = f"[{ref}] {m}"
            
            i = QTreeWidgetItem([m, a, t])
            i.setData(0, Qt.UserRole, h)
            self.log_list.addTopLevelItem(i)

    def on_done(self, s, m): 
        self.status.setText(f"✅ {m}" if s else f"❌ {m}")
        if s: self.worker.refresh_status()

    def handle_stash(self, act, arg):
        if act=="save": self.run_git_cmd(["stash", "save", arg], "Stashed")
        elif act=="pop": self.run_git_cmd(["stash", "pop", arg], "Popped")
        elif act=="drop": self.run_git_cmd(["stash", "drop", arg], "Dropped")

    # --- MENUS ---
    def ctx_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item: return
        path = item.data(0, Qt.UserRole)
        is_conf = item.data(0, Qt.UserRole+2)
        m = QMenu(); m.setStyleSheet("background:#333;color:#fff;")
        if is_conf:
            m.addAction("⚡ Resolve: Ours", lambda: self.run_git_cmd(["checkout", "--ours", path], "Ours"))
            m.addAction("⚡ Resolve: Theirs", lambda: self.run_git_cmd(["checkout", "--theirs", path], "Theirs"))
            m.addAction("✅ Mark Resolved", lambda: self.run_git_cmd(["add", path], "Resolved"))
        elif "?" in item.text(0):
            m.addAction("🙈 Ignore", lambda: self.ignore(path))
        m.addSeparator()
        m.addAction("🕵️ Blame", lambda: (self.worker.get_blame(path), self.tabs.setCurrentIndex(2)))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def log_menu(self, pos):
        item = self.log_list.itemAt(pos)
        if not item: return
        commit = item.data(0, Qt.UserRole)
        m = QMenu(); m.setStyleSheet("background:#333;color:#fff;")
        m.addAction("🍒 Cherry-Pick", lambda: self.run_git_cmd(["cherry-pick", commit], f"Picked {commit}"))
        m.addAction("↩️ Revert", lambda: self.run_git_cmd(["revert", commit], f"Reverted {commit}"))
        
        tm = m.addMenu("🏷️ Tag")
        tm.addAction("Create Tag", lambda: self.create_tag(commit))
        tm.addAction("Delete Tag", lambda: self.delete_tag())
        
        rm = m.addMenu("⚠️ Reset Branch")
        rm.addAction("Soft (Keep Changes)", lambda: self.run_git_cmd(["reset", "--soft", commit], "Soft Reset"))
        rm.addAction("Hard (Discard Changes)", lambda: self.hard_reset(commit))
        
        m.exec(self.log_list.viewport().mapToGlobal(pos))

    def ignore(self, path):
        with open(os.path.join(self.repo_path, ".gitignore"), "a") as f: f.write(f"\n{path}")
        self.refresh()

    def create_tag(self, c):
        n, ok = QInputDialog.getText(self, "Tag", "Name:")
        if ok and n: self.run_git_cmd(["tag", n, c], f"Tagged {n}")

    def delete_tag(self):
        n, ok = QInputDialog.getText(self, "Delete Tag", "Name:")
        if ok and n: self.run_git_cmd(["tag", "-d", n], f"Deleted {n}")

    def hard_reset(self, c):
        if QMessageBox.question(self,"Reset","Discard all changes?",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            self.run_git_cmd(["reset", "--hard", c], "Hard Reset")
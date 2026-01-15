import sqlite3
import os
import csv
import json
import re
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, 
                               QLineEdit, QPushButton, QMenu, QMessageBox, QLabel, 
                               QAbstractItemView, QProgressBar, QSplitter, QTableWidget, 
                               QTableWidgetItem, QTextEdit, QWidget, QTabWidget, QHeaderView,
                               QFileDialog, QComboBox, QSpinBox, QCheckBox, QInputDialog,
                               QCompleter, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
                               QGraphicsTextItem)
from PySide6.QtCore import Qt, QThread, Signal, QRegularExpression
from PySide6.QtGui import (QAction, QKeySequence, QColor, QBrush, QFont, QTextCursor, 
                           QSyntaxHighlighter, QTextCharFormat, QPainter, QPen)

from .base import BaseApp

# --- 1. UTILS: FORMATTING & HIGHLIGHTING ---

def format_sql(sql):
    """Heuristic SQL beautifier."""
    keywords = ["SELECT", "FROM", "WHERE", "AND", "OR", "ORDER BY", "GROUP BY", "LIMIT", 
                "INSERT", "UPDATE", "DELETE", "JOIN", "LEFT JOIN", "INNER JOIN", "UNION", 
                "VALUES", "SET", "HAVING", "WITH", "CASE", "WHEN", "THEN", "ELSE", "END"]
    formatted = sql
    for kw in keywords:
        # Add newline before keyword if it's not already there
        formatted = re.sub(f"\\b{kw}\\b", f"\n{kw}", formatted, flags=re.IGNORECASE)
    return formatted.strip()

class SqlHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []
        
        # Keywords (Pink/Red)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#f38ba8")) 
        fmt.setFontWeight(QFont.Bold)
        keywords = ["SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "DROP", "TABLE", 
                    "INTO", "VALUES", "AND", "OR", "NOT", "NULL", "ORDER", "BY", "LIMIT", 
                    "OFFSET", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON", "AS", "CREATE", 
                    "ALTER", "PRAGMA", "BEGIN", "COMMIT", "ROLLBACK", "LIKE", "DISTINCT", 
                    "GROUP", "HAVING", "EXPLAIN", "QUERY", "PLAN", "WITH", "SET", "VIEW", "INDEX"]
        for w in keywords:
            self.rules.append((QRegularExpression(f"\\b{w}\\b", QRegularExpression.CaseInsensitiveOption), fmt))
        
        # Strings (Green)
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#a6e3a1")) 
        self.rules.append((QRegularExpression("'.*?'"), str_fmt))
        self.rules.append((QRegularExpression("\".*?\""), str_fmt))
        
        # Numbers (Orange)
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#fab387")) 
        self.rules.append((QRegularExpression("\\b[0-9]+\\b"), num_fmt))

        # Comments (Grey)
        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor("#6c7086"))
        self.rules.append((QRegularExpression("--.*"), cmt_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            match = pattern.match(text)
            while match.hasMatch():
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)
                match = pattern.match(text, match.capturedStart() + match.capturedLength())

# --- 2. WORKER (Threaded & Secure) ---
class DbSession(QThread):
    """Handles DB operations for a single tab with Parameterized Queries."""
    query_finished = Signal(list, list, str, int, bool) # headers, rows, error, count, is_editable
    schema_loaded = Signal(dict)
    exec_finished = Signal(str)
    explain_finished = Signal(str)

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.mode = None
        self.sql = ""
        self.params = ()
        self.pagination = {"limit": 100, "offset": 0}

    def run_query(self, sql, limit=100, offset=0):
        self.mode = "query"
        self.sql = sql
        self.pagination = {"limit": limit, "offset": offset}
        self.start()

    def run_explain(self, sql):
        self.mode = "explain"
        self.sql = sql
        self.start()

    def load_schema(self):
        self.mode = "schema"
        self.start()

    def execute_update(self, sql, params=()):
        self.mode = "update"
        self.sql = sql
        self.params = params
        self.start()

    def run(self):
        if not os.path.exists(self.db_path) and self.mode != "schema":
             self.query_finished.emit([], [], "DB not found.", 0, False)
             return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            if self.mode == "schema":
                schema = {}
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                for (table,) in cursor.fetchall():
                    # Sanitize table name check (Alpha-numeric + underscore only)
                    if re.match(r'^[a-zA-Z0-9_]+$', table):
                        cursor.execute(f"PRAGMA table_info({table})")
                        schema[table] = [(c[1], c[2]) for c in cursor.fetchall()]
                self.schema_loaded.emit(schema)

            elif self.mode == "query":
                clean_sql = self.sql.strip().upper()
                is_editable = False
                
                # Check editability: "SELECT * FROM table" (Simple heuristic)
                match = re.match(r"^SELECT\s+\*\s+FROM\s+([a-zA-Z0-9_]+)\s*$", clean_sql, re.IGNORECASE)
                
                if match:
                    # Fetch rowid for editing
                    table = match.group(1)
                    # Use params for pagination
                    final_sql = f"SELECT rowid, * FROM {table} LIMIT ? OFFSET ?"
                    params = (self.pagination['limit'], self.pagination['offset'])
                    cursor.execute(final_sql, params)
                    is_editable = True
                else:
                    # Subquery Wrapper for safe pagination of complex queries (GROUP BY, etc)
                    if "LIMIT" not in clean_sql:
                        final_sql = f"SELECT * FROM ({self.sql}) LIMIT ? OFFSET ?"
                        params = (self.pagination['limit'], self.pagination['offset'])
                        cursor.execute(final_sql, params)
                    else:
                        cursor.execute(self.sql) # Trust user's limit logic
                
                if cursor.description:
                    headers = [d[0] for d in cursor.description]
                    rows = cursor.fetchall()
                    self.query_finished.emit(headers, rows, "", len(rows), is_editable)
                else:
                    conn.commit()
                    self.query_finished.emit([], [], f"Rows affected: {cursor.rowcount}", 0, False)

            elif self.mode == "update":
                # Secure execution with parameters
                cursor.execute(self.sql, self.params)
                conn.commit()
                self.exec_finished.emit(f"✅ Success. Rows affected: {cursor.rowcount}")

            elif self.mode == "explain":
                cursor.execute(f"EXPLAIN QUERY PLAN {self.sql}")
                rows = cursor.fetchall()
                plan = "\n".join([f"{r[3]}" for r in rows])
                self.explain_finished.emit(f"📋 Query Plan:\n{plan}")

        except Exception as e:
            if self.mode == "update": self.exec_finished.emit(f"❌ Error: {e}")
            elif self.mode == "explain": self.explain_finished.emit(f"❌ Error: {e}")
            else: self.query_finished.emit([], [], str(e), 0, False)
        finally:
            conn.close()

# --- 3. UI COMPONENTS ---

class SimpleChart(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setStyleSheet("background: #11111b; border: none;")

    def plot(self, headers, rows):
        self.scene.clear()
        if not rows or len(headers) < 2: 
            t = self.scene.addText("No data to chart.")
            t.setDefaultTextColor(QColor("#666"))
            return

        # Simple Bar Chart (Col 0 = Label, Col 1 = Value)
        try:
            data = []
            # Skip rowid if present (usually index 0 in editable queries)
            start_idx = 1 if "rowid" in headers[0].lower() else 0 
            
            # Use top 50 rows
            for r in rows[:50]: 
                val = float(r[start_idx+1])
                label = str(r[start_idx])
                data.append((label, val))
            
            if not data: return

            max_val = max([d[1] for d in data]) or 1
            bar_w = 30
            gap = 10
            scale = 200 / max_val
            x = 0
            
            for label, val in data:
                h = val * scale
                # Bar
                rect = QGraphicsRectItem(x, 200 - h, bar_w, h)
                rect.setBrush(QBrush(QColor("#89b4fa")))
                rect.setPen(QPen(Qt.NoPen))
                self.scene.addItem(rect)
                
                # Label (Truncated)
                t = self.scene.addText(label[:4]) 
                t.setDefaultTextColor(QColor("#cdd6f4"))
                t.setFont(QFont("Arial", 8))
                t.setPos(x, 205)
                
                # Value (Tooltip style)
                v = self.scene.addText(f"{int(val)}")
                v.setDefaultTextColor(QColor("#a6adc8"))
                v.setFont(QFont("Arial", 7))
                v.setPos(x, 200 - h - 15)
                
                x += bar_w + gap
        except: 
            self.scene.addText("Incompatible data for chart.\nNeeds: [Label, Number]")

class SqlEditor(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setFont(QFont("Consolas", 10))
        self.setStyleSheet("QTextEdit { background: #181825; color: #cdd6f4; border: 1px solid #333; }")
        self.highlighter = SqlHighlighter(self.document())
        self.completer = None

    def set_completer(self, words):
        self.completer = QCompleter(words)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self.insert_completion)

    def insert_completion(self, text):
        tc = self.textCursor()
        extra = len(text) - len(self.completer.completionPrefix())
        tc.movePosition(QTextCursor.Left)
        tc.movePosition(QTextCursor.EndOfWord)
        tc.insertText(text[-extra:])
        self.setTextCursor(tc)

    def keyPressEvent(self, e):
        if self.completer and self.completer.popup().isVisible() and e.key() in (Qt.Key_Enter, Qt.Key_Tab):
            e.ignore()
            return
        if (e.modifiers() & Qt.ControlModifier) and e.key() == Qt.Key_Space:
            self.completer.setCompletionPrefix(self.textCursor().selectedText())
            rect = self.cursorRect()
            rect.setWidth(self.completer.popup().sizeHintForColumn(0) + self.completer.popup().verticalScrollBar().sizeHint().width())
            self.completer.complete(rect)
        else:
            super().keyPressEvent(e)

class ResultGrid(QTableWidget):
    cell_edit_request = Signal(int, int, str, str) # rowid, col_name, old_val, new_val

    def __init__(self):
        super().__init__()
        self.setStyleSheet("QTableWidget { background: #1e1e2e; color: #cdd6f4; gridline-color: #313244; border: none; } QHeaderView::section { background: #11111b; color: #aaa; }")
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.row_ids = {} 
        self.itemChanged.connect(self.on_item_changed)
        self.editable_mode = False

    def display_data(self, headers, rows, is_editable):
        self.blockSignals(True)
        self.clear()
        self.editable_mode = is_editable
        
        start_col = 1 if is_editable else 0
        display_headers = headers[start_col:]
        
        self.setColumnCount(len(display_headers))
        self.setRowCount(len(rows))
        self.setHorizontalHeaderLabels(display_headers)
        self.row_ids.clear()
        
        for r, row in enumerate(rows):
            if is_editable: self.row_ids[r] = row[0]
            for c, val in enumerate(row[start_col:]):
                item = QTableWidgetItem(str(val))
                if is_editable:
                    item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    item.setBackground(QColor("#313244"))
                self.setItem(r, c, item)
        self.blockSignals(False)

    def on_item_changed(self, item):
        if not self.editable_mode: return
        r, c = item.row(), item.column()
        rowid = self.row_ids.get(r)
        col_name = self.horizontalHeaderItem(c).text()
        new_val = item.text()
        if rowid: self.cell_edit_request.emit(rowid, col_name, "", new_val)

class QuerySession(QWidget):
    """Isolated Session: Editor + Grid + Chart + Worker"""
    def __init__(self, db_path, parent_app):
        super().__init__()
        self.app = parent_app
        self.worker = DbSession(db_path)
        self.worker.query_finished.connect(self.on_results)
        self.worker.exec_finished.connect(lambda msg: self.lbl_status.setText(msg))
        self.worker.explain_finished.connect(self.on_explain)
        
        self.page = 0
        self.limit = 100
        self.last_sql = ""

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        # Toolbar
        tb = QHBoxLayout()
        self.btn_run = QPushButton("▶ Run")
        self.btn_run.clicked.connect(lambda: self.run_sql(reset=True))
        self.btn_run.setStyleSheet("background: #a6e3a1; color: #1e1e2e; font-weight: bold;")
        
        self.btn_fmt = QPushButton("✨ Format")
        self.btn_fmt.clicked.connect(self.format_sql)
        
        self.btn_exp = QPushButton("🔍 Explain")
        self.btn_exp.clicked.connect(self.explain_sql)
        
        self.btn_export = QPushButton("📤 Export")
        self.btn_export.clicked.connect(self.export_data)
        
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(10, 5000)
        self.spin_limit.setValue(100)
        
        tb.addWidget(self.btn_run)
        tb.addWidget(self.btn_fmt)
        tb.addWidget(self.btn_exp)
        tb.addWidget(self.btn_export)
        tb.addStretch()
        tb.addWidget(QLabel("Limit:"))
        tb.addWidget(self.spin_limit)
        tb.addWidget(QPushButton("◀", clicked=self.prev_page))
        tb.addWidget(QPushButton("▶", clicked=self.next_page))
        
        self.editor = SqlEditor()
        self.editor.setFixedHeight(150)
        
        # Result Tabs (Grid / Chart)
        self.res_tabs = QTabWidget()
        self.grid = ResultGrid()
        self.grid.cell_edit_request.connect(self.handle_edit)
        self.chart = SimpleChart()
        
        self.res_tabs.addTab(self.grid, "📋 Table")
        self.res_tabs.addTab(self.chart, "📊 Chart")
        
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #aaa; margin-top: 5px;")
        
        layout.addLayout(tb)
        layout.addWidget(self.editor)
        layout.addWidget(self.res_tabs)
        layout.addWidget(self.lbl_status)

    def run_sql(self, reset=True):
        sql = self.editor.toPlainText().strip()
        if not sql: return
        self.last_sql = sql
        if reset: self.page = 0
        
        # Destructive Check
        destructive = ["DROP", "DELETE", "UPDATE", "ALTER"]
        if any(w in sql.upper() for w in destructive):
            if QMessageBox.warning(self, "Safety", "Query modifies data. Proceed?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.No:
                return

        self.lbl_status.setText("Running...")
        self.worker.run_query(sql, self.spin_limit.value(), self.page * self.spin_limit.value())
        self.app.add_to_history(sql)

    def explain_sql(self):
        sql = self.editor.toPlainText().strip()
        if sql: self.worker.run_explain(sql)

    def on_results(self, headers, rows, err, count, editable):
        if err:
            self.lbl_status.setText(f"❌ {err}")
            QMessageBox.critical(self, "Error", err)
        else:
            self.grid.display_data(headers, rows, editable)
            self.chart.plot(headers, rows)
            mode = "EDITABLE" if editable else "READ-ONLY"
            self.lbl_status.setText(f"✅ Loaded {count} rows (Page {self.page+1}) [{mode}]")

    def on_explain(self, text):
        QMessageBox.information(self, "Query Plan", text)

    def handle_edit(self, rowid, col, old, new):
        match = re.match(r"^SELECT\s+\*\s+FROM\s+([a-zA-Z0-9_]+)", self.last_sql, re.IGNORECASE)
        if match:
            table = match.group(1)
            # SECURE: Using Parameterized Query to prevent injection
            sql = f"UPDATE {table} SET {col} = ? WHERE rowid = ?"
            
            if QMessageBox.question(self, "Confirm Update", f"Update {col} to '{new}'?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                self.worker.execute_update(sql, (new, rowid))

    def format_sql(self):
        self.editor.setText(format_sql(self.editor.toPlainText()))

    def export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "", "CSV (*.csv);;JSON (*.json)")
        if not path: return
        try:
            # Re-fetch everything from grid
            headers = [self.grid.horizontalHeaderItem(i).text() for i in range(self.grid.columnCount())]
            rows = []
            for r in range(self.grid.rowCount()):
                rows.append([self.grid.item(r, c).text() for c in range(self.grid.columnCount())])
                
            if path.endswith(".csv"):
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    w = csv.writer(f)
                    w.writerow(headers)
                    w.writerows(rows)
            elif path.endswith(".json"):
                data = [dict(zip(headers, r)) for r in rows]
                with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)
            self.lbl_status.setText(f"✅ Exported to {os.path.basename(path)}")
        except Exception as e: self.lbl_status.setText(f"❌ Export Failed: {e}")

    def next_page(self):
        self.page += 1
        self.run_sql(reset=False)
    def prev_page(self):
        if self.page > 0:
            self.page -= 1
            self.run_sql(reset=False)

# --- 4. MAIN APP ---
class DbApp(BaseApp):
    def __init__(self, brain=None):
        super().__init__("Data Sovereign", "database.png", "#009688")
        self.brain = brain
        self.db_path = "mio_memory.db"
        
        # State
        self.snippets = {}
        self.history = []
        self.load_data()
        
        main = QVBoxLayout()
        
        # Header
        top = QHBoxLayout()
        self.btn_open = QPushButton("📂 Open DB")
        self.btn_open.clicked.connect(self.open_db)
        self.lbl_db = QLabel("mio_memory.db")
        self.lbl_db.setStyleSheet("color: #fab387; font-weight: bold;")
        self.btn_new_tab = QPushButton("➕ New Query")
        self.btn_new_tab.clicked.connect(self.add_tab)
        top.addWidget(self.btn_open)
        top.addWidget(self.lbl_db)
        top.addWidget(self.btn_new_tab)
        top.addStretch()
        main.addLayout(top)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Sidebar (3 Tabs!)
        self.side_tabs = QTabWidget()
        self.side_tabs.setStyleSheet("QTabWidget::pane { border: none; } QTabBar::tab { background: #11111b; color: #aaa; }")
        
        self.schema_tree = QTreeWidget()
        self.schema_tree.setHeaderHidden(True)
        self.schema_tree.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none;")
        self.schema_tree.itemDoubleClicked.connect(self.on_schema_click)
        
        self.snippet_list = QTreeWidget()
        self.snippet_list.setHeaderHidden(True)
        self.snippet_list.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none;")
        self.snippet_list.itemDoubleClicked.connect(self.on_code_click)
        self.snippet_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.snippet_list.customContextMenuRequested.connect(self.snippet_menu)
        
        self.history_list = QTreeWidget()
        self.history_list.setHeaderHidden(True)
        self.history_list.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none;")
        self.history_list.itemDoubleClicked.connect(self.on_code_click)
        
        self.side_tabs.addTab(self.schema_tree, "Schema")
        self.side_tabs.addTab(self.snippet_list, "Snippets")
        self.side_tabs.addTab(self.history_list, "History")
        splitter.addWidget(self.side_tabs)
        
        # Main Session Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBarDoubleClicked.connect(self.rename_tab)
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; } QTabBar::tab { background: #11111b; color: #aaa; padding: 5px; } QTabBar::tab:selected { border-bottom: 2px solid #89b4fa; color: white; }")
        splitter.addWidget(self.tabs)
        
        splitter.setSizes([200, 700])
        main.addWidget(splitter)
        self.content_layout.addLayout(main)
        
        self.add_tab()
        self.refresh_snippets() # Refresh sidebar immediately

    def open_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open DB", "", "SQLite (*.db *.sqlite)")
        if path:
            self.db_path = path
            self.lbl_db.setText(os.path.basename(path))
            self.tabs.clear()
            self.add_tab()

    def add_tab(self):
        tab = QuerySession(self.db_path, self)
        idx = self.tabs.addTab(tab, f"Query {self.tabs.count() + 1}")
        self.tabs.setCurrentIndex(idx)
        self.refresh_schema() 

    def close_tab(self, idx):
        if self.tabs.count() > 1: self.tabs.removeTab(idx)

    def rename_tab(self, idx):
        if idx < 0: return
        old = self.tabs.tabText(idx)
        new, ok = QInputDialog.getText(self, "Rename Tab", "Name:", text=old)
        if ok and new: self.tabs.setTabText(idx, new)

    def refresh_schema(self):
        self.schema_worker = DbSession(self.db_path) # Store in self!
        self.schema_worker.schema_loaded.connect(self.on_schema_loaded)
        self.schema_worker.load_schema()

    def on_schema_loaded(self, schema):
        self.schema_tree.clear()
        words = []
        for t, cols in schema.items():
            words.append(t)
            item = QTreeWidgetItem([t])
            item.setData(0, Qt.UserRole, t)
            item.setForeground(0, QBrush(QColor("#fab387")))
            for c, _ in cols:
                words.append(c)
                child = QTreeWidgetItem([c])
                item.addChild(child)
            self.schema_tree.addTopLevelItem(item)
        self.schema_tree.expandAll()
        if self.tabs.currentWidget():
            self.tabs.currentWidget().editor.set_completer(words)

    def on_schema_click(self, item, _):
        val = item.data(0, Qt.UserRole)
        if val and self.tabs.currentWidget():
            self.tabs.currentWidget().editor.insertPlainText(val)

    # --- PERSISTENCE ---
    def load_data(self):
        try:
            with open(os.path.expanduser("~/.mio_snippets.json"), 'r') as f:
                data = json.load(f)
                self.snippets = data.get("snippets", {})
                self.history = data.get("history", [])
        except: pass

    def save_data(self):
        with open(os.path.expanduser("~/.mio_snippets.json"), 'w') as f:
            json.dump({"snippets": self.snippets, "history": self.history}, f)
        self.refresh_sidebar()

    def refresh_snippets(self):
        self.refresh_sidebar()

    def refresh_sidebar(self):
        # Snippets
        self.snippet_list.clear()
        for name, sql in self.snippets.items():
            item = QTreeWidgetItem([name])
            item.setData(0, Qt.UserRole, sql)
            item.setToolTip(0, sql)
            self.snippet_list.addTopLevelItem(item)
        
        # History
        self.history_list.clear()
        for sql in self.history:
            # First line as title
            title = sql.strip().split('\n')[0][:30]
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.UserRole, sql)
            item.setToolTip(0, sql)
            self.history_list.addTopLevelItem(item)

    def on_code_click(self, item, _):
        if self.tabs.currentWidget(): 
            self.tabs.currentWidget().editor.setText(item.data(0, Qt.UserRole))

    def add_to_history(self, sql):
        if sql in self.history: self.history.remove(sql)
        self.history.insert(0, sql)
        self.history = self.history[:50] # Keep 50
        self.save_data()

    def snippet_menu(self, pos):
        menu = QMenu()
        menu.setStyleSheet("QMenu { background: #333; color: white; }")
        act_add = QAction("➕ Save as Snippet", self)
        act_add.triggered.connect(self.add_snippet)
        menu.addAction(act_add)
        item = self.snippet_list.itemAt(pos)
        if item:
            act_del = QAction("❌ Delete", self)
            act_del.triggered.connect(lambda: self.del_snippet(item.text(0)))
            menu.addAction(act_del)
        menu.exec(self.snippet_list.viewport().mapToGlobal(pos))

    def add_snippet(self):
        if not self.tabs.currentWidget(): return
        sql = self.tabs.currentWidget().editor.toPlainText().strip()
        if not sql: return
        name, ok = QInputDialog.getText(self, "Save Snippet", "Name:")
        if ok and name:
            self.snippets[name] = sql
            self.save_data()

    def del_snippet(self, name):
        if name in self.snippets:
            del self.snippets[name]
            self.save_data()
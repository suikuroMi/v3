import psutil
import platform
import os
import datetime
import subprocess
import time
import csv
import math
from collections import deque
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, 
                               QLineEdit, QPushButton, QMenu, QMessageBox, QLabel, 
                               QAbstractItemView, QProgressBar, QSplitter, QWidget, 
                               QTabWidget, QGridLayout, QFrame, QTableWidget, QTableWidgetItem,
                               QHeaderView, QFileDialog, QDialog, QCheckBox, QScrollArea, QTextEdit,
                               QFormLayout)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPointF  
from PySide6.QtGui import QColor, QBrush, QFont, QIcon, QPainter, QPen, QAction, QPolygonF

from .base import BaseApp

# --- 1. UTILS ---
def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = {0 : 'B/s', 1: 'KB/s', 2: 'MB/s', 3: 'GB/s'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.1f} {power_labels.get(n, 'TB/s')}"

def is_critical_process(proc):
    """Heuristic to detect system processes."""
    try:
        name = proc.name().lower()
        if os.name == 'nt':
            critical = [
                'csrss.exe', 'svchost.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 
                'system', 'registry', 'smss.exe', 'winlogon.exe', 'dwm.exe', 'explorer.exe'
            ]
            if name in critical: return True
        else:
            # Linux heuristics: Root processes or key names
            if proc.uids().real == 0 and name in ['systemd', 'init', 'kthreadd', 'Xorg']: 
                return True
    except: pass
    return False

# --- 2. MONITOR WORKER ---
class SystemMonitor(QThread):
    stats_updated = Signal(float, float, dict, tuple) 
    
    def __init__(self):
        super().__init__()
        self._running = True
        self.last_net = psutil.net_io_counters()
        self.last_time = time.time()

    def run(self):
        while self._running:
            try:
                # CPU (Non-blocking)
                cpu = psutil.cpu_percent(interval=None) 
                
                # RAM
                ram = psutil.virtual_memory().percent
                
                # Disk
                try:
                    disk = psutil.disk_usage(os.path.abspath(os.sep))
                    disk_info = {"total": disk.total, "used": disk.used, "percent": disk.percent}
                except:
                    disk_info = {"total": 1, "used": 0, "percent": 0}

                # Network
                curr_net = psutil.net_io_counters()
                curr_time = time.time()
                dt = curr_time - self.last_time
                if dt <= 0: dt = 0.001 
                
                sent_speed = (curr_net.bytes_sent - self.last_net.bytes_sent) / dt
                recv_speed = (curr_net.bytes_recv - self.last_net.bytes_recv) / dt
                
                self.last_net = curr_net
                self.last_time = curr_time

                self.stats_updated.emit(cpu, ram, disk_info, (sent_speed, recv_speed))
                
                # Graceful sleep
                for _ in range(10): 
                    if not self._running: break
                    time.sleep(0.1)
            except: time.sleep(1)

    def stop(self):
        self._running = False
        self.wait()

# --- 3. UI COMPONENTS ---

class HistoryGraph(QWidget):
    """Draws a live line chart for CPU/RAM with alerts."""
    def __init__(self, title, color):
        super().__init__()
        self.title = title
        self.base_color = QColor(color)
        self.current_color = self.base_color
        self.alert_color = QColor("#f38ba8") # Red
        self.history = deque([0]*60, maxlen=60) # 60 seconds history
        self.current_val = 0
        self.setMinimumSize(150, 80)
        self.setStyleSheet("background: #181825; border-radius: 5px;")

    def add_value(self, val, alert=False):
        self.current_val = val
        self.history.append(val)
        self.current_color = self.alert_color if alert else self.base_color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        
        # BG
        painter.fillRect(0, 0, w, h, QColor("#181825"))
        
        # Grid lines
        painter.setPen(QPen(QColor("#333"), 1, Qt.DotLine))
        painter.drawLine(0, int(h/2), w, int(h/2))
        painter.drawLine(0, int(h/4), w, int(h/4))
        painter.drawLine(0, int(h*3/4), w, int(h*3/4))

        # Graph Path
        if len(self.history) > 1:
            path = QPolygonF()
            step_x = w / (len(self.history) - 1)
            
            for i, val in enumerate(self.history):
                x = i * step_x
                # Clamp to 0-100 visually
                clamped_val = max(0, min(100, val))
                y = h - (clamped_val / 100 * h) 
                path.append(QPointF(x, y))
            
            # Gradient Fill
            fill_path = QPolygonF(path)
            fill_path.append(QPointF(w, h))
            fill_path.append(QPointF(0, h))
            
            grad = self.current_color
            grad.setAlpha(50)
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(fill_path)
            
            # Line
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(self.current_color, 2))
            painter.drawPolyline(path)

        # Title Text
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(10, 20, f"{self.title}: {int(self.current_val)}%")

class AffinityDialog(QDialog):
    """Allows pinning processes to specific CPU cores with load context."""
    def __init__(self, pid, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.proc = psutil.Process(pid)
        self.setWindowTitle(f"CPU Affinity - {self.proc.name()}")
        self.resize(350, 450)
        self.setStyleSheet("background: #1e1e2e; color: white;")
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Select Allowed Cores for PID {pid}:"))
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.grid = QGridLayout(content)
        
        try:
            current_affinity = self.proc.cpu_affinity()
            # Get load per core for context
            per_cpu_load = psutil.cpu_percent(percpu=True)
        except: 
            current_affinity = []
            per_cpu_load = []
        
        self.checks = []
        count = psutil.cpu_count()
        for i in range(count):
            load = per_cpu_load[i] if i < len(per_cpu_load) else 0
            cb = QCheckBox(f"Core {i} ({load}%)")
            cb.setChecked(i in current_affinity)
            
            # Color code high load cores as warning
            if load > 80: cb.setStyleSheet("color: #f38ba8;") # Red tint
            elif load > 50: cb.setStyleSheet("color: #fab387;") # Orange tint
            
            self.checks.append(cb)
            self.grid.addWidget(cb, i // 2, i % 2)
            
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        btns = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(self.select_all)
        btn_ok = QPushButton("Apply")
        btn_ok.clicked.connect(self.apply)
        btn_ok.setStyleSheet("background: #a6e3a1; color: black; font-weight: bold;")
        
        btns.addWidget(btn_all)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def select_all(self):
        for c in self.checks: c.setChecked(True)

    def apply(self):
        cores = [i for i, cb in enumerate(self.checks) if cb.isChecked()]
        if not cores:
            QMessageBox.warning(self, "Error", "Select at least one core.")
            return
        try:
            self.proc.cpu_affinity(cores)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

class ProcessDetailsDialog(QDialog):
    """Detailed tabbed inspector for a process."""
    def __init__(self, pid, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Process Details - {pid}")
        self.resize(500, 600)
        self.setStyleSheet("background: #1e1e2e; color: #cdd6f4;")
        
        try:
            p = psutil.Process(pid)
            layout = QVBoxLayout(self)
            tabs = QTabWidget()
            tabs.setStyleSheet("QTabWidget::pane{border:none;} QTabBar::tab{background:#11111b;color:#aaa;padding:5px;} QTabBar::tab:selected{color:white;border-bottom:2px solid #89b4fa;}")
            
            # Tab 1: General
            gen_w = QWidget()
            form = QFormLayout(gen_w)
            form.addRow("Name:", QLabel(p.name()))
            form.addRow("PID:", QLabel(str(pid)))
            form.addRow("Status:", QLabel(p.status()))
            form.addRow("User:", QLabel(p.username()))
            try: form.addRow("Created:", QLabel(datetime.datetime.fromtimestamp(p.create_time()).strftime("%Y-%m-%d %H:%M:%S")))
            except: pass
            
            cmd = " ".join(p.cmdline())
            cmd_box = QTextEdit(cmd); cmd_box.setReadOnly(True); cmd_box.setFixedHeight(60)
            form.addRow("Command:", cmd_box)
            
            try: 
                cwd = p.cwd()
                cwd_box = QLineEdit(cwd); cwd_box.setReadOnly(True)
                form.addRow("CWD:", cwd_box)
            except: pass
            
            tabs.addTab(gen_w, "General")
            
            # Tab 2: Resources
            res_w = QWidget()
            res_form = QFormLayout(res_w)
            mem = p.memory_info()
            res_form.addRow("RSS Memory:", QLabel(f"{mem.rss / 1024 / 1024:.1f} MB"))
            res_form.addRow("VMS Memory:", QLabel(f"{mem.vms / 1024 / 1024:.1f} MB"))
            res_form.addRow("Threads:", QLabel(str(p.num_threads())))
            try: res_form.addRow("Nice (Priority):", QLabel(str(p.nice())))
            except: pass
            
            tabs.addTab(res_w, "Resources")
            
            # Tab 3: Environment
            env_w = QWidget()
            env_layout = QVBoxLayout(env_w)
            try:
                env_text = QTextEdit()
                env_text.setReadOnly(True)
                env_text.setFont(QFont("Consolas", 9))
                for k, v in p.environ().items():
                    env_text.append(f"{k}={v}")
                env_layout.addWidget(env_text)
            except:
                env_layout.addWidget(QLabel("Access Denied"))
            tabs.addTab(env_w, "Environment")
            
            layout.addWidget(tabs)
            
            btn_close = QPushButton("Close")
            btn_close.clicked.connect(self.accept)
            btn_close.setStyleSheet("background: #333; color: white;")
            layout.addWidget(btn_close)
            
        except Exception as e:
            l = QVBoxLayout(self)
            l.addWidget(QLabel(f"Process no longer exists or access denied.\n{e}"))

class ProcessTable(QTableWidget):
    kill_requested = Signal(list, bool) 
    priority_requested = Signal(int, int)
    details_requested = Signal(int)

    def __init__(self):
        super().__init__()
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["PID", "Name", "CPU %", "RAM (MB)"])
        self.setStyleSheet("QTableWidget { background: #1e1e2e; color: #cdd6f4; border: none; } QHeaderView::section { background: #11111b; color: #aaa; }")
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)
        self.itemDoubleClicked.connect(self.on_double_click)
        self.setSortingEnabled(True)
        self.filter_text = ""
        self.is_paused = False

    def set_filter(self, text):
        self.filter_text = text.lower()
        self.refresh()

    def refresh(self):
        if self.is_paused: return
        self.setSortingEnabled(False)
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                if self.filter_text and self.filter_text not in p.info['name'].lower(): continue
                procs.append(p.info)
            except: pass
        procs.sort(key=lambda p: p['memory_info'].rss, reverse=True)
        self.setRowCount(len(procs[:100]))
        for r, p in enumerate(procs[:100]):
            pid_item = QTableWidgetItem(str(p['pid'])); pid_item.setData(Qt.UserRole, p['pid'])
            name_item = QTableWidgetItem(p['name']); name_item.setData(Qt.UserRole, p['name'])
            cpu_item = QTableWidgetItem(f"{p['cpu_percent']:.1f}"); cpu_item.setData(Qt.UserRole, p['cpu_percent'])
            mem_mb = p['memory_info'].rss / 1024 / 1024
            mem_item = QTableWidgetItem(f"{mem_mb:.1f}"); mem_item.setData(Qt.UserRole, mem_mb)
            self.setItem(r, 0, pid_item); self.setItem(r, 1, name_item); self.setItem(r, 2, cpu_item); self.setItem(r, 3, mem_item)
        self.setSortingEnabled(True)

    def show_menu(self, pos):
        items = self.selectedItems()
        if not items: return
        pids = list(set([int(self.item(i.row(), 0).text()) for i in items]))
        count = len(pids)
        menu = QMenu(); menu.setStyleSheet("QMenu { background: #333; color: white; }")
        
        menu.addAction(f"🛑 Terminate {count}", lambda: self.kill_requested.emit(pids, False))
        menu.addAction(f"☠️ Force Kill {count}", lambda: self.kill_requested.emit(pids, True))
        menu.addSeparator()
        
        if count == 1:
            pid = pids[0]
            menu.addAction("🔍 Details...", lambda: self.details_requested.emit(pid))
            p_menu = menu.addMenu("⚖️ Set Priority")
            if os.name == 'nt':
                p_menu.addAction("High", lambda: self.priority_requested.emit(pid, psutil.HIGH_PRIORITY_CLASS))
                p_menu.addAction("Normal", lambda: self.priority_requested.emit(pid, psutil.NORMAL_PRIORITY_CLASS))
                p_menu.addAction("Idle", lambda: self.priority_requested.emit(pid, psutil.IDLE_PRIORITY_CLASS))
            else:
                p_menu.addAction("High", lambda: self.priority_requested.emit(pid, -10))
                p_menu.addAction("Normal", lambda: self.priority_requested.emit(pid, 0))
            menu.addAction("🎯 Set Affinity...", lambda: AffinityDialog(pid, self).exec())

        menu.exec(self.viewport().mapToGlobal(pos))

    def on_double_click(self, item):
        pid = int(self.item(item.row(), 0).text())
        self.details_requested.emit(pid)

# --- 4. MAIN APP ---
class SystemApp(BaseApp):
    def __init__(self, brain=None):
        super().__init__("System Omniscient", "cpu.png", "#4CAF50")
        self.brain = brain
        self.monitor = SystemMonitor()
        self.cpu_alert_counter = 0
        
        main = QVBoxLayout()
        
        # 1. Graphs Panel
        graphs_panel = QFrame()
        graphs_panel.setStyleSheet("background: #181825; border-radius: 10px;")
        gp_layout = QHBoxLayout(graphs_panel)
        
        self.cpu_graph = HistoryGraph("CPU History", "#f38ba8")
        self.ram_graph = HistoryGraph("RAM History", "#89b4fa")
        self.lbl_net = QLabel("Net: 0 KB/s")
        self.lbl_net.setStyleSheet("font-size: 16px; font-weight: bold; color: #fab387; padding: 20px;")
        
        gp_layout.addWidget(self.cpu_graph)
        gp_layout.addWidget(self.ram_graph)
        gp_layout.addWidget(self.lbl_net)
        main.addWidget(graphs_panel)
        
        # 2. Tabs
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_change)
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; } QTabBar::tab { background: #11111b; color: #aaa; padding: 8px; } QTabBar::tab:selected { color: white; border-bottom: 2px solid #4CAF50; }")
        
        # Tab 1: Processes
        p_widget = QWidget(); pl = QVBoxLayout(p_widget)
        ctrl_row = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("🔍 Filter..."); self.search.textChanged.connect(lambda t: self.proc_table.set_filter(t)); self.search.setStyleSheet("background: #222; color: #fff; border: 1px solid #444; border-radius: 5px;")
        btn_exp = QPushButton("📤 CSV"); btn_exp.setFixedSize(60, 30); btn_exp.clicked.connect(self.export_csv)
        ctrl_row.addWidget(self.search); ctrl_row.addWidget(btn_exp)
        
        self.proc_table = ProcessTable()
        self.proc_table.kill_requested.connect(self.kill_processes)
        self.proc_table.priority_requested.connect(self.set_priority)
        self.proc_table.details_requested.connect(lambda pid: ProcessDetailsDialog(pid, self).exec())
        
        pl.addLayout(ctrl_row); pl.addWidget(self.proc_table)
        self.tabs.addTab(p_widget, "⚡ Processes")
        
        # Tab 2: Tools
        t_widget = QWidget(); tl = QGridLayout(t_widget); tl.setSpacing(15)
        actions = [("📸 Screenshot", self.take_screenshot, "#fab387"), ("🧹 Clean Temp", self.clean_temp, "#f38ba8"),
                   ("🌐 Speed Test", self.net_test, "#89b4fa"), ("📝 Notepad", lambda: self.launch("notepad" if os.name=='nt' else "gedit"), "#a6adc8"),
                   ("💻 Terminal", self.launch_terminal, "#a6adc8"), ("📁 Explorer", self.launch_explorer, "#a6adc8")]
        for i, (text, func, col) in enumerate(actions):
            btn = QPushButton(text); btn.setFixedSize(120, 80); btn.clicked.connect(func)
            btn.setStyleSheet(f"QPushButton {{ background: {col}; color: #1e1e2e; font-weight: bold; border-radius: 10px; }}")
            tl.addWidget(btn, i // 3, i % 3)
        tl.setRowStretch(2, 1); self.tabs.addTab(t_widget, "🛠️ Tools")
        
        # Tab 3: Specs
        s_widget = QWidget(); sl = QVBoxLayout(s_widget)
        info = f"""<h2>System Info</h2><p><b>OS:</b> {platform.system()} {platform.release()}</p><p><b>CPU:</b> {platform.processor()}</p><p><b>Cores:</b> {psutil.cpu_count(logical=True)}</p><p><b>Boot:</b> {datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M")}</p>"""
        lbl = QLabel(info); lbl.setStyleSheet("font-size: 14px; color: #cdd6f4; padding: 20px;"); lbl.setTextFormat(Qt.RichText); lbl.setAlignment(Qt.AlignTop); sl.addWidget(lbl)
        self.tabs.addTab(s_widget, "ℹ️ Specs")
        
        main.addWidget(self.tabs)
        self.content_layout.addLayout(main)
        self.monitor.stats_updated.connect(self.update_stats)
        self.monitor.start()
        
        self.proc_timer = QTimer(self); self.proc_timer.timeout.connect(lambda: self.proc_table.refresh()); self.proc_timer.start(3000); self.proc_table.refresh()

    def update_stats(self, cpu, ram, disk, net):
        # Alert Logic: Sustained high CPU triggers red graph
        if cpu > 90: self.cpu_alert_counter += 1
        else: self.cpu_alert_counter = 0
        is_alert = self.cpu_alert_counter > 3 # >3 seconds sustained load
        
        self.cpu_graph.add_value(cpu, alert=is_alert)
        self.ram_graph.add_value(ram)
        s, r = net
        self.lbl_net.setText(f"↑ {format_bytes(s)}\n↓ {format_bytes(r)}")

    def kill_processes(self, pids, force):
        # Critical Process Check
        critical_pids = []
        for pid in pids:
            try:
                p = psutil.Process(pid)
                if is_critical_process(p): critical_pids.append(p.name())
            except: pass
            
        if critical_pids:
            msg = f"WARNING: You are trying to kill critical system processes:\n{', '.join(critical_pids)}\n\nThis may crash your system. Proceed?"
            if QMessageBox.critical(self, "System Warning", msg, QMessageBox.Yes|QMessageBox.No) == QMessageBox.No:
                return

        verb = "Force Kill" if force else "Terminate"
        if QMessageBox.question(self, verb, f"{verb} {len(pids)} processes?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            for pid in pids:
                try:
                    p = psutil.Process(pid)
                    if force: p.kill() 
                    else: p.terminate()
                except: pass
            self.proc_table.refresh()

    def set_priority(self, pid, prio):
        try: psutil.Process(pid).nice(prio)
        except Exception as e: QMessageBox.warning(self, "Error", str(e))

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "procs.csv", "CSV (*.csv)")
        if path:
            try:
                with open(path, 'w', newline='') as f:
                    w = csv.writer(f)
                    w.writerow(["PID", "Name", "CPU", "RAM"])
                    for r in range(self.proc_table.rowCount()):
                        w.writerow([self.proc_table.item(r,c).data(Qt.UserRole) for c in range(4)])
                QMessageBox.information(self, "Success", "Exported.")
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def on_tab_change(self, idx): self.proc_table.is_paused = (idx != 0)
    
    # Tools
    def launch(self, c): 
        try: subprocess.Popen(c, shell=True)
        except Exception as e: QMessageBox.warning(self, "Error", str(e))
    def launch_terminal(self): self.launch("start cmd" if os.name=='nt' else "x-terminal-emulator")
    def launch_explorer(self): self.launch("explorer" if os.name=='nt' else "xdg-open .")
    def take_screenshot(self): self.command_signal.emit("[SCREENSHOT]")
    def clean_temp(self): self.command_signal.emit("Clean temp files")
    def net_test(self): self.command_signal.emit("Check internet speed")
    def closeEvent(self, e): self.monitor.stop(); super().closeEvent(e)
import os
import logging
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QLabel, QMenu)
from PySide6.QtCore import Qt, QTimer, QSize, QSettings
from PySide6.QtGui import QPixmap, QKeySequence, QShortcut

from src.agent.llm_engine import BrainEngine
from src.core.paths import get_asset_path

# Import Modularized Components
from src.ui.manager import AppManager
from src.ui.utils.performance import UIPerformance
from src.ui.utils.thread import ThinkingThread
from src.ui.views.workstation import WorkstationWindow
from src.ui.views.phone import ModernMioPhone

logger = logging.getLogger("MioUI")

class MascotWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.brain = BrainEngine()
        self.app_manager = AppManager(self.brain, self)
        self.settings = QSettings("Ookami", "Mio_V6")
        self.perf = UIPerformance()
        
        # Command Queue Safety
        self.command_queue = []
        self.MAX_QUEUE_SIZE = 5 
        
        self.is_thinking = False
        self.mode = "COMPANION"
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.phone = ModernMioPhone(self.app_manager)
        self.workstation = WorkstationWindow(self.app_manager)
        self.workstation.hide()
        
        self.avatar = QLabel()
        self.avatar.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        
        self.layout.addWidget(self.phone)
        self.layout.addWidget(self.avatar)
        
        self.set_pose("idle")
        self.shortcut_toggle = QShortcut(QKeySequence("F12"), self)
        self.shortcut_toggle.activated.connect(self.toggle_mode)

        # Robust State Loading
        QTimer.singleShot(100, lambda: self.load_state(retry_count=0))

    # --- STATE PERSISTENCE ---
    def load_state(self, retry_count=0):
        if (not self.phone or not self.workstation) and retry_count < 5:
            QTimer.singleShot(100, lambda: self.load_state(retry_count + 1))
            return

        try:
            self.perf.start("load_state")
            geo = self.settings.value("geometry")
            if geo: self.restoreGeometry(geo)

            saved_mode = self.settings.value("mode", "COMPANION")
            if saved_mode == "OPERATOR" and self.mode != "OPERATOR":
                self.toggle_mode(force_operator=True)

            last_phone = self.settings.value("last_phone_app")
            if last_phone and last_phone != "Home":
                self.phone.switch_app_by_name(last_phone)
            
            last_work = self.settings.value("last_work_app")
            if last_work:
                self.workstation.switch_view(last_work)
            
            self.perf.end("load_state")
                
        except Exception as e:
            logger.error(f"State load error: {e}")

    def closeEvent(self, event):
        self.settings.setValue("mode", self.mode)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("last_phone_app", self.phone.get_active_app_name())
        self.settings.setValue("last_work_app", self.workstation.current_app_name)
        super().closeEvent(event)

    # --- MODE SWITCHING ---
    def toggle_mode(self, force_operator=False):
        self.perf.start("toggle_mode")
        try:
            target_mode = "OPERATOR" if force_operator else ("OPERATOR" if self.mode == "COMPANION" else "COMPANION")
            if force_operator and self.mode == "OPERATOR": return

            self.phone.hide()
            self.workstation.hide()
            self.avatar.hide()
            
            if self.phone.parent() == self: self.layout.removeWidget(self.phone)
            if self.workstation.parent() == self: self.layout.removeWidget(self.workstation)
            self.layout.removeWidget(self.avatar)
            
            if target_mode == "OPERATOR":
                self.setFixedSize(1400, 800)
                self.layout.addWidget(self.workstation)
                self.layout.addWidget(self.avatar)
                self.workstation.show()
                self.avatar.show()
                self.workstation.switch_view("Chat")
            else: 
                self.setFixedSize(700, 800)
                self.layout.addWidget(self.phone)
                self.layout.addWidget(self.avatar)
                self.phone.show()
                self.avatar.show()
                self.phone.switch_app_by_name("Chat")
            
            self.mode = target_mode
            self.perf.end("toggle_mode")
            
        except Exception as e:
            logger.critical(f"Mode toggle failed: {e}")
            self.mode = "COMPANION"
            self.setFixedSize(700, 800)
            if self.phone.parent() != self: self.layout.addWidget(self.phone)
            if self.avatar.parent() != self: self.layout.addWidget(self.avatar)
            self.phone.show()
            self.avatar.show()

    # --- BRAIN PROCESSING ---
    def process_command(self, text):
        if text == "[TOGGLE_UI]":
            self.toggle_mode()
            return
        
        if len(self.command_queue) >= self.MAX_QUEUE_SIZE:
            logger.warning("Queue full, dropping oldest command")
            self.command_queue.pop(0)

        self.command_queue.append(text)
        self.process_next_command()

    def process_next_command(self):
        if self.is_thinking or not self.command_queue:
            return
            
        text = self.command_queue.pop(0)
        self.is_thinking = True
        
        if self.mode == "COMPANION":
            self.phone.switch_app_by_name("Chat")
            self.phone.overlay.show_msg()
        else:
            self.workstation.switch_view("Chat")
            self.workstation.overlay.show_msg()
            
        chat_app = self.app_manager.get_app("Chat")
        if chat_app: chat_app.append_chat("You", text)
        
        if self.parent(): self.set_pose("think")

        self.worker = ThinkingThread(self.brain, text)
        self.worker.response_ready.connect(self.on_brain_text)
        self.worker.log_signal.connect(self.on_brain_log)
        self.worker.finished.connect(self.on_thinking_finished)
        self.worker.start()

    def on_brain_text(self, text):
        chat_app = self.app_manager.get_app("Chat")
        if chat_app: chat_app.append_chat("Mio", text)

    def on_brain_log(self, log_text):
        self.workstation.log(log_text)

    def on_thinking_finished(self):
        self.is_thinking = False
        self.set_pose("idle")
        
        self.phone.overlay.hide()
        self.workstation.overlay.hide()
        
        self.worker.deleteLater()
        QTimer.singleShot(100, self.process_next_command)

    def set_pose(self, pose_name):
        path = get_asset_path(f"mio_{pose_name}.png")
        if path and os.path.exists(path):
            self.avatar.setPixmap(QPixmap(path).scaled(250, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.avatar.setText("🐺")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if hasattr(self, 'drag_pos') and self.drag_pos:
            self.move(e.globalPosition().toPoint() - self.drag_pos)
    def mouseReleaseEvent(self, e):
        self.drag_pos = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #222; color: white; }")
        menu.addAction("🖥️ Toggle Operator Mode (F12)", self.toggle_mode)
        menu.addAction("❌ Shutdown", QApplication.quit)
        menu.exec(event.globalPos())
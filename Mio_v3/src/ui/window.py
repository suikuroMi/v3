import os
import sys
import logging
import subprocess
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QLabel, QMenu, QGraphicsOpacityEffect)
from PySide6.QtCore import Qt, QTimer, QSize, QSettings, QPoint, QRect, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QKeySequence, QShortcut, QCursor

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
        self.mode = None 
        self.previous_mode = "COMPANION" 
        
        # Configurable Input
        self.DRAG_THRESHOLD = int(self.settings.value("drag_threshold", 5))
        self.drag_offset = None
        self.click_start_pos = None
        self.is_dragging = False
        self.valid_interaction = False 
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # UX Hints
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Left-Click Mio: Toggle UI | Drag Mio: Move")
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Initialize views 
        self.phone = ModernMioPhone(self.app_manager)
        self.workstation = WorkstationWindow(self.app_manager)
        
        # Init Avatar
        self.avatar = QLabel()
        self.avatar.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        # Lock size to ensure consistent geometry calculations
        self.avatar.setFixedSize(140, 180) 
        
        # Animation Effect
        self.opacity_effect = QGraphicsOpacityEffect(self.avatar)
        self.opacity_effect.setOpacity(1.0)
        self.avatar.setGraphicsEffect(self.opacity_effect)
        
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        self.set_pose("idle") 
        
        # Start in Companion Mode
        self.setup_companion_mode()
        
        # Shortcuts
        self._init_shortcuts()

        # Robust State Loading
        QTimer.singleShot(100, lambda: self.load_state(retry_count=0))

    def _init_shortcuts(self):
        QShortcut(QKeySequence("F12"), self).activated.connect(self.toggle_mode)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(self.setup_companion_mode)
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(self.setup_operator_mode)
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(self.setup_avatar_mode)

    def flash_avatar(self):
        self.anim.stop()
        self.anim.setStartValue(0.3)
        self.anim.setEndValue(1.0)
        self.anim.start()

    # --- PIN-POINT ANCHORING SYSTEM (V17) ---
    def _capture_pin(self):
        """
        Records the GLOBAL screen position of the Avatar's Bottom-Right pixel.
        This effectively 'pins' Mio to that pixel on your monitor.
        """
        if self.avatar.isVisible():
            # Get bottom-right corner of the AVATAR WIDGET specifically
            local_pin = self.avatar.rect().bottomRight()
            return self.avatar.mapToGlobal(local_pin)
        return None

    def _restore_pin(self, target_pin):
        """
        Moves the window so the Avatar's Bottom-Right pixel lands back on target_pin.
        """
        if not target_pin: return
        
        # 1. Force layout update so we have correct new local coordinates
        QApplication.processEvents()
        
        # 2. Where is the pin now? (After resize)
        local_pin = self.avatar.rect().bottomRight()
        current_pin = self.avatar.mapToGlobal(local_pin)
        
        # 3. Calculate the shift needed
        delta = target_pin - current_pin
        
        # 4. Move the window by that shift
        if delta.manhattanLength() > 0:
            self.move(self.pos() + delta)

    def setup_companion_mode(self):
        if self.mode == "COMPANION": return
        
        pin = self._capture_pin() # Capture
        self._clear_layout()
        
        # Phone (380) + Avatar (140) + Margins ~ 600
        self.setFixedSize(600, 800) 
        
        self.workstation.hide()
        self.phone.show()
        self.avatar.show()
        
        self.layout.addWidget(self.phone)
        self.layout.addWidget(self.avatar)
        
        # Force alignment to ensure she sits at the bottom
        self.layout.setAlignment(self.avatar, Qt.AlignBottom | Qt.AlignRight)
        
        self.mode = "COMPANION"
        self.phone.go_home()
        self.flash_avatar()
        self._restore_pin(pin) # Restore

    def setup_operator_mode(self):
        if self.mode == "OPERATOR": return
        
        pin = self._capture_pin()
        self._clear_layout()
        self.setFixedSize(1400, 800)
        
        self.phone.hide()
        self.workstation.show()
        self.avatar.show()
        
        self.layout.addWidget(self.workstation)
        self.layout.addWidget(self.avatar)
        
        self.layout.setAlignment(self.avatar, Qt.AlignBottom | Qt.AlignRight)
        
        self.mode = "OPERATOR"
        self.workstation.switch_view("Chat")
        self.flash_avatar()
        self._restore_pin(pin)

    def setup_avatar_mode(self):
        if self.mode == "AVATAR_ONLY": return
        
        if self.mode != "AVATAR_ONLY":
            self.previous_mode = self.mode

        pin = self._capture_pin()
        self._clear_layout()
        # Just enough for Avatar (140x180)
        self.setFixedSize(140, 180) 
        
        self.phone.hide()
        self.workstation.hide()
        self.avatar.show()
        
        self.layout.addWidget(self.avatar)
        # Ensure she fills this small window or aligns correctly
        self.layout.setAlignment(self.avatar, Qt.AlignBottom | Qt.AlignRight)
        
        self.mode = "AVATAR_ONLY"
        self.flash_avatar()
        self._restore_pin(pin)

    def _clear_layout(self):
        self.layout.removeWidget(self.phone)
        self.phone.setParent(None) 
        self.layout.removeWidget(self.workstation)
        self.workstation.setParent(None) 
        self.layout.removeWidget(self.avatar)
        self.avatar.setParent(None) 

        self.phone.setParent(self)
        self.workstation.setParent(self)
        self.avatar.setParent(self)

    # --- STATE PERSISTENCE ---
    def load_state(self, retry_count=0):
        if (not self.phone or not self.workstation) and retry_count < 5:
            QTimer.singleShot(100, lambda: self.load_state(retry_count + 1))
            return

        try:
            self.perf.start("load_state")
            geo = self.settings.value("geometry")
            if geo: self.restoreGeometry(geo)

            if self.mode != "COMPANION":
                self.mode = None 
                self.setup_companion_mode()

            last_phone = self.settings.value("last_phone_app")
            if last_phone and last_phone != "Home":
                self.phone.switch_app_by_name(last_phone)
            
            self.perf.end("load_state")
                
        except Exception as e:
            logger.error(f"State load error: {e}")
            self.mode = None
            self.setup_companion_mode()

    def closeEvent(self, event):
        self.settings.setValue("mode", self.mode)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("last_phone_app", self.phone.get_active_app_name())
        self.settings.setValue("last_work_app", self.workstation.current_app_name)
        self.settings.setValue("drag_threshold", self.DRAG_THRESHOLD)
        super().closeEvent(event)

    # --- MODE SWITCHING ---
    def toggle_mode(self, force_operator=False):
        try:
            if force_operator:
                if self.mode != "OPERATOR": self.setup_operator_mode()
                return

            if self.mode == "COMPANION":
                self.setup_operator_mode()
            else:
                self.setup_companion_mode()
        except Exception as e:
            logger.critical(f"Mode toggle failed: {e}")
            self.setup_companion_mode()

    def handle_click(self):
        if self.mode == "AVATAR_ONLY":
            if self.previous_mode == "OPERATOR":
                self.setup_operator_mode()
            else:
                self.setup_companion_mode()
        else:
            self.setup_avatar_mode()

    def restart_app(self):
        """Reliable restart."""
        logger.info("Restarting application...")
        subprocess.Popen([sys.executable] + sys.argv)
        QApplication.exit(0)

    # --- INPUT HANDLING ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            child = self.childAt(e.position().toPoint())
            
            # STRICT CHECK: Only allow interaction if we clicked the avatar
            if child == self.avatar:
                self.valid_interaction = True
                self.click_start_pos = e.globalPosition().toPoint()
                self.drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.is_dragging = False
                self.setCursor(Qt.ClosedHandCursor) 
                e.accept()
            else:
                self.valid_interaction = False
                e.ignore() 

    def mouseMoveEvent(self, e):
        if self.valid_interaction and self.drag_offset:
            current_pos = e.globalPosition().toPoint()
            
            if not self.is_dragging:
                if (current_pos - self.click_start_pos).manhattanLength() > self.DRAG_THRESHOLD:
                    self.is_dragging = True
            
            if self.is_dragging:
                self.move(current_pos - self.drag_offset)
                e.accept()
        else:
            e.ignore()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.valid_interaction:
            if not self.is_dragging:
                self.handle_click()
            
            self.drag_offset = None
            self.click_start_pos = None
            self.is_dragging = False
            self.valid_interaction = False
            self.setCursor(Qt.PointingHandCursor) 
            e.accept()
        else:
            e.ignore()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #222; color: white; border: 1px solid #444; }")
        
        if self.mode == "AVATAR_ONLY":
            menu.addAction("📱 Show UI", self.handle_click)
        else:
            menu.addAction("🫣 Hide UI (Avatar Only)", self.setup_avatar_mode)
            
        menu.addSeparator()
        
        if self.mode == "OPERATOR":
            menu.addAction("📱 Switch to Companion Mode", self.setup_companion_mode)
        else:
            menu.addAction("🖥️ Switch to Operator Mode", self.setup_operator_mode)

        menu.addSeparator()
        
        restart_action = menu.addAction("🔄 Restart System")
        restart_action.triggered.connect(self.restart_app)
        
        menu.addAction("❌ Shutdown", QApplication.quit)
        menu.exec(event.globalPos())

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
        
        if self.mode == "AVATAR_ONLY":
            self.handle_click() 

        if self.mode == "COMPANION":
            self.phone.switch_app_by_name("Chat")
            self.phone.overlay.show_msg()
        else:
            self.workstation.switch_view("Chat")
            self.workstation.overlay.show_msg()
            
        chat_app = self.app_manager.get_app("Chat")
        if chat_app: chat_app.add_msg("You", text)
        
        self.set_pose("think")

        self.worker = ThinkingThread(self.brain, text)
        self.worker.response_ready.connect(self.on_brain_text)
        self.worker.log_signal.connect(self.on_brain_log)
        self.worker.finished.connect(self.on_thinking_finished)
        self.worker.start()

    def on_brain_text(self, text):
        chat_app = self.app_manager.get_app("Chat")
        if chat_app: 
            chat_app.on_brain_update(text)

    def on_brain_log(self, log_text):
        chat_app = self.app_manager.get_app("Chat")
        if chat_app:
            chat_app.on_brain_update(f"[LOG] {log_text}")
        self.workstation.log(log_text)

    def on_thinking_finished(self):
        self.is_thinking = False
        self.set_pose("idle")
        
        self.phone.overlay.hide()
        self.workstation.overlay.hide()
        
        chat_app = self.app_manager.get_app("Chat")
        if chat_app: chat_app.on_brain_finished("Done")

        self.worker.deleteLater()
        QTimer.singleShot(100, self.process_next_command)

    def set_pose(self, pose_name):
        path = get_asset_path(f"mio_{pose_name}.png")
        if path and os.path.exists(path):
            self.avatar.setPixmap(QPixmap(path).scaled(140, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.avatar.setText("🐺")
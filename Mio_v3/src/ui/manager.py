import logging
from PySide6.QtWidgets import QWidget

# Import Apps
from src.ui.apps.chat import ChatApp
from src.ui.apps.files import FilesApp
from src.ui.apps.system import SystemApp
from src.ui.apps.dev import DevApp
from src.ui.apps.git import GitApp
from src.ui.apps.database import DbApp
from src.ui.apps.audio_recorder import VoiceApp
from src.ui.apps.stream_listener import StreamApp
from src.ui.apps.transcriber import TranscriberApp
from src.ui.apps.web import WebApp
from src.ui.apps.clock import ClockApp
from src.ui.apps.settings import SettingsApp

logger = logging.getLogger("MioUI")

class AppManager:
    def __init__(self, brain, mascot_ref):
        self.brain = brain
        self.mascot = mascot_ref
        self.apps = {}
        self.app_classes = {
            "Chat": ChatApp, "Files": FilesApp, "System": SystemApp,
            "Dev": DevApp, "Git": GitApp, "Database": DbApp,
            "Voice": VoiceApp, "Stream": StreamApp, "Transcriber": TranscriberApp,
            "Web": WebApp, "Clock": ClockApp, "Settings": SettingsApp
        }
        self.init_all_apps()

    def init_all_apps(self):
        for name, Cls in self.app_classes.items():
            try:
                try:
                    instance = Cls(self.brain)
                except TypeError:
                    instance = Cls()
                
                if not hasattr(instance, 'brain'):
                    instance.brain = self.brain
                
                # Signal Connections
                if hasattr(instance, 'command_signal'):
                    instance.command_signal.connect(self.mascot.process_command)
                if hasattr(instance, 'request_pose'):
                    instance.request_pose.connect(self.mascot.set_pose)

                self.apps[name] = instance
                instance._app_name = name 
                
            except Exception as e:
                logger.error(f"Failed to init app {name}: {e}")

    def get_app(self, name):
        return self.apps.get(name)

    def dock_to_layout(self, app_name, layout):
        app = self.get_app(app_name)
        if not app: return False
        
        # Safety Check: Remove from old parent
        if app.parent():
            old_parent = app.parent()
            if isinstance(old_parent, QWidget) and old_parent.layout():
                old_parent.layout().removeWidget(app)
            app.setParent(None)
        
        layout.addWidget(app)
        app.show()
        return True

    def dock_to_stack(self, app_name, stack_widget):
        app = self.get_app(app_name)
        if not app: return False
        
        if app.parent():
            old_parent = app.parent()
            if isinstance(old_parent, QWidget) and old_parent.layout():
                old_parent.layout().removeWidget(app)
            app.setParent(None)

        if stack_widget.indexOf(app) == -1:
            stack_widget.addWidget(app)
            
        stack_widget.setCurrentWidget(app)
        return True
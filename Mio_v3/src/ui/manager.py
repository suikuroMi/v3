import logging
from PySide6.QtWidgets import QWidget

# --- Safe Imports for ALL Apps ---
# We try to import each app. If a file is missing, we log it but don't crash.
try: from src.ui.apps.chat import ChatApp
except ImportError: ChatApp = None

try: from src.ui.apps.files import FilesApp
except ImportError: FilesApp = None

try: from src.ui.apps.system import SystemApp
except ImportError: SystemApp = None

try: from src.ui.apps.dev import DevApp
except ImportError: DevApp = None

try: from src.ui.apps.git import GitApp
except ImportError: GitApp = None

try: from src.ui.apps.database import DbApp
except ImportError: DbApp = None

try: from src.ui.apps.audio_recorder import VoiceApp
except ImportError: VoiceApp = None

try: from src.ui.apps.stream_listener import StreamApp
except ImportError: StreamApp = None

try: from src.ui.apps.transcriber import TranscriberApp
except ImportError: TranscriberApp = None

try: from src.ui.apps.web import WebApp
except ImportError: WebApp = None

try: from src.ui.apps.clock import ClockApp
except ImportError: ClockApp = None

try: from src.ui.apps.settings import SettingsApp
except ImportError: SettingsApp = None

try: from src.ui.apps.downloader import DownloaderApp
except ImportError: DownloaderApp = None

from src.ui.apps.base import BaseApp

logger = logging.getLogger("MioUI")

class AppManager:
    def __init__(self, brain, mascot_ref):
        self.brain = brain
        self.mascot = mascot_ref
        self.apps = {}
        
        # --- APP REGISTRY ---
        # Maps "Key Name" -> Class
        # I have included BOTH old names (e.g. 'Stream') and new names (e.g. 'Translator')
        # pointing to the same class to ensure compatibility with all buttons.
        self.app_map = {
            # Core
            "Chat": ChatApp,
            "Files": FilesApp,
            "System": SystemApp,
            "Settings": SettingsApp,
            
            # Dev Tools
            "Dev": DevApp,
            "Git": GitApp,
            "Database": DbApp,
            
            # Media & AI
            "Voice": VoiceApp,
            "Transcriber": TranscriberApp,
            
            # The Hybrid Keys (Old Name = Stream, New Name = Translator)
            "Stream": StreamApp,       # For Phone Button
            "Translator": StreamApp,   # For Workstation Button
            
            # Web & Utils
            "Web": WebApp,
            "Clock": ClockApp,
            "Downloader": DownloaderApp
        }
        
        self.init_all_apps()

    def init_all_apps(self):
        """Instantiates all available app classes."""
        logger.info("Initializing Application Modules...")
        
        for name, Cls in self.app_map.items():
            if Cls is None:
                logger.warning(f"Skipping {name}: Module not imported.")
                continue
                
            try:
                # Try creating app instance
                # Some apps need 'brain', some don't. We try both.
                try:
                    instance = Cls(self.brain)
                except TypeError:
                    instance = Cls()
                
                # Inject dependencies if missing
                if not hasattr(instance, 'brain'):
                    instance.brain = self.brain
                
                # Connect Signals (if the app supports them)
                if hasattr(instance, 'command_signal'):
                    try: instance.command_signal.connect(self.mascot.process_command)
                    except: pass
                
                if hasattr(instance, 'request_pose'):
                    try: instance.request_pose.connect(self.mascot.set_pose)
                    except: pass

                # Register App
                self.apps[name] = instance
                instance._app_name = name
                logger.info(f"✔ App Loaded: {name}")
                
            except Exception as e:
                logger.error(f"❌ Failed to init app '{name}': {e}")

    def get_app(self, name):
        """Returns the app instance by name."""
        return self.apps.get(name)

    def dock_to_layout(self, app_name, layout):
        """For Workstation: Puts app into the left pane."""
        app = self.get_app(app_name)
        if not app: 
            logger.error(f"App '{app_name}' not found in registry.")
            return False
        
        # Detach from previous parent safely
        if app.parent():
            old_parent = app.parent()
            # If it's in a layout, remove it
            if hasattr(old_parent, 'layout') and old_parent.layout():
                try: old_parent.layout().removeWidget(app)
                except: pass
            # If it's in a StackedWidget (Phone), remove it
            try: app.setParent(None)
            except: pass
        
        layout.addWidget(app)
        app.show()
        return True

    def dock_to_stack(self, app_name, stack_widget):
        """For Phone: Puts app into the QStackedWidget."""
        app = self.get_app(app_name)
        if not app: 
            logger.error(f"App '{app_name}' not found in registry.")
            return False
        
        # If app is already in this stack, just switch to it
        if stack_widget.indexOf(app) != -1:
            stack_widget.setCurrentWidget(app)
            return True

        # Detach from Workstation if needed
        if app.parent() and app.parent() != stack_widget:
            try: app.setParent(None)
            except: pass

        stack_widget.addWidget(app)
        stack_widget.setCurrentWidget(app)
        return True
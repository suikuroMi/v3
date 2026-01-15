#!/usr/bin/env python3
"""
Ookami Mio AI Assistant - Enterprise Edition V4
Main entry point with Auto-Dependency Management and First-Run Wizard.
"""

import sys
import os
import time
import socket
import logging
import logging.handlers
import argparse
import traceback
import shutil
import atexit
import subprocess
import importlib.util
from typing import Dict, Any

# ============================================================================
# 🌍 GLOBALS & CONFIG
# ============================================================================
VERSION = "3.3.0 (Enterprise)"
APP_NAME = "Ookami Mio"
DEFAULT_PORT = 50005 

# ============================================================================
# 🏗️ APPLICATION LAUNCHER
# ============================================================================

class ApplicationLauncher:
    """Orchestrates the entire application startup sequence."""
    
    def __init__(self):
        self.start_time = time.time()
        self.logger = None
        self.config = {}
        self.args = None
        self.lock_socket = None
        self.restart_needed = False

    def run(self) -> int:
        """Main execution flow."""
        try:
            # 1. Bootstrap (Paths & Args)
            self._setup_paths()
            self.args = self._parse_arguments()
            
            # Simple pre-log print
            print(f"🐺 Initializing {APP_NAME} v{VERSION}...")

            # 2. Dependency Self-Healing (BEFORE logging/imports)
            if not self._check_and_install_dependencies():
                print("❌ Critical dependencies missing. Aborting.")
                return 1
                
            if self.restart_needed:
                self._perform_restart()
                return 0

            # 3. Infrastructure
            self.logger = self._setup_logging(self.args.debug)
            self.config = self._load_configuration()
            
            # 4. First Run Experience
            if self._is_first_run():
                self._run_first_time_wizard()

            if not self._ensure_single_instance():
                return 1

            # 5. Validation & Health
            self._validate_configuration()
            self._perform_health_checks()

            # 6. Security & Recovery
            self._apply_security_profile()
            self._init_recovery_system()

            # 7. Launch UI
            return self._launch_ui()

        except KeyboardInterrupt:
            print("\n👋 Shutdown requested by user.")
            return 0
        except Exception as e:
            if self.logger:
                self.logger.critical(f"FATAL ERROR: {e}", exc_info=True)
            else:
                traceback.print_exc()
            return 1
        finally:
            self._cleanup()

    def _cleanup(self):
        """Final cleanup hooks."""
        if self.lock_socket:
            try:
                self.lock_socket.close()
            except: pass

    # --- PHASE 0: DEPENDENCIES ---
    def _check_and_install_dependencies(self):
        """Checks for Python packages and offers to install them."""
        required = {
            'PySide6': '6.5.0',
            'ollama': '0.1.0',
            'requests': '2.25.0'
        }
        
        missing = []
        for pkg in required:
            if importlib.util.find_spec(pkg) is None:
                missing.append(pkg)
        
        if not missing: return True
        
        print(f"\n⚠️  Missing required packages: {', '.join(missing)}")
        if self.args.auto_install:
            choice = 'y'
        else:
            choice = input("   Install them automatically? (Y/n): ").strip().lower()
        
        if choice in ['y', 'yes', '']:
            try:
                print("📦 Installing dependencies... (This may take a moment)")
                subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
                print("✅ Installation complete.")
                self.restart_needed = True
                return True
            except subprocess.CalledProcessError as e:
                print(f"❌ Installation failed: {e}")
                print(f"   Run manually: pip install {' '.join(missing)}")
                return False
        return False

    def _perform_restart(self):
        """Restarts the application to load new libraries."""
        print("🔄 Restarting application...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # --- PHASE 1: BOOTSTRAP ---
    def _setup_paths(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    def _parse_arguments(self):
        parser = argparse.ArgumentParser(description=f"{APP_NAME} Launcher")
        parser.add_argument('--version', action='store_true', help='Show version info')
        parser.add_argument('--debug', action='store_true', help='Enable debug logging')
        parser.add_argument('--safe-mode', action='store_true', help='Force strict security')
        parser.add_argument('--auto-install', action='store_true', help='Auto-install missing deps')
        parser.add_argument('--profile', choices=['normal', 'strict', 'paranoid'], default='normal')
        parser.add_argument('--skip-checks', action='store_true', help='Skip system health checks')
        parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Single-instance lock port')
        return parser.parse_args()

    # --- PHASE 2: INFRASTRUCTURE ---
    def _setup_logging(self, debug_mode: bool):
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "mio_system.log")

        logger = logging.getLogger("Mio")
        logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
        
        if logger.hasHandlers():
            for h in logger.handlers: h.close()
            logger.handlers.clear()

        file_fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        console_fmt = logging.Formatter('🐺 %(message)s')

        fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        fh.setFormatter(file_fmt)
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(console_fmt)
        logger.addHandler(ch)
        return logger

    def _ensure_single_instance(self):
        port = self.config.get("lock_port", DEFAULT_PORT)
        try:
            self.lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.lock_socket.bind(('127.0.0.1', port))
            atexit.register(self.lock_socket.close)
            self.logger.debug(f"Instance lock acquired on port {port}.")
            return True
        except socket.error:
            self.logger.error(f"Another instance is running (Port {port} busy).")
            print("❌ Mio is already running!")
            return False

    # --- PHASE 3: CONFIG & FIRST RUN ---
    def _load_configuration(self) -> Dict[str, Any]:
        return {
            "debug": self.args.debug,
            "profile": "strict" if self.args.safe_mode else self.args.profile,
            "max_memory_mb": int(os.environ.get("MIO_MAX_MEMORY", 4096)), 
            "lock_port": self.args.port,
            "capabilities": {}
        }
    
    def _is_first_run(self):
        config_dir = os.path.expanduser("~/.mio")
        return not os.path.exists(config_dir)

    def _run_first_time_wizard(self):
        print("\n" + "="*50)
        print("🎉 Welcome to Ookami Mio!")
        print("="*50)
        print("Creating configuration directory at ~/.mio ...")
        os.makedirs(os.path.expanduser("~/.mio"), exist_ok=True)
        print("✅ Setup complete. Launching...")
        time.sleep(1)

    def _validate_configuration(self):
        mem = self.config["max_memory_mb"]
        if mem < 256: 
            self.logger.warning(f"Memory limit {mem}MB too low. Bumping to 512MB.")
            self.config["max_memory_mb"] = 512

    def _perform_health_checks(self):
        if self.args.skip_checks: return

        self.logger.info("Performing health checks...")
        caps = self.config["capabilities"]
        
        caps["has_ffmpeg"] = bool(shutil.which("ffmpeg"))
        caps["has_git"] = bool(shutil.which("git"))
        
        if not caps["has_ffmpeg"]: self.logger.warning("Missing 'ffmpeg'. Audio disabled.")
        if not caps["has_git"]: self.logger.warning("Missing 'git'.")

    # --- PHASE 4: SECURITY ---
    def _apply_security_profile(self):
        profile = self.config["profile"]
        self.logger.info(f"Applying Security Profile: {profile.upper()}")
        
        # Inject into Env for skills to read
        can_write = "0" if profile == "paranoid" else "1"
        can_exec = "1" if profile == "normal" else "0"
        
        os.environ["MIO_ALLOW_WRITE"] = can_write
        os.environ["MIO_ALLOW_EXEC"] = can_exec
        os.environ["MIO_MAX_MEMORY"] = str(self.config["max_memory_mb"])

    def _init_recovery_system(self):
        try:
            from src.core.recovery import EmergencyRecovery
            EmergencyRecovery.enable()
        except ImportError: pass

    # --- PHASE 5: LAUNCH ---
    def _launch_ui(self):
        self.logger.info("Launching UI...")
        try:
            from PySide6.QtWidgets import QApplication
            from src.ui.window import MascotWidget
            
            app = QApplication(sys.argv)
            app.setApplicationName(APP_NAME)
            app.setApplicationVersion(VERSION)
            
            # Use singleton/env config inside widget
            window = MascotWidget() 
            window.show()
            
            return app.exec()
        except Exception as e:
            self.logger.critical(f"Runtime Crash: {e}", exc_info=True)
            return 1

# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    launcher = ApplicationLauncher()
    sys.exit(launcher.run())

if __name__ == "__main__":
    main()
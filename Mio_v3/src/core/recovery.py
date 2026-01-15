import os
import sys
import json
import shutil
import atexit
import signal
import time
import getpass
from datetime import datetime

class EmergencyRecovery:
    """
    Prevents system/Mio bricking with multiple safety nets.
    Runs independent of the AI Brain.
    """
    
    RECOVERY_FILE = os.path.expanduser("~/.mio_recovery_plan.json")
    SNAPSHOT_DIR = os.path.expanduser("~/.mio_snapshots")
    SETTINGS_FILE = os.path.expanduser("~/.mio_system_settings.json")
    BACKUP_DIR = os.path.expanduser("~/.mio_settings_backups")
    
    _IN_RECOVERY_MODE = False

    @classmethod
    def enable(cls):
        """Enables all safety nets on startup."""
        cls._setup_signal_handlers()
        cls._take_snapshot()
        atexit.register(cls._emergency_cleanup)
        print("🛡️  Emergency Recovery System: ACTIVATED")
    
    @classmethod
    def is_recovery_mode(cls):
        return cls._IN_RECOVERY_MODE

    @classmethod
    def _setup_signal_handlers(cls):
        def emergency_handler(signum, frame):
            print(f"\n⚠️  EMERGENCY: Signal {signum} received! Saving state...")
            cls.emergency_save()
            sys.exit(1)
        
        signal.signal(signal.SIGINT, emergency_handler)
        signal.signal(signal.SIGTERM, emergency_handler)
    
    @classmethod
    def emergency_save(cls):
        """Forces an immediate snapshot."""
        try:
            cls._take_snapshot()
            print("💾 Emergency Snapshot Saved.")
        except Exception as e:
            print(f"❌ Save Failed: {e}")

    @classmethod
    def _take_snapshot(cls):
        os.makedirs(cls.SNAPSHOT_DIR, exist_ok=True)
        snapshot = {
            "timestamp": time.time(),
            "user": getpass.getuser(),
            "platform": sys.platform
        }
        if os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, 'r') as f:
                    snapshot["settings"] = json.load(f)
            except: snapshot["settings"] = "CORRUPTED"

        filename = os.path.join(cls.SNAPSHOT_DIR, f"snapshot_{int(time.time())}.json")
        with open(filename, 'w') as f:
            json.dump(snapshot, f, indent=2)
        
        # Keep last 5
        snapshots = sorted(os.listdir(cls.SNAPSHOT_DIR))
        for old in snapshots[:-5]:
            os.remove(os.path.join(cls.SNAPSHOT_DIR, old))
    
    @classmethod
    def _emergency_cleanup(cls):
        print("🧹 System shutting down safely.")

    @classmethod
    def check_health(cls):
        """Checks for corruption and returns status."""
        warnings = []
        
        # 1. Check Settings File Integrity
        if os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, 'r') as f:
                    json.load(f)
            except json.JSONDecodeError:
                warnings.append("settings_corrupted")
                cls._IN_RECOVERY_MODE = True
        
        return (len(warnings) == 0), warnings

    @classmethod
    def repair_settings(cls):
        """Attempts to restore settings from the latest valid backup."""
        if not os.path.exists(cls.BACKUP_DIR): return False
        
        backups = sorted(os.listdir(cls.BACKUP_DIR))
        if not backups: return False
        
        # Try last 3 backups in reverse order
        for backup_file in reversed(backups[-3:]):
            full_path = os.path.join(cls.BACKUP_DIR, backup_file)
            try:
                with open(full_path, 'r') as f:
                    json.load(f) # Verify JSON validity
                shutil.copy2(full_path, cls.SETTINGS_FILE)
                cls._IN_RECOVERY_MODE = False
                return True
            except: continue
            
        return False

    @classmethod
    def factory_reset(cls):
        """Nukes settings to restore defaults."""
        if os.path.exists(cls.SETTINGS_FILE):
            os.remove(cls.SETTINGS_FILE)
        print("✅ Factory Reset Complete.")
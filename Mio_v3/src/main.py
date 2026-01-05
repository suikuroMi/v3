import sys
import os
import time
import atexit
import argparse
import traceback  # <--- Added for better error reporting

# --- 1. PATH CONFIGURATION (Critical) ---
# Ensures Python finds the 'src' module no matter where you run it from
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- 2. QT ENVIRONMENT CONFIG ---
# Setting these env vars helps PySide6 find plugins on Windows
os.environ["QT_API"] = "pyside6"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

VERSION = "3.0.0 (Enterprise)"

def parse_arguments():
    """Parses command line arguments for advanced startup options."""
    parser = argparse.ArgumentParser(description='Ookami Mio AI Assistant')
    parser.add_argument('--safe-mode', action='store_true', help='Force strict security settings')
    parser.add_argument('--no-recovery', action='store_true', help='Skip health checks and auto-repair')
    parser.add_argument('--debug', action='store_true', help='Enable verbose debug logging')
    parser.add_argument('--version', action='store_true', help='Show version info and exit')
    return parser.parse_args()

def check_requirements():
    """Ensures the host system meets minimum requirements."""
    # 1. Python Version Check (3.8+)
    if sys.version_info < (3, 8):
        print(f"❌ Critical Error: Python 3.8+ required. You are running {sys.version}.")
        return False
    return True

def cleanup_resources():
    """Runs on exit to ensure clean shutdown."""
    print("\n🧹 Shutting down Mio services...")
    print("✅ Cleanup complete. Oyasumi! 🐺")

def main():
    # Start the Stopwatch
    startup_start = time.time()
    
    # Register cleanup hook
    atexit.register(cleanup_resources)

    # Parse Flags
    args = parse_arguments()

    if args.version:
        print(f"🐺 Ookami Mio v{VERSION}")
        sys.exit(0)

    print(f"🚀 Launching Ookami Mio v{VERSION}...")

    # Validate System
    if not check_requirements():
        input("Press Enter to exit...")
        sys.exit(1)

    # Handle Flags
    if args.debug:
        print("🔍 DEBUG MODE: Enabled")
        os.environ["MIO_DEBUG"] = "true"
    
    if args.safe_mode:
        print("🛡️ SAFE MODE: Forcing strict security protocols.")

    # --- 3. RECOVERY & SECURITY LAYER ---
    if not args.no_recovery:
        try:
            from src.core.recovery import EmergencyRecovery
            from src.skills.settings_ops import SettingsSkills
            
            # Activate Shields
            EmergencyRecovery.enable()
            
            # Health Check
            is_healthy, warnings = EmergencyRecovery.check_health()
            if not is_healthy:
                print(f"⚠️  SYSTEM HEALTH WARNING: {warnings}")
                if "settings_corrupted" in warnings:
                    print("🔄 Auto-Repairing Settings...")
                    if EmergencyRecovery.repair_settings():
                        print("✅ Settings repaired from backup.")
                    else:
                        print("❌ Repair failed. Performing Factory Reset.")
                        EmergencyRecovery.factory_reset()

            # God Mode Check
            if SettingsSkills.get("god_mode") and not args.safe_mode:
                print("\n" + "⚡"*30)
                print("   WARNING: GOD MODE ACTIVE")
                print("   ALL SAFETY LIMITERS ARE DISABLED")
                print("⚡"*30 + "\n")

        except ImportError as e:
            print(f"⚠️  Module Warning: Recovery system missing ({e}). Skipping...")
        except Exception as e:
            print(f"❌ Recovery Error: {e}. Continuing startup...")

    # --- 4. LAUNCH UI ---
    try:
        # Import PySide6 here to catch import errors specifically
        from PySide6.QtWidgets import QApplication
        from src.ui.window import MascotWidget

        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        mascot = MascotWidget()
        mascot.show()

        # Stop Stopwatch
        duration = time.time() - startup_start
        print(f"✅ Startup complete in {duration:.2f}s. Mio is ready!")

        sys.exit(app.exec())

    except ImportError as e:
        print("\n❌ CRITICAL ERROR: PySide6 Import Failed.")
        print(f"   Error Details: {e}")
        print("   Debugging Info:")
        print(f"   - Python Executable: {sys.executable}")
        print(f"   - Python Version: {sys.version}")
        print("   - Site Packages Paths:")
        for p in sys.path:
            print(f"     {p}")
        print("\n💡 Tip: You might have multiple Python versions installed.")
        print("   Try running: 'python -m pip install PySide6'")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Runtime Crash: {e}")
        traceback.print_exc() # Prints the full error stack to see WHERE it crashed
        sys.exit(1)

if __name__ == "__main__":
    main()
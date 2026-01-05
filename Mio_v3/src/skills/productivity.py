import time
import threading
from PySide6.QtWidgets import QMessageBox

# We use a simple non-blocking timer logic here
# In a real app, this would communicate back to the Main Window
class ProductivitySkills:
    @staticmethod
    def start_focus_timer(args):
        # Format: "minutes" (default 25)
        try:
            minutes = int(args.strip())
        except: minutes = 25
        
        # We start a daemon thread so it doesn't block Mio
        def timer_run():
            time.sleep(minutes * 60)
            # This print will show up in the console, 
            # ideally we'd send a signal to the UI, but this is a V3 quick win
            print(f"\n🔔 RING RING! {minutes} minute focus session done!")
            
        t = threading.Thread(target=timer_run, daemon=True)
        t.start()
        
        return f"⏱️ Focus Timer set for {minutes} minutes! Work hard! 🌲"
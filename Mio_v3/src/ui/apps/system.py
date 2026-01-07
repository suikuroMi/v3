from .base import BaseApp  # <--- FIXED IMPORT
from src.skills.system_ops import SystemSkills

class SystemApp(BaseApp):
    def __init__(self):
        super().__init__("System Control", "cpu.png", "#4CAF50") # Green
        
        # Dynamic Info
        self.info_lbl = self.add_card_button("📊 Refresh Stats", "Click to update system info", self.refresh_stats)
        
        self.add_card_button("📸 Screenshot", "Capture screen to Desktop", "[SCREENSHOT]")
        self.add_card_button("📈 App Usage", "View most used apps", "[APP_STATS]")
        
        # Quick Launchers
        self.add_card_button("📝 Notepad", "Open Text Editor", "[OPEN] notepad")
        self.add_card_button("🌐 Browser", "Open Web Browser", "[OPEN] chrome")
        self.add_card_button("💻 Terminal", "Open Command Line", "[OPEN] terminal")

    def refresh_stats(self):
        info = SystemSkills.system_info()
        self.command_signal.emit(f"System Info:\n{info}")
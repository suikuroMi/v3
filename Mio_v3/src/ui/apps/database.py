from .base import BaseApp  # <--- FIXED (Matches your file name 'base.py')
from src.skills.db_ops import DbSkills

class DbApp(BaseApp):
    def __init__(self):
        super().__init__("Database Manager", "database.png", "#009688") # Teal
        
        # --- Info Section ---
        self.add_card_button("📊 Database Stats", "View table counts and size", self.get_info)
        
        # --- Actions ---
        self.add_card_button("🔎 Run Query", "Execute SQL Selection", lambda: self.command_signal.emit("[DB_QUERY] SELECT * FROM sqlite_master"))
        self.add_card_button("📄 View Schema", "Show table structure", lambda: self.command_signal.emit("[DB_SCHEMA]"))
        self.add_card_button("💾 Backup DB", "Create timestamped backup", lambda: self.command_signal.emit("[DB_BACKUP]"))
        
        # --- Advanced ---
        self.add_card_button("📤 Export Data", "Dump to CSV/JSON", lambda: self.command_signal.emit("Export [DB_EXPORT] to csv"))

    def get_info(self):
        # We can try to call the skill directly for a quick popup, 
        # or emit a command to let the AI handle the output in the chat.
        try:
            info = DbSkills.db_info()
            self.command_signal.emit(f"Database Report:\n{info}")
        except Exception as e:
            self.command_signal.emit(f"❌ DB Check Failed: {e}")
from .base_app import BaseApp
from src.skills.git_ops import GitSkills

class GitApp(BaseApp):
    def __init__(self):
        super().__init__("Git Control", "git.png", "#F4511E") # Deep Orange
        
        self.add_card_button("📝 Check Status", "git status -s", self.check_status)
        self.add_card_button("☁️ Push Changes", "Commit & Push to Origin", lambda: self.command_signal.emit("[GITHUB] push | Auto-Save via App"))
        self.add_card_button("📥 Clone Repo", "Clone URL to Desktop", lambda: self.command_signal.emit("[GITHUB] clone | URL"))
        self.add_card_button("🆕 Init Repo", "Initialize new project", lambda: self.command_signal.emit("[GITHUB] init | Name | public"))

    def check_status(self):
        res = GitSkills.git_status()
        self.command_signal.emit(f"Git Status Result: {res}")
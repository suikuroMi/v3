from .base_app import BaseApp

class DevApp(BaseApp):
    def __init__(self):
        super().__init__("Developer Tools", "code.png", "#2196F3") # Blue
        
        self.add_card_button("🚀 Open VS Code", "Launch IDE in current folder", "[VSCODE] .")
        self.add_card_button("📜 Snippet Manager", "View saved code snippets", "[SNIPPET] list")
        self.add_card_button("🐍 Lint Python", "Check syntax of file...", lambda: self.command_signal.emit("Please specify file to [LINT]"))
        self.add_card_button("✨ New Project", "Create template (Python/Web)", lambda: self.command_signal.emit("Create a [TEMPLATE] name | python"))
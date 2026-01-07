# [FIX]: Changed '.base_app' to '.base'
from .base import BaseApp

class FilesApp(BaseApp):
    def __init__(self):
        super().__init__("File Manager", "folder.png", "#FFC107") # Amber
        
        self.add_card_button("📂 View Desktop", "List files on Desktop", "[LIST] Desktop")
        self.add_card_button("📄 View Documents", "List files in Documents", "[LIST] Documents")
        self.add_card_button("🧹 Clean Desktop", "Move images/docs to folders", "[BATCH_MOVE] *.png|Desktop/Images")
        self.add_card_button("↩️ Undo Move", "Revert last operation", "[UNDO]")
        self.add_card_button("📸 Screenshots", "List captured screenshots", "[LIST] Desktop/Mio_Downloads")
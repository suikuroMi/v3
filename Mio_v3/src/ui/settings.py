import json
import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, 
                               QPushButton, QComboBox, QMessageBox, QCheckBox, QGroupBox)
from src.core.memory import MemoryCore

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mio Neural Config")
        self.resize(350, 400)
        self.setStyleSheet("background: #222; color: white;")
        
        self.mem = MemoryCore()
        
        layout = QVBoxLayout(self)
        
        # --- IDENTITY ---
        layout.addWidget(QLabel("Your Name:"))
        self.name_input = QLineEdit()
        self.name_input.setText(self.mem.data["user_profile"]["name"])
        layout.addWidget(self.name_input)
        
        layout.addWidget(QLabel("AI Model:"))
        self.model_input = QComboBox()
        self.model_input.addItems(["qwen2.5:7b", "llama3.2", "mistral", "deepseek-coder"])
        self.model_input.setEditable(True)
        layout.addWidget(self.model_input)

        # --- BRAIN SETTINGS (Toggles) ---
        box = QGroupBox("Neural Settings")
        box_layout = QVBoxLayout()
        
        self.chk_fuzzy = QCheckBox("Enable Deep/Fuzzy Search")
        self.chk_fuzzy.setChecked(self.mem.get_preference("fuzzy_search"))
        
        self.chk_proactive = QCheckBox("Proactive Suggestions")
        self.chk_proactive.setChecked(self.mem.get_preference("proactive_mode"))
        
        self.chk_sensei = QCheckBox("Mio Sensei Mode (Teaching)")
        self.chk_sensei.setChecked(self.mem.get_preference("sensei_mode"))
        
        box_layout.addWidget(self.chk_fuzzy)
        box_layout.addWidget(self.chk_proactive)
        box_layout.addWidget(self.chk_sensei)
        box.setLayout(box_layout)
        layout.addWidget(box)
        
        # Save
        save_btn = QPushButton("Save Configuration")
        save_btn.setStyleSheet("background: #3EA6FF; padding: 10px; border-radius: 5px; font-weight: bold;")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

    def save_settings(self):
        self.mem.update_profile("name", self.name_input.text())
        # Save Toggles
        self.mem.set_preference("fuzzy_search", self.chk_fuzzy.isChecked())
        self.mem.set_preference("proactive_mode", self.chk_proactive.isChecked())
        self.mem.set_preference("sensei_mode", self.chk_sensei.isChecked())
        
        # Save Model to generic config if needed, or just memory
        QMessageBox.information(self, "Saved", "Neural pathways updated! 🧠")
        self.accept()
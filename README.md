# 🐺 Ookami Mio AI Assistant

Ookami Mio is an advanced, multi-modal AI assistant designed for productivity, development, and system management. It features a modular "Skills" architecture, dynamic personality switching, and deep system integration via the Ollama AI engine.
---

🛠️ **Project Status:** To get a better grasp of what this assistant can and can't do yet, please click [HERE](https://github.com/suikuroMi/v3/issues) to review the current project issues and development scope.

---
## 🚀 Quick Start

### Prerequisites
* **Python**: 3.10 or higher
* **AI Core**: [Ollama](https://ollama.com/) must be installed and running on port 11434
* **Models**: The system utilizes `qwen2.5:7b` and `llava:latest`

### Installation
Run the setup wizard to install dependencies and pull required AI models:
```bash
python setup_mio.py
```
*Note: This installs core libraries including PySide6, Ollama, Pillow, pyautogui, and yt-dlp.*

### Launching Mio
Start the application via the main entry point:
```bash
python src/main.py
```

---

## 🎭 Personalities
Mio features a dynamic personality system managed by the `PersonalityManager`:

| Mode | Name | Title | Description | Emojis |
| :--- | :--- | :--- | :--- | :--- |
| **maid** | Mio-mama | Wolf Priestess | Caring, motherly assistant focused on well-being. | 🌲 🍱 🐺 ✨ 🧹 ⛩️ |
| **coder** | Mio-sensei | Code Sensei | Technical developer assistant focused on standards. | 👨‍💻 🚀 🐛 🔧 ⚡ 💾 |
| **pro** | Ms. Ookami | Executive Admin | Formal, precise, and efficient administrator. | 💼 📊 ✅ 📅 📈 |

---

## 🛠️ Key Capabilities
Mio’s functionality is divided into specialized "Skill" modules registered in the `ToolRegistry`:

### 📂 File & System Management
* **Smart File Ops**: Move, batch move, and undo file operations with safety checks for critical paths.
* **System Control**: Open authorized applications, take screenshots via `pyautogui`, and monitor system health.

### 👩‍💻 Development Tools
* **Code Writing**: Create and edit files with built-in syntax validation for Python and JSON.
* **Templates**: Generate project boilerplates for Flask, React, and Web projects.
* **VS Code Integration**: Launch VS Code directly into specific project directories.

### 🌐 Web & Media
* **Secure Search**: Search Google with protocol-level security to prevent dangerous queries.
* **Media Downloader**: Download videos and audio using `yt-dlp` integration.

### 🎧 Audio & AI Hearing
* **Whisper Integration**: High-accuracy transcription using OpenAI's Whisper model.
* **Livestream Mode**: Real-time transcription and translation of online streams with automated SRT generation.
* Note: The transcription is still not good enough as it sometimes it cuts the word*

---

## 🛡️ Security & Safety
Mio is built with an "Enterprise" security mindset:
* **Path Whitelisting**: Restricts file operations to safe user directories like Desktop and Documents.
* **Extension Filtering**: Blocks dangerous file types (e.g., `.exe`, `.sh`) unless "God Mode" is enabled.
* **Process Audit**: Logs system activity and tool usage to `system_audit.log` for transparency.
* **Rate Limiting**: Prevents "app bombing" by limiting launch frequencies for system tools.

---

## 📂 Project Structure
```text
Mio_v3/
├── assets/             # Avatars (Happy, Idle, Think) and UI icons
├── config/             # System prompts and configurations
├── src/
│   ├── agent/          # LLM engine and Persona management
│   ├── core/           # OS handlers, memory, and path recovery
│   ├── skills/         # Functional modules (File, Web, Audio, etc.)
│   ├── ui/             # PySide6 window and widget management
│   └── main.py         # Application entry point
├── setup_mio.py        # Environment setup script
└── run.bat             # Windows execution script
```

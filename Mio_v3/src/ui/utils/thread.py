from PySide6.QtCore import QThread, Signal

class ThinkingThread(QThread):
    response_ready = Signal(str)
    log_signal = Signal(str)
    
    def __init__(self, brain, text):
        super().__init__()
        self.brain = brain
        self.text = text

    def run(self):
        try:
            stream = self.brain.think_stream(self.text)
            for chunk in stream:
                if any(x in chunk for x in ["⚙️", "🔧", "🧠", "[", "]"]):
                    self.log_signal.emit(chunk)
                else:
                    self.response_ready.emit(chunk)
        except Exception as e:
            self.response_ready.emit(f"❌ Brain Error: {e}")
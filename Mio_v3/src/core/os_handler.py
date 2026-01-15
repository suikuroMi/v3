import os
import sys
import platform
import subprocess

class OSHandler:
    @staticmethod
    def open_file(path):
        """Opens a file or URL using the default OS application."""
        system = platform.system()
        try:
            if system == 'Windows':
                os.startfile(path)
            elif system == 'Darwin':  # macOS
                subprocess.call(('open', path))
            else:  # Linux
                subprocess.call(('xdg-open', path))
            return True
        except Exception as e:
            print(f"❌ OS Error: {e}")
            return False

    @staticmethod
    def get_app_data_dir():
        """Returns a safe place to store memory/logs."""
        return os.path.join(os.getcwd(), 'data')
import webbrowser
import os
import urllib.parse
import yt_dlp
import re
from src.core.finder import find_path

class WebSkills:
    @staticmethod
    def search_google(query):
        # V3: Protocol Check
        DANGEROUS_PREFIXES = ["javascript:", "data:", "file:", "about:"]
        if any(query.lower().strip().startswith(p) for p in DANGEROUS_PREFIXES):
             return "❌ Security Alert: Dangerous protocol detected."
             
        safe_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={safe_query}"
        webbrowser.open(url)
        return f"🔍 Searching Google for: {query}"

    @staticmethod
    def download_media(url):
        # V3: URL Validation
        if not url.startswith(("http://", "https://")):
            return "❌ Invalid URL protocol."
            
        # V3: Extension Blacklist (Basic check on URL, yt-dlp checks content too)
        if re.search(r"(\.exe|\.bat|\.vbs|\.sh)$", url, re.IGNORECASE):
            return "❌ Security Alert: Cannot download executables."

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        save_folder = os.path.join(desktop, "Mio_Downloads")
        os.makedirs(save_folder, exist_ok=True)
        
        try:
            ydl_opts = {
                'outtmpl': os.path.join(save_folder, '%(title)s.%(ext)s'),
                'format': 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'Unknown')
                
            return f"✅ Downloaded '{title}' to {save_folder}"
        except Exception as e:
            return f"❌ Download failed: {e}"
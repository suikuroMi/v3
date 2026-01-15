import os
import threading
import time
import wave
import tempfile
import uuid
import subprocess
import shutil
import datetime
import glob
import queue # <--- NEW: For buffering
import io

try:
    import whisper
    import sounddevice as sd
    import numpy as np
    import yt_dlp
except ImportError:
    sd = None
    whisper = None
    yt_dlp = None
    np = None

class AudioSkills:
    # --- CONFIGURATION ---
    DEFAULT_MODEL_SIZE = "base" # Use 'tiny' for fastest, 'base' for balance
    DEFAULT_SAMPLE_RATE = 16000
    
    _model = None
    _is_listening_continuous = False
    _continuous_thread = None
    _session_file = None
    _current_device_index = None
    _srt_index = 1 # Track subtitle lines

    @classmethod
    def _load_model(cls, size=None):
        if not whisper: return None
        target_size = size or cls.DEFAULT_MODEL_SIZE
        if cls._model is None:
            print(f"⏳ Loading Whisper AI model ({target_size})...")
            cls._model = whisper.load_model(target_size)
        return cls._model

    @staticmethod
    def _create_temp_filename(ext=".wav"):
        return os.path.join(tempfile.gettempdir(), f"mio_audio_{uuid.uuid4()}{ext}")

    @staticmethod
    def get_latest_notes(args=""):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        files = glob.glob(os.path.join(desktop, "Mio_*_Notes_*.txt"))
        if not files: return "❌ No notes found."
        latest_file = max(files, key=os.path.getctime)
        try:
            if os.name == 'nt': os.startfile(latest_file)
            else: subprocess.call(('open', latest_file))
            return f"✅ Opened: {os.path.basename(latest_file)}"
        except: return f"✅ Found: {os.path.basename(latest_file)}"

    @staticmethod
    def list_devices(args=""):
        if not sd: return "❌ Libs missing."
        try:
            devices = sd.query_devices()
            info = "🎧 **Audio Devices:**\n"
            for i, d in enumerate(devices):
                if d['max_input_channels'] > 0:
                    icon = "🎙️"
                    if "Stereo Mix" in d['name'] or "Loopback" in d['name']: icon = "💻"
                    info += f"  `{i}`: {icon} {d['name']}\n"
            return info
        except: return "❌ Error listing devices."

    @staticmethod
    def set_input_device(args):
        try:
            AudioSkills._current_device_index = int(args.strip())
            return f"✅ Mic set to ID: {AudioSkills._current_device_index}"
        except: return "❌ Usage: [SET_MIC] ID"

    # --- LIVE LISTENING (Mic/System) ---
    @staticmethod
    def listen_live(seconds=10, translate=False):
        if not sd or not whisper: return "❌ Audio libs missing."
        temp_file = AudioSkills._create_temp_filename(".wav")
        try:
            # Record at 16k for Whisper compatibility
            recording = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, 
                               dtype='int16', device=AudioSkills._current_device_index)
            sd.wait()
            
            with wave.open(temp_file, 'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
                wf.writeframes(recording.tobytes())
            
            model = AudioSkills._load_model()
            result = model.transcribe(temp_file, task="translate" if translate else "transcribe")
            try: os.remove(temp_file)
            except: pass
            return result['text'].strip()
        except Exception as e: return f"❌ Error: {e}"

    # --- STREAMING ENGINE V6.1 (Producer-Consumer) ---
    @classmethod
    def start_livestream_mode(cls, url, callback_func, translate=False):
        """Optimized real-time streaming with overlapping processing."""
        if cls._is_listening_continuous: return "⚠️ Already active."
        if not yt_dlp or not shutil.which("ffmpeg"): return "❌ Need yt-dlp & ffmpeg."

        cls._is_listening_continuous = True
        
        # Setup Paths
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        cls._session_file = os.path.join(desktop, f"Mio_Stream_Notes_{timestamp}.txt")
        srt_file = os.path.join(desktop, f"Mio_Stream_{timestamp}.srt")
        cls._srt_index = 1
        
        # Shared Buffer
        audio_queue = queue.Queue(maxsize=5) # Buffer up to 5 chunks
        
        # PRODUCER: FFMPEG -> Queue
        def audio_producer():
            try:
                print(f"📡 Resolving stream URL...")
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'live_from_start': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    stream_url = info['url']
                
                print("🎧 Audio stream connected. Buffering...")
                cmd = [
                    'ffmpeg', '-i', stream_url,
                    '-f', 's16le', '-ar', '16000', '-ac', '1', '-acodec', 'pcm_s16le',
                    '-loglevel', 'error', '-vn', 'pipe:1'
                ]
                
                # 5-second chunks = Low Latency
                chunk_duration = 5 
                bytes_per_chunk = 16000 * 2 * chunk_duration 
                
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                
                while cls._is_listening_continuous:
                    audio_bytes = process.stdout.read(bytes_per_chunk)
                    if not audio_bytes: break
                    if len(audio_bytes) < bytes_per_chunk: continue # Skip partial
                    
                    audio_queue.put(audio_bytes) # Push to buffer
                    
                process.terminate()
            except Exception as e:
                callback_func(f"❌ Stream Source Error: {e}")
                cls._is_listening_continuous = False

        # CONSUMER: Queue -> Whisper
        def transcription_consumer():
            model = cls._load_model() # Load once
            task = "translate" if translate else "transcribe"
            accumulated_time = 0.0

            while cls._is_listening_continuous:
                try:
                    # Get from buffer (wait max 2s)
                    audio_bytes = audio_queue.get(timeout=2)
                    
                    # Convert to Float32
                    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    
                    # Transcribe
                    result = model.transcribe(audio_np, task=task, fp16=False)
                    text = result['text'].strip()
                    
                    if text:
                        time_str = datetime.datetime.now().strftime("%H:%M:%S")
                        formatted = f"[{time_str}] {text}"
                        
                        # 1. Output to UI
                        callback_func(formatted)
                        
                        # 2. Write to Log
                        with open(cls._session_file, "a", encoding="utf-8") as f:
                            f.write(formatted + "\n")
                        
                        # 3. Write to SRT
                        # Estimate timestamps relative to stream start
                        with open(srt_file, "a", encoding="utf-8") as f:
                            start_fmt = cls._seconds_to_srt_time(accumulated_time)
                            end_fmt = cls._seconds_to_srt_time(accumulated_time + 5.0)
                            f.write(f"{cls._srt_index}\n{start_fmt} --> {end_fmt}\n{text}\n\n")
                            cls._srt_index += 1
                    
                    accumulated_time += 5.0
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"Transcription Error: {e}")

        # Start Threads
        t_prod = threading.Thread(target=audio_producer, daemon=True)
        t_cons = threading.Thread(target=transcription_consumer, daemon=True)
        t_prod.start()
        t_cons.start()
        
        return f"📡 Streaming Active. Latency: ~5s. Notes: {os.path.basename(cls._session_file)}"

    @staticmethod
    def _seconds_to_srt_time(seconds):
        millis = int((seconds % 1) * 1000)
        seconds = int(seconds)
        mins, secs = divmod(seconds, 60)
        hrs, mins = divmod(mins, 60)
        return f"{hrs:02}:{mins:02}:{secs:02},{millis:03}"

    @classmethod
    def start_continuous_mode(cls, callback_func, translate=False):
        """Standard Class Mode (Mic/System)"""
        if cls._is_listening_continuous: return "⚠️ Already active."
        cls._is_listening_continuous = True
        
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        cls._session_file = os.path.join(desktop, f"Mio_Class_Notes_{timestamp}.txt")
        
        def listen_loop():
            while cls._is_listening_continuous:
                text = cls.listen_live(seconds=10, translate=translate) # 10s chunks for mic is fine
                if text and "❌" not in text and "(Silence)" not in text:
                    formatted = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}"
                    callback_func(formatted)
                    try:
                        with open(cls._session_file, "a", encoding="utf-8") as f: f.write(formatted + "\n")
                    except: pass
                time.sleep(0.1)

        cls._continuous_thread = threading.Thread(target=listen_loop, daemon=True)
        cls._continuous_thread.start()
        return f"🎙️ Class Mode Active. Notes: {os.path.basename(cls._session_file)}"

    @classmethod
    def stop_continuous_mode(cls):
        if not cls._is_listening_continuous: return "⚠️ Not listening."
        cls._is_listening_continuous = False
        return "🛑 Stopping stream..."
    
    # Registry Wrapper
    @staticmethod
    def transcribe(args):
        if not whisper: return "❌ Audio libs missing."
        return "✅ Use [TRANSCRIBE] for files. Use Livestream Mode for real-time."
    
    @staticmethod
    def livestream_wrapper(args):
        """Wrapper for registry calls."""
        return "⚠️ Use the UI button or [LIVESTREAM] url command."
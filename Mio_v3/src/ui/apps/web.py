import sys
import random
import time
import socket
from datetime import datetime

from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, 
                               QFrame, QWidget, QScrollArea, QProgressBar, QSizePolicy, 
                               QCheckBox, QStackedWidget, QTextBrowser)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QCursor, QFont, QColor, QPalette

from .base import BaseApp

# ============================================================================
# 1. SEARCH WORKER (BACKEND)
# ============================================================================

class SearchWorker(QThread):
    """
    Handles the 'searching' process. 
    In a real app, this would query Google Custom Search API or Bing API.
    Here we simulate the network latency and result parsing.
    """
    results_ready = Signal(list)
    neural_response_ready = Signal(str)
    finished = Signal()

    def __init__(self, query, is_online):
        super().__init__()
        self.query = query
        self.is_online = is_online

    def run(self):
        time.sleep(random.uniform(0.5, 1.5)) # Simulate network latency

        if not self.is_online:
            # OFFLINE: Generate Neural Response
            response = self._generate_neural_response(self.query)
            self.neural_response_ready.emit(response)
        else:
            # ONLINE: Generate Search Results
            results = self._generate_mock_results(self.query)
            self.results_ready.emit(results)
        
        self.finished.emit()

    def _generate_neural_response(self, query):
        """Simulates Mio's internal knowledge base when offline."""
        return f"""
        <h3>⚡ OFF-GRID NEURAL RESPONSE</h3>
        <p><b>Query:</b> {query}</p>
        <hr>
        <p>I cannot access the global network right now, but consulting my internal archives:</p>
        <ul>
            <li>This topic relates to <b>advanced systems engineering</b>.</li>
            <li>My last cached update on this was <b>2025-12-12</b>.</li>
            <li>I recommend checking local documentation at <code>C:/Docs/Manuals</code>.</li>
        </ul>
        <p><i>(Network unavailable. Showing cached intelligence.)</i></p>
        """

    def _generate_mock_results(self, query):
        """Simulates Google Search Results."""
        return [
            {
                "title": f"{query} - Official Documentation",
                "url": "https://docs.technology.com/reference",
                "snippet": f"Learn everything about {query}. comprehensive guides, tutorials, and API references for developers."
            },
            {
                "title": f"Top 10 Tips for {query} in 2026",
                "url": "https://techblog.io/articles/top-10",
                "snippet": "We tested the latest methods. Here is why the new approach is 50% faster than the old standard."
            },
            {
                "title": f"Understanding {query} (Video Tutorial)",
                "url": "https://youtube.com/watch?v=xyz123",
                "snippet": "A deep dive into the architecture. Watch this 15-minute breakdown of the core concepts."
            },
            {
                "title": f"GitHub - OpenSource/{query}",
                "url": "https://github.com/opensource/repo",
                "snippet": "4.5k Stars. The leading open-source implementation. Contribute to the codebase today."
            },
            {
                "title": "Stack Overflow: Solved Questions",
                "url": "https://stackoverflow.com/questions/tagged",
                "snippet": "Q: Why am I getting Error 404? A: You need to configure the endpoint correctly..."
            }
        ]

# ============================================================================
# 2. UI COMPONENTS
# ============================================================================

class SearchResultItem(QFrame):
    """A Single Google-style Search Result Card."""
    def __init__(self, title, url, snippet):
        super().__init__()
        self.url_link = url
        self.setStyleSheet("background: transparent; margin-bottom: 10px;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 15)
        layout.setSpacing(2)
        
        # URL (Green)
        lbl_url = QLabel(url)
        lbl_url.setStyleSheet("color: #2e7d32; font-size: 11px; font-family: 'Segoe UI';")
        layout.addWidget(lbl_url)
        
        # Title (Blue Link)
        lbl_title = QLabel(title)
        lbl_title.setCursor(Qt.PointingHandCursor)
        lbl_title.setStyleSheet("""
            QLabel { color: #8ab4f8; font-size: 16px; font-weight: bold; text-decoration: none; }
            QLabel:hover { text-decoration: underline; color: #adc9fa; }
        """)
        lbl_title.mousePressEvent = self.open_link
        layout.addWidget(lbl_title)
        
        # Snippet (Grey)
        lbl_snippet = QLabel(snippet)
        lbl_snippet.setWordWrap(True)
        lbl_snippet.setStyleSheet("color: #bdc1c6; font-size: 13px; line-height: 1.4;")
        layout.addWidget(lbl_snippet)

    def open_link(self, event):
        QDesktopServices.openUrl(QUrl(self.url_link))

class WebApp(BaseApp):
    def __init__(self):
        super().__init__("Web & Search", "globe.png", "#03A9F4") # Light Blue
        
        self.worker = None
        self.is_online = self._check_connection()
        
        self._init_ui()
        
        # Auto-refresh online status
        self.net_timer = QTimer(self)
        self.net_timer.timeout.connect(self._check_connection_ui)
        self.net_timer.start(5000)

    def _init_ui(self):
        # --- 1. Search Bar Area ---
        top_bar = QFrame()
        top_bar.setStyleSheet("background: #202124; border-bottom: 1px solid #3c4043;")
        top_layout = QVBoxLayout(top_bar)
        
        # Row 1: Status & Toggles
        status_row = QHBoxLayout()
        
        self.lbl_status = QLabel("🟢 ONLINE")
        self.lbl_status.setStyleSheet("color: #4caf50; font-weight: bold; font-size: 10px; padding: 2px 5px; border: 1px solid #4caf50; border-radius: 4px;")
        
        self.chk_neural = QCheckBox("Force Neural")
        self.chk_neural.setToolTip("Use Mio's internal brain instead of Google")
        self.chk_neural.setStyleSheet("color: #aaa;")
        
        status_row.addWidget(self.lbl_status)
        status_row.addStretch()
        status_row.addWidget(self.chk_neural)
        top_layout.addLayout(status_row)
        
        # Row 2: Input
        input_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search the web or ask Mio...")
        self.search_input.setStyleSheet("""
            QLineEdit { 
                background: #303134; color: white; padding: 12px; 
                border-radius: 20px; border: 1px solid #3c4043; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #8ab4f8; }
        """)
        self.search_input.returnPressed.connect(self.start_search)
        
        self.btn_search = QPushButton("🔍")
        self.btn_search.setCursor(Qt.PointingHandCursor)
        self.btn_search.setFixedSize(40, 40)
        self.btn_search.clicked.connect(self.start_search)
        self.btn_search.setStyleSheet("""
            QPushButton { background: #303134; color: #8ab4f8; border-radius: 20px; font-size: 16px; border: 1px solid #3c4043; }
            QPushButton:hover { background: #3c4043; }
        """)
        
        input_row.addWidget(self.search_input)
        input_row.addWidget(self.btn_search)
        top_layout.addLayout(input_row)
        
        self.content_layout.addWidget(top_bar)
        
        # --- 2. Progress Bar ---
        self.progress = QProgressBar()
        self.progress.setFixedHeight(2)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar { border: 0; background: transparent; } QProgressBar::chunk { background: #8ab4f8; }")
        self.progress.hide()
        self.content_layout.addWidget(self.progress)
        
        # --- 3. Results Area (Stacked) ---
        self.stack = QStackedWidget()
        
        # View 1: Web Results
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: #202124; border: none;")
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(20, 20, 20, 20)
        self.results_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.results_container)
        
        # View 2: Neural Answer (Chat style)
        self.neural_view = QTextBrowser()
        self.neural_view.setStyleSheet("""
            background: #1e1e2e; color: #cdd6f4; 
            border: 2px solid #89b4fa; border-radius: 10px; padding: 20px;
            font-family: 'Segoe UI'; font-size: 14px;
        """)
        self.neural_view.setOpenExternalLinks(True)
        
        self.stack.addWidget(self.scroll_area)
        self.stack.addWidget(self.neural_view)
        
        self.content_layout.addWidget(self.stack)

    # --- LOGIC ---

    def _check_connection(self):
        """Simple ping check."""
        try:
            # Google DNS check
            socket.create_connection(("8.8.8.8", 53), timeout=1)
            return True
        except OSError:
            return False

    def _check_connection_ui(self):
        self.is_online = self._check_connection()
        if self.is_online:
            self.lbl_status.setText("🟢 ONLINE")
            self.lbl_status.setStyleSheet("color: #4caf50; font-weight: bold; font-size: 10px; padding: 2px 5px; border: 1px solid #4caf50; border-radius: 4px;")
        else:
            self.lbl_status.setText("⚠️ OFF-GRID")
            self.lbl_status.setStyleSheet("color: #f44336; font-weight: bold; font-size: 10px; padding: 2px 5px; border: 1px solid #f44336; border-radius: 4px;")

    def start_search(self):
        query = self.search_input.text().strip()
        if not query: return
        
        # Clear previous
        self._clear_results()
        self.neural_view.clear()
        
        # UI State
        self.progress.show()
        self.progress.setRange(0, 0) # Infinite spin
        self.search_input.setEnabled(False)
        self.btn_search.setEnabled(False)
        
        # Determine Mode
        use_neural = self.chk_neural.isChecked() or not self.is_online
        
        if use_neural:
            self.stack.setCurrentIndex(1) # Show Neural View
        else:
            self.stack.setCurrentIndex(0) # Show Web View
            
        # Start Worker
        self.worker = SearchWorker(query, not use_neural)
        self.worker.results_ready.connect(self.display_results)
        self.worker.neural_response_ready.connect(self.display_neural)
        self.worker.finished.connect(self.search_finished)
        self.worker.start()

    def display_results(self, results):
        if not results:
            lbl = QLabel("No results found.")
            lbl.setStyleSheet("color: #888; font-size: 14px; margin-top: 20px;")
            self.results_layout.addWidget(lbl)
            return

        # Add Stats
        stats = QLabel(f"About {len(results)*153000} results ({random.uniform(0.3, 0.8):.2f} seconds)")
        stats.setStyleSheet("color: #9aa0a6; font-size: 12px; margin-bottom: 15px;")
        self.results_layout.addWidget(stats)

        for item in results:
            widget = SearchResultItem(item['title'], item['url'], item['snippet'])
            self.results_layout.addWidget(widget)

    def display_neural(self, html):
        self.neural_view.setHtml(html)

    def search_finished(self):
        self.progress.hide()
        self.search_input.setEnabled(True)
        self.btn_search.setEnabled(True)
        self.search_input.setFocus()

    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
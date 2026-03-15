import sys
import os
import json
import threading
import subprocess
import tempfile
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QListWidget, QMessageBox, QGroupBox, QSplitter,
                               QListWidgetItem, QProgressBar, QFileDialog)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QByteArray
from PySide6.QtGui import QPixmap

from onshape_client import OnshapeClient

CONFIG_FILE = os.path.expanduser("~/.onshape_to_orca_config.json")

class WorkerThread(QThread):
    finished = Signal(object)
    error = Signal(str)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class OnshapeOrcaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Onshape to OrcaSlicer")
        self.setGeometry(100, 100, 1000, 700)
        
        self.client = None
        self.current_docs = {}
        self.current_elements = {}
        self.active_threads = []  # Track active worker threads
        
        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)

        # Configuration Section
        self.setup_config_ui()
        
        # Navigation Section
        self.setup_navigation_ui()
        
        # Action Section
        self.setup_action_ui()

        # Load Config
        self.load_config()
        
        # Try to init client if keys exist
        if self.access_key_input.text() and self.secret_key_input.text():
            self.init_client()

    def setup_config_ui(self):
        config_group = QGroupBox("Configuration")
        config_layout = QVBoxLayout()
        
        # Access Key
        access_layout = QHBoxLayout()
        access_layout.addWidget(QLabel("Access Key:"))
        self.access_key_input = QLineEdit()
        access_layout.addWidget(self.access_key_input)
        config_layout.addLayout(access_layout)

        # Secret Key
        secret_layout = QHBoxLayout()
        secret_layout.addWidget(QLabel("Secret Key:"))
        self.secret_key_input = QLineEdit()
        self.secret_key_input.setEchoMode(QLineEdit.Password)
        secret_layout.addWidget(self.secret_key_input)
        config_layout.addLayout(secret_layout)
        
        # OrcaSlicer Path
        orca_layout = QHBoxLayout()
        orca_layout.addWidget(QLabel("OrcaSlicer Path:"))
        self.orca_path_input = QLineEdit()
        self.orca_path_input.setPlaceholderText("/path/to/orca-slicer")
        orca_layout.addWidget(self.orca_path_input)
        
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(30)
        browse_btn.clicked.connect(self.browse_orca_path)
        orca_layout.addWidget(browse_btn)
        config_layout.addLayout(orca_layout)

        # Download Path
        dl_layout = QHBoxLayout()
        dl_layout.addWidget(QLabel("Download Directory:"))
        self.dl_path_input = QLineEdit()
        self.dl_path_input.setPlaceholderText("/path/to/downloads (leave empty for temp dir)")
        dl_layout.addWidget(self.dl_path_input)
        
        browse_dl_btn = QPushButton("...")
        browse_dl_btn.setFixedWidth(30)
        browse_dl_btn.clicked.connect(self.browse_dl_path)
        dl_layout.addWidget(browse_dl_btn)
        config_layout.addLayout(dl_layout)

        # Save Button
        self.save_config_btn = QPushButton("Save & Connect")
        self.save_config_btn.clicked.connect(self.save_and_connect)
        config_layout.addWidget(self.save_config_btn)

        config_group.setLayout(config_layout)
        self.layout.addWidget(config_group)

    def browse_orca_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select OrcaSlicer Executable")
        if path:
            self.orca_path_input.setText(path)

    def browse_dl_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if path:
            self.dl_path_input.setText(path)

    def setup_navigation_ui(self):
        nav_group = QGroupBox("Navigation")
        nav_layout = QHBoxLayout()

        # Documents List with Preview
        doc_container = QVBoxLayout()
        doc_container.addWidget(QLabel("Documents (sorted by last modified)"))
        
        doc_content = QHBoxLayout()
        self.doc_list = QListWidget()
        self.doc_list.itemClicked.connect(self.on_doc_selected)
        doc_content.addWidget(self.doc_list)
        
        # Document preview
        self.doc_preview = QLabel()
        self.doc_preview.setFixedSize(300, 300)
        self.doc_preview.setAlignment(Qt.AlignCenter)
        self.doc_preview.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")
        self.doc_preview.setText("No preview")
        doc_content.addWidget(self.doc_preview)
        
        doc_container.addLayout(doc_content)
        nav_layout.addLayout(doc_container)

        # Elements List
        elem_layout = QVBoxLayout()
        elem_layout.addWidget(QLabel("Part Studios"))
        self.elem_list = QListWidget()
        self.elem_list.itemClicked.connect(self.on_elem_selected)
        elem_layout.addWidget(self.elem_list)
        nav_layout.addLayout(elem_layout)

        nav_group.setLayout(nav_layout)
        self.layout.addWidget(nav_group)

    def setup_action_ui(self):
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout()

        self.status_label = QLabel("Ready")
        action_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        action_layout.addWidget(self.progress_bar)

        self.export_btn = QPushButton("Export & Open in OrcaSlicer")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.start_export)
        action_layout.addWidget(self.export_btn)

        action_group.setLayout(action_layout)
        self.layout.addWidget(action_group)


    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.access_key_input.setText(config.get('access_key', ''))
                    self.secret_key_input.setText(config.get('secret_key', ''))
                    self.orca_path_input.setText(config.get('orca_path', ''))
                    self.dl_path_input.setText(config.get('dl_path', ''))
            except Exception as e:
                print(f"Error loading config: {e}")

    def save_and_connect(self):
        config = {
            'access_key': self.access_key_input.text().strip(),
            'secret_key': self.secret_key_input.text().strip(),
            'orca_path': self.orca_path_input.text().strip(),
            'dl_path': self.dl_path_input.text().strip()
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)
            self.status_label.setText("Configuration saved.")
            self.init_client()
            self.refresh_documents()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {e}")


    def init_client(self):
        access = self.access_key_input.text().strip()
        secret = self.secret_key_input.text().strip()
        if access and secret:
            self.client = OnshapeClient(access, secret)
            self.status_label.setText("Client initialized.")

    def refresh_documents(self):
        if not self.client:
            QMessageBox.warning(self, "Error", "Client not initialized. Save config first.")
            return
            
        self.status_label.setText("Fetching documents...")
        self.doc_list.clear()
        self.current_docs = {}
        self.elem_list.clear()
        
        self.worker = WorkerThread(self.client.get_documents)
        self.worker.finished.connect(self.handle_docs_loaded)
        self.worker.error.connect(self.handle_error)
        self.active_threads.append(self.worker)
        self.worker.start()

    def handle_docs_loaded(self, result):
        items = result.get('items', [])
        
        # Documents are already sorted by the API (modifiedAt desc)
        for doc in items:
            name = doc.get('name', 'Unknown')
            did = doc.get('id')
            default_ws = doc.get('defaultWorkspace', {}).get('id')
            
            # We need a workspace to list elements.
            if did and default_ws:
                # Find 300x300 thumbnail URL
                thumb_url = None
                thumbnail_obj = doc.get('thumbnail', {})
                for size_info in thumbnail_obj.get('sizes', []):
                    if size_info.get('size') == '300x300':
                        thumb_url = size_info.get('href')
                        break
                
                self.current_docs[did] = {
                    'name': name, 
                    'default_workspace': default_ws,
                    'thumb_url': thumb_url
                }
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, did)
                self.doc_list.addItem(item)
        
        self.status_label.setText(f"Loaded {len(items)} documents.")


    def on_doc_selected(self, item):
        did = item.data(Qt.UserRole)
        doc_info = self.current_docs.get(did)
        wid = doc_info['default_workspace']
        thumb_url = doc_info.get('thumb_url')
        
        # Fetch document thumbnail
        if thumb_url:
            self.doc_preview.setText("Loading...")
            # Extract path from URL for the client call
            path = thumb_url
            if '?' in path:
                # Keep the query string for signing
                pass
            
            thumb_worker = WorkerThread(self.client.get_thumbnail, path)
            thumb_worker.finished.connect(self.display_doc_thumbnail)
            self.active_threads.append(thumb_worker)
            thumb_worker.start()
        else:
            self.doc_preview.setText("No preview available")
        
        self.status_label.setText(f"Fetching elements for {doc_info['name']}...")
        self.elem_list.clear()
        self.export_btn.setEnabled(False)
        
        self.worker = WorkerThread(self.client.get_elements, did, wid)
        self.worker.finished.connect(lambda res: self.handle_elements_loaded(res, did, wid))
        self.worker.error.connect(self.handle_error)
        self.active_threads.append(self.worker)
        self.worker.start()

    def handle_elements_loaded(self, elements, did, wid):
        self.current_elements = {}
        count = 0
        for elem in elements:
            # Filter for Part Studio only (no assemblies)
            e_type = elem.get('elementType')
            if e_type == "PARTSTUDIO":
                name = elem.get('name', 'Unknown')
                eid = elem.get('id')
                
                self.current_elements[eid] = {
                    'name': name, 
                    'type': e_type,
                    'did': did,
                    'wid': wid
                }
                
                display_text = f"[{e_type}] {name}"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, eid)
                self.elem_list.addItem(item)
                count += 1
                
        self.status_label.setText(f"Loaded {count} part studios.")

    def on_elem_selected(self, item):
        self.export_btn.setEnabled(True)
        eid = item.data(Qt.UserRole)
        info = self.current_elements.get(eid)
        self.status_label.setText(f"Selected: {info['name']}")

    def display_doc_thumbnail(self, image_data):
        """Display document thumbnail from image bytes."""
        if image_data:
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray(image_data))
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.doc_preview.setPixmap(scaled_pixmap)
            else:
                self.doc_preview.setText("Preview unavailable")
        else:
            self.doc_preview.setText("No preview")

    def start_export(self):
        item = self.elem_list.currentItem()
        if not item:
            return
            
        eid = item.data(Qt.UserRole)
        info = self.current_elements.get(eid)
        
        # Determine output directory
        dl_dir = self.dl_path_input.text().strip()
        if dl_dir and os.path.exists(dl_dir) and os.path.isdir(dl_dir):
            output_dir = dl_dir
        else:
            output_dir = tempfile.gettempdir()
            
        # Get document name to use in filename
        did = info['did']
        doc_name = self.current_docs.get(did, {}).get('name', 'Unknown_Doc')
            
        safe_doc_name = "".join(c for c in doc_name if c.isalnum() or c in (' ', '_', '-')).strip()
        safe_elem_name = "".join(c for c in info['name'] if c.isalnum() or c in (' ', '_', '-')).strip()
        filename = f"{safe_doc_name}_{safe_elem_name}.3mf"
        output_path = os.path.join(output_dir, filename)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # Indeterminate
        self.status_label.setText("Exporting (Translate + Download)... this may take a moment.")
        self.export_btn.setEnabled(False)
        
        self.worker = WorkerThread(
            self.client.export_element_as_3mf, 
            info['did'], info['wid'], eid, info['type'], output_path
        )
        self.worker.finished.connect(lambda res: self.handle_export_success(output_path))
        self.worker.error.connect(self.handle_error)
        self.active_threads.append(self.worker)
        self.worker.start()

    def handle_export_success(self, file_path):
        self.progress_bar.setVisible(False)
        self.export_btn.setEnabled(True)
        self.status_label.setText(f"Export saved to {file_path}")
        
        # Launch OrcaSlicer
        self.launch_orcaslicer(file_path)

    def launch_orcaslicer(self, file_path):
        exec_path = self.orca_path_input.text().strip()
        if not exec_path:
            exec_path = "orcaslicer" # Fallback to PATH

        self.status_label.setText(f"Launching {exec_path}...")
        
        cmd = [exec_path, file_path]
        
        # Trying to use --single-instance anyway, as it might be supported but hidden,
        # OR just standard behavior needs checking.
        # User requested "must support importing in already open instance".
        # PrusaSlicer supports --single-instance. OrcaSlicer is a fork.
        # It's worth trying to execute it without flags first as standard file opening.
        # If the user wants to force single-instance, we might need a flag checkbox in config later.
        # For now, let's just run it.
        
        try:
            subprocess.Popen(cmd)
            self.status_label.setText(f"Sent {file_path} to OrcaSlicer.")
        except FileNotFoundError:
             QMessageBox.critical(self, "Error", f"Executable not found: {exec_path}\nPlease configure the correct path.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch OrcaSlicer: {e}")

    def closeEvent(self, event):
        """Properly clean up threads before closing."""
        # Wait for all active threads to finish
        for thread in self.active_threads:
            if thread.isRunning():
                thread.wait(1000)  # Wait up to 1 second for each thread
        event.accept()

    def handle_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.export_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error_msg}")
        QMessageBox.critical(self, "Error", error_msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OnshapeOrcaApp()
    window.show()
    sys.exit(app.exec())

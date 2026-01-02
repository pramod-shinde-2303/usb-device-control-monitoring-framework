import customtkinter as ctk
import threading
import logging
import sys
import os
import ctypes
import json

from gui.dashboard import Dashboard
from core.usb_monitor import USBMonitor
from core.reporter import Reporter

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def load_config():
    config_path = os.path.join("config", "settings.json")
    default_config = {
        "settings": {
            "log_level": "INFO",
            "report_file": "reports/final_usb_audit_report.txt",
            "audit_log": "logs/usb_events.log",
             "file_log": "logs/file_activity.log"
        },
        "allowlist": {"allowed_devices": []},
        "blocklist": {"blocked_devices": []}
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults
                if "settings" in loaded:
                    default_config["settings"].update(loaded["settings"])
                return default_config
        except Exception as e:
            print(f"Error loading config: {e}")
            
    return default_config

def setup_logging(settings):
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = settings.get("audit_log", "logs/usb_events.log")
    level_str = settings.get("log_level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("USB Security Framework - Dashboard")
        self.geometry("900x600")
        
        # Set Icon
        try:
            self.iconbitmap("gui/logo.ico")
        except: pass
        
        # Backend Setup
        self.config = load_config()
        setup_logging(self.config["settings"])
        
        report_file = self.config["settings"].get("report_file", "reports/final_usb_audit_report.txt")
        self.reporter = Reporter(report_file)
        self.monitor = USBMonitor(self.config, self.reporter)
        
        # Start Backend Thread
        self.start_backend()

        # UI Layout
        self.dashboard = Dashboard(self, self.monitor)
        self.dashboard.pack(fill="both", expand=True)

        # Handle Close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_backend(self):
        logging.info("GUI: Starting Backend Monitor...")
        # Run monitor.start() (which spawns its own threads)
        # But monitor.start() just sets running=True and launches threads. 
        # We don't need a separate thread for start(), acts instantly.
        try:
            self.monitor.start()
        except Exception as e:
            logging.error(f"Failed to start backend: {e}")

    def on_close(self):
        logging.info("GUI: Closing application...")
        if self.monitor:
            self.monitor.stop()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    # Admin Check
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
             print("CRITICAL: Run as Administrator required.")
             # We can show a popup if we want, but console is fine for now since we launch via shell
    except: pass
    
    app = App()
    app.mainloop()

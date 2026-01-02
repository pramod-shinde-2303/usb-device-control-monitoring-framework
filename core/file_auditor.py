import os
import hashlib
import logging
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class FileAuditHandler(FileSystemEventHandler):
    def __init__(self, reporter):
        self.reporter = reporter

    def calculate_sha256(self, filepath):
        """Calculate SHA256 hash of a file with usage retries."""
        sha256_hash = hashlib.sha256()
        
        # Retry up to 3 times if file is locked (common during copy)
        for attempt in range(3):
            try:
                # Check if file exists and is accessible
                if not os.path.exists(filepath):
                    return "FILE_NOT_FOUND"
                
                # Read in chunks
                with open(filepath, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                return sha256_hash.hexdigest()
            except PermissionError:
                # File is likely locked by the writing process
                time.sleep(0.5)
            except Exception as e:
                return f"ERROR_HASHING: {str(e)}"
        
        return "Generic_Error_File_Locked"

    def log_activity(self, event_type, src_path, dest_path=None, is_directory=False):
        if is_directory:
            return # Optionally skip directories for hash calculation, just log existance

        file_size = 0
        file_hash = "N/A"
        
        target_file = src_path if event_type != "moved" else dest_path
        
        try:
            if event_type != "deleted" and os.path.exists(target_file) and not is_directory:
                file_size = os.path.getsize(target_file)
                file_hash = self.calculate_sha256(target_file)
        except:
            pass

        log_msg = f"Event: {event_type.upper()} | Path: {src_path}"
        if dest_path:
            log_msg += f" -> {dest_path}"
        log_msg += f" | Size: {file_size} bytes | Hash: {file_hash}"
        
        logging.getLogger("file_activity").info(log_msg)
        
        # Update reporter stats
        if event_type == "created":
            self.reporter.update_stat("files_copied")
            # Simple check for large file transfer (e.g., > 100MB)
            if file_size > 100 * 1024 * 1024:
                 logging.getLogger("alerts").warning(f"LARGE FILE TRANSFER DETECTED: {target_file} ({file_size} bytes)")
                 self.reporter.update_stat("suspicious_activities")
                 
        elif event_type == "deleted":
            self.reporter.update_stat("files_deleted")
        elif event_type == "modified":
            self.reporter.update_stat("files_modified")
        elif event_type == "moved":
            self.reporter.update_stat("files_copied") # Treated as copy/move

    def on_created(self, event):
        # print(f"DEBUG: Watchdog CREATED {event.src_path}")
        self.log_activity("created", event.src_path, is_directory=event.is_directory)

    def on_deleted(self, event):
        # print(f"DEBUG: Watchdog DELETED {event.src_path}")
        self.log_activity("deleted", event.src_path, is_directory=event.is_directory)

    def on_modified(self, event):
        # Modified can be noisy, but let's enable it for debug
        # print(f"DEBUG: Watchdog MODIFIED {event.src_path}")
        if not event.is_directory:
            self.log_activity("modified", event.src_path, is_directory=False)

    def on_moved(self, event):
        # print(f"DEBUG: Watchdog MOVED {event.src_path}")
        self.log_activity("moved", event.src_path, event.dest_path, is_directory=event.is_directory)

class FileAuditor:
    def __init__(self, reporter):
        self.observers = {}
        self.reporter = reporter

    def start_auditing(self, drive_letter):
        if drive_letter in self.observers:
            logging.info(f"Already auditing {drive_letter}")
            return

        logging.info(f"Starting file audit on {drive_letter}")
        event_handler = FileAuditHandler(self.reporter)
        observer = Observer()
        # Verify path exists
        path = f"{drive_letter}\\"
        if not os.path.exists(path):
            logging.error(f"Cannot start auditing: Path {path} does not exist.")
            return

        observer.schedule(event_handler, path, recursive=True)
        observer.start()
        self.observers[drive_letter] = observer

    def stop_auditing(self, drive_letter):
        if drive_letter in self.observers:
            logging.info(f"Stopping file audit on {drive_letter}")
            observer = self.observers[drive_letter]
            observer.stop()
            observer.join(timeout=1) # Don't block forever if thread is stuck
            if observer.is_alive():
                 logging.warning(f"Watchdog observer for {drive_letter} did not stop gracefully.")
            del self.observers[drive_letter]
    
    def stop_all(self):
        for drive in list(self.observers.keys()):
            self.stop_auditing(drive)

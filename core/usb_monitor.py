import wmi
import logging
import time
import threading
import json
import os
import pythoncom
import win32com.client
from .device_identifier import DeviceIdentifier
from .usb_blocker import USBBlocker
from .file_auditor import FileAuditor
from .reporter import Reporter

from .disk_io_monitor import DiskIOMonitor

class USBMonitor:
    def __init__(self, config, reporter):
        # self.wmi_client removed to prevent cross-thread usage errors
        self.config = config
        self.reporter = reporter
        self.file_auditor = FileAuditor(reporter)
        self.disk_io_monitor = DiskIOMonitor(reporter)
        self.monitoring = False
        self.stop_event = threading.Event()
        self.monitor_thread = None
        self.active_drives = {} # drive_letter -> device_info

    def resolve_device_id_from_drive(self, drive_letter):
        """
        Resolves a drive letter (e.g., 'E:') to a PNP Device ID.
        """
        try:
            # Create local WMI client for this thread
            c = wmi.WMI()
            
            # Clean drive letter
            drive_letter = drive_letter.rstrip('\\')
            
            # 1. Get LogicalDisk
            logical_disks = c.query(f"SELECT * FROM Win32_LogicalDisk WHERE DeviceID='{drive_letter}'")
            if not logical_disks:
                return None
            
            disk = logical_disks[0]
            # Check if Removable (2)
            if disk.DriveType != 2:
                logging.debug(f"Drive {drive_letter} is not removable (Type: {disk.DriveType}). Ignoring.")
                return None

            # 2. Map via Partitions
            # This chain is complex in WMI. 
            # Win32_LogicalDisk -> Win32_LogicalDiskToPartition -> Win32_DiskPartition -> Win32_DiskDriveToDiskPartition -> Win32_DiskDrive
            
            query = f'ASSOCIATORS OF {{Win32_LogicalDisk.DeviceID="{drive_letter}"}} WHERE AssocClass = Win32_LogicalDiskToPartition'
            partitions = c.query(query)
            
            if not partitions:
                return None
            
            for partition in partitions:
                query_drive = f'ASSOCIATORS OF {{Win32_DiskPartition.DeviceID="{partition.DeviceID}"}} WHERE AssocClass = Win32_DiskDriveToDiskPartition'
                drives = c.query(query_drive)
                
                for drive in drives:
                    # We found the physical disk
                    if "USB" in drive.InterfaceType or "USB" in drive.PNPDeviceID:
                        return drive.PNPDeviceID
                        
            return None

        except Exception as e:
            logging.error(f"Error resolving device for {drive_letter}: {e}")
            return None

    def get_full_device_details(self, pnp_device_id):
        try:
            c = wmi.WMI()
            # Query Win32_PnPEntity for details
            # Escape backslashes for WQL
            wql_id = pnp_device_id.replace("\\", "\\\\")
            entities = c.query(f"SELECT * FROM Win32_PnPEntity WHERE DeviceID='{wql_id}'")
            if entities:
                ent = entities[0]
                return {
                    "DeviceID": ent.DeviceID,
                    "Name": ent.Name,
                    "Description": ent.Description,
                    "Service": ent.Service,
                     # Parse IDs
                    **DeviceIdentifier.parse_device_id(ent.DeviceID)
                }
        except Exception as e:
            logging.error(f"Error fetching details for {pnp_device_id}: {e}")
        
        return DeviceIdentifier.parse_device_id(pnp_device_id)

    def is_allowed(self, fingerprint):
        # Reload config from disk to ensure we have latest GUI updates
        try:
             import os, json
             # Reload Allowlist
             allow_path = os.path.join("config", "allowlist.json")
             if os.path.exists(allow_path):
                 with open(allow_path, "r") as f:
                     self.config["allowlist"] = json.load(f)
             
             # Reload Blocklist
             block_path = os.path.join("config", "blocklist.json")
             if os.path.exists(block_path):
                 with open(block_path, "r") as f:
                     self.config["blocklist"] = json.load(f)
        except Exception as e:
            logging.error(f"Error reloading config in is_allowed: {e}")

        # Check against allowlist
        allowed_list = self.config.get("allowlist", {}).get("allowed_devices", [])
        blocked_list = self.config.get("blocklist", {}).get("blocked_devices", [])
        
        serial = fingerprint.get("serial_number")

        # 1. Explicitly Blocked?
        for dev in blocked_list:
            if dev.get("serial_number") == serial:
                return False, "BLOCKED_BY_POLICY"

        # 2. Explicitly Allowed?
        for dev in allowed_list:
            if dev.get("serial_number") == serial:
                return True, "ALLOWED"

        # 3. Default Policy (Block Unknown)
        return False, "UNKNOWN_DEVICE"

    def update_blocklist(self, fingerprint):
        """
        Adds the given device fingerprint to the blocklist.json file if not already present.
        """
        self.block_device_manual(fingerprint)

    def _clean_fingerprint(self, fp):
        return {
            "vendor_id": fp.get("vendor_id"),
            "product_id": fp.get("product_id"),
            "serial_number": fp.get("serial_number"),
            "device_name": fp.get("device_name"),
            "device_id": fp.get("device_id") or fp.get("pnp_id")
        }

    def block_device_manual(self, fingerprint):
        try:
            clean_fp = self._clean_fingerprint(fingerprint)
            
            # 1. Add to Blocklist
            blocklist_path = os.path.join("config", "blocklist.json")
            data = {"blocked_devices": []}
            if os.path.exists(blocklist_path):
                with open(blocklist_path, "r") as f:
                     try: data = json.load(f)
                     except: pass
            
            exists = False
            for dev in data["blocked_devices"]:
                if dev.get("serial_number") == clean_fp.get("serial_number"):
                    exists = True; break
            
            if not exists:
                data["blocked_devices"].append(clean_fp)
                with open(blocklist_path, "w") as f: json.dump(data, f, indent=4)
                logging.info(f"Added to blocklist: {clean_fp.get('serial_number')}")

            # 2. Remove from Allowlist
            allowlist_path = os.path.join("config", "allowlist.json")
            if os.path.exists(allowlist_path):
                with open(allowlist_path, "r") as f:
                    adata = json.load(f)
                
                new_allowed = [d for d in adata.get("allowed_devices", []) 
                               if d.get("serial_number") != clean_fp.get("serial_number")]
                
                if len(new_allowed) != len(adata.get("allowed_devices", [])):
                    adata["allowed_devices"] = new_allowed
                    with open(allowlist_path, "w") as f: json.dump(adata, f, indent=4)
                    logging.info(f"Removed from allowlist: {clean_fp.get('serial_number')}")

        except Exception as e:
            logging.error(f"Failed to update config (Block): {e}")

    def allow_device(self, fingerprint):
        try:
            clean_fp = self._clean_fingerprint(fingerprint)
            
            # 1. Add to Allowlist
            allowlist_path = os.path.join("config", "allowlist.json")
            data = {"allowed_devices": []}
            if os.path.exists(allowlist_path):
                with open(allowlist_path, "r") as f:
                     try: data = json.load(f)
                     except: pass
            
            exists = False
            for dev in data["allowed_devices"]:
                if dev.get("serial_number") == clean_fp.get("serial_number"):
                    exists = True; break
            
            if not exists:
                data["allowed_devices"].append(clean_fp)
                with open(allowlist_path, "w") as f: json.dump(data, f, indent=4)
                logging.info(f"Added to allowlist: {clean_fp.get('serial_number')}")

            # 2. Remove from Blocklist
            blocklist_path = os.path.join("config", "blocklist.json")
            if os.path.exists(blocklist_path):
                with open(blocklist_path, "r") as f:
                    bdata = json.load(f)
                
                new_blocked = [d for d in bdata.get("blocked_devices", []) 
                               if d.get("serial_number") != clean_fp.get("serial_number")]
                               
                if len(new_blocked) != len(bdata.get("blocked_devices", [])):
                    bdata["blocked_devices"] = new_blocked
                    with open(blocklist_path, "w") as f: json.dump(bdata, f, indent=4)
                    logging.info(f"Removed from blocklist: {clean_fp.get('serial_number')}")

        except Exception as e:
            logging.error(f"Failed to update config (Allow): {e}")

    def handle_insertion(self, drive_letter):
        logging.info(f"USB Storage Detected on {drive_letter}")
        
        # Give Windows a moment to stabilize the mount
        time.sleep(1)
        
        pnp_id = self.resolve_device_id_from_drive(drive_letter)
        
        if not pnp_id:
            logging.warning(f"Could not resolve PnP ID for {drive_letter}. Might not be a USB mass storage.")
            return

        device_info = self.get_full_device_details(pnp_id)
        fingerprint = DeviceIdentifier.get_device_fingerprint(device_info)
        
        logging.getLogger("usb_events").info(f"INSERTION | Drive: {drive_letter} | Device: {fingerprint}")
        self.reporter.update_stat("total_connections")

        allowed, reason = self.is_allowed(fingerprint)
        
        if not allowed:
            logging.getLogger("alerts").warning(f"UNAUTHORIZED DEVICE DETECTED: {fingerprint} | Reason: {reason}")
            logging.info(f"Blocking device {drive_letter} ({pnp_id})...")
            
            success = USBBlocker.block_device(pnp_id)
            if success:
                self.reporter.update_stat("blocked_devices")
                self.reporter.update_stat("unauthorized_attempts")
                logging.getLogger("usb_events").info(f"BLOCK | Device {pnp_id} was blocked.")
                
                # Auto-add to blocklist for future reference
                self.update_blocklist(fingerprint)
            else:
                 logging.error(f"Failed to block device {pnp_id}")
        else:
            logging.info(f"Device Allowed: {fingerprint}")
            self.active_drives[drive_letter] = fingerprint
            self.file_auditor.start_auditing(drive_letter)
            self.disk_io_monitor.start_monitoring(drive_letter)

    def handle_removal(self, drive_letter):
        logging.info(f"USB Removed: {drive_letter}")
        logging.getLogger("usb_events").info(f"REMOVAL | Drive: {drive_letter}")
        
        try:
            if drive_letter in self.active_drives:
                del self.active_drives[drive_letter]
        except: pass
            
        try:
            self.file_auditor.stop_auditing(drive_letter)
        except Exception as e:
            logging.error(f"Error stopping file audit: {e}")
        finally:
            # Ensure IO monitor is stopped regardless of file auditor issues
            self.disk_io_monitor.stop_monitoring(drive_letter)


    def monitor_loop(self):
        logging.info("Starting USB Monitor Loop (Direct COM)...")
        
        import pythoncom
        import win32com.client
        
        # Initialize COM for this thread
        pythoncom.CoInitialize()
        
        try:
            # Connect to WMI directly via win32com
            objWMIService = win32com.client.Dispatch("WbemScripting.SWbemLocator")
            objSWbemServices = objWMIService.ConnectServer(".", r"root\cimv2")
            
            # Create the event watcher
            # usage: ExecNotificationQuery(Query, [Flags=0], [Context=None])
            watcher = objSWbemServices.ExecNotificationQuery("SELECT * FROM Win32_VolumeChangeEvent")
            
            while self.monitoring:
                try:
                    # NextEvent(Timeout_ms)
                    event = watcher.NextEvent(1000)
                    
                    # EventType: 2 (Insert), 3 (Remove)
                    # DriveName: "E:"
                    e_type = event.EventType
                    drive_name = event.DriveName
                    
                    if e_type == 2:
                        self.handle_insertion(drive_name)
                    elif e_type == 3:
                        self.handle_removal(drive_name)
                        
                except Exception as e:
                    # Check for timeout error (0x_something ending in 40960 or similar, but just catching any)
                    # -2147209215 is "Timed out"
                    if "Timed out" in str(e) or "-2147209215" in str(e):
                        continue
                        
                    if self.monitoring:
                        logging.error(f"Error in monitor loop: {e}")
                        time.sleep(1)
                        
        except Exception as e:
             logging.error(f"Fatal COM Error in thread: {e}")
        finally:
            pythoncom.CoUninitialize()

    def get_all_attached_devices(self):
        """
        Returns a list of all physically attached USB storage devices,
        regardless of whether they are enabled (mounted) or disabled (blocked).
        """
        attached = []
        try:
            # Create local WMI client (thread-safe)
            import wmi
            c = wmi.WMI()
            
            # Query all USB Storage devices (Service='USBSTOR')
            # This catches devices even if the driver is disabled (Blocked)
            entities = c.query("SELECT * FROM Win32_PnPEntity WHERE Service='USBSTOR'")
            
            for ent in entities:
                 # Parse details
                 try:
                     details = DeviceIdentifier.parse_device_id(ent.DeviceID)
                     details["status_raw"] = ent.Status # OK, Error, Degraded
                     details["device_id"] = ent.DeviceID
                     details["description"] = ent.Description
                     details["name"] = ent.Name
                     attached.append(details)
                 except: continue
                 
        except Exception as e:
            logging.error(f"Error scanning attached devices: {e}")
            
        return attached

    def scan_existing_drives(self):
        """
        Scans for USB devices that are already connected at startup.
        """
        logging.info("Scanning for existing USB devices...")
        import pythoncom
        pythoncom.CoInitialize()
        try:
            c = wmi.WMI()
            # Find all removable drives (Type 2)
            drives = c.query("SELECT * FROM Win32_LogicalDisk WHERE DriveType=2")
            for drive in drives:
                logging.info(f"Found existing drive: {drive.DeviceID}")
                self.handle_insertion(drive.DeviceID)
        except Exception as e:
            logging.error(f"Error during initial scan: {e}")
        finally:
            pythoncom.CoUninitialize()

    def start(self):
        if self.monitoring:
             logging.warning("Monitor already running.")
             return

        self.monitoring = True
        self.stop_event.clear()
        
        # Initial Scan
        try:
             self.scan_existing_drives()
        except Exception as e:
             logging.error(f"Scan failed: {e}")
        
        # Start Threads
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        # Start Disk IO Monitor
        if self.disk_io_monitor:
            self.disk_io_monitor.start()

    def stop(self):
        logging.info("Stopping USB Monitor...")
        self.monitoring = False
        self.stop_event.set()
        
        if self.monitor_thread:
            # We can't interrupt wmi easily, but wait briefly
            self.monitor_thread.join(timeout=2)
            self.monitor_thread = None
            
        # Stop File Auditors
        if self.file_auditor:
            self.file_auditor.stop_all()
            
        # Stop Disk IO Monitor
        if self.disk_io_monitor:
            self.disk_io_monitor.stop()

import psutil
import time
import logging
import threading
import wmi

class DiskIOMonitor:
    def __init__(self, reporter):
        self.reporter = reporter
        self.monitored_drives = {} # drive_letter -> { 'physical_drive': 'PhysicalDriveX', 'last_read': 0, 'last_write': 0 }
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

    def get_physical_drive_mapping(self, drive_letter):
        """
        Maps a drive letter (G:) to PhysicalDriveN using WMI.
        """
        try:
            c = wmi.WMI()
            # Win32_LogicalDiskToPartition matches LogicalDisk (G:) to DiskPartition
            drive_clean = drive_letter.rstrip('\\')
            query = f'ASSOCIATORS OF {{Win32_LogicalDisk.DeviceID="{drive_clean}"}} WHERE AssocClass = Win32_LogicalDiskToPartition'
            partitions = c.query(query)
            
            for part in partitions:
                # Partition DeviceID is like "Disk #1, Partition #0"
                # We need the Disk Index #1
                # Win32_DiskDriveToDiskPartition matches Partition to DiskDrive
                query_drive = f'ASSOCIATORS OF {{Win32_DiskPartition.DeviceID="{part.DeviceID}"}} WHERE AssocClass = Win32_DiskDriveToDiskPartition'
                drives = c.query(query_drive)
                for drive in drives:
                     # drive.DeviceID is usually "\\.\PHYSICALDRIVE1"
                     # psutil uses "PhysicalDrive1" (Case sensitive? No, usually Title Case)
                     # Let's clean it.
                     raw_id = drive.DeviceID # \\.\PHYSICALDRIVE1
                     if "PHYSICALDRIVE" in raw_id.upper():
                         index = raw_id.upper().split("PHYSICALDRIVE")[1]
                         return f"PhysicalDrive{index}"
            return None
        except Exception as e:
            logging.error(f"Error mapping {drive_letter} to physical drive: {e}")
            return None

    def start_monitoring(self, drive_letter):
        phy_drive = self.get_physical_drive_mapping(drive_letter)
        if not phy_drive:
            logging.warning(f"Could not map {drive_letter} to physical drive for IO monitoring.")
            return

        logging.info(f"Mapping {drive_letter} -> {phy_drive} for IO Stats")
        
        with self.lock:
            # Initialize baseline
            io = psutil.disk_io_counters(perdisk=True).get(phy_drive)
            if io:
                self.monitored_drives[drive_letter] = {
                    'physical_drive': phy_drive,
                    'last_read': io.read_bytes,
                    'last_write': io.write_bytes
                }
    
    def stop_monitoring(self, drive_letter):
        with self.lock:
            if drive_letter in self.monitored_drives:
                del self.monitored_drives[drive_letter]

    def find_open_files_on_drive(self, drive_letter):
        """
        Scans likely file-transfer processes to find open file handles on the given drive.
        Optimized: Only checks Explorer, Terminals, and common tools to avoid performance hit.
        """
        procs_with_handle = {}
        # Only scan apps likely to be copying files (User UI)
        TARGET_APPS = ['explorer.exe', 'cmd.exe', 'powershell.exe', 'robocopy.exe', 'xcopy.exe', 'totalcmd.exe', 'python.exe']
        
        try:
            # Filter by name upfront to save time
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() not in TARGET_APPS:
                        continue
                    
                    # Manually fetch open files safely
                    try:
                        flist = proc.open_files()
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        continue
                    
                    if not flist: continue

                    files_on_usb = []
                    for f in flist:
                        if f.path and f.path.lower().startswith(drive_letter.lower()):
                            files_on_usb.append(f.path)
                    
                    if files_on_usb:
                        procs_with_handle[proc.info['pid']] = {
                             'name': proc.info['name'],
                             'files': files_on_usb,
                             'obj': proc 
                        }
                except Exception:
                    continue
        except Exception as e:
            pass # logging.error(f"Scan Error: {e}")
        return procs_with_handle

    def find_destination_candidates(self, procs_data, usb_drive):
        """
        Given processes reading from USB, check if they are writing to C:/D.
        Returns a string of possible destinations.
        """
        destinations = []
        for pid, data in procs_data.items():
            proc = data['obj']
            try:
                # Re-check open files for THIS process only
                # We want files NOT on USB drive
                for f in proc.open_files():
                    if not f.path.lower().startswith(usb_drive.lower()):
                        # Heuristic: Valid destination usually on C: or D:
                        if f.path[0].upper() in ['C', 'D', 'E']: 
                             # Exclude system noise (dlls, prefetch, logs)
                             ignored = ['.dll', '.nls', '.log', '.dat', '.ini', 'appdata', 'windows']
                             if not any(x in f.path.lower() for x in ignored):
                                 destinations.append(f.path)
            except: pass
        
        return list(set(destinations))

    def monitor_loop(self):
        logging.info("Starting Disk IO Monitor Loop...")
        while self.running:
            try:
                io_counters = psutil.disk_io_counters(perdisk=True)
                
                with self.lock:
                    for drive_letter, data in list(self.monitored_drives.items()):
                        phy_drive = data['physical_drive']
                        if phy_drive in io_counters:
                            current = io_counters[phy_drive]
                            
                            # Delta
                            delta_read = current.read_bytes - data['last_read']
                            if delta_read > 0:
                                pass # print(f"DEBUG: Read Delta: {delta_read} bytes")
                            
                            # Threshold: 4KB read (Cluster size typical)
                            if delta_read > 4096:
                                mb_read = delta_read / (1024 * 1024)
                                
                                # Attempt to find WHICH file is being read
                                # Burst check: Check 10 times over 1 second to catch the handle
                                files_read = []
                                dest_candidates = []
                                
                                # print(f"DEBUG: Triggering Burst Check for {delta_read} bytes...")
                                
                                for i in range(10):
                                    found_procs = self.find_open_files_on_drive(drive_letter)
                                    if found_procs:
                                        for pid, pdata in found_procs.items():
                                            files_read.extend(pdata['files'])
                                            
                                        # Check for destination
                                        dests = self.find_destination_candidates(found_procs, drive_letter)
                                        if dests: dest_candidates.extend(dests)
                                        
                                        # If we found both, likely good to go, but keep scanning a bit to be sure
                                        if files_read and dest_candidates: break
                                    
                                    time.sleep(0.1)
                                
                                file_info_str = ""
                                if files_read:
                                    files_read = list(set(files_read))
                                    file_info_str += f" | File(s): {', '.join(files_read)}"
                                else:
                                    file_info_str += " | File: Unknown"

                                if dest_candidates:
                                    dest_candidates = list(set(dest_candidates))
                                    # Limit output length
                                    if len(dest_candidates) > 3: dest_candidates = dest_candidates[:3] + ["..."]
                                    file_info_str += f" | Possible Dest: {', '.join(dest_candidates)}"

                                # print(f"DEBUG: Final Log -> {file_info_str}")

                                # Log activity
                                logging.getLogger("file_activity").info(f"DATA TRANSFER | {drive_letter} -> System | Amount: {mb_read:.6f} MB ({delta_read} bytes){file_info_str}")
                                
                                # Only flag as suspicious if > 10MB
                                if delta_read > 10 * 1024 * 1024:
                                     self.reporter.update_stat("suspicious_activities")
                            
                            # Update baseline
                            data['last_read'] = current.read_bytes
                            data['last_write'] = current.write_bytes
                            
            except Exception as e:
                logging.error(f"IO Monitor Error: {e}")
                # import traceback
                # traceback.print_exc()
            
            time.sleep(0.5) # Poll faster to catch short transfers

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.monitor_loop)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

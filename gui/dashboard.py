import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import logging
import os

class Dashboard(ctk.CTkFrame):
    def __init__(self, master, monitor):
        super().__init__(master)
        self.monitor = monitor
        
        # Configure grid expansion
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Tab View
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        self.tab_devices = self.tab_view.add("USB Devices")
        self.tab_logs = self.tab_view.add("Live Logs")
        self.tab_files = self.tab_view.add("File Activity")
        self.tab_controls = self.tab_view.add("Controls")

        self.setup_devices_tab()
        self.setup_logs_tab()
        self.setup_files_tab()
        self.setup_controls_tab()
        
        # Start Polling
        self.start_log_polling()

    def setup_devices_tab(self):
        # Configure Grid
        self.tab_devices.columnconfigure(0, weight=1)
        self.tab_devices.rowconfigure(1, weight=1)
        
        # Header
        header = ctk.CTkLabel(self.tab_devices, text="Connected USB Mass Storage Devices", font=ctk.CTkFont(size=18, weight="bold"))
        header.grid(row=0, column=0, padx=20, pady=10, sticky="w")
        
        # Scrollable Device List
        self.device_list_frame = ctk.CTkScrollableFrame(self.tab_devices, label_text="Devices")
        self.device_list_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.device_list_frame.columnconfigure(0, weight=1)
        
        # Refresh Button
        refresh_btn = ctk.CTkButton(self.tab_devices, text="Refresh List", command=self.refresh_devices_ui)
        refresh_btn.grid(row=2, column=0, padx=20, pady=10, sticky="e")

    def setup_logs_tab(self):
        self.tab_logs.columnconfigure(0, weight=1)
        self.tab_logs.rowconfigure(0, weight=1)
        
        # wrap="none" to prevent ugly breaking. 
        self.log_textbox = ctk.CTkTextbox(self.tab_logs, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.log_textbox.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        # Configure tags for basic coloring
        # Note: CTkTextbox uses underlying tkinter Text widget for tags
        self.log_textbox.tag_config("INFO", foreground="white")
        self.log_textbox.tag_config("WARNING", foreground="orange")
        self.log_textbox.tag_config("ERROR", foreground="#FF5555")
        
        # Read initial logs
        self.last_log_pos = 0
        self.current_log_file = os.path.join("logs", "usb_events.log")

    def setup_files_tab(self):
        self.tab_files.columnconfigure(0, weight=1)
        self.tab_files.rowconfigure(0, weight=1)
        
        self.file_log_textbox = ctk.CTkTextbox(self.tab_files, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.file_log_textbox.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        self.file_log_textbox.tag_config("INFO", foreground="white")
        self.file_log_textbox.tag_config("WARNING", foreground="orange")
        self.file_log_textbox.tag_config("ERROR", foreground="#FF5555")
        
        self.last_file_log_pos = 0
        self.current_file_log = os.path.join("logs", "file_activity.log")

    def _append_colored_logs(self, textbox, new_text):
        if not new_text: return
        
        # We need to unlock state if it was disabled (default is normal though)
        # Split lines to apply tags per line
        lines = new_text.splitlines()
        for line in lines:
            tag = "INFO"
            if "WARNING" in line: tag = "WARNING"
            elif "ERROR" in line or "CRITICAL" in line: tag = "ERROR"
            
            textbox.insert("end", line + "\n", tag)
            
        textbox.see("end")

    def update_logs(self):
        # Poll log files
        try:
            # 1. USB Events
            if os.path.exists(self.current_log_file):
                with open(self.current_log_file, "r") as f:
                    f.seek(self.last_log_pos)
                    new_lines = f.read()
                    if new_lines:
                        self.last_log_pos = f.tell()
                        self._append_colored_logs(self.log_textbox, new_lines)
            
            # 2. File Activity
            if os.path.exists(self.current_file_log):
                with open(self.current_file_log, "r") as f:
                    f.seek(self.last_file_log_pos)
                    new_lines = f.read()
                    if new_lines:
                        self.last_file_log_pos = f.tell()
                        self._append_colored_logs(self.file_log_textbox, new_lines)
                        
        except Exception as e:
            pass
            
    def start_log_polling(self):
        self.refresh_devices_ui()
        self.update_logs()
        self.after(2000, self.start_log_polling) # Poll every 2s

    def setup_controls_tab(self):
        self.tab_controls.columnconfigure(0, weight=1)
        
        # Status
        self.status_label = ctk.CTkLabel(self.tab_controls, text="Monitoring Active", text_color="green", font=("Arial", 20, "bold"))
        self.status_label.grid(row=0, column=0, padx=20, pady=40)
        
        # Buttons Frame
        btn_frame = ctk.CTkFrame(self.tab_controls)
        btn_frame.grid(row=1, column=0, padx=20, pady=20)
        
        self.btn_start = ctk.CTkButton(btn_frame, text="Start Monitoring", command=self.start_monitoring, state="disabled")
        self.btn_start.grid(row=0, column=0, padx=10, pady=10)
        
        self.btn_stop = ctk.CTkButton(btn_frame, text="Stop Monitoring", command=self.stop_monitoring, fg_color="red", hover_color="darkred")
        self.btn_stop.grid(row=0, column=1, padx=10, pady=10)
        
        btn_report = ctk.CTkButton(self.tab_controls, text="Generate Audit Report", command=self.generate_report)
        btn_report.grid(row=2, column=0, padx=20, pady=20)

    # --- Actions ---
    def start_monitoring(self):
        if self.master.monitor:
             self.master.monitor.start()
             self.status_label.configure(text="Monitoring Active", text_color="green")
             self.btn_start.configure(state="disabled")
             self.btn_stop.configure(state="normal")

    def stop_monitoring(self):
        if self.master.monitor:
            self.master.monitor.stop()
            self.status_label.configure(text="Monitoring Stopped", text_color="red")
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")

    def generate_report(self):
        if self.master.monitor:
            if self.master.monitor.reporter.generate_report():
                # OS.startfile requires valid path, absolute is safest
                report_path = os.path.abspath(self.master.monitor.reporter.report_path)
                try:
                    os.startfile(report_path)
                    tk.messagebox.showinfo("Report", f"Audit Report Generated & Opened:\n{report_path}")
                except Exception as e:
                    tk.messagebox.showinfo("Report", f"Audit Report Generated:\n{report_path}\n(Could not auto-open: {e})")
            else:
                tk.messagebox.showerror("Error", "Failed to generate report.")

    def block_device_action(self, info):
        pnp_id = info.get('pnp_id')
        if not pnp_id: return
        from core.usb_blocker import USBBlocker
        
        # Block via Backend
        if USBBlocker.block_device(pnp_id):
             tk.messagebox.showinfo("Success", f"Device {pnp_id} Blocked.")
             self.master.monitor.block_device_manual(info)
             self.refresh_devices_ui()
        else:
             tk.messagebox.showerror("Error", "Failed to block device. Check logs.")

    def unblock_device_action(self, info):
        pnp_id = info.get('pnp_id')
        if not pnp_id: return
        from core.usb_blocker import USBBlocker
        
        # 1. Update allowlist & Remove from blocklist FIRST
        # This prevents the monitor loop from auto-blocking it again immediately after we enable the driver
        self.master.monitor.allow_device(info)
        
        # 2. Unblock via Backend (Enable Hardware)
        if USBBlocker.unblock_device(pnp_id):
             tk.messagebox.showinfo("Success", f"Device Unblocked.\n\nIt is now Allowed.")
             self.refresh_devices_ui()
        else:
             tk.messagebox.showerror("Error", "Failed to unblock device driver.")

    def refresh_devices_ui(self):
        # Clear existing
        try:
            for widget in self.device_list_frame.winfo_children():
                widget.destroy()
        except: pass
            
        # Get data sources
        if not self.monitor: return

        # 1. Active (Mounted) Drives
        active_drives = self.monitor.active_drives.copy()
        
        # 2. Blocklist
        blocked_data = []
        try:
             import json
             with open(os.path.join("config", "blocklist.json"), "r") as f:
                 blocked_data = json.load(f).get("blocked_devices", [])
        except: pass

        # 3. Allowlist
        allowed_data = []
        try:
             with open(os.path.join("config", "allowlist.json"), "r") as f:
                 allowed_data = json.load(f).get("allowed_devices", [])
        except: pass

        # 4. Physically Attached Devices
        attached_devices = self.monitor.get_all_attached_devices()
        attached_serials = set(d['serial_number'] for d in attached_devices if d.get('serial_number'))

        devices = []
        processed_serials = set()

        # Combine Sources
        
        # A. Blocked Devices
        for b in blocked_data:
            serial = b.get('serial_number')
            if not serial: continue
            
            processed_serials.add(serial)
            is_online = serial in attached_serials
            
            b['status_ui'] = "Blocked (Online)" if is_online else "Blocked (Offline)"
            b['color'] = "red"
            b['drive'] = 'N/A'
            b['pnp_id'] = b.get('device_id')
            b['is_blocked'] = True
            devices.append(b)
            
        # B. Active Drives (Allowed & Online)
        for drive, info in active_drives.items():
            serial = info.get('serial_number')
            if serial: 
                if serial in processed_serials: continue
                processed_serials.add(serial)
            
            info['status_ui'] = "Allowed (Online)"
            info['color'] = "green"
            info['drive'] = drive
            info['pnp_id'] = info.get('device_id')
            info['is_blocked'] = False
            devices.append(info)
            
        # C. Allowlist (Allowed & Offline)
        for a in allowed_data:
            serial = a.get('serial_number')
            if not serial: continue
            if serial in processed_serials: continue # Already handled (either Active or Blocked)
            
            # If it's here, it's not active, and not blocked.
            # Check if it's attached but maybe not mounted? Unlikely if not in Active, but possible.
            # Usually implies disconnected.
            is_online = serial in attached_serials
            
            status_str = "Allowed (Online)" if is_online else "Allowed (Offline)"
            
            a['status_ui'] = status_str
            a['color'] = "green" if is_online else "gray" # Gray for offline allowed
            a['drive'] = 'N/A'
            a['pnp_id'] = a.get('device_id')
            a['is_blocked'] = False
            devices.append(a)

        if not devices:
            try:
                lbl = ctk.CTkLabel(self.device_list_frame, text="No USB Devices Found", text_color="gray")
                lbl.pack(pady=10)
            except: pass
            return

        # Render Cards
        for info in devices:
            try:
                card = ctk.CTkFrame(self.device_list_frame, fg_color="#2b2b2b", corner_radius=10)
                card.pack(fill="x", padx=10, pady=5)
                
                # Left Info
                info_frame = ctk.CTkFrame(card, fg_color="transparent")
                info_frame.pack(side="left", padx=10, pady=10)
                
                name = info.get('device_name', 'Unknown Device')
                ctk.CTkLabel(info_frame, text=name, font=("Arial", 14, "bold")).pack(anchor="w")
                
                sub_text = f"Serial: {info.get('serial_number')}"
                if info.get('drive') != 'N/A':
                    sub_text += f" | Drive: {info.get('drive')}"
                ctk.CTkLabel(info_frame, text=sub_text, font=("Arial", 11)).pack(anchor="w")
                
                status_ui = info.get('status_ui', 'Unknown')
                color = info.get('color', 'gray')
                
                status_text = f"Status: {status_ui}"
                ctk.CTkLabel(info_frame, text=status_text, text_color=color, font=("Arial", 12, "bold")).pack(anchor="w", pady=(5,0))

                # Right Controls
                ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
                ctrl_frame.pack(side="right", padx=10)
                
                if info.get('is_blocked'):
                    ctk.CTkButton(ctrl_frame, text="Unblock", width=80, fg_color="green", hover_color="darkgreen",
                                  command=lambda i=info: self.unblock_device_action(i)).pack()
                else:
                    ctk.CTkButton(ctrl_frame, text="Block", width=80, fg_color="darkred", hover_color="red",
                                  command=lambda i=info: self.block_device_action(i)).pack()
            except Exception as e:
                logging.error(f"Error rendering device card: {e}")

    def update_logs(self):
        # Poll log files
        try:
            # 1. USB Events
            if os.path.exists(self.current_log_file):
                with open(self.current_log_file, "r") as f:
                    f.seek(self.last_log_pos)
                    new_lines = f.read()
                    if new_lines:
                        self.last_log_pos = f.tell()
                        self.log_textbox.insert("end", new_lines)
                        self.log_textbox.see("end")
            
            # 2. File Activity
            if os.path.exists(self.current_file_log):
                with open(self.current_file_log, "r") as f:
                    f.seek(self.last_file_log_pos)
                    new_lines = f.read()
                    if new_lines:
                        self.last_file_log_pos = f.tell()
                        self.file_log_textbox.insert("end", new_lines)
                        self.file_log_textbox.see("end")
                        
        except Exception as e:
            pass

    def start_log_polling(self):
        self.refresh_devices_ui()
        self.update_logs()
        self.after(2000, self.start_log_polling) # Poll every 2s

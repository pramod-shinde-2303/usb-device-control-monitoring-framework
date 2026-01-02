import logging

class DeviceIdentifier:
    """
    Responsible for generating unique device fingerprints for USB devices.
    """

    @staticmethod
    def get_device_fingerprint(device_info):
        """
        Generates a dictionary fingerprint from the device info.
        
        Args:
            device_info (dict): Dictionary containing raw device data.
                                Expected keys: VendorID, ProductID, SerialNumber, DeviceName, DeviceID.
        
        Returns:
            dict: Structured fingerprint.
        """
        return {
            "vendor_id": device_info.get("VendorID", "UNKNOWN"),
            "product_id": device_info.get("ProductID", "UNKNOWN"),
            "serial_number": device_info.get("SerialNumber", "UNKNOWN"),
            "device_name": device_info.get("DeviceName", "Unknown Device"),
            "device_id": device_info.get("DeviceID", "UNKNOWN")
        }

    @staticmethod
    def parse_device_id(pnp_device_id):
        """
        Parses a PnP Device ID string to extract VID, PID, and Serial if possible.
        Supports:
          - USB\\VID_xxxx&PID_yyyy\\serial
          - USBSTOR\\DISK&VEN_xxxx&PROD_yyyy...\\serial
        """
        fingerprint = {
            "VendorID": "UNKNOWN",
            "ProductID": "UNKNOWN",
            "SerialNumber": "UNKNOWN",
            "DeviceID": pnp_device_id
        }
        
        try:
            # Handle USBSTOR (Disk Drive) format
            # Example: USBSTOR\DISK&VEN_SANDISK&PROD_DUAL_DRIVE&REV_1.00\4C531001591110115041&0
            if pnp_device_id.startswith("USBSTOR"):
                parts = pnp_device_id.split('\\')
                if len(parts) >= 3:
                     # part[1] = DISK&VEN_SANDISK&PROD_...
                     # part[2] = 4C53...&0 (Serial)
                     
                     props = parts[1]
                     serial = parts[2]
                     
                     # Clean serial (remove &0 suffix usually added by Windows for unique instance)
                     if "&" in serial:
                         serial = serial.split("&")[0]
                     fingerprint["SerialNumber"] = serial
                     
                     # Extract VEN and PROD
                     # Naive parse of "VEN_XXXX&PROD_YYYY"
                     if "VEN_" in props:
                         try:
                             fingerprint["VendorID"] = props.split("VEN_")[1].split("&")[0]
                         except: pass
                     if "PROD_" in props:
                         try:
                             fingerprint["ProductID"] = props.split("PROD_")[1].split("&")[0]
                         except: pass
                         
                return fingerprint

            # Handle Standard USB format
            # Example: USB\VID_0781&PID_5581\...
            if pnp_device_id.startswith("USB"):
                parts = pnp_device_id.split('\\')
                if len(parts) >= 2:
                    vid_pid = parts[1]
                    serial = parts[2] if len(parts) > 2 else "UNKNOWN"
                    
                    if "VID_" in vid_pid and "PID_" in vid_pid:
                        fingerprint["VendorID"] = vid_pid.split("VID_")[1].split("&")[0]
                        fingerprint["ProductID"] = vid_pid.split("PID_")[1]
                    
                    fingerprint["SerialNumber"] = serial
                return fingerprint
                
        except Exception as e:
            logging.error(f"Error parsing Device ID {pnp_device_id}: {e}")
        
        return fingerprint

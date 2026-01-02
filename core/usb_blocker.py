import subprocess
import logging
import time

class USBBlocker:
    """
    Handles blocking and unblocking of USB devices using Windows PowerShell commands.
    Requires Admin privileges.
    """

    @staticmethod
    def block_device(instance_id):
        """
        Disables the PNP device with the given Instance ID.
        Retries up to 3 times. Uses PowerShell first, then PnPUtil as fallback.
        """
        # Escape for PowerShell string
        safe_id = instance_id.replace("'", "''")
        
        # Method 1: PowerShell Pipeline
        ps_script = f"Get-PnpDevice -InstanceId '{safe_id}' -ErrorAction SilentlyContinue | Disable-PnpDevice -Confirm:$false -ErrorAction Stop"
        
        # Method 2: PnPUtil (Native Windows Tool) - more robust for generic failures
        # pnputil /disable-device "instance_id"
        
        for attempt in range(1, 4):
            try:
                logging.info(f"Attempt {attempt} to BLOCK device: {instance_id}")
                
                # Try PowerShell
                result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
                
                if result.returncode == 0:
                    logging.info(f"Successfully BLOCKED device (via PowerShell): {instance_id}")
                    return True
                
                logging.warning(f"PowerShell block failed: {result.stderr.strip()}. Trying PnPUtil...")
                
                # Try PnPUtil as fallback
                # PnPUtil requires double quotes around ID
                pnp_cmd = ["pnputil", "/disable-device", instance_id]
                result_pnp = subprocess.run(pnp_cmd, capture_output=True, text=True)
                
                # Check for success OR pending reboot (which effectively blocks it)
                if result_pnp.returncode == 0:
                     logging.info(f"Successfully BLOCKED device (via PnPUtil): {instance_id}")
                     return True
                elif "reboot" in result_pnp.stdout.lower() or "restart" in result_pnp.stdout.lower():
                     logging.warning(f"Device disabled but requires reboot. Treating as BLOCKED: {instance_id}")
                     return True
                else:
                     # Double check status before declaring failure
                     # Sometimes it errors but still disables
                     check_cmd = ["powershell", "-Command", f"Get-PnpDevice -InstanceId '{instance_id}' | Select-Object -ExpandProperty Status"]
                     check_res = subprocess.run(check_cmd, capture_output=True, text=True)
                     status = check_res.stdout.strip()
                     if status in ["Error", "Disabled", "Degraded"]:
                         logging.info(f"Block command error, but device status is '{status}'. Success.")
                         return True
                     
                     logging.warning(f"PnPUtil block failed: {result_pnp.stdout.strip()}")
                
                time.sleep(1.5) # Wait a bit before retry
            except Exception as e:
                logging.error(f"Exception when blocking device {instance_id}: {e}")
                time.sleep(1)
        
        # Final check before failing
        try:
            check_cmd = ["powershell", "-Command", f"Get-PnpDevice -InstanceId '{instance_id}' | Select-Object -ExpandProperty Status"]
            check_res = subprocess.run(check_cmd, capture_output=True, text=True)
            if check_res.stdout.strip() in ["Error", "Disabled", "Degraded"]:
                 logging.info("Device confirmed BLOCKED despite earlier errors.")
                 return True
        except: pass

        logging.error(f"FATAL: Failed to BLOCK device {instance_id} after retries.")
        return False

    @staticmethod
    def unblock_device(instance_id):
        """
        Enables the PNP device with the given Instance ID.
        Retries up to 3 times. Uses PowerShell first, then PnPUtil as fallback.
        """
        safe_id = instance_id.replace("'", "''")
        ps_script = f"Get-PnpDevice -InstanceId '{safe_id}' | Enable-PnpDevice -Confirm:$false"
        
        for attempt in range(1, 4):
            try:
                logging.info(f"Attempt {attempt} to UNBLOCK device: {instance_id}")
                
                # Method 1: PowerShell
                result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
                if result.returncode == 0:
                    logging.info(f"Successfully UNBLOCKED device (via PowerShell): {instance_id}")
                    return True
                
                logging.warning(f"PowerShell unblock failed: {result.stderr.strip()}. Trying PnPUtil...")

                # Method 2: PnPUtil
                pnp_cmd = ["pnputil", "/enable-device", instance_id]
                result_pnp = subprocess.run(pnp_cmd, capture_output=True, text=True)
                
                if result_pnp.returncode == 0:
                     logging.info(f"Successfully UNBLOCKED device (via PnPUtil): {instance_id}")
                     return True
                elif "reboot" in result_pnp.stdout.lower() or "restart" in result_pnp.stdout.lower():
                     logging.warning(f"Device enabled but requires reboot: {instance_id}")
                     return True
                else:
                     # Double check status
                     check_cmd = ["powershell", "-Command", f"Get-PnpDevice -InstanceId '{instance_id}' | Select-Object -ExpandProperty Status"]
                     check_res = subprocess.run(check_cmd, capture_output=True, text=True)
                     if check_res.stdout.strip() == "OK":
                         logging.info("Device confirmed UNBLOCKED (Status: OK).")
                         return True
                
                time.sleep(1)
            except Exception as e:
                logging.error(f"Exception when unblocking device {instance_id}: {e}")
                time.sleep(1)
                
        logging.error(f"FATAL: Failed to UNBLOCK device {instance_id} after retries.")
        return False

import os
import datetime

class Reporter:
    def __init__(self, report_path):
        self.report_path = report_path
        self.stats = {
            "total_connections": 0,
            "unauthorized_attempts": 0,
            "blocked_devices": 0,
            "files_copied": 0,
            "files_deleted": 0,
            "files_modified": 0,
            "suspicious_activities": 0
        }
        self.session_start = datetime.datetime.now()

    def update_stat(self, key, increment=1):
        if key in self.stats:
            self.stats[key] += increment

    def generate_report(self):
        now = datetime.datetime.now()
        report_content = [
            "========================================",
            "      FINAL USB SECURITY AUDIT REPORT   ",
            "========================================",
            f"Report Generated: {now}",
            f"Session Start:    {self.session_start}",
            "----------------------------------------",
            "SUMMARY STATISTICS:",
            f"Total USB Connections:    {self.stats['total_connections']}",
            f"Unauthorized Attempts:    {self.stats['unauthorized_attempts']}",
            f"Blocked Devices:          {self.stats['blocked_devices']}",
            "----------------------------------------",
            "FILE ACTIVITY SUMMARY:",
            f"Files Copied:             {self.stats['files_copied']}",
            f"Files Deleted:            {self.stats['files_deleted']}",
            f"Files Modified:           {self.stats['files_modified']}",
            "----------------------------------------",
            "SECURITY ALERTS:",
            f"Suspicious Activities:    {self.stats['suspicious_activities']}",
            "========================================",
            "End of Report"
        ]
        
        try:
            os.makedirs(os.path.dirname(self.report_path), exist_ok=True)
            with open(self.report_path, "w") as f:
                f.write("\n".join(report_content))
            return True
        except Exception as e:
            print(f"Failed to write report: {e}")
            return False

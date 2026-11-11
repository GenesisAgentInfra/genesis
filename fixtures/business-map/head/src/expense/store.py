REPORTS = {}


def save_status(report_id, status):
    REPORTS.setdefault(report_id, {})["status"] = status


def load_report(report_id):
    return REPORTS[report_id]

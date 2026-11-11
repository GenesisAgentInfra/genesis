from fastapi import APIRouter

from .review import review_with_model
from .store import load_report, save_status

router = APIRouter()
THRESHOLD = 100


@router.post("/reports")
async def submit_report(report):
    amount = report["amount"]
    logger.info("report received")
    if amount >= THRESHOLD:
        verdict = await review_with_model(report)
        save_status(report["id"], "pending_approval")
        return {"status": "pending_approval", "review": verdict}
    save_status(report["id"], "approved")
    return {"status": "approved"}


@router.post("/reports/{report_id}/approve")
async def approve_report(report_id):
    report = load_report(report_id)
    if report["status"] != "pending_approval":
        raise ValueError("report is not waiting for approval")
    save_status(report_id, "approved")
    return {"status": "approved", "id": report_id}

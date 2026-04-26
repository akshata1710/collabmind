from fastapi import APIRouter, Depends, BackgroundTasks
from pathlib import Path
import json

from app.core.security import get_current_user
from app.models.user import User
from app.services.evaluator import run_all_evals

router = APIRouter(prefix="/eval", tags=["evaluation"])

# Store latest result in memory
_latest_report: dict | None = None


@router.post("/run")
async def trigger_eval(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    Trigger a full eval run in the background.
    Returns immediately — results available at GET /eval/report.
    Eval takes 2-5 minutes since it calls the LLM many times.
    """
    async def run():
        global _latest_report
        _latest_report = await run_all_evals()

    background_tasks.add_task(run)
    return {
        "status": "eval started",
        "message": "Check GET /eval/report in 2-5 minutes for results",
    }


@router.get("/report")
async def get_report(current_user: User = Depends(get_current_user)):
    """Return the latest eval report."""
    if _latest_report:
        return _latest_report

    # Try loading from disk if no in-memory report
    results_dir = Path("eval_results")
    if results_dir.exists():
        files = sorted(results_dir.glob("eval_*.json"))
        if files:
            with open(files[-1]) as f:
                return json.load(f)

    return {"status": "no eval results yet — POST /eval/run to start"}


@router.get("/status")
async def eval_status(current_user: User = Depends(get_current_user)):
    """Quick check — is there a report available?"""
    return {
        "has_report": _latest_report is not None,
        "overall_pass": _latest_report.get("overall_pass") if _latest_report else None,
    }
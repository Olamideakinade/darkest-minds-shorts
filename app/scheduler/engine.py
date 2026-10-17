"""Persistent autonomous scheduler coordinating research, production, publishing, and learning cycles."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Dict, Optional

from app.analytics.learning_engine import LearningEngine
from app.config import config
from app.database.db import Database, db
from app.database.models import JobState, SchedulerState, utc_now_iso
from app.intelligence.decision_engine import DecisionEngine
from app.orchestrator import Orchestrator
from app.research.service import ResearchService
from app.utils.hardware import inspect_hardware
from app.utils.logger import logger


class AutonomousScheduler:
    """Manages persistent autonomous cycles with crash recovery, safety pauses, and resource guards."""

    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self, database: Optional[Database] = None) -> None:
        self.db = database or db
        self.orchestrator = Orchestrator(database=self.db)
        self.decision_engine = DecisionEngine(database=self.db)
        self.learning_engine = LearningEngine(database=self.db)
        self.research_service = ResearchService(database=self.db)

    def get_state(self) -> SchedulerState:
        """Fetch persistent state from database."""
        return self.db.get_scheduler_state()

    def pause(self, reason: str = "Manual pause requested") -> None:
        """Globally pause autonomous operation."""
        state = self.get_state()
        state.is_paused = True
        state.pause_reason = reason
        self.db.update_scheduler_state(state)
        self.db.record_event("SCHEDULER_PAUSED", f"Autonomous scheduler paused: {reason}")
        logger.warning(f"Scheduler paused: {reason}")

    def resume(self) -> None:
        """Resume autonomous operation and clear failure count."""
        state = self.get_state()
        state.is_paused = False
        state.pause_reason = None
        state.consecutive_failures = 0
        self.db.update_scheduler_state(state)
        self.db.record_event("SCHEDULER_RESUMED", "Autonomous scheduler resumed.")
        logger.info("Scheduler resumed successfully.")

    def run_cycle(self) -> Dict[str, Any]:
        """Execute a single autonomous cycle checking research, production, and learning tasks."""
        cycle_start = utc_now_iso()
        state = self.get_state()

        # 1. Check Global Pause
        if state.is_paused or config.autonomous_paused:
            reason = state.pause_reason or "Autonomous operation is paused in settings."
            logger.info(f"Scheduler cycle skipped: {reason}")
            return {"status": "PAUSED", "reason": reason}

        # 2. Check Hardware Resources (Disk space threshold)
        hw = inspect_hardware()
        if hw.free_disk_gb < config.min_disk_free_gb:
            pause_reason = (
                f"Free disk space ({hw.free_disk_gb:.1f} GB) is below safety limit ({config.min_disk_free_gb:.1f} GB)."
            )
            self.pause(pause_reason)
            return {"status": "SAFETY_PAUSED", "reason": pause_reason}

        results: Dict[str, Any] = {
            "cycle_start": cycle_start,
            "research_triggered": False,
            "job_enqueued": False,
            "job_processed": False,
            "learning_updated": False,
            "errors": [],
        }

        try:
            # 3. Scheduled Research Check
            now = datetime.now(timezone.utc)
            should_research = False
            if not state.last_research_at:
                should_research = True
            else:
                last_res_dt = datetime.fromisoformat(state.last_research_at.replace("Z", "+00:00"))
                hours_since = (now - last_res_dt).total_seconds() / 3600.0
                if hours_since >= config.autonomous_research_interval_hours:
                    should_research = True

            if should_research:
                logger.info("Scheduler: Research interval elapsed. Running scheduled competitor research...")
                res = self.research_service.run_research(use_demo_if_unconfigured=True)
                state.last_research_at = utc_now_iso()
                results["research_triggered"] = True
                results["research_result"] = {
                    "videos_found": len(res.get("videos", [])),
                    "opportunities": len(res.get("opportunities", [])),
                }

            # 4. Production Check: Auto-Select and Process Job
            should_produce = False
            if not state.last_production_at:
                should_produce = True
            else:
                last_prod_dt = datetime.fromisoformat(state.last_production_at.replace("Z", "+00:00"))
                hours_since_prod = (now - last_prod_dt).total_seconds() / 3600.0
                if hours_since_prod >= config.autonomous_production_interval_hours:
                    should_produce = True

            # If queue has room and production is due, select and run
            counts = self.db.count_jobs_by_state()
            queued_count = counts.get("QUEUED", 0)

            if should_produce or queued_count == 0:
                decision_res = self.decision_engine.select_next_story_opportunity()
                if decision_res.job_id:
                    results["job_enqueued"] = True
                    results["selected_job_id"] = decision_res.job_id
                    try:
                        from app.telegram.notifier import notifier
                        notifier.notify_opportunity_discovered(
                            topic=decision_res.opportunity.get("topic", "Trending Mystery") if decision_res.opportunity else "New Opportunity",
                            score=decision_res.opportunity.get("opportunity_score", 90.0) if decision_res.opportunity else 90.0,
                            angle=decision_res.rationale
                        )
                    except Exception:
                        pass

            # Process next job in queue if any exist
            processed_job = self.orchestrator.process_next_job()
            if processed_job:
                results["job_processed"] = True
                results["processed_job_id"] = processed_job.id
                results["processed_job_state"] = processed_job.state.value
                state.last_production_at = utc_now_iso()
                if processed_job.state in (JobState.RETRYING, JobState.FAILED, JobState.REJECTED):
                    err_msg = f"Job {processed_job.id} failed production (state: {processed_job.state.value}, stage: {processed_job.current_stage}): {processed_job.error_message or 'QA or production failure'}"
                    results["errors"].append(err_msg)
                    logger.warning(err_msg)

            # 5. Learning & Strategy Feedback Check
            learning_result = self.learning_engine.evaluate_and_adapt()
            state.last_analytics_at = utc_now_iso()
            results["learning_updated"] = True
            results["learning_status"] = learning_result.get("status")

            if results["errors"]:
                state.consecutive_failures += 1
                results["status"] = "PARTIAL_FAILURE"
            else:
                state.consecutive_failures = 0
                results["status"] = "SUCCESS"
            self.db.update_scheduler_state(state)

        except Exception as e:
            logger.exception(f"Scheduler cycle encountered unhandled error: {e}")
            state.consecutive_failures += 1
            results["status"] = "ERROR"
            results["errors"].append(str(e))

            if state.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                pause_reason = f"Auto-paused after {state.consecutive_failures} consecutive failures. Last error: {e}"
                state.is_paused = True
                state.pause_reason = pause_reason
                logger.error(pause_reason)

            self.db.update_scheduler_state(state)

        return results

    def start_daemon(self, poll_interval_seconds: int = 60, max_iterations: Optional[int] = None) -> None:
        """Run the persistent autonomous daemon loop."""
        logger.info(
            f"Autonomous Scheduler daemon started (polling every {poll_interval_seconds}s). "
            "NOTE: On local macOS development, the Mac must remain awake."
        )
        print("=" * 70)
        print(" MHIDE STORY INTELLIGENCE — AUTONOMOUS SCHEDULER DAEMON ACTIVE")
        print("=" * 70)
        print(f"  • Polling Interval:      {poll_interval_seconds} seconds")
        print(f"  • Publishing Mode:       {config.youtube_publish_mode.upper()}")
        print(f"  • Max Daily Uploads:     {config.max_daily_uploads}")
        print("  • NOTE: Mac must remain running and awake for scheduled local execution.")
        print("=" * 70)

        try:
            from app.telegram.notifier import notifier
            hw = inspect_hardware()
            notifier.notify_startup({"hardware": {"free_disk_gb": hw.free_disk_gb}})
        except Exception:
            pass

        iterations = 0
        try:
            while True:
                results = self.run_cycle()
                if results.get("job_processed"):
                    logger.info(f"Daemon processed job {results.get('processed_job_id')} -> {results.get('processed_job_state')}")

                iterations += 1
                if max_iterations and iterations >= max_iterations:
                    break

                time.sleep(poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Autonomous Scheduler daemon stopped by user.")
            print("\nScheduler daemon stopped gracefully.")

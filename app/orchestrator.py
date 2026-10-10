"""Central orchestrator coordinating autonomous YouTube Shorts production pipeline."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from app.config import config
from app.database.db import Database, db
from app.database.models import Job, JobState
from app.utils.hardware import inspect_hardware
from app.utils.logger import logger


class Orchestrator:
    """State machine and coordinator for video production jobs."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self.db = database or db
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"

    def startup(self) -> Dict[str, Any]:
        """Perform system startup checks and recover in-flight jobs."""
        logger.info(f"Orchestrator starting up with worker ID: {self.worker_id}")
        hardware = inspect_hardware()

        # Recover in-flight jobs from prior crashes/restarts
        recovered_count = self.db.recover_in_flight_jobs()

        startup_summary = {
            "worker_id": self.worker_id,
            "hardware": hardware.to_dict(),
            "recovered_jobs": recovered_count,
            "publish_mode": config.youtube_publish_mode,
            "status": "READY" if not hardware.warnings else "WARNINGS_PRESENT",
            "warnings": hardware.warnings,
        }

        self.db.record_event(
            "ORCHESTRATOR_STARTUP",
            f"Orchestrator worker {self.worker_id} started. Recovered {recovered_count} jobs.",
            startup_summary,
        )
        return startup_summary

    def enqueue_job(self, title: str, niche: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> Job:
        """Enqueue a new video production job."""
        current_counts = self.db.count_jobs_by_state()
        active_jobs = current_counts.get(JobState.QUEUED.value, 0) + current_counts.get(JobState.RESEARCHING.value, 0)

        if active_jobs >= config.max_queue_size:
            raise RuntimeError(
                f"Queue capacity reached ({active_jobs}/{config.max_queue_size}). Please wait for current jobs to finish."
            )

        job = self.db.create_job(title=title, niche=niche, payload=payload)
        logger.info(f"Enqueued job '{job.title}' (ID: {job.id}) in niche '{job.niche}'")
        return job

    def process_next_job(self) -> Optional[Job]:
        """Fetch and execute the next queued job through the production lifecycle."""
        # Check disk space safety before processing
        hardware = inspect_hardware()
        if hardware.free_disk_gb < config.min_disk_free_gb:
            logger.error(
                f"Halting job processing: free disk space ({hardware.free_disk_gb:.1f} GB) is below safety limit ({config.min_disk_free_gb:.1f} GB)."
            )
            return None

        job = self.db.get_next_queued_job()
        if not job:
            return None

        # Attempt to acquire exclusive lock
        if not self.db.acquire_job_lock(job.id, self.worker_id):
            logger.debug(f"Could not acquire lock for job {job.id}; another worker may have claimed it.")
            return None

        logger.info(f"Processing job {job.id}: '{job.title}'")
        try:
            self._execute_job_lifecycle(job)
        except Exception as e:
            logger.exception(f"Unhandled exception while processing job {job.id}: {e}")
            self._handle_failure(job, str(e))
        finally:
            self.db.release_job_lock(job.id, self.worker_id)

        return self.db.get_job(job.id)

    def _execute_job_lifecycle(self, job: Job) -> None:
        """Step through the explicit job state machine."""
        stages = [
            (JobState.RESEARCHING, "research", self._step_research),
            (JobState.SCRIPTING, "scripting", self._step_scripting),
            (JobState.NARRATING, "narrating", self._step_narrating),
            (JobState.ASSEMBLING, "assembling", self._step_assembling),
            (JobState.QA, "qa", self._step_qa),
        ]

        for target_state, stage_name, step_fn in stages:
            logger.info(f"Job {job.id} transitioning to state: {target_state.value}")
            self.db.update_job_state(job.id, target_state, stage=stage_name)
            step_fn(job)

        # After QA passes, set to READY
        self.db.update_job_state(job.id, JobState.READY, stage="ready_for_review")
        logger.info(f"Job {job.id} passed all production stages and is in READY state.")

        # Evaluate Autonomous Publishing Policy
        from app.intelligence.decision_engine import DecisionEngine
        from app.youtube.publisher import YouTubePublisher

        decision_engine = DecisionEngine(database=self.db)
        can_publish, target_privacy, reason = decision_engine.evaluate_publishing_safety(job)

        if can_publish:
            self.db.update_job_state(job.id, JobState.UPLOADING, stage="uploading")
            publisher = YouTubePublisher(database=self.db)
            success, msg, details = publisher.publish_video(job, privacy_status=target_privacy)
            if success:
                self.db.update_job_state(
                    job.id,
                    JobState.PUBLISHED,
                    stage="published",
                    payload_updates={"youtube_url": details.get("url"), "youtube_id": details.get("youtube_id")},
                )
                logger.info(f"Job {job.id} successfully published to YouTube ({target_privacy}): {msg}")
            else:
                self.db.update_job_state(
                    job.id,
                    JobState.NEEDS_REVIEW,
                    stage="upload_blocked",
                    error_message=msg,
                    payload_updates={"upload_blocker": details.get("blocker")},
                )
                logger.warning(f"Job {job.id} upload blocked: {msg}. Moved to NEEDS_REVIEW.")
        else:
            if config.youtube_publish_mode == "disabled":
                logger.info(f"Publishing mode is disabled. Job {job.id} remains in READY state.")
            else:
                self.db.update_job_state(
                    job.id,
                    JobState.NEEDS_REVIEW,
                    stage="publishing_safeguard",
                    error_message=reason,
                )
                logger.warning(f"Job {job.id} publishing safeguard: {reason}. Moved to NEEDS_REVIEW.")

    def _handle_failure(self, job: Job, error_msg: str) -> None:
        """Handle job step failure with bounded retries."""
        latest = self.db.get_job(job.id)
        retries = latest.retry_count if latest else 0

        if retries < config.daily_shorts_target * 3:
            logger.warning(f"Job {job.id} failed ({error_msg}). Scheduling retry ({retries + 1}/{job.max_retries}).")
            self.db.update_job_state(
                job.id,
                JobState.RETRYING,
                stage="retry_queued",
                error_message=error_msg,
                payload_updates={"last_error": error_msg, "retry_attempt": retries + 1},
            )
        else:
            logger.error(f"Job {job.id} exceeded maximum retries. Marking FAILED.")
            self.db.update_job_state(
                job.id,
                JobState.FAILED,
                stage="failed",
                error_message=f"Exceeded max retries: {error_msg}",
            )

    # --------------------------------------------------------------------------
    # Lifecycle Step Stubs (Implemented in Subsequent Phases)
    # --------------------------------------------------------------------------

    def _step_research(self, job: Job) -> None:
        """Phase 2: YouTube competitor research & trend opportunity scoring."""
        logger.info(f"Executing Phase 2 research for job {job.id} ('{job.title}')...")
        from app.research.service import ResearchService
        service = ResearchService(database=self.db)
        query = job.payload.get("topic") or job.title

        result = service.run_research(query=query, max_videos=10, use_demo_if_unconfigured=True)
        if result.get("opportunities"):
            best = result["opportunities"][0]
            self.db.update_job_state(
                job.id,
                JobState.RESEARCHING,
                stage="research_complete",
                payload_updates={
                    "top_opportunity": {
                        "topic": best.topic,
                        "score": best.composite_score,
                        "confidence": best.confidence,
                        "angle": best.suggested_angle,
                    }
                },
            )
        logger.info(f"Phase 2 research completed successfully for job {job.id}.")


    def _step_scripting(self, job: Job) -> None:
        """Phase 3: Original 3-Act story generation & factual verification."""
        logger.info(f"Executing Phase 3 storytelling engine for job {job.id} ('{job.title}')...")
        from app.scripts.story_engine import StoryEngine
        engine = StoryEngine(database=self.db)
        story = engine.generate_story(job)

        self.db.update_job_state(
            job.id,
            JobState.SCRIPTING,
            stage="script_generated",
            payload_updates={
                "script_id": story.id,
                "word_count": story.word_count,
                "estimated_duration_sec": story.estimated_duration_sec,
                "hook_text": story.hook_text,
                "factual_status": story.factual_verification_status,
                "scenes_count": len(story.scenes),
            },
        )
        logger.info(
            f"Phase 3 storytelling complete for job {job.id}: {story.word_count} words, "
            f"~{story.estimated_duration_sec}s, {len(story.scenes)} scenes, factual: {story.factual_verification_status}."
        )

    def _step_narrating(self, job: Job) -> None:
        """Phase 4 hook: Natural local TTS narration."""
        logger.debug(f"[Phase 4 Hook] Generating local voiceover audio for job {job.id}")
        time.sleep(0.1)

    def _step_assembling(self, job: Job) -> None:
        """Phase 5 hook: Media assembly & vertical video rendering."""
        logger.debug(f"[Phase 5 Hook] Rendering 9:16 vertical video for job {job.id}")
        time.sleep(0.1)

    def _step_qa(self, job: Job) -> None:
        """Phase 5/QA hook: Automated quality assurance checks."""
        logger.debug(f"[QA Hook] Running QA verification checks for job {job.id}")
        time.sleep(0.1)

    def _step_upload(self, job: Job, privacy_status: str = "public") -> Tuple[bool, str, Dict[str, Any]]:
        """Phase 7: YouTube Data API upload via publisher."""
        from app.youtube.publisher import YouTubePublisher
        publisher = YouTubePublisher(database=self.db)
        return publisher.publish_video(job, privacy_status=privacy_status)

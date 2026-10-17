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

        # Verify final MP4 exists, has nonzero size, and valid metadata before READY
        from pathlib import Path
        latest_job = self.db.get_job(job.id) or job
        video_path_str = latest_job.payload.get("video_path")
        if not video_path_str or not Path(video_path_str).exists() or Path(video_path_str).stat().st_size == 0:
            raise RuntimeError(f"Job {job.id} cannot transition to READY: final MP4 video file is missing or empty.")

        # After QA passes and MP4 is verified, set to READY
        self.db.update_job_state(job.id, JobState.READY, stage="ready_for_review")
        logger.info(f"Job {job.id} passed all production stages and is in READY state ({video_path_str}).")

        # Evaluate Autonomous Publishing Policy
        from app.intelligence.decision_engine import DecisionEngine
        from app.youtube.publisher import YouTubePublisher

        decision_engine = DecisionEngine(database=self.db)
        can_publish, target_privacy, reason = decision_engine.evaluate_publishing_safety(job)

        if can_publish and (config.auto_publish_enabled or config.youtube_publish_mode in ("private_test", "autonomous_public")):
            self.db.update_job_state(job.id, JobState.PUBLISHING, stage="publishing")
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
                if config.auto_cleanup_artifacts:
                    self.cleanup_job_artifacts(job.id)
            else:
                self.db.update_job_state(
                    job.id,
                    JobState.PUBLISH_FAILED,
                    stage="upload_blocked",
                    error_message=msg,
                    payload_updates={"upload_blocker": details.get("blocker")},
                )
                logger.warning(f"Job {job.id} upload blocked: {msg}. Moved to PUBLISH_FAILED.")
        else:
            if config.youtube_publish_mode == "disabled":
                logger.info(f"Publishing mode is disabled. Job {job.id} remains in READY state.")
            else:
                self.db.update_job_state(
                    job.id,
                    JobState.REVIEW_REQUIRED,
                    stage="publishing_safeguard",
                    error_message=reason,
                )
                logger.warning(f"Job {job.id} publishing safeguard: {reason}. Moved to REVIEW_REQUIRED.")

    def _handle_failure(self, job: Job, error_msg: str) -> None:
        """Handle job step failure with bounded retries."""
        latest = self.db.get_job(job.id)
        retries = latest.retry_count if latest else 0

        if retries < job.max_retries:
            logger.warning(f"Job {job.id} failed ({error_msg}). Scheduling retry ({retries + 1}/{job.max_retries}).")
            self.db.update_job_state(
                job.id,
                JobState.RETRYING,
                stage="retry_queued",
                error_message=error_msg,
                payload_updates={"last_error": error_msg, "retry_attempt": retries + 1},
                increment_retry=True,
            )
        else:
            logger.error(f"Job {job.id} exceeded maximum retries. Marking FAILED.")
            self.db.update_job_state(
                job.id,
                JobState.FAILED,
                stage="failed",
                error_message=f"Exceeded max retries: {error_msg}",
            )
            try:
                from app.telegram.notifier import notifier
                notifier.notify_alert(
                    title=f"Production Halted for Job {job.id[:8]}",
                    message=f"Topic: {job.title}\nError: {error_msg}"
                )
            except Exception:
                pass

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
        if not result.get("opportunities"):
            raise RuntimeError(f"Phase 2 research failed for job {job.id}: No viable opportunities formulated for query '{query}'. Halting before scripting.")

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

        if not story.is_approved or story.factual_verification_status != "VERIFIED":
            raise RuntimeError(
                f"Job {job.id} script failed factual verification ({story.factual_verification_status}): "
                f"{story.factual_notes}. Halting production before narration."
            )

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
                "scenes": [sc.to_dict() if hasattr(sc, "to_dict") else sc for sc in story.scenes],
                "optimized_title": getattr(story, "optimized_title", ""),
                "description_text": getattr(story, "description_text", ""),
                "target_tags": getattr(story, "target_tags", []),
                "pinned_comment": getattr(story, "pinned_comment", ""),
                "retention_score": getattr(story, "retention_score", 90),
                "critique_feedback": getattr(story, "critique_feedback", ""),
            },
        )
        logger.info(
            f"Phase 3 storytelling complete for job {job.id}: {story.word_count} words, "
            f"~{story.estimated_duration_sec}s, {len(story.scenes)} scenes, factual: {story.factual_verification_status}."
        )

    def _step_narrating(self, job: Job) -> None:
        """Phase 4: Natural local TTS narration synthesis with word timings."""
        logger.info(f"Executing Phase 4 narration synthesis for job {job.id}...")
        from app.narration.tts_service import TTSService
        tts = TTSService(database=self.db)

        # Retrieve script text
        script_text = ""
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM scripts WHERE job_id = ? ORDER BY created_at DESC LIMIT 1", (job.id,)).fetchone()
            if row:
                script_text = row["full_text"]

        if not script_text:
            raise RuntimeError(f"Cannot narrate job {job.id}: No script record found.")

        job_dir = config.output_dir / "jobs" / job.id
        audio_path = job_dir / "narration.mp3"
        result = tts.synthesize(job.id, script_text, output_path=audio_path)

        self.db.update_job_state(
            job.id,
            JobState.NARRATING,
            stage="narration_complete",
            payload_updates={
                "audio_path": str(result.audio_path),
                "audio_duration": result.duration_sec,
                "audio_provider": result.provider,
                "audio_voice": result.voice_used,
                "word_timestamps": [w.to_dict() for w in result.word_timestamps],
            },
        )
        logger.info(f"Phase 4 narration complete for job {job.id}: {result.duration_sec:.1f}s ({result.provider})")

    def _step_assembling(self, job: Job) -> None:
        """Phase 5: Visual asset production, caption synchronization, and FFmpeg video rendering."""
        logger.info(f"Executing Phase 5 media assembly for job {job.id}...")
        import json
        from pathlib import Path
        from app.editing.audio_mixer import AudioMixer
        from app.editing.captions import CaptionGenerator, WordTimestamp
        from app.editing.timeline import TimelineEngine
        from app.editing.video_renderer import VideoRenderer
        from app.scripts.story_models import StoryScene, StoryScript
        from app.visuals.service import VisualProductionService

        latest_job = self.db.get_job(job.id) or job
        job_dir = config.output_dir / "jobs" / job.id
        audio_path_str = latest_job.payload.get("audio_path")
        if not audio_path_str or not Path(audio_path_str).exists():
            raise RuntimeError(f"Cannot assemble job {job.id}: narration audio file missing.")
        audio_path = Path(audio_path_str)

        # Reconstruct story script from database
        with self.db.connection() as conn:
            s_row = conn.execute("SELECT * FROM scripts WHERE job_id = ? ORDER BY created_at DESC LIMIT 1", (job.id,)).fetchone()

        hook = s_row["hook_text"] if s_row else ""
        body = s_row["body_text"] if s_row else ""
        payoff = s_row["payoff_text"] if s_row else ""
        title = latest_job.payload.get("topic") or latest_job.title

        story_script = StoryScript(
            job_id=job.id,
            title=title,
            hook_text=hook,
            escalation_text=body,
            payoff_text=payoff,
        )

        raw_scenes = latest_job.payload.get("scenes", [])
        scenes_list = []
        for idx, sc in enumerate(raw_scenes):
            if isinstance(sc, dict):
                scenes_list.append(
                    StoryScene(
                        scene_number=sc.get("scene_number", idx + 1),
                        narration_chunk=sc.get("narration_chunk", ""),
                        visual_prompt=sc.get("visual_prompt", ""),
                        target_duration_sec=float(sc.get("target_duration_sec", 4.0)),
                        visual_mood=sc.get("visual_mood", "cinematic_dramatic"),
                        badge_text=sc.get("badge_text", ""),
                        pexels_query=sc.get("pexels_query", ""),
                        ai_image_prompt=sc.get("ai_image_prompt", ""),
                    )
                )
        story_script.scenes = scenes_list

        raw_words = latest_job.payload.get("word_timestamps", [])
        word_timestamps = [
            WordTimestamp(word=w["word"], start_sec=w["start_sec"], end_sec=w["end_sec"])
            for w in raw_words
        ]
        total_audio_duration = float(latest_job.payload.get("audio_duration") or 30.0)

        output_mp4 = job_dir / "short_1080x1920.mp4"
        timeline_json_path = job_dir / "timeline.json"
        caption_gen = CaptionGenerator()
        renderer = VideoRenderer()
        treatment = "treatment_d"

        # Check if story has multi-scene breakdown for millisecond PerScenePipeline
        if len(scenes_list) >= 4:
            from app.editing.per_scene_pipeline import per_scene_pipeline
            logger.info(f"Assembling job {job.id} using PerScenePipeline ({len(scenes_list)} scenes)...")
            pipe_res = per_scene_pipeline.assemble_production_video(
                job_id=job.id,
                scenes=scenes_list,
                output_mp4=output_mp4,
            )

            # Generate SRT from accumulated word timestamps
            words_path = job_dir / "word_timestamps.json"
            word_ts_data = []
            if words_path.exists():
                with open(words_path, "r", encoding="utf-8") as fw:
                    word_ts_data = json.load(fw)

            w_objs = [
                WordTimestamp(word=w["word"], start_sec=w["start_sec"], end_sec=w["end_sec"])
                for w in word_ts_data
            ]
            srt_path, caption_cues = caption_gen.generate_captions(job.id, w_objs, output_dir=job_dir)
            mixed_audio_path = audio_path

            # Load timeline from generated timeline.json
            from app.editing.timeline import ScenePlan
            timeline = []
            if timeline_json_path.exists():
                with open(timeline_json_path, "r", encoding="utf-8") as ft:
                    timeline = [ScenePlan(**item) for item in json.load(ft)]

            meta_duration = pipe_res["total_duration"]
            meta_size = output_mp4.stat().st_size if output_mp4.exists() else 0
        else:
            # 1. Build dynamic scene timeline (rapid 2.5s-4.5s purposeful beats)
            timeline_engine = TimelineEngine()
            timeline = timeline_engine.build_timeline(
                story=story_script,
                word_timestamps=word_timestamps,
                total_duration=total_audio_duration,
                job_dir=job_dir,
            )

            with open(timeline_json_path, "w", encoding="utf-8") as f:
                json.dump([p.to_dict() for p in timeline], f, indent=2)

            # 2. Produce visual scenes for each timeline beat
            visual_svc = VisualProductionService(database=self.db)
            timeline = visual_svc.produce_from_timeline(job.id, timeline)

            with open(timeline_json_path, "w", encoding="utf-8") as f:
                json.dump([p.to_dict() for p in timeline], f, indent=2)

            # 3. Generate synchronized captions
            srt_path, caption_cues = caption_gen.generate_captions(job.id, word_timestamps, output_dir=job_dir)

            # 4. Professional audio mixing with ducking
            audio_mixer = AudioMixer()
            mixed_audio_path = audio_mixer.mix_soundtrack(
                job_id=job.id,
                narration_path=audio_path,
                total_duration=total_audio_duration,
                timeline=timeline,
            )

            # 5. Render 1080x1920 vertical video
            meta = renderer.render_timeline(
                job_id=job.id,
                audio_path=mixed_audio_path,
                timeline=timeline,
                caption_cues=caption_cues,
                output_mp4=output_mp4,
                treatment=treatment,
            )
            meta_duration = meta.duration_sec
            meta_size = meta.file_size_bytes

        # 6. Extract representative preview frames and contact sheet
        preview_frames = renderer.extract_preview_frames(output_mp4, output_dir=job_dir / "previews")
        contact_sheet_path = job_dir / "contact_sheet.jpg"
        if not contact_sheet_path.exists() and preview_frames:
            from app.visuals.scene_synthesizer import scene_synthesizer
            scene_synthesizer.create_contact_sheet(preview_frames, contact_sheet_path)

        self.db.update_job_state(
            job.id,
            JobState.ASSEMBLING,
            stage="assembly_complete",
            payload_updates={
                "video_path": str(output_mp4),
                "srt_path": str(srt_path),
                "mixed_audio_path": str(mixed_audio_path),
                "timeline_path": str(timeline_json_path),
                "creative_treatment": treatment,
                "video_duration": meta_duration,
                "video_resolution": "1080x1920",
                "video_size_bytes": meta_size,
                "preview_frames": [str(f) for f in preview_frames],
                "contact_sheet_path": str(contact_sheet_path) if contact_sheet_path.exists() else None,
                "scenes_rendered": len(timeline),
                "captions_count": len(caption_cues),
            },
        )
        logger.info(f"Phase 5 assembly complete for job {job.id}: {output_mp4.name} ({meta_duration:.1f}s, {meta_size / 1024 / 1024:.2f} MB)")

    def _step_qa(self, job: Job) -> None:
        """Phase 5/QA: Comprehensive quality verification checks across media, audio, captions, and facts."""
        logger.info(f"Executing QA verification for job {job.id}...")
        import json
        from pathlib import Path
        from app.editing.timeline import ScenePlan
        from app.quality.checker import QualityChecker

        latest_job = self.db.get_job(job.id) or job
        video_path_str = latest_job.payload.get("video_path")
        audio_path_str = latest_job.payload.get("mixed_audio_path") or latest_job.payload.get("audio_path")
        srt_path_str = latest_job.payload.get("srt_path")

        if not video_path_str or not Path(video_path_str).exists():
            raise RuntimeError(f"QA failed: video file {video_path_str} does not exist.")
        if not audio_path_str or not Path(audio_path_str).exists():
            raise RuntimeError(f"QA failed: audio file {audio_path_str} does not exist.")
        if not srt_path_str or not Path(srt_path_str).exists():
            raise RuntimeError(f"QA failed: srt file {srt_path_str} does not exist.")

        # Load timeline if available
        timeline_path_str = latest_job.payload.get("timeline_path")
        timeline: Optional[List[ScenePlan]] = None
        if timeline_path_str and Path(timeline_path_str).exists():
            try:
                with open(timeline_path_str, "r", encoding="utf-8") as f:
                    t_data = json.load(f)
                    timeline = [
                        ScenePlan(
                            scene_number=item["scene_number"],
                            start_sec=item["start_sec"],
                            end_sec=item["end_sec"],
                            duration_sec=item["duration_sec"],
                            narration_segment=item["narration_segment"],
                            visual_purpose=item["visual_purpose"],
                            asset_type=item["asset_type"],
                            search_query=item["search_query"],
                            motion_type=item["motion_type"],
                            transition_type=item["transition_type"],
                            kinetic_text=item["kinetic_text"],
                            sound_cue=item.get("sound_cue"),
                            source_attribution=item.get("source_attribution", ""),
                            is_public_domain=item.get("is_public_domain", True),
                            rendered_image_path=Path(item["rendered_image_path"]) if item.get("rendered_image_path") else None,
                            rendered_clip_path=Path(item["rendered_clip_path"]) if item.get("rendered_clip_path") else None,
                        )
                        for item in t_data
                    ]
            except Exception as e:
                logger.warning(f"Could not load timeline for QA: {e}")

        # Fetch script record for factual consistency check
        script_record = None
        with self.db.connection() as conn:
            s_row = conn.execute("SELECT * FROM scripts WHERE job_id = ? ORDER BY created_at DESC LIMIT 1", (job.id,)).fetchone()
            if s_row:
                from app.database.models import ScriptRecord
                script_record = ScriptRecord(
                    id=s_row["id"],
                    job_id=s_row["job_id"],
                    full_text=s_row["full_text"],
                    hook_text=s_row["hook_text"],
                    body_text=s_row["body_text"],
                    payoff_text=s_row["payoff_text"],
                    word_count=s_row["word_count"],
                    estimated_duration_sec=s_row["estimated_duration_sec"],
                    factual_verification_status=s_row["factual_verification_status"],
                    factual_notes=s_row["factual_notes"] or "",
                    created_at=s_row["created_at"],
                )

        checker = QualityChecker(database=self.db)
        report = checker.verify_production_quality(
            job_id=job.id,
            video_path=Path(video_path_str),
            audio_path=Path(audio_path_str),
            srt_path=Path(srt_path_str),
            script=script_record,
            timeline=timeline,
        )

        if report.status == "FAIL":
            has_critical = any(
                "Hard Failure" in issue or "does not exist" in issue or "Invalid video resolution" in issue
                for issue in report.issues
            )
            state_target = JobState.REJECTED if has_critical else JobState.REVIEW_REQUIRED
            self.db.update_job_state(
                job.id,
                state_target,
                stage="qa_rejected" if has_critical else "qa_review_required",
                error_message=f"QA inspection failed: {'; '.join(report.issues)}",
                payload_updates={"qa_status": "FAIL", "qa_issues": report.issues, "qa_checks": report.checks},
            )
            raise RuntimeError(f"Automated QA inspection failed with issues: {'; '.join(report.issues)}")

        self.db.update_job_state(
            job.id,
            JobState.QA,
            stage="qa_passed",
            payload_updates={"qa_status": "PASS", "qa_checks": report.checks},
        )
        logger.info(f"QA verification passed successfully for job {job.id}.")

    def _step_upload(self, job: Job, privacy_status: str = "public") -> Tuple[bool, str, Dict[str, Any]]:
        """Phase 7: YouTube Data API upload via publisher."""
        from app.youtube.publisher import YouTubePublisher
        publisher = YouTubePublisher(database=self.db)
        return publisher.publish_video(job, privacy_status=privacy_status)

    def cleanup_job_artifacts(self, job_id: str) -> bool:
        """Completely remove all local disk artifacts and folder for a job once processed or published."""
        import shutil
        job_dir = config.output_dir / "jobs" / job_id
        if job_dir.exists():
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
                logger.info(f"Auto-cleanup: Removed local job artifacts directory for job {job_id} ({job_dir}).")
                return True
            except Exception as e:
                logger.warning(f"Could not remove job artifacts directory {job_dir}: {e}")
        return False

    def clean_all_artifacts(self) -> Dict[str, Any]:
        """Completely delete old job directories, temporary clips, and cache to reclaim disk space."""
        import shutil
        freed_bytes = 0
        removed_jobs = 0
        removed_files = 0

        # 1. Clean output/jobs directory
        jobs_dir = config.output_dir / "jobs"
        if jobs_dir.exists():
            for p in list(jobs_dir.iterdir()):
                if p.is_dir():
                    try:
                        dir_size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                        shutil.rmtree(p, ignore_errors=True)
                        freed_bytes += dir_size
                        removed_jobs += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete {p}: {e}")

        # 2. Clean temporary output test files
        if config.output_dir.exists():
            for p in list(config.output_dir.iterdir()):
                if p.is_file() and (p.name.startswith("test_") or p.name.startswith("quick_test") or p.name.startswith("guy_instant_test")):
                    try:
                        freed_bytes += p.stat().st_size
                        p.unlink(missing_ok=True)
                        removed_files += 1
                    except Exception:
                        pass

        # 3. Clean video_cache
        video_cache = config.data_dir / "video_cache"
        if video_cache.exists():
            for p in list(video_cache.iterdir()):
                try:
                    if p.is_file():
                        freed_bytes += p.stat().st_size
                        p.unlink(missing_ok=True)
                        removed_files += 1
                    elif p.is_dir():
                        dir_size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                        shutil.rmtree(p, ignore_errors=True)
                        freed_bytes += dir_size
                except Exception:
                    pass

        freed_mb = freed_bytes / (1024 * 1024)
        logger.info(f"Cleaned all artifacts: {removed_jobs} job folders, {removed_files} temp files removed. Freed {freed_mb:.1f} MB.")
        return {
            "removed_job_folders": removed_jobs,
            "removed_temp_files": removed_files,
            "freed_mb": round(freed_mb, 2),
        }


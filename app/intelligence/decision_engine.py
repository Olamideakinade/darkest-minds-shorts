"""Autonomous Decision Engine coordinating content selection, publishing evaluation, and strategy execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.config import config
from app.database.db import Database, db
from app.database.models import (
    ContentStrategy,
    DecisionLog,
    Job,
    JobState,
    OpportunityAnalysis,
    utc_now_iso,
)
from app.utils.hardware import inspect_hardware
from app.utils.logger import logger
from app.youtube.channel_manager import OwnerChannelManager, channel_manager


@dataclass
class DecisionResult:
    """Result of an autonomous decision engine action."""
    action_taken: str
    decision_type: str
    rationale: str
    job_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    details: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_taken": self.action_taken,
            "decision_type": self.decision_type,
            "rationale": self.rationale,
            "job_id": self.job_id,
            "opportunity_id": self.opportunity_id,
            "details": self.details or {},
        }


class DecisionEngine:
    """Selects next actions based on channel state, research evidence, resources, and past experiments."""

    def __init__(self, database: Optional[Database] = None, ch_manager: Optional[OwnerChannelManager] = None) -> None:
        self.db = database or db
        self.channel_manager = ch_manager or channel_manager

    def select_next_story_opportunity(self) -> DecisionResult:
        """Evaluate researched opportunities, apply strategy weights, select the best candidate,

        and automatically create a production job without manual input.
        """
        # 1. Fetch available scored opportunities
        candidates = self.db.list_opportunity_analyses(limit=25)
        if not candidates:
            # No candidates in store: trigger research to populate opportunities
            rationale = "No opportunities in database. Initiated research run to discover new topics."
            decision = DecisionLog(
                decision_type="TOPIC_SELECTION",
                input_summary="Candidates count: 0",
                chosen_action="TRIGGER_RESEARCH",
                rationale=rationale,
            )
            self.db.log_decision(decision)
            logger.info("Decision Engine: No candidate opportunities found; triggering research.")
            return DecisionResult(
                action_taken="TRIGGER_RESEARCH",
                decision_type="TOPIC_SELECTION",
                rationale=rationale,
            )

        # 2. Filter out topics already enqueued or produced
        existing_jobs = self.db.list_jobs(limit=100)
        existing_topics = {j.title.lower().strip() for j in existing_jobs}
        existing_payload_topics = {
            j.payload.get("topic", "").lower().strip()
            for j in existing_jobs if isinstance(j.payload, dict) and "topic" in j.payload
        }
        seen_topics = existing_topics | existing_payload_topics

        unproduced: List[OpportunityAnalysis] = []
        for c in candidates:
            if c.topic.lower().strip() not in seen_topics:
                unproduced.append(c)

        if not unproduced:
            rationale = (
                f"All {len(candidates)} available opportunities have already been enqueued or produced. "
                "Triggering fresh research query."
            )
            decision = DecisionLog(
                decision_type="TOPIC_SELECTION",
                input_summary=f"Evaluated {len(candidates)} candidates, 0 unproduced",
                chosen_action="TRIGGER_RESEARCH",
                rationale=rationale,
            )
            self.db.log_decision(decision)
            return DecisionResult(
                action_taken="TRIGGER_RESEARCH",
                decision_type="TOPIC_SELECTION",
                rationale=rationale,
            )

        # 3. Apply active strategy weights to rank unproduced opportunities
        weights = self.db.get_strategy_weights()
        ranked = self._rank_opportunities_with_weights(unproduced, weights)

        selected_opp, final_score = ranked[0]
        rejected_candidates = [
            f"'{opp.topic}' (score: {score:.1f}, original: {opp.composite_score:.1f})"
            for opp, score in ranked[1:5]
        ]

        # 4. Formulate explicit, explainable rationale
        rejection_summary = f" Considered and deprioritized: {', '.join(rejected_candidates)}." if rejected_candidates else ""
        rationale = (
            f"Selected '{selected_opp.topic}' with weighted score {final_score:.1f}/100 "
            f"(base score: {selected_opp.composite_score:.1f}, confidence: {selected_opp.confidence}). "
            f"Angle: '{selected_opp.suggested_angle}'.{rejection_summary}"
        )

        # 5. Determine content strategy attributes (archetype, hook style, category)
        category = self._classify_category(selected_opp.topic)
        hook_style = self._select_hook_style(weights)
        narrative_archetype = self._select_narrative_archetype(weights)

        # 6. Auto-create Job in the database
        job = self.db.create_job(
            title=selected_opp.topic,
            niche=config.niche_default,
            payload={
                "topic": selected_opp.topic,
                "angle": selected_opp.suggested_angle,
                "opportunity_id": selected_opp.id,
                "weighted_score": final_score,
                "category": category,
                "hook_style": hook_style,
                "narrative_archetype": narrative_archetype,
                "target_duration_sec": 45,
                "auto_selected": True,
            },
        )

        # Record content strategy record for measurable feedback loop
        strategy_record = ContentStrategy(
            job_id=job.id,
            category=category,
            hook_style=hook_style,
            target_duration_sec=45,
            words_per_minute=150.0,
            narrative_archetype=narrative_archetype,
        )
        self.db.record_content_strategy(strategy_record)

        # 7. Record durable decision log
        decision = DecisionLog(
            decision_type="TOPIC_SELECTION",
            input_summary=f"Evaluated {len(unproduced)} unproduced candidates",
            chosen_action=f"ENQUEUE_JOB:{job.id}",
            rationale=rationale,
            outcome=f"Job {job.id} created in QUEUED state",
        )
        self.db.log_decision(decision)

        logger.info(f"Decision Engine selected topic '{selected_opp.topic}' -> Enqueued Job {job.id}")
        return DecisionResult(
            action_taken=f"ENQUEUE_JOB:{job.id}",
            decision_type="TOPIC_SELECTION",
            rationale=rationale,
            job_id=job.id,
            opportunity_id=selected_opp.id,
            details={
                "topic": selected_opp.topic,
                "angle": selected_opp.suggested_angle,
                "weighted_score": final_score,
                "hook_style": hook_style,
                "narrative_archetype": narrative_archetype,
                "category": category,
            },
        )

    def evaluate_publishing_safety(self, job: Job) -> Tuple[bool, str, str]:
        """Evaluate whether a ready video is eligible for publication according to autonomous policy.

        Returns:
            Tuple of (can_publish: bool, target_privacy: str, rationale: str)
        """
        mode = config.youtube_publish_mode

        # 1. Check Global Pause Switch
        scheduler_state = self.db.get_scheduler_state()
        if scheduler_state.is_paused or config.autonomous_paused:
            reason = scheduler_state.pause_reason or "Autonomous operation is globally paused."
            return False, "private", f"Publishing blocked: {reason}"

        # 2. Check Hardware Disk Space
        hw = inspect_hardware()
        if hw.free_disk_gb < config.min_disk_free_gb:
            return False, "private", (
                f"Publishing blocked: Free disk space ({hw.free_disk_gb:.1f} GB) is below "
                f"safety limit ({config.min_disk_free_gb:.1f} GB)."
            )

        # 3. Check Publishing Mode
        if mode == "disabled":
            return False, "private", "Publishing mode is 'disabled'. Video remains in local READY state."

        # 4. Check Owner Channel Connection
        channel_status = self.channel_manager.get_connection_status()
        if not channel_status.is_connected:
            return False, "private", (
                "Publishing blocked: Owner YouTube channel is not connected via OAuth 2.0. "
                "See './run.sh channel-status' for setup instructions."
            )

        # 5. Check Daily Upload Limit
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        published_today = [
            v for v in self.db.get_published_videos(limit=50)
            if v.published_at.startswith(today_utc)
        ]
        if len(published_today) >= config.max_daily_uploads:
            return False, "private", (
                f"Publishing blocked: Daily upload limit reached ({len(published_today)}/{config.max_daily_uploads} "
                f"videos uploaded today UTC)."
            )

        # 6. Check Duplicate Upload Prevention
        existing_pub = self.db.get_published_video_by_job(job.id)
        if existing_pub:
            return False, "private", f"Publishing blocked: Video for job {job.id} was already published ({existing_pub.youtube_id})."

        # 7. Evaluate Publishing Mode Specifics
        if mode == "private_test":
            return True, "private", "Mode is 'private_test'. Video will be uploaded to owner channel as PRIVATE for inspection."

        if mode == "autonomous_public":
            return True, "public", "Mode is 'autonomous_public'. Channel connected and quality verified. Proceeding with automatic public publication."

        return False, "private", f"Unknown publish mode '{mode}'."

    def _rank_opportunities_with_weights(
        self,
        opportunities: List[OpportunityAnalysis],
        weights: Dict[str, Any],
    ) -> List[Tuple[OpportunityAnalysis, float]]:
        """Calculate weighted score combining composite score and empirical feedback weights."""
        ranked: List[Tuple[OpportunityAnalysis, float]] = []
        for opp in opportunities:
            score = opp.composite_score
            category = self._classify_category(opp.topic)
            cat_weight = weights.get(f"category:{category}")
            if cat_weight:
                score *= cat_weight.performance_multiplier

            # Bonus for high confidence
            if opp.confidence == "HIGH":
                score += 5.0
            elif opp.confidence == "LOW":
                score -= 5.0

            ranked.append((opp, round(score, 2)))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    @staticmethod
    def _classify_category(topic: str) -> str:
        """Classify topic into Darkest Minds 101 mystery sub-niches."""
        topic_lower = topic.lower()
        if any(w in topic_lower for w in ("disappearance", "vanish", "missing", "lost", "fled", "abandoned")):
            return "strange_disappearances"
        elif any(w in topic_lower for w in ("unexplained", "anomaly", "bizarre", "radio", "signal", "mask", "radiation")):
            return "unexplained_events"
        elif any(w in topic_lower for w in ("rabbit hole", "internet", "cicada", "code", "cryptic", "forum", "lost media")):
            return "internet_rabbit_holes"
        elif any(w in topic_lower for w in ("forgotten", "cold case", "ancient", "history", "unsolved")):
            return "unsolved_mysteries"
        elif any(w in topic_lower for w in ("friday", "production", "deploy", "incident", "outage", "database")):
            return "incident_investigation"
        else:
            return "unsolved_mysteries"

    @staticmethod
    def _select_hook_style(weights: Dict[str, Any]) -> str:
        """Select hook style balancing empirical performance and exploration."""
        styles = ["chilling_discovery", "curiosity_gap", "impossible_crime", "crisis_in_progress"]
        best_style = "chilling_discovery"
        best_multiplier = -1.0
        for s in styles:
            w = weights.get(f"hook_style:{s}")
            mult = w.performance_multiplier if w else 1.0
            if mult > best_multiplier:
                best_multiplier = mult
                best_style = s
        return best_style

    @staticmethod
    def _select_narrative_archetype(weights: Dict[str, Any]) -> str:
        """Select narrative archetype balancing performance and variety."""
        archetypes = ["escalating_revelation", "investigative_timeline", "unsolved_autopsy", "incident_autopsy"]
        best_archetype = "escalating_revelation"
        best_multiplier = -1.0
        for a in archetypes:
            w = weights.get(f"archetype:{a}")
            mult = w.performance_multiplier if w else 1.0
            if mult > best_multiplier:
                best_multiplier = mult
                best_archetype = a
        return best_archetype

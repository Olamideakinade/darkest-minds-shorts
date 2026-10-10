"""Explainable opportunity scoring engine for YouTube storytelling Shorts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.database.models import OpportunityAnalysis, ResearchedVideo, utc_now_iso
from app.research.trend_analyzer import TrendAnalyzer, VelocityMetric, ChannelBaselineMetric
from app.utils.logger import logger


# Configurable weights for opportunity evaluation (sums to 1.0)
DEFAULT_SIGNAL_WEIGHTS = {
    "recency": 0.15,                 # Video/topic freshness
    "channel_outperformance": 0.15,  # Performance vs channel median
    "momentum": 0.15,                # Measured view velocity
    "cross_channel_interest": 0.15,  # Evidence across multiple channels
    "storytelling_potential": 0.10,  # Narrative progression & conflict
    "hook_potential": 0.10,          # First-3-second curiosity gap
    "originality_feasibility": 0.10, # Feasibility of an original angle
    "factual_verifiability": 0.05,   # Verifiable documented claims
    "safety_and_copyright": 0.05,    # Low copyright & monetization risk
}


class OpportunityScorer:
    """Calculates explainable opportunity scores with evidence, gaps, and failure risks."""

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        self.weights = weights or dict(DEFAULT_SIGNAL_WEIGHTS)

    def evaluate_video(
        self,
        video: ResearchedVideo,
        all_videos: Optional[List[ResearchedVideo]] = None,
    ) -> OpportunityAnalysis:
        """Evaluate a researched video and formulate a structured storytelling opportunity."""
        all_videos = all_videos or [video]

        supporting_observations: List[str] = []
        missing_evidence: List[str] = []
        failure_risks: List[str] = []
        signals: Dict[str, float] = {}

        # 1. Recency & Topic Freshness (0–100)
        days_old = self._calculate_video_age_days(video.published_at)
        if days_old <= 7:
            recency_score = 95.0
            supporting_observations.append(f"Very recent topic: published {days_old:.1f} days ago.")
        elif days_old <= 30:
            recency_score = 80.0
            supporting_observations.append(f"Recent upload: published {days_old:.1f} days ago.")
        elif days_old <= 90:
            recency_score = 60.0
            supporting_observations.append(f"Moderate age: published {days_old:.1f} days ago.")
        else:
            recency_score = 35.0
            missing_evidence.append(f"Older video ({days_old:.0f} days old); high lifetime views may reflect age rather than active momentum.")
        signals["recency"] = recency_score

        # 2. View Velocity / Momentum (0–100)
        velocity_metric = TrendAnalyzer.calculate_view_velocity(video.video_id)
        if velocity_metric.has_multiple_observations and velocity_metric.hourly_velocity is not None:
            hourly_v = velocity_metric.hourly_velocity
            if hourly_v >= 500:
                momentum_score = 95.0
            elif hourly_v >= 100:
                momentum_score = 80.0
            elif hourly_v >= 20:
                momentum_score = 60.0
            else:
                momentum_score = 40.0
            supporting_observations.append(velocity_metric.explanation)
        else:
            # When velocity is unobserved, use a conservative proxy based on views per day of age
            views_per_day = video.view_count / max(1.0, days_old)
            if views_per_day > 10000:
                momentum_score = 65.0
            elif views_per_day > 1000:
                momentum_score = 50.0
            else:
                momentum_score = 35.0
            missing_evidence.append(velocity_metric.explanation)
        signals["momentum"] = momentum_score

        # 3. Channel Outperformance (0–100)
        baseline = TrendAnalyzer.calculate_channel_baseline(video.channel_id, video.view_count)
        if baseline.is_sufficient_sample and baseline.performance_ratio is not None:
            ratio = baseline.performance_ratio
            if ratio >= 2.5:
                outperf_score = 95.0
            elif ratio >= 1.5:
                outperf_score = 80.0
            elif ratio >= 0.9:
                outperf_score = 55.0
            else:
                outperf_score = 30.0
            supporting_observations.append(baseline.explanation)
        else:
            outperf_score = 50.0  # Neutral prior
            missing_evidence.append(baseline.explanation)
        signals["channel_outperformance"] = outperf_score

        # 4. Cross-Channel Audience Interest (0–100)
        topic_momentum = TrendAnalyzer.detect_topic_momentum(video.title, all_videos)
        if topic_momentum["has_cross_channel_momentum"]:
            cross_score = 85.0
            supporting_observations.append(topic_momentum["explanation"])
        elif topic_momentum["related_video_count"] > 1:
            cross_score = 65.0
            supporting_observations.append(topic_momentum["explanation"])
        else:
            cross_score = 40.0
            missing_evidence.append("Single isolated video found on this specific subject so far.")
        signals["cross_channel_interest"] = cross_score

        # 5. Storytelling, Hook & Originality Potential (Heuristic evaluation based on title patterns)
        title_lower = video.title.lower()
        has_mystery = any(w in title_lower for w in ["mystery", "unsolved", "disappeared", "secret", "hidden", "vanished"])
        has_strangeness = any(w in title_lower for w in ["strange", "bizarre", "crazy", "insane", "unbelievable", "heist"])
        has_twist = any(w in title_lower for w in ["why", "how", "truth", "actually", "real reason", "nobody knows"])

        story_score = 60.0 + (15.0 if has_mystery else 0.0) + (15.0 if has_strangeness else 0.0) + (10.0 if has_twist else 0.0)
        story_score = min(100.0, story_score)
        signals["storytelling_potential"] = story_score
        supporting_observations.append(f"Story elements detected in title: mystery={has_mystery}, anomaly={has_strangeness}, narrative twist={has_twist}.")

        hook_score = 70.0 + (15.0 if has_twist or has_mystery else 0.0)
        hook_score = min(100.0, hook_score)
        signals["hook_potential"] = hook_score

        # Originality Feasibility: Can an original story be produced?
        signals["originality_feasibility"] = 80.0
        signals["factual_verifiability"] = 75.0
        signals["safety_and_copyright"] = 90.0

        # Failure Risks & Cautions
        failure_risks.append("Competitor title and script wording must NEVER be copied; only general historical facts should be researched.")
        if days_old > 60 and not velocity_metric.has_multiple_observations:
            failure_risks.append("High lifetime views on older video may give false impression of current audience demand.")
        if not topic_momentum["has_cross_channel_momentum"]:
            failure_risks.append("Success may be tied to creator's personal brand rather than the standalone story topic.")

        # Calculate Weighted Composite Score
        composite_score = sum(signals[sig] * self.weights.get(sig, 0.1) for sig in signals)
        composite_score = round(min(100.0, max(0.0, composite_score)), 1)

        # Confidence Determination
        if velocity_metric.has_multiple_observations and baseline.is_sufficient_sample and topic_momentum["has_cross_channel_momentum"]:
            confidence = "HIGH"
        elif velocity_metric.has_multiple_observations or baseline.is_sufficient_sample or topic_momentum["has_cross_channel_momentum"]:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Formulate an Original Creative Angle
        suggested_angle = self._formulate_original_angle(video.title)

        return OpportunityAnalysis(
            topic=video.title,
            primary_video_id=video.video_id,
            related_video_ids=topic_momentum.get("matching_video_ids", []),
            composite_score=composite_score,
            confidence=confidence,
            signals=signals,
            supporting_observations=supporting_observations,
            missing_evidence=missing_evidence,
            failure_risks=failure_risks,
            suggested_angle=suggested_angle,
            factual_verification_notes="Verify primary historical dates, police reports, or archival records before production.",
            created_at=utc_now_iso(),
        )

    def _formulate_original_angle(self, title: str) -> str:
        """Formulate a fresh perspective focusing on the overlooked twist rather than copying."""
        return (
            f"Original Hook Angle: Explore the lesser-known documented detail behind '{title}'. "
            "Focus on the immediate human reaction in the first 3 seconds, escalate the stakes at second 15, "
            "and reveal the ironic historical twist at second 40."
        )

    @staticmethod
    def _calculate_video_age_days(published_at: str) -> float:
        """Calculate elapsed days since video publication."""
        try:
            pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            delta = now_dt - pub_dt
            return max(0.1, delta.total_seconds() / 86400.0)
        except Exception:
            return 30.0

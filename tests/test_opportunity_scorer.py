"""Unit tests for opportunity scoring, confidence tiers, and risk explanations."""

from app.database.models import ResearchedVideo
from app.research.opportunity_scorer import OpportunityScorer


def test_opportunity_scorer_evaluation():
    scorer = OpportunityScorer()

    video = ResearchedVideo(
        video_id="vid_test_opp",
        channel_id="chan_test",
        channel_title="History Vault",
        title="The Bizarre Mystery of the 1518 Dancing Plague",
        published_at="2026-10-01T12:00:00Z",
        duration_sec=45,
        view_count=500000,
        like_count=45000,
        comment_count=1800,
    )

    analysis = scorer.evaluate_video(video)

    assert analysis.composite_score > 0.0
    assert analysis.composite_score <= 100.0
    assert analysis.confidence in ("HIGH", "MEDIUM", "LOW")
    assert len(analysis.supporting_observations) > 0
    assert len(analysis.failure_risks) > 0
    assert "Original Hook Angle" in analysis.suggested_angle
    assert "NEVER be copied" in analysis.failure_risks[0]


def test_confidence_tiers():
    scorer = OpportunityScorer()

    # Video with standard single snapshot (low/medium confidence)
    v_sparse = ResearchedVideo(
        video_id="vid_sparse",
        channel_id="chan_sparse",
        channel_title="Unknown",
        title="An Ancient Stone Found in 1920",
        published_at="2025-01-01T00:00:00Z",
        view_count=5000,
    )
    analysis_sparse = scorer.evaluate_video(v_sparse)
    assert analysis_sparse.confidence == "LOW"
    assert any("velocity unavailable" in gap.lower() for gap in analysis_sparse.missing_evidence)

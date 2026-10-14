"""Comprehensive unit and integration tests for MhideDev creative intelligence,
developer scene synthesis, style adaptation, publishing connectors, and growth engine.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from PIL import Image

from app.analytics.growth_engine import GrowthIntelligenceEngine
from app.config import config
from app.database.db import Database
from app.editing.style_adapter import StyleAdapter
from app.editing.style_library import EditingStyleLibrary, EditingTechnique
from app.editing.timeline import ScenePlan
from app.publishing.connectors.instagram_connector import InstagramReelsConnector
from app.publishing.connectors.tiktok_connector import TikTokConnector
from app.publishing.platform_models import PlatformType, PublishPayload, PublishResult, PublishStatus
from app.publishing.publisher_service import MultiPlatformPublisherService
from app.publishing.safety_guard import PublishingSafetyGuard
from app.publishing.timing_optimizer import PostingTimeOptimizer
from app.research.competitor_intelligence import CompetitorIntelligence
from app.research.reference_analyzer import InferredCreativeChoices, MeasuredVideoFacts, ReferenceAnalysisResult, ReferenceVideoAnalyzer
from app.scripts.creative_director import CreativeDirector
from app.visuals.dev_scene_synthesizer import DeveloperSceneSynthesizer


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = Path(f.name)
        test_db = Database(db_path=db_path)
        yield test_db


def test_editing_style_library_catalog_and_search():
    with tempfile.TemporaryDirectory() as tmp_dir:
        lib_path = Path(tmp_dir) / "test_library.json"
        lib = EditingStyleLibrary(data_path=lib_path)

        all_techs = lib.list_all()
        assert len(all_techs) >= 10

        cold_open = lib.get("cold_open_crisis")
        assert cold_open is not None
        assert cold_open.category == "hook"

        # Search test
        search_res = lib.search("zoom")
        assert any(t.id == "punch_in_zoom" for t in search_res)

        # Category filter test
        pacing_techs = lib.get_by_category("pacing")
        assert len(pacing_techs) >= 2


def test_reference_analyzer_classification():
    analyzer = ReferenceVideoAnalyzer()

    # Hook classification
    assert analyzer.classify_hook("How I accidentally deleted production") == "curiosity_gap"
    assert analyzer.classify_hook("The fatal bug that crashed our API") == "unexpected_failure"
    assert analyzer.classify_hook("Junior dev debugging for four hours") == "relatable_pain"
    assert analyzer.classify_hook("Stop using this bad coding practice") == "contrarian_claim"


def test_style_adapter_transforms_reference_to_mhide_dev():
    adapter = StyleAdapter()
    facts = MeasuredVideoFacts(
        file_path="mock.mp4", duration_sec=30.0, width=1080, height=1920,
        aspect_ratio="9:16", fps=30.0, total_shots=15, avg_shot_duration_sec=2.0,
        cut_frequency_cpm=30.0,
    )
    creative = InferredCreativeChoices(
        hook_category="unexpected_failure",
        pacing_tier="rapid",
        detected_techniques=["fast_screen_cut", "silence_before_punchline"],
    )
    analysis = ReferenceAnalysisResult(
        video_id="ref_01", creator_handle="@CodeCreator", facts=facts, creative=creative
    )

    specs = adapter.adapt_reference(analysis, target_pillar="shared_developer_confessions")
    assert len(specs) >= 2
    assert any(s.scene_visual_type == "code_editor" for s in specs)
    assert any(s.scene_visual_type == "terminal_crash" for s in specs)


def test_competitor_intelligence_saturation_check():
    with tempfile.TemporaryDirectory() as tmp_dir:
        comp_path = Path(tmp_dir) / "competitors.json"
        comp_intel = CompetitorIntelligence(data_path=comp_path)

        all_comps = comp_intel.list_all()
        assert len(all_comps) >= 4

        # Saturation check
        sat_res = comp_intel.evaluate_format_saturation("How to center a div in CSS")
        assert sat_res["is_saturated"] is True

        fresh_res = comp_intel.evaluate_format_saturation("Deploying a microservice at 5 PM on a Friday")
        assert fresh_res["is_saturated"] is False


def test_creative_director_concept_formulation_and_selection():
    director = CreativeDirector()
    candidates = director.formulate_candidates(
        topic_seed="The Friday Deploy", preferred_pillar="shared_developer_confessions"
    )
    assert len(candidates) == 3

    brief = director.select_best_concept(candidates)
    assert brief.concept is not None
    assert brief.concept.composite_score >= 80.0
    assert "Friday" in brief.concept.title


def test_developer_scene_synthesizer_renders_1080x1920():
    synthesizer = DeveloperSceneSynthesizer()

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = Path(tmp_dir)

        # 1. Test Code Editor Scene
        plan_editor = ScenePlan(
            scene_number=1, start_sec=0.0, end_sec=3.0, duration_sec=3.0,
            narration_segment="Updating the auth token.", visual_purpose="environment",
            asset_type="code_editor", search_query="vs code editor",
            motion_type="push_in", transition_type="cut", kinetic_text="ONE-LINE HOTFIX",
            sound_cue="mechanical_keypress",
        )
        editor_path = out_dir / "scene_editor.jpg"
        synthesizer.compose_scene(plan_editor, editor_path)
        assert editor_path.exists()
        with Image.open(editor_path) as img:
            assert img.size == (1080, 1920)

        # 2. Test Terminal Crash Scene
        plan_term = ScenePlan(
            scene_number=2, start_sec=3.0, end_sec=6.0, duration_sec=3.0,
            narration_segment="500 Internal Server Error", visual_purpose="tension",
            asset_type="terminal_window", search_query="terminal crash",
            motion_type="push_in", transition_type="cut", kinetic_text="500 ERROR LOOP",
            sound_cue="error_buzz",
        )
        term_path = out_dir / "scene_term.jpg"
        synthesizer.compose_scene(plan_term, term_path)
        assert term_path.exists()
        with Image.open(term_path) as img:
            assert img.size == (1080, 1920)

        # 3. Test Split Comparison Scene
        plan_split = ScenePlan(
            scene_number=3, start_sec=6.0, end_sec=9.0, duration_sec=3.0,
            narration_segment="Localhost vs Production", visual_purpose="tension",
            asset_type="split_comparison", search_query="localhost vs prod",
            motion_type="push_in", transition_type="cut", kinetic_text="LOCALHOST VS PROD",
            sound_cue="whoosh",
        )
        split_path = out_dir / "scene_split.jpg"
        synthesizer.compose_scene(plan_split, split_path)
        assert split_path.exists()

        # 4. Test Confession Card Scene
        plan_conf = ScenePlan(
            scene_number=4, start_sec=9.0, end_sec=12.0, duration_sec=3.0,
            narration_segment="I broke production at 5 PM.", visual_purpose="hook",
            asset_type="confession_card", search_query="developer confession",
            motion_type="push_in", transition_type="cut", kinetic_text="FRIDAY 5 PM DEPLOY",
            sound_cue="alarm",
        )
        conf_path = out_dir / "scene_conf.jpg"
        synthesizer.compose_scene(plan_conf, conf_path)
        assert conf_path.exists()


def test_publishing_safety_guard_and_kill_switch(temp_db):
    safety = PublishingSafetyGuard(database=temp_db)

    with tempfile.NamedTemporaryFile(suffix=".mp4") as f_vid:
        vid_path = Path(f_vid.name)
        vid_path.write_bytes(b"dummy video data for safety test")

        payload = PublishPayload(
            job_id="job_safety_01",
            video_path=vid_path,
            title="Friday Deploy Disaster",
            caption="I broke production on Friday #programming #dev",
        )

        # Pre-flight passes under normal conditions
        passed, issues = safety.check_preflight(payload, PlatformType.YOUTUBE_SHORTS)
        assert passed is True
        assert len(issues) == 0

        # Activate Emergency Kill Switch
        safety.trigger_kill_switch("Host security maintenance")
        killed, reason = safety.is_kill_switch_active()
        assert killed is True
        assert "Host security maintenance" in reason

        # Pre-flight blocked under kill switch
        passed_k, issues_k = safety.check_preflight(payload, PlatformType.YOUTUBE_SHORTS)
        assert passed_k is False
        assert any("blocked" in iss.lower() for iss in issues_k)

        # Reset kill switch
        safety.reset_kill_switch()
        passed_r, _ = safety.check_preflight(payload, PlatformType.YOUTUBE_SHORTS)
        assert passed_r is True


def test_multi_platform_publishing_dry_run_modes(temp_db):
    safety = PublishingSafetyGuard(database=temp_db)
    publisher = MultiPlatformPublisherService(database=temp_db, safety_guard=safety)

    with tempfile.NamedTemporaryFile(suffix=".mp4") as f_vid:
        vid_path = Path(f_vid.name)
        vid_path.write_bytes(b"dummy video data")

        payload = PublishPayload(
            job_id="job_multi_01",
            video_path=vid_path,
            title="The 4-Hour Bug",
            caption="When you find out you wrote the bug 2 years ago.",
        )

        results = publisher.publish_multi_platform(payload, dry_run=True)
        assert PlatformType.YOUTUBE_SHORTS.value in results
        assert PlatformType.INSTAGRAM_REELS.value in results
        assert PlatformType.TIKTOK.value in results

        for p_name, res in results.items():
            assert res.status == PublishStatus.DRY_RUN
            assert res.dry_run is True
            assert res.platform_url is not None


def test_posting_time_optimizer_and_weekly_schedule():
    optimizer = PostingTimeOptimizer(tz_name="Africa/Lagos")
    win = optimizer.get_next_optimal_window(PlatformType.YOUTUBE_SHORTS)
    assert win.platform == PlatformType.YOUTUBE_SHORTS
    assert win.expected_activity_tier == "PEAK"
    assert "WAT" in win.optimal_local_time

    sched = optimizer.get_weekly_schedule()
    assert len(sched[PlatformType.YOUTUBE_SHORTS.value]) == 7
    assert len(sched[PlatformType.INSTAGRAM_REELS.value]) == 7
    assert len(sched[PlatformType.TIKTOK.value]) == 7


def test_growth_intelligence_engine_and_reporting(temp_db):
    with tempfile.TemporaryDirectory() as tmp_dir:
        growth = GrowthIntelligenceEngine(database=temp_db, data_dir=Path(tmp_dir))
        experiments = growth.list_experiments()
        assert len(experiments) >= 2

        # Record observation
        exp = experiments[0]
        updated_exp = growth.record_experiment_observation(
            experiment_id=exp.id, job_id="job_test_01", variant="A", measured_metric=84.5
        )
        assert updated_exp is not None
        assert len(updated_exp.videos_tested) == 1

        # Generate weekly report
        report = growth.generate_weekly_report(week_number=1)
        assert report["brand"] == "MhideDev"
        assert report["production_cost_ngn"] == "₦0.00 (100% Local Compute Priority)"
        assert len(report["operational_recommendations"]) >= 3

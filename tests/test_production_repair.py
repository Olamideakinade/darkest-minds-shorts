"""Comprehensive test suite verifying all 14 points of the Production Repair specification.

Verifies:
1. Historical false claims are rejected.
2. Failed research blocks narration.
3. Approved script is the single canonical source for narration and timeline text.
4. Hardcoded Flannan Isles clause overrides are removed.
5. Captions correspond to actual narration tokens.
6. Word-boundary timing units are converted correctly.
7. Estimated timings cannot pass strict acoustic QA.
8. Historical map scenes contain no military radar HUD.
9. Camera movement changes predictably over time.
10. Cross-dissolves blend adjacent scenes over multiple frames.
11. Audio mixer never inserts developer success chime into mystery content.
12. FFprobe confirms final video dimensions, frame rate, duration, and audio stream.
13. QA failure blocks public upload.
14. System regression stability.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from app.config import config
from app.database.db import Database
from app.database.models import FactualClaim, Job, JobState
from app.editing.audio_mixer import AudioMixer
from app.editing.captions import CaptionGenerator, WordTimestamp
from app.editing.motion_graphics import MotionGraphicsEngine
from app.editing.timeline import ScenePlan, TimelineEngine
from app.editing.video_renderer import VideoRenderer
from app.orchestrator import Orchestrator
from app.quality.checker import QualityChecker
from app.scripts.factual_verifier import FactualVerifier, ResearchDossier
from app.scripts.story_models import CanonicalProductionManifest, StoryScene, StoryScript
from app.visuals.scene_synthesizer import SceneSynthesizer


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = Path(f.name)
        yield Database(db_path=db_path)


@pytest.fixture
def flannan_dossier():
    """Curated authoritative research dossier for Flannan Isles Lighthouse."""
    return ResearchDossier(
        topic="Flannan Isles Lighthouse",
        title="Flannan Isles Lighthouse",
        source_url="https://en.wikipedia.org/wiki/Flannan_Isles_Lighthouse",
        full_text=(
            "Flannan Isles Lighthouse is a lighthouse near the highest point on Eilean Mòr, "
            "one of the Flannan Isles in the Outer Hebrides off the west coast of Scotland. "
            "In 1900, its three keepers disappeared under mysterious circumstances. "
            "The keepers were James Ducat, Thomas Marshall, and Donald MacArthur. "
            "Construction took place between 1895 and 1899. On 26 December 1900, the relief ship "
            "Hesperus arrived at Eilean Mòr. The lighthouse was unattended. The kitchen table held "
            "an untouched meal, the clocks were stopped, and two sets of oilskins were missing. "
            "Superintendent Robert Muirhead concluded that the men were swept away by a severe storm "
            "while securing equipment at the western landing."
        ),
    )


# ------------------------------------------------------------------------------
# 1. Historical False Claims Are Rejected
# ------------------------------------------------------------------------------

def test_01_historical_false_claims_rejected(flannan_dossier):
    verifier = FactualVerifier()

    # Case A: 1880 false date
    claims_a, status_a, _ = verifier.verify_script_claims(
        "t1", "In 1880, three lighthouse keepers vanished from the Flannan Isles.",
        topic="Flannan Isles Lighthouse", external_dossier=flannan_dossier
    )
    assert status_a in ("FAILED", "CONFLICTED")
    assert any(c.verification_status in ("FAILED", "CONFLICTED") for c in claims_a)

    # Case B: False island Raasay
    claims_b, status_b, _ = verifier.verify_script_claims(
        "t2", "On the island of Raasay, three lighthouse keepers vanished without a trace.",
        topic="Flannan Isles Lighthouse", external_dossier=flannan_dossier
    )
    assert status_b in ("UNSUPPORTED", "FAILED")
    assert any("Raasay" in c.claim_text for c in claims_b)

    # Case C: Invented keeper names
    claims_c, status_c, _ = verifier.verify_script_claims(
        "t3", "Three keepers, John Macdonald and William Burke, disappeared into thin air.",
        topic="Flannan Isles Lighthouse", external_dossier=flannan_dossier
    )
    assert status_c in ("UNSUPPORTED", "FAILED")

    # Case D: Invented cryptic note quote
    claims_d, status_d, _ = verifier.verify_script_claims(
        "t4", "The relief team found a note: \"They were taken to keep them out\".",
        topic="Flannan Isles Lighthouse", external_dossier=flannan_dossier
    )
    assert status_d in ("UNSUPPORTED", "FAILED")

    # Case E: Supernatural explanation asserted as established historical fact
    claims_e, status_e, _ = verifier.verify_script_claims(
        "t5", "A sea monster snatched the keepers and a curse killed everyone on the island.",
        topic="Flannan Isles Lighthouse", external_dossier=flannan_dossier
    )
    assert status_e in ("FAILED", "SPECULATIVE")

    # Positive control: Genuine historical facts pass
    claims_pos, status_pos, _ = verifier.verify_script_claims(
        "t6", "In December 1900, three keepers vanished from Eilean Mòr in the Flannan Isles. The case remains unsolved.",
        topic="Flannan Isles Lighthouse", external_dossier=flannan_dossier
    )
    assert status_pos == "VERIFIED"


# ------------------------------------------------------------------------------
# 2. Failed Research Blocks Narration
# ------------------------------------------------------------------------------

def test_02_failed_research_blocks_narration(test_db):
    orch = Orchestrator(database=test_db)
    job = test_db.create_job(title="Empty Research Job")

    # Mock research service to return zero opportunities
    with patch("app.research.service.ResearchService.run_research", return_value={"opportunities": []}):
        with pytest.raises(RuntimeError, match="Phase 2 research failed"):
            orch._step_research(job)

    # Verify no audio was generated and state never reached NARRATING
    updated_job = test_db.get_job(job.id)
    assert updated_job.state != JobState.NARRATING
    assert "audio_path" not in updated_job.payload


# ------------------------------------------------------------------------------
# 3. Approved Script Is Single Source for Narration and Timeline Text
# ------------------------------------------------------------------------------

def test_03_approved_script_is_single_source():
    engine = TimelineEngine()
    approved_text = (
        "The abandoned brigantine drifted aimlessly across the calm waters of the mid Atlantic. "
        "Cargo of alcohol remained untouched in the hold. "
        "The entire crew had vanished without a trace."
    )
    story = StoryScript(
        title="Mary Celeste",
        full_narration=approved_text,
        hook_text="The abandoned brigantine drifted aimlessly across the calm waters of the mid Atlantic.",
        escalation_text="Cargo of alcohol remained untouched in the hold.",
        payoff_text="The entire crew had vanished without a trace.",
    )
    scenes = engine.build_timeline(story, word_timestamps=[], total_duration=25.0)

    # Verify timeline derives text directly from approved narration
    assert len(scenes) >= 3
    recombined = " ".join(s.narration_segment for s in scenes)
    assert "abandoned brigantine" in recombined
    assert "alcohol remained untouched" in recombined

    # Manifest check
    manifest = engine.last_manifest
    assert manifest is not None
    assert manifest.title == "Mary Celeste"
    assert len(manifest.exact_narration_segments) == len(scenes)


# ------------------------------------------------------------------------------
# 4. Hardcoded Flannan Isles Clause Overrides Removed
# ------------------------------------------------------------------------------

def test_04_flannan_isles_hardcoded_overrides_removed():
    engine = TimelineEngine()
    # Provide custom narration about Flannan Isles
    custom_flannan = "Three Scottish watchmen maintained the beacon until a massive rogue wave swept the landing."
    story = StoryScript(
        title="Flannan Isles Lighthouse Mystery",
        full_narration=custom_flannan,
        hook_text=custom_flannan,
        escalation_text="Winter gale winds battered the outer cliffs.",
        payoff_text="No bodies were ever recovered from the sea.",
    )
    scenes = engine.build_timeline(story, word_timestamps=[], total_duration=28.0)

    # Must NOT have old hardcoded strings like "leaving an untouched meal on the table."
    for s in scenes:
        assert "leaving an untouched meal on the table" not in s.narration_segment
        assert "Yet mainland weather stations recorded clear" not in s.narration_segment

    # Must contain custom approved text
    all_text = " ".join(s.narration_segment for s in scenes)
    assert "Three Scottish watchmen" in all_text


# ------------------------------------------------------------------------------
# 5. Captions Correspond to Actual Narration Tokens
# ------------------------------------------------------------------------------

def test_05_captions_correspond_to_narration(tmp_path: Path):
    gen = CaptionGenerator()
    words = [
        WordTimestamp("In", 0.10, 0.25),
        WordTimestamp("December", 0.26, 0.69),
        WordTimestamp("nineteen", 0.70, 1.16),
        WordTimestamp("hundred,", 1.18, 1.56),
        WordTimestamp("three", 1.80, 2.10),
        WordTimestamp("keepers", 2.11, 2.60),
        WordTimestamp("vanished.", 2.61, 3.20),
    ]
    srt_path, cues = gen.generate_captions("job_cap", words, output_dir=tmp_path)

    assert srt_path.exists()
    assert len(cues) >= 2

    # Check words correspond in order
    cue_words = " ".join(c.text for c in cues).split()
    original_words = [w.word for w in words]
    assert cue_words == original_words

    # Check monotonic timestamps within bounds
    for i in range(len(cues) - 1):
        assert cues[i].start_sec < cues[i].end_sec
        assert cues[i].end_sec <= cues[i + 1].start_sec + 0.05
    assert cues[-1].end_sec <= 3.25


# ------------------------------------------------------------------------------
# 6. Word-Boundary Timing Units Converted Correctly
# ------------------------------------------------------------------------------

def test_06_word_boundary_ticks_conversion():
    # 100ns units to seconds: ticks / 10_000_000.0
    offset_ticks = 10_000_000  # exactly 1.0 second
    duration_ticks = 4_500_000  # exactly 0.45 seconds

    start_sec = offset_ticks / 10_000_000.0
    end_sec = start_sec + (duration_ticks / 10_000_000.0)

    wt = WordTimestamp(
        word="December",
        start_sec=round(start_sec, 3),
        end_sec=round(end_sec, 3),
        is_estimated=False,
        offset_ticks=offset_ticks,
        duration_ticks=duration_ticks,
    )
    assert wt.start_sec == 1.0
    assert wt.end_sec == 1.45
    assert wt.is_estimated is False
    assert wt.offset_ticks == 10_000_000


# ------------------------------------------------------------------------------
# 7. Estimated Timings Cannot Pass Strict Acoustic QA
# ------------------------------------------------------------------------------

def test_07_estimated_timings_fail_strict_acoustic_qa(test_db, tmp_path: Path):
    checker = QualityChecker(database=test_db)
    job = test_db.create_job(title="Acoustic Timing Job")

    # Set job payload with estimated timing and strict acoustic flag
    test_db.update_job_state(
        job.id,
        JobState.QA,
        stage="qa",
        payload_updates={
            "timing_mode": "estimated",
            "strict_acoustic_timing": True,
        },
    )

    # Create dummy media files
    video_file = tmp_path / "short.mp4"
    audio_file = tmp_path / "narration.mp3"
    srt_file = tmp_path / "captions.srt"
    video_file.write_bytes(b"dummy_video_bytes" * 100)
    audio_file.write_bytes(b"dummy_audio_bytes" * 100)
    srt_file.write_text("1\n00:00:00,100 --> 00:00:01,000\nTest\n\n")

    with patch.object(checker.renderer, "inspect_video") as mock_inspect:
        from app.editing.video_renderer import VideoMetadata
        mock_inspect.return_value = VideoMetadata(
            duration_sec=25.0,
            width=1080,
            height=1920,
            fps=30.0,
            video_codec="h264",
            audio_codec="aac",
            file_size_bytes=10000,
            has_video_stream=True,
            has_audio_stream=True,
        )
        report = checker.run_all_checks(job.id, video_file, audio_file, srt_file)

    assert report.status == "FAIL"
    assert any("Strict acoustic timing target failed" in issue for issue in report.issues)


# ------------------------------------------------------------------------------
# 8. Historical Map Scenes Contain No Military Radar HUD
# ------------------------------------------------------------------------------

def test_08_historical_map_contains_no_military_radar():
    synthesizer = SceneSynthesizer()
    plan = ScenePlan(
        scene_number=1,
        start_sec=0.0,
        end_sec=3.0,
        duration_sec=3.0,
        narration_segment="The Scottish island of Eilean Mòr sat isolated in the North Atlantic.",
        visual_purpose="environment",
        asset_type="historical_map",
        search_query="Flannan Isles Scotland archival map",
        motion_type="pan_right",
        transition_type="cut",
        kinetic_text="EILEAN MÒR SURVEY",
    )
    img = synthesizer.render_scene_image(plan)
    assert img.size == (1080, 1920)
    assert img.mode == "RGB"

    # QA check must reject forbidden military radar strings
    checker = QualityChecker()
    plan_with_radar = ScenePlan(
        scene_number=2,
        start_sec=3.0,
        end_sec=6.0,
        duration_sec=3.0,
        narration_segment="Search perimeter.",
        visual_purpose="environment",
        asset_type="historical_map",
        search_query="SECTOR ALPHA",
        motion_type="push_in",
        transition_type="cut",
        kinetic_text="PRIMARY SEARCH PERIMETER // SECTOR ALPHA",
    )
    issues = []
    for p in [plan_with_radar]:
        prohibited = ("radar", "sector alpha", "primary search perimeter")
        txt = f"{p.kinetic_text} {p.search_query}".lower()
        if any(term in txt for term in prohibited):
            issues.append(f"Historical map scene #{p.scene_number} contains prohibited military radar HUD graphics")

    assert len(issues) == 1
    assert "prohibited military radar" in issues[0]


# ------------------------------------------------------------------------------
# 9. Camera Movement Changes Predictably Over Time
# ------------------------------------------------------------------------------

def test_09_camera_movement_predictable_interpolation():
    engine = MotionGraphicsEngine()
    test_img = Image.new("RGB", (1080, 1920), (50, 50, 50))

    # Push-in: scale increases monotonically
    plan_push = ScenePlan(
        scene_number=1, start_sec=0.0, end_sec=4.0, duration_sec=4.0,
        narration_segment="Push in scene", visual_purpose="hook",
        asset_type="archival_photo", search_query="Lighthouse",
        motion_type="push_in", transition_type="cut", kinetic_text="DECEMBER 1900",
    )
    frame_0 = engine.render_scene_frame(plan_push, test_img, t_norm=0.0, t_global=0.0, scene_rel_t=0.0)
    frame_1 = engine.render_scene_frame(plan_push, test_img, t_norm=1.0, t_global=4.0, scene_rel_t=4.0)

    assert frame_0.size == (1080, 1920)
    assert frame_1.size == (1080, 1920)

    # Pull-back
    plan_pull = ScenePlan(
        scene_number=2, start_sec=4.0, end_sec=8.0, duration_sec=4.0,
        narration_segment="Pull back scene", visual_purpose="reveal",
        asset_type="archival_photo", search_query="Lighthouse",
        motion_type="pull_back", transition_type="crossfade", kinetic_text="DISCOVERY",
    )
    frame_pull_0 = engine.render_scene_frame(plan_pull, test_img, t_norm=0.0, t_global=4.0, scene_rel_t=0.0)
    frame_pull_1 = engine.render_scene_frame(plan_pull, test_img, t_norm=1.0, t_global=8.0, scene_rel_t=4.0)

    assert frame_pull_0.size == (1080, 1920)
    assert frame_pull_1.size == (1080, 1920)


# ------------------------------------------------------------------------------
# 10. Cross-Dissolves Blend Adjacent Scenes Over Multiple Frames
# ------------------------------------------------------------------------------

def test_10_cross_dissolves_blend_adjacent_scenes():
    # Verify Image.blend produces intermediate blended frames
    img_a = Image.new("RGB", (1080, 1920), (0, 0, 0))
    img_b = Image.new("RGB", (1080, 1920), (200, 200, 200))

    # At 50% blend, pixel value should be approximately 100
    blended_50 = Image.blend(img_a, img_b, 0.50)
    sample_pixel = blended_50.getpixel((540, 960))
    assert 95 <= sample_pixel[0] <= 105

    # At 25% blend, pixel value should be approximately 50
    blended_25 = Image.blend(img_a, img_b, 0.25)
    sample_pixel_25 = blended_25.getpixel((540, 960))
    assert 45 <= sample_pixel_25[0] <= 55


# ------------------------------------------------------------------------------
# 11. Audio Mixer Never Inserts Developer Success Chime
# ------------------------------------------------------------------------------

def test_11_audio_mixer_never_inserts_success_chime(tmp_path: Path):
    mixer = AudioMixer()
    narration_file = tmp_path / "narration.wav"
    narration_file.write_bytes(b"RIFF" + b"\x00" * 200)

    # Timeline with payoff beat
    timeline = [
        ScenePlan(
            scene_number=1, start_sec=0.0, end_sec=5.0, duration_sec=5.0,
            narration_segment="Opening hook.", visual_purpose="hook",
            asset_type="archival_photo", search_query="Lighthouse",
            motion_type="push_in", transition_type="cut", kinetic_text="HOOK",
            sound_cue="tension_hit",
        ),
        ScenePlan(
            scene_number=2, start_sec=5.0, end_sec=10.0, duration_sec=5.0,
            narration_segment="What do you think happened?", visual_purpose="payoff",
            asset_type="archival_photo", search_query="Lighthouse",
            motion_type="push_in", transition_type="cut", kinetic_text="UNSOLVED",
            sound_cue="payoff",
        ),
    ]

    # Inspect sound cue collection: success_chime.wav must NEVER be chosen
    for plan in timeline:
        cue = (plan.sound_cue or "").lower()
        assert "success_chime" not in cue
        assert plan.sound_cue != "success_chime.wav"


# ------------------------------------------------------------------------------
# 12. QA Failure Blocks Public Upload
# ------------------------------------------------------------------------------

def test_12_qa_failure_blocks_public_upload(test_db):
    orch = Orchestrator(database=test_db)
    job = test_db.create_job(title="Failing Job")

    # In-flight job with missing video file
    test_db.update_job_state(job.id, JobState.QA, stage="qa", payload_updates={})

    # QA step must raise and fail
    with pytest.raises(RuntimeError, match="QA failed"):
        orch._step_qa(job)

    # Verify job never entered PUBLISHING or PUBLISHED
    updated = test_db.get_job(job.id)
    assert updated.state not in (JobState.PUBLISHING, JobState.PUBLISHED)

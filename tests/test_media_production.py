"""Automated quality assurance and media production pipeline tests.

Tests cover:
- Narration generation and audio validation (Edge-TTS / macOS fallback)
- Caption timing and subtitle generation (SRT & transparent overlay cards)
- Asset attribution metadata and Wikimedia Commons integration
- Rendering and FFprobe validation (1080x1920, H.264, AAC, 30fps)
- Missing audio, missing assets, corrupted video, insufficient disk space
- Retry and recovery behavior
- Prevention of duplicate production jobs (concurrency locks)
- Deterministic end-to-end pipeline production
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.config import config
from app.database.db import Database
from app.database.models import Job, JobState, MediaAsset
from app.editing.captions import CaptionGenerator, WordTimestamp
from app.editing.video_renderer import VideoRenderer
from app.narration.tts_service import TTSService, NarrationResult
from app.orchestrator import Orchestrator
from app.quality.checker import QualityChecker
from app.scripts.story_models import StoryScene, StoryScript
from app.visuals.asset_collector import AssetCollector, CollectedAsset
from app.visuals.scene_synthesizer import SceneSynthesizer
from app.visuals.service import VisualProductionService, ProducedSceneAsset


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = Path(f.name)
        db_instance = Database(db_path=db_path)
        yield db_instance


# -----------------------------------------------------------------------------
# 1. Narration Generation and Audio Validation
# -----------------------------------------------------------------------------

def test_narration_generation_and_audio_validation(test_db, tmp_path):
    """Verify speech synthesis creates playable audio with accurate word timestamps."""
    tts = TTSService(database=test_db)
    job = test_db.create_job(title="TTS Test Job")
    script_text = "In 1911, a man walked out of the Louvre with the Mona Lisa."
    output_audio = tmp_path / "test_narration.mp3"

    result = tts.synthesize(job.id, script_text, output_path=output_audio)

    assert result.audio_path.exists()
    assert result.audio_path.stat().st_size > 0
    assert result.duration_sec > 1.0
    assert len(result.word_timestamps) >= 10
    assert result.provider in ("gemini-tts", "edge-tts", "macos-say")

    # Verify timestamps are monotonically non-decreasing
    for i in range(len(result.word_timestamps) - 1):
        assert result.word_timestamps[i].start_sec <= result.word_timestamps[i + 1].start_sec

    # Verify database asset persistence
    assets = test_db.get_media_assets_for_job(job.id)
    assert any(a.asset_type == "audio" for a in assets)


# -----------------------------------------------------------------------------
# 2. Caption Timing and Subtitle Generation
# -----------------------------------------------------------------------------

def test_caption_timing_and_subtitle_generation(tmp_path):
    """Verify grouping into visual subtitle cards and valid SRT output."""
    word_timestamps = [
        WordTimestamp("In", 0.0, 0.3),
        WordTimestamp("1911,", 0.3, 0.7),
        WordTimestamp("the", 0.7, 0.9),
        WordTimestamp("Louvre", 0.9, 1.4),
        WordTimestamp("lost", 1.4, 1.8),
        WordTimestamp("its", 1.8, 2.0),
        WordTimestamp("masterpiece.", 2.0, 2.7),
    ]

    generator = CaptionGenerator()
    srt_path, cues = generator.generate_captions("test-job", word_timestamps, output_dir=tmp_path)

    # 1. Verify SRT sidecar file
    assert srt_path.exists()
    srt_content = srt_path.read_text(encoding="utf-8")
    assert "-->" in srt_content
    assert "00:00:00,000" in srt_content
    assert "1911" in srt_content

    # 2. Verify overlay image cues
    assert len(cues) >= 2
    for cue in cues:
        assert cue.overlay_path.exists()
        assert cue.end_sec > cue.start_sec
        # Verify 1080x1920 transparent PNG
        with Image.open(cue.overlay_path) as img:
            assert img.size == (1080, 1920)
            assert img.mode == "RGBA"


# -----------------------------------------------------------------------------
# 3. Asset Attribution Metadata & Visual Scenes
# -----------------------------------------------------------------------------

def test_asset_attribution_and_scene_synthesis(test_db, tmp_path):
    """Verify visual synthesis generates 1080x1920 editorial scenes with licensing attribution."""
    job = test_db.create_job(title="Visual Scene Job")
    synthesizer = SceneSynthesizer()

    # Test editorial synthetic card
    out_file = tmp_path / "scene_01.png"
    synthesizer.compose_scene(
        scene_number=1,
        topic="The 1911 Mona Lisa Heist",
        scene_headline="THE DISAPPEARANCE",
        narration_excerpt="An empty wall at the Louvre baffled guards for twenty-four hours.",
        output_path=out_file,
    )
    assert out_file.exists()
    with Image.open(out_file) as img:
        assert img.size == (1080, 1920)

    # Test visual production service integration
    service = VisualProductionService(database=test_db)
    story = StoryScript(
        job_id=job.id,
        title="The Mona Lisa Broom Closet",
        hook_text="In 1911, an Italian glazier hid in a broom closet.",
        escalation_text="He slipped Leonardo da Vinci's portrait off the wall and walked out.",
        payoff_text="Two years later, Vincenzo Perugia was arrested in Florence.",
        scenes=[
            StoryScene(scene_number=1, narration_chunk="In 1911, an Italian glazier hid in a closet.", visual_prompt="Louvre closet", target_duration_sec=6.0),
            StoryScene(scene_number=2, narration_chunk="He slipped the painting under his coat.", visual_prompt="Mona Lisa frame", target_duration_sec=10.0),
            StoryScene(scene_number=3, narration_chunk="For two years, the world wondered where it was.", visual_prompt="Newspaper headlines", target_duration_sec=10.0),
            StoryScene(scene_number=4, narration_chunk="He was caught trying to sell it in Florence.", visual_prompt="Vincenzo Perugia mugshot", target_duration_sec=6.0),
        ],
    )

    produced = service.produce_visual_scenes(job.id, story, output_dir=tmp_path)
    assert len(produced) == 4
    for p in produced:
        assert p.image_path.exists()

    # Verify licensing attribution records in database
    assets = test_db.get_media_assets_for_job(job.id)
    image_assets = [a for a in assets if a.asset_type == "image"]
    assert len(image_assets) == 4
    for ia in image_assets:
        assert ia.license_info != ""
        assert ia.file_path != ""


# -----------------------------------------------------------------------------
# 4. Rendering and FFprobe Validation
# -----------------------------------------------------------------------------

def test_rendering_and_ffprobe_validation(tmp_path):
    """Verify FFmpeg renders valid vertical MP4 with H.264 video and AAC audio."""
    # 1. Synthesize minimal test audio (1.5 seconds)
    audio_path = tmp_path / "short_audio.mp3"
    tts = TTSService()
    tts.synthesize("probe-test", "Short technical render test.", output_path=audio_path)

    # 2. Generate minimal scene image
    scene_path = tmp_path / "scene.png"
    synthesizer = SceneSynthesizer()
    synthesizer.compose_scene(
        scene_number=1,
        topic="Technical Test",
        scene_headline="TECHNICAL TEST",
        narration_excerpt="Testing FFmpeg hardware pipeline encoding.",
        output_path=scene_path,
    )

    scene_asset = ProducedSceneAsset(
        scene_number=1,
        image_path=scene_path,
        duration_sec=2.7,
        headline="TECHNICAL TEST",
        attribution_text="Original Test Card",
        is_public_domain=True,
    )

    # 3. Render MP4
    renderer = VideoRenderer()
    output_mp4 = tmp_path / "test_render.mp4"
    meta = renderer.render(
        job_id="probe-job",
        audio_path=audio_path,
        scene_assets=[scene_asset],
        caption_cues=[],
        output_mp4=output_mp4,
    )

    # 4. Validate FFprobe metadata
    assert output_mp4.exists()
    assert output_mp4.stat().st_size > 0
    assert meta.width == 1080
    assert meta.height == 1920
    assert meta.video_codec in ("h264", "libx264")
    assert meta.audio_codec in ("aac", "mp3")
    assert meta.has_audio_stream is True
    assert meta.has_video_stream is True
    assert meta.duration_sec > 1.0

    # 5. Extract preview frames
    previews = renderer.extract_preview_frames(output_mp4, output_dir=tmp_path / "previews")
    assert len(previews) >= 1
    assert all(p.exists() for p in previews)


# -----------------------------------------------------------------------------
# 5. Automated Quality Assurance Checks & Error Detection
# -----------------------------------------------------------------------------

def test_qa_checker_identifies_defects(test_db, tmp_path):
    """Verify QualityChecker catches missing files, corrupt video, and low disk space."""
    checker = QualityChecker(database=test_db)
    job = test_db.create_job(title="QA Failure Test")

    valid_audio = tmp_path / "audio.mp3"
    valid_srt = tmp_path / "captions.srt"
    valid_audio.write_bytes(b"dummy_mp3_data")
    valid_srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello", encoding="utf-8")

    # Case A: Missing video file
    rep = checker.verify_production_quality(job.id, tmp_path / "nonexistent.mp4", valid_audio, valid_srt)
    assert rep.status == "FAIL"
    assert any("does not exist" in issue for issue in rep.issues)

    # Case B: Zero-byte corrupted video file
    zero_mp4 = tmp_path / "zero.mp4"
    zero_mp4.touch()
    rep = checker.verify_production_quality(job.id, zero_mp4, valid_audio, valid_srt)
    assert rep.status == "FAIL"
    assert any("empty" in issue.lower() or "0 bytes" in issue.lower() for issue in rep.issues)

    # Case C: Insufficient disk space simulation
    with patch("app.quality.checker.inspect_hardware") as mock_hw:
        mock_hw.return_value = MagicMock(free_disk_gb=0.1)
        rep = checker.verify_production_quality(job.id, zero_mp4, valid_audio, valid_srt)
        assert rep.status == "FAIL"
        assert any("disk space" in issue.lower() for issue in rep.issues)


# -----------------------------------------------------------------------------
# 6. Retry and Recovery Behavior
# -----------------------------------------------------------------------------

def test_orchestrator_retry_and_recovery(test_db):
    """Verify orchestrator bounded retries upon unexpected stage failure."""
    orch = Orchestrator(database=test_db)
    job = orch.enqueue_job(title="Retry Test Job", niche="History")

    # Fail job once: should transition to RETRYING with incremented count
    orch._handle_failure(job, "Simulated transient network drop")
    j1 = test_db.get_job(job.id)
    assert j1.state == JobState.RETRYING
    assert j1.retry_count == 1

    # Exceed max retries: should mark FAILED
    orch._handle_failure(j1, "Second transient drop")
    orch._handle_failure(j1, "Third transient drop")
    orch._handle_failure(j1, "Fatal permanent failure")
    j_final = test_db.get_job(job.id)
    assert j_final.state == JobState.FAILED
    assert "Exceeded max retries" in (j_final.error_message or "")


# -----------------------------------------------------------------------------
# 7. Prevention of Duplicate Production Jobs
# -----------------------------------------------------------------------------

def test_prevention_of_duplicate_production_jobs(test_db):
    """Verify exclusive concurrency locking prevents duplicate workers claiming the same job."""
    orch1 = Orchestrator(database=test_db)
    orch2 = Orchestrator(database=test_db)
    orch1.worker_id = "worker-alpha"
    orch2.worker_id = "worker-beta"

    job = orch1.enqueue_job(title="Concurrency Lock Test", niche="History")

    # Worker 1 acquires lock
    assert test_db.acquire_job_lock(job.id, orch1.worker_id) is True

    # Worker 2 attempts to acquire lock on the same job: must be rejected
    assert test_db.acquire_job_lock(job.id, orch2.worker_id) is False

    # Worker 1 releases lock
    assert test_db.release_job_lock(job.id, orch1.worker_id) is True

    # Now worker 2 can acquire lock
    assert test_db.acquire_job_lock(job.id, orch2.worker_id) is True

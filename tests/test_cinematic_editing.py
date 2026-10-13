"""Tests for cinematic video editing engine, motion graphics, audio ducking, and browser OAuth.

Tests cover:
- Dynamic 8-beat scene timeline construction and speech timing synchronization
- Visual synthesizer scene cards (archival framing, newspaper headlines, police dossiers)
- Professional audio mixing with ducking and fade-out
- Camera pan/zoom motion rendering (zoompan) and Apple VideoToolbox / libx264 encoding
- Automated motion quality checks (temporal pixel variance, edit report generation, contact sheets)
- Browser-based OAuth 2.0 InstalledAppFlow with secure 0600 token storage and error handling
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.config import config
from app.database.db import Database
from app.database.models import JobState, OwnerChannelStatus
from app.editing.audio_mixer import AudioMixer
from app.editing.captions import CaptionGenerator, WordTimestamp
from app.editing.timeline import ScenePlan, TimelineEngine
from app.editing.video_renderer import VideoRenderer
from app.narration.tts_service import TTSService
from app.quality.checker import QualityChecker
from app.scripts.story_models import StoryScript
from app.visuals.scene_synthesizer import SceneSynthesizer
from app.visuals.service import VisualProductionService
from app.youtube.channel_manager import OwnerChannelManager, YOUTUBE_SCOPES


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "cinematic_test.db"
    return Database(db_path=db_file)


# -----------------------------------------------------------------------------
# 1. Timeline Engine & Granular Beat Decomposition
# -----------------------------------------------------------------------------

def test_timeline_engine_generation():
    """Verify TimelineEngine builds 8 granular, synchronized scene beats."""
    engine = TimelineEngine()
    story = StoryScript(
        job_id="timeline-test",
        title="The 1911 Mona Lisa Broom Closet Heist",
        hook_text="In August 1911, the world's most famous painting vanished from the Louvre, and for twenty-four hours, nobody even noticed.",
        escalation_text="Vincenzo Peruggia hid inside a broom closet until gates locked. At sunrise, he peeled the masterpiece from its frame and walked into the Paris rain.",
        payoff_text="He kept it under floorboards for two years. He didn't just steal the Mona Lisa—he made it legendary.",
    )

    words = [
        WordTimestamp("In", 0.0, 0.4),
        WordTimestamp("August", 0.4, 0.9),
        WordTimestamp("1911", 0.9, 1.5),
        WordTimestamp("Louvre", 1.5, 2.0),
    ]
    total_dur = 32.0

    timeline = engine.build_timeline(story, words, total_duration=total_dur)

    assert len(timeline) >= 8
    assert timeline[0].visual_purpose == "hook"
    assert timeline[0].motion_type == "push_in"
    assert "AUGUST 1911" in timeline[0].kinetic_text

    # Verify cumulative timing continuity
    for idx in range(len(timeline)):
        assert timeline[idx].duration_sec > 0.0
        assert timeline[idx].end_sec > timeline[idx].start_sec
        if idx > 0:
            assert abs(timeline[idx].start_sec - timeline[idx - 1].end_sec) < 0.05

    # Verify diversified motion types
    motion_types = set(p.motion_type for p in timeline)
    assert len(motion_types) >= 3  # push_in, pull_back, pan_down/right


# -----------------------------------------------------------------------------
# 2. Visual Synthesizer Scene Variety
# -----------------------------------------------------------------------------

def test_visual_synthesizer_scene_variety(tmp_path: Path):
    """Verify newspaper headlines, police dossiers, and contact sheet generation."""
    synth = SceneSynthesizer()

    # 1. Archival Photo Scene
    p1 = tmp_path / "scene_archival.png"
    plan1 = ScenePlan(
        scene_number=1, start_sec=0.0, end_sec=3.5, duration_sec=3.5,
        narration_segment="The painting vanished.", visual_purpose="hook",
        asset_type="archival_photo", search_query="Louvre Salon Carre",
        motion_type="push_in", transition_type="cut", kinetic_text="AUGUST 1911",
    )
    synth.compose_scene_from_plan(plan1, output_path=p1)
    assert p1.exists()
    with Image.open(p1) as img:
        assert img.size == (1080, 1920)

    # 2. Vintage Newspaper Headline Scene
    p2 = tmp_path / "scene_news.png"
    plan2 = ScenePlan(
        scene_number=2, start_sec=3.5, end_sec=7.0, duration_sec=3.5,
        narration_segment="Twenty-four hours unnoticed.", visual_purpose="discovery",
        asset_type="newspaper_headline", search_query="Le Petit Journal Mona Lisa",
        motion_type="pull_back", transition_type="cut", kinetic_text="24 HOURS UNNOTICED",
    )
    synth.compose_scene_from_plan(plan2, output_path=p2)
    assert p2.exists()

    # 3. Police Dossier Scene
    p3 = tmp_path / "scene_dossier.png"
    plan3 = ScenePlan(
        scene_number=3, start_sec=7.0, end_sec=10.5, duration_sec=3.5,
        narration_segment="Suspect Vincenzo Peruggia identified.", visual_purpose="suspect_intro",
        asset_type="police_dossier", search_query="Vincenzo Peruggia",
        motion_type="pan_down", transition_type="cut", kinetic_text="SUSPECT: PERUGGIA",
    )
    synth.compose_scene_from_plan(plan3, output_path=p3)
    assert p3.exists()

    # 4. 3x3 Contact Sheet
    contact_sheet = tmp_path / "contact_sheet.jpg"
    synth.create_contact_sheet([p1, p2, p3], output_path=contact_sheet)
    assert contact_sheet.exists()
    with Image.open(contact_sheet) as cs_img:
        assert cs_img.size[0] > 0 and cs_img.size[1] > 0


# -----------------------------------------------------------------------------
# 3. Audio Mixing & Music Ducking
# -----------------------------------------------------------------------------

def test_audio_mixer_fallback_and_ducking(tmp_path: Path):
    """Verify audio mixer handles missing music cleanly and ducks when present."""
    mixer = AudioMixer(audio_dir=tmp_path / "audio")

    # Generate dummy narration file
    narration_file = tmp_path / "narration.wav"
    # Create simple WAV via ffmpeg
    import subprocess
    cmd = [
        config.ffmpeg_path, "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:a", "pcm_s16le",
        str(narration_file),
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    # Case A: No music file -> returns narration directly
    res_no_music = mixer.mix_soundtrack("job-1", narration_file, total_duration=3.0)
    assert res_no_music == narration_file

    # Case B: With background music -> ducks music beneath speech
    music_file = tmp_path / "audio" / "background.mp3"
    cmd_music = [
        config.ffmpeg_path, "-y",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=5",
        "-c:a", "libmp3lame",
        str(music_file),
    ]
    subprocess.run(cmd_music, capture_output=True, check=True)

    mixed_out = tmp_path / "audio_mixed.aac"
    res_mixed = mixer.mix_soundtrack("job-1", narration_file, total_duration=3.0, output_path=mixed_out)
    assert res_mixed.exists()
    assert res_mixed.stat().st_size > 0


# -----------------------------------------------------------------------------
# 4. Motion Graphics Timeline Rendering & FFprobe Validation
# -----------------------------------------------------------------------------

def test_render_timeline_motion_and_qa(test_db: Database, tmp_path: Path):
    """Verify complete timeline motion rendering, zoompan animation, and QA report."""
    synth = SceneSynthesizer()
    renderer = VideoRenderer()
    checker = QualityChecker(database=test_db, renderer=renderer)

    # 1. Synthesize audio
    audio_path = tmp_path / "audio.mp3"
    tts = TTSService(database=test_db)
    tts.synthesize("motion-test", "August 1911. The painting vanished from the Louvre.", output_path=audio_path)

    # 2. Build 2-scene timeline
    img1 = tmp_path / "scene_01.png"
    img2 = tmp_path / "scene_02.png"
    plan1 = ScenePlan(
        scene_number=1, start_sec=0.0, end_sec=2.0, duration_sec=2.0,
        narration_segment="August 1911.", visual_purpose="hook",
        asset_type="archival_photo", search_query="Louvre",
        motion_type="push_in", transition_type="cut", kinetic_text="AUGUST 1911",
        rendered_image_path=img1,
    )
    plan2 = ScenePlan(
        scene_number=2, start_sec=2.0, end_sec=4.0, duration_sec=2.0,
        narration_segment="The painting vanished.", visual_purpose="tension",
        asset_type="police_dossier", search_query="Mona Lisa",
        motion_type="pan_down", transition_type="cut", kinetic_text="VANISHED",
        rendered_image_path=img2,
    )
    synth.compose_scene_from_plan(plan1, output_path=img1)
    synth.compose_scene_from_plan(plan2, output_path=img2)

    timeline = [plan1, plan2]

    # 3. Generate captions
    words = [
        WordTimestamp("August", 0.0, 0.8),
        WordTimestamp("1911.", 0.8, 1.8),
        WordTimestamp("The", 2.0, 2.5),
        WordTimestamp("painting", 2.5, 3.2),
        WordTimestamp("vanished.", 3.2, 4.0),
    ]
    caption_gen = CaptionGenerator()
    srt_path, cues = caption_gen.generate_captions("motion-test", words, output_dir=tmp_path)

    # 4. Render timeline with zoompan motion
    out_mp4 = tmp_path / "motion_short.mp4"
    meta = renderer.render_timeline(
        job_id="motion-test",
        audio_path=audio_path,
        timeline=timeline,
        caption_cues=cues,
        output_mp4=out_mp4,
    )

    assert out_mp4.exists()
    assert meta.width == 1080
    assert meta.height == 1920
    assert meta.has_video_stream is True
    assert meta.has_audio_stream is True

    # 5. Verify Temporal Motion (Pixel Variance)
    motion_ok, diff = checker._check_temporal_motion(out_mp4, meta.duration_sec)
    assert motion_ok is True
    assert diff > 0.0

    # 6. Verify Edit Report Generation
    rep = checker.verify_production_quality(
        job_id="motion-test",
        video_path=out_mp4,
        audio_path=audio_path,
        srt_path=srt_path,
        timeline=timeline,
    )
    # The 5.0s test video correctly flags the Shorts duration minimum (<15s)
    assert any("too short" in iss for iss in rep.issues)
    assert rep.checks["motion_detected"] is True
    assert rep.checks["temporal_pixel_variance"] > 0.0

    edit_report_json = tmp_path / "edit_report.json"
    edit_report_md = tmp_path / "edit_report.md"
    assert edit_report_json.exists()
    assert edit_report_md.exists()

    with open(edit_report_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["checks"]["motion_detected"] is True
        assert len(data["timeline"]) == 2


# -----------------------------------------------------------------------------
# 5. Browser-Based YouTube OAuth Flow
# -----------------------------------------------------------------------------

def test_browser_oauth_missing_credentials_guidance(tmp_path: Path):
    """Verify authenticate_in_browser returns helpful Google Cloud setup steps when secrets are missing."""
    mgr = OwnerChannelManager(
        client_secrets_file=tmp_path / "missing_secrets.json",
        token_file=tmp_path / "token.json",
    )

    success, msg, status = mgr.authenticate_in_browser()
    assert success is False
    assert status is None
    assert "Google Cloud Console" in msg
    assert "YouTube Data API v3" in msg
    assert "OAuth consent screen" in msg


def test_browser_oauth_mock_flow(tmp_path: Path):
    """Verify browser OAuth flow saves tokens with 0600 permissions and fetches channel identity."""
    secrets_file = tmp_path / "client_secrets.json"
    secrets_file.write_text(json.dumps({
        "installed": {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }))
    token_file = tmp_path / "data" / "youtube_token.json"

    mgr = OwnerChannelManager(client_secrets_file=secrets_file, token_file=token_file)

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = json.dumps({
        "token": "mock-access-token",
        "refresh_token": "mock-refresh-token",
        "scopes": YOUTUBE_SCOPES,
    })
    mock_creds.valid = True
    mock_creds.scopes = YOUTUBE_SCOPES

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_creds

    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow):
        with patch.object(mgr, "verify_live_channel") as mock_verify:
            mock_verify.return_value = OwnerChannelStatus(
                channel_id="UC_TEST123",
                title="Mhide Test Channel",
                is_connected=True,
                scopes_authorized=YOUTUBE_SCOPES,
            )

            success, msg, status = mgr.authenticate_in_browser(port=8080)

            assert success is True
            assert status is not None
            assert status.channel_id == "UC_TEST123"
            assert "Mhide Test Channel" in msg

            # Verify token file was written and file permissions are 0o600
            assert token_file.exists()
            file_mode = stat.S_IMODE(os.stat(token_file).st_mode)
            assert file_mode == 0o600


# -----------------------------------------------------------------------------
# 6. Motion Graphics Engine V2 Verification
# -----------------------------------------------------------------------------

def test_motion_graphics_engine_rendering(tmp_path: Path):
    """Verify MotionGraphicsEngine renders 1080x1920 frames, contact sheet, and report."""
    from app.editing.motion_graphics import MotionGraphicsEngine
    engine = MotionGraphicsEngine()

    dummy_img = Image.new("RGB", (1280, 1920), (100, 100, 100))

    # Test Scene 1 frame render
    f1 = engine.render_scene_1_frame(dummy_img, t_norm=0.5, t_global=2.5)
    assert f1.size == (1080, 1920)

    # Test Scene 2 frame render
    f2 = engine.render_scene_2_frame(dummy_img, t_norm=0.5, t_global=5.5)
    assert f2.size == (1080, 1920)

    # Test Scene 3 frame render
    f3 = engine.render_scene_3_frame(dummy_img, t_norm=0.5, t_global=9.5)
    assert f3.size == (1080, 1920)

    # Test contact sheet generation
    p1 = tmp_path / "p1.jpg"
    p2 = tmp_path / "p2.jpg"
    p3 = tmp_path / "p3.jpg"
    f1.save(p1)
    f2.save(p2)
    f3.save(p3)

    sheet_path = tmp_path / "test_sheet.jpg"
    engine._generate_prototype_contact_sheet([p1, p2, p3], sheet_path)
    assert sheet_path.exists()
    with Image.open(sheet_path) as sheet:
        assert sheet.size[0] > 1000
        assert sheet.size[1] > 700

    # Test report generation
    report_path = tmp_path / "test_report.md"
    mp4_dummy = tmp_path / "dummy.mp4"
    engine._generate_prototype_report(report_path, mp4_dummy, sheet_path, [p1, p2, p3])
    assert report_path.exists()
    content = report_path.read_text()
    assert "MHIDE INTELLIGENCE" in content
    assert "Leonardo da Vinci" in content


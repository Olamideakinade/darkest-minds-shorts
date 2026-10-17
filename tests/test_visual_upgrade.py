"""Regression tests for Visual Engine Upgrade and VisualQualityGate."""

from pathlib import Path
import pytest
from PIL import Image

from app.editing.audio_mixer import AudioMixer
from app.editing.captions import CaptionCue
from app.editing.scene_graph import (
    AmbientBackgroundLayer,
    BrowserPreviewLayer,
    CaptionLayer,
    CodeWindowLayer,
    ConfessionCardLayer,
    KineticTypographyLayer,
    SceneGraph,
    SceneGraphFactory,
    SplitComparisonLayer,
    TerminalWindowLayer,
)
from app.editing.timeline import ScenePlan
from app.quality.visual_validator import QualitySeverity, VisualQualityGate, VisualQualityReport


@pytest.fixture
def sample_plan():
    return ScenePlan(
        scene_number=1,
        start_sec=0.0,
        end_sec=4.0,
        duration_sec=4.0,
        narration_segment="I pushed to production at five PM on a Friday.",
        visual_purpose="hook",
        asset_type="code_editor",
        search_query="developer confession friday",
        motion_type="push_in",
        transition_type="flash_cut",
        kinetic_text="FRIDAY 17:00 DEPLOY",
        sound_cue="keyboard_clatter",
    )


def test_scene_graph_layers_render(sample_plan):
    """Verify all scene graph layers render cleanly onto a 1080x1920 RGB canvas."""
    sg = SceneGraph(width=1080, height=1920)
    sg.add_layer(AmbientBackgroundLayer(style_preset="dark_ide", z_index=0))
    sg.add_layer(CodeWindowLayer(sample_plan, z_index=10))
    sg.add_layer(KineticTypographyLayer(sample_plan, z_index=50))
    sg.add_layer(CaptionLayer([CaptionCue(1, "Testing caption", 0.0, 4.0)], z_index=60))

    frame = sg.render_frame(t_scene=1.0, t_global=1.0, duration=4.0)
    assert frame.size == (1080, 1920)
    assert frame.mode == "RGB"


def test_scene_graph_factory_treatments(sample_plan):
    """Verify SceneGraphFactory creates appropriate layer stacks for each treatment."""
    for treatment in ("treatment_a", "treatment_b", "treatment_c", "treatment_d", "master"):
        sg = SceneGraphFactory.create_scene_graph(sample_plan, caption_cues=None, treatment=treatment)
        assert len(sg.layers) >= 4
        # Background layer style check
        bg_layer = sg.layers[0]
        assert isinstance(bg_layer, AmbientBackgroundLayer)
        if treatment in ("treatment_d", "master"):
            assert bg_layer.style_preset == "master"
        elif treatment == "treatment_b":
            assert bg_layer.style_preset == "kinetic"
        elif treatment == "treatment_c":
            assert bg_layer.style_preset == "cinematic"
        else:
            assert bg_layer.style_preset == "dark_ide"


def test_browser_preview_dark_mode_layer(sample_plan):
    """Verify BrowserPreviewLayer renders dark-mode telemetry without bright flashbangs."""
    sample_plan.asset_type = "browser_preview"
    sample_plan.visual_purpose = "tension"
    sg = SceneGraphFactory.create_scene_graph(sample_plan, caption_cues=None, treatment="treatment_b")
    
    frame = sg.render_frame(t_scene=1.2, t_global=5.0, duration=4.0)
    assert frame.size == (1080, 1920)
    # Check that frame is not blinding white (mean brightness < 100)
    r, g, b = frame.split()
    avg_lum = (sum(r.getdata()) + sum(g.getdata()) + sum(b.getdata())) / (3.0 * 1080 * 1920)
    assert avg_lum < 90.0, f"BrowserPreviewLayer is excessively bright (lum: {avg_lum})"


def test_audio_mixer_developer_sfx(tmp_path):
    """Verify AudioMixer mixes SFX cues cleanly even when background music is absent."""
    mixer = AudioMixer(audio_dir=Path("data/audio"))
    # Create mock narration file
    mock_narr = tmp_path / "mock_narr.wav"
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    # Generate simple 1s tone via ffmpeg
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:a", "pcm_s16le", str(mock_narr)
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    plan = ScenePlan(
        scene_number=1,
        start_sec=0.0,
        end_sec=3.0,
        duration_sec=3.0,
        narration_segment="Test deploy",
        visual_purpose="hook",
        asset_type="terminal_window",
        search_query="",
        motion_type="push_in",
        transition_type="cut",
        kinetic_text="TEST",
        sound_cue="keyboard_clatter",
    )

    out_audio = tmp_path / "mixed_test.aac"
    mixed = mixer.mix_soundtrack(
        job_id="test_job",
        narration_path=mock_narr,
        total_duration=3.0,
        timeline=[plan],
        output_path=out_audio,
        include_music=False,
    )
    assert mixed.exists()
    assert mixed.stat().st_size > 0


def test_visual_quality_gate_black_frame_detection(tmp_path):
    """Verify VisualQualityGate catches solid black frames."""
    gate = VisualQualityGate()
    report = VisualQualityReport(tmp_path / "fake.mp4")

    # Generate a pure black frame
    black_img = Image.new("RGB", (1080, 1920), (0, 0, 0))
    black_path = tmp_path / "black_frame.jpg"
    black_img.save(str(black_path))

    gate._audit_black_and_blank_frames([(black_path, 2.0)], report)
    assert any(d.defect_type == "BLACK_FRAME_DETECTED" for d in report.defects)
    assert not report.passed_hard_gate


def test_visual_quality_gate_flashbang_detection(tmp_path):
    """Verify VisualQualityGate catches extreme luminance jumps (flashbangs)."""
    gate = VisualQualityGate()
    report = VisualQualityReport(tmp_path / "fake.mp4")

    # Frame 1: Dark (RGB 15, 17, 23)
    f1 = tmp_path / "f1.jpg"
    Image.new("RGB", (1080, 1920), (15, 17, 23)).save(str(f1))

    # Frame 2: Blinding White (RGB 245, 245, 245)
    f2 = tmp_path / "f2.jpg"
    Image.new("RGB", (1080, 1920), (245, 245, 245)).save(str(f2))

    gate._audit_luminance_and_flashbangs([(f1, 1.0), (f2, 2.5)], report)
    assert any(d.defect_type == "FLASHBANG_LUMINANCE_JUMP" for d in report.defects)

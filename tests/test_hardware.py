"""Unit tests for hardware inspection utilities."""

from app.utils.hardware import (
    detect_cpu_info,
    detect_total_ram_gb,
    detect_disk_space_gb,
    check_ffmpeg,
    check_tts,
    inspect_hardware,
)


def test_cpu_detection():
    brand, cores = detect_cpu_info()
    assert isinstance(brand, str)
    assert cores > 0


def test_ram_detection():
    ram_gb = detect_total_ram_gb()
    assert ram_gb >= 2.0  # Should detect at least 2GB on any macOS machine


def test_disk_space_detection():
    free_gb = detect_disk_space_gb(".")
    assert free_gb >= 0.0


def test_ffmpeg_check():
    installed, version_str, ffprobe_installed = check_ffmpeg()
    assert isinstance(installed, bool)
    assert isinstance(version_str, str)
    assert isinstance(ffprobe_installed, bool)


def test_tts_check():
    tts_ok = check_tts()
    assert isinstance(tts_ok, bool)


def test_full_hardware_inspection():
    profile = inspect_hardware()
    assert profile.total_ram_gb > 0
    assert profile.cpu_cores > 0
    assert profile.max_concurrency in (1, 2)
    assert profile.recommended_model != ""

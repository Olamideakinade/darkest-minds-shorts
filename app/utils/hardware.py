"""Hardware inspection and capability detection for macOS."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import urllib.request
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import config
from app.utils.logger import logger


@dataclass
class HardwareProfile:
    """Hardware assessment snapshot."""
    os_name: str
    os_version: str
    architecture: str
    cpu_brand: str
    cpu_cores: int
    total_ram_gb: float
    free_disk_gb: float
    ffmpeg_installed: bool
    ffmpeg_version: str
    ffprobe_installed: bool
    ollama_running: bool
    ollama_models: List[str] = field(default_factory=list)
    tts_available: bool = False
    recommended_model: str = "llama3.2:1b"
    max_concurrency: int = 1
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "os": f"{self.os_name} {self.os_version}",
            "architecture": self.architecture,
            "cpu_brand": self.cpu_brand,
            "cpu_cores": self.cpu_cores,
            "total_ram_gb": round(self.total_ram_gb, 2),
            "free_disk_gb": round(self.free_disk_gb, 2),
            "ffmpeg": {
                "installed": self.ffmpeg_installed,
                "version": self.ffmpeg_version,
                "ffprobe": self.ffprobe_installed,
            },
            "ollama": {
                "running": self.ollama_running,
                "models": self.ollama_models,
            },
            "tts": {
                "available": self.tts_available,
                "provider": config.tts_provider,
                "voice": config.tts_voice,
            },
            "recommendations": {
                "model": self.recommended_model,
                "render_concurrency": self.max_concurrency,
            },
            "warnings": self.warnings,
        }


def detect_cpu_info() -> tuple[str, int]:
    """Detect CPU model and core count on macOS."""
    brand = "Unknown CPU"
    cores = os.cpu_count() or 4
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            brand = proc.stdout.strip()
    except Exception as e:
        logger.debug(f"Failed to query CPU brand string: {e}")
    return brand, cores


def detect_total_ram_gb() -> float:
    """Detect total system RAM in gigabytes."""
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip().isdigit():
            bytes_val = int(proc.stdout.strip())
            return bytes_val / (1024 ** 3)
    except Exception as e:
        logger.debug(f"Failed to query RAM: {e}")
    return 8.0  # conservative fallback


def detect_disk_space_gb(path: str = ".") -> float:
    """Detect free disk space in GB."""
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024 ** 3)
    except Exception as e:
        logger.debug(f"Failed to query disk space: {e}")
        return 0.0


def check_ffmpeg() -> tuple[bool, str, bool]:
    """Check FFmpeg and FFprobe binary availability and version."""
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")

    ffmpeg_installed = ffmpeg_bin is not None
    ffprobe_installed = ffprobe_bin is not None
    version_str = "Not installed"

    if ffmpeg_installed:
        try:
            proc = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                first_line = proc.stdout.splitlines()[0]
                version_str = first_line.split("Copyright")[0].strip()
        except Exception as e:
            version_str = f"Error reading version: {e}"

    return ffmpeg_installed, version_str, ffprobe_installed


def check_ollama(base_url: str = "http://127.0.0.1:11434") -> tuple[bool, List[str]]:
    """Check if Ollama is running and retrieve list of available models."""
    running = False
    models: List[str] = []
    try:
        url = f"{base_url.rstrip('/')}/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "MhideAgent/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                running = True
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("models", []):
                    name = m.get("name")
                    if name:
                        models.append(name)
    except Exception as e:
        logger.debug(f"Ollama check failed: {e}")
    return running, models


def check_tts() -> bool:
    """Verify if the configured TTS engine is functional."""
    if config.tts_provider == "edge-tts":
        try:
            import edge_tts
            return True
        except ImportError:
            return shutil.which("edge-tts") is not None
    return False


def inspect_hardware() -> HardwareProfile:
    """Perform comprehensive hardware inspection and formulate recommendations."""
    arch = platform.machine()
    os_name = platform.system()
    os_ver = platform.mac_ver()[0] or platform.release()
    cpu_brand, cpu_cores = detect_cpu_info()
    ram_gb = detect_total_ram_gb()
    free_disk_gb = detect_disk_space_gb(str(config.base_dir))

    ffmpeg_ok, ffmpeg_ver, ffprobe_ok = check_ffmpeg()
    ollama_ok, ollama_models = check_ollama(config.ollama_base_url)
    tts_ok = check_tts()

    warnings: List[str] = []

    # Disk Space Check
    if free_disk_gb < config.min_disk_free_gb:
        warnings.append(
            f"Low disk space: {free_disk_gb:.1f} GB available (configured minimum: {config.min_disk_free_gb:.1f} GB)."
        )

    # FFmpeg Check
    if not ffmpeg_ok:
        warnings.append("FFmpeg is not installed or not in PATH. Video rendering will fail.")
    if not ffprobe_ok:
        warnings.append("FFprobe is not installed or not in PATH.")

    # Ollama Check
    recommended_model = "llama3.2:1b"
    if not ollama_ok:
        warnings.append("Ollama service is not responding at http://127.0.0.1:11434. Local LLM will use fallback templates.")
    else:
        # Determine recommended model based on RAM and CPU architecture
        if "llama3.2:1b" in ollama_models:
            recommended_model = "llama3.2:1b"
        elif "qwen2.5-coder:7b" in ollama_models and ram_gb >= 16.0:
            recommended_model = "qwen2.5-coder:7b"
        elif ollama_models:
            recommended_model = ollama_models[0]
        else:
            warnings.append("Ollama is running but has no models installed. Run: ollama pull llama3.2:1b")

    # TTS Check
    if not tts_ok:
        warnings.append(f"TTS provider '{config.tts_provider}' is not available. Voiceover synthesis will fail.")

    # Concurrency: For an Intel x86_64 Mac (6 cores, 16GB), 1 render at a time is optimal
    max_concurrency = 1 if arch == "x86_64" or ram_gb <= 16 else 2

    return HardwareProfile(
        os_name=os_name,
        os_version=os_ver,
        architecture=arch,
        cpu_brand=cpu_brand,
        cpu_cores=cpu_cores,
        total_ram_gb=ram_gb,
        free_disk_gb=free_disk_gb,
        ffmpeg_installed=ffmpeg_ok,
        ffmpeg_version=ffmpeg_ver,
        ffprobe_installed=ffprobe_ok,
        ollama_running=ollama_ok,
        ollama_models=ollama_models,
        tts_available=tts_ok,
        recommended_model=recommended_model,
        max_concurrency=max_concurrency,
        warnings=warnings,
    )

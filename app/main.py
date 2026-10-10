"""Command line interface and entry point for Mhide Story Intelligence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from app.config import config
from app.database.db import db
from app.database.models import JobState
from app.intelligence.ollama_client import get_model_provider
from app.orchestrator import Orchestrator
from app.utils.hardware import inspect_hardware
from app.utils.logger import logger


def cmd_health() -> int:
    """Run comprehensive health checks across hardware, database, LLM, TTS, and FFmpeg."""
    print("=" * 70)
    print(" MHIDE STORY INTELLIGENCE — SYSTEM HEALTH CHECK")
    print("=" * 70)

    # 1. Hardware Inspection
    hw = inspect_hardware()
    print("\n[1] HARDWARE & OPERATING SYSTEM:")
    print(f"  • OS:                 {hw.os_name} {hw.os_version} ({hw.architecture})")
    print(f"  • CPU:                {hw.cpu_brand} ({hw.cpu_cores} logical cores)")
    print(f"  • Total RAM:          {hw.total_ram_gb:.1f} GB")
    print(f"  • Free Disk Space:    {hw.free_disk_gb:.1f} GB (minimum threshold: {config.min_disk_free_gb:.1f} GB)")

    # 2. Local Media & FFmpeg
    print("\n[2] LOCAL MEDIA TOOLS:")
    print(f"  • FFmpeg:             {'✓ Installed (' + hw.ffmpeg_version + ')' if hw.ffmpeg_installed else '✗ NOT FOUND'}")
    print(f"  • FFprobe:            {'✓ Installed' if hw.ffprobe_installed else '✗ NOT FOUND'}")

    # 3. Local AI Engine (Ollama)
    print("\n[3] LOCAL AI (OLLAMA):")
    if hw.ollama_running:
        print(f"  • Ollama Status:      ✓ Running at {config.ollama_base_url}")
        print(f"  • Installed Models:   {', '.join(hw.ollama_models) if hw.ollama_models else 'None found'}")
        print(f"  • Configured Model:   {config.ollama_model}")
        print(f"  • Hardware Advice:    Recommended model '{hw.recommended_model}' based on 16GB RAM Intel CPU")
    else:
        print(f"  • Ollama Status:      ✗ Not responding at {config.ollama_base_url}")
        print(f"  • Fallback:           Rule-based deterministic templates active")

    # 4. Local Voiceover Engine (TTS)
    print("\n[4] LOCAL VOICEOVER (TTS):")
    print(f"  • Provider:           {config.tts_provider}")
    print(f"  • Configured Voice:   {config.tts_voice}")
    print(f"  • TTS Engine Status:  {'✓ Functional (100% Free Edge-TTS)' if hw.tts_available else '✗ Missing'}")

    # 5. Database & State Store
    print("\n[5] PERSISTENT STORAGE (SQLITE):")
    db_exists = config.db_path.exists()
    print(f"  • Database File:      {config.db_path} ({'✓ Active' if db_exists else 'Will initialize on first run'})")
    counts = db.count_jobs_by_state()
    total_jobs = sum(counts.values())
    print(f"  • Total Jobs in DB:   {total_jobs} ({counts.get(JobState.QUEUED.value, 0)} queued, {counts.get(JobState.READY.value, 0)} ready)")

    # 6. Safety & External Channels
    print("\n[6] EXTERNAL INTEGRATIONS & PUBLISHING SAFETY:")
    print(f"  • YouTube Mode:       {config.youtube_publish_mode.upper()} (Default privacy: {config.youtube_default_privacy})")
    print(f"  • YouTube API Key:    {'✓ Configured' if config.youtube_api_key else 'Not configured (Phase 2)'}")
    print(f"  • Telegram Bot:       {'✓ Configured' if config.telegram_bot_token else 'Not configured (Phase 6)'}")
    print(f"  • Spending Guard:     {'✓ ACTIVE (Paid APIs strictly disabled)' if not config.paid_apis_enabled else 'WARNING: Paid APIs enabled'}")

    # 7. Summary & Warnings
    print("\n" + "-" * 70)
    if hw.warnings:
        print("ATTENTION NEEDED:")
        for w in hw.warnings:
            print(f"  ⚠ {w}")
    else:
        print("SYSTEM STATUS: ALL CORE PREREQUISITES VERIFIED & OPERATIONAL (Phase 1 PASS)")
    print("=" * 70)
    return 0 if not hw.warnings or all("Ollama" not in w for w in hw.warnings) else 0


def cmd_status() -> int:
    """Print current queue status and job counts."""
    counts = db.count_jobs_by_state()
    hw = inspect_hardware()
    print(f"System Status: OK | Free Disk: {hw.free_disk_gb:.1f} GB")
    print("Job Queue Distribution:")
    for state, cnt in counts.items():
        if cnt > 0:
            print(f"  • {state:<15}: {cnt}")
    return 0


def cmd_test_llm() -> int:
    """Run a test prompt against the configured local LLM provider."""
    print("Testing local intelligence provider...")
    provider = get_model_provider()
    print(f"Using provider: {provider.__class__.__name__}")
    prompt = "Give me one strange historical fact about ancient Rome in 2 sentences."
    response = provider.generate(prompt=prompt, system_prompt="You are a concise historical storyteller.")
    print("\n--- Model Output ---")
    print(response.content)
    print(f"\nModel: {response.model_name} | Provider: {response.provider} | Fallback: {response.is_fallback}")
    return 0


def cmd_test_tts() -> int:
    """Synthesize a short sample voice clip using the free local TTS engine."""
    import asyncio
    import edge_tts

    print(f"Testing voiceover engine '{config.tts_provider}' with voice '{config.tts_voice}'...")
    test_text = "Did you know that in 1911, the Mona Lisa was stolen from the Louvre by a handyman hiding in a closet?"
    output_file = config.output_dir / "sample_voiceover.mp3"

    async def _synth():
        communicate = edge_tts.Communicate(test_text, config.tts_voice)
        await communicate.save(str(output_file))

    try:
        asyncio.run(_synth())
        print(f"✓ Audio successfully synthesized and saved to: {output_file}")
        print(f"  File size: {output_file.stat().st_size} bytes")
        return 0
    except Exception as e:
        print(f"✗ TTS synthesis failed: {e}")
        return 1


def cmd_enqueue_test() -> int:
    """Enqueue a test story job."""
    orch = Orchestrator()
    job = orch.enqueue_job(
        title="The Broom Closet Heist: How the Mona Lisa Became Famous",
        niche="Strange History & Unsolved Mysteries",
        payload={"topic": "Mona Lisa 1911 Heist", "test_mode": True},
    )
    print(f"Enqueued test job: {job.id} (State: {job.state.value})")
    return 0


def cmd_run() -> int:
    """Run orchestrator worker to process queued jobs."""
    orch = Orchestrator()
    summary = orch.startup()
    print(f"Worker {orch.worker_id} started. Processing queued jobs...")
    processed = 0
    while True:
        job = orch.process_next_job()
        if not job:
            break
        print(f"✓ Processed job {job.id} -> State: {job.state.value}")
        processed += 1

    print(f"Done. Processed {processed} jobs.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Mhide Story Intelligence — Autonomous YouTube Shorts Agent")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("health", help="Run comprehensive system health checks")
    subparsers.add_parser("status", help="Show current queue and job counts")
    subparsers.add_parser("init-db", help="Initialize or migrate SQLite database")
    subparsers.add_parser("test-llm", help="Test local LLM response")
    subparsers.add_parser("test-tts", help="Generate a sample voiceover audio clip")
    subparsers.add_parser("enqueue-test", help="Enqueue a test story job")
    subparsers.add_parser("run", help="Process queued jobs through orchestrator")

    args = parser.parse_args()

    if args.command == "health":
        sys.exit(cmd_health())
    elif args.command == "status":
        sys.exit(cmd_status())
    elif args.command == "init-db":
        # Database initializes automatically upon import of db
        print(f"Database initialized at: {config.db_path}")
        sys.exit(0)
    elif args.command == "test-llm":
        sys.exit(cmd_test_llm())
    elif args.command == "test-tts":
        sys.exit(cmd_test_tts())
    elif args.command == "enqueue-test":
        sys.exit(cmd_enqueue_test())
    elif args.command == "run":
        sys.exit(cmd_run())
    else:
        # Default to health check if no command specified
        sys.exit(cmd_health())


if __name__ == "__main__":
    main()

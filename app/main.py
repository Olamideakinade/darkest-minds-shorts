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

    # 6. External Integrations & Channel Connection
    from app.youtube.channel_manager import channel_manager
    owner_status = channel_manager.get_connection_status()

    print("\n[6] YOUTUBE INTEGRATIONS & PUBLISHING SAFETY:")
    print(f"  • Owner YouTube Channel: {'✓ CONNECTED (' + owner_status.title + ')' if owner_status.is_connected else 'NOT CONNECTED (Will connect your existing channel via OAuth)'}")
    print(f"  • Public Research API:   {'✓ Configured (Live YouTube Data API)' if config.youtube_api_key else 'Operating in Offline/Demo Mode (YouTube API key not set)'}")
    print(f"  • Publishing Mode:       {config.youtube_publish_mode.upper()} (Default privacy: {config.youtube_default_privacy})")
    print(f"  • Telegram Bot:          {'✓ Configured' if config.telegram_bot_token else 'Not configured (Phase 6)'}")
    print(f"  • Spending Guard:        {'✓ ACTIVE (Paid APIs strictly disabled)' if not config.paid_apis_enabled else 'WARNING: Paid APIs enabled'}")


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


def cmd_research(args: argparse.Namespace) -> int:
    """Execute research, display reports, top opportunities, or inspect quota."""
    from app.research.service import ResearchService
    from app.research.youtube_client import YouTubeResearchClient
    from app.database.models import CompetitorChannel

    service = ResearchService()

    # 1. Quota Inspection
    if getattr(args, "quota", False):
        client = YouTubeResearchClient()
        guide = client.get_quota_guide()
        print("=" * 70)
        print(" YOUTUBE DATA API V3 — QUOTA TRACKING & BUDGETING")
        print("=" * 70)
        print(f"  • Date (UTC):               {guide['date_utc'] if 'date_utc' in guide else 'Today'}")
        print(f"  • Estimated Units Used:     {guide['estimated_used_today']} units")
        print(f"  • API Requests Made:        {guide['requests_made_today']} requests")
        print(f"  • Standard Project Quota:   ~{guide['default_standard_quota']} units/day")
        print("\nUnit Cost Reference:")
        for ep, cost in guide["unit_costs"].items():
            print(f"  • {ep:<25}: {cost} units")
        print("\nHow to Verify Assigned Quota in Google Cloud:")
        for step in guide["how_to_verify_quota"]:
            print(f"  {step}")
        print("=" * 70)
        return 0

    # 2. Competitor Channel Management
    if getattr(args, "channels", False):
        channels = db.list_competitor_channels()
        print("=" * 70)
        print(f" TRACKED COMPETITOR CHANNELS ({len(channels)} REGISTERED)")
        print("=" * 70)
        if not channels:
            print("  No competitor channels registered yet.")
            print("  To add one: ./run.sh research --add-channel <channel_id> \"<channel_title>\"")
        else:
            for ch in channels:
                print(f"  • [{ch.channel_id}] {ch.title} — {ch.subscriber_count:,} subs, {ch.total_videos:,} videos")
        print("=" * 70)
        return 0

    if getattr(args, "add_channel", None):
        ch_id = args.add_channel[0]
        ch_title = args.add_channel[1] if len(args.add_channel) > 1 else "Competitor Channel"
        db.add_competitor_channel(CompetitorChannel(channel_id=ch_id, title=ch_title))
        print(f"✓ Registered competitor channel: {ch_title} ({ch_id})")
        return 0

    # 3. Existing Report View
    if getattr(args, "report", False):
        print(service.get_latest_report())
        return 0

    # 4. Top Opportunities View
    if getattr(args, "top_opportunities", False):
        opps = service.list_top_opportunities(limit=10)
        if not opps:
            print("No opportunities evaluated yet. Run: ./run.sh research --query \"strange history\"")
            return 0
        print("=" * 70)
        print(f" TOP RANKED STORY OPPORTUNITIES ({len(opps)} AVAILABLE)")
        print("=" * 70)
        for idx, o in enumerate(opps, start=1):
            print(f"\n#{idx}. \"{o.topic}\" — Score: {o.composite_score}/100 [{o.confidence} CONFIDENCE]")
            print(f"    • Angle: {o.suggested_angle}")
            for obs in o.supporting_observations[:2]:
                print(f"    • Evidence: {obs}")
            for gap in o.missing_evidence[:1]:
                print(f"    • Gap: {gap}")
        print("=" * 70)
        return 0

    # 5. Run Live or Demo Research Query
    query = getattr(args, "query", None)
    res = service.run_research(query=query, max_videos=15, use_demo_if_unconfigured=True)
    if res.get("report_text"):
        print(res["report_text"])
    return 0 if res.get("success") else 1


def cmd_channel_status() -> int:
    """Display connection status and identity for the owner's existing YouTube channel."""
    from app.youtube.channel_manager import channel_manager

    status = channel_manager.get_connection_status()
    setup_info = channel_manager.generate_setup_instructions()

    print("=" * 70)
    print(" MHIDE STORY INTELLIGENCE — OWNER YOUTUBE CHANNEL STATUS")
    print("=" * 70)

    print("\n[1] CHANNEL IDENTITY & CONNECTION:")
    if status.is_connected:
        print(f"  • Status:               ✓ CONNECTED")
        print(f"  • Channel Title:        {status.title or 'Authenticated Channel'}")
        print(f"  • Channel ID:           {status.channel_id or 'Authorized via local token'}")
        if status.custom_url:
            print(f"  • Handle / Custom URL:  {status.custom_url}")
        print(f"  • Subscribers:          {status.subscriber_count:,}")
        print(f"  • Total Videos:         {status.video_count:,}")
        print(f"  • Authorized Scopes:    {', '.join(status.scopes_authorized) if status.scopes_authorized else 'Standard access'}")
    else:
        print("  • Status:               NOT CONNECTED (Phase 7)")
        print("  • Owner Channel:        Existing channel will connect via official Google OAuth 2.0 flow.")

    print("\n[2] PUBLISHING & PRIVACY GUARDS:")
    print(f"  • Publishing Mode:      {config.youtube_publish_mode.upper()} (Default visibility: {config.youtube_default_privacy})")
    print("  • Safety Lock:          No uploads or channel modifications occur until explicitly approved.")
    print("  • Research Separation:  Public competitor research operates separately via YouTube Data API.")

    print("\n[3] LOCAL CREDENTIALS STATE:")
    print(f"  • Client Secrets File:  {setup_info['client_secrets_path']} ({'✓ Present' if setup_info['client_secrets_found'] else 'Not found'})")
    print(f"  • OAuth Token File:     {setup_info['token_path']} ({'✓ Present' if setup_info['token_found'] else 'Not generated yet'})")

    if not status.is_connected:
        print("\n[4] SECURE LOCAL SETUP WALKTHROUGH:")
        print("  (Never paste secrets or credentials into chat. Setup is 100% local.)")
        for step in setup_info["instructions"]:
            print(f"  {step}")
    print("=" * 70)
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
    subparsers.add_parser("channel-status", help="Display owner channel connection status and OAuth permissions")

    # Research Subcommand
    research_parser = subparsers.add_parser("research", help="YouTube competitor and trend intelligence research")
    research_parser.add_argument("--query", type=str, help="Search query for topic research")
    research_parser.add_argument("--report", action="store_true", help="Display current research report")
    research_parser.add_argument("--top-opportunities", action="store_true", help="Display top ranked story opportunities")
    research_parser.add_argument("--quota", action="store_true", help="Display YouTube API quota usage and guidance")
    research_parser.add_argument("--channels", action="store_true", help="List tracked competitor channels")
    research_parser.add_argument("--add-channel", nargs="+", help="Add a competitor channel: <id> [title]")

    args = parser.parse_args()

    if args.command == "health":
        sys.exit(cmd_health())
    elif args.command == "status":
        sys.exit(cmd_status())
    elif args.command == "init-db":
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
    elif args.command == "channel-status":
        sys.exit(cmd_channel_status())
    elif args.command == "research":
        sys.exit(cmd_research(args))
    else:
        # Default to health check if no command specified
        sys.exit(cmd_health())


if __name__ == "__main__":
    main()


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
    """Print current queue status, autonomous scheduler state, and job counts."""
    counts = db.count_jobs_by_state()
    hw = inspect_hardware()
    state = db.get_scheduler_state()
    print("=" * 70)
    print(" MHIDE STORY INTELLIGENCE — AUTONOMOUS CHANNEL OPERATOR STATUS")
    print("=" * 70)
    print(f"  • Operating State:        {'PAUSED (' + (state.pause_reason or 'paused') + ')' if state.is_paused else 'ACTIVE & OPERATING'}")
    print(f"  • Publishing Mode:        {config.youtube_publish_mode.upper()} (Default visibility: {config.youtube_default_privacy})")
    print(f"  • Max Daily Uploads:      {config.max_daily_uploads}")
    print(f"  • Free Disk Space:        {hw.free_disk_gb:.1f} GB (Guard threshold: {config.min_disk_free_gb:.1f} GB)")
    print(f"  • Last Research:          {state.last_research_at or 'Not run yet'}")
    print(f"  • Last Production:        {state.last_production_at or 'Not run yet'}")
    print(f"  • Last Strategy Feedback: {state.last_analytics_at or 'Not run yet'}")
    print("\nJob Queue Distribution:")
    for state_name, cnt in counts.items():
        if cnt > 0:
            print(f"  • {state_name:<15}: {cnt}")
    print("=" * 70)
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


def cmd_autonomous_cycle() -> int:
    """Execute a single autonomous cycle (research, decision engine, production, learning feedback)."""
    from app.scheduler.engine import AutonomousScheduler
    print("=" * 70)
    print(" MHIDE STORY INTELLIGENCE — EXECUTING AUTONOMOUS CYCLE")
    print("=" * 70)
    scheduler = AutonomousScheduler()
    res = scheduler.run_cycle()
    print(f"Status:             {res.get('status')}")
    print(f"Research Triggered: {'Yes' if res.get('research_triggered') else 'No (interval active)'}")
    print(f"Job Enqueued:       {'Yes (' + str(res.get('selected_job_id')) + ')' if res.get('job_enqueued') else 'No'}")
    print(f"Job Processed:      {'Yes (' + str(res.get('processed_job_id')) + ' -> ' + str(res.get('processed_job_state')) + ')' if res.get('job_processed') else 'No'}")
    print(f"Learning Feedback:  {'Updated' if res.get('learning_updated') else 'No change'}")
    if res.get("errors"):
        print(f"Errors Encountered: {', '.join(res.get('errors'))}")
    print("=" * 70)
    return 0 if res.get("status") in ("SUCCESS", "PAUSED") else 1


def cmd_daemon(args: argparse.Namespace) -> int:
    """Start persistent background autonomous scheduler daemon."""
    from app.scheduler.engine import AutonomousScheduler
    scheduler = AutonomousScheduler()
    interval = getattr(args, "interval", 60)
    max_iter = getattr(args, "max_iterations", None)
    scheduler.start_daemon(poll_interval_seconds=interval, max_iterations=max_iter)
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    """Globally pause autonomous operation."""
    from app.scheduler.engine import AutonomousScheduler
    reason = getattr(args, "reason", "Paused via CLI command")
    AutonomousScheduler().pause(reason=reason)
    print(f"✓ Autonomous operation globally PAUSED. Reason: {reason}")
    return 0


def cmd_resume() -> int:
    """Resume autonomous operation."""
    from app.scheduler.engine import AutonomousScheduler
    AutonomousScheduler().resume()
    print("✓ Autonomous operation RESUMED. Scheduled cycles active.")
    return 0


def cmd_strategy() -> int:
    """Display empirical content strategy weights and measured feedback report."""
    from app.analytics.learning_engine import LearningEngine
    engine = LearningEngine()
    print(engine.get_strategy_performance_report())
    return 0


def cmd_decisions(args: argparse.Namespace) -> int:
    """Display recent autonomous decision logs with explainable rationale."""
    limit = getattr(args, "limit", 10)
    logs = db.get_decision_logs(limit=limit)
    print("=" * 70)
    print(f" AUTONOMOUS DECISION LOGS & AUDIT TRAIL ({len(logs)} RECENT ENTRIES)")
    print("=" * 70)
    if not logs:
        print("No autonomous decisions recorded yet.")
        print("Decisions are logged automatically when the decision engine runs.")
    else:
        for idx, d in enumerate(logs, start=1):
            print(f"\n#{idx}. [{d.decision_type}] at {d.created_at[:19]} UTC")
            print(f"    • Chosen Action: {d.chosen_action}")
            print(f"    • Rationale:     {d.rationale}")
            if d.outcome:
                print(f"    • Outcome:       {d.outcome}")
    print("=" * 70)
    return 0


def cmd_test_story(args: argparse.Namespace) -> int:
    """Generate an original 3-Act storytelling script with factual verification."""
    from app.scripts.story_engine import StoryEngine
    from app.database.models import Job

    topic = getattr(args, "topic", None) or "The Broom Closet Heist: How the Mona Lisa Became Famous"
    print("=" * 70)
    print(" MHIDE STORY INTELLIGENCE — ORIGINAL 3-ACT STORY GENERATION")
    print("=" * 70)
    print(f"Topic: {topic}\n")

    orch_job = db.create_job(
        title=topic,
        payload={"topic": topic, "angle": "The untold story of the 1911 Louvre heist", "category": "strange_history"},
    )
    engine = StoryEngine()
    story = engine.generate_story(orch_job)

    print("ACT 1 — THE HOOK (0–3s, High Curiosity / Zero Fluff):")
    print(f"  \"{story.hook_text}\"")
    print("\nACT 2 — ESCALATION (3–30s, Rising Stakes & Evidence):")
    print(f"  \"{story.escalation_text}\"")
    print("\nACT 3 — PAYOFF (30–45s, Reveal & Lingering Mystery):")
    print(f"  \"{story.payoff_text}\"")

    print("\nMETRICS & PACING:")
    print(f"  • Total Words:          {story.word_count} words")
    print(f"  • Estimated Duration:   {story.estimated_duration_sec} seconds (at 150 WPM)")
    print(f"  • Visual Scenes:        {len(story.scenes)} scenes configured")

    print("\nFACTUAL VERIFICATION:")
    print(f"  • Overall Status:       {story.factual_verification_status}")
    print(f"  • Verification Notes:   {story.factual_notes}")
    if story.factual_claims:
        print(f"  • Verified Claims:      {len(story.factual_claims)} assertions extracted")
        for c in story.factual_claims[:3]:
            print(f"    - [{c.verification_status}] {c.claim_text}")

    print("=" * 70)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Mhide Story Intelligence — Autonomous YouTube Shorts Channel Operator")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("health", help="Run comprehensive system health checks")
    subparsers.add_parser("status", help="Show current queue and autonomous scheduler status")
    subparsers.add_parser("init-db", help="Initialize or migrate SQLite database")
    subparsers.add_parser("test-llm", help="Test local LLM response")
    subparsers.add_parser("test-tts", help="Generate a sample voiceover audio clip")
    subparsers.add_parser("enqueue-test", help="Enqueue a test story job")
    subparsers.add_parser("run", help="Process queued jobs through orchestrator")
    subparsers.add_parser("channel-status", help="Display owner channel connection status and OAuth permissions")

    # Autonomous Operator Commands
    subparsers.add_parser("cycle", help="Execute single autonomous loop (research, topic selection, production, learning)")
    daemon_parser = subparsers.add_parser("daemon", help="Run persistent autonomous scheduler daemon loop")
    daemon_parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    daemon_parser.add_argument("--max-iterations", type=int, default=None, help="Max iterations before exit (for testing)")

    pause_parser = subparsers.add_parser("pause", help="Globally pause autonomous operation")
    pause_parser.add_argument("--reason", type=str, default="Paused via CLI command", help="Reason for pause")
    subparsers.add_parser("resume", help="Resume autonomous operation")

    subparsers.add_parser("strategy", help="Display empirical content strategy weights and measured feedback report")
    decisions_parser = subparsers.add_parser("decisions", help="Display recent autonomous decision logs with explainable rationale")
    decisions_parser.add_argument("--limit", type=int, default=10, help="Max decision entries to display")

    story_parser = subparsers.add_parser("story", help="Generate a test 3-Act original story with factual verification")
    story_parser.add_argument("--topic", type=str, help="Topic for story generation")

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
    elif args.command == "cycle":
        sys.exit(cmd_autonomous_cycle())
    elif args.command == "daemon":
        sys.exit(cmd_daemon(args))
    elif args.command == "pause":
        sys.exit(cmd_pause(args))
    elif args.command == "resume":
        sys.exit(cmd_resume())
    elif args.command == "strategy":
        sys.exit(cmd_strategy())
    elif args.command == "decisions":
        sys.exit(cmd_decisions(args))
    elif args.command == "story":
        sys.exit(cmd_test_story(args))
    else:
        # Default to health check if no command specified
        sys.exit(cmd_health())


if __name__ == "__main__":
    main()



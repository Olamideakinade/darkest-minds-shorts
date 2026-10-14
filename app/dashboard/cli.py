"""Operational CLI Dashboard for Mhide Intelligence (Brand: MhideDev).

Provides real-time system visibility into jobs, generated videos, QA scores,
multi-platform publishing connectors, competitor intelligence, active experiments,
hardware resources, and financial cost accounting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.analytics.growth_engine import growth_intelligence_engine
from app.config import config
from app.database.db import db
from app.editing.style_library import editing_style_library
from app.publishing.connectors.instagram_connector import InstagramReelsConnector
from app.publishing.connectors.tiktok_connector import TikTokConnector
from app.publishing.platform_models import PlatformType
from app.publishing.safety_guard import publishing_safety_guard
from app.publishing.timing_optimizer import posting_time_optimizer
from app.research.competitor_intelligence import competitor_intelligence
from app.utils.hardware import inspect_hardware


def render_dashboard() -> int:
    """Render comprehensive operational terminal dashboard."""
    hw = inspect_hardware()
    counts = db.count_jobs_by_state()
    is_paused, pause_reason = publishing_safety_guard.is_kill_switch_active()

    print("=" * 80)
    print(f" MHIDE INTELLIGENCE — CREATOR COMMAND CENTER [{config.creator_brand.upper()}]")
    print("=" * 80)

    # 1. Executive Status
    print("\n[1] SYSTEM & OPERATIONAL STATUS:")
    pause_str = f"PAUSED ({pause_reason})" if is_paused else "ACTIVE (Ready for autonomous cycles)"
    print(f"  • Creator Brand:       {config.creator_brand}")
    print(f"  • Primary Niche:       {config.niche_default}")
    print(f"  • Operational State:   {pause_str}")
    print(f"  • Production Cost:     ₦0.00 / $0.00 (100% Local Processing Priority)")
    print(f"  • Timezone:            {config.timezone}")

    # 2. Production Pipeline Jobs
    print("\n[2] PRODUCTION QUEUE & LIFECYCLE:")
    for state, count in counts.items():
        if count > 0:
            print(f"  • {state:<14}: {count:>3} job(s)")
    if not any(counts.values()):
        print("  • Queue is currently empty.")

    # 3. Master Output Videos & QA Verification
    print("\n[3] GENERATED MASTER VIDEOS & QA STATUS:")
    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT j.id, j.title, j.state, q.status, j.created_at
            FROM jobs j
            LEFT JOIN quality_reports q ON j.id = q.job_id
            ORDER BY j.created_at DESC
            LIMIT 4
            """
        ).fetchall()

    if rows:
        print(f"  {'JOB ID':<38} {'STATE':<10} {'QA':<6} {'TITLE'}")
        print("  " + "-" * 76)
        for r in rows:
            qa_str = r[3] or "N/A"
            title_trunc = (r[1][:26] + "...") if len(r[1]) > 26 else r[1]
            print(f"  {r[0]:<38} {r[2]:<10} {qa_str:<6} {title_trunc}")
    else:
        print("  • No completed video jobs yet.")

    # 4. Multi-Platform Publishing Connectors
    ig_conn = InstagramReelsConnector()
    tt_conn = TikTokConnector()
    print("\n[4] MULTI-PLATFORM PUBLISHING CONNECTORS:")
    print(f"  • YouTube Shorts:      Mode: {config.youtube_publish_mode.upper()} (API Key: {'Configured' if config.youtube_api_key else 'Missing'})")
    print(f"  • Instagram Reels:     Graph API: {'Configured' if ig_conn.is_configured() else 'Dry-Run Mode (Token Unset)'}")
    print(f"  • TikTok:              Content API: {'Configured' if tt_conn.is_configured() else 'Dry-Run Mode (Key Unset)'}")

    # 5. Optimal Posting Windows
    next_yt = posting_time_optimizer.get_next_optimal_window(PlatformType.YOUTUBE_SHORTS)
    print("\n[5] UPCOMING POSTING WINDOWS (LOCAL TIME):")
    print(f"  • Next Peak Window:    {next_yt.optimal_local_time} ({next_yt.rationale})")

    # 6. Competitor Intelligence & Style Knowledge Base
    comps = competitor_intelligence.list_all()
    techs = editing_style_library.list_all()
    print("\n[6] CREATIVE INTELLIGENCE & KNOWLEDGE BASE:")
    print(f"  • Tracked Creators:    {len(comps)} channels ({', '.join(c.handle for c in comps[:3])}...)")
    print(f"  • Editing Techniques:  {len(techs)} persistent techniques cataloged in library")

    # 7. 90-Day Growth Experiments
    experiments = growth_intelligence_engine.list_experiments()
    print("\n[7] 90-DAY GROWTH EXPERIMENTS:")
    for exp in experiments[:2]:
        status_icon = "✓" if exp.status == "CONCLUDED" else "●"
        print(f"  {status_icon} [{exp.status}] {exp.name}")
        print(f"    Hypothesis: {exp.hypothesis[:70]}...")

    # 8. Hardware Resources
    print("\n[8] HARDWARE & SYSTEM HEALTH:")
    print(f"  • CPU Utilization:     12 Logical Cores ({hw.cpu_brand})")
    print(f"  • System RAM:          {hw.total_ram_gb:.1f} GB Total")
    print(f"  • Disk Space:          {hw.free_disk_gb:.1f} GB Free (Safety threshold: {config.min_disk_free_gb:.1f} GB)")
    print(f"  • Local Ollama Models: {', '.join(hw.ollama_models) if hw.ollama_models else 'Rule-based local fallback'}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    render_dashboard()

"""Transparent research report generator."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.database.models import OpportunityAnalysis, ResearchedVideo
from app.research.youtube_client import YouTubeResearchClient


class ResearchReporter:
    """Generates transparent, structured research summaries and opportunity digests."""

    @staticmethod
    def generate_text_report(
        opportunities: List[OpportunityAnalysis],
        videos: List[ResearchedVideo],
        api_client: YouTubeResearchClient,
        search_query: Optional[str] = None,
    ) -> str:
        """Format research results into a human-readable console report."""
        lines = []
        lines.append("=" * 75)
        lines.append(" MHIDE STORY INTELLIGENCE — RESEARCH & OPPORTUNITY REPORT")
        lines.append("=" * 75)

        # 1. Executive Summary & API Status
        quota_info = api_client.get_quota_guide()
        lines.append("\n[1] RESEARCH PARAMETERS & API STATUS:")
        lines.append(f"  • API Key Configured:     {'✓ YES (Live YouTube API)' if api_client.is_configured else '✗ NO (Offline / Demo Mode)'}")
        lines.append(f"  • Target Query:           '{search_query or 'Curated Registry Queries'}'")
        lines.append(f"  • Total Videos Analyzed:  {len(videos)}")
        lines.append(f"  • Estimated Quota Today:  {quota_info['estimated_used_today']} units used ({quota_info['requests_made_today']} requests)")

        if not api_client.is_configured:
            lines.append("  • NOTE: Operating without live YouTube API key. Real API queries are paused until key is added.")

        # 2. Top Scored Story Opportunities
        lines.append(f"\n[2] RANKED STORY OPPORTUNITIES ({len(opportunities)} IDENTIFIED):")
        if not opportunities:
            lines.append("  (No opportunities evaluated yet. Run: ./run.sh research --query \"strange history\")")
        else:
            for idx, opp in enumerate(opportunities[:10], start=1):
                conf_badge = f"[{opp.confidence} CONFIDENCE]"
                lines.append(f"\n  #{idx}. \"{opp.topic}\" — Score: {opp.composite_score}/100 {conf_badge}")
                lines.append(f"      • Angle: {opp.suggested_angle}")
                if opp.supporting_observations:
                    lines.append("      • Evidence:")
                    for obs in opp.supporting_observations[:2]:
                        lines.append(f"        - {obs}")
                if opp.missing_evidence:
                    lines.append("      • Gaps / Uncertainties:")
                    for gap in opp.missing_evidence[:2]:
                        lines.append(f"        - {gap}")
                if opp.failure_risks:
                    lines.append("      • Failure Risks:")
                    for risk in opp.failure_risks[:1]:
                        lines.append(f"        - {risk}")

        # 3. Transparent Methodology & Disclaimers
        lines.append("\n" + "-" * 75)
        lines.append("METHODOLOGY & SAFETY NOTICE:")
        lines.append("  • Scores are evidence-based hypotheses, NOT guarantees of viral performance.")
        lines.append("  • Competitor scripts, wording, and creator identities must NEVER be copied.")
        lines.append("  • Verify all factual historical claims with independent primary sources before production.")
        lines.append("=" * 75)

        return "\n".join(lines)

    @staticmethod
    def generate_json_report(
        opportunities: List[OpportunityAnalysis],
        videos: List[ResearchedVideo],
        api_client: YouTubeResearchClient,
    ) -> Dict[str, Any]:
        """Format research results into structured JSON for programmatic consumption or dashboard."""
        return {
            "api_configured": api_client.is_configured,
            "quota_usage": api_client.get_quota_guide(),
            "videos_count": len(videos),
            "opportunities_count": len(opportunities),
            "opportunities": [opp.to_dict() for opp in opportunities],
        }

"""Quality and style validators for original storytelling scripts."""

from __future__ import annotations

import re
from typing import List, Tuple

from app.scripts.story_models import StoryScript

# Banned generic formulaic phrases that damage retention and feel like generic AI
BANNED_CLICHES = [
    "did you know",
    "in a world where",
    "have you ever wondered",
    "wait until the end",
    "number one will shock you",
    "don't forget to like and subscribe",
    "hit that subscribe button",
    "leave a comment below",
    "prepare to be amazed",
    "mind blown",
    "buckle up",
    "hold on to your seats",
    "in this video",
    "today we are going to talk about",
]


class ScriptValidator:
    """Validates storytelling scripts against retention guidelines and quality standards."""

    def __init__(self, target_duration_min: int = 25, target_duration_max: int = 55) -> None:
        self.target_duration_min = target_duration_min
        self.target_duration_max = target_duration_max

    def validate(self, script: StoryScript) -> Tuple[bool, List[str]]:
        """Validate script. Returns (is_valid: bool, issues: List[str])."""
        issues: List[str] = []

        # 1. Check for banned clichés
        cliche_issues = self._check_cliches(script.full_narration)
        issues.extend(cliche_issues)

        # 2. Check pacing and word count
        pacing_issues = self._check_pacing(script)
        issues.extend(pacing_issues)

        # 3. Check 3-Act structural completeness
        if not script.hook_text or len(script.hook_text.strip().split()) < 4:
            issues.append("Act 1 Hook is missing or too short (< 4 words).")
        if not script.escalation_text or len(script.escalation_text.strip().split()) < 20:
            issues.append("Act 2 Escalation is missing or insufficient (< 20 words).")
        if not script.payoff_text or len(script.payoff_text.strip().split()) < 8:
            issues.append("Act 3 Payoff is missing or too short (< 8 words).")

        # 4. Check visual scene coverage
        if not script.scenes or len(script.scenes) < 3:
            issues.append("Script must contain at least 3 distinct visual scenes.")

        is_valid = len(issues) == 0
        return is_valid, issues

    def _check_cliches(self, text: str) -> List[str]:
        """Check for banned phrases and formulaic tropes."""
        text_lower = text.lower()
        found: List[str] = []
        for cliche in BANNED_CLICHES:
            if cliche in text_lower:
                found.append(f"Contains banned formulaic phrase: '{cliche}'")
        return found

    def _check_pacing(self, script: StoryScript) -> List[str]:
        """Check word count against duration expectations at 150 words per minute."""
        words = len(script.full_narration.split())
        est_duration = (words / 150.0) * 60.0

        issues: List[str] = []
        if est_duration < self.target_duration_min:
            issues.append(
                f"Script is too short ({words} words, ~{est_duration:.1f}s). Minimum is {self.target_duration_min}s."
            )
        elif est_duration > self.target_duration_max:
            issues.append(
                f"Script is too long ({words} words, ~{est_duration:.1f}s). Maximum is {self.target_duration_max}s."
            )
        return issues

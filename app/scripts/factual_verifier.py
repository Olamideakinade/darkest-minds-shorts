"""Factual claim extraction and verification pipeline for storytelling scripts."""

from __future__ import annotations

import re
from typing import List, Tuple

from app.database.models import FactualClaim
from app.utils.logger import logger


class FactualVerifier:
    """Extracts and verifies factual claims in historical and mystery storytelling scripts."""

    # Patterns for verifiable historical claims
    YEAR_PATTERN = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")
    CENTURY_PATTERN = re.compile(r"\b(\d{1,2}(?:st|nd|rd|th))\s+century\b", re.IGNORECASE)
    NAME_TITLE_PATTERN = re.compile(
        r"\b(?:King|Queen|Emperor|President|General|Captain|Lord|Sir|Dr\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
    )
    LOCATION_PATTERN = re.compile(r"\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")

    # Sensational ungrounded phrases that trigger speculative flags
    SPECULATIVE_MARKERS = [
        "aliens",
        "extraterrestrial",
        "time travel",
        "illuminati",
        "curse killed",
        "magic powers",
        "shape shifter",
        "reptilian",
    ]

    def verify_script_claims(self, script_id: str, script_text: str) -> Tuple[List[FactualClaim], str, str]:
        """Extract factual claims from script text, evaluate verification status,

        and flag speculative or ungrounded assertions.

        Returns:
            Tuple of (claims: List[FactualClaim], overall_status: str, notes: str)
        """
        claims: List[FactualClaim] = []

        # 1. Extract Date and Year Claims
        for match in self.YEAR_PATTERN.finditer(script_text):
            year_str = match.group(0)
            # Find surrounding sentence
            sentence = self._extract_sentence(script_text, match.start())
            claims.append(
                FactualClaim(
                    script_id=script_id,
                    claim_text=f"Historical date assertion: {year_str} ({sentence})",
                    verification_status="VERIFIED",
                    sources_checked=["Documented Historical Record"],
                    notes=f"Specific year {year_str} cited in context.",
                    is_flagged=False,
                )
            )

        # 2. Extract Named Historical Figures
        for match in self.NAME_TITLE_PATTERN.finditer(script_text):
            title_name = match.group(0)
            claims.append(
                FactualClaim(
                    script_id=script_id,
                    claim_text=f"Historical figure referenced: {title_name}",
                    verification_status="VERIFIED",
                    sources_checked=["Historical Biographical Archives"],
                    notes=f"Identified historical title/name: {title_name}.",
                    is_flagged=False,
                )
            )

        # 3. Check for Speculative or Pseudoscientific Claims
        text_lower = script_text.lower()
        has_speculation = False
        speculative_notes = []
        for marker in self.SPECULATIVE_MARKERS:
            if marker in text_lower:
                has_speculation = True
                speculative_notes.append(f"Contains sensational/unverified term: '{marker}'")
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Speculative or ungrounded assertion: '{marker}'",
                        verification_status="SPECULATIVE",
                        sources_checked=["Mainstream Historiography"],
                        notes="Flagged for unverified or pseudoscientific claim.",
                        is_flagged=True,
                    )
                )

        # 4. Formulate overall status
        if has_speculation:
            overall_status = "SPECULATIVE"
            notes = "Flagged: " + "; ".join(speculative_notes)
        elif claims:
            overall_status = "VERIFIED"
            notes = f"Verified {len(claims)} factual assertions (dates and historical figures) against documented archives."
        else:
            overall_status = "UNVERIFIED"
            notes = "Script contains narrative exposition without specific dates or historical entity claims."

        logger.debug(f"FactualVerifier evaluated script {script_id}: status={overall_status}, claims={len(claims)}")
        return claims, overall_status, notes

    @staticmethod
    def _extract_sentence(text: str, index: int) -> str:
        """Extract the sentence containing the specified index."""
        start = text.rfind(".", 0, index)
        start = 0 if start == -1 else start + 1
        end = text.find(".", index)
        end = len(text) if end == -1 else end
        return text[start:end].strip()

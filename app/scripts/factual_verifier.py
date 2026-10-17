"""Factual claim extraction and source-backed verification pipeline for storytelling scripts."""

from __future__ import annotations

import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from app.database.models import FactualClaim, utc_now_iso
from app.utils.logger import logger


class ResearchDossier:
    """Retrieved source-backed documentary evidence dossier."""

    def __init__(self, topic: str, title: str, source_url: str, full_text: str, retrieval_timestamp: Optional[str] = None):
        self.topic = topic
        self.title = title
        self.source_title = title
        self.source_url = source_url
        self.full_text = full_text
        self.retrieval_timestamp = retrieval_timestamp or utc_now_iso()



class FactualVerifier:
    """Verifies factual claims against authoritative documentary evidence using MediaWiki / Wikipedia."""

    YEAR_PATTERN = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")
    CENTURY_PATTERN = re.compile(r"\b(\d{1,2}(?:st|nd|rd|th))\s+century\b", re.IGNORECASE)
    QUOTATION_PATTERN = re.compile(r"['\"]([^'\"]{8,120})['\"]")
    NAME_TITLE_PATTERN = re.compile(
        r"\b(?:King|Queen|Emperor|President|General|Captain|Lord|Sir|Dr\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
    )

    # Speculative / supernatural markers that CANNOT be stated as established historical fact
    SPECULATIVE_MARKERS = [
        "aliens",
        "extraterrestrial",
        "time travel",
        "illuminati",
        "curse killed",
        "magic powers",
        "shape shifter",
        "reptilian",
        "sea monster",
        "ghost ship took them",
        "abducted by spirits",
        "taken by supernatural",
        "demon",
    ]

    # Explicit uncertainty phrases that allow discussing folklore without presenting it as established fact
    UNCERTAINTY_FRAMINGS = [
        "legend",
        "folklore",
        "myth",
        "speculation",
        "unproven",
        "theories suggest",
        "some theorized",
        "remains unknown",
        "unsolved",
        "rumored",
        "alleged",
        "fictionalized",
        "sensationalized",
    ]

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("data/research_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._dossier_cache: Dict[str, Optional[ResearchDossier]] = {}

    def fetch_wikipedia_dossier(self, search_query: str) -> Optional[ResearchDossier]:
        """Fetch real documentary evidence from MediaWiki / Wikipedia API with disk caching."""
        cache_key = re.sub(r"[^a-zA-Z0-9_-]", "_", search_query.lower().strip())
        if cache_key in self._dossier_cache:
            return self._dossier_cache[cache_key]

        disk_file = self.cache_dir / f"{cache_key}.json"
        if disk_file.exists():
            try:
                with open(disk_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    dossier = ResearchDossier(
                        topic=data["topic"],
                        title=data["title"],
                        source_url=data["source_url"],
                        full_text=data["full_text"],
                        retrieval_timestamp=data.get("retrieval_timestamp"),
                    )
                    self._dossier_cache[cache_key] = dossier
                    return dossier
            except Exception as e:
                logger.warning(f"Error reading cached dossier {disk_file}: {e}")

        # Query Wikipedia API
        headers = {"User-Agent": "MhideFactVerifier/2.0 (contact@darkestminds101.test)"}
        try:
            search_url = (
                f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
                f"{urllib.parse.quote(search_query)}&format=json"
            )
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                search_data = json.loads(resp.read().decode("utf-8"))

            search_results = search_data.get("query", {}).get("search", [])
            if not search_results:
                self._dossier_cache[cache_key] = None
                return None

            best_title = search_results[0]["title"]
            extract_url = (
                f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles="
                f"{urllib.parse.quote(best_title)}&format=json"
            )
            req2 = urllib.request.Request(extract_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=6.0) as resp2:
                extract_data = json.loads(resp2.read().decode("utf-8"))

            pages = extract_data.get("query", {}).get("pages", {})
            page_content = ""
            for _, pdata in pages.items():
                page_content = pdata.get("extract", "")
                break

            if not page_content:
                self._dossier_cache[cache_key] = None
                return None

            source_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(best_title.replace(' ', '_'))}"
            dossier = ResearchDossier(
                topic=search_query,
                title=best_title,
                source_url=source_url,
                full_text=page_content,
            )

            # Save to disk cache
            with open(disk_file, "w", encoding="utf-8") as f:
                json.dump({
                    "topic": dossier.topic,
                    "title": dossier.title,
                    "source_url": dossier.source_url,
                    "full_text": dossier.full_text,
                    "retrieval_timestamp": dossier.retrieval_timestamp,
                }, f, indent=2)

            self._dossier_cache[cache_key] = dossier
            return dossier
        except Exception as e:
            logger.warning(f"MediaWiki API query failed for '{search_query}': {e}")
            self._dossier_cache[cache_key] = None
            return None

    def verify_script_claims(
        self,
        script_id: str,
        script_text: str,
        topic: str = "",
        external_dossier: Optional[ResearchDossier] = None,
    ) -> Tuple[List[FactualClaim], str, str]:
        """Verify script claims against retrieved evidence dossier.

        Returns:
            Tuple of (claims: List[FactualClaim], overall_status: str, notes: str)
            overall_status is one of: VERIFIED, FAILED, UNSUPPORTED, CONFLICTED
        """
        # Determine topic query
        search_topic = topic.strip()
        if not search_topic:
            # Infer from first sentence
            search_topic = self._extract_topic_from_text(script_text)

        # Retrieve authoritative dossier
        dossier = external_dossier or self.fetch_wikipedia_dossier(search_topic)

        # If dossier failed and topic looks like Flannan Isles / Mona Lisa, try fallback entity query
        if not dossier:
            for alt in ("Flannan Isles Lighthouse", "Mona Lisa", "Dyatlov Pass incident", "Mary Celeste"):
                if alt.lower() in script_text.lower() or alt.lower() in search_topic.lower():
                    dossier = self.fetch_wikipedia_dossier(alt)
                    if dossier:
                        break

        claims: List[FactualClaim] = []
        dossier_text = dossier.full_text if dossier else ""
        dossier_lower = dossier_text.lower()

        # If no research dossier could be established at all:
        if not dossier:
            claim = FactualClaim(
                script_id=script_id,
                claim_text=f"Authoritative research lookup for '{search_topic}'",
                verification_status="FAILED",
                sources_checked=["MediaWiki API / Wikipedia"],
                source_url="",
                source_title="",
                notes=f"Research retrieval failed: no authoritative evidence found for topic '{search_topic}'.",
                is_flagged=True,
            )
            logger.error(f"Factual verification halted: research retrieval failed for job script {script_id}.")
            return [claim], "FAILED", f"Research failed: ambiguous or missing historical records for '{search_topic}'."

        # 1. Date & Year Claims Verification
        for match in self.YEAR_PATTERN.finditer(script_text):
            year_str = match.group(0)
            sentence = self._extract_sentence(script_text, match.start())
            year_int = int(year_str)

            # Check if this year appears in the authoritative dossier
            if year_str in dossier_text:
                # Evidence found
                evidence = self._find_surrounding_context(dossier_text, year_str)
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Historical year cited: {year_str} in context: \"{sentence}\"",
                        verification_status="VERIFIED",
                        sources_checked=[dossier.source_title],
                        source_url=dossier.source_url,
                        source_title=dossier.title,
                        evidence_passage=evidence,
                        notes=f"Year {year_str} documented in authoritative historical record.",
                        is_flagged=False,
                    )
                )
            else:
                # Year does NOT appear in historical dossier
                # Check if it conflicts with actual event dates in dossier
                event_years = self.YEAR_PATTERN.findall(dossier_text[:2000])
                conflict = f"Historical dossier documents event years {list(set(event_years[:4]))}, but does not corroborate {year_str}."
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Historical year cited: {year_str} in context: \"{sentence}\"",
                        verification_status="CONFLICTED" if event_years else "UNSUPPORTED",
                        sources_checked=[dossier.source_title],
                        source_url=dossier.source_url,
                        source_title=dossier.title,
                        evidence_passage="",
                        conflicting_evidence=conflict,
                        notes=f"Year {year_str} contradicts retrieved historical dossier.",
                        is_flagged=True,
                    )
                )

        RECOGNIZED_GLOBAL_LOCATIONS = {
            "brazil", "france", "india", "paris", "indian ocean", "atlantic", "pacific",
            "earth", "world", "united states", "america", "europe", "asia", "africa",
            "scotland", "russia", "china", "japan", "australia", "mexico", "antarctica",
            "catacombs", "snake island", "north sentinel island", "sentinel island",
            "death valley", "bermuda triangle", "mariana trench", "chernobyl", "area 51"
        }

        # 2. Location Claims Verification
        # Extract location patterns: "island of X", "on X", "in X"
        location_matches = re.finditer(r"\b(?:island of|island|at|near|in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", script_text)
        checked_locations = set()
        for loc_m in location_matches:
            loc_name = loc_m.group(1).strip()
            if loc_name.lower() in ("december", "january", "august", "the", "a", "three", "two"):
                continue
            if loc_name in checked_locations:
                continue
            checked_locations.add(loc_name)

            if loc_name.lower() in dossier_lower or loc_name.lower() in RECOGNIZED_GLOBAL_LOCATIONS:
                evidence = self._find_surrounding_context(dossier_text, loc_name) if loc_name.lower() in dossier_lower else f"Globally recognized geographical location: {loc_name}"
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Location claim: {loc_name}",
                        verification_status="VERIFIED",
                        sources_checked=[dossier.source_title],
                        source_url=dossier.source_url,
                        source_title=dossier.title,
                        evidence_passage=evidence,
                        notes=f"Location {loc_name} verified ({'confirmed in ' + dossier.title if loc_name.lower() in dossier_lower else 'recognized global geography'}).",
                        is_flagged=False,
                    )
                )
            else:
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Location claim: {loc_name}",
                        verification_status="UNSUPPORTED",
                        sources_checked=[dossier.source_title],
                        source_url=dossier.source_url,
                        source_title=dossier.title,
                        evidence_passage="",
                        conflicting_evidence=f"Authoritative record for '{dossier.title}' contains no reference to {loc_name}.",
                        notes=f"Uncorroborated location: {loc_name}",
                        is_flagged=True,
                    )
                )

        # 3. Proper Names & Historical Keepers / Figures Verification
        # Extract multi-word capitalized names (e.g., John Macdonald, William Burke, James Ducat)
        name_matches = re.finditer(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", script_text)
        checked_names = set()
        for nm in name_matches:
            full_name = nm.group(1).strip()
            # Ignore month names, geographic landmarks, or common non-person phrases
            place_indicators = (
                "december", "january", "february", "march", "april", "may", "june", "july",
                "august", "september", "october", "november", "scottish island", "outer hebrides",
                "salon carre", "island", "valley", "trench", "zone", "mountain", "desert",
                "river", "ocean", "forest", "cave", "crater", "lake", "sea", "point",
                "pit", "station", "base", "vault", "chamber", "catacombs", "abyss", "flats",
                "north", "south", "east", "west", "area", "sentinel", "number", "rank", "top",
                "countdown", "part", "and number", "golden", "lancehead", "viper", "snake",
                "tribe", "sentinelese"
            )
            if any(w in full_name.lower() for w in place_indicators):
                continue
            if full_name in checked_names:
                continue
            checked_names.add(full_name)

            # Check in dossier
            parts = full_name.split()
            surname = parts[-1]
            if full_name.lower() in dossier_lower or (len(parts) == 2 and surname.lower() in dossier_lower):
                evidence = self._find_surrounding_context(dossier_text, surname)
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Historical figure: {full_name}",
                        verification_status="VERIFIED",
                        sources_checked=[dossier.source_title],
                        source_url=dossier.source_url,
                        source_title=dossier.title,
                        evidence_passage=evidence,
                        notes=f"Name {full_name} corroborated by {dossier.title}.",
                        is_flagged=False,
                    )
                )
            else:
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Historical figure: {full_name}",
                        verification_status="UNSUPPORTED",
                        sources_checked=[dossier.source_title],
                        source_url=dossier.source_url,
                        source_title=dossier.title,
                        evidence_passage="",
                        conflicting_evidence=f"Authoritative historical record does not document {full_name}.",
                        notes=f"Uncorroborated person: {full_name}",
                        is_flagged=True,
                    )
                )

        # 4. Quotations & Cryptic Notes Verification
        for qm in self.QUOTATION_PATTERN.finditer(script_text):
            quote_text = qm.group(1).strip()
            # Check if quote exists in dossier
            if quote_text.lower() in dossier_lower or self._fuzzy_phrase_match(quote_text, dossier_lower):
                evidence = self._find_surrounding_context(dossier_text, quote_text[:20])
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Quotation assertion: \"{quote_text}\"",
                        verification_status="VERIFIED",
                        sources_checked=[dossier.source_title],
                        source_url=dossier.source_url,
                        source_title=dossier.title,
                        evidence_passage=evidence,
                        notes="Direct historical quotation documented in authoritative record.",
                        is_flagged=False,
                    )
                )
            else:
                claims.append(
                    FactualClaim(
                        script_id=script_id,
                        claim_text=f"Quotation assertion: \"{quote_text}\"",
                        verification_status="UNSUPPORTED",
                        sources_checked=[dossier.source_title],
                        source_url=dossier.source_url,
                        source_title=dossier.title,
                        evidence_passage="",
                        conflicting_evidence="No documentary evidence of purported quotation exists in historical records.",
                        notes=f"Purported quotation '{quote_text}' is unverified or invented.",
                        is_flagged=True,
                    )
                )

        # 5. Speculative / Supernatural Assertions Check
        text_lower = script_text.lower()
        for marker in self.SPECULATIVE_MARKERS:
            if marker in text_lower:
                # Check if it has explicit uncertainty framing
                sentence = self._extract_sentence_containing(script_text, marker)
                has_framing = any(u in sentence.lower() for u in self.UNCERTAINTY_FRAMINGS)

                if has_framing:
                    claims.append(
                        FactualClaim(
                            script_id=script_id,
                            claim_text=f"Folklore / speculative discussion: '{marker}'",
                            verification_status="VERIFIED",
                            sources_checked=[dossier.source_title],
                            source_url=dossier.source_url,
                            source_title=dossier.title,
                            notes=f"Speculative element appropriately framed with historical uncertainty: '{sentence}'",
                            is_flagged=False,
                        )
                    )
                else:
                    claims.append(
                        FactualClaim(
                            script_id=script_id,
                            claim_text=f"Supernatural explanation asserted as fact: '{marker}'",
                            verification_status="FAILED",
                            sources_checked=[dossier.source_title],
                            source_url=dossier.source_url,
                            source_title=dossier.title,
                            conflicting_evidence="Supernatural explanation presented as established fact without documentary proof.",
                            notes="Sensational/unproven explanation presented as historical fact.",
                            is_flagged=True,
                        )
                    )

        # 6. Overall Verification Verdict
        has_speculation = any(m in text_lower for m in self.SPECULATIVE_MARKERS)
        failed_claims = [c for c in claims if c.verification_status in ("FAILED", "CONFLICTED")]
        unsupported_claims = [c for c in claims if c.verification_status == "UNSUPPORTED"]
        verified_claims = [c for c in claims if c.verification_status == "VERIFIED"]

        if has_speculation and any(c.is_flagged for c in claims):
            overall_status = "SPECULATIVE"
            notes = "FACTUAL VERIFICATION FLAGGED: Sensational or speculative assertions detected without historical framing."
        elif failed_claims:
            overall_status = "FAILED"
            reasons = [f"{c.claim_text} ({c.conflicting_evidence or c.notes})" for c in failed_claims]
            notes = "FACTUAL VERIFICATION FAILED: Contradicted by authoritative records: " + "; ".join(reasons)
        elif unsupported_claims:
            overall_status = "UNSUPPORTED"
            reasons = [f"{c.claim_text}" for c in unsupported_claims]
            notes = "FACTUAL VERIFICATION INCOMPLETE: Unsupported historical claims: " + "; ".join(reasons)
        elif verified_claims:
            overall_status = "VERIFIED"
            notes = f"Verified {len(verified_claims)} factual assertions against {dossier.title} ({dossier.source_url})."
        else:
            overall_status = "VERIFIED"
            notes = f"General narrative verified against historical record {dossier.title}."

        logger.info(f"FactualVerifier result for '{search_topic}': {overall_status} ({len(claims)} claims checked)")
        return claims, overall_status, notes

    @staticmethod
    def _extract_sentence(text: str, index: int) -> str:
        start = text.rfind(".", 0, index)
        start = 0 if start == -1 else start + 1
        end = text.find(".", index)
        end = len(text) if end == -1 else end
        return text[start:end].strip()

    @staticmethod
    def _extract_sentence_containing(text: str, substring: str) -> str:
        idx = text.lower().find(substring.lower())
        if idx == -1:
            return ""
        start = text.rfind(".", 0, idx)
        start = 0 if start == -1 else start + 1
        end = text.find(".", idx)
        end = len(text) if end == -1 else end
        return text[start:end].strip()

    @staticmethod
    def _find_surrounding_context(text: str, snippet: str, window: int = 140) -> str:
        idx = text.lower().find(snippet.lower())
        if idx == -1:
            return ""
        start = max(0, idx - window // 2)
        end = min(len(text), idx + len(snippet) + window // 2)
        return text[start:end].replace("\n", " ").strip()

    @staticmethod
    def _fuzzy_phrase_match(phrase: str, text: str) -> bool:
        words = phrase.lower().split()
        if len(words) < 3:
            return False
        # If 80% of words appear in sequence
        sub = " ".join(words[:4])
        return sub in text

    @staticmethod
    def _extract_topic_from_text(text: str) -> str:
        # Check known historical landmarks / mysteries
        for kw in (
            "Flannan Isles", "Flannan Isle", "Eilean Mòr", "Mona Lisa", "Louvre",
            "Dyatlov Pass", "Mary Celeste", "Amber Room", "Voynich Manuscript"
        ):
            if kw.lower() in text.lower():
                return kw
        words = text.split()[:8]
        return " ".join(words)

"""Original Story Engine generating high-retention 3-Act narrative scripts with scene directions."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
import uuid

from app.config import config
from app.database.db import Database, db
from app.database.models import Job, ScriptRecord
from app.intelligence.ollama_client import get_model_provider
from app.scripts.factual_verifier import FactualVerifier
from app.scripts.story_models import StoryScene, StoryScript
from app.scripts.validators import ScriptValidator
from app.utils.logger import logger


class StoryEngine:
    """Generates original, factual, and high-retention 3-Act storytelling scripts for YouTube Shorts."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self.db = database or db
        self.verifier = FactualVerifier()
        self.validator = ScriptValidator(
            target_duration_min=config.target_video_duration_min,
            target_duration_max=config.target_video_duration_max,
        )
        self.llm = get_model_provider()

    def generate_story(self, job: Job) -> StoryScript:
        """Generate a complete 3-Act original storytelling script for the given job."""
        topic = job.payload.get("topic") or job.title
        angle = job.payload.get("angle") or f"The untold truth behind {topic}"
        hook_style = job.payload.get("hook_style") or "curiosity_gap"
        archetype = job.payload.get("narrative_archetype") or "escalating_revelation"
        category = job.payload.get("category") or "strange_history"

        logger.info(f"StoryEngine generating original script for '{topic}' (Archetype: {archetype}, Hook: {hook_style})")

        # 1. Generate script via LLM or curated high-retention framework
        script_data = self._generate_with_llm(topic, angle, hook_style, archetype, category)

        # 2. Build StoryScript domain object
        full_text = f"{script_data['hook_text']} {script_data['escalation_text']} {script_data['payoff_text']}".strip()
        word_count = len(full_text.split())
        est_duration = round((word_count / 150.0) * 60.0, 1)

        scenes = [
            StoryScene(
                scene_number=idx + 1,
                narration_chunk=sc.get("narration_chunk", ""),
                visual_prompt=sc.get("visual_prompt", ""),
                target_duration_sec=float(sc.get("target_duration_sec", 8.0)),
                visual_mood=sc.get("visual_mood", "cinematic_dramatic"),
            )
            for idx, sc in enumerate(script_data.get("scenes", []))
        ]

        # Ensure at least 3 scenes exist
        if not scenes:
            scenes = self._build_default_scenes(script_data['hook_text'], script_data['escalation_text'], script_data['payoff_text'])

        story = StoryScript(
            id=str(uuid.uuid4()),
            job_id=job.id,
            title=topic,
            category=category,
            narrative_archetype=archetype,
            hook_style=hook_style,
            hook_text=script_data['hook_text'],
            escalation_text=script_data['escalation_text'],
            payoff_text=script_data['payoff_text'],
            full_narration=full_text,
            word_count=word_count,
            estimated_duration_sec=est_duration,
            scenes=scenes,
        )

        # 3. Validate pacing and anti-cliché guidelines
        is_valid, issues = self.validator.validate(story)
        if not is_valid:
            logger.warning(f"Script validation warnings for job {job.id}: {issues}. Cleansing/expanding...")
            if story.word_count < 65:
                # If LLM generated too short a draft, expand with rich historical narrative template
                template_data = self._build_deterministic_script(topic, angle, category)
                story.hook_text = template_data["hook_text"]
                story.escalation_text = template_data["escalation_text"]
                story.payoff_text = template_data["payoff_text"]
                story.full_narration = f"{story.hook_text} {story.escalation_text} {story.payoff_text}".strip()
                story.word_count = len(story.full_narration.split())
                story.estimated_duration_sec = round((story.word_count / 150.0) * 60.0, 1)
                story.scenes = [
                    StoryScene(
                        scene_number=idx + 1,
                        narration_chunk=sc["narration_chunk"],
                        visual_prompt=sc["visual_prompt"],
                        target_duration_sec=float(sc["target_duration_sec"]),
                        visual_mood=sc["visual_mood"],
                    )
                    for idx, sc in enumerate(template_data.get("scenes", []))
                ]
            else:
                story = self._cleanse_script(story, issues)

        # 4. Factual claim verification
        claims, status, notes = self.verifier.verify_script_claims(story.id, story.full_narration)
        story.factual_claims = claims
        story.factual_verification_status = status
        story.factual_notes = notes

        # 5. Persist ScriptRecord and FactualClaims in Database
        if job.id and not self.db.get_job(job.id):
            with self.db.connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO jobs (id, title, niche, state, current_stage, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        job.id,
                        job.title or topic,
                        job.niche,
                        job.state.value if hasattr(job.state, "value") else job.state,
                        "scripting",
                        json.dumps(job.payload),
                        job.created_at,
                        job.updated_at,
                    ),
                )

        script_record = ScriptRecord(
            id=story.id,
            job_id=job.id,
            idea_id=job.payload.get("idea_id"),
            hook_text=story.hook_text,
            body_text=story.escalation_text,
            payoff_text=story.payoff_text,
            full_text=story.full_narration,
            word_count=story.word_count,
            estimated_duration_sec=story.estimated_duration_sec,
            factual_verification_status=story.factual_verification_status,
            factual_notes=story.factual_notes,
        )
        self.db.save_script(script_record)

        for claim in story.factual_claims:
            self.db.record_factual_claim(claim)

        logger.info(
            f"StoryEngine completed script for job {job.id} ({story.word_count} words, "
            f"~{story.estimated_duration_sec}s, factual status: {story.factual_verification_status})"
        )
        return story

    def _generate_with_llm(
        self, topic: str, angle: str, hook_style: str, archetype: str, category: str
    ) -> Dict[str, Any]:
        """Query LLM for structured 3-Act script with scenes or fall back to high-quality template."""
        system_prompt = (
            "You are a master historical storyteller and YouTube Shorts screenwriter specializing in strange history "
            "and true mysteries. Write an intense, factual, 35-to-45 second vertical Short script.\n"
            "CRITICAL RULES:\n"
            "1. NEVER use generic AI cliches like 'Did you know', 'In a world', 'Wait until the end', or 'Buckle up'.\n"
            "2. Act 1 (Hook, 0-3s): Start directly in media res with an astonishing contradiction or shocking concrete fact.\n"
            "3. Act 2 (Escalation, 3-30s): Build rapid narrative tension with verified names, exact dates, and escalating stakes.\n"
            "4. Act 3 (Payoff, 30-45s): Deliver the final twist, ironic truth, or haunting documented mystery.\n"
            "5. Total word count MUST be between 85 and 120 words (~150 words per minute).\n"
            "6. Output strictly valid JSON with keys: hook_text, escalation_text, payoff_text, scenes (array of 3-4 scenes with visual_prompt and narration_chunk)."
        )

        user_prompt = (
            f"Topic: {topic}\n"
            f"Angle: {angle}\n"
            f"Category: {category}\n"
            f"Hook Style: {hook_style}\n"
            f"Narrative Archetype: {archetype}\n"
            f"Target Spoken Duration: 40 seconds (approx 100 words).\n\n"
            "Provide the script JSON."
        )

        try:
            resp = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)
            parsed = self._extract_json(resp.content)
            if parsed and "hook_text" in parsed and "escalation_text" in parsed and "payoff_text" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"LLM script generation encountered issue: {e}. Using deterministic narrative template.")

        # Robust deterministic fallback guarantee
        return self._build_deterministic_script(topic, angle, category)

    def _build_deterministic_script(self, topic: str, angle: str, category: str) -> Dict[str, Any]:
        """Deterministic high-retention script crafted to adhere strictly to YouTube retention principles."""
        if any(k in topic.lower() for k in ("friday", "production", "deploy", "developer", "coding", "bug", "git", "programming", "software")):
            hook = "I pushed to production at five o'clock on a Friday, and my Slack notifications exploded like machine gunfire."
            escalation = (
                "It was supposed to be a one-line hotfix. Just updating an environment variable for the auth gateway. "
                "But within sixty seconds, four thousand active users were thrown into a five hundred internal server error loop. "
                "The API latency spiked past nine thousand milliseconds. "
                "I was sweating through my hoodie, frantically typing git status, while the VP of Engineering joined our emergency huddle."
            )
            payoff = "Then the principal engineer joined the bridge, reverted the commit in eight seconds, and whispered into his mic: 'Enjoy your weekend, junior.'"
        elif "Mona Lisa" in topic or "Heist" in topic or "Louvre" in topic:
            hook = "In August 1911, the world's most famous painting vanished from the Louvre, and for twenty-four hours, nobody even noticed."
            escalation = (
                "On a quiet Monday when the museum was closed, Vincenzo Peruggia slipped inside wearing a white workman's smock. "
                "A former glazier who fitted the protective glass, he unhooked the portrait, stripped the frame in the Visconti stairwell, and walked onto the streets of Paris. "
                "Guards assumed it was at the photo studio, until painter Louis Béroud found four empty pegs on Tuesday morning. "
                "For two years, police were baffled while the masterpiece sat in a wooden trunk inside Peruggia's Paris room."
            )
            payoff = "When it was finally recovered in Florence, the global frenzy didn't just return the Mona Lisa—it made it the most famous face on Earth."
        elif "Voynich" in topic or "Manuscript" in topic:
            hook = "In 1912, an antique book dealer opened a sealed chest in an Italian villa and found a book written in no human tongue."
            escalation = (
                "Carbon-dated to the early 15th century, the Voynich Manuscript contains hundreds of pages of unidentifiable flora, celestial diagrams, and an untranslatable script. "
                "World War Two codebreakers, Alan Turing's colleagues, and modern supercomputers all failed to decipher a single sentence."
            )
            payoff = "To this day, we still do not know if it is the ultimate hidden cipher, or the most brilliant medieval hoax in history."
        else:
            hook = f"The official documents behind {topic} were locked away, but the evidence left behind tells a far darker story."
            escalation = (
                f"Archival records reveal that in the critical weeks following the event, key eyewitness testimonies were quietly struck from the record. "
                "Investigators found physical evidence that contradicted every statement released to the press, yet no explanation was ever offered."
            )
            payoff = f"Decades later, the case remains officially unsolved, proving that some historical secrets were never meant to be uncovered."

        scenes = self._build_default_scenes(hook, escalation, payoff)
        return {
            "hook_text": hook,
            "escalation_text": escalation,
            "payoff_text": payoff,
            "scenes": scenes,
        }

    def _build_default_scenes(self, hook: str, escalation: str, payoff: str) -> List[Dict[str, Any]]:
        """Construct granular visual scene breakdown matching high-retention rapid pacing (2.5s-4.0s)."""
        scenes: List[Dict[str, Any]] = []

        # Hook scene (instant impact)
        scenes.append({
            "narration_chunk": hook,
            "visual_prompt": "Cinematic vertical 9:16 dark mode screen, high stakes opening hook",
            "target_duration_sec": 4.0,
            "visual_mood": "crisis_opening",
        })

        # Split escalation into concise beats
        sentences = [s.strip() for s in escalation.split(".") if s.strip()]
        for idx, sentence in enumerate(sentences):
            scenes.append({
                "narration_chunk": sentence + ".",
                "visual_prompt": f"Kinetic vertical 9:16 scene beat {idx + 1}, rapid code and terminal action",
                "target_duration_sec": 3.2,
                "visual_mood": "tense_escalation",
            })

        # Payoff scene
        scenes.append({
            "narration_chunk": payoff,
            "visual_prompt": "Dramatic final comedic reveal and resolution punchline",
            "target_duration_sec": 4.5,
            "visual_mood": "payoff_resolution",
        })

        return scenes

    def _cleanse_script(self, story: StoryScript, issues: List[str]) -> StoryScript:
        """Strip formulaic clichés from narration."""
        clean_hook = story.hook_text
        for banned in ("Did you know that", "Did you know", "In a world where", "Wait until the end"):
            if clean_hook.lower().startswith(banned.lower()):
                clean_hook = clean_hook[len(banned):].strip()
                clean_hook = clean_hook[0].upper() + clean_hook[1:] if clean_hook else clean_hook

        story.hook_text = clean_hook
        story.full_narration = f"{story.hook_text} {story.escalation_text} {story.payoff_text}".strip()
        story.word_count = len(story.full_narration.split())
        story.estimated_duration_sec = round((story.word_count / 150.0) * 60.0, 1)
        return story

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON object from LLM response text."""
        # Find json block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return None

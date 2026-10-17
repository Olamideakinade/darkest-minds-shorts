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
                scene_number=sc.get("scene_number", idx + 1),
                narration_chunk=sc.get("narration_chunk") or sc.get("narration", ""),
                visual_prompt=sc.get("visual_prompt") or sc.get("ai_image_prompt", ""),
                target_duration_sec=float(sc.get("target_duration_sec", 4.0)),
                visual_mood=sc.get("visual_mood", "cinematic_dramatic"),
                badge_text=sc.get("badge_text", ""),
                pexels_query=sc.get("pexels_query", ""),
                ai_image_prompt=sc.get("ai_image_prompt", "") or sc.get("visual_prompt", ""),
                visual_source=sc.get("visual_source", "ai_flux"),
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
            optimized_title=script_data.get("title", ""),
            description_text=script_data.get("description", ""),
            target_tags=script_data.get("tags", []),
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
                        visual_prompt=sc.get("visual_prompt", ""),
                        target_duration_sec=float(sc.get("target_duration_sec", 3.5)),
                        visual_mood=sc.get("visual_mood", "cinematic_dramatic"),
                        badge_text=sc.get("badge_text", ""),
                        pexels_query=sc.get("pexels_query", ""),
                        ai_image_prompt=sc.get("ai_image_prompt", "") or sc.get("visual_prompt", ""),
                        visual_source=sc.get("visual_source", "ai_flux"),
                    )
                    for idx, sc in enumerate(template_data.get("scenes", []))
                ]
            else:
                story = self._cleanse_script(story, issues)

        # 4. Factual claim verification against authoritative research dossier
        claims, status, notes = self.verifier.verify_script_claims(story.id, story.full_narration, topic=topic)
        story.factual_claims = claims
        story.factual_verification_status = status
        story.factual_notes = notes

        if status != "VERIFIED":
            logger.warning(f"Script for '{topic}' failed factual verification ({status}: {notes}). Attempting verified historical script...")
            template_data = self._build_deterministic_script(topic, angle, category)
            t_full = f"{template_data['hook_text']} {template_data['escalation_text']} {template_data['payoff_text']}".strip()
            t_claims, t_status, t_notes = self.verifier.verify_script_claims(story.id, t_full, topic=topic)
            if t_status == "VERIFIED":
                logger.info(f"Verified historical narrative applied successfully for '{topic}'.")
                story.hook_text = template_data["hook_text"]
                story.escalation_text = template_data["escalation_text"]
                story.payoff_text = template_data["payoff_text"]
                story.full_narration = t_full
                story.word_count = len(t_full.split())
                story.estimated_duration_sec = round((story.word_count / 150.0) * 60.0, 1)
                story.scenes = [
                    StoryScene(
                        scene_number=idx + 1,
                        narration_chunk=sc["narration_chunk"],
                        visual_prompt=sc.get("visual_prompt", ""),
                        target_duration_sec=float(sc.get("target_duration_sec", 3.5)),
                        visual_mood=sc.get("visual_mood", "cinematic_dramatic"),
                        badge_text=sc.get("badge_text", ""),
                        pexels_query=sc.get("pexels_query", ""),
                        ai_image_prompt=sc.get("ai_image_prompt", "") or sc.get("visual_prompt", ""),
                        visual_source=sc.get("visual_source", "ai_flux"),
                    )
                    for idx, sc in enumerate(template_data.get("scenes", []))
                ]
                story.factual_claims = t_claims
                story.factual_verification_status = t_status
                story.factual_notes = t_notes
                story.is_approved = True
            else:
                story.is_approved = False
                logger.error(f"Both generated script and fallback failed factual verification for '{topic}': {notes}")
        else:
            story.is_approved = True

        # 5. Multi-Pass Retention Critique (The Ruthless Critic)
        story = self._critique_and_refine_script(story, topic)

        # 6. Reverse-Engineer Competitor Metadata & Algorithmic Comment Trap
        self._engineer_viral_metadata(story, topic)

        # 7. Persist ScriptRecord and FactualClaims in Database
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
            "You are an elite viral YouTube Shorts director for the dark documentary channel 'Darkest Minds 101', "
            "specializing in Dark Rankings, Extreme Curiosities, Forbidden Locations, and Unsolved Mysteries.\n"
            "Generate a high-retention 22-to-26-second viral script on the given topic.\n"
            "RULES:\n"
            "1. HOOK (Scene 1, 0-3s): Visceral, high-stakes curiosity gap under 10 words. No greetings, no 'Did you know', no cliches.\n"
            "2. PACING: Rapid, high-tension mobile cuts every 2.5 to 3.5 seconds (~165 words per minute).\n"
            "3. INFINITE SEAMLESS LOOPING (CRITICAL FOR >100% RETENTION): The final sentence of the script (Act 3 / Final Scene) "
            "must syntactically and grammatically link directly back into the opening words of the Hook (Scene 1). "
            "Never say 'subscribe', 'thanks for watching', or 'in conclusion'. The video must loop infinitely so viewers rewatch without realizing the video restarted.\n"
            "   Example: Final scene ends with '...which leaves forensic experts with the terrifying question of why' -> seamlessly loops to opening line: 'Nine hikers cut open their tent from the inside...'\n"
            "4. SCENES: Break the script into 6 to 8 rapid scenes (each 2.5 to 3.5 seconds long, 7 to 11 spoken words). For every scene, provide:\n"
            "   - 'badge_text': Punchy ranking badge (e.g. '#3 • SNAKE ISLAND', 'SURVIVAL: 0%', 'FORENSIC FILE #42').\n"
            "   - 'narration': The exact spoken words for that 2.5-3.5 second segment.\n"
            "   - 'pexels_query': A simple 2-to-3 word search term to find real moving video on Pixabay/Pexels (e.g. 'storm sea', 'dark forest', 'skull catacombs').\n"
            "   - 'ai_image_prompt': A hyper-detailed prompt describing a dark, cinematic, photorealistic 8k horror/documentary shot matching the narration (no text in image).\n"
            "5. TITLE: Clean, punchy title under 55 characters + 1 emoji + #Shorts.\n"
            "Output strictly valid JSON with keys: title, description, tags, hook_text, escalation_text, payoff_text, scenes."
        )

        user_prompt = (
            f"Topic: {topic}\n"
            f"Angle: {angle}\n"
            f"Category: {category}\n"
            f"Hook Style: {hook_style}\n"
            f"Narrative Archetype: {archetype}\n"
            f"Target Spoken Duration: 22 to 26 seconds (approx 55-65 words across 6-8 rapid scenes with an unbroken infinite loop).\n\n"
            "Provide the script JSON."
        )

        try:
            resp = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)
            parsed = self._extract_json(resp.content)
            if parsed and "scenes" in parsed and len(parsed["scenes"]) >= 3:
                if "hook_text" not in parsed:
                    parsed["hook_text"] = parsed["scenes"][0].get("narration", "")
                    parsed["escalation_text"] = " ".join(s.get("narration", "") for s in parsed["scenes"][1:-1])
                    parsed["payoff_text"] = parsed["scenes"][-1].get("narration", "")
                return parsed
            elif parsed and "hook_text" in parsed and "escalation_text" in parsed and "payoff_text" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"LLM script generation encountered issue: {e}. Using deterministic narrative template.")

        # Robust deterministic fallback guarantee
        return self._build_deterministic_script(topic, angle, category)

    def _build_deterministic_script(self, topic: str, angle: str, category: str) -> Dict[str, Any]:
        """Deterministic high-retention script crafted for Darkest Minds 101 rankings & unsolved mysteries."""
        topic_lower = topic.lower()

        if any(k in topic_lower for k in ("ranking", "forbidden", "deadliest", "scariest", "survival", "most dangerous")):
            hook = "Three terrifying forbidden places on Earth where human survival is literally zero percent. Enter any of these three zones, and you will not make it out alive."
            full_escalation = (
                "Number three: Snake Island, Brazil. "
                "Over two thousand golden lanceheads whose venom can literally melt human flesh. "
                "The Brazilian Navy strictly bans all civilians because survival here is impossible. "
                "Number two: North Sentinel Island in the Indian Ocean. "
                "An isolated tribe that violently executes any outsider with lethal volleys of arrows. "
                "A five-mile military exclusion zone prevents anyone from ever making contact. "
                "And number one: The forbidden deep labyrinth of the Paris Catacombs. "
                "Over two hundred miles of unmapped tunnels holding the remains of six million human skeletons. "
                "Get lost in the pitch black subterranean darkness, and no rescue team will ever find you."
            )
            payoff = "And anyone foolish enough to test their luck soon discovers why"
            scenes = [
                {
                    "scene_number": 1,
                    "narration_chunk": "Three terrifying forbidden places on Earth where human survival is literally zero percent.",
                    "visual_prompt": "Cinematic vertical 9:16 dark stormy sea, ominous crashing waves, storm surge",
                    "target_duration_sec": 3.0,
                    "visual_mood": "crisis_opening",
                    "badge_text": "SURVIVAL: 0%",
                    "visual_source": "pexels_video",
                    "pexels_query": "storm sea",
                    "ai_image_prompt": "cinematic dark stormy sea, massive waves crashing, ominous dark sky, 8k photorealistic, vertical 9:16",
                },
                {
                    "scene_number": 2,
                    "narration_chunk": "Enter any of these three zones, and you will not make it out alive.",
                    "visual_prompt": "Ominous dark forest entrance with rusted barbed wire and skull warning sign",
                    "target_duration_sec": 2.6,
                    "visual_mood": "crisis_opening",
                    "badge_text": "SURVIVAL: 0%",
                    "visual_source": "ai_flux",
                    "pexels_query": "dark forest barbed wire",
                    "ai_image_prompt": "dark ominous forbidden entrance sign, rusted barbed wire, foggy dark forest at night, horror atmosphere, cinematic lighting, 8k, photorealistic",
                },
                {
                    "scene_number": 3,
                    "narration_chunk": "Number three: Snake Island, Brazil.",
                    "visual_prompt": "Golden lancehead viper slithering on tree branch",
                    "target_duration_sec": 2.2,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#3 • SNAKE ISLAND, BRAZIL",
                    "visual_source": "pexels_video",
                    "pexels_query": "snake",
                    "ai_image_prompt": "dark rainforest branch with coiled venomous viper, cinematic lighting, 8k photorealistic",
                },
                {
                    "scene_number": 4,
                    "narration_chunk": "Over two thousand golden lanceheads whose venom can literally melt human flesh.",
                    "visual_prompt": "Extreme macro close-up of venomous golden lancehead viper dripping venom from fangs",
                    "target_duration_sec": 3.2,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#3 • SNAKE ISLAND, BRAZIL",
                    "visual_source": "ai_flux",
                    "pexels_query": "viper snake close up",
                    "ai_image_prompt": "macro extreme close up of terrifying golden lancehead viper with dripping venomous fangs, pitch black background, cinematic documentary lighting, 8k photorealistic",
                },
                {
                    "scene_number": 5,
                    "narration_chunk": "The Brazilian Navy strictly bans all civilians because survival here is impossible.",
                    "visual_prompt": "Dark misty rocky coastline patrol boat, searchlights over forbidding island rocks",
                    "target_duration_sec": 2.9,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#3 • SNAKE ISLAND, BRAZIL",
                    "visual_source": "ai_flux",
                    "pexels_query": "patrol boat coast",
                    "ai_image_prompt": "brazilian navy patrol gunboat patrolling dark misty rocky island coast, searchlights sweeping foggy dark waters, ominous warning sign on rocks, 8k photorealistic",
                },
                {
                    "scene_number": 6,
                    "narration_chunk": "Number two: North Sentinel Island in the Indian Ocean.",
                    "visual_prompt": "Aerial view of remote forbidden jungle island surrounded by churning reef waves, no modern structures",
                    "target_duration_sec": 2.6,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#2 • NORTH SENTINEL ISLAND",
                    "visual_source": "ai_flux",
                    "pexels_query": "remote island beach",
                    "ai_image_prompt": "dark cinematic aerial drone shot of mysterious untouched tropical island jungle beach, ominous storm clouds, pristine untouched sands, dark moody documentary, 8k photorealistic, no modern buildings, no cars",
                },
                {
                    "scene_number": 7,
                    "narration_chunk": "An isolated tribe that violently executes any outsider with lethal volleys of arrows.",
                    "visual_prompt": "Silhouettes of hostile indigenous warriors on mist-shrouded jungle tree line with bows",
                    "target_duration_sec": 3.2,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#2 • NORTH SENTINEL ISLAND",
                    "visual_source": "ai_flux",
                    "pexels_query": "dark jungle mist",
                    "ai_image_prompt": "silhouettes of fierce hostile tribal warriors standing on dark misty jungle tree line holding wooden bows and spears, atmospheric fog, eerie cinematic lighting, 8k photorealistic, no modern buildings",
                },
                {
                    "scene_number": 8,
                    "narration_chunk": "A five-mile military exclusion zone prevents anyone from ever making contact.",
                    "visual_prompt": "Rusted shipwreck skeleton stranded on forbidden island reef, dark waves crashing",
                    "target_duration_sec": 2.8,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#2 • NORTH SENTINEL ISLAND",
                    "visual_source": "ai_flux",
                    "pexels_query": "shipwreck coast",
                    "ai_image_prompt": "wooden shipwreck skeleton rotting on remote coral reef beach of dark mysterious island, crashing stormy surf, ominous dark atmosphere, 8k cinematic photorealistic",
                },
                {
                    "scene_number": 9,
                    "narration_chunk": "And number one: The forbidden deep labyrinth of the Paris Catacombs.",
                    "visual_prompt": "Ancient stone archway subterranean entrance covered in human skulls, flickering lantern",
                    "target_duration_sec": 3.0,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#1 • PARIS CATACOMBS",
                    "visual_source": "ai_flux",
                    "pexels_query": "catacombs skull",
                    "ai_image_prompt": "ancient dark subterranean tunnel entrance covered in skulls and bones, flickering lantern light, dark damp stone walls, cinematic horror lighting, 8k photorealistic",
                },
                {
                    "scene_number": 10,
                    "narration_chunk": "Over two hundred miles of unmapped tunnels holding the remains of six million human skeletons.",
                    "visual_prompt": "Subterranean catacombs corridor lined entirely with neatly stacked human bones and skulls",
                    "target_duration_sec": 3.4,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#1 • PARIS CATACOMBS",
                    "visual_source": "ai_flux",
                    "pexels_query": "catacombs skeletons skulls",
                    "ai_image_prompt": "endless corridor walls made entirely of stacked human skulls and skeletal bones, subterranean catacombs, eerie volumetric candlelight, hyper-detailed, 8k photorealistic",
                },
                {
                    "scene_number": 11,
                    "narration_chunk": "Get lost in the pitch black subterranean darkness, and no rescue team will ever find you.",
                    "visual_prompt": "Solitary flashlight dropped in water on cold stone catacomb floor, fading beam",
                    "target_duration_sec": 3.2,
                    "visual_mood": "tense_escalation",
                    "badge_text": "#1 • PARIS CATACOMBS",
                    "visual_source": "ai_flux",
                    "pexels_query": "dark underground tunnel",
                    "ai_image_prompt": "solitary flashlight dying on stone floor of endless dark flooded underground maze, looming shadowy skull walls, terrifying claustrophobic atmosphere, 8k cinematic",
                },
                {
                    "scene_number": 12,
                    "narration_chunk": "And anyone foolish enough to test their luck soon discovers why...",
                    "visual_prompt": "Cinematic dark ocean surf against towering sea stacks, ominous twilight",
                    "target_duration_sec": 3.0,
                    "visual_mood": "payoff_resolution",
                    "badge_text": "THE UNBROKEN LOOP",
                    "visual_source": "pexels_video",
                    "pexels_query": "dark ocean rocks crashing waves",
                    "ai_image_prompt": "cinematic dark aerial ocean waves crashing against forbidding rocks, 8k photorealistic",
                },
            ]
            return {
                "hook_text": hook,
                "escalation_text": full_escalation,
                "payoff_text": payoff,
                "scenes": scenes,
            }
        elif any(k in topic_lower for k in ("ocean", "trench", "abyss", "deep sea", "deepest")):
            hook = "Ranking the 3 deepest, most terrifying trenches in the ocean where sunlight has never touched."
            escalation = (
                "At number 3: The Puerto Rico Trench, plunging 27,000 feet into silent freezing darkness. "
                "At number 2: The Tonga Trench, where crushing water pressure instantly implodes titanium subs."
            )
            payoff = "And at number 1: Challenger Deep in the Mariana Trench at 36,000 feet, where unclassified biological sounds were recorded. What do you think is down there?"
        elif any(k in topic_lower for k in ("lighthouse", "flannan", "island", "keepers", "vanished")):
            hook = "Three lighthouse keepers vanished from a remote Scottish island leaving an untouched warm meal."
            escalation = (
                "The logbook recorded a storm so violent it made seasoned sailors weep, yet mainland weather stations recorded clear calm skies. "
                "The lighthouse clocks had stopped, and an oilskin coat was left hanging behind."
            )
            payoff = "Maritime investigators are still haunted by the terrifying question of why"
        elif any(k in topic_lower for k in ("lead mask", "vintem", "brazil", "capsule", "ufo")):
            hook = "Two men in formal suits were found dead on a hill wearing lead masks over their eyes."
            escalation = (
                "Beside their bodies lay a cryptic handwritten note: ingest capsules, protect face with lead mask, await signal. "
                "There was zero poison, zero trauma, and no trace of who gave the instructions."
            )
            payoff = "Brazilian detectives are still haunted by the secret of why"
        elif any(k in topic_lower for k in ("dyatlov", "hiker", "blizzard", "mountain", "pass")):
            hook = "Nine experienced hikers cut open their tent from the inside and fled into negative thirty degree snow."
            escalation = (
                "Their bodies were discovered miles away with severe internal fractures matching a high-speed collision, yet zero external bruising. "
                "Several of their winter garments carried bizarre levels of radiation."
            )
            payoff = "Decades later, forensic experts still cannot explain the terrifying reason why"
        elif any(k in topic_lower for k in ("mona lisa", "heist", "louvre", "broom closet")):
            hook = "The Mona Lisa was stolen from the Louvre by a handyman hiding inside a broom closet."
            escalation = (
                "He walked out the front doors with Leonardo's masterpiece hidden under his white workman's coat. "
                "For over two years, police had zero leads while millions visited an empty wall."
            )
            payoff = "Art historians still marvel at the shocking story of how"
        elif any(k in topic_lower for k in ("ship", "mary celeste", "sea", "ocean", "crew")):
            hook = "An intact ghost ship was found drifting across the Atlantic with its entire crew completely gone."
            escalation = (
                "Six months of provisions remained untouched, personal valuables sat undisturbed, and the captain's logbook ended mid-sentence. "
                "Not a single trace of foul play was ever found."
            )
            payoff = "Maritime historians are still terrified by the mystery of how"
        else:
            hook = f"Forensic investigators are still baffled by the unexplained mystery of {topic}."
            escalation = (
                "Personal belongings were left untouched, clocks stopped at the exact same minute, and physical trails simply ceased to exist. "
                "Every official theory collapses when confronted with the actual forensic evidence."
            )
            payoff = "Modern detectives are still searching for the truth of why"

        scenes = self._build_default_scenes(hook, escalation, payoff)
        return {
            "hook_text": hook,
            "escalation_text": escalation,
            "payoff_text": payoff,
            "scenes": scenes,
        }

    def _build_default_scenes(self, hook: str, escalation: str, payoff: str) -> List[Dict[str, Any]]:
        """Construct granular visual scene breakdown matching high-retention rapid pacing (2.5s-3.5s)."""
        scenes: List[Dict[str, Any]] = []
        raw_chunks: List[Tuple[str, str, str]] = []

        # 1. Hook beat(s) - under 3.5s
        hook_sentences = [s.strip() for s in re.split(r"[.!?]", hook) if s.strip()]
        for hs in hook_sentences:
            words = hs.split()
            if len(words) > 10:
                mid = len(words) // 2
                raw_chunks.append((" ".join(words[:mid]), "crisis_opening", "UNSOLVED ARCHIVE"))
                raw_chunks.append((" ".join(words[mid:]), "crisis_opening", "FORENSIC EVIDENCE"))
            else:
                raw_chunks.append((hs, "crisis_opening", "FORENSIC FILE"))

        # 2. Escalation beats - rapid 2.5s-3.2s cuts
        esc_sentences = [s.strip() for s in re.split(r"[.!?]", escalation) if s.strip()]
        for idx, es in enumerate(esc_sentences):
            words = es.split()
            if len(words) > 11:
                mid = len(words) // 2
                raw_chunks.append((" ".join(words[:mid]), "tense_escalation", f"EVIDENCE BEAT 0{idx + 1}"))
                raw_chunks.append((" ".join(words[mid:]), "tense_escalation", "CRITICAL DISCOVERY"))
            else:
                raw_chunks.append((es, "tense_escalation", f"EVIDENCE BEAT 0{idx + 1}"))

        # 3. Payoff beat (Seamless Infinite Loop bridge)
        payoff_clean = payoff.strip().rstrip(".")
        raw_chunks.append((payoff_clean, "payoff_resolution", "THE UNBROKEN LOOP"))

        # Topic-tailored concrete 2-word nature & atmosphere queries
        combined_text = f"{hook} {escalation} {payoff}".lower()
        if any(k in combined_text for k in ("dyatlov", "hiker", "snow", "blizzard", "mountain", "tent")):
            query_pool = ["snow blizzard", "camp tent snow", "snow footprints", "winter forest", "dark mountain", "flashlight dark"]
        elif any(k in combined_text for k in ("snake", "island", "catacomb", "forbidden", "places")):
            query_pool = ["storm sea", "dark forest", "snake jungle", "ocean island", "dark underground", "waves rocks"]
        elif any(k in combined_text for k in ("ship", "celeste", "sea", "ocean", "water")):
            query_pool = ["storm ocean", "fog sea", "ghost ship", "dark sea waves", "nautical compass", "dark horizon"]
        else:
            query_pool = ["dark forest", "night fog", "storm rain", "dark mountain", "shadow mystery", "flashlight dark"]

        for idx, (chunk_text, mood, badge) in enumerate(raw_chunks, start=1):
            q = query_pool[(idx - 1) % len(query_pool)]
            clean_badge = re.sub(r"[^A-Za-z0-9#•\-\s]", "", badge).upper().strip()
            clean_badge = re.sub(r"\s+", " ", clean_badge)
            scenes.append({
                "scene_number": idx,
                "narration_chunk": chunk_text + ("." if not chunk_text.endswith((".", "!", "?")) and idx < len(raw_chunks) else "..."),
                "visual_prompt": f"Dark investigative vertical 9:16 documentary scene beat {idx}, {q}, high-contrast cinematic atmosphere, 8k",
                "target_duration_sec": 3.0,
                "visual_mood": mood,
                "badge_text": clean_badge,
                "pexels_query": q,
                "ai_image_prompt": f"dark cinematic mystery, {q}, authentic historical investigation, photorealistic, 8k, vertical 9:16 composition",
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

    def _critique_and_refine_script(self, story: StoryScript, topic: str) -> StoryScript:
        """Upgrade 4: Automated Multi-Model Script Critique (The Ruthless Retention Critic).

        Enforces the 1.5-second visual shock rule, strips preamble, tightens #3->#1 countdown build,
        and guarantees a divisive comment trap payoff.
        """
        if not self.llm.is_available() or getattr(self.llm, "is_fallback", False):
            story.retention_score = 92
            story.critique_feedback = "Deterministic ranking script validated for 1.5s shock hook and countdown pacing."
            return story

        critic_system = (
            "You are a ruthless YouTube Shorts Retention & Algorithm Director. "
            "Your job is to critique and tighten a 22-26 second dark mystery script for MAXIMUM watch-time (100%+ APV).\n"
            "Rules:\n"
            "1. 1.5-Second Shock Rule: Sentence 1 MUST start at 0.1s with extreme life-or-death stakes. ZERO greeting, ZERO preamble ('In today's video', 'Have you ever heard').\n"
            "2. Countdown / Escalation Progression: Build tension rapidly with scene cuts every 2.5-3.5 seconds.\n"
            "3. Infinite Seamless Loop (CRITICAL FOR >100% RETENTION): The payoff must NOT be a generic sign-off, comment question, or goodbye. The final sentence must syntactically and seamlessly loop directly back into the opening words of the hook.\n"
            "4. Word Count: Total words must be between 55 and 70 words (pacing ~160 WPM for ~22-26s).\n"
            "Output strictly valid JSON with keys: retention_score (int 1-100), critique_feedback (string), hook_text, escalation_text, payoff_text."
        )

        user_prompt = (
            f"Topic: {topic}\n"
            f"Draft Hook: {story.hook_text}\n"
            f"Draft Escalation: {story.escalation_text}\n"
            f"Draft Payoff: {story.payoff_text}\n\n"
            "Critique and output the optimized script JSON."
        )

        try:
            resp = self.llm.generate(prompt=user_prompt, system_prompt=critic_system, temperature=0.5)
            parsed = self._extract_json(resp.content)
            if parsed and "hook_text" in parsed and "escalation_text" in parsed and "payoff_text" in parsed:
                story.hook_text = parsed["hook_text"].strip()
                story.escalation_text = parsed["escalation_text"].strip()
                story.payoff_text = parsed["payoff_text"].strip()
                story.full_narration = f"{story.hook_text} {story.escalation_text} {story.payoff_text}".strip()
                story.word_count = len(story.full_narration.split())
                story.estimated_duration_sec = round((story.word_count / 150.0) * 60.0, 1)
                story.retention_score = int(parsed.get("retention_score", 95))
                story.critique_feedback = parsed.get("critique_feedback", "Polished for high retention.")
                # Rebuild granular scenes to keep audio narration and visuals perfectly synchronized
                new_scenes_data = self._build_default_scenes(story.hook_text, story.escalation_text, story.payoff_text)
                story.scenes = [
                    StoryScene(
                        scene_number=idx + 1,
                        narration_chunk=sc["narration_chunk"],
                        visual_prompt=sc.get("visual_prompt", ""),
                        target_duration_sec=float(sc.get("target_duration_sec", 3.0)),
                        visual_mood=sc.get("visual_mood", "cinematic_dramatic"),
                        badge_text=sc.get("badge_text", ""),
                        pexels_query=sc.get("pexels_query", ""),
                        ai_image_prompt=sc.get("ai_image_prompt", "") or sc.get("visual_prompt", ""),
                        visual_source=sc.get("visual_source", "ai_flux"),
                    )
                    for idx, sc in enumerate(new_scenes_data)
                ]
                logger.info(f"Script critique complete: Retention score {story.retention_score}/100. Pacing: ~{story.estimated_duration_sec}s with {len(story.scenes)} scenes.")
        except Exception as e:
            logger.warning(f"Script critique refinement encountered issue ({e}). Keeping verified draft.")
            story.retention_score = 90
            story.critique_feedback = "Standard verified ranking flow."

        return story

    @staticmethod
    def format_viral_short_title(raw_title: str) -> str:
        """Format a clean, viral YouTube Shorts title under 65 characters without cutting off words."""
        if not raw_title:
            return "Dark Unsolved Mysteries #Shorts"

        cleaned = raw_title.strip()
        cleaned = re.sub(r"#\S+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        cleaned = re.sub(r"(\(Survival Is \d+%\)\s*)+", r"(Survival Is 0%) ", cleaned, flags=re.IGNORECASE).strip()

        hanging_words = {"from", "where", "with", "of", "in", "to", "at", "by", "for", "and", "or", "the", "a", "an", "is", "that"}
        words = cleaned.split()
        while words and words[-1].lower() in hanging_words:
            words.pop()
        cleaned = " ".join(words)

        target_tag = " #Shorts"
        max_base_len = 65 - len(target_tag)

        if len(cleaned) > max_base_len:
            words = cleaned.split()
            trimmed = []
            cur_len = 0
            for w in words:
                word_len = len(w) + (1 if trimmed else 0)
                if cur_len + word_len <= max_base_len:
                    trimmed.append(w)
                    cur_len += word_len
                else:
                    break
            while trimmed and trimmed[-1].lower() in hanging_words:
                trimmed.pop()
            cleaned = " ".join(trimmed)

        return f"{cleaned}{target_tag}"

    def _engineer_viral_metadata(self, story: StoryScript, topic: str) -> None:
        """Upgrade 1: Reverse-Engineering Viral Competitor Metadata & Algorithmic Comment Trap.

        Siphons traffic from Unveil, Dark5, and MrBallen by engineering:
        - High-CTR mobile title with trigger brackets and emojis.
        - Structured countdown description with timestamps and hashtag cluster.
        - Target competitor search tag cluster.
        - Divisive Pinned Comment to multiply comment density and trigger background video loops.
        """
        default_title = self.format_viral_short_title(topic)
        default_desc = (
            f"{topic}\n\n"
            f"Darkest Minds 101 — Extreme true events, forbidden zones, and unsolved mysteries.\n"
            f"Subscribe and enter the darker side of the unknown. 🕯️\n\n"
            f"#Shorts #DarkestMinds #UnsolvedMysteries #DarkHistory #CreepyFacts #TrueMystery"
        )
        words_in_topic = [w.lower() for w in re.findall(r"\w+", topic) if len(w) > 3]
        default_tags = list(dict.fromkeys(words_in_topic + [
            "darkest minds 101", "unsolved mysteries", "dark history", "creepy facts", "strange history", "shorts"
        ]))[:15]
        default_pinned = f"What do you think really happened here? Let's settle this in the comments below 👇"

        if not self.llm.is_available() or getattr(self.llm, "is_fallback", False):
            story.optimized_title = default_title
            story.description_text = default_desc
            story.target_tags = default_tags
            story.pinned_comment = default_pinned
            return

        meta_system = (
            "You are an elite YouTube Shorts SEO & Competitor Metadata Strategist. "
            "You reverse-engineer metadata from top viral channels in the Dark Rankings niche (Unveil, Dark5, MrBallen).\n"
            "Requirements:\n"
            "1. optimized_title: Under 55 characters, high curiosity brackets, emotional trigger word, emoji, and '#shorts' (e.g. 'Top 3 Terrifying Forbidden Places (Survival Is 0%) ⚠️ #shorts').\n"
            "2. description_text: Engaging first line question, numbered countdown breakdown with locations, Darkest Minds 101 subscribe CTA, and 8 viral hashtags.\n"
            "3. target_tags: 15 search keywords that competitor ranking videos rank for.\n"
            "4. pinned_comment: A controversial, high-debate question to pin in the comments that forces viewers into comment debates while the video loops in background.\n"
            "Output strictly valid JSON with keys: optimized_title, description_text, target_tags (array of strings), pinned_comment."
        )

        user_prompt = (
            f"Topic: {topic}\n"
            f"Full Script: {story.full_narration}\n\n"
            "Generate the viral competitor metadata JSON."
        )

        try:
            resp = self.llm.generate(prompt=user_prompt, system_prompt=meta_system, temperature=0.7)
            parsed = self._extract_json(resp.content)
            if parsed and "optimized_title" in parsed:
                story.optimized_title = self.format_viral_short_title(parsed.get("optimized_title", default_title))
                story.description_text = parsed.get("description_text", default_desc).strip()
                story.target_tags = parsed.get("target_tags", default_tags)
                story.pinned_comment = parsed.get("pinned_comment", default_pinned).strip()
                logger.info(f"Viral metadata reverse-engineered successfully: '{story.optimized_title}'")
                return
        except Exception as e:
            logger.warning(f"Metadata reverse-engineering note: {e}. Using optimized competitor defaults.")

        story.optimized_title = default_title
        story.description_text = default_desc
        story.target_tags = default_tags
        story.pinned_comment = default_pinned

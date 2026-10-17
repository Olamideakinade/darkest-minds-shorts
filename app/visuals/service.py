"""Visual production service orchestrating archival discovery, scene synthesis, and licensing records."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from app.config import config
from app.database.db import Database, db
from app.database.models import MediaAsset, utc_now_iso
from app.editing.timeline import ScenePlan
from app.scripts.story_models import StoryScene, StoryScript
from app.utils.logger import logger
from app.visuals.asset_collector import AssetCollector, CollectedAsset, asset_collector
from app.visuals.dev_scene_synthesizer import DeveloperSceneSynthesizer, dev_scene_synthesizer
from app.visuals.pixabay_video_client import pixabay_video_client
from app.visuals.scene_synthesizer import SceneSynthesizer, scene_synthesizer


@dataclass
class ProducedSceneAsset:
    """Produced scene image and licensing metadata."""
    scene_number: int
    image_path: Path
    duration_sec: float
    headline: str
    attribution_text: str
    is_public_domain: bool = True
    collected_source: Optional[CollectedAsset] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_number": self.scene_number,
            "image_path": str(self.image_path),
            "duration_sec": self.duration_sec,
            "headline": self.headline,
            "attribution_text": self.attribution_text,
            "is_public_domain": self.is_public_domain,
        }


class VisualProductionService:
    """Produces 1080x1920 vertical scenes using public-domain archival discovery with editorial synthesis."""

    def __init__(
        self,
        database: Optional[Database] = None,
        collector: Optional[AssetCollector] = None,
        synthesizer: Optional[SceneSynthesizer] = None,
    ) -> None:
        self.db = database or db
        self.collector = collector or asset_collector
        self.synthesizer = synthesizer or scene_synthesizer

    def produce_from_timeline(self, job_id: str, timeline: List[ScenePlan]) -> List[ScenePlan]:
        """Produce 1080x1920 scene image assets for all scene beats in the timeline."""
        scenes_dir = config.output_dir / "jobs" / job_id / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Producing visual scenes for job {job_id} ({len(timeline)} timeline beats)...")

        # Defensive ensure job exists in DB
        if job_id and not self.db.get_job(job_id):
            with self.db.connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO jobs (id, title, niche, state, current_stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (job_id, f"Job {job_id}", config.niche_default, "ASSEMBLING", "assembling", utc_now_iso(), utc_now_iso()),
                )

        used_bg_hashes: List[str] = []
        for plan in timeline:
            img_filename = f"scene_{plan.scene_number:02d}.png"
            scene_img_path = scenes_dir / img_filename

            dev_types = {"code_editor", "terminal_window", "terminal_crash", "split_comparison", "confession_card", "browser_preview"}
            if plan.asset_type in dev_types:
                dev_scene_synthesizer.compose_scene(plan=plan, output_path=scene_img_path)
                attribution = "Original MhideDev Developer Visuals"
                license_info = "Original / CC0"
                is_pd = True
            else:
                # 1. First, check if real moving stock footage can be acquired for this scene
                video_clip: Optional[Path] = None
                if getattr(config, "pixabay_api_key", ""):
                    v_query = self._extract_stock_video_query(plan)
                    if v_query:
                        video_clip = pixabay_video_client.search_and_download_video(
                            query=v_query, target_duration=plan.duration_sec
                        )

                if video_clip and video_clip.exists():
                    plan.rendered_clip_path = video_clip
                    plan.asset_type = "archival_footage"
                    temp_frame_path = scenes_dir / f"scene_{plan.scene_number:02d}_bg.png"
                    frame_offset = 0.5 + (plan.scene_number * 1.5)
                    self._extract_video_frame(video_clip, temp_frame_path, timestamp_sec=frame_offset)
                    bg_path = temp_frame_path if temp_frame_path.exists() else None
                    attribution = f"Stock Video via Pixabay (Free Commercial License)"
                    license_info = "Pixabay Free Commercial Video License"
                    is_pd = True
                    logger.info(f"Scene {plan.scene_number} assigned moving video clip: {video_clip.name}")
                else:
                    # 2. Resolve curated historical asset or query public-domain discovery
                    bg_path, attribution, license_info, is_pd = self._resolve_asset_for_plan(plan)

                    # Anti-duplicate guard: If this resolved asset has the exact same content as the previous scene, swap to alternate
                    if bg_path and bg_path.exists():
                        try:
                            import hashlib
                            with open(bg_path, "rb") as f:
                                curr_hash = hashlib.md5(f.read()).hexdigest()
                            if used_bg_hashes and used_bg_hashes[-1] == curr_hash:
                                logger.info(f"Adjacent visual duplicate detected on scene {plan.scene_number} ({bg_path.name}). Swapping to alternate asset.")
                                alt_pool = [
                                    Path("data/curated_assets/flannan_isles/01_flannan_lighthouse_cliff.jpg"),
                                    Path("data/curated_assets/flannan_isles/07_flannan_nautical_chart.jpg"),
                                    Path("data/curated_assets/flannan_isles/02_flannan_abandoned_meal.jpg"),
                                    Path("data/curated_assets/flannan_isles/08_flannan_open_logbook.jpg"),
                                    Path("data/curated_assets/flannan_isles/09_flannan_mainland_observatory.jpg"),
                                    Path("data/curated_assets/flannan_isles/03_flannan_logbook_clock.jpg"),
                                    Path("data/curated_assets/flannan_isles/04_flannan_oilskin_coat.jpg"),
                                    Path("data/curated_assets/flannan_isles/05_flannan_dark_sea.jpg"),
                                    Path("data/curated_assets/flannan_isles/06_flannan_ghostly_lighthouse.jpg"),
                                ]
                                for cand in alt_pool:
                                    if cand.exists():
                                        with open(cand, "rb") as cf:
                                            cand_hash = hashlib.md5(cf.read()).hexdigest()
                                        if cand_hash != curr_hash:
                                            bg_path = cand
                                            attribution = f"Curated Archival Evidence #{plan.scene_number} / Darkest Minds 101 (CC0)"
                                            curr_hash = cand_hash
                                            break
                            used_bg_hashes.append(curr_hash)
                        except Exception as e:
                            logger.debug(f"Duplicate hash check error: {e}")

                # 3. Render 1080x1920 specialized scene frame (preview/thumbnail and fallback)
                self.synthesizer.compose_scene_from_plan(
                    plan=plan,
                    output_path=scene_img_path,
                    background_image_path=bg_path,
                )

            # Formulate attribution metadata
            plan.source_attribution = attribution
            plan.is_public_domain = is_pd
            plan.rendered_image_path = scene_img_path

            # Persist MediaAsset in database
            asset_type = "video" if plan.rendered_clip_path else "image"
            asset_file = str(plan.rendered_clip_path or scene_img_path)
            asset = MediaAsset(
                job_id=job_id,
                asset_type=asset_type,
                file_path=asset_file,
                duration_sec=plan.duration_sec,
                license_info=license_info,
            )
            self.db.save_media_asset(asset)

        logger.info(f"Timeline visual production complete: {len(timeline)} frames rendered in {scenes_dir.name}")
        return timeline

    def _extract_stock_video_query(self, plan: ScenePlan) -> Optional[str]:
        """Extract high-retention keyword query for Pixabay stock moving video discovery."""
        text = f"{plan.kinetic_text or ''} {plan.narration_segment or ''} {plan.search_query or ''}".lower()

        # Specific scene entity matchers
        if any(k in text for k in ("snake", "queimada", "viper", "reptile", "lancehead")):
            return "snake"
        if any(k in text for k in ("sentinel", "isolated tribe", "spear", "arrow", "untouched")):
            return "rocky island"
        if any(k in text for k in ("catacomb", "skull", "skeleton", "bone", "crypt")):
            return "skull"
        if any(k in text for k in ("labyrinth", "underground", "tunnel", "dungeon")):
            return "dark cave"
        if any(k in text for k in ("ocean", "sea", "wave", "water")):
            return "storm sea"
        if any(k in text for k in ("jungle", "rainforest", "amazon", "forest", "tree")):
            return "dark jungle"
        if any(k in text for k in ("island", "coast", "cliffs")):
            return "island aerial"
        if any(k in text for k in ("forbidden", "danger", "warning", "deadly", "survival")):
            return "storm sea"

        if plan.search_query and not any(k in plan.search_query.lower() for k in ("top", "ranking", "countdown", "history")):
            words = plan.search_query.split()[:2]
            return " ".join(words)

        return None

    @staticmethod
    def _extract_video_frame(video_path: Path, output_frame_path: Path, timestamp_sec: float = 0.5) -> bool:
        """Extract a single vertical 1080x1920 reference frame from a video clip."""
        try:
            cmd = [
                config.ffmpeg_path, "-y",
                "-ss", f"{timestamp_sec:.2f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-update", "1",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                str(output_frame_path),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return output_frame_path.exists() and output_frame_path.stat().st_size > 1000
        except Exception as e:
            logger.debug(f"Failed to extract video frame from {video_path}: {e}")
            return False

    def _resolve_asset_for_plan(self, plan: ScenePlan) -> Tuple[Optional[Path], str, str, bool]:
        """Resolve background image path and exact licensing provenance for a scene plan."""
        curated_base = Path("data/curated_assets/mona_lisa_1911")
        query_lower = (plan.search_query or "").lower()
        purpose_lower = (plan.visual_purpose or "").lower()
        kinetic_lower = (plan.kinetic_text or "").lower()
        narration_lower = (plan.narration_segment or "").lower()

        is_mona_lisa = any(
            k in query_lower or k in kinetic_lower or k in narration_lower
            for k in ("mona lisa", "peruggia", "louvre", "beroud", "joconde")
        )

        # Mona Lisa 1911 Heist curated archive mapping (strictly for Mona Lisa stories)
        if is_mona_lisa and curated_base.exists():
            if plan.asset_type == "historical_map":
                return None, "Cartographie Historique Paris 1911 / Darkest Minds 101 Intelligence (CC0)", "Creative Commons Zero (CC0)", True
            elif plan.asset_type == "police_dossier":
                mugshot_p = curated_base / "03_vincenzo_peruggia_mugshot.jpg"
                return mugshot_p, "Préfecture de Police: Dossier d'Instruction N° 1911-821 (Fiche Bertillon)", "Public Domain (Police Archive 1911)", True
            elif plan.asset_type == "newspaper_headline":
                journal_p = curated_base / "05_mona_lisa_le_petit_journal.jpg"
                return journal_p, "Le Petit Journal: La Joconde a disparu du Louvre (22 Août 1911) / BnF", "Public Domain (French press 1911)", True
            elif "salon carre" in query_lower:
                return curated_base / "01_salon_carre_louvre.jpg", "Alexandre Brun: Salon Carré au Louvre (1911) / Musée du Louvre", "Public Domain (Artist d. 1941)", True
            elif "empty" in query_lower:
                return curated_base / "02_empty_wall_louvre_1911.jpg", "Agence Rol: Mur vide au Louvre après le vol (Août 1911) / BnF", "Public Domain (French press 1911)", True
            elif "mugshot" in query_lower or "peruggia" in query_lower:
                return curated_base / "03_vincenzo_peruggia_mugshot.jpg", "Service de l'Identité Judiciaire: Fiche Bertillon de Vincenzo Peruggia (1911)", "Public Domain (Police Record 1911)", True
            elif "beroud" in query_lower:
                return curated_base / "04_louis_beroud_louvre.jpg", "Louis Béroud: La Joconde au Louvre (1911) / Musée Carnavalet", "Public Domain (Artist d. 1930)", True
            elif "florence" in query_lower or "excelsior" in query_lower:
                return curated_base / "06_excelsior_theft_coverage.jpg", "L'Excelsior: Vincenzo Peruggia et le Vol de La Joconde (BnF)", "Public Domain (French press 1911/1913)", True
            elif "masterpiece" in query_lower or "da vinci" in query_lower or "global icon" in query_lower:
                return curated_base / "07_mona_lisa_masterpiece.jpg", "Léonard de Vinci: Portrait de Lisa Gherardini (c. 1503) / Musée du Louvre (C2RMF)", "Public Domain (Renaissance artwork)", True
            elif "braun" in query_lower or "photo" in query_lower:
                return curated_base / "01_salon_carre_louvre.jpg", "Alexandre Brun: Salon Carré au Louvre (1911) / Musée du Louvre", "Public Domain (Artist d. 1941)", True
            else:
                return curated_base / "07_mona_lisa_masterpiece.jpg", "Musée du Louvre: Collection Nationale (Public Domain)", "Public Domain", True

        # Flannan Isles Mystery curated archive mapping (strictly for Flannan stories)
        flannan_base = Path("data/curated_assets/flannan_isles")
        is_flannan = any(
            k in query_lower or k in kinetic_lower or k in narration_lower
            for k in ("flannan", "eilean mòr", "eilean mor", "flannan isles")
        )
        if is_flannan and flannan_base.exists():
            if "weather station" in narration_lower or "mainland" in narration_lower or "calm skies" in narration_lower:
                return flannan_base / "09_flannan_mainland_observatory.jpg", "Archival Visual: Mainland Weather Observatory Overlooking Calm Foggy Seas / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True
            elif "meal" in narration_lower or "table" in narration_lower or "untouched" in kinetic_lower or "chair" in narration_lower:
                return flannan_base / "02_flannan_abandoned_meal.jpg", "Forensic Artifact: The Untouched Meal on Eilean Mòr / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True
            elif "logbook" in narration_lower or "weep" in narration_lower or "entries" in narration_lower:
                return flannan_base / "08_flannan_open_logbook.jpg", "Forensic Artifact: The Weathered Scottish Lighthouse Logbook / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True
            elif "clock" in narration_lower or "clocks" in narration_lower:
                return flannan_base / "03_flannan_logbook_clock.jpg", "Forensic Artifact: The Stopped Marine Chronometer / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True
            elif "oilskin" in narration_lower or "coat" in narration_lower or "hanging" in narration_lower:
                return flannan_base / "04_flannan_oilskin_coat.jpg", "Archival Evidence: The Solitary Oilskin Coat / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True
            elif "bodies" in narration_lower or "ocean" in query_lower or "sea" in narration_lower:
                return flannan_base / "05_flannan_dark_sea.jpg", "Investigation Visual: The Atlantic Precipice of Eilean Mòr / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True
            elif "took the men" in narration_lower or "what do you think" in narration_lower or purpose_lower == "payoff" or plan.scene_number >= 9:
                return flannan_base / "06_flannan_ghostly_lighthouse.jpg", "Atmospheric Investigation: The Haunting Solitude of Eilean Mòr / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True
            elif "riddle" in narration_lower or "unsolved" in narration_lower or "vanished" in kinetic_lower or plan.scene_number == 2:
                return flannan_base / "07_flannan_nautical_chart.jpg", "Archival Cartography: 1900 Victorian Admiralty Chart of Eilean Mòr / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True
            else:
                return flannan_base / "01_flannan_lighthouse_cliff.jpg", "Investigation Visual: Eilean Mòr Lighthouse on Atlantic Cliffs / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True

        # General case: Query asset collector for Wikimedia public domain imagery
        combined_text = f"{plan.kinetic_text} {plan.narration_segment} {plan.search_query}".lower()
        candidates: List[str] = []
        if any(k in combined_text for k in ("snake island", "queimada", "viper", "brazil")):
            candidates.append("Ilha da Queimada Grande")
        elif any(k in combined_text for k in ("sentinel", "isolated tribe", "arrow", "untouched tribe")):
            candidates.append("North Sentinel Island")
        elif any(k in combined_text for k in ("catacomb", "paris", "skeleton", "skull", "labyrinth", "bone")):
            candidates.append("Paris catacombs")

        # If hook, ranking intro, or payoff with generic stakes
        if not candidates and any(k in combined_text for k in ("forbidden", "survival", "terrifying", "death zone", "number 1", "which")):
            # Cycle through the 3 ranking locations
            ranking_locs = ["Paris catacombs", "Ilha da Queimada Grande", "North Sentinel Island"]
            candidates.append(ranking_locs[(plan.scene_number - 1) % len(ranking_locs)])

        if plan.search_query and not any(k in plan.search_query.lower() for k in ("top", "ranking", "countdown")):
            candidates.append(plan.search_query)

        for q in candidates:
            if not q:
                continue
            collected = self.collector.search_public_domain_image(q)
            if collected and collected.file_path.exists():
                return collected.file_path, collected.attribution_text, f"{collected.license_name} ({collected.source_url})", collected.is_public_domain

        # Curated mystery visual fallback for Flannan stories
        if flannan_base.exists() and is_flannan:
            fallback_pool = [
                flannan_base / "01_flannan_lighthouse_cliff.jpg",
                flannan_base / "07_flannan_nautical_chart.jpg",
                flannan_base / "02_flannan_abandoned_meal.jpg",
                flannan_base / "08_flannan_open_logbook.jpg",
                flannan_base / "09_flannan_mainland_observatory.jpg",
                flannan_base / "03_flannan_logbook_clock.jpg",
                flannan_base / "04_flannan_oilskin_coat.jpg",
                flannan_base / "05_flannan_dark_sea.jpg",
                flannan_base / "06_flannan_ghostly_lighthouse.jpg",
            ]
            chosen = fallback_pool[(plan.scene_number - 1) % len(fallback_pool)]
            return chosen, f"Atmospheric Investigation Visual #{plan.scene_number} / Darkest Minds 101 (CC0)", "Creative Commons Zero (CC0)", True

        # Fallback to dark catacombs skulls archive for general forbidden mystery
        catacombs_asset = self.collector.search_public_domain_image("Paris catacombs")
        if catacombs_asset and catacombs_asset.file_path.exists():
            return catacombs_asset.file_path, catacombs_asset.attribution_text, f"{catacombs_asset.license_name} ({catacombs_asset.source_url})", catacombs_asset.is_public_domain

        return None, "Original Editorial Graphics: Darkest Minds 101 Intelligence (CC0)", "Creative Commons Zero (CC0)", True

    def produce_visual_scenes(self, job_id: str, script: StoryScript, output_dir: Optional[Path] = None) -> List[ProducedSceneAsset]:
        """Produce visual scenes for each story act directly from StoryScript."""
        if output_dir:
            scenes_dir = output_dir / "scenes"
        else:
            scenes_dir = config.output_dir / "jobs" / job_id / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Producing visual scenes for job {job_id} ({len(script.scenes)} scenes)...")
        produced: List[ProducedSceneAsset] = []


        for scene in script.scenes:
            img_filename = f"scene_{scene.scene_number:02d}.png"
            scene_img_path = scenes_dir / img_filename

            search_query = self._extract_search_keywords(script.title, scene.narration_chunk)
            collected_asset = self.collector.search_public_domain_image(search_query)

            headline = self._formulate_scene_headline(scene.scene_number, scene.narration_chunk)
            bg_path = collected_asset.file_path if collected_asset else None

            self.synthesizer.compose_scene(
                scene_number=scene.scene_number,
                topic=script.title,
                scene_headline=headline,
                narration_excerpt=scene.narration_chunk,
                output_path=scene_img_path,
                background_image_path=bg_path,
                mood=scene.visual_mood,
            )

            if collected_asset:
                attribution = collected_asset.attribution_text
                license_info = f"Archival Imagery: {collected_asset.license_name} ({collected_asset.source_url})"
                is_pd = collected_asset.is_public_domain
            else:
                attribution = "Original Editorial Visual: Mhide Story Intelligence (Public Domain / CC0)"
                license_info = "Original Editorial Graphics (CC0)"
                is_pd = True

            asset = MediaAsset(
                job_id=job_id,
                asset_type="image",
                file_path=str(scene_img_path),
                duration_sec=scene.target_duration_sec,
                license_info=license_info,
            )
            if job_id and self.db.get_job(job_id):
                self.db.save_media_asset(asset)

            produced.append(
                ProducedSceneAsset(
                    scene_number=scene.scene_number,
                    image_path=scene_img_path,
                    duration_sec=scene.target_duration_sec,
                    headline=headline,
                    attribution_text=attribution,
                    is_public_domain=is_pd,
                    collected_source=collected_asset,
                )
            )

        logger.info(f"Visual production complete: {len(produced)} vertical 1080x1920 frames rendered in {scenes_dir.name}")
        return produced

    @staticmethod
    def _extract_search_keywords(topic: str, narration_chunk: str) -> str:
        topic_lower = topic.lower()
        if "mona lisa" in topic_lower or "heist" in topic_lower:
            return "Mona Lisa Louvre"
        elif "voynich" in topic_lower:
            return "Voynich manuscript"
        return f"{topic} history"

    @staticmethod
    def _formulate_scene_headline(scene_number: int, narration_chunk: str) -> str:
        words = narration_chunk.split()
        if scene_number == 1:
            return " ".join(words[:4]).upper() if words else "THE HOOK"
        elif scene_number == 2:
            return "CRITICAL EVIDENCE"
        elif scene_number == 3:
            return "THE TURNING POINT"
        else:
            return "THE CONCLUSION"

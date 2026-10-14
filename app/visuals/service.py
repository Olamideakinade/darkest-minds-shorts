"""Visual production service orchestrating archival discovery, scene synthesis, and licensing records."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import config
from app.database.db import Database, db
from app.database.models import MediaAsset, utc_now_iso
from app.editing.timeline import ScenePlan
from app.scripts.story_models import StoryScene, StoryScript
from app.utils.logger import logger
from app.visuals.asset_collector import AssetCollector, CollectedAsset, asset_collector
from app.visuals.dev_scene_synthesizer import DeveloperSceneSynthesizer, dev_scene_synthesizer
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
                # 1. Resolve curated historical asset or query public-domain discovery
                bg_path, attribution, license_info, is_pd = self._resolve_asset_for_plan(plan)

                # 2. Render 1080x1920 specialized scene frame
                self.synthesizer.compose_scene_from_plan(
                    plan=plan,
                    output_path=scene_img_path,
                    background_image_path=bg_path,
                )

            # 3. Formulate attribution metadata
            plan.source_attribution = attribution
            plan.is_public_domain = is_pd
            plan.rendered_image_path = scene_img_path

            # 4. Persist MediaAsset in database
            asset = MediaAsset(
                job_id=job_id,
                asset_type="image",
                file_path=str(scene_img_path),
                duration_sec=plan.duration_sec,
                license_info=license_info,
            )
            self.db.save_media_asset(asset)

        logger.info(f"Timeline visual production complete: {len(timeline)} frames rendered in {scenes_dir.name}")
        return timeline

    def _resolve_asset_for_plan(self, plan: ScenePlan) -> Tuple[Optional[Path], str, str, bool]:
        """Resolve background image path and exact licensing provenance for a scene plan."""
        curated_base = Path("data/curated_assets/mona_lisa_1911")
        query_lower = (plan.search_query or "").lower()
        purpose_lower = (plan.visual_purpose or "").lower()

        # Mona Lisa 1911 Heist curated archive mapping
        if curated_base.exists() and any(k in query_lower or k in purpose_lower for k in ("mona", "louvre", "peruggia", "heist", "beroud", "1911")):
            if plan.asset_type == "historical_map":
                return None, "Cartographie Historique Paris 1911 / Mhide Intelligence (CC0)", "Creative Commons Zero (CC0)", True
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

        # General case: Query asset collector
        if plan.search_query:
            collected = self.collector.search_public_domain_image(plan.search_query)
            if collected and collected.file_path.exists():
                return collected.file_path, collected.attribution_text, f"{collected.license_name} ({collected.source_url})", collected.is_public_domain

        # Editorial asset defaults
        if plan.asset_type == "historical_map":
            return None, "Original Historical Cartography: Mhide Story Intelligence (CC0)", "Creative Commons Zero (CC0)", True
        elif plan.asset_type == "newspaper_headline":
            return None, "Archival Press Reconstruction: Mhide Story Intelligence (CC0)", "Creative Commons Zero (CC0)", True
        elif plan.asset_type == "police_dossier":
            return None, "Historical Dossier Reconstruction: Mhide Story Intelligence (CC0)", "Creative Commons Zero (CC0)", True
        return None, "Original Editorial Graphics: Mhide Story Intelligence (CC0)", "Creative Commons Zero (CC0)", True

    def produce_visual_scenes(self, job_id: str, script: StoryScript) -> List[ProducedSceneAsset]:
        """Legacy helper for producing scenes directly from StoryScript."""
        scenes_dir = config.output_dir / "jobs" / job_id / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Producing visual scenes for job {job_id} ({len(script.scenes)} scenes)...")
        produced: List[ProducedSceneAsset] = []

        if job_id and not self.db.get_job(job_id):
            with self.db.connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO jobs (id, title, niche, state, current_stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (job_id, script.title or f"Job {job_id}", config.niche_default, "ASSEMBLING", "assembling", utc_now_iso(), utc_now_iso()),
                )

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

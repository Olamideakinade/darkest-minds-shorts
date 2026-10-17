"""Local editorial visual scene generator, vertical reframing, and motion graphics engine."""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from app.editing.timeline import ScenePlan
from app.utils.logger import logger


class SceneSynthesizer:
    """Creates 1080x1920 9:16 vertical video frames combining archival imagery, typography, and graphics."""

    WIDTH = 1080
    HEIGHT = 1920

    # Curated cinematic dark color palettes
    PALETTE_DARK_SLATE = (11, 15, 25)
    PALETTE_DEEP_NAVY = (15, 23, 42)
    PALETTE_GOLD_ACCENT = (217, 164, 65)
    PALETTE_WHITE = (248, 250, 252)
    PALETTE_MUTED_GRAY = (148, 163, 184)
    PALETTE_CRIMSON_ACCENT = (225, 29, 72)
    PALETTE_NEWSPAPER_CREAM = (243, 236, 224)
    PALETTE_INK_BLACK = (24, 24, 27)

    def __init__(self) -> None:
        self.font_large = self._load_font(34, bold=True)
        self.font_medium = self._load_font(26, bold=True)
        self.font_small = self._load_font(20, bold=False)
        self.font_badge = self._load_font(18, bold=True)
        self.font_masthead = self._load_serif_font(44, bold=True)
        self.font_stamp = self._load_font(26, bold=True)
        self.font_typewriter = self._load_typewriter_font(22, bold=True)
        self.font_typewriter_sm = self._load_typewriter_font(18, bold=False)

    def render_scene_image(
        self,
        plan: ScenePlan,
        background_image_path: Optional[Path] = None,
    ) -> Image.Image:
        """Render a specialized 1080x1920 editorial vertical frame as a PIL Image."""
        if background_image_path and background_image_path.exists():
            return self._render_archival_photo_scene(
                photo_path=background_image_path,
                headline=plan.kinetic_text or plan.visual_purpose.upper(),
                topic=plan.narration_segment[:30],
                scene_number=plan.scene_number,
                badge_text=f"ARCHIVAL PHOTOGRAPH • SCENE {plan.scene_number:02d}",
            )
        elif plan.asset_type == "historical_map":
            return self._render_historical_map_scene(plan)
        elif plan.asset_type == "newspaper_headline":
            return self._render_newspaper_scene(plan, background_image_path)
        elif plan.asset_type == "police_dossier":
            return self._render_police_dossier_scene(plan, background_image_path)
        else:
            return self._render_synthetic_editorial_scene(
                scene_number=plan.scene_number,
                topic=plan.narration_segment[:35],
                headline=plan.kinetic_text,
                narration_excerpt=plan.narration_segment,
                mood=plan.visual_purpose,
            )

    def compose_scene_from_plan(
        self,
        plan: ScenePlan,
        output_path: Path,
        background_image_path: Optional[Path] = None,
    ) -> Path:
        """Compose a specialized 1080x1920 editorial vertical frame for a timeline scene plan."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas = self.render_scene_image(plan, background_image_path)
        canvas.save(str(output_path), "PNG", quality=95)
        logger.debug(f"Composed {plan.asset_type} scene {plan.scene_number} -> {output_path.name}")
        return output_path

    def compose_scene(
        self,
        scene_number: int,
        topic: str,
        scene_headline: str,
        narration_excerpt: str,
        output_path: Path,
        background_image_path: Optional[Path] = None,
        mood: str = "cinematic_dramatic",
    ) -> Path:
        """Legacy helper for direct scene composition."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if background_image_path and background_image_path.exists():
            base_canvas = self._render_archival_photo_scene(
                background_image_path, scene_headline, topic, scene_number, f"DOCUMENTED ARCHIVE • ACT {scene_number}"
            )
        else:
            base_canvas = self._render_synthetic_editorial_scene(
                scene_number, topic, scene_headline, narration_excerpt, mood
            )

        base_canvas.save(str(output_path), "PNG", quality=95)
        return output_path

    # -------------------------------------------------------------------------
    # Specialized Scene Renderers
    # -------------------------------------------------------------------------

    def _render_archival_photo_scene(
        self,
        photo_path: Path,
        headline: str,
        topic: str,
        scene_number: int,
        badge_text: str = "ARCHIVAL RECORD",
    ) -> Image.Image:
        """Process collected archival photo: cinematic vertical framing, subtle grade, vignettes, and header badge."""
        with Image.open(photo_path) as raw_img:
            img = raw_img.convert("RGBA")

        # Netflix / BBC grade framing: full-bleed vertical cinematic composition
        canvas = self._fit_cinematic_vertical(img, self.WIDTH, self.HEIGHT)
        return canvas.convert("RGB")

    def _render_historical_map_scene(self, plan: ScenePlan) -> Image.Image:
        """Render high-tension cartographic investigation map with route vectors, tactical radar, and coordinates."""
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (15, 23, 42))
        draw = ImageDraw.Draw(canvas)

        is_mona_lisa = any(
            k in (plan.search_query or "").lower() or k in (plan.kinetic_text or "").lower() or k in (plan.narration_segment or "").lower()
            for k in ("mona lisa", "peruggia", "louvre", "salon carre", "visconti")
        )

        # Subtle cartographic coordinate grid
        grid_step = 80
        for gx in range(40, self.WIDTH, grid_step):
            draw.line([(gx, 120), (gx, self.HEIGHT - 120)], fill=(30, 41, 59, 140), width=1)
        for gy in range(120, self.HEIGHT - 120, grid_step):
            draw.line([(40, gy), (self.WIDTH - 40, gy)], fill=(30, 41, 59, 140), width=1)

        # Map Frame border
        draw.rectangle([40, 100, self.WIDTH - 40, self.HEIGHT - 100], outline=self.PALETTE_GOLD_ACCENT, width=3)
        draw.rectangle([48, 108, self.WIDTH - 48, self.HEIGHT - 108], outline=(71, 85, 105), width=1)

        if is_mona_lisa:
            # Stylized River Seine curve
            seine_pts = [
                (60, 1050), (220, 1000), (450, 930), (680, 880), (880, 850), (self.WIDTH - 60, 820)
            ]
            for idx in range(len(seine_pts) - 1):
                p1, p2 = seine_pts[idx], seine_pts[idx + 1]
                draw.line([p1, p2], fill=(44, 74, 110, 220), width=36)
                draw.line([p1, p2], fill=(70, 115, 170, 200), width=14)

            draw.text((320, 960), "LA SEINE // COURS D'EAU", font=self.font_small, fill=(100, 140, 180, 220))

            # Louvre Palace footprint polygon
            louvre_box = [280, 640, 800, 840]
            draw.rectangle(louvre_box, fill=(30, 58, 138, 120), outline=self.PALETTE_GOLD_ACCENT, width=3)
            draw.rectangle([440, 680, 640, 800], fill=(15, 23, 42), outline=(71, 85, 105), width=2)
            draw.text((310, 655), "PALAIS DU LOUVRE // SALON CARRÉ", font=self.font_badge, fill=self.PALETTE_GOLD_ACCENT)

            escape_path = [(380, 720), (410, 680), (480, 640), (520, 580), (580, 520), (740, 480)]
            for i in range(len(escape_path) - 1):
                pt1, pt2 = escape_path[i], escape_path[i + 1]
                draw.line([pt1, pt2], fill=self.PALETTE_CRIMSON_ACCENT, width=5)
                mid_x, mid_y = (pt1[0] + pt2[0]) // 2, (pt1[1] + pt2[1]) // 2
                draw.ellipse([mid_x - 6, mid_y - 6, mid_x + 6, mid_y + 6], fill=self.PALETTE_CRIMSON_ACCENT)

            draw.text((540, 540), "ITINÉRAIRE DE FUITE (ESCALIER VISCONTI)", font=self.font_small, fill=self.PALETTE_CRIMSON_ACCENT)
            pin_x, pin_y = 380, 720
            draw.ellipse([pin_x - 18, pin_y - 18, pin_x + 18, pin_y + 18], outline=self.PALETTE_GOLD_ACCENT, width=3)
            draw.ellipse([pin_x - 8, pin_y - 8, pin_x + 8, pin_y + 8], fill=self.PALETTE_CRIMSON_ACCENT)

            info_box = [80, 1150, self.WIDTH - 80, 1450]
            draw.rounded_rectangle(info_box, radius=16, fill=(11, 15, 25, 220), outline=self.PALETTE_GOLD_ACCENT, width=2)
            draw.text((110, 1175), "CARTOGRAPHIE JUDICIAIRE — PARIS 1ER ARRONDISSEMENT", font=self.font_small, fill=self.PALETTE_GOLD_ACCENT)
            draw.line([(110, 1210), (self.WIDTH - 110, 1210)], fill=(71, 85, 105), width=2)

            meta_rows = [
                ("LIEU DU CRIME:", "Musée du Louvre, Salon Carré (1er Arr.)"),
                ("POINT D'EXTRACTION:", "Escalier Visconti // Porte dérobée"),
                ("DESTINATION CACHE:", "Rue de l'Hôpital Saint-Louis (10e Arr.)"),
                ("COORDONNÉES:", "48°51'38\" N • 2°20'15\" E // ÉCHELLE 1:5000"),
            ]
            cy = 1230
            for lbl, val in meta_rows:
                draw.text((110, cy), lbl, font=self.font_small, fill=self.PALETTE_MUTED_GRAY)
                draw.text((370, cy), val, font=self.font_small, fill=self.PALETTE_WHITE)
                cy += 48

        else:
            # Authentic Archival Cartography for Darkest Minds 101 Historical Documentaries
            # 1. Elegant subtle cartographic graticule (fine latitude / longitude lines)
            for gy in range(400, 1100, 140):
                draw.line([(80, gy), (self.WIDTH - 80, gy)], fill=(45, 55, 72, 120), width=1)
                # Graticule latitude labels
                lat_deg = 58 - (gy - 400) // 140
                draw.text((88, gy + 4), f"{lat_deg:02d}°N", font=self.font_tiny if hasattr(self, "font_tiny") else self.font_small, fill=(100, 116, 139, 140))

            for gx in range(160, self.WIDTH - 80, 180):
                draw.line([(gx, 380), (gx, 1080)], fill=(45, 55, 72, 120), width=1)
                lon_deg = 7 + (gx - 160) // 180
                draw.text((gx + 4, 1060), f"{lon_deg:02d}°W", font=self.font_tiny if hasattr(self, "font_tiny") else self.font_small, fill=(100, 116, 139, 140))

            # 2. Period Maritime Survey Outer Border
            chart_box = [80, 380, self.WIDTH - 80, 1080]
            draw.rectangle(chart_box, outline=(148, 163, 184, 160), width=2)
            draw.rectangle([86, 386, self.WIDTH - 86, 1074], outline=self.PALETTE_GOLD_ACCENT, width=1)

            # 3. Restrained Historical Location Pin & Label
            pin_x, pin_y = self.WIDTH // 2, 700
            # Antique brass marker
            draw.ellipse([pin_x - 14, pin_y - 14, pin_x + 14, pin_y + 14], outline=self.PALETTE_GOLD_ACCENT, width=2)
            draw.ellipse([pin_x - 6, pin_y - 6, pin_x + 6, pin_y + 6], fill=self.PALETTE_GOLD_ACCENT)
            
            # Period survey location tag
            loc_label = plan.kinetic_text or (plan.search_query[:28] if plan.search_query else "DOCUMENTED SITE")
            draw.text((pin_x - 140, pin_y + 28), loc_label.upper(), font=self.font_small, fill=self.PALETTE_WHITE)
            draw.text((pin_x - 140, pin_y + 60), "HISTORICAL POSITION • SURVEYED", font=self.font_typewriter_sm, fill=self.PALETTE_GOLD_ACCENT)

            # 4. Archival Scale Bar (Antique Nautical Miles)
            scale_x, scale_y = 120, 1030
            draw.line([(scale_x, scale_y), (scale_x + 240, scale_y)], fill=self.PALETTE_GOLD_ACCENT, width=3)
            draw.line([(scale_x, scale_y - 6), (scale_x, scale_y + 6)], fill=self.PALETTE_GOLD_ACCENT, width=2)
            draw.line([(scale_x + 120, scale_y - 4), (scale_x + 120, scale_y + 4)], fill=self.PALETTE_GOLD_ACCENT, width=1)
            draw.line([(scale_x + 240, scale_y - 6), (scale_x + 240, scale_y + 6)], fill=self.PALETTE_GOLD_ACCENT, width=2)
            draw.text((scale_x, scale_y + 8), "0", font=self.font_small, fill=self.PALETTE_MUTED_GRAY)
            draw.text((scale_x + 105, scale_y + 8), "5 NM", font=self.font_small, fill=self.PALETTE_MUTED_GRAY)
            draw.text((scale_x + 215, scale_y + 8), "10 NM", font=self.font_small, fill=self.PALETTE_MUTED_GRAY)

            # Clean cartographic coordinates and record panel
            info_box = [80, 1180, self.WIDTH - 80, 1440]
            draw.rounded_rectangle(info_box, radius=16, fill=(15, 20, 30, 230), outline=self.PALETTE_GOLD_ACCENT, width=2)
            draw.text((110, 1205), "NAUTICAL RECONNAISSANCE // EXPEDITION TELEMETRY", font=self.font_small, fill=self.PALETTE_GOLD_ACCENT)
            draw.line([(110, 1240), (self.WIDTH - 110, 1240)], fill=(71, 85, 105), width=2)

            meta_rows = [
                ("CHART SECTOR:", "NORTH ATLANTIC // HEBRIDES BASIN"),
                ("SURVEY POSITION:", "58°17' N • 07°35' W // EILEAN MÒR"),
                ("ARCHIVAL DATUM:", "ADMIRALTY HYDROGRAPHIC SURVEY"),
            ]
            cy = 1260
            for lbl, val in meta_rows:
                draw.text((110, cy), lbl, font=self.font_small, fill=self.PALETTE_MUTED_GRAY)
                draw.text((360, cy), val, font=self.font_small, fill=self.PALETTE_WHITE)
                cy += 48

        # Compass Rose (Top Right)
        cx, cy = self.WIDTH - 130, 210
        draw.line([(cx, cy - 35), (cx, cy + 35)], fill=self.PALETTE_GOLD_ACCENT, width=2)
        draw.line([(cx - 35, cy), (cx + 35, cy)], fill=self.PALETTE_GOLD_ACCENT, width=2)
        draw.text((cx - 7, cy - 58), "N", font=self.font_badge, fill=self.PALETTE_GOLD_ACCENT)
        draw.text((cx - 5, cy + 40), "S", font=self.font_small, fill=self.PALETTE_MUTED_GRAY)

        # Safe zone bottom gradient
        self._apply_bottom_vignette(canvas)
        return canvas.convert("RGB")

    def _render_police_dossier_scene(
        self, plan: ScenePlan, background_image_path: Optional[Path] = None
    ) -> Image.Image:
        """Render high-tension vintage investigative case dossier with authentic typewriter records."""
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (18, 22, 34))
        draw = ImageDraw.Draw(canvas)

        is_mona_lisa = any(
            k in (plan.search_query or "").lower() or k in (plan.kinetic_text or "").lower() or k in (plan.narration_segment or "").lower()
            for k in ("mona lisa", "peruggia", "louvre", "salon carre", "visconti")
        )

        # Background archival grid & paper styling
        draw.rectangle([40, 100, self.WIDTH - 40, self.HEIGHT - 100], outline=(71, 85, 105), width=2)
        draw.rectangle([50, 110, self.WIDTH - 50, self.HEIGHT - 110], outline=self.PALETTE_GOLD_ACCENT, width=1)

        if is_mona_lisa:

            card_box = [70, 275, self.WIDTH - 70, 1470]
            draw.rounded_rectangle(card_box, radius=18, fill=(15, 23, 42, 230), outline=self.PALETTE_GOLD_ACCENT, width=2)
            draw.text((105, 305), "RÉPUBLIQUE FRANÇAISE — DIRECTION DE LA SÛRETÉ", font=self.font_typewriter, fill=self.PALETTE_GOLD_ACCENT)
            draw.line([(105, 340), (self.WIDTH - 105, 340)], fill=(71, 85, 105), width=2)

            photo_box = [105, 365, 485, 845]
            draw.rectangle(photo_box, fill=(11, 15, 25), outline=(148, 163, 184), width=3)

            mugshot_embedded = False
            target_mugshot = background_image_path or Path("data/curated_assets/mona_lisa_1911/03_vincenzo_peruggia_mugshot.jpg")
            if target_mugshot.exists():
                try:
                    with Image.open(target_mugshot) as m_img:
                        m_crop = ImageOps.exif_transpose(m_img).convert("RGBA")
                        m_scaled = self._crop_to_vertical(m_crop, 376, 476)
                        canvas.paste(m_scaled, (107, 367), m_scaled)
                        mugshot_embedded = True
                except Exception as e:
                    logger.debug(f"Failed to embed mugshot in dossier: {e}")

            if not mugshot_embedded:
                draw.text((150, 580), "[FICHE PHOTOGRAPHIQUE]", font=self.font_small, fill=self.PALETTE_MUTED_GRAY)

            draw.rectangle([105, 805, 485, 845], fill=(11, 15, 25, 230))
            draw.text((120, 815), "FICHE SIGNALÉTIQUE BERTILLON", font=self.font_typewriter_sm, fill=self.PALETTE_GOLD_ACCENT)

            mx = 525
            my = 370
            dossier_data = [
                ("DOSSIER N°:", "1911-821-VOL"),
                ("NOM:", "PERUGGIA"),
                ("PRÉNOM:", "Vincenzo"),
                ("NÉ LE:", "8 Octobre 1881"),
                ("LIEU:", "Dumenza (Italie)"),
                ("PROFESSION:", "Miroitier-Vitrier"),
                ("STATUT:", "Ancien ouvrier Louvre"),
                ("TAILLE:", "1m 60"),
                ("PARTICULARITÉ:", "Moustache brune"),
            ]
            for label, val in dossier_data:
                draw.text((mx, my), label, font=self.font_typewriter_sm, fill=self.PALETTE_MUTED_GRAY)
                draw.text((mx + 175, my), val, font=self.font_typewriter, fill=self.PALETTE_WHITE)
                my += 48

            notes_box = [105, 875, self.WIDTH - 105, 1435]
            draw.rounded_rectangle(notes_box, radius=12, fill=(11, 15, 25, 210), outline=(51, 65, 85), width=2)
            draw.text((130, 895), "RAPPORT D'ENQUÊTE & CONSTATATIONS MATÉRIELLES", font=self.font_typewriter, fill=self.PALETTE_GOLD_ACCENT)
            draw.line([(130, 930), (self.WIDTH - 130, 930)], fill=(51, 65, 85), width=1)

            report_lines = [
                "• Le tableau 'La Joconde' a été décroché le lundi 21 août 1911.",
                "• L'auteur portait la blouse blanche réglementaire des ouvriers.",
                "• Le cadre de chêne sculpté a été abandonné dans l'escalier Visconti.",
                "• L'œuvre est restée cachée 28 mois sous le plancher du suspect à Paris.",
                "• Récupération effectuée à Florence en décembre 1913.",
            ]
            ry = 955
            for r_line in report_lines:
                wrapped = self._wrap_text(r_line, max_chars=44)
                for w in wrapped:
                    draw.text((135, ry), w, font=self.font_typewriter_sm, fill=(226, 232, 240))
                    ry += 38
                ry += 10

            stamp_box = [self.WIDTH - 380, 1260, self.WIDTH - 130, 1370]
            draw.rectangle(stamp_box, outline=self.PALETTE_CRIMSON_ACCENT, width=4)
            draw.text((self.WIDTH - 365, 1280), "PIÈCE À CONVICTION", font=self.font_stamp, fill=self.PALETTE_CRIMSON_ACCENT)
            draw.text((self.WIDTH - 345, 1320), "PARIS • SÛRETÉ NATIONALE", font=self.font_typewriter_sm, fill=self.PALETTE_CRIMSON_ACCENT)
        else:
            # Atmospheric English Case Dossier for Darkest Minds 101 Unsolved Mysteries

            card_box = [70, 275, self.WIDTH - 70, 1470]
            draw.rounded_rectangle(card_box, radius=18, fill=(15, 23, 42, 235), outline=self.PALETTE_GOLD_ACCENT, width=2)
            draw.text((105, 305), "DARKEST MINDS INVESTIGATIVE ARCHIVES — INCIDENT DOSSIER", font=self.font_typewriter, fill=self.PALETTE_GOLD_ACCENT)
            draw.line([(105, 340), (self.WIDTH - 105, 340)], fill=(71, 85, 105), width=2)

            # Evidentiary Photo Box
            photo_box = [105, 365, 485, 845]
            draw.rectangle(photo_box, fill=(11, 15, 25), outline=(148, 163, 184), width=3)

            photo_embedded = False
            if background_image_path and background_image_path.exists():
                try:
                    with Image.open(background_image_path) as p_img:
                        p_crop = ImageOps.exif_transpose(p_img).convert("RGBA")
                        p_scaled = self._crop_to_vertical(p_crop, 376, 476)
                        canvas.paste(p_scaled, (107, 367), p_scaled)
                        photo_embedded = True
                except Exception as e:
                    logger.debug(f"Failed to embed archival photo in mystery dossier: {e}")

            if not photo_embedded:
                draw.text((130, 580), "[EVIDENTIARY ARCHIVE PHOTO]", font=self.font_small, fill=self.PALETTE_MUTED_GRAY)

            draw.rectangle([105, 805, 485, 845], fill=(11, 15, 25, 230))
            draw.text((120, 815), f"EXHIBIT #{plan.scene_number:02d} • FORENSIC RECORD", font=self.font_typewriter_sm, fill=self.PALETTE_GOLD_ACCENT)

            # Metadata Table
            mx = 525
            my = 370
            query_label = (plan.search_query or plan.visual_purpose).replace("_", " ").title()[:20]
            mystery_data = [
                ("CASE FILE:", f"DM-101-CASE-{plan.scene_number:02d}"),
                ("CATEGORY:", "UNRESOLVED ANOMALY"),
                ("INCIDENT:", query_label),
                ("STATUS:", "VANISHED / COLD CASE"),
                ("EVIDENCE:", "PHYSICAL RECORD VERIFIED"),
                ("TIMELINE:", "CORROBORATED LOG"),
                ("RESOLUTION:", "OFFICIALLY UNEXPLAINED"),
                ("ARCHIVE:", "DARKEST MINDS 101"),
            ]
            for label, val in mystery_data:
                draw.text((mx, my), label, font=self.font_typewriter_sm, fill=self.PALETTE_MUTED_GRAY)
                draw.text((mx + 175, my), val, font=self.font_typewriter, fill=self.PALETTE_WHITE)
                my += 52

            # Lower Section: Official Investigation Log
            notes_box = [105, 875, self.WIDTH - 105, 1435]
            draw.rounded_rectangle(notes_box, radius=12, fill=(11, 15, 25, 210), outline=(51, 65, 85), width=2)
            draw.text((130, 895), "OFFICIAL INVESTIGATION RECORD & WITNESS LOG", font=self.font_typewriter, fill=self.PALETTE_GOLD_ACCENT)
            draw.line([(130, 930), (self.WIDTH - 130, 930)], fill=(51, 65, 85), width=1)

            # Render narration excerpt as official evidence log
            narration_clean = plan.narration_segment.strip()
            evidence_points = [
                f"• {narration_clean}",
                "• Forensic inspection revealed no signs of struggle or external intervention.",
                "• All official inquiries ended without conclusive explanation or recovery.",
            ]
            ry = 955
            for ep in evidence_points:
                wrapped = self._wrap_text(ep, max_chars=44)
                for w in wrapped:
                    draw.text((135, ry), w, font=self.font_typewriter_sm, fill=(226, 232, 240))
                    ry += 38
                ry += 10

            # Red Official Investigation Stamp
            stamp_box = [self.WIDTH - 400, 1260, self.WIDTH - 110, 1370]
            draw.rectangle(stamp_box, outline=self.PALETTE_CRIMSON_ACCENT, width=4)
            draw.text((self.WIDTH - 385, 1280), "CLASSIFIED EVIDENCE", font=self.font_stamp, fill=self.PALETTE_CRIMSON_ACCENT)
            draw.text((self.WIDTH - 380, 1320), "DARKEST MINDS 101 • ARCHIVES", font=self.font_typewriter_sm, fill=self.PALETTE_CRIMSON_ACCENT)

        # Safe zone bottom gradient
        self._apply_bottom_vignette(canvas)
        self._draw_viewfinder_corners(draw)
        return canvas.convert("RGB")

    def _render_newspaper_scene(
        self, plan: ScenePlan, background_image_path: Optional[Path] = None
    ) -> Image.Image:
        """Render vintage newspaper clipping with authentic newsprint tone, columns, and exhibit stamp."""
        is_mona_lisa = any(
            k in (plan.search_query or "").lower() or k in (plan.kinetic_text or "").lower() or k in (plan.narration_segment or "").lower()
            for k in ("mona lisa", "peruggia", "louvre", "salon carre", "visconti")
        )

        # If an authentic archival press image is provided, use cinematic vertical composite
        if background_image_path and background_image_path.exists():
            with Image.open(background_image_path) as pimg:
                p_trans = ImageOps.exif_transpose(pimg).convert("RGBA")
            canvas = self._fit_cinematic_vertical(p_trans, self.WIDTH, self.HEIGHT)
            return canvas.convert("RGB")

        # Synthetic vintage broadsheet
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), self.PALETTE_NEWSPAPER_CREAM)
        draw = ImageDraw.Draw(canvas)

        # Aged newsprint double border
        draw.rectangle([35, 35, self.WIDTH - 35, self.HEIGHT - 35], outline=(180, 165, 140), width=4)
        draw.rectangle([45, 45, self.WIDTH - 45, self.HEIGHT - 45], outline=(70, 60, 50), width=2)

        if is_mona_lisa:
            # Masthead
            draw.text((140, 95), "LE PETIT JOURNAL", font=self.font_masthead, fill=self.PALETTE_INK_BLACK)
            draw.text((self.WIDTH - 420, 115), "ÉDITION DU MATIN • MARDI 22 AOÛT 1911", font=self.font_small, fill=(90, 80, 70))
            draw.line([(60, 165), (self.WIDTH - 60, 165)], fill=self.PALETTE_INK_BLACK, width=4)
            draw.line([(60, 173), (self.WIDTH - 60, 173)], fill=self.PALETTE_INK_BLACK, width=1)

            # Huge broadsheet headline
            main_headline = plan.kinetic_text or "LA JOCONDE A DISPARU DU MUSÉE DU LOUVRE"
            wrapped = self._wrap_text(main_headline, max_chars=28)
            hy = 200
            for line in wrapped[:3]:
                draw.text((70, hy), line, font=self.font_large, fill=self.PALETTE_INK_BLACK)
                hy += 55

            hy += 15
            draw.line([(70, hy), (self.WIDTH - 70, hy)], fill=(120, 100, 80), width=2)
            hy += 25

            cols = [
                (
                    "Le musée du Louvre a fermé ses portes après la découverte consternante. "
                    "Le cadre vide a été retrouvé dans l'escalier Visconti. L'administration judiciaire "
                    "interroge le personnel et les gardiens de nuit dans le plus grand secret.",
                    70, 480
                ),
                (
                    "M. Louis Béroud, peintre, s'étant présenté ce matin pour continuer son étude, "
                    "a constaté l'absence du chef-d'œuvre. Les gardiens crurent d'abord que le tableau "
                    "avait été transporté aux ateliers photographiques de la maison Braun.",
                    540, 480
                ),
            ]
            for col_text, col_x, col_w in cols:
                w_lines = self._wrap_text(col_text, max_chars=26)
                cy = hy
                for line in w_lines:
                    draw.text((col_x, cy), line, font=self.font_small, fill=(50, 45, 40))
                    cy += 34

            stamp_box = [self.WIDTH - 440, 1150, self.WIDTH - 80, 1260]
            draw.rectangle(stamp_box, outline=self.PALETTE_CRIMSON_ACCENT, width=4)
            draw.text((self.WIDTH - 420, 1175), "PIÈCE D'ARCHIVE", font=self.font_stamp, fill=self.PALETTE_CRIMSON_ACCENT)
            draw.text((self.WIDTH - 420, 1215), "RÉPUBLIQUE FRANÇAISE", font=self.font_small, fill=self.PALETTE_CRIMSON_ACCENT)
        else:
            # Broadheet for Darkest Minds 101 mysteries
            draw.text((120, 95), "THE INVESTIGATIVE CHRONICLE", font=self.font_masthead, fill=self.PALETTE_INK_BLACK)
            draw.text((self.WIDTH - 440, 115), "SPECIAL DISPATCH • UNRESOLVED CASES DESK", font=self.font_small, fill=(90, 80, 70))
            draw.line([(60, 165), (self.WIDTH - 60, 165)], fill=self.PALETTE_INK_BLACK, width=4)
            draw.line([(60, 173), (self.WIDTH - 60, 173)], fill=self.PALETTE_INK_BLACK, width=1)

            main_headline = plan.kinetic_text or "UNEXPLAINED DISAPPEARANCE BAFFLES INVESTIGATORS"
            wrapped = self._wrap_text(main_headline, max_chars=28)
            hy = 200
            for line in wrapped[:3]:
                draw.text((70, hy), line, font=self.font_large, fill=self.PALETTE_INK_BLACK)
                hy += 55

            hy += 15
            draw.line([(70, hy), (self.WIDTH - 70, hy)], fill=(120, 100, 80), width=2)
            hy += 25

            col1_body = (
                f"Authorities and search parties have reported baffling discoveries at the scene. "
                f"{plan.narration_segment} Initial inquiries have left investigators with more questions than answers."
            )
            col2_body = (
                "Forensic teams confirmed that personal effects remained undisturbed, yet no traces of the missing "
                "parties could be uncovered. Official reports have classified the occurrence as unexplained."
            )
            cols = [
                (col1_body, 70, 480),
                (col2_body, 540, 480),
            ]
            for col_text, col_x, col_w in cols:
                w_lines = self._wrap_text(col_text, max_chars=26)
                cy = hy
                for line in w_lines:
                    draw.text((col_x, cy), line, font=self.font_small, fill=(50, 45, 40))
                    cy += 34

            stamp_box = [self.WIDTH - 440, 1150, self.WIDTH - 80, 1260]
            draw.rectangle(stamp_box, outline=self.PALETTE_CRIMSON_ACCENT, width=4)
            draw.text((self.WIDTH - 420, 1175), "PRESS ARCHIVE", font=self.font_stamp, fill=self.PALETTE_CRIMSON_ACCENT)
            draw.text((self.WIDTH - 420, 1215), "DARKEST MINDS 101", font=self.font_small, fill=self.PALETTE_CRIMSON_ACCENT)

        self._apply_bottom_vignette(canvas)
        return canvas.convert("RGB")

    def _render_synthetic_editorial_scene(
        self, scene_number: int, topic: str, headline: str, narration_excerpt: str, mood: str
    ) -> Image.Image:
        """Generate high-contrast editorial scene using typography, cards, and archival graphic motifs."""
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), self.PALETTE_DARK_SLATE)
        draw = ImageDraw.Draw(canvas)

        center_x, center_y = self.WIDTH // 2, 700
        glow_radius = 450
        for r in range(glow_radius, 0, -10):
            alpha = int(45 * (1.0 - (r / glow_radius)))
            color = (217, 164, 65, alpha) if "revelation" in mood or "payoff" in mood else (30, 58, 138, alpha)
            draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], fill=color)


        # Full-height card extending to y=1480 (leaving zero awkward black empty void)
        card_box = [70, 240, self.WIDTH - 70, 1480]
        draw.rounded_rectangle(card_box, radius=20, fill=(15, 23, 42, 225), outline=(217, 164, 65, 140), width=3)

        draw.text((110, 280), "DECLASSIFIED / CASE ARCHIVE", font=self.font_small, fill=self.PALETTE_GOLD_ACCENT)
        draw.line([(110, 320), (self.WIDTH - 110, 320)], fill=(71, 85, 105, 150), width=2)

        display_headline = headline or topic
        wrapped_headline = self._wrap_text(display_headline, max_chars=28)
        cur_y = 360
        for line in wrapped_headline[:3]:
            draw.text((110, cur_y), line, font=self.font_large, fill=self.PALETTE_WHITE)
            cur_y += 60

        cur_y += 20
        draw.line([(110, cur_y), (self.WIDTH - 110, cur_y)], fill=(51, 65, 85), width=2)
        cur_y += 35

        meta_items = [
            ("STATUS:", "OFFICIAL HISTORICAL INVESTIGATION"),
            ("EVIDENCE:", f"ARCHIVAL RECORD #{scene_number:02d}"),
            ("SUBJECT:", topic[:32]),
            ("LOCATION:", "EVIDENTIARY ARCHIVE // UNRESOLVED LOCUS"),
        ]
        for lbl, val in meta_items:
            draw.text((110, cur_y), lbl, font=self.font_small, fill=self.PALETTE_MUTED_GRAY)
            draw.text((320, cur_y), val, font=self.font_medium, fill=self.PALETTE_WHITE)
            cur_y += 58

        cur_y += 30
        draw.rounded_rectangle([110, cur_y, self.WIDTH - 110, cur_y + 240], radius=16, fill=(30, 41, 59, 180), outline=(51, 65, 85), width=2)
        quote_text = f"\"{narration_excerpt[:120]}...\"" if len(narration_excerpt) > 120 else f"\"{narration_excerpt}\""
        wrapped_quote = self._wrap_text(quote_text, max_chars=38)
        qy = cur_y + 30
        for q_line in wrapped_quote[:4]:
            draw.text((140, qy), q_line, font=self.font_small, fill=(226, 232, 240))
            qy += 44

        self._apply_bottom_vignette(canvas)
        return canvas.convert("RGB")

    # -------------------------------------------------------------------------
    # Visual Utilities & Contact Sheet
    # -------------------------------------------------------------------------

    @classmethod
    def _fit_cinematic_vertical(cls, img: Image.Image, target_w: int = 1080, target_h: int = 1920) -> Image.Image:
        """BBC / Netflix documentary-grade full-bleed vertical composition.
        
        1. Normalizes EXIF orientation to prevent rotated images.
        2. Fills the entire 1080x1920 vertical canvas seamlessly (0% black void, 0% floating boxes).
        3. Centers the visual sweet-spot (slightly upper-biased for facial and focal clarity).
        4. Applies subtle dark gradient overlays at top (for title safe zone) and bottom (for captions).
        """
        img = ImageOps.exif_transpose(img)
        img_w, img_h = img.size

        # High-res vertical coverage: scale to fully cover 1080x1920
        scale = max(target_w / img_w, target_h / img_h)
        nw = int(round(img_w * scale))
        nh = int(round(img_h * scale))
        resized = img.resize((nw, nh), Image.Resampling.LANCZOS).convert("RGBA")

        # Upper-center weighted crop (0.42 bias frames horizons, portraits, and focal objects in sweet spot)
        cx = max(0, min(nw - target_w, (nw - target_w) // 2))
        cy = max(0, min(nh - target_h, int((nh - target_h) * 0.42)))
        composite = resized.crop((cx, cy, cx + target_w, cy + target_h))

        # Apply rich cinematic vignette overlays
        overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        # Top gradient for title readability (0 to 300)
        for y in range(300):
            alpha = int(140 * (1.0 - (y / 300.0)))
            draw_ov.line([(0, y), (target_w, y)], fill=(8, 12, 20, alpha))
        # Bottom gradient for subtitle readability (1320 to 1920)
        for y in range(1320, target_h):
            progress = (y - 1320) / 600.0
            alpha = int(195 * progress)
            draw_ov.line([(0, y), (target_w, y)], fill=(8, 12, 20, alpha))

        return Image.alpha_composite(composite, overlay)

    def create_contact_sheet(self, frame_paths: List[Path], output_path: Path) -> Path:
        """Composite representative scene frames into a professional 3x3 editorial contact sheet."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        valid_frames = [p for p in frame_paths if p.exists()]
        if not valid_frames:
            raise ValueError("No valid frame paths provided to generate contact sheet.")

        cols = 3
        rows = math.ceil(len(valid_frames) / cols)
        thumb_w, thumb_h = 360, 640
        sheet_w = cols * thumb_w + (cols + 1) * 20
        sheet_h = rows * thumb_h + (rows + 1) * 20 + 80  # Top header

        sheet = Image.new("RGB", (sheet_w, sheet_h), (15, 23, 42))
        draw = ImageDraw.Draw(sheet)

        # Header Title
        draw.text((25, 25), "DARKEST MINDS 101 — PRODUCTION TIMELINE & SCENE AUDIT", font=self.font_medium, fill=self.PALETTE_GOLD_ACCENT)
        draw.line([(20, 70), (sheet_w - 20, 70)], fill=(51, 65, 85), width=2)

        for idx, fp in enumerate(valid_frames):
            r = idx // cols
            c = idx % cols
            x = 20 + c * (thumb_w + 20)
            y = 85 + r * (thumb_h + 20)

            try:
                with Image.open(fp) as f_img:
                    thumb = f_img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                    sheet.paste(thumb, (x, y))
                    # Border & Scene label
                    draw.rectangle([x, y, x + thumb_w, y + thumb_h], outline=self.PALETTE_GOLD_ACCENT, width=2)
                    draw.rectangle([x, y + thumb_h - 40, x + thumb_w, y + thumb_h], fill=(11, 15, 25, 220))
                    draw.text((x + 10, y + thumb_h - 32), f"SCENE #{idx + 1:02d}", font=self.font_small, fill=self.PALETTE_WHITE)
            except Exception as e:
                logger.warning(f"Error thumbnailing frame {fp}: {e}")

        sheet.save(str(output_path), "JPEG", quality=90)
        logger.info(f"Generated editorial contact sheet ({len(valid_frames)} frames) -> {output_path.name}")
        return output_path

    def _draw_header_badge(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        fill_color: Tuple[int, int, int, int] = (15, 23, 42, 230),
        outline_color: Tuple[int, int, int] = (217, 164, 65),
    ) -> None:
        """Draw top centered badge pill strictly above the visual zone."""
        box_w, box_h = max(380, len(text) * 14 + 60), 48
        bx1 = (self.WIDTH - box_w) // 2
        by1 = 110
        draw.rounded_rectangle([bx1, by1, bx1 + box_w, by1 + box_h], radius=14, fill=fill_color, outline=outline_color, width=2)
        draw.text((bx1 + 25, by1 + 12), text, font=self.font_badge, fill=outline_color)

    def _draw_headline_banner(self, draw: ImageDraw.ImageDraw, headline: str, y_pos: int = 185) -> None:
        """Draw compact kinetic headline banner strictly above the visual focal area."""
        wrapped = self._wrap_text(headline, max_chars=32)
        line_height = 42
        card_h = len(wrapped) * line_height + 20
        max_len = max(len(l) for l in wrapped) if wrapped else 10
        card_w = min(self.WIDTH - 120, max(380, max_len * 18 + 50))
        cx = (self.WIDTH - card_w) // 2
        draw.rounded_rectangle([cx, y_pos, cx + card_w, y_pos + card_h], radius=12, fill=(11, 15, 25, 220), outline=(217, 164, 65, 140), width=2)

        hy = y_pos + 10
        for line in wrapped:
            draw.text((cx + 20, hy), line, font=self.font_medium, fill=self.PALETTE_WHITE)
            hy += line_height

    def _apply_bottom_vignette(self, canvas: Image.Image) -> None:
        """Protective gradient overlay at bottom to ensure subtitle captions readability."""
        overlay = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for y in range(1450, self.HEIGHT):
            progress = (y - 1450) / (self.HEIGHT - 1450)
            draw.line([(0, y), (self.WIDTH, y)], fill=(11, 15, 25, int(220 * progress)))
        canvas.paste(overlay, (0, 0), overlay)

    def _draw_viewfinder_corners(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw subtle camera/archival viewfinder brackets in corners."""
        size = 35
        thick = 3
        color = (217, 164, 65, 160)
        # Top-left
        draw.line([(50, 70), (50 + size, 70)], fill=color, width=thick)
        draw.line([(50, 70), (50, 70 + size)], fill=color, width=thick)
        # Top-right
        draw.line([(self.WIDTH - 50, 70), (self.WIDTH - 50 - size, 70)], fill=color, width=thick)
        draw.line([(self.WIDTH - 50, 70), (self.WIDTH - 50, 70 + size)], fill=color, width=thick)
        # Bottom-left
        draw.line([(50, self.HEIGHT - 70), (50 + size, self.HEIGHT - 70)], fill=color, width=thick)
        draw.line([(50, self.HEIGHT - 70), (50, self.HEIGHT - 70 - size)], fill=color, width=thick)
        # Bottom-right
        draw.line([(self.WIDTH - 50, self.HEIGHT - 70), (self.WIDTH - 50 - size, self.HEIGHT - 70)], fill=color, width=thick)
        draw.line([(self.WIDTH - 50, self.HEIGHT - 70), (self.WIDTH - 50, self.HEIGHT - 70 - size)], fill=color, width=thick)

    @staticmethod
    def _crop_to_vertical(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Scale and center-crop image to specified dimensions."""
        img = ImageOps.exif_transpose(img)
        target_aspect = target_w / target_h
        img_aspect = img.width / img.height

        if img_aspect > target_aspect:
            new_h = target_h
            new_w = int(img.width * (target_h / img.height))
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            x_offset = (new_w - target_w) // 2
            return resized.crop((x_offset, 0, x_offset + target_w, target_h))
        else:
            new_w = target_w
            new_h = int(img.height * (target_w / img.width))
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            y_offset = (new_h - target_h) // 2
            return resized.crop((0, y_offset, target_w, y_offset + target_h))

    @staticmethod
    def _wrap_text(text: str, max_chars: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        cur_line = ""
        for w in words:
            if not cur_line:
                cur_line = w
            elif len(cur_line) + len(w) + 1 <= max_chars:
                cur_line += " " + w
            else:
                lines.append(cur_line)
                cur_line = w
        if cur_line:
            lines.append(cur_line)
        return lines

    @staticmethod
    def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Trebuchet MS.ttf",
        ]
        for p in font_paths:
            if Path(p).exists():
                try:
                    return ImageFont.truetype(p, size=size)
                except Exception:
                    pass
        return ImageFont.load_default()

    @staticmethod
    def _load_typewriter_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Courier New Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Courier New.ttf",
            "/System/Library/Fonts/Courier.dfont",
        ]
        for p in font_paths:
            if Path(p).exists():
                try:
                    return ImageFont.truetype(p, size=size)
                except Exception:
                    pass
        return SceneSynthesizer._load_font(size, bold)

    @staticmethod
    def _load_serif_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            "/System/Library/Fonts/Times.ttc",
        ]
        for p in font_paths:
            if Path(p).exists():
                try:
                    return ImageFont.truetype(p, size=size)
                except Exception:
                    pass
        return SceneSynthesizer._load_font(size, bold)


# Global scene synthesizer singleton
scene_synthesizer = SceneSynthesizer()

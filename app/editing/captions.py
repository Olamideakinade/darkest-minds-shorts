"""Subtitle synchronizer and high-retention vertical caption overlay generator."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.narration.tts_service import WordTimestamp
from app.utils.logger import logger


@dataclass
class CaptionCue:
    """Synchronized spoken phrase with timing and rendered overlay path."""
    index: int
    text: str
    start_sec: float
    end_sec: float
    overlay_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "start_sec": round(self.start_sec, 3),
            "end_sec": round(self.end_sec, 3),
            "overlay_path": str(self.overlay_path) if self.overlay_path else None,
        }


class CaptionGenerator:
    """Generates standard SRT sidecars and synchronized phrase cues for Shorts."""

    WIDTH = 1080
    HEIGHT = 1920
    # Safe zone Y position for YouTube Shorts (above bottom YouTube metadata and below visual center)
    CAPTION_Y = 1380

    def __init__(self) -> None:
        self.font = self._load_bold_font(38)

    def generate_captions(
        self,
        job_id: str,
        word_timestamps: List[WordTimestamp],
        output_dir: Path,
        words_per_cue: int = 4,
        render_cards: bool = True,
    ) -> Tuple[Path, List[CaptionCue]]:
        """Group word timestamps into natural phrases, generate SRT sidecar, and timing manifest."""
        captions_dir = output_dir / "captions"
        captions_dir.mkdir(parents=True, exist_ok=True)
        srt_path = output_dir / "captions.srt"

        cues = self._group_words_into_cues(word_timestamps, words_per_cue=words_per_cue)

        # 1. Write standard SRT sidecar file
        self._write_srt_file(cues, srt_path)

        # 2. Render PNG card overlays ONLY if explicitly requested (preserves disk I/O)
        if render_cards:
            for cue in cues:
                card_filename = f"caption_{cue.index:03d}.png"
                card_path = captions_dir / card_filename
                self._render_caption_card(cue.text, card_path)
                cue.overlay_path = card_path

        # 3. Save timing manifest
        manifest_path = captions_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in cues], f, indent=2)

        logger.info(f"Generated {len(cues)} synchronized caption cues and SRT sidecar: {srt_path.name}")
        return srt_path, cues

    def _group_words_into_cues(
        self, word_timestamps: List[WordTimestamp], words_per_cue: int = 4
    ) -> List[CaptionCue]:
        """Group words into high-impact spoken chunks (3-5 words) respecting natural pauses."""
        if not word_timestamps:
            return []

        cues: List[CaptionCue] = []
        current_words: List[str] = []
        cue_start = max(0.0, word_timestamps[0].start_sec)
        cue_index = 1
        last_end = 0.0

        for idx, wt in enumerate(word_timestamps):
            current_words.append(wt.word)
            # Break on punctuation or word count threshold
            is_end_of_sentence = wt.word.endswith((".", "!", "?"))
            is_comma_break = wt.word.endswith((",", ";", ":", "—")) and len(current_words) >= 3

            if len(current_words) >= words_per_cue or is_end_of_sentence or is_comma_break or idx == len(word_timestamps) - 1:
                cue_text = " ".join(current_words).strip()
                cue_end = max(cue_start + 0.1, wt.end_sec)
                # Ensure monotonic timing
                if cue_start < last_end:
                    cue_start = last_end

                cues.append(
                    CaptionCue(
                        index=cue_index,
                        text=cue_text,
                        start_sec=round(cue_start, 3),
                        end_sec=round(cue_end, 3),
                    )
                )
                last_end = cue_end
                cue_index += 1
                current_words = []
                if idx + 1 < len(word_timestamps):
                    cue_start = max(last_end, word_timestamps[idx + 1].start_sec)

        return cues

    def _render_caption_card(self, text: str, output_path: Path) -> None:
        """Render transparent 1080x1920 PNG with a high-contrast pill caption in the safe zone."""
        img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        clean_text = text.strip().upper()
        bbox = draw.textbbox((0, 0), clean_text, font=self.font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x = 40
        pad_y = 20
        pill_w = min(text_w + pad_x * 2, self.WIDTH - 120)
        pill_h = text_h + pad_y * 2
        pill_x = (self.WIDTH - pill_w) // 2
        pill_y = self.CAPTION_Y

        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
            radius=18,
            fill=(11, 15, 25, 225),
            outline=(217, 164, 65, 180),
            width=2,
        )

        tx = pill_x + (pill_w - text_w) // 2
        ty = pill_y + (pill_h - text_h) // 2 - 4

        draw.text((tx + 2, ty + 2), clean_text, font=self.font, fill=(0, 0, 0, 240))
        draw.text((tx, ty), clean_text, font=self.font, fill=(255, 255, 255, 255))

        img.save(str(output_path), "PNG")

    @staticmethod
    def _write_srt_file(cues: List[CaptionCue], srt_path: Path) -> None:
        """Write cues to standard SubRip (.srt) format."""
        with open(srt_path, "w", encoding="utf-8") as f:
            for cue in cues:
                start_str = CaptionGenerator._format_srt_timestamp(cue.start_sec)
                end_str = CaptionGenerator._format_srt_timestamp(cue.end_sec)
                f.write(f"{cue.index}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{cue.text}\n\n")

    @staticmethod
    def _format_srt_timestamp(seconds: float) -> str:
        """Format seconds to HH:MM:SS,mmm SRT timestamp."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000))
        if millis >= 1000:
            millis = 999
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _load_bold_font(size: int) -> ImageFont.FreeTypeFont:
        """Load native system bold font."""
        paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for p in paths:
            if Path(p).exists():
                try:
                    return ImageFont.truetype(p, size=size)
                except Exception:
                    pass
        return ImageFont.load_default()


# Global caption generator singleton
caption_generator = CaptionGenerator()

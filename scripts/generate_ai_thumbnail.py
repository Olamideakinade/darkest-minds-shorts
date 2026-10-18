#!/usr/bin/env python3
"""Universal AI YouTube Thumbnail Generator.

Features:
- 100% Free online AI diffusion via FLUX.1-schnell (Black Forest Labs) & Pollinations.ai fallback.
- No paid API keys or subscriptions required.
- Interactive terminal mode or single-command CLI.
- Supports Darkest Minds (Dark Mystery) & PrayerTV (Prophetic Altar) presets or custom scripts.
- Outputs crisp broadcast 1280x720 HD thumbnails.
"""

import argparse
import io
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "output" / "thumbnails"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# System Fonts
FONT_IMPACT = Path("/System/Library/Fonts/Supplemental/Impact.ttf")
FONT_ARIAL_BLACK = Path("/System/Library/Fonts/Supplemental/Arial Black.ttf")


def get_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    return ImageFont.load_default()


STYLE_PRESETS = {
    "dark_mystery": (
        "dark cinematic YouTube thumbnail, dramatic ominous fog, eerie mysterious silhouette, "
        "atmospheric volumetric rim lighting, deep shadows with crimson red and amber accents, "
        "high contrast, hyper-detailed, 8k resolution, Unreal Engine 5 render, trending on ArtStation"
    ),
    "fire_prophetic": (
        "cinematic YouTube thumbnail, dramatic golden cross on heavenly mountain, blazing holy fire altar "
        "with embers, radiant celestial sunbeams breaking through storm clouds, volumetric lighting, "
        "photorealistic, 8k resolution, Unreal Engine 5 render, hyper-detailed"
    ),
    "heavenly_glory": (
        "epic celestial dawn over holy mountain, radiant golden sunburst bursting through clouds, "
        "glowing transparent cross of pure golden light, heavenly peaceful atmosphere, divine favour "
        "and blessings, volumetric lighting, 8k resolution, cinematic masterpiece, photorealistic"
    ),
    "midnight_warfare": (
        "dramatic midnight deliverance prayer atmosphere, stormy nocturnal sky with spiritual lightning, "
        "glowing sacred altar of fire, golden sparks and embers, dark ethereal clouds with celestial rim light, "
        "supernatural victory, cinematic photorealistic, 8k resolution"
    ),
}


def generate_flux_image(prompt: str, width: int = 1280, height: int = 720) -> Image.Image:
    """Generate image using free online FLUX.1-schnell diffusion model."""
    print(f"\n[AI-Diffusion] Synthesizing prompt:\n  \"{prompt[:90]}...\"")
    
    # 1. Hugging Face Gradio FLUX.1-schnell
    try:
        print("[AI-Diffusion] Connecting to FLUX.1-schnell on Hugging Face...")
        from gradio_client import Client
        client = Client("black-forest-labs/FLUX.1-schnell")
        res, _ = client.predict(
            prompt=prompt,
            seed=0,
            randomize_seed=True,
            width=1024,
            height=576,
            num_inference_steps=4,
            api_name="/infer",
        )
        img = Image.open(res)
        print("[AI-Diffusion] ✓ FLUX.1-schnell image generated successfully!")
        return img.resize((width, height), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"[AI-Diffusion] Gradio client unavailable ({e}), trying Pollinations AI...")

    # 2. Pollinations FLUX / Turbo
    try:
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model=flux&nologo=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = resp.read()
            img = Image.open(io.BytesIO(data))
            print("[AI-Diffusion] ✓ Pollinations AI image generated successfully!")
            return img.resize((width, height), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"[AI-Diffusion] Pollinations fallback failed ({e}).")

    # Fallback solid cinematic background
    print("[AI-Diffusion] Warning: Network fallback to dark gradient canvas.")
    return Image.new("RGB", (width, height), (15, 15, 20))


def overlay_viral_text(
    base_img: Image.Image,
    hero_text: str,
    sub_text: str = "",
    badge_text: str = "",
) -> Image.Image:
    """Overlay big, bold YouTube typography with heavy drop shadows and contrast vignette."""
    width, height = base_img.size
    canvas_rgba = base_img.convert("RGBA")

    # Left-side dark vignette for clear text visibility
    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    grad_width = int(width * 0.65)
    for x in range(grad_width):
        factor = (1.0 - (x / grad_width)) ** 1.3
        alpha = int(165 * factor)
        vdraw.line([(x, 0), (x, height)], fill=(0, 0, 0, alpha))
    canvas_rgba = Image.alpha_composite(canvas_rgba, vignette)

    draw = ImageDraw.Draw(canvas_rgba)
    font_hero = get_font(FONT_IMPACT, 106)
    font_sub = get_font(FONT_IMPACT, 70)
    font_badge = get_font(FONT_IMPACT, 34)

    curr_x = 45
    curr_y = 50

    # Top Badge (Crimson Red)
    if badge_text:
        badge_clean = badge_text.strip().upper()
        bbox = draw.textbbox((0, 0), badge_clean, font=font_badge)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([(curr_x, curr_y), (curr_x + bw + 24, curr_y + bh + 14)], fill=(220, 20, 20, 240))
        draw.text((curr_x + 12, curr_y + 5), badge_clean, font=font_badge, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        curr_y += bh + 36
    else:
        curr_y += 30

    # Huge Hero Word (Yellow/Gold)
    if hero_text:
        hero_clean = hero_text.strip().upper()
        # Drop shadow
        draw.text((curr_x + 6, curr_y + 6), hero_clean, font=font_hero, fill=(0, 0, 0, 240))
        # Main text
        draw.text(
            (curr_x, curr_y),
            hero_clean,
            font=font_hero,
            fill=(255, 215, 0),
            stroke_width=6,
            stroke_fill=(0, 0, 0),
        )
        hbbox = draw.textbbox((0, 0), hero_clean, font=font_hero)
        curr_y += (hbbox[3] - hbbox[1]) + 16

    # Sub-Word (Crisp White)
    if sub_text:
        sub_clean = sub_text.strip().upper()
        draw.text((curr_x + 5, curr_y + 5), sub_clean, font=font_sub, fill=(0, 0, 0, 220))
        draw.text(
            (curr_x, curr_y),
            sub_clean,
            font=font_sub,
            fill=(255, 255, 255),
            stroke_width=5,
            stroke_fill=(0, 0, 0),
        )

    return canvas_rgba.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description="Universal AI YouTube Thumbnail Generator")
    parser.add_argument("topic", nargs="?", default="", help="Video topic or title")
    parser.add_argument("--hero", default="", help="Big bold hero text")
    parser.add_argument("--sub", default="", help="Sub-hook text")
    parser.add_argument("--badge", default="", help="Top badge text (e.g. 'DO NOT WATCH ALONE', '18TH OCTOBER 2026')")
    parser.add_argument("--style", default="fire_prophetic", choices=list(STYLE_PRESETS.keys()) + ["custom"], help="Visual style")
    parser.add_argument("--prompt", default="", help="Custom prompt for AI diffusion")
    parser.add_argument("--mode", default="composite", choices=["composite", "ai_only"], help="Thumbnail format")
    parser.add_argument("--open", action="store_true", help="Open generated thumbnail preview")

    args = parser.parse_args()

    topic = args.topic
    hero = args.hero
    sub = args.sub
    badge = args.badge
    style = args.style
    prompt = args.prompt
    mode = args.mode

    if not topic and not prompt:
        print("\n=========================================================")
        print("      AI YOUTUBE THUMBNAIL STUDIO (100% FREE ONLINE AI)   ")
        print("=========================================================\n")
        topic = input("Enter video topic or script title: ").strip() or "JESUS HAS DONE IT"
        hero = input(f"Big Bold Hero Word (default '{topic.split()[0]}'): ").strip() or topic.split()[0]
        sub = input("Sub-Word: ").strip() or "HAS DONE IT!"
        badge = input("Top Badge (optional): ").strip()

        print("\nChoose Atmosphere Preset:")
        print("  [1] Fiery Prophetic Altar (Golden Cross, Fire, Sunbeams)")
        print("  [2] Heavenly Celestial Glory (Dawn, Sunburst, Mountains)")
        print("  [3] Midnight Deliverance & Warfare (Storm, Lightning, Altar)")
        print("  [4] Dark Mystery & Eerie Fog (Darkest Minds style)")
        print("  [5] Custom Prompt (Type whatever you want)")
        choice = input("Select preset [1-5] (default 1): ").strip() or "1"
        smap = {"1": "fire_prophetic", "2": "heavenly_glory", "3": "midnight_warfare", "4": "dark_mystery", "5": "custom"}
        style = smap.get(choice, "fire_prophetic")
        if style == "custom":
            prompt = input("Enter custom AI image prompt: ").strip()

        print("\nChoose Mode:")
        print("  [1] Full YouTube Thumbnail (AI Backdrop + Bold Typography)")
        print("  [2] Pure Cinematic AI Artwork (No Text Overlay)")
        mchoice = input("Select mode [1-2] (default 1): ").strip() or "1"
        mode = "composite" if mchoice == "1" else "ai_only"

    # Assemble diffusion prompt
    if prompt:
        full_prompt = f"cinematic YouTube thumbnail, {prompt}, 8k resolution, volumetric lighting, photorealistic, Unreal Engine 5 render"
    else:
        preset = STYLE_PRESETS.get(style, STYLE_PRESETS["fire_prophetic"])
        clean_topic = re.sub(r"[#|\[\]]", " ", topic)
        clean_topic = " ".join(clean_topic.split()[:8])
        full_prompt = f"cinematic YouTube thumbnail depicting '{clean_topic}', {preset}"

    t0 = time.time()
    ai_img = generate_flux_image(full_prompt)

    # Color grading
    ai_img = ImageEnhance.Color(ai_img).enhance(1.15)
    ai_img = ImageEnhance.Contrast(ai_img).enhance(1.15)

    if mode == "composite":
        final_img = overlay_viral_text(ai_img, hero_text=hero, sub_text=sub, badge_text=badge)
    else:
        final_img = ai_img

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (hero if hero else "ai_thumb").lower()).strip("_")
    filename = f"ai_thumb_{slug}_{int(time.time())}.jpg"
    out_path = OUTPUT_DIR / filename
    final_img.save(out_path, format="JPEG", quality=95, optimize=True)

    print(f"\n[AI-Studio] ✓ Generated thumbnail in {time.time()-t0:.2f}s!")
    print(f"[AI-Studio] Saved to: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")

    if args.open:
        os.system(f"open '{out_path}'")


if __name__ == "__main__":
    main()

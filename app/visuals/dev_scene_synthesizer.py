"""Developer Scene Synthesizer for MhideDev content.

Renders broadcast-grade 1080x1920 vertical developer visuals:
- VS Code Dark Theme editor with realistic syntax highlighting and error indicators
- Authentic terminal / shell prompts with real compiler crashes and stack traces
- Split-screen comparison cards (Localhost vs Production, Junior vs Senior)
- Developer confession cards with Slack alert notification overlays
- Browser preview mockups with live HTTP error pages
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from app.editing.timeline import ScenePlan
from app.utils.logger import logger


class DeveloperSceneSynthesizer:
    """Creates pixel-perfect 1080x1920 vertical frames for programming and tech storytelling."""

    WIDTH = 1080
    HEIGHT = 1920

    # Color Tokens (One Dark Pro & Modern Dev Palette)
    BG_DARK = (15, 17, 23)
    EDITOR_BG = (24, 27, 36)
    TITLEBAR_BG = (32, 36, 48)
    GUTTER_BG = (28, 31, 42)
    TEXT_MAIN = (220, 225, 235)
    TEXT_MUTED = (98, 108, 128)
    
    # Syntax Colors
    SYNTAX_KEYWORD = (198, 120, 221)  # Purple
    SYNTAX_FUNC = (97, 175, 239)     # Cyan/Blue
    SYNTAX_STRING = (152, 195, 121)   # Green
    SYNTAX_TYPE = (229, 192, 123)     # Yellow
    SYNTAX_ERROR = (244, 63, 94)      # Bright Red
    SYNTAX_COMMENT = (92, 99, 112)    # Muted Gray

    # Alert & Status Colors
    ALERT_GREEN = (34, 197, 94)
    ALERT_RED = (239, 68, 68)
    ALERT_AMBER = (245, 158, 11)
    MAC_RED = (255, 95, 86)
    MAC_YELLOW = (255, 189, 46)
    MAC_GREEN = (39, 201, 63)

    def __init__(self) -> None:
        self.font_code = self._load_mono_font(28, bold=True)
        self.font_code_sm = self._load_mono_font(22, bold=False)
        self.font_code_lg = self._load_mono_font(34, bold=True)
        self.font_heading = self._load_sans_font(36, bold=True)
        self.font_sub = self._load_sans_font(24, bold=False)
        self.font_pill = self._load_mono_font(18, bold=True)
        self.font_banner = self._load_sans_font(44, bold=True)

    def _load_mono_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        paths = [
            "/System/Library/Fonts/Menlo.ttc",
            "/System/Library/Fonts/Monaco.ttf",
            "/System/Library/Fonts/Courier.ttc",
        ]
        for p in paths:
            if Path(p).exists():
                try:
                    return ImageFont.truetype(p, size=size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def _load_sans_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for p in paths:
            if Path(p).exists():
                try:
                    return ImageFont.truetype(p, size=size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def compose_scene(self, plan: ScenePlan, output_path: Path) -> Path:
        """Compose 1080x1920 developer frame based on plan asset type and purpose."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        asset_type = plan.asset_type.lower()
        purpose = plan.visual_purpose.lower()

        if asset_type in ("terminal_window", "terminal_crash") or "terminal" in purpose:
            img = self.render_terminal_scene(plan)
        elif asset_type in ("split_comparison", "split_screen") or "split" in purpose:
            img = self.render_split_comparison_scene(plan)
        elif asset_type in ("confession_card", "confession") or purpose == "hook":
            img = self.render_confession_card_scene(plan)
        elif asset_type in ("browser_preview", "500_error") or "browser" in purpose:
            img = self.render_browser_preview_scene(plan)
        else:
            # Default to VS Code editor
            img = self.render_code_editor_scene(plan)

        img.save(output_path, "JPEG", quality=95)
        return output_path

    def render_code_editor_scene(self, plan: ScenePlan) -> Image.Image:
        """Render realistic VS Code dark theme code editor frame."""
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), self.BG_DARK)
        draw = ImageDraw.Draw(img)

        # Draw Window Container
        w_x1, w_y1, w_x2, w_y2 = 40, 140, 1040, 1780
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y2], radius=18, fill=self.EDITOR_BG, outline=(50, 56, 74), width=2)

        # Title bar & Window Controls
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y1 + 65], radius=18, fill=self.TITLEBAR_BG)
        draw.rectangle([w_x1, w_y1 + 45, w_x2, w_y1 + 65], fill=self.TITLEBAR_BG)
        draw.ellipse([w_x1 + 25, w_y1 + 24, w_x1 + 41, w_y1 + 40], fill=self.MAC_RED)
        draw.ellipse([w_x1 + 52, w_y1 + 24, w_x1 + 68, w_y1 + 40], fill=self.MAC_YELLOW)
        draw.ellipse([w_x1 + 79, w_y1 + 24, w_x1 + 95, w_y1 + 40], fill=self.MAC_GREEN)

        # Active File Tab
        tab_x1, tab_x2 = w_x1 + 140, w_x1 + 420
        draw.rectangle([tab_x1, w_y1 + 15, tab_x2, w_y1 + 65], fill=self.EDITOR_BG)
        draw.text((tab_x1 + 25, w_y1 + 25), "prod_gateway.py  ●", fill=self.TEXT_MAIN, font=self.font_pill)

        # Editor Gutter
        gutter_w = 90
        draw.rectangle([w_x1, w_y1 + 65, w_x1 + gutter_w, w_y2], fill=self.GUTTER_BG)

        # Code Lines with Authentic Syntax Highlighting
        code_snippets = [
            ("import", self.SYNTAX_KEYWORD, " os, sys, requests"),
            ("from", self.SYNTAX_KEYWORD, " auth_service import TokenGateway"),
            ("", self.TEXT_MAIN, ""),
            ("def", self.SYNTAX_KEYWORD, " deploy_auth_patch():"),
            ("    # CRITICAL: Production token must be valid", self.SYNTAX_COMMENT, ""),
            ("    auth_key = os.getenv(", self.TEXT_MAIN, '"GATEWAY_SECRET")'),
            ("    if not auth_key:", self.SYNTAX_KEYWORD, ""),
            ('        raise FatalConfigError("TOKEN_MISSING")', self.SYNTAX_ERROR, ""),
            ("    ", self.TEXT_MAIN, ""),
            ("    client = TokenGateway(auth_key)", self.TEXT_MAIN, ""),
            ("    client.bind_all_users()", self.SYNTAX_FUNC, ""),
            ("    print(", self.TEXT_MAIN, '"Patch applied: 4,000 users active")'),
            ("    return True", self.SYNTAX_KEYWORD, ""),
        ]

        # Draw code lines
        start_y = w_y1 + 105
        line_height = 54
        for idx, (prefix, color, rest) in enumerate(code_snippets):
            y_pos = start_y + (idx * line_height)
            line_no = f"{idx + 38:>2}"

            # Highlight Line 45 (the fatal error line)
            if idx == 7:
                draw.rectangle([w_x1 + gutter_w, y_pos - 6, w_x2 - 10, y_pos + line_height - 12], fill=(60, 20, 30))
                draw.text((w_x1 + 25, y_pos), line_no, fill=self.SYNTAX_ERROR, font=self.font_code_sm)
                # Red Gutter Marker
                draw.rectangle([w_x1 + gutter_w - 4, y_pos - 6, w_x1 + gutter_w, y_pos + line_height - 12], fill=self.SYNTAX_ERROR)
            else:
                draw.text((w_x1 + 25, y_pos), line_no, fill=self.TEXT_MUTED, font=self.font_code_sm)

            draw.text((w_x1 + gutter_w + 30, y_pos), prefix, fill=color, font=self.font_code)
            prefix_w = draw.textlength(prefix, font=self.font_code) if prefix else 0
            if rest:
                draw.text((w_x1 + gutter_w + 30 + prefix_w + 8, y_pos), rest, fill=self.TEXT_MAIN, font=self.font_code)

        # Inline Error Hover Tooltip
        err_box_y = start_y + (7 * line_height) + 48
        draw.rounded_rectangle([w_x1 + 140, err_box_y, w_x2 - 80, err_box_y + 90], radius=8, fill=(45, 15, 22), outline=self.SYNTAX_ERROR, width=2)
        draw.text((w_x1 + 165, err_box_y + 16), "! FatalConfigError: GATEWAY_SECRET is undefined in production", fill=(255, 180, 190), font=self.font_code_sm)
        draw.text((w_x1 + 165, err_box_y + 48), "  Exception caught at auth_gateway.py:45 [4,000 active sessions dropped]", fill=(200, 100, 110), font=self.font_pill)

        # Top Brand Pill
        self._draw_brand_pill(draw, "VS CODE // DEBUGGING PRODUCTION")

        # Bottom Evidence Pill
        pill_text = plan.kinetic_text or "ONE-LINE HOTFIX"
        self._draw_evidence_pill(draw, pill_text, self.ALERT_RED if "error" in plan.visual_purpose else self.ALERT_AMBER)

        return img

    def render_terminal_scene(self, plan: ScenePlan) -> Image.Image:
        """Render authentic dark terminal crash / execution frame."""
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), (12, 14, 20))
        draw = ImageDraw.Draw(img)

        # Window Container
        w_x1, w_y1, w_x2, w_y2 = 40, 140, 1040, 1780
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y2], radius=16, fill=(18, 20, 28), outline=(45, 52, 70), width=2)

        # Title bar
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y1 + 65], radius=16, fill=(26, 30, 42))
        draw.rectangle([w_x1, w_y1 + 45, w_x2, w_y1 + 65], fill=(26, 30, 42))
        draw.ellipse([w_x1 + 25, w_y1 + 24, w_x1 + 41, w_y1 + 40], fill=self.MAC_RED)
        draw.ellipse([w_x1 + 52, w_y1 + 24, w_x1 + 68, w_y1 + 40], fill=self.MAC_YELLOW)
        draw.ellipse([w_x1 + 79, w_y1 + 24, w_x1 + 95, w_y1 + 40], fill=self.MAC_GREEN)
        draw.text((w_x1 + 380, w_y1 + 22), "zsh — mhide@prod-cluster: ~", fill=self.TEXT_MUTED, font=self.font_pill)

        # Terminal Output
        y = w_y1 + 100
        lines = [
            ("mhide@prod-cluster:~/api $ git status", self.ALERT_AMBER),
            ("On branch main. Your branch is up to date.", self.TEXT_MUTED),
            ("", self.TEXT_MAIN),
            ("mhide@prod-cluster:~/api $ ./deploy_prod.sh --force", self.TEXT_MAIN),
            ("[17:02:04] Deploying commit c8f921a -> production cluster...", self.TEXT_MUTED),
            ("[17:02:11] Syncing environment variables...", self.TEXT_MUTED),
            ("[17:02:14] ERROR: 500 INTERNAL SERVER ERROR", self.ALERT_RED),
            ("FATAL: Database connection pool exhausted (max 100 conns)", self.ALERT_RED),
            ("Traceback (most recent call last):", self.SYNTAX_ERROR),
            ('  File "server.py", line 142, in handle_request', self.TEXT_MUTED),
            ('    conn = pool.get_connection(timeout=3.0)', self.TEXT_MUTED),
            ('  File "db.py", line 88, in get_connection', self.TEXT_MUTED),
            ('TimeoutError: PoolTimeout: 4,000 queued requests timed out', self.SYNTAX_ERROR),
            ("", self.TEXT_MAIN),
            (">>> ALERTS FIRING: #incident-sev-1 (Slack)", self.ALERT_RED),
            (">>> LATENCY: 9,420ms | DROPPED REQUESTS: 99.8%", self.ALERT_RED),
        ]

        for text, color in lines:
            draw.text((w_x1 + 35, y), text, fill=color, font=self.font_code_sm)
            y += 42

        # Flashing Cursor Block
        draw.rectangle([w_x1 + 35, y + 10, w_x1 + 52, y + 36], fill=self.ALERT_AMBER)

        # Top Brand Pill
        self._draw_brand_pill(draw, "TERMINAL // 500 SERVER CRASH")

        # Bottom Evidence Pill
        pill_text = plan.kinetic_text or "LATENCY SPIKE"
        self._draw_evidence_pill(draw, pill_text, self.ALERT_RED)

        return img

    def render_split_comparison_scene(self, plan: ScenePlan) -> Image.Image:
        """Render dual vertical split-screen card comparison (Localhost vs Production)."""
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), self.BG_DARK)
        draw = ImageDraw.Draw(img)

        # Card 1: Localhost (Top)
        top_y1, top_y2 = 140, 920
        draw.rounded_rectangle([40, top_y1, 1040, top_y2], radius=16, fill=(18, 28, 22), outline=self.ALERT_GREEN, width=3)
        draw.rectangle([40, top_y1, 1040, top_y1 + 65], fill=(24, 42, 30))
        draw.text((65, top_y1 + 20), "LOCALHOST:3000 // 1 TEST USER", fill=self.ALERT_GREEN, font=self.font_pill)
        draw.text((780, top_y1 + 20), "STATUS: 200 OK", fill=self.ALERT_GREEN, font=self.font_pill)

        draw.text((70, top_y1 + 120), "✓ Compiled in 42ms", fill=(180, 240, 190), font=self.font_code)
        draw.text((70, top_y1 + 190), "✓ Database latency: 2ms", fill=(180, 240, 190), font=self.font_code)
        draw.text((70, top_y1 + 260), "✓ Memory usage: 48 MB", fill=(180, 240, 190), font=self.font_code)
        draw.text((70, top_y1 + 340), '"Works on my machine!" — Junior Dev', fill=self.TEXT_MAIN, font=self.font_sub)

        # Card 2: Production (Bottom)
        bot_y1, bot_y2 = 980, 1760
        draw.rounded_rectangle([40, bot_y1, 1040, bot_y2], radius=16, fill=(35, 16, 22), outline=self.ALERT_RED, width=3)
        draw.rectangle([40, bot_y1, 1040, bot_y1 + 65], fill=(55, 20, 28))
        draw.text((65, bot_y1 + 20), "PRODUCTION:443 // 4,000 ACTIVE USERS", fill=self.ALERT_RED, font=self.font_pill)
        draw.text((740, bot_y1 + 20), "STATUS: 504 TIMEOUT", fill=self.ALERT_RED, font=self.font_pill)

        draw.text((70, bot_y1 + 120), "✗ Connection pool exhausted (100/100)", fill=(255, 170, 180), font=self.font_code)
        draw.text((70, bot_y1 + 190), "✗ API latency: 9,420ms (P99 Spike)", fill=(255, 170, 180), font=self.font_code)
        draw.text((70, bot_y1 + 260), "✗ Error rate: 99.8% dropped requests", fill=(255, 170, 180), font=self.font_code)
        draw.text((70, bot_y1 + 340), '"Who touched the auth gateway?" — VP Eng', fill=self.ALERT_AMBER, font=self.font_sub)

        # Top Brand Pill
        self._draw_brand_pill(draw, "EXPECTATION VS REALITY")

        # Bottom Evidence Pill
        pill_text = plan.kinetic_text or "PRODUCTION COLLAPSE"
        self._draw_evidence_pill(draw, pill_text, self.ALERT_RED)

        return img

    def render_confession_card_scene(self, plan: ScenePlan) -> Image.Image:
        """Render high-retention developer confession statement with Slack alert card."""
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), (16, 18, 25))
        draw = ImageDraw.Draw(img)

        # Background subtle code grid pattern
        for y_g in range(120, 1800, 80):
            draw.line([(40, y_g), (1040, y_g)], fill=(24, 28, 38), width=1)

        # Main Confession Card
        card_x1, card_y1, card_x2, card_y2 = 50, 260, 1030, 960
        draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=20, fill=(24, 28, 40), outline=self.ALERT_AMBER, width=3)

        # Header Tag
        draw.rectangle([card_x1 + 30, card_y1 + 30, card_x1 + 320, card_y1 + 75], fill=(45, 35, 20))
        draw.text((card_x1 + 45, card_y1 + 42), "● INCIDENT RECORD // 17:02", fill=self.ALERT_AMBER, font=self.font_pill)

        # Confession Headline
        headline = "I DEPLOYED TO PRODUCTION AT 5:00 PM."
        draw.text((card_x1 + 45, card_y1 + 120), headline, fill=self.TEXT_MAIN, font=self.font_banner)

        # Subtext quote
        sub = "And my Slack notifications sounded like machine gunfire."
        draw.text((card_x1 + 45, card_y1 + 200), sub, fill=(180, 195, 220), font=self.font_heading)

        # Metrics box
        draw.rounded_rectangle([card_x1 + 45, card_y1 + 300, card_x2 - 45, card_y1 + 440], radius=12, fill=(18, 21, 30))
        draw.text((card_x1 + 70, card_y1 + 330), "SEVERITY: SEV-1 CRITICAL", fill=self.ALERT_RED, font=self.font_code_sm)
        draw.text((card_x1 + 70, card_y1 + 375), "BLAST RADIUS: 4,000 ACTIVE USERS", fill=self.TEXT_MUTED, font=self.font_code_sm)

        # Slack Notification Overlay Card (Bottom)
        s_x1, s_y1, s_x2, s_y2 = 50, 1040, 1030, 1640
        draw.rounded_rectangle([s_x1, s_y1, s_x2, s_y2], radius=18, fill=(28, 32, 46), outline=(60, 70, 95), width=2)
        
        # Slack header
        draw.rectangle([s_x1, s_y1, s_x2, s_y1 + 65], fill=(36, 42, 60))
        draw.text((s_x1 + 30, s_y1 + 22), "#general  |  Slack Incident Bridge", fill=self.TEXT_MAIN, font=self.font_pill)

        slack_messages = [
            ("DevOps Bot", "[17:02:18]", "🚨 500 Spike: auth-cluster unhealthy", self.ALERT_RED),
            ("VP Engineering", "[17:02:35]", "Is anyone looking at this? Users can't log in.", self.ALERT_AMBER),
            ("Junior Dev (Me)", "[17:02:49]", "Just reverting my one-line PR... sweating...", self.TEXT_MAIN),
            ("Senior Architect", "[17:03:02]", "Reverted. First time on a Friday?", self.ALERT_GREEN),
        ]

        sy = s_y1 + 100
        for sender, ts, msg, col in slack_messages:
            draw.text((s_x1 + 30, sy), sender, fill=col, font=self.font_code_sm)
            draw.text((s_x1 + 260, sy), ts, fill=self.TEXT_MUTED, font=self.font_pill)
            draw.text((s_x1 + 30, sy + 38), msg, fill=self.TEXT_MAIN, font=self.font_sub)
            sy += 110

        # Brand Pill
        self._draw_brand_pill(draw, "MHIDEDEV // DEVELOPER CONFESSION")

        # Bottom Evidence Pill
        pill_text = plan.kinetic_text or "FRIDAY 5 PM DEPLOY"
        self._draw_evidence_pill(draw, pill_text, self.ALERT_AMBER)

        return img

    def render_browser_preview_scene(self, plan: ScenePlan) -> Image.Image:
        """Render browser address bar with live 500 error page."""
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), (20, 22, 30))
        draw = ImageDraw.Draw(img)

        # Browser Window
        w_x1, w_y1, w_x2, w_y2 = 40, 140, 1040, 1780
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y2], radius=16, fill=(240, 243, 248), outline=(60, 68, 88), width=2)

        # Dark Browser Chrome
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y1 + 80], radius=16, fill=(35, 40, 54))
        draw.rectangle([w_x1, w_y1 + 50, w_x2, w_y1 + 80], fill=(35, 40, 54))
        draw.ellipse([w_x1 + 25, w_y1 + 30, w_x1 + 41, w_y1 + 46], fill=self.MAC_RED)
        draw.ellipse([w_x1 + 52, w_y1 + 30, w_x1 + 68, w_y1 + 46], fill=self.MAC_YELLOW)
        draw.ellipse([w_x1 + 79, w_y1 + 30, w_x1 + 95, w_y1 + 46], fill=self.MAC_GREEN)

        # Address bar
        draw.rounded_rectangle([w_x1 + 140, w_y1 + 20, w_x2 - 50, w_y1 + 62], radius=8, fill=(22, 25, 35))
        draw.text((w_x1 + 165, w_y1 + 28), "🔒 https://app.mhide.dev/dashboard", fill=(170, 185, 210), font=self.font_pill)

        # Browser Viewport 500 Error Screen
        draw.text((w_x1 + 200, w_y1 + 320), "500", fill=(220, 38, 38), font=self._load_sans_font(120, bold=True))
        draw.text((w_x1 + 140, w_y1 + 480), "Internal Server Error", fill=(30, 41, 59), font=self.font_banner)
        draw.text((w_x1 + 140, w_y1 + 560), "The server encountered a catastrophic configuration error.", fill=(100, 116, 139), font=self.font_sub)
        draw.text((w_x1 + 140, w_y1 + 605), "Ray ID: 89f410c8293b • Location: prod-us-east-1", fill=(148, 163, 184), font=self.font_code_sm)

        # Top Brand Pill
        self._draw_brand_pill(draw, "WEB APP // 500 SERVER ERROR")

        # Bottom Evidence Pill
        pill_text = plan.kinetic_text or "SERVER DOWN"
        self._draw_evidence_pill(draw, pill_text, self.ALERT_RED)

        return img

    def _draw_brand_pill(self, draw: ImageDraw.ImageDraw, text: str) -> None:
        """Render top branding pill in mobile-safe zone (y ~ 65px)."""
        pill_w = int(draw.textlength(text, font=self.font_pill)) + 40
        pill_x = (self.WIDTH - pill_w) // 2
        draw.rounded_rectangle([pill_x, 60, pill_x + pill_w, 105], radius=22, fill=(24, 28, 40), outline=self.ALERT_AMBER, width=2)
        draw.text((pill_x + 20, 72), text, fill=self.ALERT_AMBER, font=self.font_pill)

    def _draw_evidence_pill(self, draw: ImageDraw.ImageDraw, text: str, border_color: Tuple[int, int, int]) -> None:
        """Render bottom kinetic pill above mobile caption zone (y ~ 1380px)."""
        pill_w = int(draw.textlength(text, font=self.font_pill)) + 48
        pill_x = (self.WIDTH - pill_w) // 2
        draw.rounded_rectangle([pill_x, 1370, pill_x + pill_w, 1420], radius=25, fill=(16, 20, 28), outline=border_color, width=2)
        draw.text((pill_x + 24, 1385), text, fill=(255, 255, 255), font=self.font_pill)


# Singleton instance
dev_scene_synthesizer = DeveloperSceneSynthesizer()

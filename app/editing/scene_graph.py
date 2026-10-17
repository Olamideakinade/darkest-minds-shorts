"""Modular Scene Graph Architecture for MhideDev Vertical Video Production.

Provides layered compositing:
- AmbientBackgroundLayer (radial dark gradients, dot matrices, circuit grids)
- CodeWindowLayer (VS Code UI, syntax highlighting, dynamic typing, line highlight)
- TerminalWindowLayer (ZSH shell, progressive command execution & output stream)
- SplitComparisonLayer (Localhost vs Production cards with active telemetry)
- ConfessionCardLayer (Incident cards with live Slack message stack)
- KineticTypographyLayer (Punchy easing typography reveals in safe zones)
- CaptionLayer (Mobile-safe captions with active word highlighting)
- PostProcessingLayer (Cinematic vignette, subtle scanlines, chromatic pulse)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from app.editing.captions import CaptionCue
from app.editing.timeline import ScenePlan


class Easing:
    """Standard motion easing equations for kinetic typography and camera moves."""
    
    @staticmethod
    def ease_out_cubic(t: float) -> float:
        return 1.0 - math.pow(1.0 - max(0.0, min(1.0, t)), 3.0)

    @staticmethod
    def ease_in_out_quad(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 2.0 * t * t if t < 0.5 else 1.0 - math.pow(-2.0 * t + 2.0, 2.0) / 2.0

    @staticmethod
    def punch_in(t: float) -> float:
        """Slight overshoot for kinetic impact."""
        t = max(0.0, min(1.0, t))
        c4 = (2.0 * math.pi) / 3.0
        if t == 0.0:
            return 0.0
        if t == 1.0:
            return 1.0
        return math.pow(2.0, -10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0


class FontCatalog:
    """Cached font provider with robust local fallback."""

    _cache: Dict[Tuple[str, int, bool], ImageFont.FreeTypeFont] = {}

    @classmethod
    def get_font(cls, family: str = "mono", size: int = 24, bold: bool = False) -> ImageFont.FreeTypeFont:
        key = (family, size, bold)
        if key in cls._cache:
            return cls._cache[key]

        paths: List[str] = []
        if family == "mono":
            paths = [
                "/System/Library/Fonts/Menlo.ttc",
                "/System/Library/Fonts/Monaco.ttf",
                "/System/Library/Fonts/Courier.ttc",
            ]
        elif family == "sans":
            paths = [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        elif family == "headline":
            paths = [
                "/System/Library/Fonts/Supplemental/Futura.ttc",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]

        for p in paths:
            if Path(p).exists():
                try:
                    f = ImageFont.truetype(p, size=size)
                    cls._cache[key] = f
                    return f
                except Exception:
                    pass

        default_f = ImageFont.load_default()
        cls._cache[key] = default_f
        return default_f


class Layer:
    """Base interface for a composable scene graph layer."""
    
    def __init__(self, z_index: int = 0, opacity: float = 1.0) -> None:
        self.z_index = z_index
        self.opacity = opacity

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        raise NotImplementedError


class AmbientBackgroundLayer(Layer):
    """Dynamic dark ambient background with dark radial gradient and optional subtle grid."""

    def __init__(self, style_preset: str = "dark_ide", z_index: int = 0) -> None:
        super().__init__(z_index=z_index)
        self.style_preset = style_preset

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        w, h = canvas.size
        draw = ImageDraw.Draw(canvas)

        if self.style_preset == "kinetic":
            # High-energy deep purple to dark blue gradient
            base_bg = (14, 12, 28)
            draw.rectangle([0, 0, w, h], fill=base_bg)
            # Subtle moving grid lines
            grid_shift = int((t_global * 24.0) % 60.0)
            for gy in range(grid_shift, h, 60):
                alpha = int(18 + 8 * math.sin(t_global + gy * 0.01))
                draw.line([(0, gy), (w, gy)], fill=(45, 35, 75, alpha), width=1)
            for gx in range(0, w, 60):
                draw.line([(gx, 0), (gx, h)], fill=(45, 35, 75, 20), width=1)
        elif self.style_preset == "cinematic":
            # Deep midnight blue with subtle code watermarks
            base_bg = (10, 14, 22)
            draw.rectangle([0, 0, w, h], fill=base_bg)
            # Subtle ambient center glow
            center_x, center_y = w // 2, h // 2
            glow_radius = 450 + int(30 * math.sin(t_scene * 2.0))
            draw.ellipse(
                [center_x - glow_radius, center_y - glow_radius, center_x + glow_radius, center_y + glow_radius],
                fill=(18, 28, 48),
            )
        elif self.style_preset in ("master", "hybrid", "treatment_d"):
            # Master cut: deep charcoal with ambient blue center glow and animated tech grid
            base_bg = (12, 14, 20)
            draw.rectangle([0, 0, w, h], fill=base_bg)
            center_x, center_y = w // 2, h // 2
            glow_radius = 500 + int(25 * math.sin(t_scene * 2.5))
            draw.ellipse(
                [center_x - glow_radius, center_y - glow_radius, center_x + glow_radius, center_y + glow_radius],
                fill=(18, 24, 38),
            )
            grid_shift = int((t_global * 18.0) % 60.0)
            for gy in range(grid_shift, h, 60):
                alpha = int(14 + 6 * math.sin(t_global + gy * 0.01))
                draw.line([(0, gy), (w, gy)], fill=(32, 42, 65, alpha), width=1)
            for gx in range(0, w, 60):
                draw.line([(gx, 0), (gx, h)], fill=(32, 42, 65, 14), width=1)
        else:
            # Default One Dark Pro charcoal
            base_bg = (15, 17, 23)
            draw.rectangle([0, 0, w, h], fill=base_bg)
            # Subtle horizontal rule lines
            for gy in range(120, h - 200, 70):
                draw.line([(40, gy), (w - 40, gy)], fill=(24, 28, 38), width=1)


class CodeWindowLayer(Layer):
    """VS Code IDE with realistic syntax highlighting, line numbers, and dynamic typing/highlighting."""

    def __init__(self, plan: ScenePlan, z_index: int = 10) -> None:
        super().__init__(z_index=z_index)
        self.plan = plan

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        draw = ImageDraw.Draw(canvas)
        w, h = canvas.size

        # Window Coordinates (Safe Zone: 260px to 1480px)
        w_x1, w_y1 = 45, 260
        w_x2, w_y2 = w - 45, 1480

        # Push-in camera movement
        p_norm = max(0.0, min(1.0, t_scene / max(0.1, duration)))
        ease_p = Easing.ease_out_cubic(p_norm)
        cam_zoom = 1.0 + 0.04 * ease_p
        
        # Window Shadow & Background
        draw.rounded_rectangle([w_x1 + 6, w_y1 + 8, w_x2 + 6, w_y2 + 8], radius=16, fill=(8, 10, 14, 180))
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y2], radius=16, fill=(24, 27, 36), outline=(50, 56, 74), width=2)

        # Title bar & Window Controls (macOS traffic lights)
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y1 + 60], radius=16, fill=(32, 36, 48))
        draw.rectangle([w_x1, w_y1 + 40, w_x2, w_y1 + 60], fill=(32, 36, 48))
        draw.ellipse([w_x1 + 24, w_y1 + 22, w_x1 + 38, w_y1 + 36], fill=(255, 95, 86))
        draw.ellipse([w_x1 + 48, w_y1 + 22, w_x1 + 62, w_y1 + 36], fill=(255, 189, 46))
        draw.ellipse([w_x1 + 72, w_y1 + 22, w_x1 + 86, w_y1 + 36], fill=(39, 201, 63))

        # Active File Tab
        tab_font = FontCatalog.get_font("mono", 20, bold=True)
        draw.rectangle([w_x1 + 120, w_y1 + 12, w_x1 + 380, w_y1 + 60], fill=(24, 27, 36))
        draw.text((w_x1 + 145, w_y1 + 22), "prod_gateway.py  ●", fill=(220, 225, 235), font=tab_font)

        # Gutter (Line Numbers)
        gutter_w = 85
        draw.rectangle([w_x1, w_y1 + 60, w_x1 + gutter_w, w_y2], fill=(28, 31, 42))

        # Authentic Python Code Lines
        code_lines = [
            ("import", (198, 120, 221), " os, sys, requests"),
            ("from", (198, 120, 221), " auth_service import TokenGateway"),
            ("", (220, 225, 235), ""),
            ("def", (198, 120, 221), " deploy_auth_patch():"),
            ("    # CRITICAL: Production token must be valid", (92, 99, 112), ""),
            ("    auth_key = os.getenv(", (220, 225, 235), '"GATEWAY_SECRET")'),
            ("    if not auth_key:", (198, 120, 221), ""),
            ('        raise FatalConfigError("TOKEN_MISSING")', (244, 63, 94), ""),
            ("    ", (220, 225, 235), ""),
            ("    client = TokenGateway(auth_key)", (220, 225, 235), ""),
            ("    client.bind_all_users()", (97, 175, 239), ""),
            ("    print(", (220, 225, 235), '"Patch applied: 4,000 users active")'),
            ("    return True", (198, 120, 221), ""),
        ]

        # Progressive typing / reveal
        total_lines = len(code_lines)
        lines_to_show = min(total_lines, int(4 + (total_lines - 4) * Easing.ease_out_cubic(min(1.0, t_scene / 1.5))))

        code_font = FontCatalog.get_font("mono", 28, bold=True)
        gutter_font = FontCatalog.get_font("mono", 22, bold=False)
        start_y = w_y1 + 95
        line_height = 54

        for idx in range(lines_to_show):
            prefix, col, rest = code_lines[idx]
            y_pos = start_y + (idx * line_height)
            line_num_str = f"{idx + 38:>2}"

            # Highlighting Line 45 (the fatal bug)
            is_fatal_line = (idx == 7)
            if is_fatal_line:
                # Pulse highlight if past 1.0s
                pulse = 0.5 + 0.5 * math.sin(t_scene * 6.0)
                pulse_color = (int(50 + 25 * pulse), 18, 26)
                draw.rectangle([w_x1 + gutter_w, y_pos - 6, w_x2 - 10, y_pos + line_height - 10], fill=pulse_color)
                draw.rectangle([w_x1 + gutter_w - 5, y_pos - 6, w_x1 + gutter_w, y_pos + line_height - 10], fill=(244, 63, 94))
                draw.text((w_x1 + 22, y_pos), line_num_str, fill=(244, 63, 94), font=gutter_font)
            else:
                draw.text((w_x1 + 22, y_pos), line_num_str, fill=(98, 108, 128), font=gutter_font)

            draw.text((w_x1 + gutter_w + 25, y_pos), prefix, fill=col, font=code_font)
            prefix_w = draw.textlength(prefix, font=code_font) if prefix else 0
            if rest:
                draw.text((w_x1 + gutter_w + 25 + prefix_w + 8, y_pos), rest, fill=(220, 225, 235), font=code_font)

        # Flashing typing cursor on latest line
        if lines_to_show < total_lines and int(t_scene * 3.0) % 2 == 0:
            cur_y = start_y + (lines_to_show * line_height)
            draw.rectangle([w_x1 + gutter_w + 25, cur_y + 4, w_x1 + gutter_w + 40, cur_y + 36], fill=(245, 158, 11))

        # Inline Error Tooltip (appears at t >= 0.8s)
        if t_scene >= 0.8:
            err_box_y = start_y + (7 * line_height) + 48
            tooltip_alpha = min(1.0, (t_scene - 0.8) / 0.3)
            draw.rounded_rectangle(
                [w_x1 + 120, err_box_y, w_x2 - 60, err_box_y + 90],
                radius=8,
                fill=(45, 16, 24),
                outline=(244, 63, 94),
                width=2,
            )
            draw.text((w_x1 + 145, err_box_y + 16), "! FatalConfigError: GATEWAY_SECRET is undefined in production", fill=(255, 190, 200), font=gutter_font)
            draw.text((w_x1 + 145, err_box_y + 48), "  Exception caught at auth_gateway.py:45 [4,000 active sessions dropped]", fill=(210, 110, 120), font=FontCatalog.get_font("mono", 18, bold=True))


class TerminalWindowLayer(Layer):
    """Authentic terminal window with progressive line streaming, command typing, and error highlights."""

    def __init__(self, plan: ScenePlan, z_index: int = 10) -> None:
        super().__init__(z_index=z_index)
        self.plan = plan

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        draw = ImageDraw.Draw(canvas)
        w, h = canvas.size

        w_x1, w_y1 = 45, 260
        w_x2, w_y2 = w - 45, 1480

        # Window background & drop shadow
        draw.rounded_rectangle([w_x1 + 6, w_y1 + 8, w_x2 + 6, w_y2 + 8], radius=16, fill=(6, 8, 12, 180))
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y2], radius=16, fill=(18, 20, 28), outline=(48, 55, 75), width=2)

        # Title bar
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y1 + 60], radius=16, fill=(26, 30, 42))
        draw.rectangle([w_x1, w_y1 + 40, w_x2, w_y1 + 60], fill=(26, 30, 42))
        draw.ellipse([w_x1 + 24, w_y1 + 22, w_x1 + 38, w_y1 + 36], fill=(255, 95, 86))
        draw.ellipse([w_x1 + 48, w_y1 + 22, w_x1 + 62, w_y1 + 36], fill=(255, 189, 46))
        draw.ellipse([w_x1 + 72, w_y1 + 22, w_x1 + 86, w_y1 + 36], fill=(39, 201, 63))

        title_font = FontCatalog.get_font("mono", 20, bold=False)
        draw.text((w_x1 + 360, w_y1 + 20), "zsh — mhide@prod-cluster: ~", fill=(120, 130, 150), font=title_font)

        # Progressive command line stream
        terminal_lines = [
            ("mhide@prod-cluster:~/api $ git status", (245, 158, 11), 0.0),
            ("On branch main. Your branch is up to date.", (100, 110, 130), 0.3),
            ("", (220, 225, 235), 0.5),
            ("mhide@prod-cluster:~/api $ ./deploy_prod.sh --force", (220, 225, 235), 0.6),
            ("[17:02:04] Deploying commit c8f921a -> production cluster...", (100, 110, 130), 0.9),
            ("[17:02:11] Syncing environment variables...", (100, 110, 130), 1.2),
            ("[17:02:14] ERROR: 500 INTERNAL SERVER ERROR", (239, 68, 68), 1.5),
            ("FATAL: Database connection pool exhausted (max 100 conns)", (239, 68, 68), 1.8),
            ("Traceback (most recent call last):", (244, 63, 94), 2.1),
            ('  File "server.py", line 142, in handle_request', (120, 130, 150), 2.3),
            ('    conn = pool.get_connection(timeout=3.0)', (120, 130, 150), 2.5),
            ('  File "db.py", line 88, in get_connection', (120, 130, 150), 2.7),
            ('TimeoutError: PoolTimeout: 4,000 queued requests timed out', (244, 63, 94), 2.9),
            ("", (220, 225, 235), 3.0),
            (">>> ALERTS FIRING: #incident-sev-1 (Slack)", (239, 68, 68), 3.1),
            (">>> LATENCY: 9,420ms | DROPPED REQUESTS: 99.8%", (239, 68, 68), 3.3),
        ]

        term_font = FontCatalog.get_font("mono", 24, bold=False)
        y = w_y1 + 85
        last_y = y
        for text, col, reveal_time in terminal_lines:
            if t_scene >= reveal_time:
                draw.text((w_x1 + 35, y), text, fill=col, font=term_font)
                last_y = y
                y += 42

        # Flashing terminal block cursor
        if int(t_scene * 3.0) % 2 == 0 and y < w_y2 - 60:
            draw.rectangle([w_x1 + 35, y + 6, w_x1 + 52, y + 32], fill=(245, 158, 11))


class SplitComparisonLayer(Layer):
    """Localhost vs Production comparative split screen with live telemetry status cards."""

    def __init__(self, plan: ScenePlan, z_index: int = 10) -> None:
        super().__init__(z_index=z_index)
        self.plan = plan

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        draw = ImageDraw.Draw(canvas)
        w, h = canvas.size

        # Card 1: Localhost (Top: 260px to 840px)
        top_y1, top_y2 = 260, 840
        draw.rounded_rectangle([45, top_y1, w - 45, top_y2], radius=16, fill=(16, 26, 20), outline=(34, 197, 94), width=2)
        draw.rectangle([45, top_y1, w - 45, top_y1 + 55], fill=(22, 38, 28))
        
        pill_font = FontCatalog.get_font("mono", 18, bold=True)
        code_font = FontCatalog.get_font("mono", 28, bold=True)
        sub_font = FontCatalog.get_font("sans", 24, bold=False)

        draw.text((70, top_y1 + 18), "LOCALHOST:3000 // 1 TEST USER", fill=(34, 197, 94), font=pill_font)
        draw.text((w - 240, top_y1 + 18), "STATUS: 200 OK", fill=(34, 197, 94), font=pill_font)

        draw.text((75, top_y1 + 100), "✓ Compiled in 42ms", fill=(180, 240, 190), font=code_font)
        draw.text((75, top_y1 + 170), "✓ Database latency: 2ms", fill=(180, 240, 190), font=code_font)
        draw.text((75, top_y1 + 240), "✓ Memory usage: 48 MB", fill=(180, 240, 190), font=code_font)
        draw.text((75, top_y1 + 330), '"Works on my machine!" — Junior Dev', fill=(220, 225, 235), font=sub_font)

        # Card 2: Production (Bottom: 880px to 1480px)
        bot_y1, bot_y2 = 880, 1480
        # Pulse border on failure
        pulse = 0.5 + 0.5 * math.sin(t_scene * 5.0)
        border_col = (int(200 + 45 * pulse), 40, 50)
        draw.rounded_rectangle([45, bot_y1, w - 45, bot_y2], radius=16, fill=(32, 14, 20), outline=border_col, width=3)
        draw.rectangle([45, bot_y1, w - 45, bot_y1 + 55], fill=(48, 18, 26))

        draw.text((70, bot_y1 + 18), "PRODUCTION:443 // 4,000 ACTIVE USERS", fill=(239, 68, 68), font=pill_font)
        draw.text((w - 280, bot_y1 + 18), "STATUS: 504 TIMEOUT", fill=(239, 68, 68), font=pill_font)

        draw.text((75, bot_y1 + 100), "✗ Connection pool exhausted (100/100)", fill=(255, 170, 180), font=code_font)
        draw.text((75, bot_y1 + 170), "✗ API latency: 9,420ms (P99 Spike)", fill=(255, 170, 180), font=code_font)
        draw.text((75, bot_y1 + 240), "✗ Error rate: 99.8% dropped requests", fill=(255, 170, 180), font=code_font)
        draw.text((75, bot_y1 + 330), '"Who touched the auth gateway?" — VP Eng', fill=(245, 158, 11), font=sub_font)


class ConfessionCardLayer(Layer):
    """Incident report and live Slack incident bridge chat conversation."""

    def __init__(self, plan: ScenePlan, z_index: int = 10) -> None:
        super().__init__(z_index=z_index)
        self.plan = plan

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        draw = ImageDraw.Draw(canvas)
        w, h = canvas.size

        card_x1, card_y1 = 45, 260
        card_x2, card_y2 = w - 45, 840

        pill_font = FontCatalog.get_font("mono", 18, bold=True)
        banner_font = FontCatalog.get_font("headline", 44, bold=True)
        heading_font = FontCatalog.get_font("sans", 30, bold=True)
        sub_font = FontCatalog.get_font("sans", 22, bold=False)

        # Main Incident Card
        draw.rounded_rectangle([card_x1 + 6, card_y1 + 8, card_x2 + 6, card_y2 + 8], radius=16, fill=(8, 10, 16, 180))
        draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=16, fill=(24, 28, 40), outline=(245, 158, 11), width=2)

        # Header Pill Tag
        draw.rounded_rectangle([card_x1 + 28, card_y1 + 24, card_x1 + 320, card_y1 + 65], radius=8, fill=(45, 35, 20))
        draw.text((card_x1 + 42, card_y1 + 33), "● INCIDENT RECORD // 17:02", fill=(245, 158, 11), font=pill_font)

        # Confession Headline
        draw.text((card_x1 + 35, card_y1 + 100), "I DEPLOYED TO PROD AT 5 PM.", fill=(255, 255, 255), font=banner_font)
        draw.text((card_x1 + 35, card_y1 + 175), "And my Slack exploded like machine gunfire.", fill=(185, 200, 225), font=heading_font)

        # Metrics Box
        m_y1, m_y2 = card_y1 + 270, card_y1 + 390
        draw.rounded_rectangle([card_x1 + 35, m_y1, card_x2 - 35, m_y2], radius=10, fill=(16, 19, 28))
        draw.text((card_x1 + 60, m_y1 + 25), "SEVERITY: SEV-1 CRITICAL", fill=(239, 68, 68), font=pill_font)
        draw.text((card_x1 + 60, m_y1 + 65), "BLAST RADIUS: 4,000 ACTIVE USERS AFFECTED", fill=(120, 130, 150), font=pill_font)

        # Slack Incident Bridge Card (Bottom: 880px to 1480px)
        s_x1, s_y1 = 45, 880
        s_x2, s_y2 = w - 45, 1480
        draw.rounded_rectangle([s_x1 + 6, s_y1 + 8, s_x2 + 6, s_y2 + 8], radius=16, fill=(8, 10, 16, 180))
        draw.rounded_rectangle([s_x1, s_y1, s_x2, s_y2], radius=16, fill=(28, 32, 46), outline=(58, 68, 92), width=2)

        # Slack Titlebar
        draw.rounded_rectangle([s_x1, s_y1, s_x2, s_y1 + 55], radius=16, fill=(36, 42, 60))
        draw.rectangle([s_x1, s_y1 + 35, s_x2, s_y1 + 55], fill=(36, 42, 60))
        draw.text((s_x1 + 30, s_y1 + 18), "#incident-bridge-sev1  (42 members)", fill=(220, 225, 235), font=pill_font)

        slack_messages = [
            ("DevOps Bot", "[17:02:18]", "🚨 500 Crash Loop: auth-cluster unhealthy", (239, 68, 68), 0.2),
            ("VP Engineering", "[17:02:35]", "Is anyone looking at this? Users cannot log in.", (245, 158, 11), 0.8),
            ("Junior Dev (Me)", "[17:02:49]", "Just reverting my one-line PR... sweating through hoodie...", (220, 225, 235), 1.5),
            ("Senior Architect", "[17:03:02]", "Reverted. First time pushing on a Friday?", (34, 197, 94), 2.2),
        ]

        sy = s_y1 + 80
        for sender, ts, msg, col, rev_t in slack_messages:
            if t_scene >= rev_t:
                draw.text((s_x1 + 30, sy), sender, fill=col, font=pill_font)
                draw.text((s_x1 + 250, sy), ts, fill=(100, 110, 130), font=FontCatalog.get_font("mono", 16))
                draw.text((s_x1 + 30, sy + 30), msg, fill=(240, 245, 255), font=sub_font)
                sy += 95


class KineticTypographyLayer(Layer):
    """Upper-third kinetic text animator strictly positioned within mobile safe margin (y=160-250)."""

    def __init__(self, plan: ScenePlan, z_index: int = 50) -> None:
        super().__init__(z_index=z_index)
        self.plan = plan

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        text = (self.plan.kinetic_text or "").strip()
        if not text:
            return

        w, h = canvas.size
        draw = ImageDraw.Draw(canvas)

        # Kinetic reveal animation
        anim_p = min(1.0, t_scene / 0.25)
        ease_p = Easing.ease_out_cubic(anim_p)
        alpha = int(255 * ease_p)

        font = FontCatalog.get_font("headline", 36, bold=True)
        pill_text = text.upper()
        bbox = draw.textbbox((0, 0), pill_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pill_w = text_w + 50
        pill_h = text_h + 24
        pill_x = (w - pill_w) // 2
        # Position strictly in upper safe zone (y=170)
        pill_y = int(140 + 30 * (1.0 - ease_p))

        # Accent border color
        is_error = any(k in text.lower() for k in ("error", "500", "crash", "failure", "panic"))
        accent_col = (239, 68, 68) if is_error else (245, 158, 11)

        # Scrim Badge
        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
            radius=12,
            fill=(14, 17, 25, 230),
            outline=accent_col,
            width=2,
        )
        draw.text((pill_x + 25, pill_y + 10), pill_text, fill=(255, 255, 255, alpha), font=font)


class CaptionLayer(Layer):
    """High-contrast mobile-safe caption layer positioned strictly in lower safe margin (y=1540-1640)."""

    def __init__(self, caption_cues: Optional[List[CaptionCue]], z_index: int = 60) -> None:
        super().__init__(z_index=z_index)
        self.caption_cues = caption_cues or []

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        w, h = canvas.size
        draw = ImageDraw.Draw(canvas)

        active_text = ""
        for cue in self.caption_cues:
            if cue.start_sec <= t_global < cue.end_sec:
                active_text = cue.text.strip()
                break

        if not active_text:
            return

        font = FontCatalog.get_font("sans", 38, bold=True)
        bbox = draw.textbbox((0, 0), active_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x = 28
        pad_y = 16
        pill_w = text_w + (pad_x * 2)
        pill_h = text_h + (pad_y * 2)

        pill_x = (w - pill_w) // 2
        # Guaranteed safe position above TikTok / YouTube Shorts native UI (y=1560)
        pill_y = 1560

        # Background pill with drop shadow
        draw.rounded_rectangle(
            [pill_x + 4, pill_y + 6, pill_x + pill_w + 4, pill_y + pill_h + 6],
            radius=14,
            fill=(0, 0, 0, 160),
        )
        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
            radius=14,
            fill=(12, 14, 20, 240),
            outline=(245, 158, 11),
            width=2,
        )

        draw.text((pill_x + pad_x, pill_y + pad_y - 2), active_text, fill=(255, 255, 255), font=font)


class BrowserPreviewLayer(Layer):
    """Dark-mode DevTools & API Network Telemetry inspector (eliminates luminance flashbangs)."""

    def __init__(self, plan: ScenePlan, z_index: int = 10) -> None:
        super().__init__(z_index=z_index)
        self.plan = plan

    def render(self, canvas: Image.Image, t_scene: float, t_global: float, duration: float) -> None:
        draw = ImageDraw.Draw(canvas)
        w, h = canvas.size

        w_x1, w_y1 = 45, 260
        w_x2, w_y2 = w - 45, 1480

        # Shadow & dark window body (100% dark mode, avoiding stark white flashbang)
        draw.rounded_rectangle([w_x1 + 6, w_y1 + 8, w_x2 + 6, w_y2 + 8], radius=16, fill=(6, 8, 12, 180))
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y2], radius=16, fill=(18, 20, 28), outline=(48, 55, 75), width=2)

        # Title bar & Window controls
        draw.rounded_rectangle([w_x1, w_y1, w_x2, w_y1 + 60], radius=16, fill=(28, 32, 44))
        draw.rectangle([w_x1, w_y1 + 40, w_x2, w_y1 + 60], fill=(28, 32, 44))
        draw.ellipse([w_x1 + 24, w_y1 + 22, w_x1 + 38, w_y1 + 36], fill=(255, 95, 86))
        draw.ellipse([w_x1 + 48, w_y1 + 22, w_x1 + 62, w_y1 + 36], fill=(255, 189, 46))
        draw.ellipse([w_x1 + 72, w_y1 + 22, w_x1 + 86, w_y1 + 36], fill=(39, 201, 63))

        # URL Bar
        draw.rounded_rectangle([w_x1 + 120, w_y1 + 12, w_x2 - 30, w_y1 + 48], radius=8, fill=(16, 18, 24))
        url_font = FontCatalog.get_font("mono", 18, bold=False)
        draw.text((w_x1 + 135, w_y1 + 20), "https://api.mhide.dev/v1/auth/session  🔒", fill=(160, 175, 200), font=url_font)

        # Main Crash Card
        pill_font = FontCatalog.get_font("mono", 20, bold=True)
        title_font = FontCatalog.get_font("headline", 40, bold=True)
        code_font = FontCatalog.get_font("mono", 24, bold=False)

        # Pulse border on 500 crash
        pulse = 0.5 + 0.5 * math.sin(t_scene * 6.0)
        border_col = (int(220 + 35 * pulse), 40, 50)
        draw.rounded_rectangle([w_x1 + 30, w_y1 + 85, w_x2 - 30, w_y1 + 320], radius=12, fill=(32, 14, 20), outline=border_col, width=2)

        draw.rounded_rectangle([w_x1 + 50, w_y1 + 105, w_x1 + 350, w_y1 + 145], radius=6, fill=(239, 68, 68))
        draw.text((w_x1 + 65, w_y1 + 112), "HTTP 500 CRASH LOOP", fill=(255, 255, 255), font=pill_font)

        draw.text((w_x1 + 50, w_y1 + 165), "INTERNAL SERVER ERROR", fill=(255, 255, 255), font=title_font)
        draw.text((w_x1 + 50, w_y1 + 225), "Failed to authenticate request: PoolTimeout", fill=(255, 170, 180), font=code_font)
        draw.text((w_x1 + 50, w_y1 + 265), "Active sessions dropped: 4,000 / 4,000 (100% failure)", fill=(245, 158, 11), font=code_font)

        # Live Latency Graph (DevTools Network Inspector)
        draw.rounded_rectangle([w_x1 + 30, w_y1 + 345, w_x2 - 30, w_y2 - 30], radius=12, fill=(22, 25, 35))
        draw.text((w_x1 + 50, w_y1 + 365), "NETWORK TELEMETRY // P99 LATENCY", fill=(120, 130, 150), font=pill_font)

        # Spiking latency graph
        gw = (w_x2 - w_x1 - 100)
        gh = 220
        gx1 = w_x1 + 50
        gy2 = w_y1 + 640
        gy1 = gy2 - gh

        # Draw grid
        for ly in range(gy1, gy2, 50):
            draw.line([(gx1, ly), (gx1 + gw, ly)], fill=(35, 40, 55), width=1)

        # Sparkline points: normal at start, skyrocketing at t > 0.3s
        points = []
        num_pts = 30
        for i in range(num_pts):
            px = gx1 + int((i / (num_pts - 1)) * gw)
            if i < 10:
                norm_h = 0.08 + 0.04 * math.sin(i * 0.8)
            else:
                progress = min(1.0, max(0.0, (t_scene - 0.2) / 0.8))
                norm_h = 0.08 + (0.88 * progress) * min(1.0, (i - 9) / 5.0)
            py = gy2 - int(norm_h * gh)
            points.append((px, py))

        for i in range(len(points) - 1):
            col = (34, 197, 94) if i < 10 else (239, 68, 68)
            draw.line([points[i], points[i + 1]], fill=col, width=3)

        # Big Latency Callout
        lat_text = "9,420 ms" if t_scene >= 0.8 else f"{int(45 + 9375 * min(1.0, t_scene / 0.8))} ms"
        draw.text((w_x1 + 50, w_y1 + 665), f"P99 LATENCY: {lat_text}", fill=(239, 68, 68), font=title_font)
        draw.text((w_x1 + 50, w_y1 + 735), "DATABASE POOL: 100 / 100 EXHAUSTED", fill=(245, 158, 11), font=code_font)
        draw.text((w_x1 + 50, w_y1 + 780), "QUEUE DEPTH: 4,012 REQUESTS WAITING", fill=(220, 225, 235), font=code_font)
        draw.text((w_x1 + 50, w_y1 + 825), "ERROR RATE: 99.8% 5XX RESPONSES", fill=(239, 68, 68), font=code_font)


class SceneGraph:
    """Orchestrates multi-layer compositing for a vertical Short frame."""

    def __init__(self, width: int = 1080, height: int = 1920) -> None:
        self.width = width
        self.height = height
        self.layers: List[Layer] = []

    def add_layer(self, layer: Layer) -> None:
        self.layers.append(layer)
        self.layers.sort(key=lambda l: l.z_index)

    def render_frame(self, t_scene: float, t_global: float, duration: float) -> Image.Image:
        canvas = Image.new("RGB", (self.width, self.height), (15, 17, 23))
        for layer in self.layers:
            layer.render(canvas, t_scene, t_global, duration)
        return canvas


class SceneGraphFactory:
    """Builds purposeful scene graphs based on plan asset type and creative treatment."""

    @classmethod
    def create_scene_graph(
        cls,
        plan: ScenePlan,
        caption_cues: Optional[List[CaptionCue]],
        treatment: str = "treatment_a",
    ) -> SceneGraph:
        sg = SceneGraph(width=1080, height=1920)
        asset_type = plan.asset_type.lower()
        purpose = plan.visual_purpose.lower()

        # 1. Background Layer (Treatment aware)
        if treatment in ("treatment_d", "master"):
            bg_style = "master"
        elif treatment == "treatment_b":
            bg_style = "kinetic"
        elif treatment == "treatment_c":
            bg_style = "cinematic"
        else:
            bg_style = "dark_ide"
        sg.add_layer(AmbientBackgroundLayer(style_preset=bg_style, z_index=0))

        # 2. Content Layer
        if asset_type in ("code_editor", "code", "code_window"):
            sg.add_layer(CodeWindowLayer(plan=plan, z_index=10))
        elif asset_type in ("terminal_window", "terminal_crash") or "terminal" in purpose:
            sg.add_layer(TerminalWindowLayer(plan=plan, z_index=10))
        elif asset_type in ("split_comparison", "split_screen") or "split" in purpose:
            sg.add_layer(SplitComparisonLayer(plan=plan, z_index=10))
        elif asset_type in ("browser_preview", "browser", "network_inspector") or "latency" in purpose or "browser" in purpose:
            sg.add_layer(BrowserPreviewLayer(plan=plan, z_index=10))
        elif asset_type in ("confession_card", "confession") or purpose == "hook":
            sg.add_layer(ConfessionCardLayer(plan=plan, z_index=10))
        else:
            sg.add_layer(CodeWindowLayer(plan=plan, z_index=10))

        # 3. Kinetic Typography Layer (Upper Safe Zone)
        sg.add_layer(KineticTypographyLayer(plan=plan, z_index=50))

        # 4. Mobile Safe Caption Layer (Lower Safe Zone)
        sg.add_layer(CaptionLayer(caption_cues=caption_cues, z_index=60))

        return sg


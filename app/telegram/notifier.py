"""Telegram remote control room notifier sending non-blocking status updates and alerts."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

from app.config import config
from app.utils.logger import logger


class TelegramNotifier:
    """Non-blocking Telegram notifier. Operates as an optional monitoring interface."""

    def __init__(self, bot_token: Optional[str] = None, allowed_user_ids: Optional[List[int]] = None) -> None:
        self.bot_token = bot_token or config.telegram_bot_token
        self.allowed_user_ids = allowed_user_ids if allowed_user_ids is not None else config.telegram_allowed_user_ids

    @property
    def is_configured(self) -> bool:
        """Return True if bot token and at least one recipient are configured."""
        return bool(self.bot_token and self.allowed_user_ids)

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send message to all authorized user IDs. Non-blocking with error safety."""
        if not self.is_configured:
            logger.debug(f"[Telegram Notifier (Unconfigured)]: {text[:100]}...")
            return False

        success = True
        for chat_id in self.allowed_user_ids:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                }
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status != 200:
                        success = False
            except Exception as e:
                logger.warning(f"Failed to deliver Telegram notification to {chat_id}: {e}")
                success = False

        return success

    def notify_startup(self, startup_info: Dict[str, Any]) -> bool:
        """Notify on agent or scheduler startup."""
        msg = (
            "🚀 *Mhide Story Intelligence — Autonomous Operator Online*\n\n"
            f"• Mode: `{config.youtube_publish_mode.upper()}`\n"
            f"• Free Disk: `{startup_info.get('hardware', {}).get('free_disk_gb', 0):.1f} GB`\n"
            f"• Concurrency: `{config.render_concurrency} render job`\n"
            f"• Daily Target: `{config.daily_shorts_target} Short(s)/day`\n"
            "• Status: *Active & Monitoring*"
        )
        return self.send_message(msg)

    def notify_opportunity_discovered(self, topic: str, score: float, angle: str) -> bool:
        """Notify on newly discovered and selected storytelling opportunity."""
        msg = (
            "💡 *New Story Opportunity Selected*\n\n"
            f"• *Topic:* {topic}\n"
            f"• *Weighted Score:* {score:.1f}/100\n"
            f"• *Angle:* {angle}\n\n"
            "_Production pipeline initiating autonomously._"
        )
        return self.send_message(msg)

    def notify_video_ready(self, job_id: str, title: str, word_count: int, est_duration: float) -> bool:
        """Notify when video script and QA have passed."""
        msg = (
            "🎬 *Video Ready (QA Passed)*\n\n"
            f"• *Job ID:* `{job_id}`\n"
            f"• *Title:* {title}\n"
            f"• *Words:* {word_count} (~{est_duration:.1f}s)\n"
            f"• *Publishing Policy:* `{config.youtube_publish_mode}`"
        )
        return self.send_message(msg)

    def notify_video_published(self, title: str, url: str, privacy: str) -> bool:
        """Notify on successful video publication."""
        msg = (
            "🎉 *Short Published to YouTube!*\n\n"
            f"• *Title:* {title}\n"
            f"• *Visibility:* `{privacy.upper()}`\n"
            f"• *Link:* [Watch on YouTube]({url})\n\n"
            "_Performance feedback loop will track 24h/48h analytics._"
        )
        return self.send_message(msg)

    def notify_alert(self, title: str, message: str) -> bool:
        """Notify on critical alert or auto-pause."""
        msg = (
            f"⚠️ *ALERT: {title}*\n\n"
            f"{message}\n\n"
            "Use `/resume` once resolved."
        )
        return self.send_message(msg)


# Global notifier singleton
notifier = TelegramNotifier()

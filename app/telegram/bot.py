"""Telegram Control Room bot handling remote operator commands."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

from app.analytics.learning_engine import LearningEngine
from app.config import config
from app.database.db import db
from app.scheduler.engine import AutonomousScheduler
from app.utils.hardware import inspect_hardware
from app.utils.logger import logger


class TelegramControlRoom:
    """Handles operator commands from Telegram to inspect, pause, or resume the agent."""

    def __init__(self) -> None:
        self.bot_token = config.telegram_bot_token
        self.allowed_users = config.telegram_allowed_user_ids
        self.scheduler = AutonomousScheduler()
        self.learning_engine = LearningEngine()

    def handle_command(self, user_id: int, command: str) -> str:
        """Process command string from an authenticated user."""
        if self.allowed_users and user_id not in self.allowed_users:
            logger.warning(f"Unauthorized Telegram access attempt by user ID: {user_id}")
            return "⛔ Unauthorized access. This user ID is not registered in TELEGRAM_ALLOWED_USER_IDS."

        cmd = command.strip().lower()

        if cmd in ("/start", "/help"):
            return (
                "🎮 *Mhide Story Intelligence — Control Room Commands*\n\n"
                "• `/status` — Channel status, queue distribution, and disk headroom\n"
                "• `/latest` — Show latest produced/published YouTube Short\n"
                "• `/clean` — Purge old video render folders and cache to free disk space\n"
                "• `/pause` — Globally pause autonomous production & uploads\n"
                "• `/resume` — Resume autonomous scheduler\n"
                "• `/strategy` — View empirical strategy weights and performance feedback\n"
                "• `/decisions` — View recent autonomous AI decision audit trail\n"
            )

        elif cmd == "/status":
            hw = inspect_hardware()
            counts = db.count_jobs_by_state()
            state = self.scheduler.get_state()
            owner_status = db.get_owner_channel_status()

            status_lines = [
                "📊 *Autonomous System Status*",
                f"• State: `{'PAUSED (' + (state.pause_reason or '') + ')' if state.is_paused else 'ACTIVE & OPERATING'}`",
                f"• Publish Mode: `{config.youtube_publish_mode.upper()}`",
                f"• Owner Channel: `{'CONNECTED (' + owner_status.title + ')' if owner_status.is_connected else 'NOT CONNECTED'}`",
                f"• Free Disk Space: `{hw.free_disk_gb:.1f} GB` (min: {config.min_disk_free_gb:.1f} GB)",
                f"• Concurrency: `{config.render_concurrency} render job`",
                "\n*Job Queue Distribution:*",
            ]
            for s, c in counts.items():
                if c > 0:
                    status_lines.append(f"  - `{s}`: {c}")
            return "\n".join(status_lines)

        elif cmd == "/pause":
            self.scheduler.pause("Paused by owner via Telegram command")
            return "⏸️ *Autonomous Scheduler Paused.* No new jobs will be generated or published until resumed."

        elif cmd == "/resume":
            self.scheduler.resume()
            return "▶️ *Autonomous Scheduler Resumed.* Normal scheduled operations have recommenced."

        elif cmd == "/strategy":
            return f"```\n{self.learning_engine.get_strategy_performance_report()}\n```"

        elif cmd == "/decisions":
            logs = db.get_decision_logs(limit=5)
            if not logs:
                return "No autonomous decisions logged yet."
            lines = ["📋 *Recent Autonomous Decisions:*"]
            for d in logs:
                lines.append(f"\n• *[{d.decision_type}]* `{d.created_at[:16]}`\n  Action: `{d.chosen_action}`\n  Rationale: {d.rationale}")
            return "\n".join(lines)

        elif cmd == "/latest":
            pubs = db.get_published_videos(limit=1)
            if pubs:
                v = pubs[0]
                return f"🎥 *Latest Published Video:*\n• Title: *{v.title}*\n• Visibility: `{v.privacy_status}`\n• URL: {v.youtube_url}"
            else:
                jobs = db.list_jobs(limit=1)
                if jobs:
                    j = jobs[0]
                    return f"Latest Job: *{j.title}* (State: `{j.state.value}`, ID: `{j.id}`)"
        elif cmd == "/clean":
            from app.orchestrator import Orchestrator
            orch = Orchestrator()
            res = orch.clean_all_artifacts()
            return (
                "🧹 *Disk Cleanup Complete*\n\n"
                f"• Removed Job Folders: `{res['removed_job_folders']}`\n"
                f"• Removed Temp Clips: `{res['removed_temp_files']}`\n"
                f"• Reclaimed Space: `{res['freed_mb']:.1f} MB`\n"
            )

        return "Unknown command. Send `/help` for available commands."

    def start_polling(self, poll_interval_sec: float = 2.0) -> None:
        """Poll Telegram getUpdates and reply to incoming commands."""
        if not self.bot_token:
            logger.warning("Telegram bot token not configured.")
            return

        logger.info(f"Telegram Control Room bot active (polling @DarkestMindsbot)...")
        offset = None

        while True:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {"timeout": 10}
                if offset:
                    params["offset"] = offset
                url = f"{url}?{urllib.parse.urlencode(params)}"

                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    updates = data.get("result", [])

                for update in updates:
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    user_id = msg.get("from", {}).get("id")
                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")

                    if user_id and text and chat_id:
                        reply_text = self.handle_command(user_id, text)
                        send_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                        send_data = json.dumps({
                            "chat_id": chat_id,
                            "text": reply_text,
                            "parse_mode": "Markdown",
                        }).encode("utf-8")
                        send_req = urllib.request.Request(
                            send_url,
                            data=send_data,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        urllib.request.urlopen(send_req, timeout=5)
            except Exception as e:
                logger.debug(f"Telegram polling note: {e}")

            time.sleep(poll_interval_sec)

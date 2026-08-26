"""Slim Telegram poller: photos start an interview, any text stops it (spec 5).

This is NOT the Hermes gateway. It carries no audio and holds no state.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from kg.photos import make_portrait

log = logging.getLogger(__name__)

#: python-telegram-bot's own defaults. The token is appended to both by
#: `telegram._bot._parse_base_url`, so these end in `/bot` without a slash.
TELEGRAM_API_URL = "https://api.telegram.org/bot"
TELEGRAM_FILE_URL = "https://api.telegram.org/file/bot"


class TelegramSource:
    def __init__(
        self,
        token: str,
        chat_id: int | None,
        photo_dir: Path,
        portrait_dir: Path,
        portrait_size: int,
        on_photo: Callable[[Path, Path, float], None],
        on_text: Callable[[str, float], None],
        downloader: Callable[[str, Path], None] | None = None,
        api_base_url: str = TELEGRAM_API_URL,
        api_base_file_url: str = TELEGRAM_FILE_URL,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        # The two API roots are arguments, not constants, for exactly one
        # reason: the end-to-end test (tests/e2e) points the REAL poller and
        # the REAL downloader at a local stand-in of Telegram's HTTP API, so
        # `getUpdates` -> `getFile` -> file download runs as shipped, without a
        # token and without the network. Live operation never passes them.
        self.api_base_url = api_base_url
        self.api_base_file_url = api_base_file_url
        self.photo_dir = Path(photo_dir)
        self.portrait_dir = Path(portrait_dir)
        self.portrait_size = portrait_size
        self.on_photo = on_photo
        self.on_text = on_text
        self.downloader = downloader or self._download_via_bot
        self._bot = None
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        self.portrait_dir.mkdir(parents=True, exist_ok=True)

    async def dispatch(self, update: dict) -> None:
        message = update.get("message") or update.get("channel_post")
        if not isinstance(message, dict):
            return
        if self.chat_id is not None and message.get("chat", {}).get("id") != self.chat_id:
            return

        at = float(message.get("date", 0.0))
        photos = message.get("photo") or []
        if photos:
            await self._handle_photo(photos, message.get("message_id", 0), at)
            return

        text = message.get("text")
        if isinstance(text, str) and text.strip():
            self.on_text(text.strip(), at)

    async def _handle_photo(self, photos: list[dict], message_id: int, at: float) -> None:
        largest = max(photos, key=lambda p: p.get("width", 0) * p.get("height", 0))
        photo_path = self.photo_dir / f"{int(at)}_{message_id}.jpg"
        portrait_path = self.portrait_dir / f"{int(at)}_{message_id}.png"
        try:
            await asyncio.to_thread(self.downloader, largest["file_id"], photo_path)
            await asyncio.to_thread(
                make_portrait, photo_path, portrait_path, self.portrait_size
            )
        except Exception as exc:  # Telegram offline / broken image: stay alive
            log.warning("photo handling failed (%s)", exc)
            return
        self.on_photo(photo_path, portrait_path, at)

    def _download_via_bot(self, file_id: str, dest: Path) -> None:
        from telegram import Bot  # imported lazily so tests need no network stack

        async def _run() -> None:
            bot = Bot(
                self.token,
                base_url=self.api_base_url,
                base_file_url=self.api_base_file_url,
            )
            async with bot:
                file = await bot.get_file(file_id)
                await file.download_to_drive(custom_path=str(dest))

        asyncio.run(_run())

    def build_application(self):
        """Wire python-telegram-bot to dispatch(). Called only by kg.core."""
        from telegram.ext import Application, MessageHandler, filters

        application = (
            Application.builder()
            .token(self.token)
            .base_url(self.api_base_url)
            .base_file_url(self.api_base_file_url)
            .build()
        )

        async def handler(update, context) -> None:
            await self.dispatch(update.to_dict())

        application.add_handler(MessageHandler(filters.ALL, handler))
        return application

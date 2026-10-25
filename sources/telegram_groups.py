"""Telegram grupos/canales PUBLICOS via Telethon (opcional). Requiere TELEGRAM_API_ID/HASH de https://my.telegram.org
y una sesion creada una vez de forma interactiva: python -m sources.telegram_groups --login
(Experimental: no probado en este entorno; usar con cuidado.)"""
from __future__ import annotations

import asyncio
import logging
import sys

from config import settings
from sources.base import Post, Source

log = logging.getLogger("source.telegram")
SESSION = str(settings.data_dir / "telegram_session")


class TelegramSource(Source):
    name = "telegram"

    def __init__(self):
        from telethon import TelegramClient  # noqa: F401  (valida que este instalado)

        self.interval_minutes = settings.telegram_interval_minutes

    def fetch(self) -> list[Post]:
        return asyncio.run(self._fetch())

    async def _fetch(self) -> list[Post]:
        from telethon import TelegramClient

        posts: list[Post] = []
        client = TelegramClient(SESSION, int(settings.telegram_api_id), settings.telegram_api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            log.error("Telegram: sesion no autorizada. Ejecuta: python -m sources.telegram_groups --login")
            await client.disconnect()
            return []
        for group in settings.telegram_groups:
            try:
                async for msg in client.iter_messages(group, limit=settings.telegram_messages_per_group):
                    if not msg.message:
                        continue
                    username = group.rsplit("/", 1)[-1].lstrip("@")
                    url = f"https://t.me/{username}/{msg.id}"
                    sender = ""
                    try:
                        s = await msg.get_sender()
                        sender = getattr(s, "username", None) or getattr(s, "first_name", "") or ""
                        if sender and not sender.startswith("@") and getattr(s, "username", None):
                            sender = "@" + sender
                    except Exception:
                        pass
                    posts.append(Post(id=f"telegram:{username}:{msg.id}", source=self.name, text=msg.message, url=url,
                                      author=sender, posted_at=msg.date, extra={"group": username}))
            except Exception as e:
                log.warning("Telegram grupo %s fallo: %s", group, e)
        await client.disconnect()
        return posts


async def _login():
    from telethon import TelegramClient

    client = TelegramClient(SESSION, int(settings.telegram_api_id), settings.telegram_api_hash)
    await client.start()  # pide telefono + codigo de forma interactiva
    me = await client.get_me()
    print(f"Sesion creada para {me.first_name} ({me.phone}). Archivo: {SESSION}.session")
    await client.disconnect()


if __name__ == "__main__":
    if "--login" in sys.argv:
        asyncio.run(_login())
    else:
        print("Uso: python -m sources.telegram_groups --login")

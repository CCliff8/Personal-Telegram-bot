import os
from typing import Optional

from dotenv import load_dotenv

from .telegram import TelegramClient
from .router import Router
from .handlers import make_echo_handler


def main() -> None:
    load_dotenv()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed_ids = {int(x.strip()) for x in os.environ["TELEGRAM_CHAT_ID"].split(",")}

    client = TelegramClient(token)
    router = Router()
    router.register(lambda msg: bool(msg.get("text")))(make_echo_handler(client))

    offset: Optional[int] = None
    print("Bot running. Press Ctrl-C to stop.")

    try:
        while True:
            updates = client.get_updates(offset=offset)
            for update in updates:
                # Advance the offset so Telegram drops this update from the queue.
                # Setting offset = update_id + 1 is the acknowledgement mechanism.
                offset = update["update_id"] + 1
                msg = update.get("message")
                if msg and msg["chat"]["id"] in allowed_ids:
                    router.dispatch(msg)
                    router.save_state()
    finally:
        client.close()

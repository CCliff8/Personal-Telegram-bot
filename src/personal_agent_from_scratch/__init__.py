import os
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from .telegram import TelegramClient
from .router import Router
from .handlers import make_echo_handler
from .skills.morning_brief import run as morning_brief_run


def main() -> None:
    load_dotenv()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed_ids = {int(x.strip()) for x in os.environ["TELEGRAM_CHAT_ID"].split(",")}
    brief_chat_id = int(os.environ["TELEGRAM_CHAT_ID"].split(",")[0].strip())

    client = TelegramClient(token)
    router = Router()
    def send_morning_brief() -> None:
        try:
            text = morning_brief_run()
            client.send_message(brief_chat_id, text)
        except Exception as e:
            client.send_message(brief_chat_id, f"Morning brief failed: {e}")

    @router.register(lambda msg: msg.get("text", "").startswith("/brief"))
    def handle_brief(message: dict, router) -> None:
        send_morning_brief()

    router.register(lambda msg: bool(msg.get("text")))(make_echo_handler(client))

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        send_morning_brief,
        CronTrigger(hour=7, minute=0, timezone="Europe/Rome"),
    )
    scheduler.start()
    print("Bot running. Press Ctrl-C to stop.")

    offset: Optional[int] = None
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
        scheduler.shutdown()
        client.close()

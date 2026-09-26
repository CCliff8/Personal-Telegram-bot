import os
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from .telegram import TelegramClient
from .router import Router
from .handlers import make_echo_handler
from .skills.morning_brief import run as morning_brief_run
from .skills import evening_reflection as reflection


def main() -> None:
    load_dotenv()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed_ids = {int(x.strip()) for x in os.environ["TELEGRAM_CHAT_ID"].split(",")}
    brief_chat_id = int(os.environ["TELEGRAM_CHAT_ID"].split(",")[0].strip())

    client = TelegramClient(token)
    router = Router()

    # --- Morning brief ---

    def send_morning_brief() -> None:
        try:
            text = morning_brief_run()
            client.send_message(brief_chat_id, text)
        except Exception as e:
            client.send_message(brief_chat_id, f"Morning brief failed: {e}")

    @router.register(lambda msg: msg.get("text", "").startswith("/brief"))
    def handle_brief(message: dict, router) -> None:
        send_morning_brief()

    # --- Evening reflection ---

    def send_reflection_prompt() -> None:
        reflection.start(router.state)
        router.save_state()
        client.send_message(brief_chat_id, reflection.PROMPT_MESSAGE)

    @router.register(lambda msg: msg.get("text", "").startswith("/reflect"))
    def handle_reflect(message: dict, router) -> None:
        send_reflection_prompt()

    @router.register(lambda msg: msg.get("text", "").startswith("/done") and reflection.is_active(router.state))
    def handle_done(message: dict, router) -> None:
        if not router.state.get("reflection_messages"):
            client.send_message(message["chat"]["id"], "Nothing to save — you didn't write anything.")
            reflection.reset(router.state)
            return
        structured = reflection.finish(router.state)
        client.send_message(message["chat"]["id"], structured)

    @router.register(lambda msg: reflection.is_active(router.state) and bool(msg.get("text")))
    def handle_reflection_input(message: dict, router) -> None:
        reflection.accumulate(router.state, message["text"])

    # --- Echo (catch-all) ---

    router.register(lambda msg: bool(msg.get("text")))(make_echo_handler(client))

    # --- Scheduler ---

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        send_morning_brief,
        CronTrigger(hour=7, minute=0, timezone="Europe/Rome"),
    )
    scheduler.add_job(
        send_reflection_prompt,
        CronTrigger(hour=21, minute=0, timezone="Europe/Rome"),
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

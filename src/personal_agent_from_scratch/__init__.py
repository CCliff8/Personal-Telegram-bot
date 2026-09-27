import os
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from .telegram import TelegramClient
from .router import Router
from .skills.morning_brief import run as morning_brief_run
from .skills import evening_reflection as reflection
from .skills.linkedin_draft import run as linkedin_run
from .skills import quiz


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

    @router.register(lambda msg: msg.get("text", "").startswith("/exit"))
    def handle_exit(message: dict, router) -> None:
        router.state.clear()
        client.send_message(message["chat"]["id"], "Cancelled.")

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

    # --- LinkedIn draft ---

    def send_linkedin_draft() -> None:
        try:
            text = linkedin_run()
            client.send_message(brief_chat_id, text)
        except Exception as e:
            client.send_message(brief_chat_id, f"LinkedIn draft failed: {e}")

    @router.register(lambda msg: msg.get("text", "").startswith("/linkedin"))
    def handle_linkedin(message: dict, router) -> None:
        send_linkedin_draft()

    # --- Quiz ---

    @router.register(lambda msg: msg.get("text", "").lower().startswith("/testme"))
    def handle_testme(message: dict, router) -> None:
        parts = message["text"].split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            client.send_message(message["chat"]["id"], "Usage: /testme <topic>")
            return
        topic = parts[1].strip()
        question = quiz.generate_question(topic)
        router.state["awaiting_quiz_answer"] = True
        router.state["quiz_topic"] = topic
        router.state["quiz_question"] = question
        client.send_message(message["chat"]["id"], question)

    @router.register(lambda msg: router.state.get("awaiting_quiz_answer") and bool(msg.get("text")))
    def handle_quiz_answer(message: dict, router) -> None:
        topic = router.state.pop("quiz_topic", "")
        question = router.state.pop("quiz_question", "")
        router.state.pop("awaiting_quiz_answer", None)
        evaluation = quiz.evaluate_answer(topic, question, message["text"])
        client.send_message(message["chat"]["id"], evaluation)

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
    scheduler.add_job(
        send_linkedin_draft,
        CronTrigger(day_of_week="sun", hour=18, minute=0, timezone="Europe/Rome"),
    )
    scheduler.start()
    print("Bot running. Press Ctrl-C to stop.")

    client.send_message(brief_chat_id, (
        "Agent online.\n\n"
        "/brief — morning brief (weather, calendar, email)\n"
        "/reflect — start evening reflection\n"
        "/done — save and finish reflection\n"
        "/linkedin — generate LinkedIn draft from last 6 reflections\n"
        "/testme <topic> — get quizzed on any topic\n"
        "/exit — cancel any active session"
    ))

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

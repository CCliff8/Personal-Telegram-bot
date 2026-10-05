import os
import threading
from typing import Optional

from dotenv import load_dotenv

from .startup import decode_google_credentials, sync_data_from_repo
from .telegram import TelegramClient
from .router import Router
from .skills.morning_brief import run as morning_brief_run
from .skills import evening_reflection as reflection
from .skills.linkedin_draft import run as linkedin_run
from .skills import quiz
from .skills import remind
from .skills import chat
from .skills import read as read_skill
from .skills import schedule as schedule_skill


SESSION_KEYS = {
    "awaiting_reflection": "/reflect",
    "read_title": "/read",
    "in_chat": "/chat",
    "awaiting_quiz_answer": "/testme",
    "schedule_pending": "/schedule",
}

COMMANDS = {
    "/exit", "/brief", "/reflect", "/done", "/linkedin",
    "/testme", "/remind", "/chat", "/read", "/schedule",
}


def _is_command(text: str) -> bool:
    return text.split()[0].lower() in COMMANDS


def _active_session(state: dict) -> Optional[str]:
    for key, name in SESSION_KEYS.items():
        if state.get(key):
            return name
    return None


def main() -> None:
    load_dotenv()
    decode_google_credentials()
    sync_data_from_repo()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed_ids = {int(x.strip()) for x in os.environ["TELEGRAM_CHAT_ID"].split(",")}
    brief_chat_id = int(os.environ["TELEGRAM_CHAT_ID"].split(",")[0].strip())

    client = TelegramClient(token)
    router = Router()

    def _busy(chat_id: int) -> bool:
        session = _active_session(router.state)
        if session:
            client.send_message(chat_id, f"You're in a {session} session. Send /exit first.")
            return True
        return False

    # --- /exit (always first) ---

    @router.register(lambda msg: msg.get("text", "").startswith("/exit"))
    def handle_exit(message: dict, router) -> None:
        router.state.clear()
        client.send_message(message["chat"]["id"], "Cancelled.")

    # --- Morning brief ---

    def send_morning_brief() -> None:
        try:
            text = morning_brief_run()
            client.send_message(brief_chat_id, text)
        except Exception as e:
            client.send_message(brief_chat_id, f"Morning brief failed: {e}")

    @router.register(lambda msg: msg.get("text", "").startswith("/brief"))
    def handle_brief(message: dict, router) -> None:
        if _busy(message["chat"]["id"]):
            return
        send_morning_brief()

    # --- Evening reflection ---

    def send_reflection_prompt() -> None:
        reflection.start(router.state)
        router.save_state()
        client.send_message(brief_chat_id, reflection.PROMPT_MESSAGE)

    @router.register(lambda msg: msg.get("text", "").startswith("/reflect"))
    def handle_reflect(message: dict, router) -> None:
        if _busy(message["chat"]["id"]):
            return
        send_reflection_prompt()

    @router.register(lambda msg: msg.get("text", "").startswith("/done") and reflection.is_active(router.state))
    def handle_done_reflection(message: dict, router) -> None:
        if not router.state.get("reflection_messages"):
            client.send_message(message["chat"]["id"], "Nothing to save — you didn't write anything.")
            reflection.reset(router.state)
            return
        structured = reflection.finish(router.state)
        client.send_message(message["chat"]["id"], structured)

    @router.register(lambda msg: reflection.is_active(router.state) and bool(msg.get("text")) and not _is_command(msg["text"]))
    def handle_reflection_input(message: dict, router) -> None:
        reflection.accumulate(router.state, message["text"])

    # --- /read ---

    @router.register(lambda msg: msg.get("text", "").lower().startswith("/read"))
    def handle_read(message: dict, router) -> None:
        if _busy(message["chat"]["id"]):
            return
        parts = message["text"].split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            client.send_message(message["chat"]["id"], "Usage: /read <title>")
            return
        title = parts[1].strip()
        router.state["read_title"] = title
        router.state["read_messages"] = []
        client.send_message(message["chat"]["id"], f"Reading session started: {title}\nDump your notes. Send /done when finished.")

    @router.register(lambda msg: msg.get("text", "").startswith("/done") and bool(router.state.get("read_title")))
    def handle_done_read(message: dict, router) -> None:
        title = router.state.pop("read_title", "")
        notes = router.state.pop("read_messages", [])
        if not notes:
            client.send_message(message["chat"]["id"], "Nothing to save — you didn't write anything.")
            return
        raw = "\n".join(notes)
        structured = read_skill.structure(title, raw)
        read_skill.save(title, structured)
        client.send_message(message["chat"]["id"], structured)

    @router.register(lambda msg: bool(router.state.get("read_title")) and bool(msg.get("text")) and not _is_command(msg["text"]))
    def handle_read_input(message: dict, router) -> None:
        router.state["read_messages"].append(message["text"])

    # --- /chat ---

    @router.register(lambda msg: msg.get("text", "").lower().startswith("/chat"))
    def handle_chat_start(message: dict, router) -> None:
        if _busy(message["chat"]["id"]):
            return
        parts = message["text"].split(maxsplit=1)
        router.state["in_chat"] = True
        router.state["chat_history"] = []
        if len(parts) > 1 and parts[1].strip():
            response = chat.reply(router.state["chat_history"], parts[1].strip())
            client.send_message(message["chat"]["id"], response)
        else:
            client.send_message(message["chat"]["id"], "Chat started. Send /exit to end.")

    @router.register(lambda msg: router.state.get("in_chat") and bool(msg.get("text")) and not _is_command(msg["text"]))
    def handle_chat_message(message: dict, router) -> None:
        response = chat.reply(router.state["chat_history"], message["text"])
        client.send_message(message["chat"]["id"], response)

    # --- LinkedIn draft ---

    def send_linkedin_draft() -> None:
        try:
            text = linkedin_run()
            client.send_message(brief_chat_id, text)
        except Exception as e:
            client.send_message(brief_chat_id, f"LinkedIn draft failed: {e}")

    @router.register(lambda msg: msg.get("text", "").startswith("/linkedin"))
    def handle_linkedin(message: dict, router) -> None:
        if _busy(message["chat"]["id"]):
            return
        send_linkedin_draft()

    # --- Quiz ---

    @router.register(lambda msg: msg.get("text", "").lower().startswith("/testme"))
    def handle_testme(message: dict, router) -> None:
        if _busy(message["chat"]["id"]):
            return
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

    @router.register(lambda msg: router.state.get("awaiting_quiz_answer") and bool(msg.get("text")) and not _is_command(msg["text"]))
    def handle_quiz_answer(message: dict, router) -> None:
        topic = router.state.pop("quiz_topic", "")
        question = router.state.pop("quiz_question", "")
        router.state.pop("awaiting_quiz_answer", None)
        evaluation = quiz.evaluate_answer(topic, question, message["text"])
        client.send_message(message["chat"]["id"], evaluation)

    # --- Reminders ---

    @router.register(lambda msg: msg.get("text", "").lower().startswith("/remind"))
    def handle_remind(message: dict, router) -> None:
        chat_id = message["chat"]["id"]
        if _busy(chat_id):
            return
        parts = message["text"].split(maxsplit=1)
        if len(parts) < 2:
            client.send_message(chat_id, "Usage: /remind <message> in <time> (e.g. /remind call Marco in 10m)")
            return
        parsed = remind.parse(parts[1])
        if parsed is None:
            client.send_message(chat_id, "Couldn't parse that. Try: /remind call Marco in 10m")
            return
        reminder_text, seconds = parsed
        label = remind.fire_time_label(seconds)

        def fire() -> None:
            client.send_message(chat_id, f"Reminder: {reminder_text}")

        threading.Timer(seconds, fire).start()
        client.send_message(chat_id, f"Reminder set for {label}.")

    # --- Schedule ---

    def _complete_schedule(chat_id: int, fields: dict) -> None:
        router.state.pop("schedule_pending", None)
        router.state.pop("schedule_awaiting", None)
        try:
            confirmation = schedule_skill.create_event(fields)
            client.send_message(chat_id, confirmation)
        except Exception as e:
            client.send_message(chat_id, f"Failed to create event: {e}")

    @router.register(lambda msg: msg.get("text", "").lower().startswith("/schedule"))
    def handle_schedule(message: dict, router) -> None:
        chat_id = message["chat"]["id"]
        if _busy(chat_id):
            return
        parts = message["text"].split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            client.send_message(chat_id, "Usage: /schedule <event> (e.g. /schedule tempo 8km thursday 18:00)")
            return
        fields = schedule_skill.extract(parts[1])
        fields["duration_min"] = schedule_skill.calculate_duration(fields)
        missing = schedule_skill.first_missing(fields)
        if missing is None:
            _complete_schedule(chat_id, fields)
        else:
            field_name, question = missing
            router.state["schedule_pending"] = fields
            router.state["schedule_awaiting"] = field_name
            client.send_message(chat_id, question)

    @router.register(lambda msg: bool(router.state.get("schedule_pending")) and bool(msg.get("text")) and not _is_command(msg["text"]))
    def handle_schedule_answer(message: dict, router) -> None:
        chat_id = message["chat"]["id"]
        fields = router.state["schedule_pending"]
        awaiting = router.state.get("schedule_awaiting")
        text = message["text"].strip()

        if awaiting == "date":
            parsed = schedule_skill.parse_date(text)
            if not parsed:
                client.send_message(chat_id, "Couldn't parse that date. Try 'Thursday' or '2026-10-09'.")
                return
            fields["date"] = parsed
        elif awaiting == "time":
            parsed = schedule_skill.parse_time(text)
            if not parsed:
                client.send_message(chat_id, "Couldn't parse that time. Try '18:00' or '7am'.")
                return
            fields["time"] = parsed
        elif awaiting == "duration_min":
            parsed = schedule_skill.parse_duration(text)
            if not parsed:
                client.send_message(chat_id, "Couldn't parse that duration. Try '45min' or '1h30'.")
                return
            fields["duration_min"] = parsed

        router.state["schedule_pending"] = fields
        missing = schedule_skill.first_missing(fields)
        if missing is None:
            _complete_schedule(chat_id, fields)
        else:
            field_name, question = missing
            router.state["schedule_awaiting"] = field_name
            client.send_message(chat_id, question)

    print("Bot running. Press Ctrl-C to stop.")

    client.send_message(brief_chat_id,
        "Agent online.\n\n"
        "/brief — morning brief (weather, calendar, email)\n"
        "/reflect — start evening reflection\n"
        "/done — save and finish reflection or reading session\n"
        "/linkedin — generate LinkedIn draft from last 6 reflections\n"
        "/testme <topic> — get quizzed on any topic\n"
        "/remind <message> in <time> — set a reminder (e.g. in 10m, 2h, 1d)\n"
        "/chat — start a conversation with Haiku (uses memory.md as context)\n"
        "/read <title> — start a reading note session, /done to save\n"
        "/schedule <event> — create a calendar event (e.g. /schedule tempo 8km thursday 18:00)\n"
        "/exit — cancel any active session"
    )

    offset: Optional[int] = None
    try:
        while True:
            updates = client.get_updates(offset=offset)
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message")
                if msg and msg["chat"]["id"] in allowed_ids:
                    router.dispatch(msg)
                    router.save_state()
    finally:
        client.close()

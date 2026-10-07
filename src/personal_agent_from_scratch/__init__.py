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
from .skills import calendar_skill


SESSION_KEYS = {
    "awaiting_reflection": "/reflect",
    "read_title": "/notes",
    "in_chat": "/chat",
    "awaiting_quiz_answer": "/testme",
    "calendar_pending": "/calendar",
}

COMMANDS = {
    "/brief", "/reflect", "/done", "/linkedin",
    "/testme", "/remind", "/chat", "/notes", "/calendar",
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
            client.send_message(chat_id, f"You're in a {session} session. Send /done to exit.")
            return True
        return False

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

    # --- /notes ---

    @router.register(lambda msg: msg.get("text", "").lower().startswith("/notes"))
    def handle_notes(message: dict, router) -> None:
        if _busy(message["chat"]["id"]):
            return
        parts = message["text"].split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            client.send_message(message["chat"]["id"], "Usage: /notes <title>")
            return
        title = parts[1].strip()
        router.state["read_title"] = title
        router.state["read_messages"] = []
        client.send_message(message["chat"]["id"], f"Notes session started: {title}\nDump your notes. Send /done when finished.")

    @router.register(lambda msg: msg.get("text", "").startswith("/done") and bool(router.state.get("read_title")))
    def handle_done_notes(message: dict, router) -> None:
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
    def handle_notes_input(message: dict, router) -> None:
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
            client.send_message(message["chat"]["id"], "Chat started. Send /done to end.")

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

    # --- Calendar ---

    @router.register(lambda msg: msg.get("text", "").lower().startswith("/calendar"))
    def handle_calendar(message: dict, router) -> None:
        chat_id = message["chat"]["id"]
        if _busy(chat_id):
            return
        parts = message["text"].split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            client.send_message(chat_id, "Usage: /calendar <event> — e.g. /calendar meeting tomorrow 10am 1h")
            return
        fields = calendar_skill.extract_intent(parts[1])

        if fields.get("intent") == "delete":
            query = fields.get("search_query") or fields.get("title") or None
            events = calendar_skill.search_events(query, fields.get("date"), fields.get("time"))
            if not events:
                date_label = fields.get("date") or "the next 30 days"
                client.send_message(chat_id, f"No events found for {date_label}.")
                return
            if len(events) == 1:
                event = events[0]
                summary = calendar_skill.format_event(event)
                router.state["calendar_pending"] = {"mode": "delete_confirm", "event_id": event["id"], "calendar_id": event.get("_calendarId", "primary"), "summary": summary}
                router.state["calendar_awaiting"] = "confirm_delete"
                client.send_message(chat_id, f"Delete: {summary}\n\nReply yes to confirm.")
            else:
                items = [{"id": e["id"], "calendar_id": e.get("_calendarId", "primary"), "summary": calendar_skill.format_event(e)} for e in events[:5]]
                lines = "\n".join(f"{i+1}. {it['summary']}" for i, it in enumerate(items))
                router.state["calendar_pending"] = {"mode": "delete_select", "events": items}
                router.state["calendar_awaiting"] = "select_event"
                client.send_message(chat_id, f"Which event?\n{lines}\n\nReply with the number to delete.")
        else:
            missing = calendar_skill.first_missing(fields)
            if missing is None:
                try:
                    client.send_message(chat_id, calendar_skill.create_event(fields))
                except Exception as e:
                    client.send_message(chat_id, f"Failed to create event: {e}")
            else:
                field_name, question = missing
                router.state["calendar_pending"] = {"mode": "create", **fields}
                router.state["calendar_awaiting"] = field_name
                client.send_message(chat_id, question)

    @router.register(lambda msg: bool(router.state.get("calendar_pending")) and bool(msg.get("text")) and not _is_command(msg["text"]))
    def handle_calendar_answer(message: dict, router) -> None:
        chat_id = message["chat"]["id"]
        pending = router.state["calendar_pending"]
        text = message["text"].strip()

        if pending["mode"] == "delete_confirm":
            router.state.pop("calendar_pending", None)
            router.state.pop("calendar_awaiting", None)
            if text.lower() in ("yes", "y", "si", "sì"):
                try:
                    calendar_skill.delete_event(pending["event_id"], pending.get("calendar_id", "primary"))
                    client.send_message(chat_id, f"Deleted: {pending['summary']}")
                except Exception as e:
                    client.send_message(chat_id, f"Failed to delete: {e}")
            else:
                client.send_message(chat_id, "Cancelled.")

        elif pending["mode"] == "delete_select":
            try:
                idx = int(text) - 1
                events = pending["events"]
                if 0 <= idx < len(events):
                    event = events[idx]
                    router.state["calendar_pending"] = {"mode": "delete_confirm", "event_id": event["id"], "calendar_id": event.get("calendar_id", "primary"), "summary": event["summary"]}
                    router.state["calendar_awaiting"] = "confirm_delete"
                    client.send_message(chat_id, f"Delete: {event['summary']}\n\nReply yes to confirm.")
                else:
                    client.send_message(chat_id, f"Reply with a number between 1 and {len(events)}.")
            except ValueError:
                client.send_message(chat_id, "Reply with a number.")

        elif pending["mode"] == "create":
            awaiting = router.state.get("calendar_awaiting")
            parsed = calendar_skill.parse_field(awaiting, text)
            if not parsed:
                client.send_message(chat_id, "Couldn't parse that, try again.")
                return
            pending[awaiting] = parsed
            router.state["calendar_pending"] = pending
            missing = calendar_skill.first_missing(pending)
            if missing is None:
                router.state.pop("calendar_pending", None)
                router.state.pop("calendar_awaiting", None)
                try:
                    client.send_message(chat_id, calendar_skill.create_event(pending))
                except Exception as e:
                    client.send_message(chat_id, f"Failed to create event: {e}")
            else:
                field_name, question = missing
                router.state["calendar_awaiting"] = field_name
                client.send_message(chat_id, question)

    # --- /done fallback: exit any remaining active session ---

    @router.register(lambda msg: msg.get("text", "").startswith("/done"))
    def handle_done_fallback(message: dict, router) -> None:
        router.state.clear()
        client.send_message(message["chat"]["id"], "Done.")

    print("Bot running. Press Ctrl-C to stop.")

    client.send_message(brief_chat_id,
        "Agent online.\n\n"
        "/brief — morning brief (weather, calendar, email)\n"
        "/reflect — start evening reflection\n"
        "/linkedin — generate LinkedIn draft from last 6 reflections\n"
        "/testme <topic> — get quizzed on any topic\n"
        "/remind <message> in <time> — set a reminder (e.g. in 10m, 2h, 1d)\n"
        "/chat — start a conversation with Haiku (uses memory.md as context)\n"
        "/notes <title> — start a note-taking session, /done to save\n"
        "/calendar <event> — create or delete a calendar event\n"
        "/done — save and finish current session, or cancel"
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

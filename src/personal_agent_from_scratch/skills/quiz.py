import anthropic


def generate_question(topic: str) -> str:
    prompt = (
        f"You are quizzing a developer who is learning in public.\n\n"
        f"Generate one focused question about: {topic}\n\n"
        "Rules:\n"
        "- One question only, no preamble\n"
        "- Conceptual or applied (not trivia)\n"
        "- Clear and specific enough to give a real answer to"
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def evaluate_answer(topic: str, question: str, answer: str) -> str:
    prompt = (
        f"A developer learning in public answered a quiz question.\n\n"
        f"Topic: {topic}\n"
        f"Question: {question}\n"
        f"Their answer: {answer}\n\n"
        "Give a brief evaluation:\n"
        "1. What they got right\n"
        "2. What's missing or imprecise (be specific)\n"
        "3. One concept or resource to deep dive next\n\n"
        "Rules: no filler, max 150 words, direct tone."
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()

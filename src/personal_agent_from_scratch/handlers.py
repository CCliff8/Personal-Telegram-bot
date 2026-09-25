from .telegram import TelegramClient


def make_echo_handler(client: TelegramClient) -> callable:
    def echo(message: dict, router) -> None:
        client.send_message(message["chat"]["id"], message.get("text", ""))
    return echo

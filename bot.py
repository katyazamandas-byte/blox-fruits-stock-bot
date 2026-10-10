"""Telegram bot that displays live Normal and Mirage Blox Fruits stock."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from stock_api import (
    DEFAULT_STOCK_API_URL,
    STOCK_SOURCE_URL,
    FruitStock,
    StockApiError,
    StockSnapshot,
    fetch_stock,
)


from language_support import get_language, get_text, save_language, language_keyboard

TELEGRAM_API_URL = "https://api.telegram.org"
TELEGRAM_LONG_POLL_SECONDS = 45
TELEGRAM_REQUEST_TIMEOUT_SECONDS = 60
RETRY_DELAY_SECONDS = 3

HELP_TEXT = (
    "Blox Fruits Stock Bot\n"
    "Use /stock to show both live stock lists, /normal or /mirage for one list, "
    "or use the buttons below. Refresh fetches the API again."
)
STOCK_UNAVAILABLE_TEXT = (
    "Current stock is unavailable. The public API did not return verified fruit "
    "names and prices, so I did not show any stock data. Please try Refresh again later."
)

LOGGER = logging.getLogger("blox_fruits_stock_bot")


class TelegramApiError(Exception):
    """A Telegram API error with no request URL or bot token in its message."""



def inline_keyboard(language: str = "en", include_language: bool = False) -> dict:
    rows = [
        [
            {"text": get_text(language, "normal"), "callback_data": "normal"},
            {"text": get_text(language, "mirage"), "callback_data": "mirage"},
        ],
        [{"text": get_text(language, "refresh"), "callback_data": "refresh"}],
    ]
    if include_language:
        rows.append([{
            "text": "🍎 Выбрать фрукты" if language == "ru" else "🍎 Choose fruits",
            "callback_data": "fruits:open",
        }])
        rows.append([{
            "text": get_text(language, "language"),
            "callback_data": "lang",
        }])
    return {"inline_keyboard": rows}

def telegram_request(
    token: str,
    method: str,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> Any:
    url = f"{TELEGRAM_API_URL}/bot{token}/{method}"
    request_body: bytes | None = None
    headers = {"Accept": "application/json"}

    if query is not None:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    if body is not None:
        request_body = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=request_body, headers=headers)
    try:
        with urllib.request.urlopen(
            request, timeout=TELEGRAM_REQUEST_TIMEOUT_SECONDS
        ) as response:
            raw_response = response.read()
    except urllib.error.HTTPError as error:
        raise TelegramApiError(
            f"Telegram {method} failed with HTTP {error.code}."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TelegramApiError(f"Could not reach Telegram while calling {method}.") from None

    try:
        result = json.loads(raw_response)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        raise TelegramApiError(f"Telegram returned an invalid response to {method}.") from None

    if not isinstance(result, dict) or not result.get("ok"):
        error_code = result.get("error_code") if isinstance(result, dict) else None
        if error_code == 401:
            raise TelegramApiError("Telegram rejected the bot token (HTTP 401).")
        raise TelegramApiError(f"Telegram rejected the {method} request.")

    return result.get("result")


FRUIT_NAMES_RU = {
    "Rocket": "Ракета",
    "Spin": "Спин",
    "Chop": "Чоп",
    "Spring": "Пружина",
    "Bomb": "Бомба",
    "Smoke": "Дым",
    "Spike": "Шип",
    "Flame": "Пламя",
    "Falcon": "Сокол",
    "Ice": "Лёд",
    "Sand": "Песок",
    "Dark": "Тьма",
    "Diamond": "Алмаз",
    "Light": "Свет",
    "Rubber": "Резина",
    "Barrier": "Барьер",
    "Ghost": "Призрак",
    "Magma": "Магма",
    "Quake": "Дрожь",
    "Buddha": "Будда",
    "Love": "Любовь",
    "Spider": "Паук",
    "Sound": "Звук",
    "Phoenix": "Феникс",
    "Portal": "Портал",
    "Rumble": "Грохот",
    "Pain": "Боль",
    "Blizzard": "Метель",
    "Gravity": "Гравитация",
    "Mammoth": "Мамонт",
    "T-Rex": "Ти-Рекс",
    "Dough": "Тесто",
    "Shadow": "Тень",
    "Venom": "Яд",
    "Control": "Контроль",
    "Spirit": "Дух",
    "Dragon": "Дракон",
    "Leopard": "Леопард",
    "Kitsune": "Лисица",
    "Yeti": "Йети",
    "Gas": "Газ",
}


SUBSCRIPTIONS_FILE = os.path.join(os.path.dirname(__file__), "fruit_subscriptions.json")


def load_subscriptions() -> dict:
    try:
        with open(SUBSCRIPTIONS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_subscriptions(data: dict) -> None:
    temp = SUBSCRIPTIONS_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp, SUBSCRIPTIONS_FILE)


def fruit_label(name: str, language: str) -> str:
    translated = FRUIT_NAMES_RU.get(name)
    if language == "ru" and translated:
        return f"{name} ({translated})"
    return name


def fruit_selection_keyboard(chat_id: int, language: str) -> dict:
    subscriptions = load_subscriptions()
    selected = set(subscriptions.get(str(chat_id), []))
    fruits = sorted(FRUIT_NAMES_RU.keys())
    rows = []
    for i in range(0, len(fruits), 2):
        row = []
        for name in fruits[i:i + 2]:
            mark = "✅ " if name in selected else ""
            row.append({
                "text": mark + fruit_label(name, language),
                "callback_data": "fruit:" + name,
            })
        rows.append(row)
    rows.append([{
        "text": "Готово" if language == "ru" else "Done",
        "callback_data": "fruits:done",
    }])
    return {"inline_keyboard": rows}


def fruit_selection_text(chat_id: int, language: str) -> str:
    selected = load_subscriptions().get(str(chat_id), [])
    if language == "ru":
        if not selected:
            return "🍎 Выбери фрукты для уведомлений. Нажми на фрукт, чтобы отметить его галочкой."
        return "🍎 Выбери фрукты для уведомлений.\nОтмечено: " + ", ".join(
            fruit_label(x, language) for x in selected
        )
    if not selected:
        return "🍎 Choose fruits to get alerts. Tap a fruit to select it."
    return "🍎 Choose fruits to get alerts.\nSelected: " + ", ".join(selected)


def check_stock_alerts(token: str, previous: set | None) -> set | None:
    api_url = os.environ.get("STOCK_API_URL", DEFAULT_STOCK_API_URL).strip()
    try:
        snapshot = fetch_stock(api_url)
    except StockApiError as error:
        LOGGER.warning("Could not check fruit alerts: %s", error)
        return previous

    current = set()
    for fruit in snapshot.normal:
        current.add((fruit.name, "normal"))
    for fruit in snapshot.mirage:
        current.add((fruit.name, "mirage"))

    # The first check establishes a baseline and avoids a flood of old alerts.
    if previous is not None:
        subscriptions = load_subscriptions()
        for chat_id, names in subscriptions.items():
            try:
                numeric_chat_id = int(chat_id)
            except (TypeError, ValueError):
                continue
            language = get_language(numeric_chat_id)
            for name in names if isinstance(names, list) else []:
                appeared = [(fruit, area) for fruit, area in current
                            if fruit == name and (fruit, area) not in previous]
                for fruit, area in appeared:
                    if language == "ru":
                        area_text = "Normal Stock" if area == "normal" else "Mirage Stock"
                        message = f"🔔 Твой фрукт появился в стоке!\n🍎 {fruit_label(fruit, language)}\n📦 {area_text}"
                    else:
                        area_text = "Normal Stock" if area == "normal" else "Mirage Stock"
                        message = f"🔔 Your selected fruit is in stock!\n🍎 {fruit}\n📦 {area_text}"
                    try:
                        send_message(token, numeric_chat_id, message, language)
                    except TelegramApiError as error:
                        LOGGER.warning("Could not send fruit alert: %s", error)
    return current


def format_fruit(fruit: FruitStock, language: str = "en") -> str:
    name = fruit.name
    if language == "ru":
        translated = FRUIT_NAMES_RU.get(name)
        if translated:
            name = f"{name} ({translated})"
    return f"• {name} — {fruit.beli:,} Beli"



def format_stock(snapshot: StockSnapshot, view: str = "all", language: str = "en") -> str:
    lines = [get_text(language, "title")]
    sections = []
    if view in ("all", "normal"):
        sections.append((get_text(language, "normal"), snapshot.normal))
    if view in ("all", "mirage"):
        sections.append((get_text(language, "mirage"), snapshot.mirage))
    for title, fruits in sections:
        lines.extend(["", title])
        lines.extend(format_fruit(fruit, language) for fruit in fruits)
    if snapshot.last_updated:
        updated = snapshot.last_updated.strftime("%d %b %Y, %H:%M UTC")
        lines.extend(["", f"{get_text(language, 'updated')}: {updated}"])
    lines.extend(["", f"{get_text(language, 'source')}: {STOCK_SOURCE_URL}"])
    return "\n".join(lines)


def show_stock(view: str, language: str = "en") -> str:
    api_url = os.environ.get("STOCK_API_URL", DEFAULT_STOCK_API_URL).strip()
    try:
        snapshot = fetch_stock(api_url)
    except StockApiError as error:
        LOGGER.warning("Stock data unavailable: %s", error)
        return get_text(language, "unavailable")
    return format_stock(snapshot, view=view, language=language)


def send_message(token: str, chat_id: int, text: str, language: str = "en",
                 reply_markup: dict | None = None) -> None:
    telegram_request(
        token, "sendMessage",
        body={
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup or inline_keyboard(language, include_language=True),
            "disable_web_page_preview": True,
        },
    )


def edit_message(token: str, query: dict, text: str, language: str = "en",
                 reply_markup: dict | None = None) -> None:
    message = query.get("message")
    if not isinstance(message, dict) or "message_id" not in message:
        return
    telegram_request(
        token, "editMessageText",
        body={
            "chat_id": message["chat"]["id"],
            "message_id": message["message_id"],
            "text": text,
            "reply_markup": reply_markup or inline_keyboard(language, include_language=True),
            "disable_web_page_preview": True,
        },
    )


def handle_message(token: str, message: dict) -> None:
    text = message.get("text")
    chat = message.get("chat")
    if not isinstance(text, str) or not isinstance(chat, dict):
        return

    chat_id = chat["id"]
    command = text.strip().split(maxsplit=1)[0].split("@", maxsplit=1)[0].lower()
    language = get_language(chat_id)

    if command in ("/language", "/lang"):
        send_message(token, chat_id, get_text(language, "choose"),
                     language, language_keyboard())
        return

    if command == "/start" and language != "ru" and language != "en":
        send_message(token, chat_id, get_text("en", "choose"),
                     "en", language_keyboard())
        return

    if command == "/start":
        # Show language selection to new users.
        import json
        from pathlib import Path
        try:
            with open(Path(__file__).resolve().parent / "user_languages.json", encoding="utf-8") as f:
                user_languages = json.load(f)
        except (OSError, json.JSONDecodeError):
            user_languages = {}
        if not isinstance(user_languages, dict) or str(chat_id) not in user_languages:
            send_message(token, chat_id, get_text("en", "choose"),
                         "en", language_keyboard())
            return

    views = {
        "/start": "all", "/stock": "all", "/refresh": "all",
        "/normal": "normal", "/mirage": "mirage",
    }
    view = views.get(command)
    if view is None:
        send_message(token, chat_id, get_text(language, "help"), language)
        return
    send_message(token, chat_id, show_stock(view, language), language)


def handle_callback(token: str, query: dict) -> None:
    callback_id = query.get("id")
    action = query.get("data")
    message = query.get("message")
    if not isinstance(callback_id, str):
        return

    chat_id = message.get("chat", {}).get("id") if isinstance(message, dict) else None
    language = get_language(chat_id) if chat_id is not None else "en"

    try:
        telegram_request(
            token, "answerCallbackQuery",
            body={"callback_query_id": callback_id, "text": get_text(language, "loading")},
        )
    except TelegramApiError as error:
        LOGGER.warning("%s", error)

    if chat_id is not None and action == "fruits:open":
        edit_message(
            token, query, fruit_selection_text(chat_id, language), language,
            fruit_selection_keyboard(chat_id, language),
        )
        return

    if chat_id is not None and isinstance(action, str) and action.startswith("fruit:"):
        name = action.split(":", 1)[1]
        if name in FRUIT_NAMES_RU:
            subscriptions = load_subscriptions()
            key = str(chat_id)
            selected = subscriptions.get(key, [])
            if not isinstance(selected, list):
                selected = []
            if name in selected:
                selected.remove(name)
            else:
                selected.append(name)
            subscriptions[key] = selected
            save_subscriptions(subscriptions)
            edit_message(
                token, query, fruit_selection_text(chat_id, language), language,
                fruit_selection_keyboard(chat_id, language),
            )
        return

    if chat_id is not None and action == "fruits:done":
        edit_message(
            token, query,
            show_stock("all", language),
            language,
            inline_keyboard(language, include_language=True),
        )
        return

    if action == "lang":
        edit_message(token, query, get_text(language, "choose"),
                     language, language_keyboard())
        return

    if action in ("setlang:ru", "setlang:en") and chat_id is not None:
        language = action.split(":", 1)[1]
        save_language(chat_id, language)
        edit_message(token, query, show_stock("all", language), language)
        return

    view = action if action in ("normal", "mirage") else "all"
    try:
        edit_message(token, query, show_stock(view, language), language)
    except TelegramApiError as error:
        if "message is not modified" not in str(error).lower():
            LOGGER.warning("%s", error)

def process_update(token: str, update: dict[str, Any]) -> None:
    message = update.get("message")
    if isinstance(message, dict):
        handle_message(token, message)
        return

    callback = update.get("callback_query")
    if isinstance(callback, dict):
        handle_callback(token, callback)


def run_bot(token: str) -> None:
    bot_info = telegram_request(token, "getMe")
    username = bot_info.get("username", "unknown") if isinstance(bot_info, dict) else "unknown"
    LOGGER.info("Connected to Telegram as @%s. Press Ctrl+C to stop.", username)

    offset: int | None = None
    last_stock_state = None
    next_stock_check = time.monotonic()
    while True:
        query: dict[str, Any] = {
            "timeout": TELEGRAM_LONG_POLL_SECONDS,
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }
        if offset is not None:
            query["offset"] = offset

        try:
            updates = telegram_request(token, "getUpdates", query=query)
            if not isinstance(updates, list):
                raise TelegramApiError("Telegram returned an invalid updates list.")

            for update in updates:
                if not isinstance(update, dict):
                    continue
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                try:
                    process_update(token, update)
                except TelegramApiError as error:
                    LOGGER.warning("%s", error)

            if time.monotonic() >= next_stock_check:
                last_stock_state = check_stock_alerts(token, last_stock_state)
                next_stock_check = time.monotonic() + 60
        except TelegramApiError as error:
            if "HTTP 401" in str(error):
                LOGGER.error(
                    "Telegram rejected TELEGRAM_BOT_TOKEN. Check it with BotFather and restart."
                )
                raise SystemExit(1) from None
            LOGGER.warning("%s Retrying in %s seconds.", error, RETRY_DELAY_SECONDS)
            time.sleep(RETRY_DELAY_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        LOGGER.error(
            "TELEGRAM_BOT_TOKEN is not set. See README.md for secure setup instructions."
        )
        raise SystemExit(2)

    try:
        run_bot(token)
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped.")


if __name__ == "__main__":
    main()

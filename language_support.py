import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TRANSLATIONS_FILE = BASE_DIR / "languages.json"
PREFERENCES_FILE = BASE_DIR / "user_languages.json"


def load_translations():
    with open(TRANSLATIONS_FILE, encoding="utf-8") as file:
        return json.load(file)


def get_language(chat_id):
    try:
        with open(PREFERENCES_FILE, encoding="utf-8") as file:
            preferences = json.load(file)
        language = preferences.get(str(chat_id), "en")
        return language if language in ("ru", "en") else "en"
    except (OSError, json.JSONDecodeError):
        return "en"


def save_language(chat_id, language):
    if language not in ("ru", "en"):
        return

    try:
        with open(PREFERENCES_FILE, encoding="utf-8") as file:
            preferences = json.load(file)
        if not isinstance(preferences, dict):
            preferences = {}
    except (OSError, json.JSONDecodeError):
        preferences = {}

    preferences[str(chat_id)] = language
    temp_file = PREFERENCES_FILE.with_suffix(".tmp")

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(preferences, file, ensure_ascii=False, indent=2)

    temp_file.replace(PREFERENCES_FILE)


def get_text(language, key):
    translations = load_translations()
    return translations.get(language, translations["en"]).get(
        key, translations["en"].get(key, key)
    )


def language_keyboard():
    return {
        "inline_keyboard": [[
            {"text": "🇷🇺 Русский", "callback_data": "setlang:ru"},
            {"text": "🇬🇧 English", "callback_data": "setlang:en"}
        ]]
    }

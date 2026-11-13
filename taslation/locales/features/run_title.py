"""The window's title while a whole-book run reads the pages and while it writes the notes (`ui.banner.busy_title`):
nothing is translated in those passes, so the title does not say "translating" then. Worded as the title that says
"translating..." is in each language."""

TEXTS: dict[str, dict[str, str]] = {
    "TASlation - reading...": {
        "ja": "TASlation - 読み取り中...",
        "es": "TASlation - leyendo...",
        "pt": "TASlation - lendo...",
        "fr": "TASlation - lecture...",
        "de": "TASlation - wird gelesen...",
        "it": "TASlation - lettura...",
        "nl": "TASlation - lezen...",
        "pl": "TASlation - czytanie...",
        "ru": "TASlation - чтение...",
        "tr": "TASlation - okunuyor...",
        "id": "TASlation - membaca...",
        "vi": "TASlation - đang đọc...",
        "zh": "TASlation - 正在读取...",
        "zh-tw": "TASlation - 正在讀取...",
        "ko": "TASlation - 읽는 중...",
        "th": "TASlation - กำลังอ่าน...",
    },
}

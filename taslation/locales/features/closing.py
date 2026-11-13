"""The buttons of the question at closing while pages of a run are not finished (`ui.app._close_allowed`): TASlation's
own box, so that its buttons are in the window's language (a system box takes Windows' language), each saying what
it does. Worded after the question's last line in each language ("Close anyway?")."""

TEXTS: dict[str, dict[str, str]] = {
    "Close anyway": {
        "ja": "それでも閉じる",
        "es": "Cerrar de todos modos",
        "pt": "Fechar mesmo assim",
        "fr": "Fermer quand même",
        "de": "Trotzdem schließen",
        "it": "Chiudi comunque",
        "nl": "Toch sluiten",
        "pl": "Zamknij mimo to",
        "ru": "Всё равно закрыть",
        "tr": "Yine de kapat",
        "id": "Tetap tutup",
        "vi": "Vẫn đóng",
        "zh": "仍然关闭",
        "zh-tw": "仍然關閉",
        "ko": "그래도 닫기",
        "th": "ปิดเลย",
    },
    "Keep TASlation open": {
        "ja": "TASlation を開いたままにする",
        "es": "Mantener TASlation abierto",
        "pt": "Manter o TASlation aberto",
        "fr": "Garder TASlation ouvert",
        "de": "TASlation geöffnet lassen",
        "it": "Tieni aperto TASlation",
        "nl": "TASlation open laten",
        "pl": "Zostaw TASlation otwarty",
        "ru": "Оставить TASlation открытым",
        "tr": "TASlation açık kalsın",
        "id": "Biarkan TASlation terbuka",
        "vi": "Giữ TASlation mở",
        "zh": "保持 TASlation 打开",
        "zh-tw": "保持 TASlation 開啟",
        "ko": "TASlation 열어 두기",
        "th": "เปิด TASlation ไว้",
    },
}

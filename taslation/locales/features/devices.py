"""The window's strings for where the models load: the status line while Ollama's model is loaded at the start,
before the OCR model (what loaded where is said with the message catalogs: ``ocr.device``, ``ollama.loaded``)."""

TEXTS: dict[str, dict[str, str]] = {
    "Getting the translator ready...": {
        "ja": "翻訳の準備をしています...",
        "es": "Preparando el traductor...",
        "pt": "Preparando o tradutor...",
        "fr": "Préparation du traducteur...",
        "de": "Übersetzer wird vorbereitet...",
        "it": "Preparazione del traduttore...",
        "nl": "De vertaler wordt klaargezet...",
        "pl": "Przygotowywanie tłumacza...",
        "ru": "Подготовка переводчика...",
        "tr": "Çevirici hazırlanıyor...",
        "id": "Menyiapkan penerjemah...",
        "vi": "Đang chuẩn bị bộ dịch...",
        "zh": "正在准备翻译...",
        "zh-tw": "正在準備翻譯...",
        "ko": "번역을 준비하는 중...",
        "th": "กำลังเตรียมการแปล...",
    },
}

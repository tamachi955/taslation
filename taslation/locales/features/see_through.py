"""The window's strings for see-through mode's side panes (`ui.seethrough`, a prototype behind ``see_through``): the
controls left of the page (Stop while a page is translated, the lettering's switch with its key, the indicators'
switch, the way back to TASlation's own window) and the indicators right of it (how far the page on show is, where the
translator runs). The other words of the panes are the window's own (Translate, Auto, Set area..., Settings..., Quit,
the status line, the indicator's lines). "Lettering" is worded as in the window's other strings (ja 「写植」), the
processor as in the System page's (ja 「CPU」).

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "Stop": {
        "ja": "停止", "es": "Detener", "pt": "Parar", "fr": "Arrêter", "de": "Stopp", "it": "Ferma", "nl": "Stop",
        "pl": "Stop", "ru": "Стоп", "tr": "Durdur", "id": "Hentikan", "vi": "Dừng", "zh": "停止", "zh-tw": "停止",
        "ko": "중지", "th": "หยุด",
    },
    "Lettering (F9)": {
        "ja": "写植 (F9)", "es": "Rotulado (F9)", "pt": "Letreiramento (F9)", "fr": "Lettrage (F9)",
        "de": "Beschriftung (F9)", "it": "Lettering (F9)", "nl": "Belettering (F9)", "pl": "Liternictwo (F9)",
        "ru": "Надписи (F9)", "tr": "Yazı (F9)", "id": "Huruf (F9)", "vi": "Chữ (F9)", "zh": "文字排版 (F9)",
        "zh-tw": "文字排版 (F9)", "ko": "글자 (F9)", "th": "การลงตัวอักษร (F9)",
    },
    "Indicators": {
        "ja": "インジケーター", "es": "Indicadores", "pt": "Indicadores", "fr": "Indicateurs", "de": "Anzeigen",
        "it": "Indicatori", "nl": "Indicatoren", "pl": "Wskaźniki", "ru": "Индикаторы", "tr": "Göstergeler",
        "id": "Indikator", "vi": "Chỉ báo", "zh": "指示器", "zh-tw": "指示器", "ko": "표시기", "th": "ตัวบ่งชี้",
    },
    "TASlation window": {
        "ja": "TASlation のウィンドウ", "es": "Ventana de TASlation", "pt": "Janela do TASlation",
        "fr": "Fenêtre de TASlation", "de": "TASlation-Fenster", "it": "Finestra di TASlation",
        "nl": "TASlation-venster", "pl": "Okno TASlation", "ru": "Окно TASlation", "tr": "TASlation penceresi",
        "id": "Jendela TASlation", "vi": "Cửa sổ TASlation", "zh": "TASlation 窗口", "zh-tw": "TASlation 視窗",
        "ko": "TASlation 창", "th": "หน้าต่าง TASlation",
    },
    "This page: {done} of {total} lines": {
        "ja": "このページ: {total} 行中 {done} 行",
        "es": "Esta página: {done} de {total} líneas",
        "pt": "Esta página: {done} de {total} linhas",
        "fr": "Cette page : {done} lignes sur {total}",
        "de": "Diese Seite: {done} von {total} Zeilen",
        "it": "Questa pagina: {done} di {total} righe",
        "nl": "Deze pagina: {done} van {total} regels",
        "pl": "Ta strona: {done} z {total} linii",
        "ru": "Эта страница: {done} из {total} строк",
        "tr": "Bu sayfa: {total} satırdan {done}",
        "id": "Halaman ini: {done} dari {total} baris",
        "vi": "Trang này: {done}/{total} dòng",
        "zh": "本页：{total} 行中的 {done} 行",
        "zh-tw": "本頁：{total} 行中的 {done} 行",
        "ko": "이 페이지: {total}줄 중 {done}줄",
        "th": "หน้านี้: {done} จาก {total} บรรทัด",
    },
    "Translator: on the GPU": {
        "ja": "翻訳: GPU", "es": "Traductor: en la GPU", "pt": "Tradutor: na GPU", "fr": "Traducteur : sur le GPU",
        "de": "Übersetzer: auf der GPU", "it": "Traduttore: sulla GPU", "nl": "Vertaler: op de GPU",
        "pl": "Tłumacz: na GPU", "ru": "Переводчик: на GPU", "tr": "Çevirmen: GPU'da", "id": "Penerjemah: di GPU",
        "vi": "Bộ dịch: trên GPU", "zh": "翻译：在 GPU 上", "zh-tw": "翻譯：在 GPU 上", "ko": "번역기: GPU",
        "th": "ตัวแปล: บน GPU",
    },
    "Translator: on the processor": {
        "ja": "翻訳: CPU", "es": "Traductor: en el procesador", "pt": "Tradutor: no processador",
        "fr": "Traducteur : sur le processeur", "de": "Übersetzer: auf dem Prozessor",
        "it": "Traduttore: sul processore", "nl": "Vertaler: op de processor", "pl": "Tłumacz: na procesorze",
        "ru": "Переводчик: на процессоре", "tr": "Çevirmen: işlemcide", "id": "Penerjemah: di prosesor",
        "vi": "Bộ dịch: trên bộ xử lý", "zh": "翻译：在处理器上", "zh-tw": "翻譯：在處理器上", "ko": "번역기: 프로세서",
        "th": "ตัวแปล: บนโปรเซสเซอร์",
    },
}

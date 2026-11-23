"""The window's strings for see-through mode's side panes (`ui.seethrough`, a prototype behind ``see_through``): the
controls left of the page (Stop while a page is translated, the indicators' switch, the Menu row and the two entries
of its menu that stand in for the toolbar of TASlation's own window, which this mode never shows: the viewer chooser
and the book's Series and Volume) and the indicators right of it (how far the page on show is, where the translator
runs). The other words of the panes and of the menu are the window's own (Translate, Auto, Lettering - the Settings
dialog's, ja 「写植」 -, Set area..., Settings..., Quit, the status line, the indicator's lines, the menu's entries);
the processor is worded as in the System page's (ja 「CPU」); the viewer as in the toolbar's "Viewer:" (ja 「ビューア」),
the book's two fields as in their labels (ja 「シリーズ」「巻」).

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "Stop": {
        "ja": "停止", "es": "Detener", "pt": "Parar", "fr": "Arrêter", "de": "Stopp", "it": "Ferma", "nl": "Stop",
        "pl": "Stop", "ru": "Стоп", "tr": "Durdur", "id": "Hentikan", "vi": "Dừng", "zh": "停止", "zh-tw": "停止",
        "ko": "중지", "th": "หยุด",
    },
    "Indicators": {
        "ja": "インジケーター", "es": "Indicadores", "pt": "Indicadores", "fr": "Indicateurs", "de": "Anzeigen",
        "it": "Indicatori", "nl": "Indicatoren", "pl": "Wskaźniki", "ru": "Индикаторы", "tr": "Göstergeler",
        "id": "Indikator", "vi": "Chỉ báo", "zh": "指示器", "zh-tw": "指示器", "ko": "표시기", "th": "ตัวบ่งชี้",
    },
    "Menu": {
        "ja": "メニュー", "es": "Menú", "pt": "Menu", "fr": "Menu", "de": "Menü", "it": "Menu", "nl": "Menu",
        "pl": "Menu", "ru": "Меню", "tr": "Menü", "id": "Menu", "vi": "Menu", "zh": "菜单", "zh-tw": "選單",
        "ko": "메뉴", "th": "เมนู",
    },
    "Viewer...": {
        "ja": "ビューア...", "es": "Visor...", "pt": "Visualizador...", "fr": "Visionneuse...", "de": "Viewer...",
        "it": "Visualizzatore...", "nl": "Viewer...", "pl": "Czytnik...", "ru": "Просмотрщик...",
        "tr": "Görüntüleyici...", "id": "Penampil...", "vi": "Trình xem...", "zh": "查看器...", "zh-tw": "檢視器...",
        "ko": "뷰어...", "th": "โปรแกรมอ่าน...",
    },
    "Series and Volume...": {
        "ja": "シリーズと巻...", "es": "Serie y tomo...", "pt": "Série e volume...", "fr": "Série et tome...",
        "de": "Serie und Band...", "it": "Serie e volume...", "nl": "Serie en deel...", "pl": "Seria i tom...",
        "ru": "Серия и том...", "tr": "Seri ve cilt...", "id": "Seri dan volume...", "vi": "Bộ truyện và tập...",
        "zh": "系列与卷...", "zh-tw": "系列與卷...", "ko": "시리즈와 권...", "th": "ซีรีส์และเล่ม...",
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

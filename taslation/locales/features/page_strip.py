"""The window's strings for a page's stages as the indicator beside the page tells them (`ui.side_model`): the stage
letters and names, the states of a stage, a page that went by before it could be taken; and the role a book opens in
(`ui.translator`, `start_role`). (The file is named after the whole-book run's page strip, whose strings these were
first.)"""

TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ the stages: a letter each, and a name
    "E": {
        "ja": "消", "es": "B", "pt": "A", "fr": "E", "de": "E", "it": "C", "nl": "W", "pl": "U", "ru": "С", "tr": "S",
        "id": "H", "vi": "X", "zh": "擦", "zh-tw": "擦", "ko": "지", "th": "ล",
    },
    "T": {
        "ja": "訳", "es": "T", "pt": "T", "fr": "T", "de": "Ü", "it": "T", "nl": "V", "pl": "T", "ru": "П", "tr": "Ç",
        "id": "T", "vi": "B", "zh": "译", "zh-tw": "譯", "ko": "번", "th": "ป",
    },
    # ------------------------------------------------------------------ the state of a bar
    "done": {
        "ja": "完了", "es": "hecho", "pt": "feito", "fr": "terminé", "de": "fertig", "it": "fatto", "nl": "klaar",
        "pl": "gotowe", "ru": "готово", "tr": "bitti", "id": "selesai", "vi": "xong", "zh": "完成", "zh-tw": "完成",
        "ko": "완료", "th": "เสร็จแล้ว",
    },
    # ------------------------------------------------------------------ the role a book opens in
    "This book has no translations yet, so it opens in translator mode.": {
        "ja": "この本にはまだ翻訳がないため、翻訳者モードで開きます。",
        "es": "Este libro aún no tiene traducciones, así que se abre en el modo traductor.",
        "pt": "Este livro ainda não tem traduções, então abre no modo tradutor.",
        "fr": "Ce livre n'a pas encore de traductions : il s'ouvre en mode traducteur.",
        "de": "Dieses Buch hat noch keine Übersetzungen, darum öffnet es im Übersetzermodus.",
        "it": "Questo libro non ha ancora traduzioni, quindi si apre in modalità traduttore.",
        "nl": "Dit boek heeft nog geen vertalingen, dus het opent in de vertalersmodus.",
        "pl": "Ta książka nie ma jeszcze tłumaczeń, więc otwiera się w trybie tłumacza.",
        "ru": "У этой книги ещё нет переводов, поэтому она открывается в режиме переводчика.",
        "tr": "Bu kitabın henüz çevirisi yok, bu yüzden çevirmen modunda açılıyor.",
        "id": "Buku ini belum punya terjemahan, jadi dibuka dalam mode penerjemah.",
        "vi": "Cuốn sách này chưa có bản dịch nên được mở ở chế độ người dịch.",
        "zh": "这本书还没有译文，因此以译者模式打开。",
        "zh-tw": "這本書還沒有譯文，因此以譯者模式開啟。",
        "ko": "이 책에는 아직 번역이 없어 번역자 모드로 엽니다.",
        "th": "หนังสือเล่มนี้ยังไม่มีคำแปล จึงเปิดในโหมดผู้แปล",
    },
    "This book's pages are translated, so it opens in reader mode.": {
        "ja": "この本のページは翻訳済みのため、読者モードで開きます。",
        "es": "Las páginas de este libro están traducidas, así que se abre en el modo lector.",
        "pt": "As páginas deste livro estão traduzidas, então abre no modo leitor.",
        "fr": "Les pages de ce livre sont traduites : il s'ouvre en mode lecteur.",
        "de": "Die Seiten dieses Buchs sind übersetzt, darum öffnet es im Lesermodus.",
        "it": "Le pagine di questo libro sono tradotte, quindi si apre in modalità lettore.",
        "nl": "De pagina's van dit boek zijn vertaald, dus het opent in de lezersmodus.",
        "pl": "Strony tej książki są przetłumaczone, więc otwiera się w trybie czytelnika.",
        "ru": "Страницы этой книги переведены, поэтому она открывается в режиме читателя.",
        "tr": "Bu kitabın sayfaları çevrildi, bu yüzden okuyucu modunda açılıyor.",
        "id": "Halaman buku ini sudah diterjemahkan, jadi dibuka dalam mode pembaca.",
        "vi": "Các trang của cuốn sách này đã được dịch nên được mở ở chế độ người đọc.",
        "zh": "这本书的页面已翻译，因此以读者模式打开。",
        "zh-tw": "這本書的頁面已翻譯，因此以讀者模式開啟。",
        "ko": "이 책의 페이지는 번역되어 있어 독자 모드로 엽니다.",
        "th": "หน้าของหนังสือเล่มนี้แปลแล้ว จึงเปิดในโหมดผู้อ่าน",
    },
    # ------------------------------------------------------------------ a page that went by before it was taken
}

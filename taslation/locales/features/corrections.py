"""The window's strings for a person's corrections: the region editor's "Read as:" field, where a misreading of the
Japanese is corrected for the model (in memory only, never saved).

"Ask again" is worded as the editor's button is (ja 「もう一度訳す」, de „Noch einmal übersetzen“).

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ the reading, corrected in the editor
    "What was read here. Correct it where it was misread: Ask again then translates your reading, and so does this page translated again in this session. Your reading is never saved.": {
        "ja": "ここで読み取った日本語です。読み間違いがあれば直してください。「もう一度訳す」は直した読みを訳し、このセッション中にこのページを訳し直すときも同じです。直した読みは保存されません。",
        "es": "Lo que se leyó aquí. Corríjalo donde se leyó mal: «Traducir de nuevo» traduce entonces su lectura, igual que esta página traducida de nuevo en esta sesión. Su lectura nunca se guarda.",
        "pt": "O que foi lido aqui. Corrija onde foi lido errado: «Traduzir de novo» traduz então a sua leitura, assim como esta página traduzida de novo nesta sessão. A sua leitura nunca é guardada.",
        "fr": "Ce qui a été lu ici. Corrigez-le là où il a été mal lu : « Retraduire » traduit alors votre lecture, tout comme cette page retraduite pendant cette session. Votre lecture n'est jamais enregistrée.",
        "de": "Was hier gelesen wurde. Korrigieren Sie es, wo es falsch gelesen wurde: „Noch einmal übersetzen“ übersetzt dann Ihre Lesung, ebenso diese Seite, wenn sie in dieser Sitzung neu übersetzt wird. Ihre Lesung wird nie gespeichert.",
        "it": "Ciò che è stato letto qui. Correggilo dove è stato letto male: «Traduci di nuovo» traduce allora la tua lettura, come anche questa pagina tradotta di nuovo in questa sessione. La tua lettura non viene mai salvata.",
        "nl": "Wat hier gelezen is. Verbeter het waar het verkeerd gelezen is: 'Opnieuw vertalen' vertaalt dan uw lezing, net als deze pagina opnieuw vertaald in deze sessie. Uw lezing wordt nooit bewaard.",
        "pl": "To, co tu odczytano. Popraw tam, gdzie odczytano źle: „Przetłumacz ponownie” przetłumaczy wtedy twój odczyt, tak samo jak ta strona przetłumaczona ponownie w tej sesji. Twój odczyt nigdy nie jest zapisywany.",
        "ru": "То, что здесь прочитано. Исправьте, где прочитано неверно: «Перевести снова» переведёт ваше прочтение, как и эта страница, переведённая заново в этом сеансе. Ваше прочтение никогда не сохраняется.",
        "tr": "Burada okunan. Yanlış okunduğu yerde düzeltin: «Yeniden çevir» o zaman sizin okumanızı çevirir, bu oturumda yeniden çevrilen bu sayfa da öyle. Okumanız asla kaydedilmez.",
        "id": "Yang terbaca di sini. Perbaiki di bagian yang salah baca: \"Terjemahkan lagi\" lalu menerjemahkan bacaan Anda, begitu pula halaman ini bila diterjemahkan ulang di sesi ini. Bacaan Anda tidak pernah disimpan.",
        "vi": "Những gì đã đọc được ở đây. Hãy sửa chỗ đọc sai: khi đó \"Dịch lại\" sẽ dịch cách đọc của bạn, trang này khi dịch lại trong phiên này cũng vậy. Cách đọc của bạn không bao giờ được lưu.",
        "zh": "这里读到的日语。读错的地方请改正：“重新翻译”会翻译你改正后的读法，本次会话中重新翻译此页时也一样。你的读法从不保存。",
        "zh-tw": "這裡讀到的日語。讀錯的地方請改正：「重新翻譯」會翻譯你改正後的讀法，本次工作階段中重新翻譯此頁時也一樣。你的讀法從不儲存。",
        "ko": "여기서 읽은 일본어입니다. 잘못 읽은 곳을 고치세요. 그러면 '다시 번역'이 고친 읽기를 번역하며, 이번 세션에서 이 페이지를 다시 번역할 때도 마찬가지입니다. 고친 읽기는 저장되지 않습니다.",
        "th": "สิ่งที่อ่านได้ตรงนี้ แก้ไขตรงที่อ่านผิด แล้ว \"ถามอีกครั้ง\" จะแปลคำอ่านของคุณ เช่นเดียวกับเมื่อแปลหน้านี้ใหม่ในเซสชันนี้ คำอ่านของคุณจะไม่ถูกบันทึก",
    },
}

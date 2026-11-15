"""The window's strings for going from bubble to bubble without the pointer (`ui.bubble_text`): the actions of the
keys that pin a bubble's panel on the next or the previous bubble of the page, and the status lines they say. Worded
as `bubble_panel`'s (ja 「吹き出し」, de „Sprechblase“, zh-tw 「對話框」, ko '말풍선').

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ the actions (`ui.shortcuts`)
    "Show the Japanese of the next bubble, to select and copy": {
        "ja": "次の吹き出しの日本語を表示（選択・コピー用）",
        "es": "Mostrar el japonés del globo siguiente, para seleccionar y copiar",
        "pt": "Mostrar o japonês do próximo balão, para selecionar e copiar",
        "fr": "Afficher le japonais de la bulle suivante, à sélectionner et copier",
        "de": "Das Japanisch der nächsten Sprechblase zeigen, zum Markieren und Kopieren",
        "it": "Mostra il giapponese del balloon successivo, da selezionare e copiare",
        "nl": "Het Japans van de volgende ballon tonen, om te selecteren en te kopiëren",
        "pl": "Pokaż japoński tekst następnego dymka do zaznaczenia i skopiowania",
        "ru": "Показать японский текст следующего пузыря, чтобы выделить и скопировать",
        "tr": "Sonraki balonun Japoncasını seçip kopyalamak için göster",
        "id": "Tampilkan bahasa Jepang balon berikutnya, untuk dipilih dan disalin",
        "vi": "Hiện chữ tiếng Nhật của bong bóng tiếp theo, để chọn và sao chép",
        "zh": "显示下一个气泡的日语原文，可选中并复制", "zh-tw": "顯示下一個對話框的日語原文，可選取並複製",
        "ko": "다음 말풍선의 일본어 원문 표시(선택·복사용)", "th": "แสดงข้อความภาษาญี่ปุ่นของลูกโป่งคำพูดถัดไป เพื่อเลือกและคัดลอก",
    },
    "Show the Japanese of the previous bubble, to select and copy": {
        "ja": "前の吹き出しの日本語を表示（選択・コピー用）",
        "es": "Mostrar el japonés del globo anterior, para seleccionar y copiar",
        "pt": "Mostrar o japonês do balão anterior, para selecionar e copiar",
        "fr": "Afficher le japonais de la bulle précédente, à sélectionner et copier",
        "de": "Das Japanisch der vorigen Sprechblase zeigen, zum Markieren und Kopieren",
        "it": "Mostra il giapponese del balloon precedente, da selezionare e copiare",
        "nl": "Het Japans van de vorige ballon tonen, om te selecteren en te kopiëren",
        "pl": "Pokaż japoński tekst poprzedniego dymka do zaznaczenia i skopiowania",
        "ru": "Показать японский текст предыдущего пузыря, чтобы выделить и скопировать",
        "tr": "Önceki balonun Japoncasını seçip kopyalamak için göster",
        "id": "Tampilkan bahasa Jepang balon sebelumnya, untuk dipilih dan disalin",
        "vi": "Hiện chữ tiếng Nhật của bong bóng trước đó, để chọn và sao chép",
        "zh": "显示上一个气泡的日语原文，可选中并复制", "zh-tw": "顯示上一個對話框的日語原文，可選取並複製",
        "ko": "이전 말풍선의 일본어 원문 표시(선택·복사용)", "th": "แสดงข้อความภาษาญี่ปุ่นของลูกโป่งคำพูดก่อนหน้า เพื่อเลือกและคัดลอก",
    },
    # ------------------------------------------------------------------ the status lines (`ui.bubble_text`)
    "Bubble {n} of {total}.": {
        "ja": "吹き出し {n}（全 {total} 個）。", "es": "Globo {n} de {total}.", "pt": "Balão {n} de {total}.",
        "fr": "Bulle {n} sur {total}.", "de": "Sprechblase {n} von {total}.", "it": "Balloon {n} di {total}.",
        "nl": "Ballon {n} van {total}.", "pl": "Dymek {n} z {total}.", "ru": "Пузырь {n} из {total}.",
        "tr": "Balon {n} / {total}.", "id": "Balon {n} dari {total}.", "vi": "Bong bóng {n} trên {total}.",
        "zh": "第 {n} 个气泡，共 {total} 个。", "zh-tw": "第 {n} 個對話框，共 {total} 個。",
        "ko": "{total}개 중 {n}번째 말풍선.", "th": "ลูกโป่งคำพูดที่ {n} จาก {total}",
    },
    "This is the first bubble of the page.": {
        "ja": "このページの最初の吹き出しです。", "es": "Es el primer globo de la página.",
        "pt": "Este é o primeiro balão da página.", "fr": "C'est la première bulle de la page.",
        "de": "Das ist die erste Sprechblase der Seite.", "it": "Questo è il primo balloon della pagina.",
        "nl": "Dit is de eerste ballon van de pagina.", "pl": "To pierwszy dymek na stronie.",
        "ru": "Это первый пузырь на странице.", "tr": "Bu, sayfanın ilk balonu.", "id": "Ini balon pertama di halaman.",
        "vi": "Đây là bong bóng đầu tiên của trang.", "zh": "这是本页的第一个气泡。", "zh-tw": "這是本頁的第一個對話框。",
        "ko": "이 페이지의 첫 말풍선입니다.", "th": "นี่คือลูกโป่งคำพูดแรกของหน้า",
    },
    "This is the last bubble of the page.": {
        "ja": "このページの最後の吹き出しです。", "es": "Es el último globo de la página.",
        "pt": "Este é o último balão da página.", "fr": "C'est la dernière bulle de la page.",
        "de": "Das ist die letzte Sprechblase der Seite.", "it": "Questo è l'ultimo balloon della pagina.",
        "nl": "Dit is de laatste ballon van de pagina.", "pl": "To ostatni dymek na stronie.",
        "ru": "Это последний пузырь на странице.", "tr": "Bu, sayfanın son balonu.", "id": "Ini balon terakhir di halaman.",
        "vi": "Đây là bong bóng cuối cùng của trang.", "zh": "这是本页的最后一个气泡。", "zh-tw": "這是本頁的最後一個對話框。",
        "ko": "이 페이지의 마지막 말풍선입니다.", "th": "นี่คือลูกโป่งคำพูดสุดท้ายของหน้า",
    },
    "The page on show has no bubble to go to.": {
        "ja": "表示中のページには、移動できる吹き出しがありません。",
        "es": "La página que se muestra no tiene ningún globo al que ir.",
        "pt": "A página exibida não tem nenhum balão para onde ir.", "fr": "La page affichée n'a aucune bulle où aller.",
        "de": "Auf der gezeigten Seite gibt es keine Sprechblase, zu der man gehen kann.",
        "it": "La pagina mostrata non ha alcun balloon a cui andare.",
        "nl": "De getoonde pagina heeft geen ballon om naartoe te gaan.",
        "pl": "Na wyświetlanej stronie nie ma dymka, do którego można przejść.",
        "ru": "На показанной странице нет пузырей, к которым можно перейти.", "tr": "Gösterilen sayfada gidilecek balon yok.",
        "id": "Halaman yang ditampilkan tidak punya balon untuk dituju.",
        "vi": "Trang đang hiện không có bong bóng nào để chuyển tới.", "zh": "当前显示的页面没有可以跳转的气泡。",
        "zh-tw": "目前顯示的頁面沒有可以跳轉的對話框。", "ko": "표시 중인 페이지에는 이동할 말풍선이 없습니다.",
        "th": "หน้าที่แสดงอยู่ไม่มีลูกโป่งคำพูดให้ไป",
    },
}

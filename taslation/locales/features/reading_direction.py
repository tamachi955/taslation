"""The window's strings for a book's reading direction in Book settings (`ui.dialogs.book_settings`): the row's label,
its two choices and its tip. "Clear all" is worded as the dialog's button (ja 「すべて消去」, de „Alles löschen“), the
bubbles as in the dialog's other choices (ja 「吹き出し」, fr « bulles », ko '말풍선').

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "Reading direction:": {
        "ja": "読む方向:", "es": "Sentido de lectura:", "pt": "Sentido de leitura:", "fr": "Sens de lecture :",
        "de": "Leserichtung:", "it": "Senso di lettura:", "nl": "Leesrichting:", "pl": "Kierunek czytania:",
        "ru": "Направление чтения:", "tr": "Okuma yönü:", "id": "Arah baca:", "vi": "Hướng đọc:",
        "zh": "阅读方向：", "zh-tw": "閱讀方向：", "ko": "읽는 방향:", "th": "ทิศทางการอ่าน:",
    },
    "Right to left (Japanese books)": {
        "ja": "右から左（日本の本）", "es": "De derecha a izquierda (libros japoneses)",
        "pt": "Da direita para a esquerda (livros japoneses)", "fr": "De droite à gauche (livres japonais)",
        "de": "Von rechts nach links (japanische Bücher)", "it": "Da destra a sinistra (libri giapponesi)",
        "nl": "Van rechts naar links (Japanse boeken)", "pl": "Od prawej do lewej (książki japońskie)",
        "ru": "Справа налево (японские книги)", "tr": "Sağdan sola (Japon kitapları)",
        "id": "Kanan ke kiri (buku Jepang)", "vi": "Phải sang trái (sách Nhật)", "zh": "从右到左（日本书籍）",
        "zh-tw": "從右到左（日本書籍）", "ko": "오른쪽에서 왼쪽 (일본 책)", "th": "ขวาไปซ้าย (หนังสือญี่ปุ่น)",
    },
    "Left to right": {
        "ja": "左から右", "es": "De izquierda a derecha", "pt": "Da esquerda para a direita", "fr": "De gauche à droite",
        "de": "Von links nach rechts", "it": "Da sinistra a destra", "nl": "Van links naar rechts",
        "pl": "Od lewej do prawej", "ru": "Слева направо", "tr": "Soldan sağa", "id": "Kiri ke kanan",
        "vi": "Trái sang phải", "zh": "从左到右", "zh-tw": "從左到右", "ko": "왼쪽에서 오른쪽", "th": "ซ้ายไปขวา",
    },
    "Which page of a two-page spread is read first, and the order of the bubbles on a page. Pages translated before keep their translations and take the new order when shown again. Clear all leaves it as it is.": {
        "ja": "見開きのどちらのページを先に読むか、またページ内の吹き出しの順番です。翻訳済みのページは訳文をそのまま残し、次に表示したときに新しい順番になります。「すべて消去」ではこの設定は変わりません。",
        "es": "Qué página de una doble página se lee primero, y el orden de los bocadillos en una página. Las páginas ya traducidas conservan sus traducciones y toman el nuevo orden cuando vuelven a mostrarse. Borrar todo no lo cambia.",
        "pt": "Qual página de uma página dupla é lida primeiro, e a ordem dos balões numa página. As páginas já traduzidas mantêm as traduções e passam à nova ordem quando forem mostradas de novo. Limpar tudo não o altera.",
        "fr": "Quelle page d'une double page se lit en premier, et l'ordre des bulles sur une page. Les pages déjà traduites gardent leurs traductions et prennent le nouvel ordre quand elles s'affichent de nouveau. Tout effacer ne le change pas.",
        "de": "Welche Seite einer Doppelseite zuerst gelesen wird, und die Reihenfolge der Sprechblasen auf einer Seite. Schon übersetzte Seiten behalten ihre Übersetzungen und bekommen die neue Reihenfolge, wenn sie wieder gezeigt werden. Alles löschen ändert sie nicht.",
        "it": "Quale pagina di una doppia pagina si legge per prima, e l'ordine delle nuvolette su una pagina. Le pagine già tradotte mantengono le traduzioni e prendono il nuovo ordine quando vengono mostrate di nuovo. Cancella tutto non la cambia.",
        "nl": "Welke pagina van een dubbele pagina eerst wordt gelezen, en de volgorde van de tekstballonnen op een pagina. Al vertaalde pagina's houden hun vertalingen en krijgen de nieuwe volgorde zodra ze weer getoond worden. Alles wissen verandert dit niet.",
        "pl": "Która strona rozkładówki jest czytana pierwsza oraz kolejność dymków na stronie. Strony przetłumaczone wcześniej zachowują tłumaczenia i przyjmują nową kolejność przy następnym wyświetleniu. Wyczyść wszystko tego nie zmienia.",
        "ru": "Какая страница разворота читается первой и в каком порядке идут пузыри на странице. Уже переведённые страницы сохраняют переводы и получают новый порядок, когда показываются снова. «Очистить всё» этого не меняет.",
        "tr": "Çift sayfalık bir açılımda hangi sayfanın önce okunduğu ve bir sayfadaki balonların sırası. Daha önce çevrilen sayfalar çevirilerini korur ve yeniden gösterildiklerinde yeni sırayı alır. Tümünü temizle bunu değiştirmez.",
        "id": "Halaman mana dari halaman ganda yang dibaca lebih dulu, dan urutan balon di satu halaman. Halaman yang sudah diterjemahkan tetap memakai terjemahannya dan mengikuti urutan baru saat ditampilkan lagi. Bersihkan semua tidak mengubahnya.",
        "vi": "Trang nào của một cặp trang đôi được đọc trước, và thứ tự các bong bóng trên một trang. Các trang đã dịch giữ nguyên bản dịch và theo thứ tự mới khi được hiển thị lại. Xóa tất cả không thay đổi mục này.",
        "zh": "跨页中先读哪一页，以及页面上气泡的顺序。已翻译的页面保留译文，再次显示时按新的顺序排列。“全部清除”不会改变此项。",
        "zh-tw": "跨頁中先讀哪一頁，以及頁面上氣泡的順序。已翻譯的頁面保留譯文，再次顯示時依新的順序排列。「全部清除」不會改變此項。",
        "ko": "두 쪽 펼침에서 어느 쪽을 먼저 읽는지, 그리고 한 쪽 안의 말풍선 순서입니다. 이미 번역한 쪽은 번역을 그대로 두고, 다시 표시될 때 새 순서를 따릅니다. '모두 지우기'로는 바뀌지 않습니다.",
        "th": "หน้าไหนของหน้าคู่ที่อ่านก่อน และลำดับของบอลลูนในหน้า หน้าที่แปลไว้แล้วจะเก็บคำแปลไว้และใช้ลำดับใหม่เมื่อแสดงอีกครั้ง ล้างทั้งหมดจะไม่เปลี่ยนค่านี้",
    },
}

"""The window's strings for a book's name as two fields, Series and Volume (`ui.book_fields`): the fields' labels and
tooltips in the toolbar, the start dialog and the colophon's offer; the line under them when the Volume field holds
no volume; the cache list's headings; the rename review's line with the new name's parts; the offer to rename a book
kept under an older spelling of its name to the one spelling, and the status line after Not now.

The volumes that are no number (上, 中, 下, 前編, 後編) and the edition 完全版 stay in Japanese in every language: they
are what the reader types, as the book's own cover writes them. "Series" is worded as in the series sheet (ja
「シリーズ設定」, de „Serienblatt“, es «ficha de la serie», ko '시리즈 시트'); the Volume field's label as the volume
of a book in a series (ja 「巻」, zh 「卷」, ko '권').

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ the two fields
    "Series:": {
        "ja": "シリーズ:", "es": "Serie:", "pt": "Série:", "fr": "Série :", "de": "Serie:", "it": "Serie:",
        "nl": "Serie:", "pl": "Seria:", "ru": "Серия:", "tr": "Seri:", "id": "Seri:", "vi": "Bộ truyện:",
        "zh": "系列：", "zh-tw": "系列：", "ko": "시리즈:", "th": "ซีรีส์:",
    },
    "Volume:": {
        "ja": "巻:", "es": "Tomo:", "pt": "Volume:", "fr": "Tome :", "de": "Band:", "it": "Volume:", "nl": "Deel:",
        "pl": "Tom:", "ru": "Том:", "tr": "Cilt:", "id": "Volume:", "vi": "Tập:", "zh": "卷：", "zh-tw": "卷：",
        "ko": "권:", "th": "เล่ม:",
    },
    "Vol.:": {  # the toolbar's short label of the Volume field
        "ja": "巻:", "es": "T.:", "pt": "Vol.:", "fr": "T. :", "de": "Bd.:", "it": "Vol.:", "nl": "Dl.:", "pl": "T.:",
        "ru": "Т.:", "tr": "C.:", "id": "Vol.:", "vi": "Tập:", "zh": "卷：", "zh-tw": "卷：", "ko": "권:", "th": "เล่ม:",
    },
    "The book's series: what its volumes share, an edition such as 完全版 included. With the volume it names the book its translations are kept under.": {
        "ja": "本のシリーズ名。各巻に共通の部分で、完全版などの版もここに含めます。巻と合わせて、訳文を保存する本の名前になります。",
        "es": "La serie del libro: lo que comparten sus tomos, incluida una edición como 完全版. Con el tomo, da el nombre del libro bajo el que se guardan sus traducciones.",
        "pt": "A série do livro: o que os volumes têm em comum, incluindo uma edição como 完全版. Com o volume, forma o nome do livro sob o qual as traduções são guardadas.",
        "fr": "La série du livre : ce que ses tomes ont en commun, édition comme 完全版 comprise. Avec le tome, elle donne le nom sous lequel ses traductions sont gardées.",
        "de": "Die Serie des Buchs: was seine Bände gemeinsam haben, eine Ausgabe wie 完全版 eingeschlossen. Mit dem Band ergibt sie den Namen, unter dem seine Übersetzungen gespeichert werden.",
        "it": "La serie del libro: ciò che i volumi hanno in comune, compresa un'edizione come 完全版. Con il volume forma il nome del libro sotto cui si conservano le traduzioni.",
        "nl": "De serie van het boek: wat de delen gemeen hebben, een uitgave zoals 完全版 inbegrepen. Met het deel vormt ze de naam waaronder de vertalingen bewaard worden.",
        "pl": "Seria książki: to, co wspólne dla jej tomów, łącznie z wydaniem takim jak 完全版. Razem z tomem tworzy nazwę, pod którą zapisywane są tłumaczenia.",
        "ru": "Серия книги: то, что общее у её томов, включая издание вроде 完全版. Вместе с томом даёт имя книги, под которым хранятся переводы.",
        "tr": "Kitabın serisi: ciltlerinin ortak adı, 完全版 gibi bir baskı da dahil. Ciltle birlikte, çevirilerin saklandığı kitap adını oluşturur.",
        "id": "Seri buku: bagian yang sama di semua volumenya, termasuk edisi seperti 完全版. Bersama volume, ini menjadi nama buku tempat terjemahannya disimpan.",
        "vi": "Bộ truyện của sách: phần chung của các tập, kể cả ấn bản như 完全版. Cùng với số tập, nó tạo thành tên sách dùng để lưu bản dịch.",
        "zh": "书的系列名：各卷共有的部分，包括“完全版”之类的版本。与卷号一起构成保存译文所用的书名。",
        "zh-tw": "書的系列名：各卷共有的部分，包括「完全版」之類的版本。與卷號一起構成儲存譯文所用的書名。",
        "ko": "책의 시리즈 이름: 각 권에 공통인 부분으로, 完全版 같은 판도 포함합니다. 권과 함께 번역을 저장하는 책 이름이 됩니다.",
        "th": "ชื่อซีรีส์ของหนังสือ: ส่วนที่ทุกเล่มมีร่วมกัน รวมถึงฉบับอย่าง 完全版 เมื่อรวมกับเล่มจะเป็นชื่อหนังสือที่ใช้เก็บคำแปล",
    },
    "The volume's number (3, 10.5) or 上, 中, 下, 前編, 後編; empty for a book of one volume. 第3巻, Vol. 3 and ③ are taken as 3.": {
        "ja": "巻の番号（3、10.5）、または 上・中・下・前編・後編。1冊だけの本は空欄のままにします。第3巻、Vol. 3、③ は 3 として扱います。",
        "es": "El número del tomo (3, 10.5) o 上, 中, 下, 前編, 後編; vacío para un libro de un solo tomo. 第3巻, Vol. 3 y ③ se toman como 3.",
        "pt": "O número do volume (3, 10.5) ou 上, 中, 下, 前編, 後編; vazio para um livro de um só volume. 第3巻, Vol. 3 e ③ contam como 3.",
        "fr": "Le numéro du tome (3, 10.5) ou 上, 中, 下, 前編, 後編 ; vide pour un livre en un seul tome. 第3巻, Vol. 3 et ③ valent 3.",
        "de": "Die Nummer des Bands (3, 10.5) oder 上, 中, 下, 前編, 後編; leer bei einem Buch aus nur einem Band. 第3巻, Vol. 3 und ③ gelten als 3.",
        "it": "Il numero del volume (3, 10.5) o 上, 中, 下, 前編, 後編; vuoto per un libro in un solo volume. 第3巻, Vol. 3 e ③ valgono 3.",
        "nl": "Het nummer van het deel (3, 10.5) of 上, 中, 下, 前編, 後編; leeg voor een boek van één deel. 第3巻, Vol. 3 en ③ gelden als 3.",
        "pl": "Numer tomu (3, 10.5) albo 上, 中, 下, 前編, 後編; puste dla książki jednotomowej. 第3巻, Vol. 3 i ③ liczą się jako 3.",
        "ru": "Номер тома (3, 10.5) или 上, 中, 下, 前編, 後編; пусто для книги в одном томе. 第3巻, Vol. 3 и ③ считаются за 3.",
        "tr": "Cildin numarası (3, 10.5) ya da 上, 中, 下, 前編, 後編; tek ciltlik bir kitapta boş. 第3巻, Vol. 3 ve ③, 3 olarak alınır.",
        "id": "Nomor volume (3, 10.5) atau 上, 中, 下, 前編, 後編; kosong untuk buku satu volume. 第3巻, Vol. 3, dan ③ dibaca sebagai 3.",
        "vi": "Số tập (3, 10.5) hoặc 上, 中, 下, 前編, 後編; để trống với sách chỉ có một tập. 第3巻, Vol. 3 và ③ được hiểu là 3.",
        "zh": "卷号（3、10.5），或 上、中、下、前編、後編；只有一册的书留空。第3巻、Vol. 3 和 ③ 都视为 3。",
        "zh-tw": "卷號（3、10.5），或 上、中、下、前編、後編；只有一冊的書留空。第3巻、Vol. 3 和 ③ 都視為 3。",
        "ko": "권 번호(3, 10.5) 또는 上, 中, 下, 前編, 後編. 한 권짜리 책은 비워 둡니다. 第3巻, Vol. 3, ③은 3으로 봅니다.",
        "th": "หมายเลขเล่ม (3, 10.5) หรือ 上, 中, 下, 前編, 後編 เว้นว่างไว้สำหรับหนังสือเล่มเดียวจบ 第3巻, Vol. 3 และ ③ จะถือเป็น 3",
    },
    "{volume} is not a volume: the Volume field takes a number (3, 10.5) or 上, 中, 下, 前編, 後編. An edition such as 完全版 belongs to the series.": {
        "ja": "「{volume}」は巻として使えません。巻の欄には番号（3、10.5）か 上・中・下・前編・後編 を入れてください。完全版などの版はシリーズ名に含めます。",
        "es": "{volume} no es un tomo: el campo Tomo admite un número (3, 10.5) o 上, 中, 下, 前編, 後編. Una edición como 完全版 va en la serie.",
        "pt": "{volume} não é um volume: o campo Volume aceita um número (3, 10.5) ou 上, 中, 下, 前編, 後編. Uma edição como 完全版 fica na série.",
        "fr": "{volume} n'est pas un tome : le champ Tome prend un numéro (3, 10.5) ou 上, 中, 下, 前編, 後編. Une édition comme 完全版 fait partie de la série.",
        "de": "{volume} ist kein Band: Das Feld Band nimmt eine Nummer (3, 10.5) oder 上, 中, 下, 前編, 後編. Eine Ausgabe wie 完全版 gehört zur Serie.",
        "it": "{volume} non è un volume: il campo Volume accetta un numero (3, 10.5) o 上, 中, 下, 前編, 後編. Un'edizione come 完全版 va nella serie.",
        "nl": "{volume} is geen deel: het veld Deel neemt een nummer (3, 10.5) of 上, 中, 下, 前編, 後編. Een uitgave zoals 完全版 hoort bij de serie.",
        "pl": "{volume} to nie tom: pole Tom przyjmuje numer (3, 10.5) albo 上, 中, 下, 前編, 後編. Wydanie takie jak 完全版 należy do serii.",
        "ru": "{volume} — не том: в поле «Том» вводится номер (3, 10.5) или 上, 中, 下, 前編, 後編. Издание вроде 完全版 относится к серии.",
        "tr": "{volume} bir cilt değil: Cilt alanı bir numara (3, 10.5) ya da 上, 中, 下, 前編, 後編 alır. 完全版 gibi bir baskı seriye aittir.",
        "id": "{volume} bukan volume: kolom Volume menerima nomor (3, 10.5) atau 上, 中, 下, 前編, 後編. Edisi seperti 完全版 termasuk ke seri.",
        "vi": "{volume} không phải là tập: ô Tập nhận một số (3, 10.5) hoặc 上, 中, 下, 前編, 後編. Ấn bản như 完全版 thuộc về tên bộ truyện.",
        "zh": "“{volume}”不是卷号：卷栏只接受数字（3、10.5）或 上、中、下、前編、後編。“完全版”之类的版本属于系列名。",
        "zh-tw": "「{volume}」不是卷號：卷欄只接受數字（3、10.5）或 上、中、下、前編、後編。「完全版」之類的版本屬於系列名。",
        "ko": "{volume}은(는) 권이 아닙니다. 권 칸에는 번호(3, 10.5)나 上, 中, 下, 前編, 後編만 넣습니다. 完全版 같은 판은 시리즈 이름에 넣습니다.",
        "th": "{volume} ไม่ใช่เล่ม: ช่องเล่มรับเฉพาะหมายเลข (3, 10.5) หรือ 上, 中, 下, 前編, 後編 ส่วนฉบับอย่าง 完全版 ให้อยู่ในชื่อซีรีส์",
    },
    # ------------------------------------------------------------------ the cache list's headings
    "Series": {
        "ja": "シリーズ", "es": "Serie", "pt": "Série", "fr": "Série", "de": "Serie", "it": "Serie", "nl": "Serie",
        "pl": "Seria", "ru": "Серия", "tr": "Seri", "id": "Seri", "vi": "Bộ truyện", "zh": "系列", "zh-tw": "系列",
        "ko": "시리즈", "th": "ซีรีส์",
    },
    "Volume": {
        "ja": "巻", "es": "Tomo", "pt": "Volume", "fr": "Tome", "de": "Band", "it": "Volume", "nl": "Deel", "pl": "Tom",
        "ru": "Том", "tr": "Cilt", "id": "Volume", "vi": "Tập", "zh": "卷", "zh-tw": "卷", "ko": "권", "th": "เล่ม",
    },
    # ------------------------------------------------------------------ the rename review's line
    "The new name: {parts}": {
        "ja": "新しい名前: {parts}", "es": "El nuevo nombre: {parts}", "pt": "O novo nome: {parts}",
        "fr": "Le nouveau nom : {parts}", "de": "Der neue Name: {parts}", "it": "Il nuovo nome: {parts}",
        "nl": "De nieuwe naam: {parts}", "pl": "Nowa nazwa: {parts}", "ru": "Новое имя: {parts}",
        "tr": "Yeni ad: {parts}", "id": "Nama baru: {parts}", "vi": "Tên mới: {parts}", "zh": "新名称：{parts}",
        "zh-tw": "新名稱：{parts}", "ko": "새 이름: {parts}", "th": "ชื่อใหม่: {parts}",
    },
    "Series {series}, volume {volume}": {
        "ja": "シリーズ「{series}」、{volume} 巻", "es": "serie {series}, tomo {volume}",
        "pt": "série {series}, volume {volume}", "fr": "série {series}, tome {volume}",
        "de": "Serie {series}, Band {volume}", "it": "serie {series}, volume {volume}",
        "nl": "serie {series}, deel {volume}", "pl": "seria {series}, tom {volume}", "ru": "серия {series}, том {volume}",
        "tr": "seri {series}, cilt {volume}", "id": "seri {series}, volume {volume}",
        "vi": "bộ truyện {series}, tập {volume}", "zh": "系列《{series}》，第 {volume} 卷",
        "zh-tw": "系列《{series}》，第 {volume} 卷", "ko": "시리즈 {series}, {volume}권",
        "th": "ซีรีส์ {series} เล่ม {volume}",
    },
    "Series {series}, no volume": {
        "ja": "シリーズ「{series}」、巻なし", "es": "serie {series}, sin tomo", "pt": "série {series}, sem volume",
        "fr": "série {series}, sans tome", "de": "Serie {series}, ohne Band", "it": "serie {series}, senza volume",
        "nl": "serie {series}, zonder deel", "pl": "seria {series}, bez tomu", "ru": "серия {series}, без тома",
        "tr": "seri {series}, ciltsiz", "id": "seri {series}, tanpa volume", "vi": "bộ truyện {series}, không có tập",
        "zh": "系列《{series}》，无卷号", "zh-tw": "系列《{series}》，無卷號", "ko": "시리즈 {series}, 권 없음",
        "th": "ซีรีส์ {series} ไม่มีเล่ม",
    },
    # ------------------------------------------------------------------ a book kept under an older spelling
    "This book's files are kept under {old}, a spelling from before the Series and Volume fields. Rename the book to {new}? Its translations, notes and sheet move along; until then everything is found under the old name.": {
        "ja": "この本のファイルは『{old}』という、シリーズと巻の欄ができる前の書き方で保存されています。書名を『{new}』に変えますか？ 訳文・ノート・シリーズ設定も一緒に移ります。変えるまでは、すべて元の名前のまま使えます。",
        "es": "Los archivos de este libro se guardan como {old}, una forma de escribirlo de antes de los campos Serie y Tomo. ¿Renombrar el libro a {new}? Sus traducciones, notas y ficha lo acompañan; hasta entonces todo sigue bajo el nombre antiguo.",
        "pt": "Os arquivos deste livro estão guardados como {old}, uma grafia de antes dos campos Série e Volume. Renomear o livro para {new}? As traduções, as notas e a ficha vão junto; até lá, tudo continua sob o nome antigo.",
        "fr": "Les fichiers de ce livre sont gardés sous {old}, une graphie d'avant les champs Série et Tome. Renommer le livre en {new} ? Ses traductions, ses notes et sa fiche le suivent ; d'ici là, tout reste sous l'ancien nom.",
        "de": "Die Dateien dieses Buchs liegen unter {old}, einer Schreibweise aus der Zeit vor den Feldern Serie und Band. Das Buch in {new} umbenennen? Seine Übersetzungen, Notizen und sein Blatt ziehen mit um; bis dahin bleibt alles unter dem alten Namen.",
        "it": "I file di questo libro sono conservati come {old}, una grafia di prima dei campi Serie e Volume. Rinominare il libro in {new}? Traduzioni, note e scheda lo seguono; fino ad allora tutto resta sotto il vecchio nome.",
        "nl": "De bestanden van dit boek staan onder {old}, een schrijfwijze van vóór de velden Serie en Deel. Het boek hernoemen naar {new}? De vertalingen, notities en het blad gaan mee; tot dan blijft alles onder de oude naam.",
        "pl": "Pliki tej książki są zapisane jako {old}, w pisowni sprzed pól Seria i Tom. Zmienić nazwę książki na {new}? Tłumaczenia, notatki i karta zostaną przeniesione; do tego czasu wszystko jest pod starą nazwą.",
        "ru": "Файлы этой книги хранятся под именем {old} — так его писали до полей «Серия» и «Том». Переименовать книгу в {new}? Переводы, заметки и карточка перейдут вместе с ней; до тех пор всё остаётся под старым именем.",
        "tr": "Bu kitabın dosyaları, Seri ve Cilt alanlarından önceki bir yazımla {old} adı altında saklanıyor. Kitabın adı {new} olarak değiştirilsin mi? Çevirileri, notları ve kartı da taşınır; o zamana kadar her şey eski adın altında bulunur.",
        "id": "Berkas buku ini disimpan sebagai {old}, ejaan dari sebelum ada kolom Seri dan Volume. Ganti nama buku menjadi {new}? Terjemahan, catatan, dan lembarnya ikut pindah; sampai saat itu semuanya tetap di bawah nama lama.",
        "vi": "Các tệp của sách này được lưu dưới tên {old}, cách viết từ trước khi có ô Bộ truyện và Tập. Đổi tên sách thành {new}? Bản dịch, ghi chú và phiếu sẽ chuyển theo; cho đến lúc đó, mọi thứ vẫn nằm dưới tên cũ.",
        "zh": "本书的文件保存在《{old}》之下，这是有“系列”和“卷”两栏之前的写法。要把书名改为《{new}》吗？其译文、笔记和设定会一起移动；在此之前，一切仍保存在旧名称下。",
        "zh-tw": "本書的檔案儲存在《{old}》之下，這是有「系列」和「卷」兩欄之前的寫法。要把書名改為《{new}》嗎？其譯文、筆記和設定會一起移動；在此之前，一切仍儲存在舊名稱下。",
        "ko": "이 책의 파일은 시리즈와 권 칸이 생기기 전의 표기인 '{old}'(으)로 저장되어 있습니다. 책 이름을 '{new}'(으)로 바꿀까요? 번역, 노트, 시트도 함께 옮겨집니다. 그전까지는 모두 예전 이름으로 그대로 쓸 수 있습니다.",
        "th": "ไฟล์ของหนังสือเล่มนี้เก็บไว้ในชื่อ {old} ซึ่งเป็นการสะกดจากก่อนมีช่องซีรีส์และเล่ม เปลี่ยนชื่อหนังสือเป็น {new} ไหม คำแปล บันทึก และแผ่นข้อมูลจะย้ายไปด้วย จนกว่าจะเปลี่ยน ทุกอย่างยังอยู่ใต้ชื่อเดิม",
    },
    "{book} keeps its name for now; its translations are found under it as before.": {
        "ja": "『{book}』の名前は今のところそのままです。訳文はこれまでどおりこの名前で見つかります。",
        "es": "{book} conserva su nombre por ahora; sus traducciones siguen encontrándose bajo él.",
        "pt": "{book} mantém o nome por enquanto; as traduções continuam sob ele, como antes.",
        "fr": "{book} garde son nom pour l'instant ; ses traductions se trouvent sous ce nom, comme avant.",
        "de": "{book} behält vorerst seinen Namen; seine Übersetzungen finden sich wie bisher darunter.",
        "it": "{book} mantiene il nome per ora; le sue traduzioni si trovano sotto di esso come prima.",
        "nl": "{book} houdt voorlopig zijn naam; de vertalingen staan er zoals voorheen onder.",
        "pl": "{book} na razie zachowuje nazwę; tłumaczenia są pod nią jak dotąd.",
        "ru": "{book} пока сохраняет своё имя; переводы, как и раньше, находятся под ним.",
        "tr": "{book} şimdilik adını koruyor; çevirileri eskisi gibi bu adın altında bulunur.",
        "id": "{book} tetap memakai namanya untuk saat ini; terjemahannya tetap ada di bawah nama itu seperti sebelumnya.",
        "vi": "{book} tạm thời giữ tên; bản dịch vẫn nằm dưới tên này như trước.",
        "zh": "《{book}》暂时保留原名；其译文仍像以前一样保存在此名称下。",
        "zh-tw": "《{book}》暫時保留原名；其譯文仍像以前一樣儲存在此名稱下。",
        "ko": "'{book}'은(는) 당분간 이름을 그대로 둡니다. 번역은 전처럼 이 이름으로 찾을 수 있습니다.",
        "th": "{book} ยังใช้ชื่อเดิมไปก่อน คำแปลยังอยู่ใต้ชื่อนี้เหมือนเดิม",
    },
}

"""The window's strings for the name check of the pages read one by one (`ui.name_check.keep_page_found`,
`JobsMixin._offer_page_names`): the band's line that offers the names found, and the line when nothing was found. The
names' own words (Review names..., the dialog) are the name helper's (`names_helper`), and so is the wording of
"rendered in more than one way".

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "{n} name(s) rendered in more than one way in the pages read so far.": {
        "ja": "ここまで読んだページで、複数の訳し方をされた名前が {n} 個あります。",
        "es": "Nombres traducidos de más de una forma en las páginas leídas hasta ahora: {n}.",
        "pt": "Nomes traduzidos de mais de uma forma nas páginas lidas até agora: {n}.",
        "fr": "Noms rendus de plusieurs façons dans les pages lues jusqu'ici : {n}.",
        "de": "Namen, die in den bisher gelesenen Seiten auf mehr als eine Weise übersetzt wurden: {n}.",
        "it": "Nomi resi in più di un modo nelle pagine lette finora: {n}.",
        "nl": "Namen die in de tot nu toe gelezen pagina's op meer dan één manier zijn vertaald: {n}.",
        "pl": "Imiona oddane na więcej niż jeden sposób na dotąd przeczytanych stronach: {n}.",
        "ru": "Имён, переданных по-разному на прочитанных до сих пор страницах: {n}.",
        "tr": "Şimdiye kadar okunan sayfalarda birden fazla biçimde çevrilen ad sayısı: {n}.",
        "id": "Nama yang diterjemahkan lebih dari satu cara di halaman yang sudah dibaca: {n}.",
        "vi": "Số tên được dịch theo nhiều cách trong các trang đã đọc đến giờ: {n}.",
        "zh": "到目前为止读过的页面中，有 {n} 个名字被译成了不止一种写法。",
        "zh-tw": "到目前為止讀過的頁面中，有 {n} 個名字被譯成了不只一種寫法。",
        "ko": "지금까지 읽은 페이지에서 여러 가지로 옮겨진 이름이 {n}개 있습니다.",
        "th": "ชื่อที่ถูกแปลมากกว่าหนึ่งแบบในหน้าที่อ่านมาจนถึงตอนนี้: {n}",
    },
    "Neither a whole-book run nor the pages read one by one in this session rendered a name of this book in more than one way. The Japanese lines are looked at only while TASlation is open.": {
        "ja": "この起動中の1冊まるごと読む実行でも、1ページずつ読んだページでも、この本で複数の訳し方をされた名前は見つかりませんでした。日本語の行は TASlation を開いている間だけ確かめます。",
        "es": "Ni una lectura de todo el libro ni las páginas leídas una a una en esta sesión tradujeron un nombre de este libro de más de una forma. Las líneas en japonés solo se miran mientras TASlation está abierto.",
        "pt": "Nem uma leitura do livro inteiro nem as páginas lidas uma a uma nesta sessão traduziram um nome deste livro de mais de uma forma. As linhas em japonês só são vistas enquanto o TASlation está aberto.",
        "fr": "Ni une lecture du livre entier ni les pages lues une à une dans cette session n'ont rendu un nom de ce livre de plusieurs façons. Les lignes en japonais ne sont examinées que tant que TASlation est ouvert.",
        "de": "Weder ein Durchlauf des ganzen Buchs noch die einzeln gelesenen Seiten haben in dieser Sitzung einen Namen dieses Buchs auf mehrere Weisen übersetzt. Die japanischen Zeilen werden nur angesehen, solange TASlation offen ist.",
        "it": "Né una lettura di tutto il libro né le pagine lette una per una in questa sessione hanno reso un nome di questo libro in più di un modo. Le righe in giapponese si esaminano solo finché TASlation è aperto.",
        "nl": "Geen doorloop van het hele boek en geen van de pagina's die één voor één zijn gelezen heeft in deze sessie een naam van dit boek op meer manieren vertaald. De Japanse regels worden alleen bekeken zolang TASlation open is.",
        "pl": "Ani czytanie całej książki, ani strony czytane po jednej w tej sesji nie oddały imienia z tej książki na różne sposoby. Japońskie wiersze są sprawdzane tylko, dopóki TASlation jest otwarty.",
        "ru": "Ни проход всей книги, ни страницы, прочитанные по одной в этом сеансе, не передали имя этой книги по-разному. Японские строки просматриваются, только пока TASlation открыт.",
        "tr": "Bu oturumda ne kitabın tamamı okuması ne de tek tek okunan sayfalar bu kitaptaki bir adı birden fazla biçimde çevirdi. Japonca satırlara yalnızca TASlation açıkken bakılır.",
        "id": "Baik pembacaan seluruh buku maupun halaman yang dibaca satu per satu dalam sesi ini tidak menerjemahkan nama dari buku ini lebih dari satu cara. Baris bahasa Jepang hanya diperiksa selama TASlation terbuka.",
        "vi": "Cả lượt đọc cả cuốn lẫn các trang đọc từng trang trong phiên này đều không dịch tên nào của cuốn sách theo nhiều cách. Các dòng tiếng Nhật chỉ được xem khi TASlation đang mở.",
        "zh": "本次运行中，无论是整本书读取还是逐页读过的页面，都没有把此书中的名字译成多种写法。日文行只在 TASlation 打开期间检查。",
        "zh-tw": "本次執行中，無論是整本書讀取還是逐頁讀過的頁面，都沒有把此書中的名字譯成多種寫法。日文行只在 TASlation 開啟期間檢查。",
        "ko": "이번 실행 중에는 책 전체 읽기에서도, 한 페이지씩 읽은 페이지에서도 이 책의 이름이 여러 가지로 옮겨지지 않았습니다. 일본어 줄은 TASlation이 열려 있는 동안에만 확인합니다.",
        "th": "ในรอบนี้ ทั้งการอ่านทั้งเล่มและหน้าที่อ่านทีละหน้าไม่ได้แปลชื่อในเล่มนี้มากกว่าหนึ่งแบบ บรรทัดภาษาญี่ปุ่นจะถูกตรวจเฉพาะตอนที่ TASlation เปิดอยู่",
    },
}

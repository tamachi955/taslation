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
    "The pages read in this session rendered no name of this book in more than one way. The Japanese lines are looked at only while TASlation is open.": {
        "ja": "この起動中に読んだページでは、この本で複数の訳し方をされた名前は見つかりませんでした。日本語の行は TASlation を開いている間だけ確かめます。",
        "es": "Las páginas leídas en esta sesión no tradujeron ningún nombre de este libro de más de una forma. Las líneas en japonés solo se miran mientras TASlation está abierto.",
        "pt": "As páginas lidas nesta sessão não traduziram nenhum nome deste livro de mais de uma forma. As linhas em japonês só são examinadas enquanto o TASlation está aberto.",
        "fr": "Les pages lues dans cette session n'ont rendu aucun nom de ce livre de plusieurs façons. Les lignes en japonais ne sont examinées que tant que TASlation est ouvert.",
        "de": "Die in dieser Sitzung gelesenen Seiten haben keinen Namen dieses Buchs auf mehrere Weisen übersetzt. Die japanischen Zeilen werden nur angesehen, solange TASlation offen ist.",
        "it": "Le pagine lette in questa sessione non hanno reso nessun nome di questo libro in più di un modo. Le righe in giapponese vengono esaminate solo mentre TASlation è aperto.",
        "nl": "De pagina's die in deze sessie zijn gelezen, gaven geen naam van dit boek op meer dan één manier weer. De Japanse regels worden alleen bekeken zolang TASlation open is.",
        "pl": "Strony przeczytane w tej sesji nie oddały żadnego imienia z tej książki na więcej niż jeden sposób. Japońskie wiersze są sprawdzane tylko wtedy, gdy TASlation jest otwarty.",
        "ru": "На страницах, прочитанных в этом сеансе, ни одно имя этой книги не переведено по-разному. Японские строки просматриваются, только пока TASlation открыт.",
        "tr": "Bu oturumda okunan sayfalar bu kitabın hiçbir adını birden fazla biçimde çevirmedi. Japonca satırlara yalnızca TASlation açıkken bakılır.",
        "id": "Halaman yang dibaca dalam sesi ini tidak menerjemahkan nama apa pun dari buku ini dengan lebih dari satu cara. Baris bahasa Jepang hanya diperiksa selama TASlation terbuka.",
        "vi": "Các trang đã đọc trong phiên này không dịch tên nào của sách này theo nhiều cách. Các dòng tiếng Nhật chỉ được xem khi TASlation đang mở.",
        "zh": "本次会话中读过的页面里，本书没有哪个名字被译成多种写法。日文行仅在 TASlation 打开期间查看。",
        "zh-tw": "本次工作階段中讀過的頁面裡，本書沒有哪個名字被譯成多種寫法。日文行僅在 TASlation 開啟期間查看。",
        "ko": "이번 세션에서 읽은 페이지에서는 이 책의 이름이 여러 방식으로 번역된 경우가 없었습니다. 일본어 줄은 TASlation이 열려 있는 동안에만 확인합니다.",
        "th": "หน้าที่อ่านในเซสชันนี้ไม่มีชื่อใดของหนังสือเล่มนี้ที่ถูกแปลมากกว่าหนึ่งแบบ บรรทัดภาษาญี่ปุ่นจะถูกตรวจดูเฉพาะขณะที่ TASlation เปิดอยู่",
    },
}

"""The window's strings for being over a full-screen viewer (`ui.overbook`): the View menu's entry and its tip, the line
said when it starts, the line for a page key a browser did not take (`reading.forward_key`), and the help's two
paragraphs (Reading mode). The menu's name is the same in every string that names it (`_ENTRY`, `_VIEW`)."""

_VIEW = {"ja": "表示", "es": "Ver", "pt": "Exibir", "fr": "Affichage", "de": "Ansicht", "it": "Visualizza", "nl": "Beeld",
         "pl": "Widok", "ru": "Вид", "tr": "Görünüm", "id": "Tampilan", "vi": "Xem", "zh": "视图", "zh-tw": "檢視",
         "ko": "보기", "th": "มุมมอง"}
_ENTRY = {
    "ja": "全画面ビューアの上に表示",
    "es": "Sobre el visor a pantalla completa",
    "pt": "Sobre o visualizador em tela cheia",
    "fr": "Au-dessus de la visionneuse plein écran",
    "de": "Über dem Viewer im Vollbild",
    "it": "Sopra il visualizzatore a schermo intero",
    "nl": "Boven de viewer op volledig scherm",
    "pl": "Nad czytnikiem na pełnym ekranie",
    "ru": "Поверх полноэкранного просмотрщика",
    "tr": "Tam ekran görüntüleyicinin üstünde",
    "id": "Di atas penampil layar penuh",
    "vi": "Nằm trên trình xem toàn màn hình",
    "zh": "置于全屏查看器之上",
    "zh-tw": "置於全螢幕檢視器之上",
    "ko": "전체 화면 뷰어 위에 표시",
    "th": "อยู่เหนือโปรแกรมอ่านแบบเต็มจอ",
}


def _menu(code: str) -> str:
    return f"{_VIEW[code]} > {_ENTRY[code]}"


_STARTED = {
    "ja": "TASlation は全画面のビューアの上に表示されています。キー操作は本に届き、F5 での翻訳もそのまま使えます。{menu} でオフにできます。",
    "es": "TASlation se queda sobre el visor a pantalla completa: tus teclas van al libro y F5 sigue traduciendo. {menu} lo desactiva.",
    "pt": "O TASlation fica sobre o visualizador em tela cheia: suas teclas vão para o livro e F5 continua traduzindo. {menu} desativa isso.",
    "fr": "TASlation reste au-dessus de la visionneuse plein écran : vos touches vont au livre, et F5 traduit toujours. {menu} le désactive.",
    "de": "TASlation bleibt über dem Viewer im Vollbild: Ihre Tasten gehen an das Buch, und F5 übersetzt weiterhin. {menu} schaltet das aus.",
    "it": "TASlation resta sopra il visualizzatore a schermo intero: i tuoi tasti vanno al libro e F5 traduce ancora. {menu} lo disattiva.",
    "nl": "TASlation blijft boven de viewer op volledig scherm: uw toetsen gaan naar het boek en F5 vertaalt nog steeds. {menu} zet dit uit.",
    "pl": "TASlation zostaje nad czytnikiem na pełnym ekranie: klawisze trafiają do książki, a F5 nadal tłumaczy. {menu} to wyłącza.",
    "ru": "TASlation остаётся поверх полноэкранного просмотрщика: клавиши идут в книгу, а F5 по-прежнему переводит. {menu} отключает это.",
    "tr": "TASlation tam ekran görüntüleyicinin üstünde kalır: tuşlarınız kitaba gider, F5 yine çevirir. {menu} bunu kapatır.",
    "id": "TASlation tetap di atas penampil layar penuh: tombol Anda masuk ke buku, dan F5 tetap menerjemahkan. {menu} mematikannya.",
    "vi": "TASlation nằm trên trình xem toàn màn hình: phím của bạn đến cuốn sách, F5 vẫn dịch. {menu} tắt chế độ này.",
    "zh": "TASlation 置于全屏查看器之上：按键会送到书中，F5 仍可翻译。{menu} 可关闭此功能。",
    "zh-tw": "TASlation 置於全螢幕檢視器之上：按鍵會送到書中，F5 仍可翻譯。{menu} 可關閉此功能。",
    "ko": "TASlation이 전체 화면 뷰어 위에 표시됩니다. 키는 책으로 가고, F5로 번역도 그대로 됩니다. {menu}에서 끌 수 있습니다.",
    "th": "TASlation อยู่เหนือโปรแกรมอ่านแบบเต็มจอ: ปุ่มที่กดจะไปที่หนังสือ และ F5 ยังแปลได้ตามเดิม ปิดได้ที่ {menu}",
}
_HELP_OFF = {
    "ja": "TASlation のボタンやページの帯は、いつもどおりクリックで使えます。文字を入力する欄やダイアログは、使っている間だけキー入力を受け取ります。{menu} でオフにできます。本が別のモニターにあるときは何も変わりません。",
    "es": "Los botones y la tira de páginas de TASlation funcionan con clics como siempre. Una casilla en la que escribes, y cada diálogo, toma las teclas mientras lo usas. {menu} lo desactiva; con el libro en otro monitor no cambia nada.",
    "pt": "Os botões e a faixa de páginas do TASlation funcionam com cliques como sempre. Uma caixa em que você digita, e cada diálogo, recebe as teclas enquanto você o usa. {menu} desativa isso; com o livro em outro monitor nada muda.",
    "fr": "Les boutons et la bande des pages de TASlation marchent au clic comme d'habitude. Une case où vous tapez, et chaque boîte de dialogue, prend les touches le temps que vous l'utilisez. {menu} le désactive ; avec le livre sur un autre écran, rien ne change.",
    "de": "Die Schaltflächen und die Seitenleiste von TASlation funktionieren wie immer per Klick. Ein Feld, in das Sie tippen, und jeder Dialog bekommt die Tasten, solange Sie ihn benutzen. {menu} schaltet das aus; liegt das Buch auf einem anderen Bildschirm, ändert sich nichts.",
    "it": "I pulsanti e la striscia delle pagine di TASlation funzionano con un clic come sempre. Una casella in cui scrivi, e ogni finestra di dialogo, riceve i tasti mentre la usi. {menu} lo disattiva; con il libro su un altro monitor non cambia nulla.",
    "nl": "De knoppen en de paginastrook van TASlation werken met een klik zoals altijd. Een vak waarin u typt, en elk dialoogvenster, krijgt de toetsen zolang u het gebruikt. {menu} zet dit uit; staat het boek op een andere monitor, dan verandert er niets.",
    "pl": "Przyciski i pasek stron TASlation działają po kliknięciu jak zawsze. Pole, w którym piszesz, i każde okno dialogowe dostaje klawisze, dopóki z niego korzystasz. {menu} to wyłącza; gdy książka jest na innym monitorze, nic się nie zmienia.",
    "ru": "Кнопки и полоса страниц TASlation работают по щелчку, как обычно. Поле, в которое вы печатаете, и любое диалоговое окно получают клавиши, пока вы ими пользуетесь. {menu} отключает это; если книга на другом мониторе, ничего не меняется.",
    "tr": "TASlation'ın düğmeleri ve sayfa şeridi her zamanki gibi tıklamayla çalışır. Yazı yazdığınız bir kutu ve her iletişim kutusu, siz kullanırken tuşları alır. {menu} bunu kapatır; kitap başka bir monitördeyse hiçbir şey değişmez.",
    "id": "Tombol dan strip halaman TASlation tetap bisa diklik seperti biasa. Kotak tempat Anda mengetik, dan setiap dialog, menerima tombol selama Anda memakainya. {menu} mematikannya; jika buku ada di monitor lain, tidak ada yang berubah.",
    "vi": "Các nút và dải trang của TASlation vẫn dùng bằng cách nhấp như thường. Ô bạn gõ chữ, và mọi hộp thoại, nhận phím trong lúc bạn dùng. {menu} tắt chế độ này; khi sách ở màn hình khác thì không có gì thay đổi.",
    "zh": "TASlation 的按钮和页面条照常可以点击。输入文字的框和各个对话框在使用期间接收按键。{menu} 可关闭此功能；书在另一台显示器上时一切照旧。",
    "zh-tw": "TASlation 的按鈕和頁面條照常可以點按。輸入文字的欄位和各個對話方塊在使用期間接收按鍵。{menu} 可關閉此功能；書在另一台螢幕上時一切照舊。",
    "ko": "TASlation의 버튼과 페이지 띠는 평소처럼 클릭으로 쓸 수 있습니다. 글자를 입력하는 칸과 모든 대화 상자는 쓰는 동안 키를 받습니다. {menu}에서 끌 수 있으며, 책이 다른 모니터에 있으면 아무것도 바뀌지 않습니다.",
    "th": "ปุ่มและแถบหน้าของ TASlation ยังคลิกใช้ได้ตามปกติ ช่องที่คุณพิมพ์และกล่องโต้ตอบทุกอันจะรับปุ่มระหว่างที่ใช้งาน ปิดได้ที่ {menu} ถ้าหนังสืออยู่บนจออื่นจะไม่มีอะไรเปลี่ยน",
}

TEXTS: dict[str, dict[str, str]] = {
    "Over the full-screen viewer": dict(_ENTRY),
    "Over a viewer in full screen, stay on top without taking its keys: you turn the pages there.": {
        "ja": "全画面のビューアの上に表示したまま、キー操作は奪いません。ページはビューアでめくります。",
        "es": "Sobre un visor a pantalla completa, quedarse encima sin quitarle las teclas: pasas las páginas allí.",
        "pt": "Sobre um visualizador em tela cheia, ficar por cima sem tirar as teclas dele: você vira as páginas lá.",
        "fr": "Au-dessus d'une visionneuse plein écran, rester devant sans lui prendre les touches : vous tournez les pages là-bas.",
        "de": "Über einem Viewer im Vollbild oben bleiben, ohne ihm die Tasten zu nehmen: Sie blättern dort um.",
        "it": "Sopra un visualizzatore a schermo intero, restare in primo piano senza togliergli i tasti: giri le pagine lì.",
        "nl": "Boven een viewer op volledig scherm blijven zonder hem de toetsen af te nemen: u bladert daar om.",
        "pl": "Nad czytnikiem na pełnym ekranie zostań na wierzchu, nie zabierając mu klawiszy: strony przewracasz w nim.",
        "ru": "Над полноэкранным просмотрщиком оставаться сверху, не забирая у него клавиши: страницы листаете в нём.",
        "tr": "Tam ekran bir görüntüleyicinin üstünde, tuşlarını almadan önde kal: sayfaları orada çevirirsiniz.",
        "id": "Di atas penampil layar penuh, tetap di depan tanpa mengambil tombolnya: Anda membalik halaman di sana.",
        "vi": "Trên trình xem toàn màn hình, nằm trên cùng mà không lấy phím của nó: bạn lật trang ở đó.",
        "zh": "在全屏查看器之上保持置顶，但不夺取它的按键：翻页在查看器中进行。",
        "zh-tw": "在全螢幕檢視器之上保持置頂，但不奪取它的按鍵：翻頁在檢視器中進行。",
        "ko": "전체 화면 뷰어 위에 떠 있되 키는 가져오지 않습니다. 페이지는 뷰어에서 넘깁니다.",
        "th": "อยู่ด้านบนโปรแกรมอ่านแบบเต็มจอโดยไม่แย่งปุ่มของมัน: คุณพลิกหน้าในโปรแกรมอ่าน",
    },
    "TASlation stays over the full-screen viewer: your keys go to the book, and F5 still translates. View > Over the full-screen viewer turns this off.": {
        code: text.format(menu=_menu(code)) for code, text in _STARTED.items()
    },
    "The browser did not take the key: click the book and turn the page there.": {
        "ja": "ブラウザがキーを受け取りませんでした。本をクリックして、そちらでページをめくってください。",
        "es": "El navegador no recibió la tecla: haz clic en el libro y pasa la página allí.",
        "pt": "O navegador não recebeu a tecla: clique no livro e vire a página lá.",
        "fr": "Le navigateur n'a pas reçu la touche : cliquez sur le livre et tournez la page là-bas.",
        "de": "Der Browser hat die Taste nicht angenommen: Klicken Sie auf das Buch und blättern Sie dort um.",
        "it": "Il browser non ha ricevuto il tasto: fai clic sul libro e gira la pagina lì.",
        "nl": "De browser kreeg de toets niet: klik op het boek en sla daar de pagina om.",
        "pl": "Przeglądarka nie przyjęła klawisza: kliknij książkę i przewróć stronę w niej.",
        "ru": "Браузер не принял клавишу: щёлкните по книге и переверните страницу там.",
        "tr": "Tarayıcı tuşu almadı: kitaba tıklayın ve sayfayı orada çevirin.",
        "id": "Peramban tidak menerima tombol: klik buku dan balik halamannya di sana.",
        "vi": "Trình duyệt không nhận phím: hãy nhấp vào cuốn sách và lật trang ở đó.",
        "zh": "浏览器没有接收到按键：请点击书本，在那里翻页。",
        "zh-tw": "瀏覽器沒有接收到按鍵：請點按書本，在那裡翻頁。",
        "ko": "브라우저가 키를 받지 않았습니다. 책을 클릭하고 거기서 페이지를 넘기세요.",
        "th": "เบราว์เซอร์ไม่ได้รับปุ่ม: คลิกที่หนังสือแล้วพลิกหน้าที่นั่น",
    },
    "With the viewer in full screen on TASlation's monitor, TASlation stays on top of it without taking its keys, as the on-screen keyboard does: turn the pages in the viewer as usual and TASlation follows. F5 still translates, and in reading mode F11 and Esc leave it.": {
        "ja": "ビューアが TASlation と同じモニターで全画面のとき、TASlation はスクリーン キーボードのように、キー操作を奪わずにその上に表示されます。いつもどおりビューアでページをめくれば、TASlation がついてきます。F5 での翻訳も使え、読書モードでは F11 か Esc で終了します。",
        "es": "Con el visor a pantalla completa en el monitor de TASlation, TASlation se queda encima sin quitarle las teclas, como el teclado en pantalla: pasa las páginas en el visor como siempre y TASlation te sigue. F5 sigue traduciendo, y en el modo de lectura F11 y Esc lo cierran.",
        "pt": "Com o visualizador em tela cheia no monitor do TASlation, o TASlation fica por cima sem tirar as teclas dele, como o teclado virtual: vire as páginas no visualizador como sempre e o TASlation acompanha. F5 continua traduzindo, e no modo de leitura F11 e Esc saem dele.",
        "fr": "Quand la visionneuse est en plein écran sur l'écran de TASlation, TASlation reste au-dessus sans lui prendre les touches, comme le clavier visuel : tournez les pages dans la visionneuse comme d'habitude et TASlation suit. F5 traduit toujours, et en mode lecture F11 et Échap le quittent.",
        "de": "Ist der Viewer im Vollbild auf dem Bildschirm von TASlation, bleibt TASlation darüber, ohne ihm die Tasten zu nehmen, wie die Bildschirmtastatur: Blättern Sie wie gewohnt im Viewer um, TASlation folgt. F5 übersetzt weiterhin, und im Lesemodus beenden F11 und Esc ihn.",
        "it": "Con il visualizzatore a schermo intero sul monitor di TASlation, TASlation resta sopra senza togliergli i tasti, come la tastiera su schermo: gira le pagine nel visualizzatore come sempre e TASlation ti segue. F5 traduce ancora, e nella modalità lettura F11 ed Esc la chiudono.",
        "nl": "Staat de viewer op volledig scherm op de monitor van TASlation, dan blijft TASlation erboven zonder hem de toetsen af te nemen, zoals het schermtoetsenbord: sla de pagina's in de viewer om zoals altijd en TASlation volgt. F5 vertaalt nog steeds, en in de leesmodus sluiten F11 en Esc die af.",
        "pl": "Gdy czytnik jest na pełnym ekranie na monitorze TASlation, TASlation zostaje nad nim, nie zabierając mu klawiszy, jak klawiatura ekranowa: przewracaj strony w czytniku jak zwykle, a TASlation podąża za tobą. F5 nadal tłumaczy, a w trybie czytania F11 i Esc go zamykają.",
        "ru": "Когда просмотрщик развёрнут на весь экран на мониторе TASlation, TASlation остаётся поверх него, не забирая клавиши, как экранная клавиатура: листайте страницы в просмотрщике как обычно, и TASlation следует за вами. F5 по-прежнему переводит, а в режиме чтения F11 и Esc выходят из него.",
        "tr": "Görüntüleyici TASlation'ın monitöründe tam ekranken TASlation, ekran klavyesi gibi tuşlarını almadan onun üstünde kalır: sayfaları her zamanki gibi görüntüleyicide çevirin, TASlation sizi izler. F5 yine çevirir; okuma kipinde F11 ve Esc kipten çıkar.",
        "id": "Saat penampil layar penuh di monitor TASlation, TASlation tetap di atasnya tanpa mengambil tombolnya, seperti keyboard di layar: balik halaman di penampil seperti biasa dan TASlation mengikuti. F5 tetap menerjemahkan, dan di mode baca F11 dan Esc keluar darinya.",
        "vi": "Khi trình xem ở chế độ toàn màn hình trên màn hình của TASlation, TASlation nằm trên nó mà không lấy phím, giống bàn phím ảo: cứ lật trang trong trình xem như thường và TASlation theo kịp. F5 vẫn dịch, và trong chế độ đọc F11 và Esc thoát khỏi chế độ đó.",
        "zh": "查看器在 TASlation 所在的显示器上全屏时，TASlation 会像屏幕键盘一样置于其上而不夺取按键：照常在查看器中翻页，TASlation 会跟上。F5 仍可翻译，在阅读模式中按 F11 或 Esc 退出。",
        "zh-tw": "檢視器在 TASlation 所在的螢幕上全螢幕時，TASlation 會像螢幕小鍵盤一樣置於其上而不奪取按鍵：照常在檢視器中翻頁，TASlation 會跟上。F5 仍可翻譯，在閱讀模式中按 F11 或 Esc 離開。",
        "ko": "뷰어가 TASlation과 같은 모니터에서 전체 화면일 때, TASlation은 화상 키보드처럼 키를 가져오지 않고 그 위에 떠 있습니다. 평소처럼 뷰어에서 페이지를 넘기면 TASlation이 따라갑니다. F5로 번역할 수 있고, 읽기 모드에서는 F11이나 Esc로 나갑니다.",
        "th": "เมื่อโปรแกรมอ่านเต็มจอบนจอเดียวกับ TASlation, TASlation จะอยู่ด้านบนโดยไม่แย่งปุ่มของมัน เหมือนแป้นพิมพ์บนหน้าจอ: พลิกหน้าในโปรแกรมอ่านตามปกติแล้ว TASlation จะตามไป F5 ยังแปลได้ และในโหมดอ่าน F11 หรือ Esc จะออกจากโหมด",
    },
    "Clicks on TASlation's buttons and page strip work as ever. A box you type in, and every dialog, takes the keys while you use it. View > Over the full-screen viewer turns this off; with the book on another monitor nothing changes.": {
        code: text.format(menu=_menu(code)) for code, text in _HELP_OFF.items()
    },
}

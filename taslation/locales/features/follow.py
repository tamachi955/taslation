"""The window's strings for following the viewer and for the full screen's messages: the band shown while the viewer
stops drawing behind TASlation, the line while the browser window shows another tab, Set area... offered before
the full screen, the area set by hand in words, the keys passed on to the viewer by their names, and the line
when a key pressed for real made the viewer turn two pages."""

TEXTS: dict[str, dict[str, str]] = {
    "Waiting: the browser shows another tab. Bring the book's tab back, or drag that tab out into a window of its own.": {
        "ja": "待機中: ブラウザが別のタブを表示しています。本のタブに戻すか、そのタブをドラッグして別のウィンドウにしてください。",
        "es": "En espera: el navegador muestra otra pestaña. Vuelve a la pestaña del libro o arrastra esa pestaña a una ventana propia.",
        "pt": "Aguardando: o navegador mostra outra aba. Volte à aba do livro ou arraste aquela aba para uma janela própria.",
        "fr": "En attente : le navigateur affiche un autre onglet. Revenez à l'onglet du livre, ou faites glisser cet onglet dans une fenêtre à part.",
        "de": "Warten: Der Browser zeigt einen anderen Tab. Holen Sie den Tab des Buchs zurück oder ziehen Sie diesen Tab in ein eigenes Fenster.",
        "it": "In attesa: il browser mostra un'altra scheda. Torna alla scheda del libro, oppure trascina quella scheda in una finestra propria.",
        "nl": "Wachten: de browser toont een ander tabblad. Haal het tabblad van het boek terug, of sleep dat tabblad naar een eigen venster.",
        "pl": "Oczekiwanie: przeglądarka pokazuje inną kartę. Wróć do karty książki albo przeciągnij tamtą kartę do osobnego okna.",
        "ru": "Ожидание: браузер показывает другую вкладку. Вернитесь на вкладку книги или перетащите ту вкладку в отдельное окно.",
        "tr": "Bekleniyor: tarayıcı başka bir sekme gösteriyor. Kitabın sekmesine dönün ya da o sekmeyi kendi penceresine sürükleyin.",
        "id": "Menunggu: peramban menampilkan tab lain. Kembali ke tab buku, atau seret tab itu ke jendelanya sendiri.",
        "vi": "Đang chờ: trình duyệt hiện tab khác. Hãy quay lại tab của sách, hoặc kéo tab đó ra cửa sổ riêng.",
        "zh": "等待中：浏览器显示的是另一个标签页。请切回书的标签页，或把那个标签页拖到单独的窗口。",
        "zh-tw": "等待中：瀏覽器顯示的是另一個分頁。請切回書的分頁，或把那個分頁拖到單獨的視窗。",
        "ko": "대기 중: 브라우저가 다른 탭을 보여 주고 있습니다. 책 탭으로 돌아가거나 그 탭을 끌어내 별도의 창으로 만드세요.",
        "th": "กำลังรอ: เบราว์เซอร์แสดงแท็บอื่น กลับไปที่แท็บของหนังสือ หรือลากแท็บนั้นออกเป็นหน้าต่างของตัวเอง",
    },
    # the area set by hand, in words: "{area}" is the edges below, joined by "{a}, {b}"
    "Viewer: {title}  (area set)": {
        "ja": "ビューア: {title}（範囲設定済み）",
        "es": "Visor: {title}  (área definida)",
        "pt": "Visualizador: {title}  (área definida)",
        "fr": "Visionneuse : {title}  (zone définie)",
        "de": "Viewer: {title}  (Bereich festgelegt)",
        "it": "Visualizzatore: {title}  (area impostata)",
        "nl": "Viewer: {title}  (gebied ingesteld)",
        "pl": "Czytnik: {title}  (obszar ustawiony)",
        "ru": "Просмотрщик: {title}  (область задана)",
        "tr": "Görüntüleyici: {title}  (alan belirlendi)",
        "id": "Penampil: {title}  (area diatur)",
        "vi": "Trình xem: {title}  (đã đặt vùng)",
        "zh": "查看器：{title}（已设置区域）",
        "zh-tw": "檢視器：{title}（已設定區域）",
        "ko": "뷰어: {title}  (영역 설정됨)",
        "th": "โปรแกรมอ่าน: {title}  (กำหนดพื้นที่แล้ว)",
    },
    "Area set. Only this part of the viewer is read.": {
        "ja": "範囲を設定しました。ビューアのこの部分だけを読みます。",
        "es": "Área definida. Solo se lee esta parte del visor.",
        "pt": "Área definida. Só esta parte do visualizador é lida.",
        "fr": "Zone définie. Seule cette partie de la visionneuse est lue.",
        "de": "Bereich gesetzt. Nur dieser Teil des Viewers wird gelesen.",
        "it": "Area impostata. Viene letta solo questa parte del visualizzatore.",
        "nl": "Gebied ingesteld. Alleen dit deel van de viewer wordt gelezen.",
        "pl": "Obszar ustawiony. Czytana jest tylko ta część czytnika.",
        "ru": "Область задана. Читается только эта часть просмотрщика.",
        "tr": "Alan belirlendi. Görüntüleyicinin yalnızca bu kısmı okunur.",
        "id": "Area diatur. Hanya bagian penampil ini yang dibaca.",
        "vi": "Đã đặt vùng. Chỉ phần này của trình xem được đọc.",
        "zh": "已设置区域。只读取查看器的这一部分。",
        "zh-tw": "已設定區域。只讀取檢視器的這一部分。",
        "ko": "영역 설정됨. 뷰어의 이 부분만 읽습니다.",
        "th": "กำหนดพื้นที่แล้ว จะอ่านเฉพาะส่วนนี้ของโปรแกรมอ่าน",
    },
    # the keys passed on to the viewer, as the window names them (the arrow keys are arrows in every language)
    "Page Up": {
        "ja": "PageUp", "es": "Re Pág", "pt": "Page Up", "fr": "Pg préc", "de": "Bild auf", "it": "Pag su",
        "nl": "Page Up", "pl": "Page Up", "ru": "Page Up", "tr": "Page Up", "id": "Page Up", "vi": "Page Up",
        "zh": "PageUp", "zh-tw": "PageUp", "ko": "Page Up",
        "th": "Page Up",
    },
    "Page Down": {
        "ja": "PageDown", "es": "Av Pág", "pt": "Page Down", "fr": "Pg suiv", "de": "Bild ab", "it": "Pag giù",
        "nl": "Page Down", "pl": "Page Down", "ru": "Page Down", "tr": "Page Down", "id": "Page Down",
        "vi": "Page Down", "zh": "PageDown", "zh-tw": "PageDown", "ko": "Page Down",
        "th": "Page Down",
    },
    "Home": {
        "ja": "Home", "es": "Inicio", "pt": "Home", "fr": "Début", "de": "Pos1", "it": "Inizio", "nl": "Home",
        "pl": "Home", "ru": "Home", "tr": "Home", "id": "Home", "vi": "Home", "zh": "Home", "zh-tw": "Home",
        "ko": "Home",
        "th": "Home",
    },
    "End": {
        "ja": "End", "es": "Fin", "pt": "End", "fr": "Fin", "de": "Ende", "it": "Fine", "nl": "End", "pl": "End",
        "ru": "End", "tr": "End", "id": "End", "vi": "End", "zh": "End", "zh-tw": "End", "ko": "End",
        "th": "End",
    },
    "Space": {
        "ja": "スペース", "es": "Espacio", "pt": "Espaço", "fr": "Espace", "de": "Leertaste", "it": "Spazio",
        "nl": "Spatiebalk", "pl": "Spacja", "ru": "Пробел", "tr": "Boşluk", "id": "Spasi", "vi": "Phím cách",
        "zh": "空格键", "zh-tw": "空白鍵", "ko": "스페이스",
        "th": "Space",
    },
    # a key pressed for real after the posted one seemed lost, and the page turned twice: {key} turns back one page
}

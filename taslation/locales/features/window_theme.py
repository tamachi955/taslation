"""The window's strings for its colours in the Settings dialog (`ui.dialogs.settings`, `ui.theme`): the row's label,
its three choices, its tip, and the line said while Windows' high contrast is on. The choices agree with the label
where a language makes them (ru «Цвета: Светлые», fr « Couleurs : Claires »); Windows' own words for its settings as
its translations have them (ja 「アプリ モード」「ハイ コントラスト」, de „hoher Kontrast“).

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "Colours:": {
        "ja": "配色:", "es": "Colores:", "pt": "Cores:", "fr": "Couleurs :", "de": "Farben:", "it": "Colori:",
        "nl": "Kleuren:", "pl": "Kolory:", "ru": "Цвета:", "tr": "Renkler:", "id": "Warna:", "vi": "Màu:",
        "zh": "配色：", "zh-tw": "配色：", "ko": "색:", "th": "สี:",
    },
    "As Windows is set": {
        "ja": "Windows の設定に合わせる", "es": "Como en Windows", "pt": "Como no Windows", "fr": "Comme Windows",
        "de": "Wie Windows", "it": "Come Windows", "nl": "Zoals Windows", "pl": "Jak w Windows", "ru": "Как в Windows",
        "tr": "Windows'taki gibi", "id": "Sesuai Windows", "vi": "Theo Windows", "zh": "跟随 Windows",
        "zh-tw": "跟隨 Windows", "ko": "Windows 설정대로", "th": "ตาม Windows",
    },
    "Light": {
        "ja": "ライト", "es": "Claros", "pt": "Claras", "fr": "Claires", "de": "Hell", "it": "Chiari", "nl": "Licht",
        "pl": "Jasne", "ru": "Светлые", "tr": "Açık", "id": "Terang", "vi": "Sáng", "zh": "浅色", "zh-tw": "淺色",
        "ko": "밝게", "th": "สว่าง",
    },
    "Dark": {
        "ja": "ダーク", "es": "Oscuros", "pt": "Escuras", "fr": "Sombres", "de": "Dunkel", "it": "Scuri", "nl": "Donker",
        "pl": "Ciemne", "ru": "Тёмные", "tr": "Koyu", "id": "Gelap", "vi": "Tối", "zh": "深色", "zh-tw": "深色",
        "ko": "어둡게", "th": "มืด",
    },
    "The dialogs' colours: light, dark, or as Windows has them for apps (the app mode in Windows' colour settings). The side panes take theirs from the ground of the page in the viewer. While Windows' high contrast is on, the dialogs take Windows' colours.": {
        'ja': 'ダイアログの配色です。ライト、ダーク、または Windows のアプリの設定（Windows の色の設定のアプリ モード）に合わせます。左右のパネルの色は、ビューアのページの地の色に合わせます。Windows のハイ コントラストがオンのあいだは、ダイアログは Windows の色を使います。',
        'es': 'Los colores de los diálogos: claros, oscuros o como Windows los tiene para las aplicaciones (el modo de aplicación de la configuración de color de Windows). Los paneles laterales toman los suyos del fondo de la página en el visor. Mientras el contraste alto de Windows está activado, los diálogos usan los colores de Windows.',
        'pt': 'As cores das caixas de diálogo: claras, escuras ou como o Windows as tem para os aplicativos (o modo de aplicativo nas configurações de cor do Windows). Os painéis laterais tomam as suas do fundo da página no visualizador. Enquanto o alto contraste do Windows estiver ativado, as caixas de diálogo usam as cores do Windows.',
        'fr': 'Les couleurs des boîtes de dialogue : claires, sombres, ou comme Windows les règle pour les applications (le mode des applications dans les paramètres de couleur de Windows). Les volets latéraux prennent les leurs du fond de la page dans la visionneuse. Tant que le contraste élevé de Windows est activé, les boîtes de dialogue prennent les couleurs de Windows.',
        'de': 'Die Farben der Dialoge: hell, dunkel oder wie Windows sie für Apps eingestellt hat (der App-Modus in den Farbeinstellungen von Windows). Die Seitenbereiche nehmen ihre vom Hintergrund der Seite im Viewer. Solange der hohe Kontrast von Windows eingeschaltet ist, nehmen die Dialoge die Farben von Windows.',
        'it': 'I colori delle finestre di dialogo: chiari, scuri o come Windows li imposta per le app (la modalità app nelle impostazioni dei colori di Windows). I pannelli laterali prendono i loro dallo sfondo della pagina nel visualizzatore. Finché il contrasto elevato di Windows è attivo, le finestre di dialogo usano i colori di Windows.',
        'nl': 'De kleuren van de dialoogvensters: licht, donker of zoals Windows ze voor apps heeft ingesteld (de app-modus in de kleurinstellingen van Windows). De zijpanelen nemen de hunne van de achtergrond van de pagina in de viewer. Zolang het hoge contrast van Windows aan staat, nemen de dialoogvensters de kleuren van Windows.',
        'pl': 'Kolory okien dialogowych: jasne, ciemne lub takie, jakie Windows ustawia dla aplikacji (tryb aplikacji w ustawieniach kolorów Windows). Panele boczne biorą swoje z tła strony w czytniku. Gdy w Windows włączony jest duży kontrast, okna dialogowe przyjmują kolory Windows.',
        'ru': 'Цвета диалоговых окон: светлые, тёмные или как в Windows для приложений (режим приложений в настройках цвета Windows). Боковые панели берут свои от фона страницы в программе просмотра. Пока в Windows включена высокая контрастность, диалоговые окна берут цвета Windows.',
        'tr': "İletişim kutularının renkleri: açık, koyu ya da Windows'un uygulamalar için ayarladığı gibi (Windows renk ayarlarındaki uygulama modu). Yan bölmeler renklerini görüntüleyicideki sayfanın zemininden alır. Windows'ta yüksek karşıtlık açıkken iletişim kutuları Windows'un renklerini alır.",
        'id': 'Warna dialog: terang, gelap, atau sesuai pengaturan Windows untuk aplikasi (mode aplikasi di pengaturan warna Windows). Panel samping mengambil warnanya dari latar halaman di penampil. Selama kontras tinggi Windows aktif, dialog memakai warna Windows.',
        'vi': 'Màu của các hộp thoại: sáng, tối, hoặc theo cách Windows đặt cho ứng dụng (chế độ ứng dụng trong cài đặt màu của Windows). Các khung bên lấy màu theo nền của trang trong trình xem. Khi độ tương phản cao của Windows đang bật, các hộp thoại dùng màu của Windows.',
        'zh': '对话框的配色：浅色、深色，或跟随 Windows 为应用设置的模式（Windows 颜色设置中的应用模式）。两侧窗格的颜色取自查看器中页面的底色。Windows 的高对比度打开时，对话框使用 Windows 的颜色。',
        'zh-tw': '對話方塊的配色：淺色、深色，或跟隨 Windows 為應用程式設定的模式（Windows 色彩設定中的應用程式模式）。兩側窗格的顏色取自檢視器中頁面的底色。Windows 的高對比開啟時，對話方塊使用 Windows 的色彩。',
        'ko': '대화 상자의 색입니다. 밝게, 어둡게, 또는 Windows가 앱에 설정한 대로(Windows 색 설정의 앱 모드) 표시합니다. 양쪽 패널의 색은 뷰어에 있는 페이지의 바탕에서 가져옵니다. Windows의 고대비가 켜져 있는 동안에는 대화 상자가 Windows의 색을 씁니다.',
        'th': 'สีของกล่องโต้ตอบ: สว่าง มืด หรือตามที่ Windows ตั้งไว้สำหรับแอป (โหมดแอปในการตั้งค่าสีของ Windows) แผงด้านข้างใช้สีตามพื้นของหน้าในโปรแกรมอ่าน ระหว่างที่เปิดคอนทราสต์สูงของ Windows กล่องโต้ตอบจะใช้สีของ Windows',
    },
    "Windows' high contrast is on: the dialogs take Windows' colours.": {
        'ja': 'Windows のハイ コントラストがオンです。ダイアログは Windows の色を使います。',
        'es': 'El contraste alto de Windows está activado: los diálogos usan los colores de Windows.',
        'pt': 'O alto contraste do Windows está ativado: as caixas de diálogo usam as cores do Windows.',
        'fr': 'Le contraste élevé de Windows est activé : les boîtes de dialogue prennent les couleurs de Windows.',
        'de': 'Der hohe Kontrast von Windows ist eingeschaltet: Die Dialoge nehmen die Farben von Windows.',
        'it': 'Il contrasto elevato di Windows è attivo: le finestre di dialogo usano i colori di Windows.',
        'nl': 'Het hoge contrast van Windows staat aan: de dialoogvensters nemen de kleuren van Windows.',
        'pl': 'W Windows włączony jest duży kontrast: okna dialogowe przyjmują kolory Windows.',
        'ru': 'В Windows включена высокая контрастность: диалоговые окна берут цвета Windows.',
        'tr': "Windows'ta yüksek karşıtlık açık: iletişim kutuları Windows'un renklerini alır.",
        'id': 'Kontras tinggi Windows aktif: dialog memakai warna Windows.',
        'vi': 'Độ tương phản cao của Windows đang bật: các hộp thoại dùng màu của Windows.',
        'zh': 'Windows 的高对比度已打开：对话框使用 Windows 的颜色。',
        'zh-tw': 'Windows 的高對比已開啟：對話方塊使用 Windows 的色彩。',
        'ko': 'Windows의 고대비가 켜져 있습니다. 대화 상자는 Windows의 색을 씁니다.',
        'th': 'เปิดคอนทราสต์สูงของ Windows อยู่: กล่องโต้ตอบใช้สีของ Windows',
    },
}

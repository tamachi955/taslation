"""The window's strings for one place per command: the hint that says where Set area... is (the left pane), the region editor's
fold of its formatting bar, the help's lines on where things went, and the 20 target languages by their names in the
window's language (the "To:" box: what is kept and what the model is told stay the English names, `constants.LANGUAGES`).

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "No area is set for this viewer: Set area... in the Menu lets you drag a rectangle around the page.": {
        "ja": "このビューアには範囲が設定されていません。「メニュー」の「範囲設定...」でページの周りに矩形をドラッグして指定できます。",
        "es": "Este visor no tiene área definida: Definir área..., en el Menú, te deja arrastrar un rectángulo alrededor de la página.",
        "pt": "Este visualizador não tem área definida: Definir área..., no Menu, deixa você arrastar um retângulo em volta da página.",
        "fr": "Aucune zone n'est définie pour cette visionneuse : Définir la zone..., dans le Menu, permet de tracer un rectangle autour de la page.",
        "de": "Für diesen Viewer ist kein Bereich gesetzt: Mit „Bereich festlegen...“ im Menü ziehen Sie ein Rechteck um die Seite.",
        "it": "Per questo visualizzatore non è impostata un'area: Imposta area..., nel Menu, ti fa trascinare un rettangolo attorno alla pagina.",
        "nl": "Voor deze viewer is geen gebied ingesteld: met Gebied instellen... in het Menu sleept u een rechthoek om de pagina.",
        "pl": "Dla tego czytnika nie ustawiono obszaru: Ustaw obszar... w Menu pozwala przeciągnąć prostokąt wokół strony.",
        "ru": "Для этого просмотрщика область не задана: «Задать область...» в «Меню» позволяет обвести страницу прямоугольником.",
        "tr": "Bu görüntüleyici için alan belirlenmedi: Menü'deki Alan belirle... ile sayfanın etrafına bir dikdörtgen sürükleyebilirsiniz.",
        "id": "Belum ada area untuk penampil ini: Atur area... di Menu memungkinkan Anda menyeret persegi di sekitar halaman.",
        "vi": "Trình xem này chưa đặt vùng: Đặt vùng... trong Menu cho phép kéo một hình chữ nhật quanh trang.",
        "zh": "此查看器尚未设置区域：用“菜单”中的“设置区域...”可在页面周围拖出矩形。",
        "zh-tw": "此檢視器尚未設定區域：用「選單」中的「設定區域...」可在頁面周圍拖出矩形。",
        "ko": "이 뷰어에는 영역이 설정되지 않았습니다. 메뉴의 영역 설정...으로 페이지 주위에 사각형을 드래그할 수 있습니다.",
        "th": "ยังไม่ได้กำหนดพื้นที่สำหรับโปรแกรมอ่านนี้: “กำหนดพื้นที่...” ในเมนูให้คุณลากสี่เหลี่ยมล้อมรอบหน้าได้",
    },
    "Formatting": {
        "ja": "書式",
        "es": "Formato",
        "pt": "Formatação",
        "fr": "Mise en forme",
        "de": "Formatierung",
        "it": "Formattazione",
        "nl": "Opmaak",
        "pl": "Formatowanie",
        "ru": "Форматирование",
        "tr": "Biçimlendirme",
        "id": "Format",
        "vi": "Định dạng",
        "zh": "格式",
        "zh-tw": "格式",
        "ko": "서식",
        "th": "รูปแบบ",
    },
    "English": {
        "ja": "英語", "es": "Inglés", "pt": "Inglês", "fr": "Anglais", "de": "Englisch", "it": "Inglese", "nl": "Engels",
        "pl": "Angielski", "ru": "Английский", "tr": "İngilizce", "id": "Inggris", "vi": "Tiếng Anh", "zh": "英语",
        "zh-tw": "英語", "ko": "영어", "th": "อังกฤษ",
    },
    "Spanish": {
        "ja": "スペイン語", "es": "Español", "pt": "Espanhol", "fr": "Espagnol", "de": "Spanisch", "it": "Spagnolo",
        "nl": "Spaans", "pl": "Hiszpański", "ru": "Испанский", "tr": "İspanyolca", "id": "Spanyol", "vi": "Tiếng Tây Ban Nha",
        "zh": "西班牙语", "zh-tw": "西班牙語", "ko": "스페인어", "th": "สเปน",
    },
    "Portuguese (Brazil)": {
        "ja": "ポルトガル語（ブラジル）", "es": "Portugués (Brasil)", "pt": "Português (Brasil)", "fr": "Portugais (Brésil)",
        "de": "Portugiesisch (Brasilien)", "it": "Portoghese (Brasile)", "nl": "Portugees (Brazilië)",
        "pl": "Portugalski (Brazylia)", "ru": "Португальский (Бразилия)", "tr": "Portekizce (Brezilya)",
        "id": "Portugis (Brasil)", "vi": "Tiếng Bồ Đào Nha (Brazil)", "zh": "葡萄牙语（巴西）", "zh-tw": "葡萄牙語（巴西）",
        "ko": "포르투갈어(브라질)", "th": "โปรตุเกส (บราซิล)",
    },
    "French": {
        "ja": "フランス語", "es": "Francés", "pt": "Francês", "fr": "Français", "de": "Französisch", "it": "Francese",
        "nl": "Frans", "pl": "Francuski", "ru": "Французский", "tr": "Fransızca", "id": "Prancis", "vi": "Tiếng Pháp",
        "zh": "法语", "zh-tw": "法語", "ko": "프랑스어", "th": "ฝรั่งเศส",
    },
    "German": {
        "ja": "ドイツ語", "es": "Alemán", "pt": "Alemão", "fr": "Allemand", "de": "Deutsch", "it": "Tedesco", "nl": "Duits",
        "pl": "Niemiecki", "ru": "Немецкий", "tr": "Almanca", "id": "Jerman", "vi": "Tiếng Đức", "zh": "德语", "zh-tw": "德語",
        "ko": "독일어", "th": "เยอรมัน",
    },
    "Italian": {
        "ja": "イタリア語", "es": "Italiano", "pt": "Italiano", "fr": "Italien", "de": "Italienisch", "it": "Italiano",
        "nl": "Italiaans", "pl": "Włoski", "ru": "Итальянский", "tr": "İtalyanca", "id": "Italia", "vi": "Tiếng Ý",
        "zh": "意大利语", "zh-tw": "義大利語", "ko": "이탈리아어", "th": "อิตาลี",
    },
    "Russian": {
        "ja": "ロシア語", "es": "Ruso", "pt": "Russo", "fr": "Russe", "de": "Russisch", "it": "Russo", "nl": "Russisch",
        "pl": "Rosyjski", "ru": "Русский", "tr": "Rusça", "id": "Rusia", "vi": "Tiếng Nga", "zh": "俄语", "zh-tw": "俄語",
        "ko": "러시아어", "th": "รัสเซีย",
    },
    "Polish": {
        "ja": "ポーランド語", "es": "Polaco", "pt": "Polonês", "fr": "Polonais", "de": "Polnisch", "it": "Polacco",
        "nl": "Pools", "pl": "Polski", "ru": "Польский", "tr": "Polonyaca", "id": "Polandia", "vi": "Tiếng Ba Lan",
        "zh": "波兰语", "zh-tw": "波蘭語", "ko": "폴란드어", "th": "โปแลนด์",
    },
    "Dutch": {
        "ja": "オランダ語", "es": "Neerlandés", "pt": "Holandês", "fr": "Néerlandais", "de": "Niederländisch",
        "it": "Olandese", "nl": "Nederlands", "pl": "Niderlandzki", "ru": "Нидерландский", "tr": "Felemenkçe",
        "id": "Belanda", "vi": "Tiếng Hà Lan", "zh": "荷兰语", "zh-tw": "荷蘭語", "ko": "네덜란드어", "th": "ดัตช์",
    },
    "Turkish": {
        "ja": "トルコ語", "es": "Turco", "pt": "Turco", "fr": "Turc", "de": "Türkisch", "it": "Turco", "nl": "Turks",
        "pl": "Turecki", "ru": "Турецкий", "tr": "Türkçe", "id": "Turki", "vi": "Tiếng Thổ Nhĩ Kỳ", "zh": "土耳其语",
        "zh-tw": "土耳其語", "ko": "튀르키예어", "th": "ตุรกี",
    },
    "Indonesian": {
        "ja": "インドネシア語", "es": "Indonesio", "pt": "Indonésio", "fr": "Indonésien", "de": "Indonesisch",
        "it": "Indonesiano", "nl": "Indonesisch", "pl": "Indonezyjski", "ru": "Индонезийский", "tr": "Endonezce",
        "id": "Bahasa Indonesia", "vi": "Tiếng Indonesia", "zh": "印度尼西亚语", "zh-tw": "印尼語", "ko": "인도네시아어",
        "th": "อินโดนีเซีย",
    },
    "Vietnamese": {
        "ja": "ベトナム語", "es": "Vietnamita", "pt": "Vietnamita", "fr": "Vietnamien", "de": "Vietnamesisch",
        "it": "Vietnamita", "nl": "Vietnamees", "pl": "Wietnamski", "ru": "Вьетнамский", "tr": "Vietnamca", "id": "Vietnam",
        "vi": "Tiếng Việt", "zh": "越南语", "zh-tw": "越南語", "ko": "베트남어", "th": "เวียดนาม",
    },
    "Thai": {
        "ja": "タイ語", "es": "Tailandés", "pt": "Tailandês", "fr": "Thaï", "de": "Thailändisch", "it": "Tailandese",
        "nl": "Thai", "pl": "Tajski", "ru": "Тайский", "tr": "Tayca", "id": "Thai", "vi": "Tiếng Thái", "zh": "泰语",
        "zh-tw": "泰語", "ko": "태국어", "th": "ไทย",
    },
    "Chinese (Simplified)": {
        "ja": "中国語（簡体字）", "es": "Chino (simplificado)", "pt": "Chinês (simplificado)", "fr": "Chinois (simplifié)",
        "de": "Chinesisch (vereinfacht)", "it": "Cinese (semplificato)", "nl": "Chinees (vereenvoudigd)",
        "pl": "Chiński (uproszczony)", "ru": "Китайский (упрощённый)", "tr": "Çince (Basitleştirilmiş)",
        "id": "Tionghoa (Sederhana)", "vi": "Tiếng Trung (Giản thể)", "zh": "简体中文", "zh-tw": "簡體中文",
        "ko": "중국어(간체)", "th": "จีน (ตัวย่อ)",
    },
    "Chinese (Traditional)": {
        "ja": "中国語（繁体字）", "es": "Chino (tradicional)", "pt": "Chinês (tradicional)", "fr": "Chinois (traditionnel)",
        "de": "Chinesisch (traditionell)", "it": "Cinese (tradizionale)", "nl": "Chinees (traditioneel)",
        "pl": "Chiński (tradycyjny)", "ru": "Китайский (традиционный)", "tr": "Çince (Geleneksel)",
        "id": "Tionghoa (Tradisional)", "vi": "Tiếng Trung (Phồn thể)", "zh": "繁体中文", "zh-tw": "繁體中文",
        "ko": "중국어(번체)", "th": "จีน (ตัวเต็ม)",
    },
    "Korean": {
        "ja": "韓国語", "es": "Coreano", "pt": "Coreano", "fr": "Coréen", "de": "Koreanisch", "it": "Coreano", "nl": "Koreaans",
        "pl": "Koreański", "ru": "Корейский", "tr": "Korece", "id": "Korea", "vi": "Tiếng Hàn", "zh": "韩语", "zh-tw": "韓語",
        "ko": "한국어", "th": "เกาหลี",
    },
    "Arabic": {
        "ja": "アラビア語", "es": "Árabe", "pt": "Árabe", "fr": "Arabe", "de": "Arabisch", "it": "Arabo", "nl": "Arabisch",
        "pl": "Arabski", "ru": "Арабский", "tr": "Arapça", "id": "Arab", "vi": "Tiếng Ả Rập", "zh": "阿拉伯语",
        "zh-tw": "阿拉伯語", "ko": "아랍어", "th": "อาหรับ",
    },
    "Hebrew": {
        "ja": "ヘブライ語", "es": "Hebreo", "pt": "Hebraico", "fr": "Hébreu", "de": "Hebräisch", "it": "Ebraico",
        "nl": "Hebreeuws", "pl": "Hebrajski", "ru": "Иврит", "tr": "İbranice", "id": "Ibrani", "vi": "Tiếng Do Thái",
        "zh": "希伯来语", "zh-tw": "希伯來語", "ko": "히브리어", "th": "ฮีบรู",
    },
    "Hindi": {
        "ja": "ヒンディー語", "es": "Hindi", "pt": "Hindi", "fr": "Hindi", "de": "Hindi", "it": "Hindi", "nl": "Hindi",
        "pl": "Hindi", "ru": "Хинди", "tr": "Hintçe", "id": "Hindi", "vi": "Tiếng Hindi", "zh": "印地语", "zh-tw": "印地語",
        "ko": "힌디어", "th": "ฮินดี",
    },
    "Bengali": {
        "ja": "ベンガル語", "es": "Bengalí", "pt": "Bengali", "fr": "Bengali", "de": "Bengalisch", "it": "Bengalese",
        "nl": "Bengaals", "pl": "Bengalski", "ru": "Бенгальский", "tr": "Bengalce", "id": "Bengali", "vi": "Tiếng Bengal",
        "zh": "孟加拉语", "zh-tw": "孟加拉語", "ko": "벵골어", "th": "เบงกาลี",
    },
}

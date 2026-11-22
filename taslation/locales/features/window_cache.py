"""The window's strings for the window cache of the Ollama TASlation starts (``ollama_window_cache``,
`taslation.ollama_start.server_setup`): the System page's list (on, off) with its line (`ui.dialogs.system_page`), and
what the translator's row there says of the server running now (`devices.window_cache_text`, also printed by
``taslation doctor``). The translation model is worded as in the System page's other lines (ja 「翻訳モデル」).

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "Translator's window cache:": {
        "ja": "翻訳モデルのウィンドウキャッシュ:", "es": "Caché de ventana del traductor:",
        "pt": "Cache de janela do tradutor:", "fr": "Cache de fenêtre du traducteur :",
        "de": "Fenster-Cache des Übersetzers:", "it": "Cache della finestra del traduttore:",
        "nl": "Venstercache van de vertaler:", "pl": "Pamięć podręczna okna tłumacza:", "ru": "Кэш окна переводчика:",
        "tr": "Çevirmenin pencere önbelleği:", "id": "Cache jendela penerjemah:", "vi": "Bộ đệm cửa sổ của trình dịch:",
        "zh": "翻译模型的窗口缓存：", "zh-tw": "翻譯模型的視窗快取：", "ko": "번역 모델의 윈도 캐시:",
        "th": "แคชหน้าต่างของตัวแปล:",
    },
    "On": {
        "ja": "使う", "es": "Activada", "pt": "Ativado", "fr": "Activé", "de": "An", "it": "Attiva", "nl": "Aan",
        "pl": "Włączona", "ru": "Вкл.", "tr": "Açık", "id": "Aktif", "vi": "Bật", "zh": "开启", "zh-tw": "開啟",
        "ko": "켜기", "th": "เปิด",
    },
    "Off": {
        "ja": "使わない", "es": "Desactivada", "pt": "Desativado", "fr": "Désactivé", "de": "Aus", "it": "Disattivata",
        "nl": "Uit", "pl": "Wyłączona", "ru": "Выкл.", "tr": "Kapalı", "id": "Nonaktif", "vi": "Tắt", "zh": "关闭",
        "zh-tw": "關閉", "ko": "끄기", "th": "ปิด",
    },
    "The Ollama TASlation starts keeps the cache of the translation model's whole window, and 256 MB of earlier requests in RAM, so that each request goes on from the last: translation about a quarter faster, for about 130 MB more GPU memory (220 MB on a GPU of more than 6 GB). Not for an Ollama you run yourself. From the next start of Ollama.": {
        "ja": "TASlation が起動する Ollama が、翻訳モデルのウィンドウ全体のキャッシュを持ち、以前の要求 256 MB 分を RAM に置いて、要求ごとに前の要求の続きから計算するようにします。翻訳は約 4 分の 1 速くなり、GPU のメモリーを約 130 MB（6 GB を超える GPU では 220 MB）多く使います。自分で起動した Ollama には効きません。次に Ollama が起動したときから適用されます。",
        "es": "El Ollama que inicia TASlation guarda la caché de toda la ventana del modelo de traducción y 256 MB de peticiones anteriores en la RAM, para que cada petición siga desde la anterior: la traducción es aproximadamente una cuarta parte más rápida, a cambio de unos 130 MB más de memoria de la GPU (220 MB en una GPU de más de 6 GB). No se aplica a un Ollama que usted inicie por su cuenta. Desde el próximo inicio de Ollama.",
        "pt": "O Ollama que o TASlation inicia guarda o cache de toda a janela do modelo de tradução e 256 MB de pedidos anteriores na RAM, para que cada pedido continue a partir do anterior: a tradução fica cerca de um quarto mais rápida, por cerca de 130 MB a mais de memória da GPU (220 MB numa GPU com mais de 6 GB). Não vale para um Ollama que você mesmo inicia. A partir do próximo início do Ollama.",
        "fr": "L'Ollama que TASlation démarre garde le cache de toute la fenêtre du modèle de traduction et 256 Mo de requêtes précédentes en RAM, pour que chaque requête reprenne là où la précédente s'est arrêtée : la traduction est environ un quart plus rapide, pour environ 130 Mo de mémoire GPU en plus (220 Mo sur une GPU de plus de 6 Go). Sans effet sur un Ollama que vous lancez vous-même. À partir du prochain démarrage d'Ollama.",
        "de": "Das Ollama, das TASlation startet, hält den Cache des ganzen Fensters des Übersetzungsmodells und 256 MB früherer Anfragen im RAM, sodass jede Anfrage dort weitermacht, wo die letzte aufgehört hat: Die Übersetzung wird etwa um ein Viertel schneller, für etwa 130 MB mehr GPU-Speicher (220 MB auf einer GPU mit mehr als 6 GB). Nicht für ein Ollama, das Sie selbst starten. Ab dem nächsten Start von Ollama.",
        "it": "L'Ollama avviato da TASlation tiene in RAM la cache dell'intera finestra del modello di traduzione e 256 MB di richieste precedenti, così ogni richiesta riprende da dove si era fermata la precedente: la traduzione è circa un quarto più veloce, al costo di circa 130 MB di memoria della GPU in più (220 MB su una GPU di oltre 6 GB). Non vale per un Ollama avviato da te. Dal prossimo avvio di Ollama.",
        "nl": "De Ollama die TASlation start houdt de cache van het hele venster van het vertaalmodel en 256 MB eerdere verzoeken in het RAM, zodat elk verzoek verdergaat waar het vorige ophield: de vertaling is ongeveer een kwart sneller, voor ongeveer 130 MB meer GPU-geheugen (220 MB op een GPU van meer dan 6 GB). Niet voor een Ollama die u zelf start. Vanaf de volgende start van Ollama.",
        "pl": "Ollama uruchamiana przez TASlation trzyma w RAM pamięć podręczną całego okna modelu tłumaczenia i 256 MB wcześniejszych żądań, tak aby każde żądanie zaczynało od miejsca, w którym skończyło poprzednie: tłumaczenie jest o około jedną czwartą szybsze, kosztem około 130 MB więcej pamięci GPU (220 MB na GPU z więcej niż 6 GB). Nie dotyczy Ollamy uruchamianej przez Ciebie. Od następnego uruchomienia Ollamy.",
        "ru": "Ollama, которую запускает TASlation, держит в RAM кэш всего окна модели перевода и 256 МБ прежних запросов, чтобы каждый запрос продолжал с того места, где остановился предыдущий: перевод примерно на четверть быстрее, ценой примерно 130 МБ дополнительной памяти GPU (220 МБ на GPU больше 6 ГБ). Не действует на Ollama, которую вы запускаете сами. Со следующего запуска Ollama.",
        "tr": "TASlation'ın başlattığı Ollama, çeviri modelinin tüm penceresinin önbelleğini ve önceki isteklerin 256 MB'ını RAM'de tutar; böylece her istek bir öncekinin kaldığı yerden devam eder: çeviri yaklaşık dörtte bir daha hızlıdır, karşılığında yaklaşık 130 MB daha fazla GPU belleği kullanılır (6 GB'tan büyük bir GPU'da 220 MB). Kendiniz başlattığınız bir Ollama için geçerli değildir. Ollama'nın bir sonraki başlatılmasından itibaren.",
        "id": "Ollama yang dijalankan TASlation menyimpan cache seluruh jendela model terjemahan dan 256 MB permintaan sebelumnya di RAM, sehingga setiap permintaan melanjutkan dari permintaan sebelumnya: terjemahan kira-kira seperempat lebih cepat, dengan memakai sekitar 130 MB memori GPU lebih banyak (220 MB pada GPU lebih dari 6 GB). Tidak berlaku untuk Ollama yang Anda jalankan sendiri. Mulai Ollama dijalankan berikutnya.",
        "vi": "Ollama do TASlation khởi động giữ trong RAM bộ đệm của toàn bộ cửa sổ của mô hình dịch và 256 MB yêu cầu trước đó, để mỗi yêu cầu tiếp tục từ yêu cầu trước: dịch nhanh hơn khoảng một phần tư, đổi lại dùng thêm khoảng 130 MB bộ nhớ GPU (220 MB trên GPU trên 6 GB). Không áp dụng cho Ollama bạn tự khởi động. Áp dụng từ lần khởi động Ollama tiếp theo.",
        "zh": "TASlation 启动的 Ollama 会保留翻译模型整个窗口的缓存，并在内存（RAM）中保留 256 MB 的先前请求，使每个请求都从上一个请求接着计算：翻译大约快四分之一，代价是多用约 130 MB 的 GPU 内存（超过 6 GB 的 GPU 上为 220 MB）。对你自己启动的 Ollama 无效。从 Ollama 下次启动起生效。",
        "zh-tw": "TASlation 啟動的 Ollama 會保留翻譯模型整個視窗的快取，並在記憶體（RAM）中保留 256 MB 的先前請求，讓每個請求都從上一個請求接著計算：翻譯大約快四分之一，代價是多用約 130 MB 的 GPU 記憶體（超過 6 GB 的 GPU 上為 220 MB）。對你自己啟動的 Ollama 無效。從 Ollama 下次啟動起生效。",
        "ko": "TASlation이 시작하는 Ollama가 번역 모델의 윈도 전체 캐시와 이전 요청 256 MB를 RAM에 보관해, 각 요청이 이전 요청에 이어서 계산되게 합니다. 번역이 약 4분의 1 빨라지고, GPU 메모리를 약 130 MB(6 GB를 넘는 GPU에서는 220 MB) 더 씁니다. 직접 시작한 Ollama에는 적용되지 않습니다. 다음에 Ollama가 시작될 때부터 적용됩니다.",
        "th": "Ollama ที่ TASlation เริ่มจะเก็บแคชของหน้าต่างทั้งหมดของโมเดลแปล และคำขอก่อนหน้า 256 MB ไว้ใน RAM เพื่อให้แต่ละคำขอคำนวณต่อจากคำขอก่อนหน้า: การแปลเร็วขึ้นราวหนึ่งในสี่ แลกกับหน่วยความจำ GPU ที่ใช้เพิ่มราว 130 MB (220 MB บน GPU ที่มีมากกว่า 6 GB) ไม่มีผลกับ Ollama ที่คุณเริ่มเอง มีผลตั้งแต่ Ollama เริ่มครั้งถัดไป",
    },
    "Started by TASlation with the window cache": {
        "ja": "TASlation が起動（ウィンドウキャッシュあり）", "es": "Iniciado por TASlation con la caché de ventana",
        "pt": "Iniciado pelo TASlation com o cache de janela", "fr": "Démarré par TASlation avec le cache de fenêtre",
        "de": "Von TASlation gestartet, mit dem Fenster-Cache", "it": "Avviato da TASlation con la cache della finestra",
        "nl": "Gestart door TASlation, met de venstercache", "pl": "Uruchomiona przez TASlation z pamięcią podręczną okna",
        "ru": "Запущена TASlation, с кэшем окна", "tr": "TASlation tarafından başlatıldı, pencere önbelleğiyle",
        "id": "Dijalankan oleh TASlation dengan cache jendela", "vi": "Do TASlation khởi động, có bộ đệm cửa sổ",
        "zh": "由 TASlation 启动，带窗口缓存", "zh-tw": "由 TASlation 啟動，帶視窗快取",
        "ko": "TASlation이 시작함(윈도 캐시 사용)", "th": "TASlation เป็นผู้เริ่ม พร้อมแคชหน้าต่าง",
    },
    "Started by TASlation without the window cache": {
        "ja": "TASlation が起動（ウィンドウキャッシュなし）", "es": "Iniciado por TASlation sin la caché de ventana",
        "pt": "Iniciado pelo TASlation sem o cache de janela", "fr": "Démarré par TASlation sans le cache de fenêtre",
        "de": "Von TASlation gestartet, ohne den Fenster-Cache", "it": "Avviato da TASlation senza la cache della finestra",
        "nl": "Gestart door TASlation, zonder de venstercache",
        "pl": "Uruchomiona przez TASlation bez pamięci podręcznej okna", "ru": "Запущена TASlation, без кэша окна",
        "tr": "TASlation tarafından başlatıldı, pencere önbelleği olmadan",
        "id": "Dijalankan oleh TASlation tanpa cache jendela", "vi": "Do TASlation khởi động, không có bộ đệm cửa sổ",
        "zh": "由 TASlation 启动，不带窗口缓存", "zh-tw": "由 TASlation 啟動，不帶視窗快取",
        "ko": "TASlation이 시작함(윈도 캐시 없음)", "th": "TASlation เป็นผู้เริ่ม โดยไม่มีแคชหน้าต่าง",
    },
}

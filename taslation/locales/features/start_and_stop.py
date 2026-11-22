"""The window's strings for the translation model loaded at the start (``load_model_at_start``: its row on the System
page of Tools > Settings..., `ui.dialogs.system_page`). Menus and entries are worded as the window words them (ja
「ツール」「モデルを今すぐ解放」).

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ the model loaded at the start (System page)
    "Load the translation model at start": {
        "ja": "起動時に翻訳モデルを読み込む", "es": "Cargar el modelo de traducción al iniciar",
        "pt": "Carregar o modelo de tradução ao iniciar", "fr": "Charger le modèle de traduction au démarrage",
        "de": "Übersetzungsmodell beim Start laden", "it": "Carica il modello di traduzione all'avvio",
        "nl": "Vertaalmodel laden bij het starten", "pl": "Wczytuj model tłumaczenia przy starcie",
        "ru": "Загружать модель перевода при запуске", "tr": "Çeviri modelini başlangıçta yükle",
        "id": "Muat model terjemahan saat mulai", "vi": "Tải mô hình dịch khi khởi động",
        "zh": "启动时加载翻译模型", "zh-tw": "啟動時載入翻譯模型", "ko": "시작할 때 번역 모델 불러오기",
        "th": "โหลดโมเดลแปลตอนเริ่มโปรแกรม",
    },
    "The translation model loads while TASlation starts, so the first page to translate does not wait a few seconds for it. Off: it loads when the first line to translate comes up. Either way it leaves the GPU after a while without requests (ollama_keep_alive), or at once with Tools > Release the model now. From the next start.": {
        "ja": "TASlation の起動中に翻訳モデルを読み込むので、最初に翻訳するページがその数秒を待たずに済みます。オフ: 最初に翻訳する行が来たときに読み込みます。どちらの場合も、しばらく要求がないと GPU から外れます（ollama_keep_alive）。「ツール」>「モデルを今すぐ解放」ですぐに外すこともできます。次の起動から有効です。",
        "es": "El modelo de traducción se carga mientras TASlation se inicia, así la primera página que se traduce no espera unos segundos por él. Desactivado: se carga cuando llega la primera línea que traducir. En ambos casos deja la GPU tras un rato sin peticiones (ollama_keep_alive), o enseguida con Herramientas > Liberar el modelo ahora. A partir del próximo inicio.",
        "pt": "O modelo de tradução carrega enquanto o TASlation inicia, assim a primeira página a traduzir não espera alguns segundos por ele. Desligado: carrega quando chega a primeira linha a traduzir. Em ambos os casos ele deixa a GPU após um tempo sem pedidos (ollama_keep_alive), ou na hora com Ferramentas > Liberar o modelo agora. A partir do próximo início.",
        "fr": "Le modèle de traduction se charge pendant le démarrage de TASlation, ainsi la première page à traduire ne l'attend pas quelques secondes. Désactivé : il se charge quand vient la première ligne à traduire. Dans les deux cas, il quitte le GPU après un moment sans requête (ollama_keep_alive), ou tout de suite avec Outils > Libérer le modèle maintenant. À partir du prochain démarrage.",
        "de": "Das Übersetzungsmodell lädt, während TASlation startet, sodass die erste zu übersetzende Seite nicht ein paar Sekunden darauf wartet. Aus: Es lädt, wenn die erste zu übersetzende Zeile kommt. In beiden Fällen verlässt es die GPU nach einer Weile ohne Anfragen (ollama_keep_alive), oder sofort mit Werkzeuge > Modell jetzt freigeben. Ab dem nächsten Start.",
        "it": "Il modello di traduzione si carica mentre TASlation si avvia, così la prima pagina da tradurre non lo aspetta qualche secondo. Disattivato: si carica quando arriva la prima riga da tradurre. In entrambi i casi lascia la GPU dopo un po' senza richieste (ollama_keep_alive), o subito con Strumenti > Libera il modello ora. Dal prossimo avvio.",
        "nl": "Het vertaalmodel laadt terwijl TASlation start, zodat de eerste pagina die vertaald wordt er geen paar seconden op wacht. Uit: het laadt wanneer de eerste regel om te vertalen komt. In beide gevallen verlaat het de GPU na een tijd zonder verzoeken (ollama_keep_alive), of meteen met Extra > Model nu vrijgeven. Vanaf de volgende start.",
        "pl": "Model tłumaczenia wczytuje się podczas uruchamiania TASlation, więc pierwsza tłumaczona strona nie czeka na niego kilku sekund. Wyłączone: wczytuje się, gdy pojawi się pierwszy wiersz do tłumaczenia. W obu przypadkach zwalnia GPU po pewnym czasie bez żądań (ollama_keep_alive) albo od razu przez Narzędzia > Zwolnij model teraz. Od następnego uruchomienia.",
        "ru": "Модель перевода загружается во время запуска TASlation, поэтому первая переводимая страница не ждёт её несколько секунд. Выключено: она загружается, когда появляется первая строка для перевода. В обоих случаях она освобождает GPU через некоторое время без запросов (ollama_keep_alive) или сразу через «Инструменты» > «Освободить модель сейчас». Со следующего запуска.",
        "tr": "Çeviri modeli TASlation açılırken yüklenir; böylece çevrilecek ilk sayfa onun için birkaç saniye beklemez. Kapalı: çevrilecek ilk satır geldiğinde yüklenir. Her iki durumda da bir süre istek gelmezse GPU'dan çıkar (ollama_keep_alive) ya da Araçlar > Modeli şimdi serbest bırak ile hemen çıkar. Bir sonraki açılıştan itibaren.",
        "id": "Model terjemahan dimuat saat TASlation dimulai, jadi halaman pertama yang diterjemahkan tidak menunggunya beberapa detik. Mati: model dimuat saat baris pertama yang perlu diterjemahkan muncul. Dalam kedua kasus, model meninggalkan GPU setelah beberapa saat tanpa permintaan (ollama_keep_alive), atau segera lewat Alat > Lepaskan model sekarang. Mulai dari start berikutnya.",
        "vi": "Mô hình dịch được tải trong lúc TASlation khởi động, nên trang đầu tiên cần dịch không phải chờ nó vài giây. Tắt: nó được tải khi có dòng đầu tiên cần dịch. Dù thế nào, nó rời GPU sau một lúc không có yêu cầu (ollama_keep_alive), hoặc ngay lập tức với Công cụ > Giải phóng mô hình ngay. Có hiệu lực từ lần khởi động sau.",
        "zh": "TASlation 启动时就加载翻译模型，这样第一页要翻译时不必再等几秒。关闭：在第一行需要翻译时才加载。无论哪种方式，一段时间没有请求后模型都会离开 GPU（ollama_keep_alive），也可以用“工具”>“立即释放模型”马上释放。下次启动时生效。",
        "zh-tw": "TASlation 啟動時就載入翻譯模型，這樣第一頁要翻譯時不必再等幾秒。關閉：在第一行需要翻譯時才載入。無論哪種方式，一段時間沒有請求後模型都會離開 GPU（ollama_keep_alive），也可以用「工具」>「立即釋放模型」馬上釋放。下次啟動時生效。",
        "ko": "TASlation이 시작되는 동안 번역 모델을 불러오므로, 처음 번역할 페이지가 몇 초를 기다리지 않습니다. 끄면: 처음 번역할 줄이 나올 때 불러옵니다. 어느 쪽이든 한동안 요청이 없으면 GPU에서 내려가며(ollama_keep_alive), 도구 > 지금 모델 해제로 바로 내릴 수도 있습니다. 다음 시작부터 적용됩니다.",
        "th": "โมเดลแปลจะโหลดระหว่างที่ TASlation เริ่มทำงาน หน้าแรกที่ต้องแปลจึงไม่ต้องรอโมเดลอีกหลายวินาที ปิด: โมเดลจะโหลดเมื่อมีบรรทัดแรกที่ต้องแปล ไม่ว่าแบบไหน โมเดลจะออกจาก GPU เมื่อไม่มีคำขอสักพัก (ollama_keep_alive) หรือออกทันทีด้วย เครื่องมือ > ปล่อยโมเดลตอนนี้ มีผลตั้งแต่การเริ่มโปรแกรมครั้งถัดไป",
    },
}

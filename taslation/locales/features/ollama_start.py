"""The window's strings for Ollama started by TASlation (`taslation.ollama_start`), and the help's paragraph on its
end; what comes of a start is a message of `taslation.messages`."""

from __future__ import annotations

TEXTS: dict[str, dict[str, str]] = {
    "Starting the translation program...": {
        "ja": "翻訳プログラムを起動しています...",
        "es": "Iniciando el programa de traducción...",
        "pt": "Iniciando o programa de tradução...",
        "fr": "Démarrage du programme de traduction...",
        "de": "Das Übersetzungsprogramm wird gestartet...",
        "it": "Avvio del programma di traduzione...",
        "nl": "Het vertaalprogramma wordt gestart...",
        "pl": "Uruchamianie programu tłumaczącego...",
        "ru": "Запуск программы перевода...",
        "tr": "Çeviri programı başlatılıyor...",
        "id": "Menjalankan program penerjemah...",
        "vi": "Đang khởi động chương trình dịch...",
        "zh": "正在启动翻译程序...",
        "zh-tw": "正在啟動翻譯程式...",
        "ko": "번역 프로그램을 시작하는 중...",
        "th": "กำลังเริ่มโปรแกรมแปล...",
    },
    "When you close TASlation, it stops the translation program it started, unless another program is using it. If you started the translation program yourself, TASlation leaves it running.": {
        "ja": "TASlation を閉じると、TASlation が起動した翻訳プログラムも止まります。ただし、ほかのプログラムが使っているときは止めません。翻訳プログラムを自分で起動したときは、TASlation はそのまま動かしておきます。",
        "es": "Al cerrar TASlation, se detiene el programa de traducción que inició, salvo que otro programa lo esté usando. Si iniciaste tú el programa de traducción, TASlation lo deja en marcha.",
        "pt": "Ao fechar o TASlation, ele para o programa de tradução que iniciou, a menos que outro programa o esteja usando. Se você mesmo iniciou o programa de tradução, o TASlation o deixa em execução.",
        "fr": "Quand vous fermez TASlation, il arrête le programme de traduction qu'il a démarré, sauf si un autre programme l'utilise. Si vous avez démarré vous-même le programme de traduction, TASlation le laisse tourner.",
        "de": "Wenn Sie TASlation schließen, beendet es das Übersetzungsprogramm, das es gestartet hat, außer ein anderes Programm nutzt es. Haben Sie das Übersetzungsprogramm selbst gestartet, lässt TASlation es laufen.",
        "it": "Quando chiudi TASlation, il programma di traduzione che ha avviato si ferma, a meno che un altro programma lo stia usando. Se hai avviato tu il programma di traduzione, TASlation lo lascia in funzione.",
        "nl": "Als u TASlation sluit, stopt het het vertaalprogramma dat het heeft gestart, tenzij een ander programma het gebruikt. Hebt u het vertaalprogramma zelf gestart, dan laat TASlation het draaien.",
        "pl": "Po zamknięciu TASlation zatrzymuje uruchomiony przez siebie program tłumaczący, chyba że używa go inny program. Jeśli program tłumaczący uruchomiono samodzielnie, TASlation zostawia go włączonego.",
        "ru": "Когда вы закрываете TASlation, он останавливает запущенную им программу перевода, если ею не пользуется другая программа. Если вы запустили программу перевода сами, TASlation оставляет её работать.",
        "tr": "TASlation'ı kapattığınızda, başka bir program kullanmıyorsa başlattığı çeviri programını da durdurur. Çeviri programını kendiniz başlattıysanız TASlation onu çalışır durumda bırakır.",
        "id": "Saat Anda menutup TASlation, program penerjemah yang dijalankannya ikut dihentikan, kecuali sedang dipakai program lain. Jika Anda sendiri yang menjalankan program penerjemah, TASlation membiarkannya tetap berjalan.",
        "vi": "Khi bạn đóng TASlation, nó sẽ dừng chương trình dịch mà nó đã khởi động, trừ khi một chương trình khác đang dùng. Nếu bạn tự khởi động chương trình dịch, TASlation sẽ để nó tiếp tục chạy.",
        "zh": "关闭 TASlation 时，它会停止自己启动的翻译程序，除非另一个程序正在使用它。如果翻译程序是你自己启动的，TASlation 会让它继续运行。",
        "zh-tw": "關閉 TASlation 時，它會停止自己啟動的翻譯程式，除非另一個程式正在使用它。如果翻譯程式是你自己啟動的，TASlation 會讓它繼續執行。",
        "ko": "TASlation을 닫으면 TASlation이 시작한 번역 프로그램도 멈춥니다. 다른 프로그램이 사용 중이면 멈추지 않습니다. 번역 프로그램을 직접 시작했다면 TASlation은 그대로 실행되게 둡니다.",
        "th": "เมื่อปิด TASlation โปรแกรมแปลที่ TASlation เริ่มไว้จะหยุดด้วย เว้นแต่มีโปรแกรมอื่นใช้อยู่ หากคุณเริ่มโปรแกรมแปลเอง TASlation จะปล่อยให้ทำงานต่อไป",
    },
}

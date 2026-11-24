"""The window's strings for what a bubble under the pointer shows while reading and how (`ui.hover`, `ui.zoom`,
`ui.in_place`): View's choices of the translation or the original on the page and of a panel beside the bubble or the
bubble itself, their keys and status lines, a bubble's Japanese as text and its Copy buttons and keys
(`ui.bubble_text`), and the help's lines on them. Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ View's choice (`ui.hover`)
    "This choice holds until TASlation closes: it could not be kept in the settings file ({error}).": {
        "ja": "この選択は TASlation を閉じるまで有効です。設定ファイルに保存できませんでした（{error}）。",
        "es": "Esta elección vale hasta que se cierre TASlation: no se pudo guardar en el archivo de ajustes ({error}).",
        "pt": "Esta escolha vale até fechar o TASlation: não foi possível guardá-la no arquivo de configurações ({error}).",
        "fr": "Ce choix vaut jusqu'à la fermeture de TASlation : il n'a pas pu être gardé dans le fichier de réglages ({error}).",
        "de": "Diese Wahl gilt, bis TASlation schließt: Sie konnte nicht in der Einstellungsdatei gespeichert werden ({error}).",
        "it": "Questa scelta vale fino alla chiusura di TASlation: non è stato possibile salvarla nel file delle impostazioni ({error}).",
        "nl": "Deze keuze geldt tot TASlation sluit: ze kon niet in het instellingenbestand worden bewaard ({error}).",
        "pl": "Ten wybór obowiązuje do zamknięcia TASlation: nie udało się go zapisać w pliku ustawień ({error}).",
        "ru": "Этот выбор действует до закрытия TASlation: его не удалось сохранить в файле настроек ({error}).",
        "tr": "Bu seçim TASlation kapanana kadar geçerli: ayar dosyasına kaydedilemedi ({error}).",
        "id": "Pilihan ini berlaku sampai TASlation ditutup: tidak dapat disimpan di berkas pengaturan ({error}).",
        "vi": "Lựa chọn này có hiệu lực đến khi đóng TASlation: không lưu được vào tệp cài đặt ({error}).",
        "zh": "此选择在关闭 TASlation 之前有效：无法保存到设置文件（{error}）。",
        "zh-tw": "此選擇在關閉 TASlation 之前有效：無法儲存到設定檔（{error}）。",
        "ko": "이 선택은 TASlation을 닫을 때까지 유효합니다. 설정 파일에 저장하지 못했습니다({error}).",
        "th": "ตัวเลือกนี้ใช้ได้จนกว่าจะปิด TASlation: บันทึกลงไฟล์การตั้งค่าไม่ได้ ({error})",
    },
    # ------------------------------------------------------------------ the panel (`ui.zoom`)
    # ------------------------------------------------------------------ a bubble's Japanese and translation (`ui.bubble_text`)
    "Copy the Japanese": {
        "ja": "日本語をコピー", "es": "Copiar el japonés", "pt": "Copiar o japonês", "fr": "Copier le japonais",
        "de": "Japanisch kopieren", "it": "Copia il giapponese", "nl": "Japans kopiëren", "pl": "Kopiuj japoński tekst",
        "ru": "Копировать японский текст", "tr": "Japoncayı kopyala", "id": "Salin bahasa Jepang", "vi": "Sao chép tiếng Nhật",
        "zh": "复制日语原文", "zh-tw": "複製日語原文", "ko": "일본어 복사", "th": "คัดลอกภาษาญี่ปุ่น",
    },
    "Copy the translation": {
        "ja": "訳文をコピー", "es": "Copiar la traducción", "pt": "Copiar a tradução", "fr": "Copier la traduction",
        "de": "Übersetzung kopieren", "it": "Copia la traduzione", "nl": "Vertaling kopiëren", "pl": "Kopiuj tłumaczenie",
        "ru": "Копировать перевод", "tr": "Çeviriyi kopyala", "id": "Salin terjemahan", "vi": "Sao chép bản dịch",
        "zh": "复制译文", "zh-tw": "複製譯文", "ko": "번역 복사", "th": "คัดลอกคำแปล",
    },
    "The bubble's Japanese is on the clipboard.": {
        "ja": "吹き出しの日本語をクリップボードにコピーしました。", "es": "El japonés del globo está en el portapapeles.",
        "pt": "O japonês do balão está na área de transferência.", "fr": "Le japonais de la bulle est dans le presse-papiers.",
        "de": "Das Japanisch der Sprechblase ist in der Zwischenablage.", "it": "Il giapponese del balloon è negli appunti.",
        "nl": "Het Japans van de ballon staat op het klembord.", "pl": "Japoński tekst dymka jest w schowku.",
        "ru": "Японский текст пузыря в буфере обмена.", "tr": "Balonun Japoncası panoda.", "id": "Bahasa Jepang balon ada di papan klip.",
        "vi": "Chữ tiếng Nhật của bong bóng đã ở trong bảng nhớ tạm.", "zh": "气泡的日语原文已复制到剪贴板。",
        "zh-tw": "對話框的日語原文已複製到剪貼簿。", "ko": "말풍선의 일본어를 클립보드에 복사했습니다.",
        "th": "ข้อความภาษาญี่ปุ่นของลูกโป่งคำพูดอยู่ในคลิปบอร์ดแล้ว",
    },
    "The bubble's translation is on the clipboard.": {
        "ja": "吹き出しの訳文をクリップボードにコピーしました。", "es": "La traducción del globo está en el portapapeles.",
        "pt": "A tradução do balão está na área de transferência.", "fr": "La traduction de la bulle est dans le presse-papiers.",
        "de": "Die Übersetzung der Sprechblase ist in der Zwischenablage.", "it": "La traduzione del balloon è negli appunti.",
        "nl": "De vertaling van de ballon staat op het klembord.", "pl": "Tłumaczenie dymka jest w schowku.",
        "ru": "Перевод пузыря в буфере обмена.", "tr": "Balonun çevirisi panoda.", "id": "Terjemahan balon ada di papan klip.",
        "vi": "Bản dịch của bong bóng đã ở trong bảng nhớ tạm.", "zh": "气泡的译文已复制到剪贴板。",
        "zh-tw": "對話框的譯文已複製到剪貼簿。", "ko": "말풍선의 번역을 클립보드에 복사했습니다.",
        "th": "คำแปลของลูกโป่งคำพูดอยู่ในคลิปบอร์ดแล้ว",
    },
    # ------------------------------------------------------------------ the help's Full screen topic (`ui.dialogs.help`)
}

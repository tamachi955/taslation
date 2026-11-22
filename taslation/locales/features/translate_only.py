"""What the window says of the kept files since the model only translates (2026-11-06: no translator's notes of its
own, no review pass, no shorter versions, no alternatives): the line after a rename, the title of the saved
translations' dialog."""

TEXTS: dict[str, dict[str, str]] = {
    # (the last sentence rewritten on 2026-11-20 to say what is true of the disk; machine-translated; no native review)
    "This book is now called {book}. Moved along: {caches} translation file(s), {marks} file(s) of page marks, {sheets} series sheet file(s).": {
        "ja": "この本の書名を『{book}』にしました。一緒に移したもの: 訳文ファイル {caches} 件、ページに付けた情報のファイル {marks} 件、シリーズ設定ファイル {sheets} 件。",
        "es": "Este libro se llama ahora {book}. Se trasladaron con él: {caches} archivo(s) de traducciones, {marks} archivo(s) de marcas en las páginas, {sheets} archivo(s) de la ficha de la serie.",
        "pt": "Este livro agora se chama {book}. Foram junto: {caches} arquivo(s) de traduções, {marks} arquivo(s) de marcações nas páginas, {sheets} arquivo(s) da ficha da série.",
        "fr": "Ce livre s'appelle désormais {book}. Déplacés avec lui : {caches} fichier(s) de traductions, {marks} fichier(s) de repères sur les pages, {sheets} fichier(s) de fiche de série.",
        "de": "Dieses Buch heißt jetzt {book}. Mit umgezogen: {caches} Übersetzungsdatei(en), {marks} Datei(en) mit Seitenmarkierungen, {sheets} Serienblatt-Datei(en).",
        "it": "Questo libro ora si chiama {book}. Spostati con lui: {caches} file di traduzioni, {marks} file di segni sulle pagine, {sheets} file della scheda della serie.",
        "nl": "Dit boek heet nu {book}. Meeverhuisd: {caches} vertaalbestand(en), {marks} bestand(en) met paginamarkeringen, {sheets} serieblad-bestand(en).",
        "pl": "Ta książka nazywa się teraz {book}. Przeniesiono: pliki tłumaczeń: {caches}, pliki oznaczeń na stronach: {marks}, pliki karty serii: {sheets}.",
        "ru": "Теперь эта книга называется {book}. Перенесено: файлов с переводами — {caches}, файлов с пометками на страницах — {marks}, файлов карточки серии — {sheets}.",
        "tr": "Bu kitabın adı artık {book}. Onunla taşınanlar: {caches} çeviri dosyası, {marks} sayfa işaretleri dosyası, {sheets} seri kartı dosyası.",
        "id": "Buku ini sekarang bernama {book}. Ikut dipindahkan: {caches} file terjemahan, {marks} file tanda pada halaman, {sheets} file lembar seri.",
        "vi": "Cuốn sách này giờ có tên là {book}. Đã chuyển theo: {caches} tệp bản dịch, {marks} tệp đánh dấu trên trang, {sheets} tệp phiếu bộ truyện.",
        "zh": "这本书现在的书名是《{book}》。一并迁移：译文文件 {caches} 个，页面标记文件 {marks} 个，系列设定文件 {sheets} 个。",
        "zh-tw": "這本書現在的書名是《{book}》。一併搬移：譯文檔案 {caches} 個，頁面標記檔案 {marks} 個，系列設定檔案 {sheets} 個。",
        "ko": "이 책의 이름을 '{book}'(으)로 바꿨습니다. 함께 옮긴 것: 번역 파일 {caches}개, 페이지 표시 파일 {marks}개, 시리즈 시트 파일 {sheets}개.",
        "th": "ตอนนี้หนังสือเล่มนี้ชื่อ {book} แล้ว ย้ายตามไปด้วย: ไฟล์คำแปล {caches} ไฟล์, ไฟล์เครื่องหมายหน้า {marks} ไฟล์, ไฟล์แผ่นข้อมูลซีรีส์ {sheets} ไฟล์",
    },
    "Saved translations": {
        "ja": "保存した翻訳",
        "es": "Traducciones guardadas",
        "pt": "Traduções salvas",
        "fr": "Traductions enregistrées",
        "de": "Gespeicherte Übersetzungen",
        "it": "Traduzioni salvate",
        "nl": "Bewaarde vertalingen",
        "pl": "Zapisane tłumaczenia",
        "ru": "Сохранённые переводы",
        "tr": "Kaydedilen çeviriler",
        "id": "Terjemahan tersimpan",
        "vi": "Bản dịch đã lưu",
        "zh": "已保存的翻译",
        "zh-tw": "已儲存的翻譯",
        "ko": "저장된 번역",
        "th": "คำแปลที่บันทึกไว้",
    },
}

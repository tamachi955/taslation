"""The viewer chooser's own words (`ui.see_menu.ViewerDialog`), the dialog in which the person chooses the viewer's
window at every start - TASlation chooses none by itself: its List again, and its line (and the status line's) once
the viewer's window was closed. Its OK, Quit and Close are the window's words for them elsewhere.

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "List again": {
        "ja": "一覧を更新",
        "es": "Actualizar lista",
        "pt": "Atualizar lista",
        "fr": "Actualiser la liste",
        "de": "Liste aktualisieren",
        "it": "Aggiorna elenco",
        "nl": "Lijst vernieuwen",
        "pl": "Odśwież listę",
        "ru": "Обновить список",
        "tr": "Listeyi yenile",
        "id": "Muat ulang daftar",
        "vi": "Làm mới danh sách",
        "zh": "刷新列表",
        "zh-tw": "重新整理清單",
        "ko": "목록 새로 고침",
        "th": "รีเฟรชรายการ",
    },
    "The viewer was closed. Open your book again and choose its window.": {
        "ja": "ビューアが閉じられました。本をもう一度開き、そのウィンドウを選んでください。",
        "es": "Se cerró el visor. Abre tu libro de nuevo y elige su ventana.",
        "pt": "O visualizador foi fechado. Abra seu livro de novo e escolha a janela dele.",
        "fr": "La visionneuse a été fermée. Rouvrez votre livre et choisissez sa fenêtre.",
        "de": "Der Viewer wurde geschlossen. Öffnen Sie Ihr Buch erneut und wählen Sie sein Fenster.",
        "it": "Il visualizzatore è stato chiuso. Riapri il libro e scegli la sua finestra.",
        "nl": "De viewer is gesloten. Open je boek opnieuw en kies het venster ervan.",
        "pl": "Czytnik został zamknięty. Otwórz książkę ponownie i wybierz jej okno.",
        "ru": "Окно просмотра закрыто. Откройте книгу снова и выберите её окно.",
        "tr": "Görüntüleyici kapatıldı. Kitabınızı yeniden açın ve penceresini seçin.",
        "id": "Penampil ditutup. Buka lagi buku Anda dan pilih jendelanya.",
        "vi": "Trình xem đã đóng. Hãy mở lại sách và chọn cửa sổ của nó.",
        "zh": "阅读器已关闭。请重新打开书，并选择它的窗口。",
        "zh-tw": "閱讀器已關閉。請重新開啟書，並選擇它的視窗。",
        "ko": "뷰어가 닫혔습니다. 책을 다시 열고 그 창을 고르세요.",
        "th": "ปิดตัวอ่านแล้ว เปิดหนังสืออีกครั้งแล้วเลือกหน้าต่างของมัน",
    },
}

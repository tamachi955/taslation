"""The window's strings for line reuse (`taslation.linememo`): the region editor's note on a translation reused from
an identical line before it (the count of the lines reused this session is in Copy a report: `ui.report`)."""

from __future__ import annotations

TEXTS: dict[str, dict[str, str]] = {
    "This translation was reused from an earlier identical line; the model was not asked. Ask again gives a fresh one.": {
        "ja": "この訳は、前に出た同じセリフの訳を使い回したものです（モデルには尋ねていません）。「もう一度訳す」で新しい訳が出ます。",
        "es": "Esta traducción se reutilizó de una frase idéntica anterior; no se preguntó al modelo. «Traducir de nuevo» da una nueva.",
        "pt": "Esta tradução foi reutilizada de uma fala idêntica anterior; o modelo não foi consultado. \"Traduzir de novo\" dá uma nova.",
        "fr": "Cette traduction reprend celle d'une réplique identique plus haut ; le modèle n'a pas été interrogé. « Retraduire » en donne une nouvelle.",
        "de": "Diese Übersetzung stammt von einer gleichen Zeile davor; das Modell wurde nicht gefragt. „Noch einmal übersetzen“ liefert eine neue.",
        "it": "Questa traduzione è ripresa da una battuta identica precedente; il modello non è stato interpellato. «Traduci di nuovo» ne dà una nuova.",
        "nl": "Deze vertaling is hergebruikt van een eerdere, gelijke regel; het model is niet gevraagd. ‘Opnieuw vertalen’ geeft een nieuwe.",
        "pl": "To tłumaczenie użyto ponownie z wcześniejszej, identycznej kwestii; model nie był pytany. „Przetłumacz ponownie” daje nowe.",
        "ru": "Этот перевод взят у такой же реплики раньше; модель не спрашивали. «Перевести снова» даёт новый.",
        "tr": "Bu çeviri daha önceki aynı replikten yeniden kullanıldı; modele sorulmadı. \"Yeniden çevir\" yenisini verir.",
        "id": "Terjemahan ini dipakai ulang dari baris identik sebelumnya; model tidak ditanya. \"Terjemahkan lagi\" memberi yang baru.",
        "vi": "Bản dịch này được dùng lại từ một câu giống hệt trước đó; mô hình không được hỏi. \"Dịch lại\" sẽ cho một bản mới.",
        "zh": "此译文沿用了此前一句相同台词的译文，没有询问模型。“重新翻译”会给出新的译文。",
        "zh-tw": "此譯文沿用了先前一句相同台詞的譯文，沒有詢問模型。「重新翻譯」會給出新的譯文。",
        "ko": "이 번역은 앞에 나온 같은 대사의 번역을 다시 쓴 것입니다(모델에 묻지 않음). \"다시 번역\"으로 새 번역을 받을 수 있습니다.",
        "th": "คำแปลนี้ใช้ซ้ำจากบทพูดที่เหมือนกันก่อนหน้า โดยไม่ได้ถามโมเดล \"ถามอีกครั้ง\" จะให้คำแปลใหม่",
    },
}

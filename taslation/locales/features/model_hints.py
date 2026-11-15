"""The window's strings for a translation model that does not read a region's hint: the line under "Hint for the
model" in the region editor when the model in use leaves the hint out of its prompt (PLaMo 3 Translate:
`translate.base.reads_hints`, `ui.dialogs.review.HINT_UNREAD`). "Ask again", "series sheet" and "speaker" are
worded as the editor's button, the Series sheet... button and the Speaker: field are in each language."""

TEXTS: dict[str, dict[str, str]] = {
    "The translation model in use does not read hints: Ask again does not follow this one. Names and terms in the "
    "series sheet, and the speaker, do reach the model.": {
        "ja": "使用中の翻訳モデルはヒントを読みません。「もう一度訳す」でもこのヒントは反映されません。"
              "シリーズ設定の名前と用語、それに話者はモデルに伝わります。",
        "es": "El modelo de traducción en uso no lee las pistas: «Traducir de nuevo» no sigue esta. Los nombres y "
              "términos de la ficha de la serie, y el hablante, sí llegan al modelo.",
        "pt": "O modelo de tradução em uso não lê dicas: “Traduzir de novo” não segue esta. Os nomes e termos da "
              "ficha da série, e o falante, chegam sim ao modelo.",
        "fr": "Le modèle de traduction utilisé ne lit pas les indices : « Retraduire » ne suit pas celui-ci. Les noms "
              "et termes de la fiche de la série, ainsi que le locuteur, parviennent bien au modèle.",
        "de": "Das verwendete Übersetzungsmodell liest keine Hinweise: „Noch einmal übersetzen“ folgt diesem nicht. "
              "Namen und Begriffe aus dem Serienblatt sowie der Sprecher erreichen das Modell durchaus.",
        "it": "Il modello di traduzione in uso non legge i suggerimenti: “Traduci di nuovo” non segue questo. I nomi "
              "e i termini della scheda della serie, e il parlante, arrivano invece al modello.",
        "nl": "Het gebruikte vertaalmodel leest geen aanwijzingen: “Opnieuw vertalen” volgt deze niet. Namen en "
              "termen uit het serieblad, en de spreker, bereiken het model wel.",
        "pl": "Używany model tłumaczenia nie czyta wskazówek: „Przetłumacz ponownie” nie uwzględni tej. Imiona i "
              "terminy z karty serii oraz mówiący docierają jednak do modelu.",
        "ru": "Используемая модель перевода не читает подсказки: «Перевести снова» эту подсказку не учтёт. Имена и "
              "термины из карточки серии, а также говорящий, до модели доходят.",
        "tr": "Kullanılan çeviri modeli ipuçlarını okumaz: “Yeniden çevir” bu ipucunu dikkate almaz. Seri kartındaki "
              "adlar ve terimler ile konuşan ise modele ulaşır.",
        "id": "Model terjemahan yang dipakai tidak membaca petunjuk: “Terjemahkan lagi” tidak mengikuti petunjuk ini. "
              "Nama dan istilah di lembar seri, serta pembicara, tetap sampai ke model.",
        "vi": "Mô hình dịch đang dùng không đọc gợi ý: “Dịch lại” sẽ không theo gợi ý này. Tên và thuật ngữ trong "
              "phiếu bộ truyện, cùng người nói, thì vẫn đến được mô hình.",
        "zh": "当前使用的翻译模型不读取提示：“重新翻译”也不会遵循这条提示。系列设定中的名字和术语，以及说话者，会传给模型。",
        "zh-tw": "目前使用的翻譯模型不讀取提示：「重新翻譯」也不會遵循這條提示。系列設定中的名字和術語，以及說話者，會傳給模型。",
        "ko": "사용 중인 번역 모델은 힌트를 읽지 않습니다. ‘다시 번역’도 이 힌트를 따르지 않습니다. 시리즈 시트의 이름과 "
              "용어, 그리고 화자는 모델에 전달됩니다.",
        "th": "โมเดลแปลที่ใช้อยู่ไม่อ่านคำใบ้ “ถามอีกครั้ง” จะไม่ทำตามคำใบ้นี้ ส่วนชื่อและคำศัพท์ในแผ่นข้อมูลซีรีส์ "
              "รวมถึงผู้พูด จะถูกส่งถึงโมเดล",
    },
}

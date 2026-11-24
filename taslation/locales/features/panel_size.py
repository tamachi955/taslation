"""The window's strings for the panel beside a bubble under the pointer in the Settings dialog
(`ui.dialogs.settings.NUMBER_ROWS`): the panel's text size (``panel_font_size``) and the delay under the pointer
(``hover_delay_ms``), each a label, its tip and what Save says of a value that does not fit. The panel and the
pointer are worded as in the dialog's hover rows (ja 「パネル」「ポインターの下」), the review size as its "List for
review below" row (ja 「要確認」).

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    # (see-through mode's tip of the same delay: the patch under the pointer and the right pane's bubble)
    "How long the pointer rests on a bubble before its translation gives way to the original under it, and the pane at the right shows that bubble. 0: at once.": {
        "ja": "ポインターを吹き出しに置いてから、その訳文が下の原文に替わり、右の欄にその吹き出しが出るまでの時間。0：すぐに。",
        "es": "Cuánto descansa el puntero sobre un globo antes de que su traducción deje ver el original debajo y el panel de la derecha muestre ese globo. 0: al instante.",
        "pt": "Quanto tempo o ponteiro fica sobre um balão antes que a tradução dê lugar ao original por baixo e o painel à direita mostre esse balão. 0: na hora.",
        "fr": "Combien de temps le pointeur reste sur une bulle avant que sa traduction laisse voir l'original dessous et que le volet de droite montre cette bulle. 0 : aussitôt.",
        "de": "Wie lange der Zeiger auf einer Sprechblase ruht, bevor ihre Übersetzung dem Original darunter weicht und die Leiste rechts diese Sprechblase zeigt. 0: sofort.",
        "it": "Quanto il puntatore resta su un balloon prima che la sua traduzione lasci vedere l'originale sotto e il riquadro a destra mostri quel balloon. 0: subito.",
        "nl": "Hoe lang de aanwijzer op een ballon rust voordat de vertaling plaatsmaakt voor het origineel eronder en het paneel rechts die ballon toont. 0: meteen.",
        "pl": "Jak długo wskaźnik spoczywa na dymku, zanim tłumaczenie ustąpi oryginałowi pod nim, a panel po prawej pokaże ten dymek. 0: od razu.",
        "ru": "Сколько указатель задерживается на пузыре, прежде чем перевод уступит место оригиналу под ним, а панель справа покажет этот пузырь. 0: сразу.",
        "tr": "İşaretçi bir balonun üzerinde ne kadar durunca çevirisinin yerini altındaki asıl metne bıraktığı ve sağdaki bölmenin o balonu gösterdiği. 0: hemen.",
        "id": "Berapa lama penunjuk diam di atas balon sebelum terjemahannya memberi tempat bagi aslinya di bawah dan panel di kanan menampilkan balon itu. 0: langsung.",
        "vi": "Thời gian con trỏ dừng trên một bong bóng trước khi bản dịch nhường chỗ cho bản gốc bên dưới và ô bên phải hiện bong bóng đó. 0: ngay lập tức.",
        "zh": "指针在气泡上停留多久后，其译文让位于下面的原文，右侧面板显示该气泡。0：立即。",
        "zh-tw": "指標在對話框上停留多久後，其譯文讓位於下方的原文，右側面板顯示該對話框。0：立即。",
        "ko": "포인터가 말풍선 위에 머문 뒤 번역이 그 아래 원문으로 바뀌고 오른쪽 창에 그 말풍선이 표시되기까지의 시간. 0: 바로.",
        "th": "ระยะเวลาที่ตัวชี้ค้างบนลูกโป่งคำพูดก่อนที่คำแปลจะเปิดให้เห็นต้นฉบับด้านล่าง และแผงทางขวาแสดงลูกโป่งคำพูดนั้น 0: ทันที",
    },
    "Delay under the pointer (milliseconds):": {
        "ja": "ポインターの下で待つ時間（ミリ秒）:", "es": "Espera bajo el puntero (milisegundos):",
        "pt": "Espera sob o ponteiro (milissegundos):", "fr": "Délai sous le pointeur (millisecondes) :",
        "de": "Verzögerung unter dem Zeiger (Millisekunden):", "it": "Attesa sotto il puntatore (millisecondi):",
        "nl": "Vertraging onder de aanwijzer (milliseconden):", "pl": "Opóźnienie pod wskaźnikiem (milisekundy):",
        "ru": "Задержка под указателем (миллисекунды):", "tr": "İşaretçinin altında gecikme (milisaniye):",
        "id": "Jeda di bawah penunjuk (milidetik):", "vi": "Độ trễ dưới con trỏ (mili giây):",
        "zh": "指针下的延迟（毫秒）：", "zh-tw": "指標下的延遲（毫秒）：", "ko": "포인터 아래 지연(밀리초):",
        "th": "เวลารอใต้ตัวชี้ (มิลลิวินาที):",
    },
    "The delay under the pointer: a whole number from {low} to {high} milliseconds.": {
        "ja": "ポインターの下で待つ時間: {low} から {high} までの整数（ミリ秒）にしてください。",
        "es": "La espera bajo el puntero: un número entero de {low} a {high} milisegundos.",
        "pt": "A espera sob o ponteiro: um número inteiro de {low} a {high} milissegundos.",
        "fr": "Le délai sous le pointeur : un nombre entier de {low} à {high} millisecondes.",
        "de": "Die Verzögerung unter dem Zeiger: eine ganze Zahl von {low} bis {high} Millisekunden.",
        "it": "L'attesa sotto il puntatore: un numero intero da {low} a {high} millisecondi.",
        "nl": "De vertraging onder de aanwijzer: een heel getal van {low} tot {high} milliseconden.",
        "pl": "Opóźnienie pod wskaźnikiem: liczba całkowita od {low} do {high} milisekund.",
        "ru": "Задержка под указателем: целое число от {low} до {high} миллисекунд.",
        "tr": "İşaretçinin altında gecikme: {low} ile {high} milisaniye arasında bir tam sayı.",
        "id": "Jeda di bawah penunjuk: bilangan bulat dari {low} sampai {high} milidetik.",
        "vi": "Độ trễ dưới con trỏ: một số nguyên từ {low} đến {high} mili giây.",
        "zh": "指针下的延迟：{low} 到 {high} 毫秒之间的整数。",
        "zh-tw": "指標下的延遲：{low} 到 {high} 毫秒之間的整數。",
        "ko": "포인터 아래 지연: {low}에서 {high} 밀리초 사이의 정수.",
        "th": "เวลารอใต้ตัวชี้: จำนวนเต็มตั้งแต่ {low} ถึง {high} มิลลิวินาที",
    },
}

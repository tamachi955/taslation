"""The window's strings for a translation model that follows a region's hint only now and then: the line under "Hint
for the model" in the region editor when the model in use is given the hint but follows it in about half of the
answers of a test (PLaMo 3 Translate: `translate.base.hint_support` "sometimes", `ui.dialogs.review.HINT_SOMETIMES`).
"Hint" and "series sheet" are worded as the editor's Hint for the model: field and the Series sheet... button are in
each language."""

TEXTS: dict[str, dict[str, str]] = {
    "This model follows a hint only sometimes (about half the time in a test), best for how a name or term is read and "
    "who or how many are meant. Names and terms that must always come out the same belong in the series sheet.": {
        "ja": "このモデルがヒントに従うのはときどきです（試験ではおよそ半分）。よく効くのは名前や用語の読み方と、"
              "誰のことか・いくつのことかです。いつも同じ訳にしたい名前と用語はシリーズ設定に入れてください。",
        "es": "Este modelo solo sigue una pista a veces (cerca de la mitad de las veces en una prueba), mejor para "
              "cómo se lee un nombre o término y a quién o a cuántos se refiere. Los nombres y términos que deben "
              "salir siempre igual van en la ficha de la serie.",
        "pt": "Este modelo só segue uma dica às vezes (cerca de metade das vezes num teste), melhor para como se lê um "
              "nome ou termo e a quem ou a quantos se refere. Nomes e termos que devem sair sempre iguais vão na ficha "
              "da série.",
        "fr": "Ce modèle ne suit un indice que parfois (environ une fois sur deux lors d'un test), surtout pour la "
              "lecture d'un nom ou d'un terme, et pour qui ou combien sont visés. Les noms et termes à rendre "
              "toujours de la même façon vont dans la fiche de la série.",
        "de": "Dieses Modell folgt einem Hinweis nur manchmal (in einem Test etwa in der Hälfte der Fälle), am ehesten "
              "bei der Lesung eines Namens oder Begriffs und dabei, wer oder wie viele gemeint sind. Namen und "
              "Begriffe, die immer gleich herauskommen müssen, gehören ins Serienblatt.",
        "it": "Questo modello segue un suggerimento solo a volte (circa metà delle volte in un test), soprattutto per "
              "come si legge un nome o un termine e per chi o quanti si intendono. Nomi e termini che devono venire "
              "sempre uguali vanno nella scheda della serie.",
        "nl": "Dit model volgt een aanwijzing maar soms (in een test ongeveer de helft van de keren), het best bij hoe "
              "een naam of term gelezen wordt en wie of hoeveel er bedoeld zijn. Namen en termen die altijd hetzelfde "
              "moeten uitkomen, horen in het serieblad.",
        "pl": "Ten model stosuje się do wskazówki tylko czasami (w teście mniej więcej w połowie przypadków), "
              "najlepiej co do tego, jak czytać imię lub termin, oraz o kogo lub o ilu chodzi. Imiona i terminy, "
              "które zawsze mają wychodzić tak samo, należą do karty serii.",
        "ru": "Эта модель следует подсказке лишь иногда (в тесте примерно в половине случаев), лучше всего в том, как "
              "читается имя или термин и о ком или о скольких речь. Имена и термины, всегда переводимые одинаково, "
              "вносите в карточку серии.",
        "tr": "Bu model bir ipucuna yalnızca bazen uyar (bir testte yaklaşık yarı yarıya); en çok bir adın ya da "
              "terimin nasıl okunduğunda ve kimin ya da kaç kişinin kastedildiğinde işe yarar. Her zaman aynı çıkması "
              "gereken adlar ve terimler seri kartına yazılmalıdır.",
        "id": "Model ini hanya kadang-kadang mengikuti petunjuk (sekitar separuh kali dalam sebuah uji), paling baik "
              "untuk cara membaca nama atau istilah dan siapa atau berapa banyak yang dimaksud. Nama dan istilah yang "
              "harus selalu sama tempatnya di lembar seri.",
        "vi": "Mô hình này chỉ thỉnh thoảng làm theo gợi ý (khoảng một nửa số lần trong một thử nghiệm), tốt nhất với "
              "cách đọc một tên hay thuật ngữ và việc nói về ai hay bao nhiêu. Tên và thuật ngữ luôn phải ra giống "
              "nhau thì nên ghi vào phiếu bộ truyện.",
        "zh": "此模型只是有时遵循提示（测试中约一半），对名字或术语的读法、指的是谁或多少最有效。"
              "必须始终译得一致的名字和术语，请写进系列设定。",
        "zh-tw": "此模型只是有時遵循提示（測試中約一半），對名字或術語的讀法、指的是誰或多少最有效。"
                 "必須始終譯得一致的名字和術語，請寫進系列設定。",
        "ko": "이 모델은 힌트를 가끔만 따릅니다(테스트에서 약 절반). 이름이나 용어를 어떻게 읽는지, 누구 또는 "
              "몇을 가리키는지에 가장 잘 듣습니다. 항상 똑같이 나와야 하는 이름과 용어는 시리즈 시트에 넣으세요.",
        "th": "โมเดลนี้ทำตามคำใบ้เพียงบางครั้ง (ราวครึ่งหนึ่งในการทดสอบ) ได้ผลดีที่สุดกับวิธีอ่านชื่อหรือคำศัพท์ "
              "และการบอกว่าหมายถึงใครหรือกี่คน ชื่อและคำศัพท์ที่ต้องออกมาเหมือนกันทุกครั้งควรใส่ไว้ในแผ่นข้อมูลซีรีส์",
    },
}

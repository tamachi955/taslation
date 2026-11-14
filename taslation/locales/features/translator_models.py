"""The window's strings for the translator model: the offer to install the model a target language needs (and to
remove the one no longer needed), PLaMo's licence step, the install's progress and how it ended."""

TEXTS: dict[str, dict[str, str]] = {
    "Translating into {language} needs the translation model {model}, which is not on this computer yet. TASlation can download it now: about {size} GB.": {
        "ja": "{language} への翻訳には翻訳モデル {model} が必要ですが、このパソコンにはまだありません。TASlation が今ダウンロードできます（約 {size} GB）。",
        "es": "Para traducir al {language} hace falta el modelo de traducción {model}, que aún no está en este ordenador. TASlation puede descargarlo ahora: unos {size} GB.",
        "pt": "Para traduzir para {language} é preciso o modelo de tradução {model}, que ainda não está neste computador. O TASlation pode baixá-lo agora: cerca de {size} GB.",
        "fr": "Traduire en {language} demande le modèle de traduction {model}, qui n'est pas encore sur cet ordinateur. TASlation peut le télécharger maintenant : environ {size} GB.",
        "de": "Für Übersetzungen ins {language} braucht es das Übersetzungsmodell {model}, das noch nicht auf diesem Computer ist. TASlation kann es jetzt herunterladen: etwa {size} GB.",
        "it": "Per tradurre in {language} serve il modello di traduzione {model}, che non è ancora su questo computer. TASlation può scaricarlo ora: circa {size} GB.",
        "nl": "Vertalen naar het {language} vraagt het vertaalmodel {model}, dat nog niet op deze computer staat. TASlation kan het nu downloaden: ongeveer {size} GB.",
        "pl": "Tłumaczenie na {language} wymaga modelu tłumaczenia {model}, którego nie ma jeszcze na tym komputerze. TASlation może go teraz pobrać: około {size} GB.",
        "ru": "Для перевода на {language} нужна модель перевода {model}, которой на этом компьютере ещё нет. TASlation может скачать её сейчас: около {size} GB.",
        "tr": "{language} diline çeviri için {model} çeviri modeli gerekiyor; bu bilgisayarda henüz yok. TASlation onu şimdi indirebilir: yaklaşık {size} GB.",
        "id": "Menerjemahkan ke {language} memerlukan model terjemahan {model}, yang belum ada di komputer ini. TASlation dapat mengunduhnya sekarang: sekitar {size} GB.",
        "vi": "Dịch sang {language} cần mô hình dịch {model}, hiện chưa có trên máy tính này. TASlation có thể tải xuống ngay bây giờ: khoảng {size} GB.",
        "zh": "译为{language}需要翻译模型 {model}，这台电脑上还没有。TASlation 现在可以下载它：约 {size} GB。",
        "zh-tw": "譯為{language}需要翻譯模型 {model}，這台電腦上還沒有。TASlation 現在可以下載它：約 {size} GB。",
        "ko": "{language}(으)로 번역하려면 번역 모델 {model}이(가) 필요하지만 이 컴퓨터에는 아직 없습니다. TASlation이 지금 다운로드할 수 있습니다(약 {size} GB).",
        "th": "การแปลเป็น{language}ต้องใช้โมเดลแปลภาษา {model} ซึ่งยังไม่มีในคอมพิวเตอร์เครื่องนี้ TASlation ดาวน์โหลดให้ได้ทันที: ประมาณ {size} GB",
    },
    "{old} is not needed for {language} and is then removed, which frees about {freed} GB.": {
        "ja": "{old} は {language} には不要なので、その後で削除します。約 {freed} GB が空きます。",
        "es": "{old} no hace falta para el {language} y se elimina después, lo que libera unos {freed} GB.",
        "pt": "{old} não é necessário para {language} e é removido em seguida, o que libera cerca de {freed} GB.",
        "fr": "{old} n'est pas utile pour le {language} et sera ensuite supprimé, ce qui libère environ {freed} GB.",
        "de": "{old} wird für {language} nicht gebraucht und danach entfernt; das gibt etwa {freed} GB frei.",
        "it": "{old} non serve per {language} e viene poi rimosso, liberando circa {freed} GB.",
        "nl": "{old} is niet nodig voor het {language} en wordt daarna verwijderd; dat maakt ongeveer {freed} GB vrij.",
        "pl": "{old} nie jest potrzebny do języka {language} i zostanie potem usunięty, co zwolni około {freed} GB.",
        "ru": "{old} для языка {language} не нужна и затем удаляется; освободится около {freed} GB.",
        "tr": "{old}, {language} için gerekli değil ve ardından kaldırılır; bu yaklaşık {freed} GB yer açar.",
        "id": "{old} tidak diperlukan untuk {language} dan akan dihapus setelahnya, sehingga membebaskan sekitar {freed} GB.",
        "vi": "{old} không cần cho {language} và sẽ được gỡ sau đó, giải phóng khoảng {freed} GB.",
        "zh": "{language}不需要 {old}，之后会将其删除，可腾出约 {freed} GB。",
        "zh-tw": "{language}不需要 {old}，之後會將其刪除，可騰出約 {freed} GB。",
        "ko": "{old}은(는) {language}에 필요하지 않으므로 그 후 삭제되며, 약 {freed} GB가 확보됩니다.",
        "th": "{language}ไม่ต้องใช้ {old} จึงจะลบออกหลังจากนั้น ซึ่งจะคืนพื้นที่ประมาณ {freed} GB",
    },
    "{old} was on this computer before TASlation installed anything, and {language} does not need it. Remove it too, to free about {freed} GB?": {
        "ja": "{old} は TASlation が何かをインストールする前からこのパソコンにありました。{language} には不要です。これも削除して約 {freed} GB 空けますか？",
        "es": "{old} ya estaba en este ordenador antes de que TASlation instalara nada, y el {language} no lo necesita. ¿Eliminarlo también para liberar unos {freed} GB?",
        "pt": "{old} já estava neste computador antes de o TASlation instalar qualquer coisa, e {language} não precisa dele. Removê-lo também para liberar cerca de {freed} GB?",
        "fr": "{old} était sur cet ordinateur avant que TASlation n'installe quoi que ce soit, et le {language} n'en a pas besoin. Le supprimer aussi pour libérer environ {freed} GB ?",
        "de": "{old} war schon auf diesem Computer, bevor TASlation irgendetwas installiert hat, und {language} braucht es nicht. Auch entfernen, um etwa {freed} GB freizugeben?",
        "it": "{old} era su questo computer prima che TASlation installasse qualcosa, e {language} non ne ha bisogno. Rimuoverlo anche, per liberare circa {freed} GB?",
        "nl": "{old} stond al op deze computer voordat TASlation iets installeerde, en het {language} heeft het niet nodig. Ook verwijderen om ongeveer {freed} GB vrij te maken?",
        "pl": "{old} był na tym komputerze, zanim TASlation cokolwiek zainstalował, a język {language} go nie potrzebuje. Usunąć go też, aby zwolnić około {freed} GB?",
        "ru": "{old} была на этом компьютере ещё до того, как TASlation что-либо установил, и для языка {language} она не нужна. Удалить и её, чтобы освободить около {freed} GB?",
        "tr": "{old}, TASlation herhangi bir şey kurmadan önce de bu bilgisayardaydı ve {language} için gerekmiyor. Yaklaşık {freed} GB yer açmak için bu da kaldırılsın mı?",
        "id": "{old} sudah ada di komputer ini sebelum TASlation memasang apa pun, dan {language} tidak memerlukannya. Hapus juga untuk membebaskan sekitar {freed} GB?",
        "vi": "{old} đã có trên máy tính này trước khi TASlation cài đặt bất cứ thứ gì, và {language} không cần nó. Gỡ cả nó để giải phóng khoảng {freed} GB?",
        "zh": "{old} 在 TASlation 安装任何东西之前就已在这台电脑上，{language}不需要它。是否也将其删除，腾出约 {freed} GB？",
        "zh-tw": "{old} 在 TASlation 安裝任何東西之前就已在這台電腦上，{language}不需要它。是否也將其刪除，騰出約 {freed} GB？",
        "ko": "{old}은(는) TASlation이 무언가를 설치하기 전부터 이 컴퓨터에 있었으며, {language}에는 필요하지 않습니다. 이것도 삭제해 약 {freed} GB를 확보할까요?",
        "th": "{old} อยู่ในคอมพิวเตอร์เครื่องนี้ก่อนที่ TASlation จะติดตั้งสิ่งใด และ{language}ไม่ต้องใช้ ต้องการลบออกด้วยเพื่อคืนพื้นที่ประมาณ {freed} GB หรือไม่",
    },
    "Download": {
        "ja": "ダウンロード", "es": "Descargar", "pt": "Baixar", "fr": "Télécharger", "de": "Herunterladen",
        "it": "Scarica", "nl": "Downloaden", "pl": "Pobierz", "ru": "Скачать", "tr": "İndir", "id": "Unduh",
        "vi": "Tải xuống", "zh": "下载", "zh-tw": "下載", "ko": "다운로드", "th": "ดาวน์โหลด",
    },
    "Keep it": {
        "ja": "残す", "es": "Conservarlo", "pt": "Manter", "fr": "Le garder", "de": "Behalten", "it": "Tienilo",
        "nl": "Houden", "pl": "Zachowaj", "ru": "Оставить", "tr": "Kalsın", "id": "Simpan", "vi": "Giữ lại",
        "zh": "保留", "zh-tw": "保留", "ko": "유지", "th": "เก็บไว้",
    },
    "Remove it": {
        "ja": "削除する", "es": "Eliminarlo", "pt": "Remover", "fr": "Le supprimer", "de": "Entfernen", "it": "Rimuovilo",
        "nl": "Verwijderen", "pl": "Usuń", "ru": "Удалить", "tr": "Kaldır", "id": "Hapus", "vi": "Gỡ bỏ",
        "zh": "删除", "zh-tw": "刪除", "ko": "삭제", "th": "ลบออก",
    },
    "The licence of PLaMo": {
        "ja": "PLaMo のライセンス", "es": "La licencia de PLaMo", "pt": "A licença do PLaMo", "fr": "La licence de PLaMo",
        "de": "Die Lizenz von PLaMo", "it": "La licenza di PLaMo", "nl": "De licentie van PLaMo",
        "pl": "Licencja PLaMo", "ru": "Лицензия PLaMo", "tr": "PLaMo lisansı", "id": "Lisensi PLaMo",
        "vi": "Giấy phép của PLaMo", "zh": "PLaMo 的许可", "zh-tw": "PLaMo 的授權", "ko": "PLaMo 라이선스",
        "th": "สัญญาอนุญาตของ PLaMo",
    },
    "TASlation translates with PLaMo 3 Translate 2B by Preferred Networks (PFN). Its licence is the PLaMo Community License, as revised on November 9, 2026:\n"
    "\u2022 Personal and other non-commercial use is free, with no registration. Commercial use needs registering with PFN first (article 3).\n"
    "\u2022 You must be 18 or older (or of age where you live), or have a parent's or guardian's consent (article 2).\n"
    "\u2022 You are responsible for having the rights to what you put into it and to what comes out of it; the licence gives no rights to other people's works (article 9).\n"
    "\u2022 A translation made with it may be published without a note that it is PLaMo's output, but one published as all or a large part of a book or another long publication must say that PLaMo was used. When you give a translation to someone or make it public, you must tell them that models trained on it fall under this licence (article 5). TASlation asks you not to publish translations at all.\n"
    "\u2022 The model comes as is, without any warranty; how you use it is your responsibility (article 7).": {
        "ja": "TASlation は Preferred Networks (PFN) の PLaMo 3 Translate 2B で翻訳します。ライセンスは PLaMo Community License（PLaMoコミュニティライセンス、2026年11月9日改定）です。\n"
              "\u2022 個人での利用など商用以外の利用は無料で、登録も要りません。商用で使うには先に PFN への登録が必要です（第3条）。\n"
              "\u2022 18歳以上（またはお住まいの国で成人）であるか、親権者・法定代理人の同意が必要です（第2条）。\n"
              "\u2022 入力する内容と翻訳結果を使うのに必要な権利・許諾は、ご自身の責任で確保します。このライセンスは、他人の作品についての権利を何も与えません（第9条）。\n"
              "\u2022 これで作った翻訳は、PLaMo の生成物である旨を書かずに公表できます。ただし、書籍などの長い公表物の全部または大部分として公表するときは、PLaMo を翻訳に使ったことを明示しなければなりません。翻訳を人に渡したり公開したりするときは、それで学習したモデルにもこのライセンスが適用されることを、相手にわかるように示さなければなりません（第5条）。TASlation は、翻訳を一切公表しないようお願いしています。\n"
              "\u2022 モデルは現状のまま、いかなる保証もなく提供されます。使い方の責任はご自身にあります（第7条）。",
        "es": "TASlation traduce con PLaMo 3 Translate 2B, de Preferred Networks (PFN). Su licencia es la PLaMo Community License, revisada el 9 de noviembre de 2026:\n"
              "\u2022 El uso personal y cualquier otro uso no comercial es gratuito y sin registro. El uso comercial exige registrarse antes con PFN (artículo 3).\n"
              "\u2022 Debes tener 18 años o más (o la mayoría de edad donde vives), o el consentimiento de tus padres o tutores (artículo 2).\n"
              "\u2022 Eres responsable de tener los derechos sobre lo que introduces y sobre lo que sale; la licencia no da ningún derecho sobre obras ajenas (artículo 9).\n"
              "\u2022 Una traducción hecha con él puede publicarse sin indicar que es un resultado de PLaMo, pero si se publica como la totalidad o una parte sustancial de un libro u otra publicación extensa, debe indicar que se usó PLaMo. Si das una traducción a alguien o la haces pública, debes indicarle que los modelos entrenados con ella quedan sujetos a esta licencia (artículo 5). TASlation te pide que no publiques ninguna traducción.\n"
              "\u2022 El modelo se ofrece tal cual, sin ninguna garantía; cómo lo uses es responsabilidad tuya (artículo 7).",
        "pt": "O TASlation traduz com o PLaMo 3 Translate 2B, da Preferred Networks (PFN). A licença dele é a PLaMo Community License, revisada em 9 de novembro de 2026:\n"
              "\u2022 O uso pessoal e qualquer outro uso não comercial é gratuito e sem cadastro. O uso comercial exige cadastro prévio na PFN (artigo 3).\n"
              "\u2022 Você precisa ter 18 anos ou mais (ou a maioridade onde mora), ou o consentimento dos pais ou do responsável (artigo 2).\n"
              "\u2022 Você é responsável por ter os direitos sobre o que coloca nele e sobre o que sai dele; a licença não dá nenhum direito sobre obras de outras pessoas (artigo 9).\n"
              "\u2022 Uma tradução feita com ele pode ser publicada sem indicar que é um resultado do PLaMo, mas, se for publicada como o todo ou uma parte substancial de um livro ou de outra publicação longa, deve informar que o PLaMo foi usado. Ao entregar uma tradução a alguém ou torná-la pública, você deve informar que modelos treinados com ela ficam sujeitos a esta licença (artigo 5). O TASlation pede que você não publique nenhuma tradução.\n"
              "\u2022 O modelo é fornecido como está, sem nenhuma garantia; a forma como você o usa é responsabilidade sua (artigo 7).",
        "fr": "TASlation traduit avec PLaMo 3 Translate 2B, de Preferred Networks (PFN). Sa licence est la PLaMo Community License, révisée le 9 novembre 2026 :\n"
              "\u2022 L'usage personnel et tout autre usage non commercial est gratuit, sans inscription. Un usage commercial demande de s'inscrire d'abord auprès de PFN (article 3).\n"
              "\u2022 Vous devez avoir 18 ans ou plus (ou être majeur là où vous vivez), ou avoir l'accord d'un parent ou d'un tuteur (article 2).\n"
              "\u2022 Il vous revient d'avoir les droits sur ce que vous lui donnez et sur ce qui en sort ; la licence ne donne aucun droit sur les œuvres d'autrui (article 9).\n"
              "\u2022 Une traduction faite avec lui peut être publiée sans indiquer qu'elle est produite par PLaMo, mais publiée comme tout ou partie substantielle d'un livre ou d'une autre publication longue, elle doit indiquer que PLaMo a été utilisé. Si vous remettez une traduction à quelqu'un ou la rendez publique, vous devez indiquer que les modèles entraînés avec elle relèvent de cette licence (article 5). TASlation vous demande de ne publier aucune traduction.\n"
              "\u2022 Le modèle est fourni tel quel, sans aucune garantie ; l'usage que vous en faites relève de votre responsabilité (article 7).",
        "de": "TASlation übersetzt mit PLaMo 3 Translate 2B von Preferred Networks (PFN). Seine Lizenz ist die PLaMo Community License in der Fassung vom 9. November 2026:\n"
              "\u2022 Private und andere nicht kommerzielle Nutzung ist kostenlos und ohne Registrierung. Für kommerzielle Nutzung müssen Sie sich zuerst bei PFN registrieren (Artikel 3).\n"
              "\u2022 Sie müssen mindestens 18 Jahre alt sein (oder dort, wo Sie leben, volljährig) oder die Zustimmung eines Elternteils oder Vormunds haben (Artikel 2).\n"
              "\u2022 Sie sind dafür verantwortlich, die Rechte an dem zu haben, was Sie eingeben, und an dem, was herauskommt; die Lizenz gibt keine Rechte an Werken anderer (Artikel 9).\n"
              "\u2022 Eine damit gemachte Übersetzung darf ohne Hinweis darauf veröffentlicht werden, dass sie eine Ausgabe von PLaMo ist; wird sie aber als Ganzes oder wesentlicher Teil eines Buchs oder einer anderen langen Veröffentlichung veröffentlicht, muss angegeben werden, dass PLaMo verwendet wurde. Wenn Sie eine Übersetzung jemandem geben oder veröffentlichen, müssen Sie darauf hinweisen, dass damit trainierte Modelle unter diese Lizenz fallen (Artikel 5). TASlation bittet Sie, Übersetzungen überhaupt nicht zu veröffentlichen.\n"
              "\u2022 Das Modell wird so bereitgestellt, wie es ist, ohne jede Gewährleistung; wie Sie es nutzen, liegt in Ihrer Verantwortung (Artikel 7).",
        "it": "TASlation traduce con PLaMo 3 Translate 2B di Preferred Networks (PFN). La sua licenza è la PLaMo Community License, nella revisione del 9 novembre 2026:\n"
              "\u2022 L'uso personale e ogni altro uso non commerciale è gratuito, senza registrazione. L'uso commerciale richiede prima la registrazione presso PFN (articolo 3).\n"
              "\u2022 Devi avere almeno 18 anni (o la maggiore età dove vivi), oppure il consenso di un genitore o tutore (articolo 2).\n"
              "\u2022 Sei responsabile di avere i diritti su ciò che inserisci e su ciò che ne esce; la licenza non dà alcun diritto sulle opere altrui (articolo 9).\n"
              "\u2022 Una traduzione fatta con esso può essere pubblicata senza indicare che è un risultato di PLaMo, ma se è pubblicata come tutto o parte sostanziale di un libro o di un'altra pubblicazione lunga deve dire che è stato usato PLaMo. Se dai una traduzione a qualcuno o la rendi pubblica, devi indicare che i modelli addestrati su di essa ricadono sotto questa licenza (articolo 5). TASlation ti chiede di non pubblicare alcuna traduzione.\n"
              "\u2022 Il modello è fornito così com'è, senza alcuna garanzia; come lo usi è una tua responsabilità (articolo 7).",
        "nl": "TASlation vertaalt met PLaMo 3 Translate 2B van Preferred Networks (PFN). De licentie is de PLaMo Community License, herzien op 9 november 2026:\n"
              "\u2022 Persoonlijk en ander niet-commercieel gebruik is gratis, zonder registratie. Voor commercieel gebruik moet u zich eerst bij PFN registreren (artikel 3).\n"
              "\u2022 U moet 18 jaar of ouder zijn (of meerderjarig waar u woont), of toestemming hebben van een ouder of voogd (artikel 2).\n"
              "\u2022 U bent er zelf verantwoordelijk voor dat u de rechten hebt op wat u erin stopt en op wat eruit komt; de licentie geeft geen rechten op werk van anderen (artikel 9).\n"
              "\u2022 Een vertaling die ermee is gemaakt, mag worden gepubliceerd zonder vermelding dat het uitvoer van PLaMo is, maar wordt ze gepubliceerd als geheel of groot deel van een boek of een andere lange publicatie, dan moet worden vermeld dat PLaMo is gebruikt. Als u een vertaling aan iemand geeft of openbaar maakt, moet u vermelden dat modellen die ermee worden getraind onder deze licentie vallen (artikel 5). TASlation vraagt u helemaal geen vertalingen te publiceren.\n"
              "\u2022 Het model wordt geleverd zoals het is, zonder enige garantie; hoe u het gebruikt, is uw eigen verantwoordelijkheid (artikel 7).",
        "pl": "TASlation tłumaczy za pomocą PLaMo 3 Translate 2B firmy Preferred Networks (PFN). Jego licencja to PLaMo Community License w brzmieniu zmienionym 9 listopada 2026 r.:\n"
              "\u2022 Użytek osobisty i inny niekomercyjny jest bezpłatny i nie wymaga rejestracji. Użytek komercyjny wymaga wcześniejszej rejestracji w PFN (artykuł 3).\n"
              "\u2022 Musisz mieć ukończone 18 lat (lub być pełnoletni tam, gdzie mieszkasz) albo mieć zgodę rodzica lub opiekuna (artykuł 2).\n"
              "\u2022 Sam odpowiadasz za to, by mieć prawa do tego, co do niego wprowadzasz, i do tego, co z niego wychodzi; licencja nie daje żadnych praw do cudzych utworów (artykuł 9).\n"
              "\u2022 Tłumaczenie wykonane za jego pomocą można opublikować bez informacji, że jest wynikiem działania PLaMo, ale tłumaczenie opublikowane jako całość lub istotna część książki albo innej długiej publikacji musi podawać, że użyto PLaMo. Gdy przekazujesz komuś tłumaczenie lub udostępniasz je publicznie, musisz zaznaczyć, że modele na nim trenowane podlegają tej licencji (artykuł 5). TASlation prosi, by w ogóle nie publikować tłumaczeń.\n"
              "\u2022 Model jest udostępniany w obecnej postaci, bez żadnej gwarancji; za sposób jego użycia odpowiadasz sam (artykuł 7).",
        "ru": "TASlation переводит с помощью PLaMo 3 Translate 2B от Preferred Networks (PFN). Его лицензия — PLaMo Community License в редакции от 9 ноября 2026 года:\n"
              "\u2022 Личное и другое некоммерческое использование бесплатно и без регистрации. Для коммерческого использования нужно сначала зарегистрироваться у PFN (статья 3).\n"
              "\u2022 Вам должно быть 18 лет или больше (или вы должны быть совершеннолетним там, где живёте), либо нужно согласие родителя или опекуна (статья 2).\n"
              "\u2022 Вы сами отвечаете за то, чтобы у вас были права на то, что вы в него вводите, и на то, что он выдаёт; лицензия не даёт никаких прав на чужие произведения (статья 9).\n"
              "\u2022 Перевод, сделанный с его помощью, можно публиковать без указания, что это результат работы PLaMo, но если он публикуется как вся книга или другая длинная публикация либо как их существенная часть, нужно указать, что использовалась PLaMo. Передавая перевод кому-либо или публикуя его, вы должны указать, что на модели, обученные на нём, распространяется эта лицензия (статья 5). TASlation просит вообще не публиковать переводы.\n"
              "\u2022 Модель предоставляется как есть, без каких-либо гарантий; за то, как вы её используете, отвечаете вы (статья 7).",
        "tr": "TASlation, Preferred Networks (PFN) tarafından geliştirilen PLaMo 3 Translate 2B ile çeviri yapar. Lisansı, 9 Kasım 2026'da revize edilen haliyle PLaMo Community License'tır:\n"
              "\u2022 Kişisel ve diğer ticari olmayan kullanım ücretsizdir, kayıt gerekmez. Ticari kullanım için önce PFN'ye kayıt olmak gerekir (madde 3).\n"
              "\u2022 18 yaşında veya daha büyük (ya da yaşadığınız yerde reşit) olmalı ya da ebeveyninizin veya vasinizin onayını almalısınız (madde 2).\n"
              "\u2022 Ona verdiğiniz içerik ve ondan çıkan sonuç üzerindeki haklara sahip olmak sizin sorumluluğunuzdadır; lisans, başkalarının eserleri üzerinde hiçbir hak vermez (madde 9).\n"
              "\u2022 Onunla yapılan bir çeviri, PLaMo'nun çıktısı olduğu belirtilmeden yayımlanabilir; ancak bir kitabın veya başka uzun bir yayının tamamı ya da büyük bir kısmı olarak yayımlanırsa PLaMo'nun kullanıldığı belirtilmelidir. Bir çeviriyi birine verir veya herkese açarsanız, onunla eğitilen modellerin bu lisansa tabi olduğunu belirtmeniz gerekir (madde 5). TASlation, çevirileri hiç yayımlamamanızı rica eder.\n"
              "\u2022 Model olduğu gibi, hiçbir garanti olmadan sunulur; onu nasıl kullandığınız sizin sorumluluğunuzdadır (madde 7).",
        "id": "TASlation menerjemahkan dengan PLaMo 3 Translate 2B dari Preferred Networks (PFN). Lisensinya adalah PLaMo Community License, sebagaimana direvisi pada 9 November 2026:\n"
              "\u2022 Penggunaan pribadi dan penggunaan nonkomersial lainnya gratis, tanpa pendaftaran. Penggunaan komersial harus didaftarkan dulu ke PFN (pasal 3).\n"
              "\u2022 Anda harus berusia 18 tahun atau lebih (atau cukup umur di tempat tinggal Anda), atau mendapat persetujuan orang tua atau wali (pasal 2).\n"
              "\u2022 Anda bertanggung jawab memiliki hak atas apa yang Anda masukkan dan atas hasil yang keluar; lisensi ini tidak memberi hak apa pun atas karya orang lain (pasal 9).\n"
              "\u2022 Terjemahan yang dibuat dengannya boleh dipublikasikan tanpa keterangan bahwa itu hasil PLaMo, tetapi jika dipublikasikan sebagai seluruh atau sebagian besar sebuah buku atau publikasi panjang lainnya, harus disebutkan bahwa PLaMo digunakan. Jika Anda memberikan terjemahan kepada orang lain atau memublikasikannya, Anda harus menyatakan bahwa model yang dilatih dengannya tunduk pada lisensi ini (pasal 5). TASlation meminta Anda untuk sama sekali tidak memublikasikan terjemahan.\n"
              "\u2022 Model ini diberikan apa adanya, tanpa jaminan apa pun; cara Anda menggunakannya adalah tanggung jawab Anda (pasal 7).",
        "vi": "TASlation dịch bằng PLaMo 3 Translate 2B của Preferred Networks (PFN). Giấy phép của nó là PLaMo Community License, bản sửa đổi ngày 9 tháng 11 năm 2026:\n"
              "\u2022 Dùng cho cá nhân và các mục đích phi thương mại khác là miễn phí, không cần đăng ký. Dùng cho mục đích thương mại phải đăng ký với PFN trước (điều 3).\n"
              "\u2022 Bạn phải từ 18 tuổi trở lên (hoặc đủ tuổi thành niên nơi bạn sống), hoặc được cha mẹ hay người giám hộ đồng ý (điều 2).\n"
              "\u2022 Bạn tự chịu trách nhiệm có đủ quyền đối với nội dung bạn đưa vào và kết quả nhận được; giấy phép không trao bất kỳ quyền nào đối với tác phẩm của người khác (điều 9).\n"
              "\u2022 Bản dịch tạo bằng nó có thể được công bố mà không cần ghi đó là kết quả của PLaMo, nhưng nếu công bố như toàn bộ hoặc phần lớn một cuốn sách hay một ấn phẩm dài khác thì phải ghi rõ đã dùng PLaMo. Khi đưa bản dịch cho người khác hoặc công khai nó, bạn phải cho họ biết rằng các mô hình được huấn luyện bằng nó cũng thuộc giấy phép này (điều 5). TASlation đề nghị bạn hoàn toàn không công bố bản dịch.\n"
              "\u2022 Mô hình được cung cấp nguyên trạng, không có bất kỳ bảo đảm nào; bạn tự chịu trách nhiệm về cách mình sử dụng (điều 7).",
        "zh": "TASlation 使用 Preferred Networks (PFN) 的 PLaMo 3 Translate 2B 进行翻译。其许可为 PLaMo Community License（2026 年 11 月 9 日修订版）：\n"
              "\u2022 个人使用及其他非商业用途免费，无需注册。商业用途须先在 PFN 注册（第 3 条）。\n"
              "\u2022 您须年满 18 岁（或达到您所在地的成年年龄），或取得父母或监护人的同意（第 2 条）。\n"
              "\u2022 您须自行负责取得输入内容和输出结果所需的权利与许可；该许可不授予任何对他人作品的权利（第 9 条）。\n"
              "\u2022 用它生成的译文可以不注明是 PLaMo 的输出而公开；但作为书籍或其他长篇出版物的全部或主要部分公开时，必须注明使用了 PLaMo。把译文交给他人或公开时，须让对方知道用它训练的模型也适用本许可（第 5 条）。TASlation 请您完全不要公开译文。\n"
              "\u2022 该模型按现状提供，不附带任何保证；如何使用由您自己负责（第 7 条）。",
        "zh-tw": "TASlation 使用 Preferred Networks (PFN) 的 PLaMo 3 Translate 2B 進行翻譯。其授權為 PLaMo Community License（2026 年 11 月 9 日修訂版）：\n"
                 "\u2022 個人使用及其他非商業用途免費，無需註冊。商業用途須先向 PFN 註冊（第 3 條）。\n"
                 "\u2022 您須年滿 18 歲（或達到您所在地的成年年齡），或取得父母或監護人的同意（第 2 條）。\n"
                 "\u2022 您須自行負責取得輸入內容與輸出結果所需的權利與許可；本授權不給予任何對他人作品的權利（第 9 條）。\n"
                 "\u2022 用它產生的譯文可以不註明是 PLaMo 的輸出而公開；但作為書籍或其他長篇出版物的全部或主要部分公開時，必須註明使用了 PLaMo。把譯文交給他人或公開時，須讓對方知道用它訓練的模型也適用本授權（第 5 條）。TASlation 請您完全不要公開譯文。\n"
                 "\u2022 該模型依現狀提供，不附帶任何保證；如何使用由您自己負責（第 7 條）。",
        "ko": "TASlation은 Preferred Networks (PFN)의 PLaMo 3 Translate 2B로 번역합니다. 라이선스는 PLaMo Community License(2026년 11월 9일 개정)입니다.\n"
              "\u2022 개인 이용 등 비상업적 이용은 무료이며 등록이 필요 없습니다. 상업적으로 이용하려면 먼저 PFN에 등록해야 합니다(제3조).\n"
              "\u2022 18세 이상(또는 거주하는 나라의 성년)이거나, 부모 또는 보호자의 동의가 있어야 합니다(제2조).\n"
              "\u2022 입력하는 내용과 출력 결과를 사용하는 데 필요한 권리와 허락은 본인의 책임으로 확보해야 합니다. 이 라이선스는 다른 사람의 저작물에 대한 권리를 전혀 주지 않습니다(제9조).\n"
              "\u2022 이 모델로 만든 번역은 PLaMo의 출력물이라고 밝히지 않고 공개할 수 있습니다. 다만 책이나 그 밖의 긴 출판물의 전부 또는 상당 부분으로 공개할 때는 PLaMo를 사용했음을 밝혀야 합니다. 번역을 다른 사람에게 주거나 공개할 때는 그것으로 학습한 모델에도 이 라이선스가 적용된다는 것을 상대가 알 수 있게 표시해야 합니다(제5조). TASlation은 번역을 전혀 공개하지 않기를 부탁드립니다.\n"
              "\u2022 모델은 있는 그대로, 어떠한 보증도 없이 제공됩니다. 어떻게 사용하는지는 본인의 책임입니다(제7조).",
        "th": "TASlation แปลด้วย PLaMo 3 Translate 2B ของ Preferred Networks (PFN) สัญญาอนุญาตของโมเดลนี้คือ PLaMo Community License ฉบับแก้ไขเมื่อวันที่ 9 พฤศจิกายน 2026:\n"
              "\u2022 การใช้ส่วนตัวและการใช้อื่นที่ไม่ใช่เชิงพาณิชย์ใช้ได้ฟรี ไม่ต้องลงทะเบียน การใช้เชิงพาณิชย์ต้องลงทะเบียนกับ PFN ก่อน (ข้อ 3)\n"
              "\u2022 คุณต้องมีอายุ 18 ปีขึ้นไป (หรือบรรลุนิติภาวะตามที่ที่คุณอาศัยอยู่) หรือได้รับความยินยอมจากพ่อแม่หรือผู้ปกครอง (ข้อ 2)\n"
              "\u2022 คุณต้องรับผิดชอบเองในการมีสิทธิ์ในสิ่งที่ใส่เข้าไปและในผลลัพธ์ที่ได้ สัญญาอนุญาตนี้ไม่ให้สิทธิ์ใด ๆ ในผลงานของผู้อื่น (ข้อ 9)\n"
              "\u2022 คำแปลที่สร้างด้วยโมเดลนี้เผยแพร่ได้โดยไม่ต้องระบุว่าเป็นผลลัพธ์ของ PLaMo แต่ถ้าเผยแพร่เป็นหนังสือหรือสิ่งพิมพ์ขนาดยาวอื่นทั้งเล่มหรือเป็นส่วนสำคัญของสิ่งพิมพ์นั้น ต้องระบุว่าใช้ PLaMo เมื่อมอบคำแปลให้ผู้อื่นหรือเผยแพร่ ต้องแจ้งให้ผู้รับทราบว่าโมเดลที่ฝึกด้วยคำแปลนั้นอยู่ภายใต้สัญญาอนุญาตนี้ด้วย (ข้อ 5) TASlation ขอให้คุณไม่เผยแพร่คำแปลเลย\n"
              "\u2022 โมเดลนี้ให้มาตามสภาพ โดยไม่มีการรับประกันใด ๆ การใช้งานเป็นความรับผิดชอบของคุณเอง (ข้อ 7)",
    },
    "The full licence, in English and in Japanese:": {
        "ja": "ライセンスの全文（英語と日本語）:",
        "es": "La licencia completa, en inglés y en japonés:",
        "pt": "A licença completa, em inglês e em japonês:",
        "fr": "La licence complète, en anglais et en japonais :",
        "de": "Die vollständige Lizenz, auf Englisch und auf Japanisch:",
        "it": "La licenza completa, in inglese e in giapponese:",
        "nl": "De volledige licentie, in het Engels en in het Japans:",
        "pl": "Pełny tekst licencji, po angielsku i po japońsku:",
        "ru": "Полный текст лицензии, на английском и японском:",
        "tr": "Lisansın tam metni, İngilizce ve Japonca:",
        "id": "Lisensi lengkap, dalam bahasa Inggris dan Jepang:",
        "vi": "Toàn văn giấy phép, bằng tiếng Anh và tiếng Nhật:",
        "zh": "许可全文（英文和日文）：",
        "zh-tw": "授權全文（英文和日文）：",
        "ko": "라이선스 전문(영어, 일본어):",
        "th": "สัญญาอนุญาตฉบับเต็ม ภาษาอังกฤษและภาษาญี่ปุ่น:",
    },
    "I am 18 or older, or have a parent's or guardian's consent, and I agree to the PLaMo Community License.": {
        "ja": "18歳以上である（または親権者・法定代理人の同意がある）ことを確認し、PLaMo Community License に同意します。",
        "es": "Tengo 18 años o más, o el consentimiento de mis padres o tutores, y acepto la PLaMo Community License.",
        "pt": "Tenho 18 anos ou mais, ou o consentimento dos meus pais ou responsável, e concordo com a PLaMo Community License.",
        "fr": "J'ai 18 ans ou plus, ou l'accord d'un parent ou d'un tuteur, et j'accepte la PLaMo Community License.",
        "de": "Ich bin mindestens 18 Jahre alt oder habe die Zustimmung eines Elternteils oder Vormunds, und ich stimme der PLaMo Community License zu.",
        "it": "Ho almeno 18 anni, o il consenso di un genitore o tutore, e accetto la PLaMo Community License.",
        "nl": "Ik ben 18 jaar of ouder, of heb toestemming van een ouder of voogd, en ik ga akkoord met de PLaMo Community License.",
        "pl": "Mam ukończone 18 lat lub zgodę rodzica albo opiekuna i akceptuję PLaMo Community License.",
        "ru": "Мне 18 лет или больше, или у меня есть согласие родителя или опекуна, и я принимаю PLaMo Community License.",
        "tr": "18 yaşında veya daha büyüğüm ya da ebeveynimin veya vasimin onayı var ve PLaMo Community License'ı kabul ediyorum.",
        "id": "Saya berusia 18 tahun atau lebih, atau mendapat persetujuan orang tua atau wali, dan saya menyetujui PLaMo Community License.",
        "vi": "Tôi từ 18 tuổi trở lên, hoặc được cha mẹ hay người giám hộ đồng ý, và tôi đồng ý với PLaMo Community License.",
        "zh": "我已年满 18 岁，或已取得父母或监护人的同意，并同意 PLaMo Community License。",
        "zh-tw": "我已年滿 18 歲，或已取得父母或監護人的同意，並同意 PLaMo Community License。",
        "ko": "18세 이상이거나 부모 또는 보호자의 동의가 있으며, PLaMo Community License에 동의합니다.",
        "th": "ฉันอายุ 18 ปีขึ้นไป หรือได้รับความยินยอมจากพ่อแม่หรือผู้ปกครอง และยอมรับ PLaMo Community License",
    },
    "Agree and download": {
        "ja": "同意してダウンロード", "es": "Aceptar y descargar", "pt": "Concordar e baixar",
        "fr": "Accepter et télécharger", "de": "Zustimmen und herunterladen", "it": "Accetta e scarica",
        "nl": "Akkoord en downloaden", "pl": "Akceptuj i pobierz", "ru": "Принять и скачать", "tr": "Kabul et ve indir",
        "id": "Setujui dan unduh", "vi": "Đồng ý và tải xuống", "zh": "同意并下载", "zh-tw": "同意並下載",
        "ko": "동의하고 다운로드", "th": "ยอมรับและดาวน์โหลด",
    },
    "Translation model": {
        "ja": "翻訳モデル", "es": "Modelo de traducción", "pt": "Modelo de tradução", "fr": "Modèle de traduction",
        "de": "Übersetzungsmodell", "it": "Modello di traduzione", "nl": "Vertaalmodel", "pl": "Model tłumaczenia",
        "ru": "Модель перевода", "tr": "Çeviri modeli", "id": "Model terjemahan", "vi": "Mô hình dịch",
        "zh": "翻译模型", "zh-tw": "翻譯模型", "ko": "번역 모델", "th": "โมเดลแปลภาษา",
    },
    "Downloading {model}: {done} of {total} GB": {
        "ja": "{model} をダウンロード中: {done} / {total} GB",
        "es": "Descargando {model}: {done} de {total} GB",
        "pt": "Baixando {model}: {done} de {total} GB",
        "fr": "Téléchargement de {model} : {done} sur {total} GB",
        "de": "{model} wird heruntergeladen: {done} von {total} GB",
        "it": "Download di {model}: {done} di {total} GB",
        "nl": "{model} wordt gedownload: {done} van {total} GB",
        "pl": "Pobieranie {model}: {done} z {total} GB",
        "ru": "Скачивание {model}: {done} из {total} GB",
        "tr": "{model} indiriliyor: {done} / {total} GB",
        "id": "Mengunduh {model}: {done} dari {total} GB",
        "vi": "Đang tải {model}: {done} / {total} GB",
        "zh": "正在下载 {model}：{done} / {total} GB",
        "zh-tw": "正在下載 {model}：{done} / {total} GB",
        "ko": "{model} 다운로드 중: {done} / {total} GB",
        "th": "กำลังดาวน์โหลด {model}: {done} จาก {total} GB",
    },
    "Checking the download...": {
        "ja": "ダウンロードを確認しています...", "es": "Comprobando la descarga...", "pt": "Verificando o download...",
        "fr": "Vérification du téléchargement...", "de": "Der Download wird geprüft...",
        "it": "Verifica del download...", "nl": "De download wordt gecontroleerd...", "pl": "Sprawdzanie pobranego pliku...",
        "ru": "Проверка загрузки...", "tr": "İndirilen dosya denetleniyor...", "id": "Memeriksa unduhan...",
        "vi": "Đang kiểm tra bản tải xuống...", "zh": "正在检查下载的文件...", "zh-tw": "正在檢查下載的檔案...",
        "ko": "다운로드를 확인하는 중...", "th": "กำลังตรวจสอบไฟล์ที่ดาวน์โหลด...",
    },
    "Putting {model} into Ollama...": {
        "ja": "{model} を Ollama に取り込んでいます...",
        "es": "Pasando {model} a Ollama...",
        "pt": "Colocando {model} no Ollama...",
        "fr": "Installation de {model} dans Ollama...",
        "de": "{model} wird in Ollama übernommen...",
        "it": "Inserimento di {model} in Ollama...",
        "nl": "{model} wordt in Ollama gezet...",
        "pl": "Przenoszenie {model} do Ollama...",
        "ru": "{model} передаётся в Ollama...",
        "tr": "{model}, Ollama'ya aktarılıyor...",
        "id": "Memasukkan {model} ke Ollama...",
        "vi": "Đang đưa {model} vào Ollama...",
        "zh": "正在将 {model} 导入 Ollama...",
        "zh-tw": "正在將 {model} 匯入 Ollama...",
        "ko": "{model}을(를) Ollama에 넣는 중...",
        "th": "กำลังนำ {model} เข้าสู่ Ollama...",
    },
    "Downloading {model}: {percent} %": {
        "ja": "{model} をダウンロード中: {percent} %",
        "es": "Descargando {model}: {percent} %",
        "pt": "Baixando {model}: {percent} %",
        "fr": "Téléchargement de {model} : {percent} %",
        "de": "{model} wird heruntergeladen: {percent} %",
        "it": "Download di {model}: {percent} %",
        "nl": "{model} wordt gedownload: {percent} %",
        "pl": "Pobieranie {model}: {percent} %",
        "ru": "Скачивание {model}: {percent} %",
        "tr": "{model} indiriliyor: %{percent}",
        "id": "Mengunduh {model}: {percent} %",
        "vi": "Đang tải {model}: {percent} %",
        "zh": "正在下载 {model}：{percent} %",
        "zh-tw": "正在下載 {model}：{percent} %",
        "ko": "{model} 다운로드 중: {percent} %",
        "th": "กำลังดาวน์โหลด {model}: {percent} %",
    },
    "{model} is installed. TASlation translates into {language} now.": {
        "ja": "{model} をインストールしました。これで {language} に翻訳できます。",
        "es": "{model} está instalado. TASlation ya traduce al {language}.",
        "pt": "{model} está instalado. Agora o TASlation traduz para {language}.",
        "fr": "{model} est installé. TASlation traduit maintenant en {language}.",
        "de": "{model} ist installiert. TASlation übersetzt jetzt ins {language}.",
        "it": "{model} è installato. Ora TASlation traduce in {language}.",
        "nl": "{model} is geïnstalleerd. TASlation vertaalt nu naar het {language}.",
        "pl": "{model} jest zainstalowany. TASlation tłumaczy teraz na {language}.",
        "ru": "{model} установлена. Теперь TASlation переводит на {language}.",
        "tr": "{model} kuruldu. TASlation artık {language} diline çeviriyor.",
        "id": "{model} sudah terpasang. TASlation kini menerjemahkan ke {language}.",
        "vi": "Đã cài đặt {model}. Giờ TASlation dịch sang {language}.",
        "zh": "{model} 已安装。TASlation 现在可以译为{language}。",
        "zh-tw": "{model} 已安裝。TASlation 現在可以譯為{language}。",
        "ko": "{model}이(가) 설치되었습니다. 이제 TASlation이 {language}(으)로 번역합니다.",
        "th": "ติดตั้ง {model} แล้ว ตอนนี้ TASlation แปลเป็น{language}ได้",
    },
    "{old} was removed, freeing about {freed} GB.": {
        "ja": "{old} を削除しました。約 {freed} GB 空きました。",
        "es": "Se eliminó {old}; se liberaron unos {freed} GB.",
        "pt": "{old} foi removido, liberando cerca de {freed} GB.",
        "fr": "{old} a été supprimé, ce qui libère environ {freed} GB.",
        "de": "{old} wurde entfernt; etwa {freed} GB sind frei geworden.",
        "it": "{old} è stato rimosso, liberando circa {freed} GB.",
        "nl": "{old} is verwijderd; ongeveer {freed} GB is vrijgekomen.",
        "pl": "Usunięto {old}, zwalniając około {freed} GB.",
        "ru": "{old} удалена; освобождено около {freed} GB.",
        "tr": "{old} kaldırıldı; yaklaşık {freed} GB yer açıldı.",
        "id": "{old} telah dihapus, membebaskan sekitar {freed} GB.",
        "vi": "Đã gỡ {old}, giải phóng khoảng {freed} GB.",
        "zh": "已删除 {old}，腾出约 {freed} GB。",
        "zh-tw": "已刪除 {old}，騰出約 {freed} GB。",
        "ko": "{old}을(를) 삭제해 약 {freed} GB를 확보했습니다.",
        "th": "ลบ {old} แล้ว คืนพื้นที่ประมาณ {freed} GB",
    },
    "Stopped. Nothing was left on the disk.": {
        "ja": "中止しました。ディスクには何も残っていません。",
        "es": "Detenido. No ha quedado nada en el disco.",
        "pt": "Interrompido. Nada ficou no disco.",
        "fr": "Arrêté. Rien n'est resté sur le disque.",
        "de": "Abgebrochen. Auf dem Datenträger ist nichts zurückgeblieben.",
        "it": "Interrotto. Sul disco non è rimasto nulla.",
        "nl": "Gestopt. Er is niets op de schijf achtergebleven.",
        "pl": "Zatrzymano. Na dysku nic nie zostało.",
        "ru": "Остановлено. На диске ничего не осталось.",
        "tr": "Durduruldu. Diskte hiçbir şey kalmadı.",
        "id": "Dihentikan. Tidak ada yang tertinggal di disk.",
        "vi": "Đã dừng. Không có gì còn sót lại trên ổ đĩa.",
        "zh": "已停止。磁盘上没有留下任何东西。",
        "zh-tw": "已停止。磁碟上沒有留下任何東西。",
        "ko": "중지했습니다. 디스크에 남은 것은 없습니다.",
        "th": "หยุดแล้ว ไม่มีสิ่งใดค้างอยู่บนดิสก์",
    },
    "{model} could not be installed: the publisher's server refused the download or no longer has this file. Trying again will not help: update TASlation (a newer version names the current file), or look at the project's issues page. Nothing was left on the disk.": {
        "ja": "{model} をインストールできませんでした。配布元のサーバーがダウンロードを拒否したか、このファイルをもう置いていません。もう一度試しても変わりません。TASlation を更新するか（新しい版は現在のファイルを指定しています）、プロジェクトの Issues ページをご覧ください。ディスクには何も残っていません。",
        "es": "No se pudo instalar {model}: el servidor del editor rechazó la descarga o ya no tiene este archivo. Volver a intentarlo no servirá: actualiza TASlation (una versión más reciente indica el archivo actual) o consulta la página de incidencias (issues) del proyecto. No ha quedado nada en el disco.",
        "pt": "Não foi possível instalar {model}: o servidor do publicador recusou o download ou não tem mais este arquivo. Tentar de novo não vai adiantar: atualize o TASlation (uma versão mais nova indica o arquivo atual) ou veja a página de issues do projeto. Nada ficou no disco.",
        "fr": "{model} n'a pas pu être installé : le serveur de l'éditeur a refusé le téléchargement ou n'a plus ce fichier. Réessayer n'y changera rien : mettez TASlation à jour (une version plus récente indique le fichier actuel) ou consultez la page des tickets (issues) du projet. Rien n'est resté sur le disque.",
        "de": "{model} konnte nicht installiert werden: Der Server des Anbieters hat den Download abgelehnt oder hat diese Datei nicht mehr. Ein neuer Versuch hilft nicht: Aktualisieren Sie TASlation (eine neuere Version nennt die aktuelle Datei) oder sehen Sie auf der Issues-Seite des Projekts nach. Auf dem Datenträger ist nichts zurückgeblieben.",
        "it": "Non è stato possibile installare {model}: il server dell'editore ha rifiutato il download o non ha più questo file. Riprovare non servirà: aggiorna TASlation (una versione più recente indica il file attuale) oppure consulta la pagina delle segnalazioni (issues) del progetto. Sul disco non è rimasto nulla.",
        "nl": "{model} kon niet worden geïnstalleerd: de server van de uitgever weigerde de download of heeft dit bestand niet meer. Opnieuw proberen helpt niet: werk TASlation bij (een nieuwere versie noemt het huidige bestand) of kijk op de issues-pagina van het project. Er is niets op de schijf achtergebleven.",
        "pl": "Nie udało się zainstalować {model}: serwer wydawcy odmówił pobrania albo nie ma już tego pliku. Ponowna próba nic nie da: zaktualizuj TASlation (nowsza wersja wskazuje aktualny plik) albo zajrzyj na stronę zgłoszeń (issues) projektu. Na dysku nic nie zostało.",
        "ru": "Не удалось установить {model}: сервер издателя отказал в загрузке или этого файла у него больше нет. Повторная попытка не поможет: обновите TASlation (в более новой версии указан текущий файл) или загляните на страницу issues проекта. На диске ничего не осталось.",
        "tr": "{model} kurulamadı: yayıncının sunucusu indirmeyi reddetti ya da bu dosya artık onda yok. Yeniden denemek işe yaramaz: TASlation'ı güncelleyin (daha yeni bir sürüm güncel dosyayı belirtir) ya da projenin issues sayfasına bakın. Diskte hiçbir şey kalmadı.",
        "id": "{model} tidak dapat dipasang: server penerbit menolak unduhan atau tidak lagi memiliki berkas ini. Mencoba lagi tidak akan membantu: perbarui TASlation (versi yang lebih baru menyebut berkas yang berlaku) atau lihat halaman issues proyek. Tidak ada yang tertinggal di disk.",
        "vi": "Không cài đặt được {model}: máy chủ của nhà phát hành đã từ chối tải xuống hoặc không còn tệp này. Thử lại cũng không giúp được: hãy cập nhật TASlation (phiên bản mới hơn chỉ định tệp hiện hành) hoặc xem trang issues của dự án. Không có gì còn sót lại trên ổ đĩa.",
        "zh": "无法安装 {model}：发布方的服务器拒绝了下载，或已不再提供此文件。重试也没有用：请更新 TASlation（较新的版本指定了当前的文件），或查看项目的 issues 页面。磁盘上没有留下任何东西。",
        "zh-tw": "無法安裝 {model}：發布方的伺服器拒絕了下載，或已不再提供此檔案。重試也沒有用：請更新 TASlation（較新的版本指定了目前的檔案），或查看專案的 issues 頁面。磁碟上沒有留下任何東西。",
        "ko": "{model}을(를) 설치하지 못했습니다. 배포처의 서버가 다운로드를 거부했거나 이 파일이 더 이상 없습니다. 다시 시도해도 소용없습니다. TASlation을 업데이트하거나(새 버전은 현재 파일을 지정합니다) 프로젝트의 issues 페이지를 확인하세요. 디스크에 남은 것은 없습니다.",
        "th": "ติดตั้ง {model} ไม่ได้: เซิร์ฟเวอร์ของผู้เผยแพร่ปฏิเสธการดาวน์โหลด หรือไม่มีไฟล์นี้แล้ว ลองอีกครั้งก็ไม่ช่วย: อัปเดต TASlation (เวอร์ชันใหม่กว่าระบุไฟล์ปัจจุบัน) หรือดูหน้า issues ของโปรเจกต์ ไม่มีสิ่งใดค้างอยู่บนดิสก์",
    },
    "{model} could not be installed. Check the network and the disk space, and try again. Nothing was left on the disk.": {
        "ja": "{model} をインストールできませんでした。ネットワークとディスクの空きを確認して、もう一度お試しください。ディスクには何も残っていません。",
        "es": "No se pudo instalar {model}. Comprueba la red y el espacio en disco y vuelve a intentarlo. No ha quedado nada en el disco.",
        "pt": "Não foi possível instalar {model}. Verifique a rede e o espaço em disco e tente de novo. Nada ficou no disco.",
        "fr": "{model} n'a pas pu être installé. Vérifiez le réseau et l'espace disque, puis réessayez. Rien n'est resté sur le disque.",
        "de": "{model} konnte nicht installiert werden. Prüfen Sie das Netzwerk und den freien Speicherplatz und versuchen Sie es noch einmal. Auf dem Datenträger ist nichts zurückgeblieben.",
        "it": "Non è stato possibile installare {model}. Controlla la rete e lo spazio su disco e riprova. Sul disco non è rimasto nulla.",
        "nl": "{model} kon niet worden geïnstalleerd. Controleer het netwerk en de schijfruimte en probeer het opnieuw. Er is niets op de schijf achtergebleven.",
        "pl": "Nie udało się zainstalować {model}. Sprawdź sieć i miejsce na dysku, a potem spróbuj ponownie. Na dysku nic nie zostało.",
        "ru": "Не удалось установить {model}. Проверьте сеть и свободное место на диске и попробуйте ещё раз. На диске ничего не осталось.",
        "tr": "{model} kurulamadı. Ağı ve disk alanını denetleyip yeniden deneyin. Diskte hiçbir şey kalmadı.",
        "id": "{model} tidak dapat dipasang. Periksa jaringan dan ruang disk, lalu coba lagi. Tidak ada yang tertinggal di disk.",
        "vi": "Không cài đặt được {model}. Hãy kiểm tra mạng và dung lượng ổ đĩa rồi thử lại. Không có gì còn sót lại trên ổ đĩa.",
        "zh": "无法安装 {model}。请检查网络和磁盘空间后重试。磁盘上没有留下任何东西。",
        "zh-tw": "無法安裝 {model}。請檢查網路和磁碟空間後再試一次。磁碟上沒有留下任何東西。",
        "ko": "{model}을(를) 설치하지 못했습니다. 네트워크와 디스크 공간을 확인한 뒤 다시 시도하세요. 디스크에 남은 것은 없습니다.",
        "th": "ติดตั้ง {model} ไม่ได้ ตรวจสอบเครือข่ายและพื้นที่ดิสก์ แล้วลองอีกครั้ง ไม่มีสิ่งใดค้างอยู่บนดิสก์",
    },
    "There is too little disk space for {model}. Nothing was downloaded.": {
        "ja": "{model} を入れるにはディスクの空きが足りません。何もダウンロードしていません。",
        "es": "No hay espacio suficiente en el disco para {model}. No se ha descargado nada.",
        "pt": "Não há espaço suficiente em disco para {model}. Nada foi baixado.",
        "fr": "Il n'y a pas assez d'espace disque pour {model}. Rien n'a été téléchargé.",
        "de": "Für {model} ist zu wenig Speicherplatz frei. Es wurde nichts heruntergeladen.",
        "it": "Non c'è abbastanza spazio su disco per {model}. Non è stato scaricato nulla.",
        "nl": "Er is te weinig schijfruimte voor {model}. Er is niets gedownload.",
        "pl": "Za mało miejsca na dysku dla {model}. Niczego nie pobrano.",
        "ru": "Для {model} слишком мало места на диске. Ничего не скачано.",
        "tr": "{model} için disk alanı yetersiz. Hiçbir şey indirilmedi.",
        "id": "Ruang disk tidak cukup untuk {model}. Tidak ada yang diunduh.",
        "vi": "Ổ đĩa không đủ chỗ cho {model}. Chưa tải xuống gì cả.",
        "zh": "磁盘空间不足，无法安装 {model}。没有下载任何内容。",
        "zh-tw": "磁碟空間不足，無法安裝 {model}。沒有下載任何內容。",
        "ko": "{model}을(를) 위한 디스크 공간이 부족합니다. 아무것도 다운로드하지 않았습니다.",
        "th": "พื้นที่ดิสก์ไม่พอสำหรับ {model} ยังไม่ได้ดาวน์โหลดสิ่งใด",
    },
    "The language stays {before}: {language} needs {model}, which is not installed.": {
        "ja": "翻訳先は {before} のままです。{language} には {model} が必要ですが、インストールされていません。",
        "es": "El idioma sigue siendo {before}: el {language} necesita {model}, que no está instalado.",
        "pt": "O idioma continua {before}: {language} precisa de {model}, que não está instalado.",
        "fr": "La langue reste {before} : le {language} demande {model}, qui n'est pas installé.",
        "de": "Die Sprache bleibt {before}: {language} braucht {model}, das nicht installiert ist.",
        "it": "La lingua resta {before}: {language} richiede {model}, che non è installato.",
        "nl": "De taal blijft {before}: het {language} vraagt {model}, dat niet is geïnstalleerd.",
        "pl": "Język pozostaje bez zmian ({before}): {language} wymaga modelu {model}, który nie jest zainstalowany.",
        "ru": "Язык остаётся прежним ({before}): для языка {language} нужна модель {model}, которая не установлена.",
        "tr": "Dil {before} olarak kalıyor: {language} için {model} gerekiyor ve kurulu değil.",
        "id": "Bahasa tetap {before}: {language} memerlukan {model}, yang belum terpasang.",
        "vi": "Ngôn ngữ vẫn là {before}: {language} cần {model}, hiện chưa được cài đặt.",
        "zh": "目标语言仍为{before}：{language}需要 {model}，但它尚未安装。",
        "zh-tw": "目標語言仍為{before}：{language}需要 {model}，但它尚未安裝。",
        "ko": "번역 언어는 {before}(으)로 유지됩니다. {language}에는 {model}이(가) 필요하지만 설치되어 있지 않습니다.",
        "th": "ภาษายังคงเป็น{before}: {language}ต้องใช้ {model} ซึ่งยังไม่ได้ติดตั้ง",
    },
    "Translation is off: {language} needs {model}, which is not installed. Choose {language} in the To list again to install it.": {
        "ja": "翻訳は止まっています。{language} には {model} が必要ですが、インストールされていません。インストールするには「翻訳先」で {language} をもう一度選んでください。",
        "es": "La traducción está desactivada: el {language} necesita {model}, que no está instalado. Para instalarlo, vuelve a elegir {language} en la lista «A».",
        "pt": "A tradução está desligada: {language} precisa de {model}, que não está instalado. Para instalá-lo, escolha {language} de novo na lista «Para».",
        "fr": "La traduction est désactivée : le {language} demande {model}, qui n'est pas installé. Pour l'installer, choisissez à nouveau {language} dans la liste « Vers ».",
        "de": "Die Übersetzung ist aus: {language} braucht {model}, das nicht installiert ist. Wählen Sie {language} in der Liste „Nach“ erneut, um es zu installieren.",
        "it": "La traduzione è disattivata: {language} richiede {model}, che non è installato. Per installarlo, scegli di nuovo {language} nell'elenco «In».",
        "nl": "Vertalen staat uit: het {language} vraagt {model}, dat niet is geïnstalleerd. Kies {language} opnieuw in de lijst 'Naar' om het te installeren.",
        "pl": "Tłumaczenie jest wyłączone: {language} wymaga modelu {model}, który nie jest zainstalowany. Aby go zainstalować, wybierz ponownie {language} na liście „Na”.",
        "ru": "Перевод отключён: для языка {language} нужна модель {model}, которая не установлена. Чтобы установить её, снова выберите {language} в списке «На».",
        "tr": "Çeviri kapalı: {language} için {model} gerekiyor ve kurulu değil. Kurmak için «Hedef» listesinde {language} dilini yeniden seçin.",
        "id": "Terjemahan mati: {language} memerlukan {model}, yang belum terpasang. Untuk memasangnya, pilih lagi {language} di daftar \"Ke\".",
        "vi": "Đang tắt dịch: {language} cần {model}, hiện chưa được cài đặt. Để cài đặt, hãy chọn lại {language} trong danh sách \"Sang\".",
        "zh": "翻译已关闭：{language}需要 {model}，但它尚未安装。要安装它，请在“译为”列表中再次选择{language}。",
        "zh-tw": "翻譯已關閉：{language}需要 {model}，但它尚未安裝。要安裝它，請在「譯為」清單中再次選擇{language}。",
        "ko": "번역이 꺼져 있습니다. {language}에는 {model}이(가) 필요하지만 설치되어 있지 않습니다. 설치하려면 '번역 언어' 목록에서 {language}을(를) 다시 선택하세요.",
        "th": "การแปลปิดอยู่: {language}ต้องใช้ {model} ซึ่งยังไม่ได้ติดตั้ง หากต้องการติดตั้ง ให้เลือก{language}ในรายการ \"แปลเป็น\" อีกครั้ง",
    },
    "Translation is off: {language} needs {model}, which is not installed. TASlation asks about it when you are back in its window.": {
        "ja": "翻訳は止まっています。{language} には {model} が必要ですが、インストールされていません。TASlation のウィンドウに戻ったときにお尋ねします。",
        "es": "La traducción está desactivada: el {language} necesita {model}, que no está instalado. TASlation te lo preguntará cuando vuelvas a su ventana.",
        "pt": "A tradução está desligada: {language} precisa de {model}, que não está instalado. O TASlation pergunta sobre isso quando você voltar à janela dele.",
        "fr": "La traduction est désactivée : le {language} demande {model}, qui n'est pas installé. TASlation vous le proposera quand vous reviendrez à sa fenêtre.",
        "de": "Die Übersetzung ist aus: {language} braucht {model}, das nicht installiert ist. TASlation fragt danach, wenn Sie wieder in seinem Fenster sind.",
        "it": "La traduzione è disattivata: {language} richiede {model}, che non è installato. TASlation te lo chiederà quando tornerai alla sua finestra.",
        "nl": "Vertalen staat uit: het {language} vraagt {model}, dat niet is geïnstalleerd. TASlation vraagt ernaar zodra u terug bent in het venster.",
        "pl": "Tłumaczenie jest wyłączone: {language} wymaga modelu {model}, który nie jest zainstalowany. TASlation zapyta o to, gdy wrócisz do jego okna.",
        "ru": "Перевод отключён: для языка {language} нужна модель {model}, которая не установлена. TASlation спросит об этом, когда вы вернётесь в его окно.",
        "tr": "Çeviri kapalı: {language} için {model} gerekiyor ve kurulu değil. TASlation penceresine döndüğünüzde bunu soracak.",
        "id": "Terjemahan mati: {language} memerlukan {model}, yang belum terpasang. TASlation akan menanyakannya saat Anda kembali ke jendelanya.",
        "vi": "Đang tắt dịch: {language} cần {model}, hiện chưa được cài đặt. TASlation sẽ hỏi bạn khi bạn quay lại cửa sổ của nó.",
        "zh": "翻译已关闭：{language}需要 {model}，但它尚未安装。回到 TASlation 窗口时，它会询问您。",
        "zh-tw": "翻譯已關閉：{language}需要 {model}，但它尚未安裝。回到 TASlation 視窗時，它會詢問您。",
        "ko": "번역이 꺼져 있습니다. {language}에는 {model}이(가) 필요하지만 설치되어 있지 않습니다. TASlation 창으로 돌아오면 이에 대해 묻습니다.",
        "th": "การแปลปิดอยู่: {language}ต้องใช้ {model} ซึ่งยังไม่ได้ติดตั้ง TASlation จะถามเรื่องนี้เมื่อคุณกลับมาที่หน้าต่างของโปรแกรม",
    },
}

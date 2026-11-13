"""The legal notice shown when the window starts, in the window's language, until the reader ticks "do not show
this again": a general part (here) and a part for the reader's country (``jurisdictions``).

What it says, and why, is in README "Legal position". The general text says the same thing in every language,
written in each language's own register rather than translated word for word. The reader's choices are remembered
in ``~/.taslation/notice.json`` (the country, the notice version dismissed, the time, the language it was shown
in); raising ``NOTICE_VERSION`` shows it again. The command line prints the notice once, the first time a command
reads a book, and remembers that separately.
"""

from __future__ import annotations

import re

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from . import jurisdictions
from .atomic import write_atomic

NOTICE_VERSION = 6  # 6: PLaMo's licence on published translations (article 5)
DEFAULT = "en"

TITLES: dict[str, str] = {
    "en": "Before you start", "ja": "ご利用の前に", "es": "Antes de empezar", "pt": "Antes de começar",
    "fr": "Avant de commencer", "de": "Bevor Sie beginnen", "it": "Prima di iniziare", "nl": "Voordat u begint",
    "pl": "Zanim zaczniesz", "ru": "Прежде чем начать", "tr": "Başlamadan önce", "id": "Sebelum memulai",
    "vi": "Trước khi bắt đầu", "zh": "开始之前", "zh-tw": "開始之前", "ko": "시작하기 전에",
    "th": "ก่อนเริ่มใช้งาน",
}

# (acknowledge, quit)
BUTTONS: dict[str, tuple[str, str]] = {
    "en": ("I understand", "Quit"), "ja": ("理解しました", "終了"), "es": ("Entendido", "Salir"),
    "pt": ("Entendi", "Sair"), "fr": ("J'ai compris", "Quitter"), "de": ("Verstanden", "Beenden"),
    "it": ("Ho capito", "Esci"), "nl": ("Begrepen", "Afsluiten"), "pl": ("Rozumiem", "Zakończ"),
    "ru": ("Понятно", "Выход"), "tr": ("Anladım", "Çık"), "id": ("Saya mengerti", "Keluar"),
    "vi": ("Tôi đã hiểu", "Thoát"), "zh": ("我已了解", "退出"), "zh-tw": ("我已了解", "結束"),
    "ko": ("이해했습니다", "종료"), "th": ("ฉันเข้าใจแล้ว", "ออก"),
}

# the "do not show this again" box
CHECKBOX: dict[str, str] = {
    "en": "Do not show this again", "ja": "次回以降表示しない", "es": "No volver a mostrar",
    "pt": "Não mostrar novamente", "fr": "Ne plus afficher", "de": "Nicht mehr anzeigen", "it": "Non mostrare più",
    "nl": "Niet meer tonen", "pl": "Nie pokazuj ponownie", "ru": "Больше не показывать", "tr": "Bir daha gösterme",
    "id": "Jangan tampilkan lagi", "vi": "Không hiển thị lại", "zh": "不再显示", "zh-tw": "不再顯示",
    "ko": "다시 표시하지 않음", "th": "ไม่ต้องแสดงอีก",
}

# the labels of the two choosers at the top of the dialog
COUNTRY_LABEL: dict[str, str] = {
    "en": "Where you read:", "ja": "読む場所（国・地域）:", "es": "Dónde lees:", "pt": "Onde você lê:", "fr": "Où vous lisez :",
    "de": "Wo Sie lesen:", "it": "Dove leggi:", "nl": "Waar u leest:", "pl": "Gdzie czytasz:", "ru": "Где вы читаете:",
    "tr": "Okuduğunuz yer:", "id": "Tempat Anda membaca:", "vi": "Nơi bạn đọc:", "zh": "您阅读所在的国家或地区：",
    "zh-tw": "您閱讀所在的國家或地區：", "ko": "읽는 국가·지역:", "th": "สถานที่ที่คุณอ่าน:",
}
LANGUAGE_LABEL: dict[str, str] = {
    "en": "Language:", "ja": "言語:", "es": "Idioma:", "pt": "Idioma:", "fr": "Langue :", "de": "Sprache:",
    "it": "Lingua:", "nl": "Taal:", "pl": "Język:", "ru": "Язык:", "tr": "Dil:", "id": "Bahasa:", "vi": "Ngôn ngữ:",
    "zh": "语言：", "zh-tw": "語言：", "ko": "언어:", "th": "ภาษา:",
}

TEXTS: dict[str, str] = {
    "en": """TASlation shows the pages of a book that you have opened in your own viewer, with the Japanese lettering replaced by a machine translation, on this computer only. Page images are held in memory and never saved; nothing is sent anywhere except to the translation program on this computer; only translated text is kept.

Whether you may do this depends on where you live. In Japan, copying and translating a work for your own private use is permitted by the Copyright Act (Articles 30 and 47-6); many other countries allow less, or nothing of the kind, and your bookshop's terms of use may forbid screen capture. The part for your country below says more. Where it says that a translation for yourself "infringes in law as a civil matter", that means the rights holder could ask a civil court to stop it or to award damages; it is not a crime, so no police or prosecutor is involved, and no one has ever been sued over a private, unshared translation. The law that applies is that of the place where you read, whatever country the book or the store is in. Checking the law and the terms that apply to you is your responsibility.

Never post, share or publish translated pages or the translated text. That is distributing a derivative work and infringes the author's rights everywhere. TASlation therefore exports nothing readable: the only way your translations leave it is as a backup file encrypted with your passphrase, meant for your own other computer or as a copy for yourself, not for anyone else.

TASlation does not filter or censor what your viewer shows; you see the book as published. Manga published in Japan may contain depictions, drawn ones included, that are illegal to possess, import or view where you are, even for private reading and even though they are lawful in Japan. In several countries mere possession is a serious crime; the usual example is sexual drawings of characters who look like minors, lawful in Japan and not there, whereas sexual images of real children are a crime everywhere, Japan included. TASlation keeps no copies, but the books you own and anything you save are yours to answer for.

In practice the risks come in this order: the laws of your country on possessing certain content; your store closing your account for breaking its terms; and copyright, which becomes real only if you share what you translated.

Translations come from a local AI model and can be wrong, including names, numbers and the sense of a line. Do not rely on them for anything that matters. The translation model PLaMo, which TASlation uses for most languages, has a licence of its own: if a translation made with it is ever published, it must say clearly that it is PLaMo's output (PLaMo Community License, article 5).

TASlation is provided as is, without any warranty, under the MIT licence. To the extent the law allows, its author accepts no liability for any damage or legal consequence arising from its use, from the books you read with it or from this notice, which summarises laws that change and is not legal advice. By continuing you accept this.

The README describes the legal position in more detail. This notice appears at every start until you tick the box below. To read it again at any time, use Help > Legal notice... in the window.""",
    "ja": """TASlation は、お使いのビューアで開いている本のページを、日本語の文字を機械翻訳に置き換えて、このパソコンの画面上にだけ表示します。ページ画像はメモリ上にのみ置かれ、保存されません。このパソコン内の翻訳プログラム以外にデータを送ることはなく、保存されるのは翻訳文だけです。

この利用が許されるかどうかは、お住まいの国や地域の法律によります。日本では、私的使用のための複製と翻訳は著作権法（第30条・第47条の6）で認められていますが、他の多くの国ではこの範囲が狭いか、認められていません。また、ご利用の電子書店の利用規約が画面の取り込みを禁じている場合があります。下の国別の項に詳しく書いてあります。そこで「自分用の翻訳は法律上は侵害にあたる民事上の問題」とあるのは、権利者が民事裁判で差止めや賠償を求める根拠にはなるが、警察や検察が動く犯罪ではない、という意味です。共有しない私的な翻訳が訴えられた例はありません。適用されるのは、本や書店の国ではなく、あなたが読んでいる場所の法律です。適用される法律と規約の確認は、ご自身の責任で行ってください。

翻訳したページや翻訳文を投稿・共有・公開することは絶対にしないでください。二次的著作物の頒布にあたり、どの国でも著作者の権利を侵害します。そのため TASlation は読める形では何も書き出しません。訳文を外に出す唯一の方法は、自分のパスフレーズで暗号化したバックアップファイルで、自分の別のパソコンに移したり控えを取ったりするためのものです。他人に渡すためのものではありません。

TASlation は、ビューアに表示される内容を一切検閲・フィルタリングせず、本を出版されたままの形で表示します。日本で出版された漫画には、日本では合法でも、お住まいの国では所持・輸入・閲覧が違法となる表現（絵によるものを含む）が含まれることがあります。国によっては、私的な閲覧目的であっても単純所持だけで重い犯罪となります。典型は、未成年に見えるキャラクターの性的な描写（絵）で、日本では合法でも国によっては所持だけで犯罪です。実在する未成年者の性的な画像は、日本を含むどの国でも犯罪です。TASlation は複製を残しませんが、お持ちの本や、ご自身で保存したものについての責任はご本人にあります。

現実の危険は、大きい順に次のとおりです。お住まいの国で特定の内容の所持を罰する法律、規約違反による書店のアカウント停止、そして著作権。著作権は、訳したものを共有したときに初めて現実の問題になります。

翻訳はこのパソコン上の AI モデルによるもので、名前・数字・文の意味を含めて誤ることがあります。重要な判断の根拠にはしないでください。TASlation がほとんどの言語で使う翻訳モデル PLaMo には独自のライセンスがあり、これで作った翻訳を公表する場合は、PLaMo の生成物であることを明示しなければなりません（PLaMo Community License 第5条）。

TASlation は MIT ライセンスのもと、現状のまま、いかなる保証もなく提供されます。法令が許す限りにおいて、作者は、本ソフトウェアの使用、本ソフトウェアで読んだ本、およびこの案内（変わり得る法律の要約であり、法的助言ではありません）から生じるいかなる損害や法的な結果についても責任を負いません。続行することで、これに同意したものとします。

詳しい法的な考え方は README に記載しています。この案内は、下のチェックを入れるまで起動のたびに表示されます。読み直すには、ウィンドウの「ヘルプ」メニューの「法的な注意事項...」を使ってください。""",
    "es": """TASlation muestra, solo en este ordenador, las páginas del libro que tienes abierto en tu propio visor, con el texto japonés sustituido por una traducción automática. Las imágenes de las páginas se mantienen únicamente en memoria y nunca se guardan; no se envía nada a ningún sitio salvo al programa de traducción de este ordenador; solo se conserva el texto traducido.

Que puedas hacer esto depende del lugar donde vives. En Japón, la Ley de Derechos de Autor permite copiar y traducir una obra para tu uso privado (artículos 30 y 47-6); muchos otros países permiten menos o no permiten nada parecido, y las condiciones de uso de tu librería digital pueden prohibir la captura de pantalla. La parte dedicada a tu país, más abajo, da más detalles. Cuando allí se lee que una traducción para uno mismo «constituye en derecho una infracción, de carácter civil», significa que el titular de los derechos podría pedir a un tribunal civil que ordenara su cese o que le concediera una indemnización por daños y perjuicios; no es un delito, así que no intervienen ni la policía ni la fiscalía, y nunca se ha demandado a nadie por una traducción privada y no compartida. La ley que se aplica es la del lugar donde lees, sea cual sea el país del libro o de la tienda. Comprobar la ley y las condiciones que se te aplican es tu responsabilidad.

Nunca publiques, compartas ni difundas páginas traducidas ni el texto traducido: eso es distribuir una obra derivada e infringe los derechos del autor en cualquier país. Por eso TASlation no exporta nada legible: la única forma de que tus traducciones salgan de él es un archivo de copia de seguridad cifrado con tu contraseña, pensado para tu otro ordenador o como copia para ti, no para nadie más.

TASlation no filtra ni censura lo que muestra tu visor: ves el libro tal como se publicó. El manga publicado en Japón puede contener representaciones, incluidas las dibujadas, cuya posesión, importación o visualización sea ilegal donde te encuentres, incluso para la lectura privada y aunque sean legales en Japón. En varios países la mera posesión es un delito grave; el ejemplo habitual son los dibujos sexuales de personajes que parecen menores, legales en Japón pero no allí, mientras que las imágenes sexuales de niños reales son delito en todas partes, Japón incluido. TASlation no conserva copias, pero los libros que posees y todo lo que guardes son responsabilidad tuya.

En la práctica, los riesgos son, por este orden: las leyes de tu país sobre la posesión de determinados contenidos; que tu tienda cierre tu cuenta por incumplir sus condiciones; y los derechos de autor, que solo se convierten en un riesgo real si compartes lo que has traducido.

Las traducciones proceden de un modelo de IA local y pueden ser erróneas, incluso en nombres, números y el sentido de una frase. No te fíes de ellas para nada importante. El modelo de traducción PLaMo, que TASlation usa para la mayoría de los idiomas, tiene su propia licencia: si alguna vez se publica una traducción hecha con él, debe indicar claramente que es un resultado de PLaMo (PLaMo Community License, artículo 5).

TASlation se ofrece tal cual, sin garantía alguna, bajo la licencia MIT. En la medida en que la ley lo permita, su autor declina toda responsabilidad por cualquier daño o consecuencia jurídica que se derive de su uso, de los libros que leas con él o de este aviso, que resume leyes cambiantes y no constituye asesoramiento jurídico. Al continuar, lo aceptas.

El README describe la situación jurídica con más detalle. Este aviso aparece cada vez que se inicia el programa hasta que marques la casilla de abajo. Para volver a leerlo en cualquier momento, usa Ayuda > Aviso legal... en la ventana.""",
    "pt": """O TASlation mostra, somente neste computador, as páginas do livro que você abriu no seu próprio leitor, com o texto em japonês substituído por uma tradução automática. As imagens das páginas ficam apenas na memória e nunca são salvas; nada é enviado a lugar algum além do programa de tradução deste computador; só o texto traduzido é guardado.

Se você pode ou não fazer isso depende de onde você mora. No Japão, a Lei de Direitos Autorais permite copiar e traduzir uma obra para uso privado (artigos 30 e 47-6); muitos outros países permitem menos ou não permitem nada parecido, e os termos de uso da sua livraria digital podem proibir a captura de tela. A parte sobre o seu país, mais abaixo, traz mais detalhes. Quando ela diz que uma tradução para uso próprio "é, em direito, uma violação, de natureza civil", isso significa que o titular dos direitos poderia pedir a um tribunal cível que a fizesse cessar ou fixasse uma indenização; não é crime, portanto nem a polícia nem o Ministério Público intervêm, e ninguém jamais foi processado por uma tradução privada e não compartilhada. A lei que se aplica é a do lugar onde você lê, seja qual for o país do livro ou da loja. Verificar a lei e os termos que se aplicam a você é responsabilidade sua.

Nunca publique, compartilhe ou divulgue páginas traduzidas nem o texto traduzido: isso é distribuir uma obra derivada e viola os direitos do autor em qualquer país. Por isso o TASlation não exporta nada legível: o único modo de as suas traduções saírem dele é um arquivo de backup criptografado com a sua senha, pensado para o seu outro computador ou como cópia para você, não para mais ninguém.

O TASlation não filtra nem censura o que o seu leitor mostra: você vê o livro como foi publicado. Mangás publicados no Japão podem conter representações, inclusive desenhadas, cuja posse, importação ou visualização seja ilegal onde você estiver, mesmo para leitura privada e mesmo sendo legais no Japão. Em vários países a simples posse é crime grave; o exemplo habitual são desenhos sexuais de personagens que parecem menores, legais no Japão, mas não lá, enquanto imagens sexuais de crianças reais são crime em toda parte, inclusive no Japão. O TASlation não guarda cópias, mas os livros que você possui e tudo o que você salvar são de sua responsabilidade.

Na prática, os riscos são, nesta ordem: as leis do seu país sobre a posse de determinados conteúdos; a sua loja encerrar a sua conta por violação dos termos; e os direitos autorais, que só se tornam um risco real se você compartilhar o que traduziu.

As traduções vêm de um modelo de IA local e podem estar erradas, inclusive em nomes, números e no sentido de uma frase. Não confie nelas para nada importante. O modelo de tradução PLaMo, que o TASlation usa para a maioria dos idiomas, tem uma licença própria: se uma tradução feita com ele for publicada, ela deve indicar claramente que é um resultado do PLaMo (PLaMo Community License, artigo 5).

O TASlation é fornecido como está, sem garantia alguma, sob a licença MIT. Na medida em que a lei permitir, o autor não assume responsabilidade por qualquer dano ou consequência jurídica decorrente do seu uso, dos livros que você ler com ele ou deste aviso, que resume leis que mudam e não constitui aconselhamento jurídico. Ao continuar, você aceita isso.

O README descreve a situação jurídica em mais detalhes. Este aviso aparece sempre que o programa é iniciado, até você marcar a caixa abaixo. Para lê-lo de novo a qualquer momento, use Ajuda > Aviso legal... na janela.""",
    "fr": """TASlation affiche, sur cet ordinateur seulement, les pages du livre que vous avez ouvert dans votre propre lecteur, le texte japonais étant remplacé par une traduction automatique. Les images des pages ne sont conservées qu'en mémoire et jamais enregistrées ; rien n'est envoyé ailleurs qu'au programme de traduction de cet ordinateur ; seul le texte traduit est conservé.

Que vous ayez le droit de le faire dépend du pays où vous vivez. Au Japon, la loi sur le droit d'auteur autorise la copie et la traduction d'une œuvre pour votre propre usage privé (articles 30 et 47-6) ; beaucoup d'autres pays autorisent moins, ou rien de tel, et les conditions d'utilisation de votre librairie numérique peuvent interdire la capture d'écran. La partie consacrée à votre pays, ci-dessous, en dit plus. Lorsqu'elle indique qu'une traduction pour vous-même « constitue en droit une contrefaçon, de nature civile », cela signifie que le titulaire des droits pourrait demander à un tribunal civil de la faire cesser ou d'accorder des dommages-intérêts ; ce n'est pas une infraction pénale, donc ni la police ni le parquet n'interviennent, et personne n'a jamais été assigné en justice pour une traduction privée non partagée. La loi applicable est celle du lieu où vous lisez, quel que soit le pays du livre ou de la boutique. Vérifier la loi et les conditions qui s'appliquent à vous relève de votre responsabilité.

Ne publiez, ne partagez et ne diffusez jamais de pages traduites ni le texte traduit : c'est distribuer une œuvre dérivée, ce qui viole les droits de l'auteur dans tous les pays. C'est pourquoi TASlation n'exporte rien de lisible : la seule façon dont vos traductions en sortent est un fichier de sauvegarde chiffré avec votre phrase secrète, destiné à votre autre ordinateur ou à servir de copie pour vous-même, et à personne d'autre.

TASlation ne filtre ni ne censure ce que votre lecteur affiche : vous voyez le livre tel qu'il a été publié. Les mangas publiés au Japon peuvent contenir des représentations, y compris dessinées, dont la possession, l'importation ou la consultation est illégale là où vous êtes, même pour une lecture privée et même si elles sont légales au Japon. Dans plusieurs pays, la simple possession est une infraction grave ; l'exemple habituel est celui des dessins sexuels de personnages qui paraissent mineurs, légaux au Japon mais pas là-bas, tandis que les images sexuelles de mineurs réels sont réprimées partout, Japon compris. TASlation ne conserve aucune copie, mais les livres que vous possédez et tout ce que vous enregistrez relèvent de votre responsabilité.

En pratique, les risques se présentent dans cet ordre : les lois de votre pays sur la possession de certains contenus ; la fermeture de votre compte par votre boutique pour non-respect de ses conditions ; et le droit d'auteur, qui ne devient un risque réel que si vous partagez ce que vous avez traduit.

Les traductions proviennent d'un modèle d'IA local et peuvent être erronées, y compris dans les noms, les chiffres et le sens d'une réplique. Ne vous y fiez pas pour quoi que ce soit d'important. Le modèle de traduction PLaMo, que TASlation utilise pour la plupart des langues, a sa propre licence : si une traduction faite avec lui est un jour publiée, elle doit indiquer clairement qu'elle est produite par PLaMo (PLaMo Community License, article 5).

TASlation est fourni tel quel, sans aucune garantie, sous licence MIT. Dans la mesure permise par la loi, son auteur décline toute responsabilité pour tout dommage ou toute conséquence juridique découlant de son utilisation, des livres que vous lisez avec lui ou du présent avis, qui résume des lois susceptibles de changer et ne constitue pas un conseil juridique. En continuant, vous l'acceptez.

Le README décrit la situation juridique plus en détail. Cet avis s'affiche à chaque démarrage tant que la case ci-dessous n'est pas cochée . Pour le relire à tout moment, utilisez Aide > Avis juridique... dans la fenêtre.""",
    "de": """TASlation zeigt die Seiten des Buches, das Sie in Ihrem eigenen Viewer geöffnet haben, nur auf diesem Rechner an, wobei der japanische Text durch eine maschinelle Übersetzung ersetzt wird. Seitenbilder werden nur im Arbeitsspeicher gehalten und nie gespeichert; nichts wird irgendwohin gesendet außer an das Übersetzungsprogramm auf diesem Computer; nur der übersetzte Text wird behalten.

Ob Sie das dürfen, hängt davon ab, wo Sie leben. In Japan erlaubt das Urheberrechtsgesetz das Kopieren und Übersetzen eines Werks zum eigenen privaten Gebrauch (Artikel 30 und 47-6); viele andere Länder erlauben weniger oder nichts dergleichen, und die Nutzungsbedingungen Ihres E-Book-Shops können Bildschirmaufnahmen untersagen. Der Abschnitt zu Ihrem Land weiter unten enthält Näheres. Wo dort steht, eine Übersetzung für sich selbst sei „rechtlich eine Urheberrechtsverletzung, aber eine zivilrechtliche Angelegenheit“, heißt das: Der Rechteinhaber könnte vor einem Zivilgericht Unterlassung oder Schadensersatz verlangen; es ist keine Straftat, Polizei und Staatsanwaltschaft werden also nicht tätig, und niemand ist je wegen einer privaten, nicht geteilten Übersetzung verklagt worden. Es gilt das Recht des Ortes, an dem Sie lesen, gleich aus welchem Land das Buch oder der Shop stammt. Es liegt in Ihrer Verantwortung, das für Sie geltende Recht und die für Sie geltenden Bedingungen zu prüfen.

Veröffentlichen, teilen oder verbreiten Sie niemals übersetzte Seiten oder den übersetzten Text: Das ist die Verbreitung eines abgeleiteten Werks und verletzt überall die Rechte des Urhebers. Deshalb exportiert TASlation nichts Lesbares: Der einzige Weg, auf dem Ihre Übersetzungen es verlassen, ist eine mit Ihrer Passphrase verschlüsselte Sicherungsdatei, gedacht für Ihren anderen Rechner oder als Kopie für Sie selbst, nicht für andere.

TASlation filtert und zensiert nicht, was Ihr Viewer anzeigt: Sie sehen das Buch so, wie es veröffentlicht wurde. In Japan veröffentlichte Manga können Darstellungen enthalten, auch gezeichnete, deren Besitz, Einfuhr oder Betrachtung dort, wo Sie sind, verboten ist, selbst zum privaten Lesen und auch wenn sie in Japan legal sind. In mehreren Ländern ist der bloße Besitz eine schwere Straftat; das typische Beispiel sind sexuelle Zeichnungen von Figuren, die minderjährig aussehen, in Japan legal, dort aber nicht, während sexuelle Bilder realer Kinder überall eine Straftat sind, Japan eingeschlossen. TASlation bewahrt keine Kopien auf, aber für die Bücher, die Sie besitzen, und alles, was Sie speichern, sind Sie selbst verantwortlich.

In der Praxis ergeben sich die Risiken in dieser Reihenfolge: die Gesetze Ihres Landes zum Besitz bestimmter Inhalte; die Schließung Ihres Kontos durch Ihren Shop wegen Verstoßes gegen seine Bedingungen; und das Urheberrecht, das erst dann zu einem realen Risiko wird, wenn Sie das Übersetzte teilen.

Die Übersetzungen stammen von einem lokalen KI-Modell und können fehlerhaft sein, auch bei Namen, Zahlen und dem Sinn eines Satzes. Verlassen Sie sich bei nichts Wichtigem darauf. Das Übersetzungsmodell PLaMo, das TASlation für die meisten Sprachen verwendet, hat eine eigene Lizenz: Wird eine damit gemachte Übersetzung jemals veröffentlicht, muss sie klar angeben, dass sie eine Ausgabe von PLaMo ist (PLaMo Community License, Artikel 5).

TASlation wird unter der MIT-Lizenz so bereitgestellt, wie es ist, ohne jede Gewährleistung. Soweit gesetzlich zulässig, übernimmt der Autor keine Haftung für Schäden oder rechtliche Folgen, die aus der Nutzung, aus den damit gelesenen Büchern oder aus diesem Hinweis entstehen, der sich ändernde Gesetze zusammenfasst und keine Rechtsberatung ist. Indem Sie fortfahren, akzeptieren Sie dies.

Die README beschreibt die rechtliche Lage genauer. Dieser Hinweis erscheint bei jedem Start, bis Sie das Kästchen unten ankreuzen. Um ihn jederzeit erneut zu lesen, wählen Sie im Fenster Hilfe > Rechtlicher Hinweis...""",
    "it": """TASlation mostra, solo su questo computer, le pagine del libro che hai aperto nel tuo lettore, con il testo giapponese sostituito da una traduzione automatica. Le immagini delle pagine restano solo in memoria e non vengono mai salvate; nulla viene inviato altrove se non al programma di traduzione di questo computer; viene conservato solo il testo tradotto.

Se puoi farlo dipende dal paese in cui vivi. In Giappone la legge sul diritto d'autore permette di copiare e tradurre un'opera per il tuo uso privato (articoli 30 e 47-6); molti altri paesi permettono meno o nulla del genere, e le condizioni d'uso della tua libreria digitale possono vietare la cattura dello schermo. La parte dedicata al tuo paese, qui sotto, fornisce più dettagli. Dove vi si legge che una traduzione per sé "viola la legge, come questione civile", significa che il titolare dei diritti potrebbe chiedere a un giudice civile di farla cessare o di concedere un risarcimento; non è un reato, quindi né la polizia né la procura intervengono, e nessuno è mai stato citato in giudizio per una traduzione privata non condivisa. La legge che si applica è quella del luogo in cui leggi, qualunque sia il paese del libro o del negozio. Verificare la legge e le condizioni che si applicano a te è tua responsabilità.

Non pubblicare, condividere o diffondere mai pagine tradotte né il testo tradotto: equivale a distribuire un'opera derivata e viola i diritti dell'autore in qualsiasi paese. Per questo TASlation non esporta nulla di leggibile: l'unico modo in cui le tue traduzioni ne escono è un file di backup cifrato con la tua passphrase, pensato per il tuo altro computer o come copia per te, non per altri.

TASlation non filtra né censura ciò che il tuo lettore mostra: vedi il libro così come è stato pubblicato. I manga pubblicati in Giappone possono contenere rappresentazioni, anche disegnate, che è illegale possedere, importare o guardare dove ti trovi, anche per lettura privata e anche se sono legali in Giappone. In diversi paesi il semplice possesso è un reato grave; l'esempio tipico sono i disegni sessuali di personaggi che sembrano minorenni, legali in Giappone ma non lì, mentre le immagini sessuali di minori reali sono reato ovunque, Giappone compreso. TASlation non conserva copie, ma i libri che possiedi e tutto ciò che salvi sono sotto la tua responsabilità.

In pratica i rischi si presentano in quest'ordine: le leggi del tuo paese sul possesso di certi contenuti; la chiusura del tuo account da parte del negozio per violazione delle condizioni; e il diritto d'autore, che diventa un rischio concreto solo se condividi ciò che hai tradotto.

Le traduzioni provengono da un modello di IA locale e possono contenere errori, anche nei nomi, nei numeri e nel senso di una battuta. Non farci affidamento per nulla di importante. Il modello di traduzione PLaMo, che TASlation usa per la maggior parte delle lingue, ha una licenza propria: se una traduzione fatta con esso venisse pubblicata, dovrebbe indicare chiaramente che è un risultato di PLaMo (PLaMo Community License, articolo 5).

TASlation è fornito così com'è, senza alcuna garanzia, con licenza MIT. Nei limiti consentiti dalla legge, l'autore non risponde di alcun danno o conseguenza legale derivante dal suo uso, dai libri che leggi con esso o da questo avviso, che riassume leggi soggette a cambiamenti e non è una consulenza legale. Proseguendo accetti tutto ciò.

Il README descrive la situazione giuridica più in dettaglio. Questo avviso compare a ogni avvio finché non spunti la casella qui sotto. Per rileggerlo in qualsiasi momento, usa Aiuto > Avviso legale... nella finestra.""",
    "nl": """TASlation toont, alleen op deze computer, de pagina's van het boek dat u in uw eigen viewer hebt geopend, waarbij de Japanse tekst is vervangen door een machinevertaling. Pagina-afbeeldingen blijven alleen in het geheugen en worden nooit opgeslagen; er wordt niets verstuurd behalve naar het vertaalprogramma op deze computer; alleen de vertaalde tekst wordt bewaard.

Of u dit mag, hangt ervan af waar u woont. In Japan staat de Auteurswet het kopiëren en vertalen van een werk voor uw eigen privégebruik toe (artikelen 30 en 47-6); veel andere landen staan minder of niets dergelijks toe, en de gebruiksvoorwaarden van uw e-boekwinkel kunnen schermopnamen verbieden. In het deel over uw land hieronder leest u meer. Waar daar staat dat een vertaling voor uzelf “juridisch een inbreuk is, maar een civielrechtelijke kwestie”, betekent dat: de rechthebbende zou een civiele rechter om een verbod of schadevergoeding kunnen vragen; het is geen strafbaar feit, dus komen politie en openbaar ministerie er niet aan te pas, en niemand is ooit gedagvaard wegens een privévertaling die niet is gedeeld. Het recht dat geldt, is dat van de plaats waar u leest, uit welk land het boek of de winkel ook komt. Het is uw verantwoordelijkheid om de wet en de voorwaarden die op u van toepassing zijn, na te gaan.

Plaats, deel of publiceer nooit vertaalde pagina's of de vertaalde tekst: dat is het verspreiden van een afgeleid werk en schendt overal de rechten van de auteur. Daarom exporteert TASlation niets leesbaars: de enige weg waarlangs uw vertalingen het verlaten, is een met uw wachtwoordzin versleuteld back-upbestand, bedoeld voor uw andere computer of als kopie voor uzelf, niet voor anderen.

TASlation filtert of censureert niet wat uw viewer toont: u ziet het boek zoals het is uitgegeven. In Japan uitgegeven manga kunnen afbeeldingen bevatten, ook getekende, waarvan het bezit, de invoer of het bekijken verboden is waar u bent, zelfs als u ze alleen voor uzelf leest en zelfs al zijn ze in Japan legaal. In meerdere landen is het enkele bezit een ernstig misdrijf; het typische voorbeeld zijn seksuele tekeningen van personages die minderjarig lijken, in Japan legaal, maar daar niet, terwijl seksuele beelden van echte kinderen overal een misdrijf zijn, Japan inbegrepen. TASlation bewaart geen kopieën, maar voor de boeken die u bezit en alles wat u opslaat, bent u zelf verantwoordelijk.

In de praktijk zijn de risico's, in deze volgorde: de wetten van uw land over het bezit van bepaalde inhoud; het sluiten van uw account door uw winkel wegens schending van de voorwaarden; en het auteursrecht, dat pas een reëel risico wordt als u deelt wat u hebt vertaald.

De vertalingen komen van een lokaal AI-model en kunnen fouten bevatten, ook in namen, getallen en de betekenis van een zin. Vertrouw er niet op voor iets dat ertoe doet. Het vertaalmodel PLaMo, dat TASlation voor de meeste talen gebruikt, heeft een eigen licentie: wordt een vertaling die ermee is gemaakt ooit gepubliceerd, dan moet die duidelijk vermelden dat het uitvoer van PLaMo is (PLaMo Community License, artikel 5).

TASlation wordt geleverd zoals het is, zonder enige garantie, onder de MIT-licentie. Voor zover de wet het toestaat, aanvaardt de auteur geen aansprakelijkheid voor schade of juridische gevolgen die voortvloeien uit het gebruik, uit de boeken die u ermee leest of uit deze kennisgeving, die veranderende wetten samenvat en geen juridisch advies is. Door verder te gaan aanvaardt u dit.

De README beschrijft de juridische situatie uitvoeriger. Deze kennisgeving verschijnt bij elke start totdat u het vakje hieronder aanvinkt. Om hem op elk moment opnieuw te lezen, gebruikt u Help > Juridische kennisgeving... in het venster.""",
    "pl": """TASlation wyświetla tylko na tym komputerze strony książki otwartej w Twoim własnym czytniku, zastępując japoński tekst tłumaczeniem maszynowym. Obrazy stron pozostają wyłącznie w pamięci i nigdy nie są zapisywane; nic nie jest wysyłane nigdzie indziej niż do programu tłumaczącego na tym komputerze; przechowywany jest tylko przetłumaczony tekst.

To, czy wolno Ci to robić, zależy od kraju, w którym mieszkasz. W Japonii ustawa o prawie autorskim pozwala kopiować i tłumaczyć utwór na własny użytek prywatny (art. 30 i 47-6); wiele innych krajów pozwala na mniej albo nie pozwala na nic podobnego, a regulamin Twojej księgarni internetowej może zabraniać przechwytywania ekranu. Więcej informacji zawiera poniższa część poświęcona Twojemu krajowi. Gdy jest tam mowa, że tłumaczenie na własny użytek „stanowi w świetle prawa naruszenie o charakterze cywilnoprawnym”, znaczy to, że uprawniony mógłby żądać przed sądem cywilnym zaniechania naruszenia lub odszkodowania; nie jest to przestępstwo, więc nie zajmują się tym ani policja, ani prokuratura, a nikt nigdy nie został pozwany za prywatne, nieudostępnione tłumaczenie. Stosuje się prawo miejsca, w którym czytasz, niezależnie od tego, z jakiego kraju pochodzi książka lub sklep. Sprawdzenie prawa i regulaminów, które Cię obowiązują, należy do Ciebie.

Nigdy nie publikuj, nie udostępniaj ani nie rozpowszechniaj przetłumaczonych stron ani przetłumaczonego tekstu: to rozpowszechnianie utworu zależnego, które narusza prawa autora w każdym kraju. Dlatego TASlation nie eksportuje niczego czytelnego: Twoje tłumaczenia mogą go opuścić jedynie w postaci pliku kopii zapasowej zaszyfrowanego Twoim hasłem, przeznaczonego na Twój drugi komputer albo na kopię dla Ciebie, nie dla nikogo innego.

TASlation nie filtruje ani nie cenzuruje tego, co pokazuje Twój czytnik: widzisz książkę taką, jaką wydano. Manga wydana w Japonii może zawierać przedstawienia, także rysunkowe, których posiadanie, przywóz lub oglądanie jest nielegalne tam, gdzie jesteś, nawet na potrzeby prywatnej lektury i nawet jeśli w Japonii są legalne. W kilku krajach samo posiadanie jest poważnym przestępstwem; typowym przykładem są seksualne rysunki postaci wyglądających na małoletnie, legalne w Japonii, a tam nie, podczas gdy seksualne obrazy rzeczywistych dzieci są przestępstwem wszędzie, także w Japonii. TASlation nie zachowuje kopii, ale to Ty odpowiadasz za posiadane książki i wszystko, co zapiszesz.

W praktyce ryzyka układają się w następującej kolejności: prawo Twojego kraju dotyczące posiadania określonych treści; zamknięcie konta przez sklep za złamanie regulaminu; i prawo autorskie, które staje się realnym problemem dopiero wtedy, gdy udostępnisz swoje tłumaczenia.

Tłumaczenia pochodzą z lokalnego modelu AI i mogą zawierać błędy, także w imionach, liczbach i sensie wypowiedzi. Nie polegaj na nich w niczym istotnym. Model tłumaczenia PLaMo, którego TASlation używa dla większości języków, ma własną licencję: jeśli wykonane nim tłumaczenie zostanie kiedykolwiek opublikowane, musi wyraźnie informować, że jest wynikiem działania PLaMo (PLaMo Community License, artykuł 5).

TASlation jest dostarczany w stanie, w jakim się znajduje, bez jakiejkolwiek gwarancji, na licencji MIT. W zakresie dozwolonym przez prawo jego autor nie ponosi odpowiedzialności za żadne szkody ani skutki prawne wynikające z korzystania z programu, z książek, które za jego pomocą czytasz, ani z tej informacji, która streszcza zmieniające się przepisy i nie jest poradą prawną. Kontynuując, akceptujesz to.

Sytuację prawną dokładniej opisuje plik README. Ta informacja pojawia się przy każdym uruchomieniu, dopóki nie zaznaczysz pola poniżej. Aby przeczytać ją ponownie w dowolnej chwili, użyj Pomoc > Informacja prawna... w oknie.""",
    "ru": """TASlation показывает только на этом компьютере страницы книги, открытой в вашей собственной программе просмотра, заменяя японский текст машинным переводом. Изображения страниц хранятся только в памяти и никогда не сохраняются; ничего никуда не отправляется, кроме как в программу перевода на этом компьютере; сохраняется только переведённый текст.

Разрешено ли вам это делать, зависит от того, где вы живёте. В Японии Закон об авторском праве разрешает копировать и переводить произведение для личного использования (статьи 30 и 47-6); во многих других странах такое разрешено в меньшем объёме или не разрешено вовсе, а условия использования вашего книжного магазина могут запрещать захват экрана. Подробнее — в разделе о вашей стране ниже. Там, где сказано, что перевод для себя «юридически является гражданско-правовым нарушением», это означает: правообладатель мог бы обратиться в гражданский суд с требованием прекратить нарушение или возместить убытки; это не преступление, поэтому ни полиция, ни прокуратура этим не занимаются, и ещё никому не предъявляли иск за частный перевод, которым ни с кем не делились. Применяется право места, где вы читаете, из какой бы страны ни были книга или магазин. Проверить, какие законы и условия на вас распространяются, — ваша обязанность.

Никогда не публикуйте, не передавайте и не распространяйте переведённые страницы или переведённый текст: это распространение производного произведения, нарушающее права автора в любой стране. Поэтому TASlation не экспортирует ничего в читаемом виде: ваши переводы могут покинуть его только в виде файла резервной копии, зашифрованного вашей парольной фразой и предназначенного для другого вашего компьютера или в качестве копии для вас самих, а не для кого-то ещё.

TASlation не фильтрует и не цензурирует то, что показывает ваша программа просмотра: вы видите книгу такой, какой она была издана. Манга, изданная в Японии, может содержать изображения, в том числе рисованные, хранение, ввоз или просмотр которых там, где вы находитесь, незаконны — даже для личного чтения и даже если в Японии они законны. В ряде стран само хранение является тяжким преступлением; обычный пример — сексуальные рисунки персонажей, выглядящих несовершеннолетними: в Японии они законны, а там нет, тогда как сексуальные изображения реальных детей — преступление везде, включая Японию. TASlation не хранит копий, но за книги, которыми вы владеете, и за всё, что вы сохраняете, отвечаете вы.

На практике риски располагаются в следующем порядке: законы вашей страны о хранении определённых материалов; закрытие вашего аккаунта магазином за нарушение его условий; и авторское право, которое становится реальной проблемой лишь тогда, когда вы делитесь тем, что перевели.

Переводы делает локальная ИИ-модель, и они могут содержать ошибки, в том числе в именах, числах и смысле реплики. Не полагайтесь на них ни в чём важном. У модели перевода PLaMo, которую TASlation использует для большинства языков, своя лицензия: если сделанный с её помощью перевод когда-либо публикуется, в нём должно быть ясно указано, что это результат работы PLaMo (PLaMo Community License, статья 5).

TASlation предоставляется «как есть», без каких-либо гарантий, по лицензии MIT. В той мере, в какой это допускает закон, его автор не несёт ответственности за любой ущерб или правовые последствия, возникшие в связи с его использованием, с книгами, которые вы с его помощью читаете, или с этим уведомлением, которое кратко излагает меняющиеся законы и не является юридической консультацией. Продолжая, вы соглашаетесь с этим.

Правовое положение подробнее описано в README. Это уведомление показывается при каждом запуске, пока вы не отметите флажок ниже. Чтобы прочитать его снова в любое время, выберите в окне Справка > Правовое уведомление...""",
    "tr": """TASlation, kendi görüntüleyicinizde açtığınız kitabın sayfalarını, Japonca metnin yerine makine çevirisi koyarak yalnızca bu bilgisayarda gösterir. Sayfa görüntüleri yalnızca bellekte tutulur ve hiçbir zaman kaydedilmez; bu bilgisayardaki çeviri programı dışında hiçbir yere hiçbir şey gönderilmez; yalnızca çevrilmiş metin saklanır.

Bunu yapıp yapamayacağınız, yaşadığınız ülkeye bağlıdır. Japonya'da Telif Hakkı Kanunu, bir eserin kendi özel kullanımınız için kopyalanmasına ve çevrilmesine izin verir (30. ve 47-6. maddeler); diğer birçok ülke daha azına izin verir ya da buna benzer hiçbir şeye izin vermez ve e-kitap mağazanızın kullanım koşulları ekran yakalamayı yasaklıyor olabilir. Ülkenize ilişkin aşağıdaki bölüm daha ayrıntılı bilgi verir. Orada kendiniz için yaptığınız bir çeviri hakkında "kanunen ihlaldir, ancak bir özel hukuk meselesidir" deniyorsa, bu şu anlama gelir: hak sahibi, bir hukuk mahkemesinden ihlalin durdurulmasını ya da tazminata hükmedilmesini isteyebilir; bu bir suç değildir, dolayısıyla polis de savcılık da devreye girmez ve bugüne kadar hiç kimse paylaşmadığı özel bir çeviri yüzünden dava edilmemiştir. Uygulanan hukuk, kitabın ya da mağazanın ülkesi ne olursa olsun, okuduğunuz yerin hukukudur. Size uygulanan hukuku ve koşulları kontrol etmek sizin sorumluluğunuzdadır.

Çevrilmiş sayfaları ya da çevrilmiş metni asla internete koymayın, paylaşmayın ya da yayımlamayın: bu, türev bir eserin dağıtımıdır ve her ülkede yazarın haklarını ihlal eder. Bu yüzden TASlation okunabilir hiçbir şeyi dışa aktarmaz: çevirilerinizin ondan çıkmasının tek yolu, kendi parolanızla şifrelenmiş bir yedek dosyasıdır; bu dosya diğer bilgisayarınız için ya da kendinize bir kopya olarak düşünülmüştür, başkası için değil.

TASlation, görüntüleyicinizin gösterdiği içeriği filtrelemez ve sansürlemez: kitabı yayımlandığı hâliyle görürsünüz. Japonya'da yayımlanan mangalar, bulunduğunuz yerde bulundurulması, ithali ya da görüntülenmesi yasa dışı olan tasvirler (çizim olanlar da dâhil) içerebilir; bu, özel okuma için olsa ve söz konusu tasvirler Japonya'da yasal olsa bile böyledir. Çeşitli ülkelerde salt bulundurma bile ağır bir suçtur; en sık verilen örnek, reşit olmayan gibi görünen karakterlerin cinsel çizimleridir: bunlar Japonya'da yasaldır, o ülkelerde değil; gerçek çocukların cinsel görüntüleri ise Japonya dâhil her yerde suçtur. TASlation kopya saklamaz, ancak sahip olduğunuz kitaplardan ve kaydettiğiniz her şeyden siz sorumlusunuz.

Uygulamada riskler şu sıradadır: ülkenizin belirli içerikleri bulundurmaya ilişkin yasaları; koşullarını ihlal ettiğiniz için mağazanızın hesabınızı kapatması; ve ancak çevirdiklerinizi paylaştığınızda gerçek bir sorun hâline gelen telif hakkı.

Çeviriler yerel bir yapay zekâ modelinden gelir ve adlar, sayılar ile bir cümlenin anlamı da dâhil olmak üzere yanlış olabilir. Önemli hiçbir konuda onlara güvenmeyin. TASlation'ın çoğu dil için kullandığı çeviri modeli PLaMo'nun kendi lisansı vardır: onunla yapılan bir çeviri bir gün yayımlanırsa, PLaMo'nun çıktısı olduğunu açıkça belirtmelidir (PLaMo Community License, madde 5).

TASlation, MIT lisansı altında, olduğu gibi ve hiçbir garanti olmaksızın sunulur. Yasanın izin verdiği ölçüde yazar, kullanımından, onunla okuduğunuz kitaplardan ya da değişen yasaları özetleyen ve hukuki tavsiye olmayan bu bildirimden doğan hiçbir zarar veya hukuki sonuçtan sorumlu değildir. Devam ederek bunu kabul etmiş olursunuz.

README dosyası hukuki durumu daha ayrıntılı açıklar. Bu bildirim, aşağıdaki kutuyu işaretleyene kadar her açılışta gösterilir. İstediğiniz zaman yeniden okumak için pencerede Yardım > Yasal bildirim... seçeneğini kullanın.""",
    "id": """TASlation menampilkan, hanya di komputer ini, halaman buku yang Anda buka di penampil Anda sendiri, dengan teks berbahasa Jepang digantikan oleh terjemahan mesin. Gambar halaman hanya ada di memori dan tidak pernah disimpan ke disk; tidak ada yang dikirim ke mana pun selain ke program penerjemah di komputer ini; hanya teks terjemahan yang disimpan.

Boleh tidaknya Anda melakukan ini bergantung pada negara tempat Anda tinggal. Di Jepang, Undang-Undang Hak Cipta mengizinkan penyalinan dan penerjemahan sebuah karya untuk penggunaan pribadi Anda (Pasal 30 dan 47-6); banyak negara lain mengizinkan lebih sedikit atau sama sekali tidak mengizinkan hal semacam itu, dan ketentuan penggunaan toko buku digital Anda mungkin melarang tangkapan layar. Bagian tentang negara Anda di bawah menjelaskan lebih lanjut. Jika di sana tertulis bahwa terjemahan untuk diri sendiri "secara hukum merupakan pelanggaran yang bersifat perdata", artinya pemegang hak dapat meminta pengadilan perdata menghentikannya atau menetapkan ganti rugi; ini bukan tindak pidana, sehingga baik polisi maupun jaksa tidak terlibat, dan belum pernah ada orang yang digugat karena terjemahan pribadi yang tidak dibagikan. Hukum yang berlaku adalah hukum tempat Anda membaca, apa pun negara asal buku atau tokonya. Memeriksa hukum dan ketentuan yang berlaku bagi Anda adalah tanggung jawab Anda.

Jangan pernah mengunggah, membagikan, atau menerbitkan halaman terjemahan maupun teks terjemahannya: itu adalah penyebaran karya turunan dan melanggar hak pencipta di negara mana pun. Karena itu, TASlation tidak mengekspor apa pun yang dapat dibaca: satu-satunya jalan keluar bagi terjemahan Anda adalah berkas cadangan yang dienkripsi dengan frasa sandi Anda dan dimaksudkan untuk komputer Anda yang lain atau sebagai salinan untuk diri sendiri, bukan untuk orang lain.

TASlation tidak menyaring maupun menyensor apa yang tampil di penampil Anda: Anda melihat buku sebagaimana diterbitkan. Manga yang terbit di Jepang dapat memuat penggambaran, termasuk yang berupa gambar ilustrasi, yang ilegal untuk dimiliki, diimpor, atau dilihat di tempat Anda berada, bahkan untuk dibaca secara pribadi dan meskipun legal di Jepang. Di sejumlah negara, sekadar memiliki sudah merupakan kejahatan serius; contoh yang lazim adalah gambar ilustrasi seksual tokoh yang tampak di bawah umur, yang legal di Jepang tetapi tidak di sana, sedangkan gambar seksual anak sungguhan adalah kejahatan di mana pun, termasuk di Jepang. TASlation tidak menyimpan salinan, tetapi buku yang Anda miliki dan apa pun yang Anda simpan adalah tanggung jawab Anda.

Dalam praktiknya, urutan risikonya adalah sebagai berikut: hukum negara Anda tentang kepemilikan konten tertentu; toko Anda menutup akun Anda karena Anda melanggar ketentuannya; dan hak cipta, yang baru menjadi masalah nyata jika Anda membagikan apa yang Anda terjemahkan.

Terjemahan dihasilkan oleh model AI lokal dan bisa salah, termasuk nama, angka, dan makna sebuah kalimat. Jangan mengandalkannya untuk hal yang penting. Model terjemahan PLaMo, yang dipakai TASlation untuk sebagian besar bahasa, memiliki lisensi sendiri: jika terjemahan yang dibuat dengannya dipublikasikan, terjemahan itu harus menyebutkan dengan jelas bahwa itu hasil PLaMo (PLaMo Community License, pasal 5).

TASlation disediakan apa adanya, tanpa jaminan apa pun, di bawah lisensi MIT. Sejauh diizinkan oleh hukum, pembuatnya tidak bertanggung jawab atas kerugian atau akibat hukum apa pun yang timbul dari penggunaannya, dari buku yang Anda baca dengannya, atau dari pemberitahuan ini, yang merangkum hukum yang dapat berubah dan bukan merupakan nasihat hukum. Dengan melanjutkan, Anda menerima hal ini.

README menjelaskan kedudukan hukumnya secara lebih rinci. Pemberitahuan ini muncul setiap kali program dimulai sampai Anda mencentang kotak di bawah. Untuk membacanya lagi kapan saja, gunakan Bantuan > Pemberitahuan hukum... di jendela.""",
    "vi": """TASlation hiển thị, chỉ trên máy tính này, các trang của cuốn sách bạn đã mở trong trình xem của chính bạn, với phần chữ tiếng Nhật được thay bằng bản dịch máy. Ảnh trang chỉ được giữ trong bộ nhớ và không bao giờ được lưu; không có gì được gửi đi đâu ngoài chương trình dịch trên máy tính này; chỉ văn bản đã dịch được giữ lại.

Việc bạn có được phép làm vậy hay không tùy thuộc vào nơi bạn sống. Ở Nhật Bản, Luật Bản quyền cho phép sao chép và dịch một tác phẩm để sử dụng riêng (Điều 30 và 47-6); nhiều nước khác cho phép ít hơn hoặc hoàn toàn không cho phép điều tương tự, và điều khoản sử dụng của cửa hàng sách điện tử của bạn có thể cấm chụp màn hình. Phần về quốc gia của bạn ở bên dưới nói rõ hơn. Khi ở đó ghi rằng bản dịch cho riêng mình "về mặt pháp luật là xâm phạm, nhưng là vấn đề dân sự", điều đó có nghĩa là chủ sở hữu quyền có thể yêu cầu tòa án dân sự buộc chấm dứt việc đó hoặc bồi thường thiệt hại; đây không phải là tội phạm hình sự, nên công an và viện kiểm sát không can dự, và chưa từng có ai bị kiện vì một bản dịch riêng tư không chia sẻ. Luật được áp dụng là luật của nơi bạn đọc, bất kể cuốn sách hay cửa hàng thuộc nước nào. Kiểm tra luật và các điều khoản áp dụng cho bạn là trách nhiệm của bạn.

Đừng bao giờ đăng, chia sẻ hay công bố các trang đã dịch hoặc văn bản đã dịch: đó là phân phối tác phẩm phái sinh và xâm phạm quyền của tác giả ở mọi quốc gia. Vì vậy TASlation không xuất ra bất cứ thứ gì đọc được: cách duy nhất để bản dịch của bạn rời khỏi nó là một tệp sao lưu được mã hóa bằng cụm mật khẩu của bạn, dành cho máy tính khác của bạn hoặc làm bản sao cho chính bạn, không dành cho ai khác.

TASlation không lọc hay kiểm duyệt những gì trình xem của bạn hiển thị: bạn thấy cuốn sách đúng như khi được xuất bản. Manga xuất bản ở Nhật Bản có thể chứa những hình ảnh, kể cả hình vẽ, mà việc tàng trữ, nhập khẩu hay xem là bất hợp pháp ở nơi bạn đang ở, dù chỉ để đọc riêng và dù chúng hợp pháp ở Nhật Bản. Ở một số nước, chỉ riêng việc tàng trữ đã là tội nghiêm trọng; ví dụ thường gặp là hình vẽ tình dục về nhân vật trông như trẻ vị thành niên, hợp pháp ở Nhật Bản nhưng không hợp pháp ở đó, trong khi hình ảnh tình dục về trẻ em thật là tội phạm ở mọi nơi, kể cả Nhật Bản. TASlation không giữ bản sao nào, nhưng những cuốn sách bạn sở hữu và bất cứ thứ gì bạn lưu lại đều thuộc trách nhiệm của bạn.

Trên thực tế, các rủi ro xếp theo thứ tự sau: luật của nước bạn về việc tàng trữ một số nội dung; cửa hàng đóng tài khoản của bạn vì vi phạm điều khoản; và bản quyền, vốn chỉ trở thành vấn đề thật sự khi bạn chia sẻ những gì mình đã dịch.

Bản dịch do một mô hình AI cục bộ tạo ra và có thể sai, kể cả về tên, con số và ý nghĩa của một câu thoại. Đừng dựa vào chúng cho bất cứ điều gì quan trọng. Mô hình dịch PLaMo, mà TASlation dùng cho hầu hết các ngôn ngữ, có giấy phép riêng: nếu một bản dịch tạo bằng nó được công bố, bản dịch đó phải ghi rõ là kết quả của PLaMo (PLaMo Community License, điều 5).

TASlation được cung cấp nguyên trạng, không có bất kỳ bảo đảm nào, theo giấy phép MIT. Trong phạm vi pháp luật cho phép, tác giả không chịu trách nhiệm về bất kỳ thiệt hại hay hậu quả pháp lý nào phát sinh từ việc sử dụng nó, từ những cuốn sách bạn đọc bằng nó, hoặc từ thông báo này, vốn chỉ tóm tắt các luật có thể thay đổi và không phải là tư vấn pháp lý. Bằng việc tiếp tục, bạn chấp nhận điều này.

README mô tả tình hình pháp lý chi tiết hơn. Thông báo này xuất hiện mỗi lần khởi động cho đến khi bạn đánh dấu ô bên dưới. Để đọc lại bất cứ lúc nào, dùng Trợ giúp > Thông báo pháp lý... trong cửa sổ.""",
    "zh": """TASlation 只在这台电脑上显示您在自己的阅读器中打开的图书页面，并把日文文字替换为机器翻译。页面图像只保存在内存中，绝不会写入磁盘；除了本机上的翻译程序，不会向任何地方发送任何数据；只保留译文。

您是否可以这样做，取决于您所在的国家或地区。在日本，《著作权法》允许为私人使用而复制和翻译作品（第 30 条和第 47 条之 6）；许多其他国家允许的范围更窄，或者根本不允许，而且您所用电子书店的使用条款可能禁止屏幕截取。下方关于您所在国家或地区的部分有更详细的说明。其中写到为自己所作的翻译“在法律上构成侵权，属民事事宜”，意思是权利人可以请求民事法院责令停止或判令赔偿；这不是犯罪，因此警察和检察机关都不会介入，也从未有人因为未分享的私人翻译而被提起诉讼。适用的是您阅读所在地的法律，与图书或书店属于哪个国家无关。核实适用于您的法律和条款是您自己的责任。

切勿发布、分享或公开翻译后的页面或译文：这属于传播演绎作品，在任何国家都侵犯作者的权利。因此 TASlation 不导出任何可读内容：您的译文离开它的唯一途径，是用您的口令加密的备份文件，供您的另一台电脑使用或作为自己的副本，不供任何他人使用。

TASlation 不会对阅读器显示的内容做任何过滤或审查，您看到的是出版时的原样。在日本出版的漫画可能包含在您所在地持有、进口或观看即属违法的内容（包括绘画作品），即使只是私下阅读，即使这些内容在日本合法。在一些国家，仅仅持有就是重罪；最常见的例子是外表像未成年人的角色的色情绘画，在日本合法而在那些国家不合法；至于真实儿童的性图像，在包括日本在内的任何国家都是犯罪。TASlation 不保留任何副本，但您拥有的图书以及您自行保存的任何内容，由您自己负责。

实际的风险按以下顺序排列：您所在国家关于持有特定内容的法律；书店因您违反条款而关闭账户；以及著作权，只有在您分享所译内容时才会成为现实问题。

译文由本机的 AI 模型生成，可能出错，包括人名、数字和一句话的意思。请勿在任何重要事项上依赖译文。TASlation 在大多数语言中使用的翻译模型 PLaMo 有其自身的许可：用它生成的译文如被公开，必须清楚注明是 PLaMo 的输出（PLaMo Community License 第 5 条）。

TASlation 依 MIT 许可证按现状提供，不附带任何保证。在法律允许的范围内，作者对因使用本软件、因您用它阅读的图书或因本提示而产生的任何损害或法律后果不承担责任；本提示只是对可能变化的法律的概括，不构成法律意见。继续使用即表示您接受这一点。

README 中有更详细的法律说明。在您勾选下方的复选框之前，每次启动都会显示本提示。如需随时再次查看，请在窗口中使用「帮助 > 法律提示...」。""",
    "zh-tw": """TASlation 只在這台電腦上顯示您在自己的閱讀器中開啟的書籍頁面，並將日文文字換成機器翻譯。頁面影像只保存在記憶體中，絕不會寫入磁碟；除了本機上的翻譯程式，不會向任何地方傳送任何資料；只保留譯文。

您是否可以這樣做，取決於您所在的國家或地區。在日本，《著作權法》允許為私人使用而重製及翻譯著作（第 30 條及第 47 條之 6）；許多其他國家允許的範圍較窄，或者完全不允許，而且您所用電子書店的使用條款可能禁止螢幕擷取。下方關於您所在國家或地區的部分有更詳細的說明。其中寫到為自己所作的翻譯「在法律上構成侵害，屬民事問題」，意思是權利人可以請求民事法院命令停止或判決賠償；這不是犯罪，因此警察和檢察機關都不會介入，也從未有人因為未分享的私人翻譯而被告。適用的是您閱讀所在地的法律，與書籍或書店屬於哪個國家無關。確認適用於您的法律與條款是您自己的責任。

切勿發布、分享或公開翻譯後的頁面或譯文：這屬於散布衍生著作，在任何國家都侵害著作人的權利。因此 TASlation 不匯出任何可讀內容：您的譯文離開它的唯一途徑，是以您的通關密語加密的備份檔案，供您的另一台電腦使用或作為自己的副本，不供任何他人使用。

TASlation 不會對閱讀器顯示的內容做任何過濾或審查，您看到的是出版時的原樣。在日本出版的漫畫可能包含在您所在地持有、輸入或觀看即屬違法的內容（包括繪畫作品），即使只是私下閱讀，即使這些內容在日本合法。在一些國家，僅僅持有就是重罪；最常見的例子是外表像未成年人的角色的色情繪畫，在日本合法而在那些國家不合法；至於真實兒童的性影像，在包括日本在內的任何國家都是犯罪。TASlation 不保留任何副本，但您擁有的書籍以及您自行儲存的任何內容，由您自己負責。

實際的風險依以下順序排列：您所在國家關於持有特定內容的法律；書店因您違反條款而關閉帳戶；以及著作權，只有在您分享所譯內容時才會成為現實問題。

譯文由本機的 AI 模型產生，可能出錯，包括人名、數字和一句話的意思。請勿在任何重要事項上依賴譯文。TASlation 在大多數語言中使用的翻譯模型 PLaMo 有其自身的授權：用它產生的譯文如被公開，必須清楚註明是 PLaMo 的輸出（PLaMo Community License 第 5 條）。

TASlation 依 MIT 授權按現狀提供，不附帶任何保證。在法律允許的範圍內，作者對因使用本軟體、因您用它閱讀的書籍或因本提示而產生的任何損害或法律後果不負任何責任；本提示只是對可能變動的法律的概括，不構成法律意見。繼續使用即表示您接受這一點。

README 中有更詳細的法律說明。在您勾選下方的核取方塊之前，每次啟動都會顯示本提示。如需隨時再次查看，請在視窗中使用「說明 > 法律提示...」。""",
    "ko": """TASlation는 사용자가 자신의 뷰어에서 연 책의 페이지를, 일본어 글자를 기계 번역으로 바꾸어 이 컴퓨터에서만 보여 줍니다. 페이지 이미지는 메모리에만 두며 저장하지 않습니다. 이 컴퓨터의 번역 프로그램 외에는 어디에도 아무것도 보내지 않으며, 번역문만 보관합니다.

이렇게 해도 되는지는 사는 나라에 따라 다릅니다. 일본에서는 저작권법이 개인의 사적 이용을 위한 복제와 번역을 허용합니다(제30조, 제47조의6). 다른 많은 나라에서는 허용 범위가 더 좁거나 전혀 허용되지 않으며, 이용 중인 전자책 서점의 이용 약관이 화면 캡처를 금지할 수도 있습니다. 아래의 국가별 항목에 자세히 적혀 있습니다. 거기에 자신을 위한 번역이 “법적으로는 침해에 해당하는 민사 문제”라고 적혀 있다면, 권리자가 민사 법원에 금지나 손해배상을 청구할 근거는 되지만 경찰이나 검찰이 움직이는 범죄는 아니라는 뜻입니다. 공유하지 않은 사적인 번역 때문에 소송을 당한 사람은 아직 없습니다. 적용되는 법은 책이나 서점이 어느 나라 것이든 상관없이 사용자가 읽고 있는 곳의 법입니다. 자신에게 적용되는 법과 약관을 확인하는 것은 사용자 본인의 책임입니다.

번역된 페이지나 번역문을 절대 게시·공유·공개하지 마십시오. 이는 2차적 저작물의 배포이며 어느 나라에서든 저작자의 권리를 침해합니다. 그래서 TASlation는 읽을 수 있는 형태로는 아무것도 내보내지 않습니다. 번역이 밖으로 나가는 유일한 길은 자신의 암호 문구로 암호화한 백업 파일이며, 자신의 다른 컴퓨터로 옮기거나 자신을 위한 사본으로 쓰기 위한 것이지 다른 사람을 위한 것이 아닙니다.

TASlation는 뷰어가 보여 주는 내용을 전혀 걸러 내거나 검열하지 않으며, 책을 출판된 그대로 보여 줍니다. 일본에서 출판된 만화에는, 일본에서는 합법이더라도 사용자가 있는 곳에서는 소지·반입·열람이 불법인 표현(그림 포함)이 들어 있을 수 있습니다. 개인적으로 읽기 위한 것이라도 마찬가지입니다. 여러 나라에서는 단순 소지만으로도 중범죄가 되며, 대표적인 예는 미성년자로 보이는 캐릭터의 성적인 그림입니다. 일본에서는 합법이지만 그런 나라에서는 불법인 반면, 실제 아동의 성적 이미지는 일본을 포함한 모든 나라에서 범죄입니다. TASlation는 사본을 남기지 않지만, 소유한 책과 직접 저장한 것에 대한 책임은 사용자 본인에게 있습니다.

실제 위험은 다음 순서입니다. 특정 내용의 소지를 처벌하는 거주국의 법, 약관 위반으로 인한 서점의 계정 정지, 그리고 저작권. 저작권은 번역한 것을 공유했을 때 비로소 현실적인 문제가 됩니다.

번역은 이 컴퓨터의 AI 모델이 만든 것으로, 이름·숫자·대사의 뜻을 포함해 틀릴 수 있습니다. 중요한 일의 근거로 삼지 마십시오. TASlation이 대부분의 언어에 사용하는 번역 모델 PLaMo에는 별도의 라이선스가 있습니다. 이 모델로 만든 번역을 공개하는 경우에는 PLaMo의 출력물임을 분명히 밝혀야 합니다(PLaMo Community License 제5조).

TASlation는 MIT 라이선스에 따라 있는 그대로, 어떠한 보증도 없이 제공됩니다. 법이 허용하는 범위에서 작성자는 이 소프트웨어의 사용, 이것으로 읽은 책, 또는 변할 수 있는 법을 요약한 것일 뿐 법률 자문이 아닌 이 안내로부터 생기는 어떠한 손해나 법적 결과에 대해서도 책임지지 않습니다. 계속 진행하면 이에 동의한 것으로 봅니다.

자세한 법적 설명은 README에 있습니다. 이 안내는 아래 확인란에 표시하기 전까지는 시작할 때마다 표시됩니다. 언제든 다시 보려면 창의 도움말 > 법적 안내... 메뉴를 사용하세요.""",
    "th": """TASlation แสดงหน้าหนังสือที่คุณเปิดในโปรแกรมอ่านของคุณเอง โดยแทนที่ตัวอักษรภาษาญี่ปุ่นด้วยคำแปลจากเครื่อง บนคอมพิวเตอร์เครื่องนี้เท่านั้น ภาพหน้าจะอยู่ในหน่วยความจำและไม่ถูกบันทึกเลย ไม่มีการส่งสิ่งใดไปที่ใดนอกจากโปรแกรมแปลบนคอมพิวเตอร์เครื่องนี้ และเก็บเฉพาะข้อความแปลเท่านั้น

คุณจะทำเช่นนี้ได้หรือไม่ขึ้นอยู่กับว่าคุณอาศัยอยู่ที่ไหน ในญี่ปุ่น พระราชบัญญัติลิขสิทธิ์อนุญาตให้ทำสำเนาและแปลงานเพื่อการใช้ส่วนตัวของคุณเอง (มาตรา 30 และ 47-6) ประเทศอื่นจำนวนมากอนุญาตน้อยกว่านั้นหรือไม่อนุญาตเลย และข้อกำหนดการใช้งานของร้านหนังสือของคุณอาจห้ามการจับภาพหน้าจอ ส่วนของประเทศคุณด้านล่างให้รายละเอียดเพิ่มเติม เมื่อส่วนนั้นระบุว่าคำแปลเพื่อตัวเอง “ถือเป็นการละเมิดตามกฎหมายในทางแพ่ง” หมายความว่าผู้ทรงสิทธิอาจขอให้ศาลแพ่งสั่งให้หยุดหรือให้ชดใช้ค่าเสียหาย ไม่ใช่อาชญากรรม จึงไม่มีตำรวจหรืออัยการเกี่ยวข้อง และยังไม่เคยมีใครถูกฟ้องเพราะคำแปลส่วนตัวที่ไม่ได้แบ่งปัน กฎหมายที่ใช้บังคับคือกฎหมายของสถานที่ที่คุณอ่าน ไม่ว่าหนังสือหรือร้านจะอยู่ในประเทศใด การตรวจสอบกฎหมายและข้อกำหนดที่ใช้กับคุณเป็นความรับผิดชอบของคุณ

ห้ามโพสต์ แบ่งปัน หรือเผยแพร่หน้าที่แปลแล้วหรือข้อความแปลเด็ดขาด การกระทำนั้นคือการเผยแพร่งานดัดแปลงและละเมิดสิทธิของผู้สร้างสรรค์ในทุกประเทศ TASlation จึงไม่ส่งออกสิ่งใดในรูปแบบที่อ่านได้ ทางเดียวที่คำแปลของคุณจะออกจากโปรแกรมได้ คือไฟล์สำรองที่เข้ารหัสด้วยวลีรหัสผ่านของคุณ ซึ่งมีไว้สำหรับคอมพิวเตอร์เครื่องอื่นของคุณเองหรือเป็นสำเนาสำหรับตัวคุณ ไม่ใช่สำหรับผู้อื่น

TASlation ไม่กรองหรือเซ็นเซอร์สิ่งที่โปรแกรมอ่านของคุณแสดง คุณจะเห็นหนังสือตามที่ตีพิมพ์ มังงะที่ตีพิมพ์ในญี่ปุ่นอาจมีภาพ รวมถึงภาพวาด ที่ผิดกฎหมายในการครอบครอง นำเข้า หรือดูในที่ที่คุณอยู่ แม้เพื่ออ่านเป็นการส่วนตัวและแม้จะถูกกฎหมายในญี่ปุ่นก็ตาม ในหลายประเทศการครอบครองเพียงอย่างเดียวเป็นอาชญากรรมร้ายแรง ตัวอย่างที่พบบ่อยคือภาพวาดทางเพศของตัวละครที่ดูเหมือนผู้เยาว์ ซึ่งถูกกฎหมายในญี่ปุ่นแต่ไม่ถูกกฎหมายในประเทศเหล่านั้น ส่วนภาพทางเพศของเด็กจริงเป็นอาชญากรรมในทุกที่ รวมถึงญี่ปุ่น TASlation ไม่เก็บสำเนา แต่หนังสือที่คุณเป็นเจ้าของและสิ่งใดก็ตามที่คุณบันทึกไว้เป็นความรับผิดชอบของคุณ

ในทางปฏิบัติ ความเสี่ยงมาตามลำดับนี้: กฎหมายของประเทศคุณเกี่ยวกับการครอบครองเนื้อหาบางประเภท ร้านของคุณปิดบัญชีของคุณเพราะละเมิดข้อกำหนด และลิขสิทธิ์ ซึ่งจะกลายเป็นเรื่องจริงจังก็ต่อเมื่อคุณแบ่งปันสิ่งที่แปล

คำแปลมาจากโมเดล AI ในเครื่อง และอาจผิดพลาดได้ รวมถึงชื่อ ตัวเลข และความหมายของบทพูด อย่าใช้คำแปลเป็นหลักในเรื่องที่สำคัญ โมเดลแปลภาษา PLaMo ซึ่ง TASlation ใช้กับภาษาส่วนใหญ่ มีสัญญาอนุญาตของตนเอง หากมีการเผยแพร่คำแปลที่สร้างด้วยโมเดลนี้ ต้องระบุอย่างชัดเจนว่าเป็นผลลัพธ์ของ PLaMo (PLaMo Community License ข้อ 5)

TASlation จัดให้ตามสภาพที่เป็นอยู่ โดยไม่มีการรับประกันใด ๆ ภายใต้สัญญาอนุญาต MIT เท่าที่กฎหมายอนุญาต ผู้สร้างจะไม่รับผิดต่อความเสียหายหรือผลทางกฎหมายใด ๆ ที่เกิดจากการใช้งาน จากหนังสือที่คุณอ่านด้วยโปรแกรมนี้ หรือจากประกาศนี้ ซึ่งเป็นการสรุปกฎหมายที่เปลี่ยนแปลงได้และไม่ใช่คำแนะนำทางกฎหมาย การดำเนินการต่อถือว่าคุณยอมรับเงื่อนไขนี้

README อธิบายสถานะทางกฎหมายโดยละเอียดมากขึ้น ประกาศนี้จะปรากฏทุกครั้งที่เริ่มโปรแกรมจนกว่าคุณจะทำเครื่องหมายในช่องด้านล่าง หากต้องการอ่านอีกครั้งเมื่อใดก็ได้ ให้ใช้ ความช่วยเหลือ > ประกาศทางกฎหมาย... ในหน้าต่าง""",
}


def text(code: str | None) -> str:
    """The general part, in the window's language."""
    return TEXTS.get(code or DEFAULT, TEXTS[DEFAULT])


_LEAD = re.compile(r"^([^.。:：\n]{1,40})[.。]\s*")  # "Japan. Copyright: ..." / "日本。著作権: ..."


def _own_section(country: str | None, lang: str) -> tuple[str, str] | None:
    """The name a country's part begins with and the rest of it, for a country in the list whose part exists in
    *lang* itself (not the English stand-in under a note); None otherwise."""
    j = jurisdictions.JURISDICTIONS.get((country or "").upper())
    own = j.sections.get(lang) if j is not None else None
    match = _LEAD.match(own) if own else None
    if match is None:
        return None
    return match.group(1).strip(), own[match.end():]


def country_heading(country: str | None, code: str | None) -> str:
    """The line that heads the country part: the country's name in the window's language, as its part begins with
    it, or the "not in the list" entry."""
    lang = code or DEFAULT
    own = _own_section(country, lang)
    if own is not None:
        return own[0]
    j = jurisdictions.JURISDICTIONS.get((country or "").upper())
    return j.name if j is not None else other_name(lang)


def full_text(code: str | None, country: str | None) -> str:
    """The notice as shown: the first paragraph of the general part, then the part for *country* under a heading
    with its name (the "not in the list" text for an unknown one), then the rest of the general part. The reader's
    own country comes first because it is the part that decides anything for them; the name the part begins with
    becomes its heading rather than being said twice."""
    lang = code or DEFAULT
    first, _, rest = text(lang).partition("\n\n")
    own = _own_section(country, lang)
    body = own[1] if own is not None else jurisdictions.section(country, lang)
    section = country_heading(country, lang) + "\n" + body
    return "\n\n".join(part for part in (first, section, rest) if part)


def title(code: str | None) -> str:
    return TITLES.get(code or DEFAULT, TITLES[DEFAULT])


def buttons(code: str | None) -> tuple[str, str]:
    return BUTTONS.get(code or DEFAULT, BUTTONS[DEFAULT])


def checkbox(code: str | None) -> str:
    return CHECKBOX.get(code or DEFAULT, CHECKBOX[DEFAULT])


def country_label(code: str | None) -> str:
    return COUNTRY_LABEL.get(code or DEFAULT, COUNTRY_LABEL[DEFAULT])


def language_label(code: str | None) -> str:
    return LANGUAGE_LABEL.get(code or DEFAULT, LANGUAGE_LABEL[DEFAULT])


def other_name(code: str | None) -> str:
    """The "not in the list" entry of the country chooser."""
    return jurisdictions.OTHER_NAMES.get(code or DEFAULT, jurisdictions.OTHER_NAMES[DEFAULT])


def wraps_by_character(code: str | None) -> bool:
    """Scripts without spaces between words wrap by character."""
    return (code or DEFAULT) in ("ja", "zh", "zh-tw", "ko", "th")


def default_country() -> str | None:
    """The country of the user's region setting (Windows) or locale, when it is one of the listed ones."""
    code = ""
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(16)
        if ctypes.windll.kernel32.GetUserDefaultGeoName(buf, 16) > 1:  # "JP"; a number for an unknown region
            code = buf.value
        if not code.isalpha():
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85) > 1:  # "ja-JP"
                code = buf.value.split("-")[-1]
    except (AttributeError, OSError, ValueError):
        pass
    if not code.isalpha():
        try:
            import locale

            code = (locale.getlocale()[0] or "").replace("-", "_").split("_")[-1]  # "en_GB" -> "GB"
        except (ValueError, TypeError):
            code = ""
    code = code.upper()
    return code if code in jurisdictions.JURISDICTIONS else None


def notice_path(state_dir: Path) -> Path:
    return Path(state_dir) / "notice.json"


def _load(state_dir: Path) -> dict:
    try:
        with open(notice_path(state_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(state_dir: Path, data: dict) -> None:
    path = notice_path(state_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
    except OSError:
        pass


def country(state_dir: Path) -> str | None:
    """The country the reader chose (None before the first choice; "other" for one not in the list)."""
    code = _load(state_dir).get("country")
    if code == jurisdictions.OTHER:
        return code
    return code.upper() if isinstance(code, str) and code.upper() in jurisdictions.JURISDICTIONS else None


def save_country(state_dir: Path, code: str | None) -> None:
    data = _load(state_dir)
    data["country"] = code or jurisdictions.OTHER
    _save(state_dir, data)


def dismissed(state_dir: Path) -> bool:
    """Whether the reader ticked "do not show this again" for this version of the notice, in the window."""
    try:
        return int(_load(state_dir).get("dismissed", 0)) >= NOTICE_VERSION
    except (TypeError, ValueError):
        return False


def dismiss(state_dir: Path, code: str | None) -> None:
    """Remember the reader's choice not to see this version of the notice again."""
    data = _load(state_dir)
    data.update({"dismissed": NOTICE_VERSION, "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "language": code or DEFAULT})
    _save(state_dir, data)


def printed(state_dir: Path) -> bool:
    """Whether the command line has printed this version of the notice."""
    try:
        return int(_load(state_dir).get("printed", 0)) >= NOTICE_VERSION
    except (TypeError, ValueError):
        return False


def reset(state_dir: Path) -> bool:
    """Forget the dismissal and the printing (the country stays): the notice shows and prints again."""
    data = _load(state_dir)
    if "dismissed" not in data and "printed" not in data:
        return False
    data.pop("dismissed", None)
    data.pop("printed", None)
    data.pop("when", None)
    _save(state_dir, data)
    return True


def console_text(code: str | None, country_code: str | None = None) -> str:
    bar = "=" * 72
    return f"{bar}\n{title(code)}\n{bar}\n{full_text(code, country_code)}\n{bar}"


def print_once(state_dir: Path, code: str | None, country_code: str | None = None, stream: TextIO | None = None) -> bool:
    """On the command line: print the notice the first time any command reads a book, and remember that."""
    if printed(state_dir):
        return False
    print(console_text(code, country_code), file=stream or sys.stderr, flush=True)
    data = _load(state_dir)
    data.update({"printed": NOTICE_VERSION, "printed_language": code or DEFAULT})
    _save(state_dir, data)
    return True


__all__ = ["NOTICE_VERSION", "TEXTS", "TITLES", "BUTTONS", "CHECKBOX", "COUNTRY_LABEL", "LANGUAGE_LABEL", "text",
           "full_text", "country_heading", "title", "buttons", "checkbox", "country_label", "language_label", "other_name",
           "wraps_by_character", "default_country", "notice_path", "country", "save_country", "dismissed", "dismiss",
           "printed", "reset", "console_text", "print_once"]

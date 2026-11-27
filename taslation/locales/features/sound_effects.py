"""The window's line on the kind "Sound effect" under the region editor's Kind list (`ui.dialogs.review.SFX_TIP`): how a
sound effect is lettered (at the slant the drawing gives it, as large as it fits, in the series sheet's lettering for
sound effects: `Pipeline._doubtful_slant`, `render.typeset.UNCAPPED_KINDS`) and that the program finds the sound words
lettered on the drawing itself (`Pipeline._sound_word`), which "(not set)" keeps and another kind turns off. "(not
set)" and "Sound effect" are worded as the Kind list's entries are in each language.

Machine-translated; no native review."""

TEXTS: dict[str, dict[str, str]] = {
    "Sound effect: lettered at the slant the drawing gives it, as large as it fits, in the series sheet's lettering "
    "for sound effects. The program finds the sound words lettered on the drawing itself: (not set) keeps what it "
    "found, and another kind turns it off.": {
        "ja": "効果音: 絵が付けている傾きのまま、収まる限り大きく、シリーズ設定の効果音の写植で入れます。"
              "絵に描かれた効果音はプログラムが自分で見つけます。（指定なし）なら見つけたとおりに、"
              "ほかの種別にすると効果音として扱いません。",
        "es": "Efecto de sonido: se rotula con la inclinación que le da el dibujo, tan grande como quepa, con la "
              "rotulación de efectos de sonido de la ficha de la serie. El programa encuentra por sí mismo las "
              "onomatopeyas dibujadas: (sin indicar) mantiene lo que encontró y otro tipo lo desactiva.",
        "pt": "Efeito sonoro: letreirado com a inclinação que o desenho lhe dá, tão grande quanto couber, com o "
              "letreiramento de efeitos sonoros da ficha da série. O programa encontra sozinho as onomatopeias "
              "desenhadas: (não definido) mantém o que ele encontrou e outro tipo desativa isso.",
        "fr": "Bruitage : lettré avec l'inclinaison que lui donne le dessin, aussi grand qu'il tient, dans le "
              "lettrage des effets sonores de la fiche de la série. Le programme trouve lui-même les bruitages "
              "dessinées : (non précisé) garde ce qu'il a trouvé, un autre type le désactive.",
        "de": "Soundeffekt: mit der Neigung gelettert, die die Zeichnung ihm gibt, so groß, wie er passt, im "
              "Lettering des Serienblatts für Soundeffekte. Das Programm findet die gezeichneten Lautwörter selbst: "
              "(nicht angegeben) behält, was es gefunden hat, eine andere Art schaltet es ab.",
        "it": "Effetto sonoro: letterato con l'inclinazione che gli dà il disegno, grande quanto ci sta, con il "
              "lettering per gli effetti sonori della scheda della serie. Il programma trova da sé le onomatopee "
              "disegnate: (non indicato) mantiene ciò che ha trovato, un altro tipo lo disattiva.",
        "nl": "Geluidseffect: geletterd met de helling die de tekening het geeft, zo groot als het past, in de "
              "belettering voor geluidseffecten van het serieblad. Het programma vindt de getekende klanknabootsingen "
              "zelf: (niet ingesteld) houdt wat het vond, een ander soort zet het uit.",
        "pl": "Efekt dźwiękowy: liternictwo z nachyleniem, jakie nadaje mu rysunek, tak duże, jak się zmieści, w "
              "liternictwie efektów dźwiękowych z karty serii. Program sam znajduje narysowane onomatopeje: (nie "
              "ustawiono) zachowuje to, co znalazł, a inny rodzaj to wyłącza.",
        "ru": "Звуковой эффект: надпись с тем наклоном, который ей даёт рисунок, настолько крупно, насколько "
              "помещается, шрифтом для звуковых эффектов из листа серии. Нарисованные звукоподражания программа "
              "находит сама: (не задано) оставляет найденное, другой вид отключает это.",
        "tr": "Ses efekti: çizimin ona verdiği eğimle, sığdığı kadar büyük, seri sayfasındaki ses efektleri "
              "yazısıyla yazılır. Çizime yazılmış yansıma sözcükleri program kendisi bulur: (belirtilmedi) bulduğunu "
              "korur, başka bir tür bunu kapatır.",
        "id": "Efek suara: ditulis dengan kemiringan yang diberikan gambarnya, sebesar yang muat, dengan huruf efek "
              "suara dari lembar seri. Program menemukan sendiri onomatope yang digambar: (tidak diatur) "
              "mempertahankan yang ditemukannya, dan jenis lain mematikannya.",
        "vi": "Hiệu ứng âm thanh: được viết chữ theo độ nghiêng mà hình vẽ cho nó, lớn nhất có thể vừa, bằng kiểu "
              "chữ hiệu ứng âm thanh của bảng bộ truyện. Chương trình tự tìm các từ tượng thanh được vẽ: (chưa đặt) "
              "giữ những gì nó tìm thấy, còn loại khác thì tắt việc đó.",
        "zh": "音效：按画面给它的倾斜角度、在放得下的范围内尽量大，用系列设定中音效的字体嵌字。画中的拟声词由程序自己找出：（未指定）保留它找到的，"
              "选其他类型则关闭。",
        "zh-tw": "音效：依畫面給它的傾斜角度、在放得下的範圍內盡量大，用系列設定中音效的字體嵌字。畫中的擬聲詞由程式自己找出：（未指定）保留它找到的，"
                 "選其他類型則關閉。",
        "ko": "효과음: 그림이 준 기울기 그대로, 들어가는 한 크게, 시리즈 시트의 효과음 레터링으로 넣습니다. 그림에 그려진 의성어는 "
              "프로그램이 스스로 찾습니다. (지정 안 함)이면 찾은 대로 두고, 다른 종류로 하면 끕니다.",
        "th": "เสียงประกอบ: ใส่ตัวอักษรตามความเอียงที่ภาพวาดให้ไว้ ใหญ่เท่าที่ใส่ได้ "
              "ด้วยตัวอักษรสำหรับเสียงประกอบในแผ่นข้อมูลชุด "
              "โปรแกรมหาคำเลียนเสียงที่วาดไว้บนภาพเอง: (ไม่ได้กำหนด) จะคงสิ่งที่หาเจอไว้ และชนิดอื่นจะปิดสิ่งนี้",
    },
}

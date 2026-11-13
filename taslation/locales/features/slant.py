"""The region editor's slant: the box for the angle the lettering is set at, and its tip."""

TEXTS: dict[str, dict[str, str]] = {
    "Slant:": {
        "ja": "傾き:", "es": "Inclinación:", "pt": "Inclinação:", "fr": "Inclinaison :", "de": "Neigung:",
        "it": "Inclinazione:", "nl": "Helling:", "pl": "Nachylenie:", "ru": "Наклон:", "tr": "Eğim:",
        "id": "Kemiringan:", "vi": "Độ nghiêng:", "zh": "倾斜：", "zh-tw": "傾斜：", "ko": "기울기:",
        "th": "ความเอียง:",
    },
    "How far the lines are turned, in degrees counter-clockwise. Auto keeps the slant of the original lettering; 0 sets them straight.": {
        "ja": "行を傾ける角度（反時計回り、度）。自動は元の文字の傾きのまま、0 でまっすぐにします。",
        "es": "Cuánto se giran las líneas, en grados en sentido antihorario. Auto mantiene la inclinación del rotulado original; 0 las pone rectas.",
        "pt": "Quanto as linhas são giradas, em graus no sentido anti-horário. Auto mantém a inclinação do letreiramento original; 0 as deixa retas.",
        "fr": "De combien les lignes sont tournées, en degrés dans le sens antihoraire. Auto garde l'inclinaison du lettrage d'origine ; 0 les redresse.",
        "de": "Wie weit die Zeilen gedreht sind, in Grad gegen den Uhrzeigersinn. Auto behält die Neigung der ursprünglichen Schrift; 0 stellt sie gerade.",
        "it": "Di quanto sono ruotate le righe, in gradi in senso antiorario. Auto mantiene l'inclinazione del lettering originale; 0 le raddrizza.",
        "nl": "Hoe ver de regels gedraaid zijn, in graden tegen de klok in. Auto houdt de helling van de oorspronkelijke belettering; 0 zet ze recht.",
        "pl": "O ile obrócone są wiersze, w stopniach przeciwnie do ruchu wskazówek zegara. Auto zachowuje nachylenie oryginalnego liternictwa; 0 je prostuje.",
        "ru": "Насколько повёрнуты строки, в градусах против часовой стрелки. «Авто» сохраняет наклон исходного текста; 0 выпрямляет их.",
        "tr": "Satırların ne kadar döndürüldüğü, saat yönünün tersine derece olarak. Otomatik, özgün yazının eğimini korur; 0 onları düzeltir.",
        "id": "Seberapa jauh baris diputar, dalam derajat berlawanan arah jarum jam. Otomatis mempertahankan kemiringan huruf aslinya; 0 meluruskannya.",
        "vi": "Các dòng được xoay bao nhiêu độ, ngược chiều kim đồng hồ. Tự động giữ độ nghiêng của chữ gốc; 0 đặt chúng thẳng.",
        "zh": "各行旋转的角度（逆时针，度）。自动保持原文字的倾斜；0 则摆正。",
        "zh-tw": "各行旋轉的角度（逆時針，度）。自動保持原文字的傾斜；0 則擺正。",
        "ko": "줄을 돌리는 각도(반시계 방향, 도)입니다. 자동은 원래 글자의 기울기를 따르고, 0은 똑바로 놓습니다.",
        "th": "มุมที่หมุนบรรทัด เป็นองศาทวนเข็มนาฬิกา อัตโนมัติจะคงความเอียงของตัวอักษรต้นฉบับ 0 จะตั้งให้ตรง",
    },
}

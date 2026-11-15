"""The window's string for a target language whose script this computer cannot shape (`render.shaping`): the setup
banner's notice that Hindi or Bengali lettering is drawn letter by letter here, until uharfbuzz is installed again.
{language} is the language's name as the "To:" box shows it in the window's language.

Machine-translated; no native review."""

from __future__ import annotations

TEXTS: dict[str, dict[str, str]] = {
    "Lettering in {language} cannot be shaped on this computer: its letters are drawn one by one, so conjuncts and vowel signs come out wrong. Run install.cmd again to install what is missing.": {
        "ja": "この PC では{language}の文字を正しく組めません。文字が1つずつ描かれるため、結合文字や母音記号が崩れて表示されます。install.cmd をもう一度実行して、足りないものをインストールしてください。",
        "es": "El rotulado en {language} no se puede componer en este equipo: sus letras se dibujan una a una, así que los grupos consonánticos y los signos vocálicos salen mal. Ejecuta install.cmd de nuevo para instalar lo que falta.",
        "pt": "O letreiramento em {language} não pode ser composto neste computador: as letras são desenhadas uma a uma, então os grupos consonantais e os sinais vocálicos saem errados. Execute install.cmd novamente para instalar o que falta.",
        "fr": "Le lettrage en {language} ne peut pas être composé sur cet ordinateur : ses lettres sont dessinées une à une, si bien que les consonnes conjointes et les signes vocaliques sont faux. Exécutez de nouveau install.cmd pour installer ce qui manque.",
        "de": "Die Beschriftung auf {language} kann auf diesem Rechner nicht gesetzt werden: Die Buchstaben werden einzeln gezeichnet, sodass Konsonantenverbindungen und Vokalzeichen falsch erscheinen. Führen Sie install.cmd erneut aus, um das Fehlende zu installieren.",
        "it": "Il lettering in {language} non può essere composto su questo computer: le lettere vengono disegnate una per una, quindi i nessi consonantici e i segni vocalici risultano sbagliati. Esegui di nuovo install.cmd per installare ciò che manca.",
        "nl": "Belettering in het {language} kan op deze computer niet worden gezet: de letters worden een voor een getekend, zodat medeklinkerverbindingen en klinkertekens verkeerd uitvallen. Voer install.cmd opnieuw uit om te installeren wat ontbreekt.",
        "pl": "Liternictwa w języku {language} nie da się złożyć na tym komputerze: litery są rysowane pojedynczo, więc zbitki spółgłoskowe i znaki samogłoskowe wychodzą źle. Uruchom ponownie install.cmd, aby zainstalować to, czego brakuje.",
        "ru": "Надписи на языке «{language}» нельзя правильно набрать на этом компьютере: буквы рисуются по одной, поэтому лигатуры согласных и знаки гласных выходят неверно. Запустите install.cmd ещё раз, чтобы установить недостающее.",
        "tr": "{language} yazı bu bilgisayarda doğru dizilemiyor: harfler tek tek çiziliyor, bu yüzden ünsüz birleşimleri ve ünlü işaretleri yanlış çıkıyor. Eksik olanı kurmak için install.cmd dosyasını yeniden çalıştırın.",
        "id": "Huruf {language} tidak dapat disusun dengan benar di komputer ini: hurufnya digambar satu per satu, sehingga gugus konsonan dan tanda vokal tampil salah. Jalankan install.cmd lagi untuk memasang yang kurang.",
        "vi": "Chữ {language} không thể được dàn đúng trên máy này: các chữ cái được vẽ từng chữ một, nên các phụ âm ghép và dấu nguyên âm hiển thị sai. Hãy chạy lại install.cmd để cài phần còn thiếu.",
        "zh": "本机无法正确排版{language}文字：字母被逐个绘制，因此连写辅音和元音符号显示有误。请再次运行 install.cmd 安装缺少的部分。",
        "zh-tw": "本機無法正確排版{language}文字：字母被逐一繪製，因此連寫子音和母音符號顯示有誤。請再次執行 install.cmd 安裝缺少的部分。",
        "ko": "이 컴퓨터에서는 {language} 글자를 제대로 조판할 수 없습니다. 글자가 하나씩 그려져서 결합 자음과 모음 기호가 잘못 표시됩니다. install.cmd를 다시 실행하여 빠진 부분을 설치하세요.",
        "th": "คอมพิวเตอร์เครื่องนี้จัดเรียงตัวอักษร{language}ให้ถูกต้องไม่ได้ ตัวอักษรจะถูกวาดทีละตัว ทำให้พยัญชนะควบและเครื่องหมายสระแสดงผิด เรียก install.cmd อีกครั้งเพื่อติดตั้งส่วนที่ขาด",
    },
}

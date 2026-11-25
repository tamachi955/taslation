"""Turkish (Türkçe) templates for `taslation.messages` (see `taslation.message_texts`): the polite imperative, as the
window; its buttons as the window names them (Durdur).

A noun after a number stays singular in Turkish ("3 sayfa"), so counts need no plural words; no suffix is put on a
placeholder (its sound decides the suffix), it goes on the noun after it ("{model} modeli", "{url} adresinde").

Machine-translated; no native review.
"""

TEMPLATES: dict[str, str] = {
    "batch.reply_unusable": "modelin yanıtı kullanılamadı",
    "batch.note_gave_up": "{units} sayfa birimi tekrarlanan hatalardan sonra bırakıldı; sayfaları okunurken çevrilir",
    "batch.note_retry_failed": "{bubbles} satırlık istek başarısız oldu ({error}); iki yarıya bölünerek yeniden deneniyor",
    "batch.note_retry_unusable": "{bubbles} satırlık istek kullanılamaz döndü; iki yarıya bölünerek yeniden deneniyor",
    "batch.note_unit_failed": "sayfa birimi {unit}: {error}; sayfası okunurken çevrilecek",
    "batch.note_incomplete": "{units} sayfa biriminden {incomplete} tanesi eksik döndü; eksik olanlar yeniden isteniyor",
    "batch.note_unit_incomplete": "sayfa birimi {unit}: eksik çeviri; eksik kalan kısım sayfası okunurken çevrilecek",
    "viewer.gone": "TASlation görüntüleyici penceresini göremiyor. Açık ve simge durumuna küçültülmemiş olduğunu denetleyin.",
    "viewer.no_area": "TASlation görüntüleyici penceresini göremiyor. Açık ve simge durumuna küçültülmemiş olduğunu denetleyin.",
    "viewer.windows_only": "pencere yakalama yalnızca Windows'ta kullanılabilir",
    "viewer.api_failed": "TASlation görüntüleyici penceresini göremiyor. Açık ve simge durumuna küçültülmemiş olduğunu denetleyin.",
    "viewer.window_api_failed": "TASlation görüntüleyici penceresini göremiyor. Açık ve simge durumuna küçültülmemiş olduğunu denetleyin.",
    "viewer.empty_rect": "TASlation görüntüleyici penceresini göremiyor. Açık ve simge durumuna küçültülmemiş olduğunu denetleyin.",
    "viewer.error": "{detail}",
    "pipeline.stage_finding": "Balonlar aranıyor...",
    "pipeline.stage_reading": "Metin okunuyor {done}/{total}...",
    "pipeline.stage_translating": "{bubbles} balon {translator} ile çevriliyor...",
    "pipeline.stage_rendering": "Sayfa çiziliyor...",
    "pipeline.no_translator": "çevirmen ayarlanmamış",
    "pipeline.cancelled": "iptal edildi",
    "pipeline.from_cache": "Önceki çevirilerden gösterilen satır: {bubbles}.",
    "pipeline.translated": "Çevrilen satır: {bubbles} ({seconds:.0f} sn).",
    "pipeline.to_review": "Bakmaya değer: {review} (Okuyucu modu'nu kapatın, sonra Menü > Gözden geçir...).",
    "pipeline.page_error": "{error}",
    "pipeline.no_content": "Görüntüleyicide sayfa bulunamadı. Kitabın açık olduğunu denetleyin veya sol bölmedeki Alan belirle... seçeneğini kullanın.",
    "ollama.unreachable": "TASlation çeviri programına ulaşamadı. Biraz sonra Çevir'e basın; kendiliğinden başlar.",
    "ollama.model_missing": ("{model} çeviri modeli kurulu değil. Kurmak için install.cmd dosyasını yeniden çalıştırın."),
    "ollama.http_error": "Çeviri programı reddetti ({status}). Yeniden denemek için Çevir'e basın; tekrarlarsa bilgisayarınızı yeniden başlatın.",
    "ollama.timeout": "Çeviri çok uzun sürdü. Yeniden denemek için Çevir'e basın.",
    "ollama.connection_failed": "Çeviri programı yanıt vermeyi bıraktı. Yeniden denemek için Çevir'e basın.",
    "ollama.bad_json": "Çeviri programı, TASlation'ın kullanamadığı bir yanıt verdi. Yeniden denemek için Çevir'e basın.",
    "ollama.reported_error": "Çeviri programı, TASlation'ın kullanamadığı bir yanıt verdi. Yeniden denemek için Çevir'e basın.",
    "ollama.broke_off": "Çeviri programı, TASlation'ın kullanamadığı bir yanıt verdi. Yeniden denemek için Çevir'e basın.",
    "ollama.bad_answer": "Çeviri programı, TASlation'ın kullanamadığı bir yanıt verdi. Yeniden denemek için Çevir'e basın.",
    "ollama.not_loopback": "Ollama URL'si bu bilgisayarı gösteren (loopback) bir http(s) adresi olmalı; verilen: “{url}”",
    "ollama.slow": "Çeviri programı yavaş yanıt veriyor (hâlâ yükleniyor olabilir). Durdur bu sayfayı iptal eder.",
    "ollama.no_answer": "Çeviri programı {seconds:.0f} sn yanıt vermedi, bu yüzden TASlation yeniden soruyor.",
    "ollama.restarting": "Çeviri programı hâlâ yanıt vermiyor, bu yüzden TASlation onu yeniden başlatıyor...",
    "ollama.not_answering": ("Bu bilgisayardaki çeviri programı yanıt vermiyor. Onu (veya TASlation'ı) yeniden "
                             "başlatın, sonra Çevir'e basın."),
    "ollama.loaded": "Çevirici hazır.",
    "ollama.loading": "Çevirici hazırlanıyor...",
    "ollama.partly_on_gpu": "Çeviricinin yalnızca %{percent} kadarı ekran kartına sığıyor, bu yüzden çeviri yavaş olacak. Ekran kartını kullanan diğer programları kapatın.",
    "translator.failed": "{detail}",
    "ocr.model_missing": ("Japonca okuyan bölüm eksik. TASlation klasöründeki install.cmd dosyasına çift tıklayın. Çevrilmiş sayfalar gösterilmeye devam eder."),
    "ocr.error": "{detail}",
    "ocr.one_reader": "Japonca okuma temel biçimde çalışıyor. İyileştirmek için install.cmd dosyasına çift tıklayın.",
    "layout.classical": "Çizimin üzerindeki yazılar temel yöntemle aranıyor. Daha fazlasını bulmak için install.cmd dosyasına çift tıklayın.",
    "health.ollama_down": ("Çeviri programı çalışmıyor, bu yüzden yeni sayfalar çevrilemez. TASlation bir sonraki sayfada başlatmayı dener; bu uyarı kalırsa bilgisayarınızı yeniden başlatın. Çevrilmiş sayfalar yine okunabilir."),
    "health.ollama_not_installed": "Çeviri programı yüklü değil. TASlation klasöründeki install.cmd dosyasına çift tıklayın.",
    "health.ollama_no_answer": ("Çeviri programı başlamadı. Bilgisayarınızı yeniden başlatın, sonra TASlation'ı yeniden açın. Çevrilmiş sayfalar yine okunabilir."),
    "health.model_missing": "{model} çeviri modeli kurulu değil. Kurmak için install.cmd dosyasını yeniden çalıştırın.",
    "health.chosen_model_missing": ("Ayarlarda seçilen {model} modeli Ollama'da kurulu değil. Bir terminalde şunu "
                                    "çalıştırın: {command}"),
    "health.ocr_missing": ("Japonca okuyan bölüm eksik. TASlation klasöründeki install.cmd dosyasına çift tıklayın. Çevrilmiş sayfalar gösterilmeye devam eder."),
    "health.other_model": ("{wanted} modeli Ollama'da kurulu değil; şimdilik {used} modeliyle çevriliyor. {wanted} "
                           "modelini kurmak için install.cmd dosyasını yeniden çalıştırın."),
    "health.chosen_other_model": ("Ayarlarda seçilen {wanted} modeli Ollama'da kurulu değil; şimdilik {used} "
                                  "modeliyle çevriliyor. {wanted} modelini kurmak için bir terminalde şunu "
                                  "çalıştırın: {command}"),
    "pipeline.no_text": "Bu sayfada metin yok.",
    "rename.unreadable": "{path} okunamıyor. Onu {folder} dışına taşıyın, sonra yeniden deneyin.",
    "rename.busy": "{path} şu anda açılamıyor. Onu tutan programı kapatın, sonra yeniden deneyin.",
    "rename.in_way": "{path} engel oluyor. Onu {folder} dışına taşıyın, sonra yeniden deneyin.",
    "rename.no_name": "Bu ad bir kitabı belirtmiyor; kitaba kendi adını verin.",
    "rename.same_name": "Kitabın adı zaten {book}.",
    "store.protected": "{files} kayıtlı dosya korundu: bundan sonra yalnızca bu Windows kullanıcısı onları bu bilgisayarda açabilir.",
    "store.not_protected": "{files} kayıtlı dosya henüz korunamadı: başka bir program onları kullanıyor. TASlation bir sonraki başlatmada yeniden dener.",
    "store.not_here": "{files} kayıtlı dosya bu Windows kullanıcısı tarafından bu bilgisayarda açılamıyor: başka bir Windows kullanıcısı tarafından ya da başka bir bilgisayarda kaydedilmiş veya bozuk. TASlation bunların üzerine asla yazmaz: böyle bir kitap baştan başlar ve dosyası yeni bir adla yanında saklanır. Bir kitabın çevirilerini buraya getirmek için onları kaydedildikleri yerde dışa aktarın (Menü > Kaydedilen çeviriler... > Şifreli dışa aktar...) ve o dosyayı burada içe aktarın (İçe aktar...).",
    "store.set_aside": "Bu kitabın kayıtlı bir dosyası bu Windows kullanıcısı tarafından bu bilgisayarda açılamıyor: başka bir Windows kullanıcısı tarafından ya da başka bir bilgisayarda kaydedilmiş veya bozuk. Dosya {path} olarak saklanıyor ve kitap burada baştan başlıyor. Çevirilerini buraya getirmek için onları kaydedildikleri yerde dışa aktarın (Menü > Kaydedilen çeviriler... > Şifreli dışa aktar...) ve o dosyayı burada içe aktarın (İçe aktar...).",
    # the translation model the target language chooses (translate/models.py, translate/plamo.py)
    "translator.model_missing": "Bu dilin çeviri modeli {name} kurulu değil. Kurmak için install.cmd dosyasını yeniden çalıştırın.",
    "translator.other_model": "Bu dilin çeviri modeli {name} kurulu değil; şimdilik {used} modeliyle çevriliyor. {name} modelini kurmak için install.cmd dosyasını yeniden çalıştırın.",
    "plamo.cannot_write": "Ayarlarda seçilen model bu dile çeviri yapamıyor. Ayar dosyasından ollama_model satırını silin; TASlation doğru modeli kendisi seçer.",
}

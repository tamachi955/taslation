"""German (Deutsch) templates for `taslation.messages` (see `taslation.message_texts`): Sie, as the window; its buttons
as the window names them (Stopp)."""

TEMPLATES: dict[str, str] = {
    "batch.reply_unusable": "die Antwort des Modells war nicht verwendbar",
    "batch.note_gave_up": "nach wiederholten Fehlschlägen aufgegeben: {units:Seiteneinheit|Seiteneinheiten}; sie werden beim Lesen ihrer Seite übersetzt",
    "batch.note_retry_failed": "Anfrage für {bubbles:Zeile|Zeilen} fehlgeschlagen ({error}); neuer Versuch in zwei Hälften",
    "batch.note_retry_unusable": "Anfrage für {bubbles:Zeile|Zeilen} kam unbrauchbar zurück; neuer Versuch in zwei Hälften",
    "batch.note_unit_failed": "Seiteneinheit {unit}: {error}; wird beim Lesen ihrer Seite übersetzt",
    "batch.note_incomplete": ("unvollständig zurückgekommen: {incomplete} von {units:Seiteneinheit|Seiteneinheiten}; "
                              "neue Anfrage dafür"),
    "batch.note_unit_incomplete": ("Seiteneinheit {unit}: unvollständige Übersetzung; was fehlt, wird beim Lesen "
                                   "ihrer Seite übersetzt"),
    "viewer.covered": ("Der Viewer zeichnet nicht mehr, weil TASlation ihn vollständig verdeckt. Heben Sie die Maximierung "
                       "von TASlation auf oder verschieben Sie es so, dass ein Streifen des Viewers sichtbar bleibt."),
    "viewer.gone": "TASlation kann das Viewer-Fenster nicht sehen. Prüfen Sie, ob es offen und nicht minimiert ist.",
    "viewer.no_area": "TASlation kann das Viewer-Fenster nicht sehen. Prüfen Sie, ob es offen und nicht minimiert ist.",
    "viewer.windows_only": "Fensteraufnahme gibt es nur unter Windows",
    "viewer.unknown_key": ("unbekannter Tastenname: „{key}“ (Left, Right, PageDown, Space, ... oder ein einzelnes "
                           "Zeichen verwenden)"),
    "viewer.api_failed": "TASlation kann das Viewer-Fenster nicht sehen. Prüfen Sie, ob es offen und nicht minimiert ist.",
    "viewer.window_api_failed": "TASlation kann das Viewer-Fenster nicht sehen. Prüfen Sie, ob es offen und nicht minimiert ist.",
    "viewer.empty_rect": "TASlation kann das Viewer-Fenster nicht sehen. Prüfen Sie, ob es offen und nicht minimiert ist.",
    "viewer.error": "{detail}",
    "pipeline.stage_finding": "Sprechblasen werden gesucht...",
    "pipeline.stage_reading": "Text wird gelesen {done}/{total}...",
    "pipeline.stage_translating": "{bubbles:Sprechblase wird|Sprechblasen werden} mit {translator} übersetzt...",
    "pipeline.stage_rendering": "Seite wird gezeichnet...",
    "pipeline.no_translator": "kein Übersetzer eingerichtet",
    "pipeline.cancelled": "abgebrochen",
    "pipeline.from_cache": "{bubbles:Zeile|Zeilen} aus früheren Übersetzungen angezeigt.",
    "pipeline.translated": "{bubbles:Zeile|Zeilen} in {seconds:.0f} s übersetzt.",
    "pipeline.to_review": "{review:Zeile ist|Zeilen sind} einen Blick wert (Rolle Übersetzer, Durchsehen...).",
    "pipeline.page_error": "{error}",
    "pipeline.no_content": "Keine Seite im Viewer gefunden. Prüfen Sie, ob das Buch offen ist, oder verwenden Sie Bereich festlegen... (Menü Seite)",
    "ollama.unreachable": "TASlation konnte das Übersetzungsprogramm nicht erreichen. Drücken Sie gleich F5; es startet von selbst.",
    "ollama.model_missing": ("Das Übersetzungsmodell {model} ist nicht installiert. Führen Sie install.cmd erneut "
                             "aus, um es zu installieren."),
    "ollama.http_error": "Das Übersetzungsprogramm hat abgelehnt ({status}). Drücken Sie F5, um es noch einmal zu versuchen; wiederholt es sich, starten Sie den PC neu.",
    "ollama.timeout": "Die Übersetzung hat zu lange gedauert. Drücken Sie F5, um es noch einmal zu versuchen.",
    "ollama.connection_failed": ("Das Übersetzungsprogramm antwortet nicht mehr. Drücken Sie F5, um es noch einmal zu versuchen."),
    "ollama.bad_json": "Das Übersetzungsprogramm gab eine Antwort, die TASlation nicht verwenden konnte. Drücken Sie F5, um es noch einmal zu versuchen.",
    "ollama.reported_error": "Das Übersetzungsprogramm gab eine Antwort, die TASlation nicht verwenden konnte. Drücken Sie F5, um es noch einmal zu versuchen.",
    "ollama.broke_off": "Das Übersetzungsprogramm gab eine Antwort, die TASlation nicht verwenden konnte. Drücken Sie F5, um es noch einmal zu versuchen.",
    "ollama.bad_answer": "Das Übersetzungsprogramm gab eine Antwort, die TASlation nicht verwenden konnte. Drücken Sie F5, um es noch einmal zu versuchen.",
    "ollama.not_loopback": ("die Ollama-URL muss eine Loopback-Adresse (dieser Computer) mit http(s) sein, erhalten: "
                            "„{url}“"),
    "ollama.slow": "Das Übersetzungsprogramm antwortet langsam (es lädt vielleicht noch). Stopp bricht diese Seite ab.",
    "ollama.no_answer": "Das Übersetzungsprogramm hat {seconds:.0f} s lang nicht geantwortet, daher fragt TASlation es noch einmal.",
    "ollama.restarting": "Das Übersetzungsprogramm antwortet immer noch nicht, daher startet TASlation es neu...",
    "ollama.not_answering": ("Das Übersetzungsprogramm auf diesem Computer antwortet nicht. Starten Sie es (oder TASlation) "
                             "neu und drücken Sie dann F5."),
    "ollama.loaded": "Übersetzer bereit.",
    "ollama.loading": "Übersetzer wird vorbereitet...",
    "ollama.partly_on_gpu": "Nur {percent} % des Übersetzers passen auf die Grafikkarte, das Übersetzen wird daher langsam. Schließen Sie andere Programme, die die Grafikkarte nutzen.",
    "translator.failed": "{detail}",
    "ocr.model_missing": ("Der Teil, der Japanisch liest, fehlt. Doppelklicken Sie auf install.cmd im TASlation-Ordner. Bereits übersetzte Seiten werden weiter angezeigt."),
    "ocr.error": "{detail}",
    "ocr.one_reader": "Das Lesen des Japanischen läuft in der einfachen Form. Ein Doppelklick auf install.cmd verbessert es.",
    "layout.classical": "Schrift auf der Zeichnung wird auf die einfache Art gesucht. Ein Doppelklick auf install.cmd findet mehr davon.",
    "health.ollama_down": ("Das Übersetzungsprogramm läuft nicht, darum können neue Seiten nicht übersetzt werden. TASlation versucht bei der nächsten Seite, es zu starten; bleibt diese Meldung, starten Sie den PC neu. Bereits übersetzte Seiten können weiter gelesen werden."),
    "health.ollama_not_installed": ("Das Übersetzungsprogramm ist nicht installiert. Doppelklicken Sie auf install.cmd im TASlation-Ordner."),
    "health.ollama_no_answer": ("Das Übersetzungsprogramm ist nicht gestartet. Starten Sie den PC neu und öffnen Sie TASlation dann wieder. Bereits übersetzte Seiten können weiter gelesen werden."),
    "health.model_missing": ("Das Übersetzungsmodell {model} ist nicht installiert. Führen Sie install.cmd erneut "
                             "aus, um es zu installieren."),
    "health.chosen_model_missing": ("Das in den Einstellungen gewählte Modell {model} ist in Ollama nicht "
                                    "installiert. Führen Sie in einem Terminal aus: {command}"),
    "health.ocr_missing": ("Der Teil, der Japanisch liest, fehlt. Doppelklicken Sie auf install.cmd im TASlation-Ordner. Bereits übersetzte Seiten werden weiter angezeigt."),
    "health.other_model": ("{wanted} ist in Ollama nicht installiert; vorerst wird mit {used} übersetzt. Führen Sie "
                           "install.cmd erneut aus, um {wanted} zu installieren."),
    "health.chosen_other_model": ("Das in den Einstellungen gewählte {wanted} ist in Ollama nicht installiert; "
                                  "vorerst wird mit {used} übersetzt. Um {wanted} zu installieren, führen Sie in "
                                  "einem Terminal aus: {command}"),
    "pipeline.no_text": "Kein Text auf dieser Seite.",
    "rename.unreadable": "{path} kann nicht gelesen werden. Verschieben Sie die Datei aus {folder} und versuchen Sie es noch einmal.",
    "rename.busy": "{path} kann gerade nicht geöffnet werden. Schließen Sie das Programm, das die Datei hält, und versuchen Sie es noch einmal.",
    "rename.in_way": "{path} steht im Weg. Verschieben Sie die Datei aus {folder} und versuchen Sie es noch einmal.",
    "rename.no_name": "Dieser Name bezeichnet kein Buch; geben Sie dem Buch einen eigenen Namen.",
    "rename.same_name": "Das Buch heißt bereits {book}.",
    "store.protected": "{files:gespeicherte Datei|gespeicherte Dateien} geschützt: Ab jetzt kann nur dieser Windows-Benutzer sie öffnen, auf diesem Computer.",
    "store.not_protected": "Noch nicht geschützt: {files:gespeicherte Datei|gespeicherte Dateien}, die ein anderes Programm geöffnet hat. TASlation versucht es beim nächsten Start erneut.",
    "store.not_here": "Dieser Windows-Benutzer kann {files:gespeicherte Datei|gespeicherte Dateien} auf diesem Computer nicht öffnen: gespeichert von einem anderen Windows-Benutzer oder auf einem anderen Computer, oder beschädigt. TASlation überschreibt sie nie: Ein solches Buch beginnt neu, und seine Datei bleibt unter einem neuen Namen daneben liegen. Um die Übersetzungen eines Buchs hierher zu holen, exportieren Sie sie dort, wo sie gespeichert wurden (Menü > Gespeicherte Übersetzungen... > Exportieren (verschlüsselt)...), und importieren Sie diese Datei hier (Importieren...).",
    "store.set_aside": "Dieser Windows-Benutzer kann eine gespeicherte Datei dieses Buchs auf diesem Computer nicht öffnen: Sie wurde von einem anderen Windows-Benutzer oder auf einem anderen Computer gespeichert, oder sie ist beschädigt. Sie bleibt als {path} erhalten, und das Buch beginnt hier neu. Um seine Übersetzungen hierher zu holen, exportieren Sie sie dort, wo sie gespeichert wurden (Menü > Gespeicherte Übersetzungen... > Exportieren (verschlüsselt)...), und importieren Sie diese Datei hier (Importieren...).",
    # the translation model the target language chooses (translate/models.py, translate/plamo.py)
    "translator.model_missing": "Das Übersetzungsmodell für diese Sprache, {name}, ist nicht installiert. Führen Sie install.cmd erneut aus, um es zu installieren.",
    "translator.other_model": "Das Übersetzungsmodell für diese Sprache, {name}, ist nicht installiert; vorerst wird mit {used} übersetzt. Führen Sie install.cmd erneut aus, um {name} zu installieren.",
    "plamo.cannot_write": "Das in den Einstellungen gewählte Modell kann nicht in diese Sprache übersetzen. Entfernen Sie ollama_model aus der Einstellungsdatei, dann wählt TASlation selbst das passende Modell.",
}

"""Polish (Polski) templates for `taslation.messages` (see `taslation.message_texts`): the informal imperative, as the
window; its buttons as the window names them (Stop).

Polish has several plural forms: a count is written as a label ("dymków: 5", "stron: 21") or with a word that does
not change ("{minutes} min"), so that it reads right for every number.
"""

TEMPLATES: dict[str, str] = {
    "batch.reply_unusable": "nie udało się użyć odpowiedzi modelu",
    "batch.note_gave_up": "jednostek stron porzuconych po powtarzających się błędach: {units}; zostaną przetłumaczone podczas czytania ich strony",
    "batch.note_retry_failed": "żądanie (wierszy: {bubbles}) nie powiodło się ({error}); ponowna próba w dwóch połowach",
    "batch.note_retry_unusable": "żądanie (wierszy: {bubbles}) wróciło bezużyteczne; ponowna próba w dwóch połowach",
    "batch.note_unit_failed": "jednostka strony {unit}: {error}; zostanie przetłumaczona podczas czytania strony",
    "batch.note_incomplete": "niekompletnych jednostek stron: {incomplete} z {units}; ponowne żądanie dla nich",
    "batch.note_unit_incomplete": ("jednostka strony {unit}: niekompletne tłumaczenie; brakująca część zostanie "
                                   "przetłumaczona podczas czytania strony"),
    "viewer.covered": ("Czytnik przestał rysować, bo TASlation zasłania go całkowicie. Wyłącz maksymalizację okna "
                       "TASlation albo przesuń je tak, aby było widać choćby pasek czytnika."),
    "viewer.gone": "TASlation nie widzi okna czytnika. Sprawdź, czy jest otwarte i niezminimalizowane.",
    "viewer.no_area": "TASlation nie widzi okna czytnika. Sprawdź, czy jest otwarte i niezminimalizowane.",
    "viewer.windows_only": "przechwytywanie okien działa tylko w systemie Windows",
    "viewer.unknown_key": ("nieznana nazwa klawisza: „{key}” (użyj Left, Right, PageDown, Space... albo pojedynczej "
                           "litery)"),
    "viewer.api_failed": "TASlation nie widzi okna czytnika. Sprawdź, czy jest otwarte i niezminimalizowane.",
    "viewer.window_api_failed": "TASlation nie widzi okna czytnika. Sprawdź, czy jest otwarte i niezminimalizowane.",
    "viewer.empty_rect": "TASlation nie widzi okna czytnika. Sprawdź, czy jest otwarte i niezminimalizowane.",
    "viewer.error": "{detail}",
    "pipeline.stage_finding": "Szukanie dymków...",
    "pipeline.stage_reading": "Odczytywanie tekstu {done}/{total}...",
    "pipeline.stage_translating": "Tłumaczenie przez {translator} (dymków: {bubbles})...",
    "pipeline.stage_rendering": "Rysowanie strony...",
    "pipeline.no_translator": "nie skonfigurowano tłumacza",
    "pipeline.cancelled": "anulowano",
    "pipeline.from_cache": "Wiersze pokazane z wcześniejszych tłumaczeń: {bubbles}.",
    "pipeline.translated": "Przetłumaczone wiersze: {bubbles} ({seconds:.0f} s).",
    "pipeline.to_review": "Warto spojrzeć: {review} (rola Tłumacz, Przegląd...).",
    "pipeline.page_error": "{error}",
    "pipeline.no_content": "Nie znaleziono strony w czytniku. Sprawdź, czy książka jest otwarta, albo użyj Ustaw obszar... (menu Strona)",
    "ollama.unreachable": "TASlation nie może połączyć się z programem tłumaczącym. Naciśnij F5 za chwilę; uruchamia się sam.",
    "ollama.model_missing": "Model tłumaczenia {model} nie jest zainstalowany. Uruchom ponownie install.cmd, aby go "
                             "zainstalować.",
    "ollama.http_error": "Program tłumaczący odmówił ({status}). Naciśnij F5, aby spróbować ponownie; jeśli to się powtórzy, uruchom komputer ponownie.",
    "ollama.timeout": "Tłumaczenie trwało zbyt długo. Naciśnij F5, aby spróbować ponownie.",
    "ollama.connection_failed": ("Program tłumaczący przestał odpowiadać. Naciśnij F5, aby spróbować ponownie."),
    "ollama.bad_json": "Program tłumaczący dał odpowiedź, której TASlation nie mógł użyć. Naciśnij F5, aby spróbować ponownie.",
    "ollama.reported_error": "Program tłumaczący dał odpowiedź, której TASlation nie mógł użyć. Naciśnij F5, aby spróbować ponownie.",
    "ollama.broke_off": "Program tłumaczący dał odpowiedź, której TASlation nie mógł użyć. Naciśnij F5, aby spróbować ponownie.",
    "ollama.bad_answer": "Program tłumaczący dał odpowiedź, której TASlation nie mógł użyć. Naciśnij F5, aby spróbować ponownie.",
    "ollama.not_loopback": ("adres URL serwera Ollama musi być adresem http(s) pętli zwrotnej (ten komputer); podano: "
                            "„{url}”"),
    "ollama.slow": "Program tłumaczący wolno odpowiada (może jeszcze się wczytuje). Stop anuluje tę stronę.",
    "ollama.no_answer": "Program tłumaczący nie odpowiadał przez {seconds:.0f} s, więc TASlation pyta go ponownie.",
    "ollama.restarting": "Program tłumaczący nadal nie odpowiada, więc TASlation uruchamia go ponownie...",
    "ollama.not_answering": ("Program tłumaczący na tym komputerze nie odpowiada. Uruchom go ponownie (lub uruchom ponownie "
                             "TASlation), a potem naciśnij F5."),
    "ollama.loaded": "Tłumacz gotowy.",
    "ollama.loading": "Przygotowywanie tłumacza...",
    "ollama.partly_on_gpu": "Tylko {percent}% tłumacza mieści się na karcie graficznej, więc tłumaczenie będzie wolne. Zamknij inne programy korzystające z karty graficznej.",
    "translator.failed": "{detail}",
    "ocr.model_missing": ("Brakuje części czytającej japoński. Kliknij dwukrotnie install.cmd w folderze TASlation. Strony już przetłumaczone nadal się wyświetlają."),
    "ocr.error": "{detail}",
    "ocr.one_reader": "Odczyt japońskiego działa w wersji podstawowej. Kliknij dwukrotnie install.cmd, aby go ulepszyć.",
    "layout.classical": "Tekst na rysunku jest wyszukiwany w sposób podstawowy. Kliknij dwukrotnie install.cmd, aby znaleźć go więcej.",
    "health.ollama_down": ("Program tłumaczący nie działa, więc nowych stron nie można przetłumaczyć. TASlation spróbuje go uruchomić przy następnej stronie; jeśli to nie zniknie, uruchom komputer ponownie. Strony już przetłumaczone można nadal czytać."),
    "health.ollama_not_installed": "Program tłumaczący nie jest zainstalowany. Kliknij dwukrotnie install.cmd w folderze TASlation.",
    "health.ollama_no_answer": ("Program tłumaczący się nie uruchomił. Uruchom komputer ponownie, a potem znów otwórz TASlation. Strony już przetłumaczone można nadal czytać."),
    "health.model_missing": ("Model tłumaczenia {model} nie jest zainstalowany. Uruchom ponownie install.cmd, aby go "
                             "zainstalować."),
    "health.chosen_model_missing": ("Ollama nie ma zainstalowanego modelu {model} wybranego w ustawieniach. Uruchom "
                                    "w terminalu: {command}"),
    "health.ocr_missing": ("Brakuje części czytającej japoński. Kliknij dwukrotnie install.cmd w folderze TASlation. Strony już przetłumaczone nadal się wyświetlają."),
    "health.other_model": ("Ollama nie ma zainstalowanego modelu {wanted}; na razie tłumaczenie odbywa się modelem "
                           "{used}. Uruchom ponownie install.cmd, aby zainstalować {wanted}."),
    "health.chosen_other_model": ("Ollama nie ma zainstalowanego modelu {wanted} wybranego w ustawieniach; na razie "
                                  "tłumaczenie odbywa się modelem {used}. Aby zainstalować {wanted}, uruchom w "
                                  "terminalu: {command}"),
    "pipeline.no_text": "Na tej stronie nie ma tekstu.",
    "rename.unreadable": "Nie można odczytać {path}. Przenieś plik poza {folder} i spróbuj ponownie.",
    "rename.busy": "Nie można teraz otworzyć {path}. Zamknij program, który go trzyma, i spróbuj ponownie.",
    "rename.in_way": "{path} przeszkadza. Przenieś plik poza {folder} i spróbuj ponownie.",
    "rename.no_name": "Ta nazwa nie oznacza żadnej książki; nadaj książce własną nazwę.",
    "rename.same_name": "Książka już nazywa się {book}.",
    "store.protected": "Zabezpieczone zapisane pliki: {files}. Od teraz może je otworzyć tylko ten użytkownik systemu Windows, na tym komputerze.",
    "store.not_protected": "Jeszcze niezabezpieczone zapisane pliki: {files} (używa ich inny program). TASlation spróbuje ponownie przy następnym uruchomieniu.",
    "store.not_here": "Zapisane pliki, których ten użytkownik systemu Windows nie może otworzyć na tym komputerze: {files}. Zapisał je inny użytkownik systemu Windows lub inny komputer albo są uszkodzone. TASlation nigdy ich nie nadpisuje: taka książka zaczyna się od nowa, a jej plik zostaje obok pod nową nazwą. Aby przenieść tutaj tłumaczenia książki, wyeksportuj je tam, gdzie zostały zapisane (Menu > Zapisane tłumaczenia... > Eksportuj (zaszyfrowany)...), i zaimportuj ten plik tutaj (Importuj...).",
    "store.set_aside": "Ten użytkownik systemu Windows nie może otworzyć na tym komputerze zapisanego pliku tej książki: zapisał go inny użytkownik systemu Windows lub inny komputer albo plik jest uszkodzony. Zostaje zachowany jako {path}, a książka zaczyna się tutaj od nowa. Aby przenieść tutaj jej tłumaczenia, wyeksportuj je tam, gdzie zostały zapisane (Menu > Zapisane tłumaczenia... > Eksportuj (zaszyfrowany)...), i zaimportuj ten plik tutaj (Importuj...).",
    # the translation model the target language chooses (translate/models.py, translate/plamo.py)
    "translator.model_missing": "Model tłumaczenia dla tego języka, {name}, nie jest zainstalowany. Uruchom ponownie install.cmd, aby go zainstalować.",
    "translator.other_model": "Model tłumaczenia dla tego języka, {name}, nie jest zainstalowany; na razie tłumaczenie odbywa się modelem {used}. Uruchom ponownie install.cmd, aby zainstalować {name}.",
    "plamo.cannot_write": "Model wybrany w ustawieniach nie potrafi tłumaczyć na ten język. Usuń ollama_model z pliku ustawień, a TASlation sam wybierze właściwy model.",
}

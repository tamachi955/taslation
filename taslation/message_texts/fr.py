"""French (Français) templates for `taslation.messages` (see `taslation.message_texts`): vous, as the window; its
buttons as the window names them (Arrêter).

French takes the singular for 0 as for 1, which ``{n:one|many}`` cannot say: a count that can be 0 is written as a
label ("bulles : 0"); the plural words are used only for counts that are 1 or more whenever the message is shown.

Machine-translated; no native review.
"""

TEMPLATES: dict[str, str] = {
    "batch.reply_unusable": "la réponse du modèle est inutilisable",
    "batch.note_gave_up": "abandon après des échecs répétés ({units:unité de page|unités de page}) ; elles sont traduites à la lecture de leur page",
    "batch.note_retry_failed": "la requête de {bubbles:ligne|lignes} a échoué ({error}) ; nouvel essai en deux moitiés",
    "batch.note_retry_unusable": "la requête de {bubbles:ligne|lignes} est revenue inutilisable ; nouvel essai en deux moitiés",
    "batch.note_unit_failed": "unité de page {unit} : {error} ; elle est traduite à la lecture de sa page",
    "batch.note_incomplete": "unités de page incomplètes : {incomplete} sur {units} ; nouvelle demande pour celles-ci",
    "batch.note_unit_incomplete": ("unité de page {unit} : traduction incomplète ; ce qui manque est traduit à la "
                                   "lecture de sa page"),
    "viewer.gone": "TASlation ne voit pas la fenêtre de la visionneuse. Vérifiez qu'elle est ouverte et non réduite.",
    "viewer.no_area": "TASlation ne voit pas la fenêtre de la visionneuse. Vérifiez qu'elle est ouverte et non réduite.",
    "viewer.windows_only": "la capture de fenêtre n'est disponible que sous Windows",
    "viewer.api_failed": "TASlation ne voit pas la fenêtre de la visionneuse. Vérifiez qu'elle est ouverte et non réduite.",
    "viewer.window_api_failed": "TASlation ne voit pas la fenêtre de la visionneuse. Vérifiez qu'elle est ouverte et non réduite.",
    "viewer.empty_rect": "TASlation ne voit pas la fenêtre de la visionneuse. Vérifiez qu'elle est ouverte et non réduite.",
    "viewer.error": "{detail}",
    "pipeline.stage_finding": "Recherche des bulles...",
    "pipeline.stage_reading": "Lecture du texte {done}/{total}...",
    "pipeline.stage_translating": "Traduction de {bubbles:bulle|bulles} avec {translator}...",
    "pipeline.stage_rendering": "Rendu de la page...",
    "pipeline.no_translator": "aucun traducteur configuré",
    "pipeline.cancelled": "annulé",
    "pipeline.from_cache": "Lignes affichées depuis des traductions précédentes : {bubbles}.",
    "pipeline.translated": "Lignes traduites : {bubbles}, en {seconds:.0f} s.",
    "pipeline.to_review": "À regarder : {review} (activez Modifier, puis Menu > Relire...).",
    "pipeline.page_error": "{error}",
    "pipeline.no_content": "Aucune page trouvée dans la visionneuse. Vérifiez que le livre est ouvert, ou utilisez Définir la zone... dans le volet gauche.",
    "ollama.unreachable": "TASlation n'a pas pu joindre le programme de traduction. Appuyez sur Traduire dans un instant ; il démarre tout seul.",
    "ollama.model_missing": ("Le modèle de traduction {model} n'est pas installé. Exécutez de nouveau install.cmd "
                             "pour l'installer."),
    "ollama.http_error": "Le programme de traduction a refusé ({status}). Appuyez sur Traduire pour réessayer ; si cela se répète, redémarrez le PC.",
    "ollama.timeout": "La traduction a pris trop de temps. Appuyez sur Traduire pour réessayer.",
    "ollama.connection_failed": "Le programme de traduction ne répond plus. Appuyez sur Traduire pour réessayer.",
    "ollama.bad_json": "Le programme de traduction a donné une réponse que TASlation n'a pas pu utiliser. Appuyez sur Traduire pour réessayer.",
    "ollama.reported_error": "Le programme de traduction a donné une réponse que TASlation n'a pas pu utiliser. Appuyez sur Traduire pour réessayer.",
    "ollama.broke_off": "Le programme de traduction a donné une réponse que TASlation n'a pas pu utiliser. Appuyez sur Traduire pour réessayer.",
    "ollama.bad_answer": ("Le programme de traduction a donné une réponse que TASlation n'a pas pu utiliser. Appuyez sur Traduire pour réessayer."),
    "ollama.not_loopback": ("l'URL d'Ollama doit être une adresse http(s) de bouclage (cet ordinateur) ; reçu : "
                            "« {url} »"),
    "ollama.slow": "Le programme de traduction tarde à répondre (il se charge peut-être encore). Arrêter annule cette page.",
    "ollama.no_answer": "Le programme de traduction n'a pas répondu pendant {seconds:.0f} s ; TASlation lui redemande.",
    "ollama.restarting": "Le programme de traduction ne répond toujours pas ; TASlation le redémarre...",
    "ollama.not_answering": ("Le programme de traduction de cet ordinateur ne répond pas. Redémarrez-le (ou "
                             "redémarrez TASlation), puis appuyez sur Traduire."),
    "ollama.loaded": "Traducteur prêt.",
    "ollama.loading": "Préparation du traducteur...",
    "ollama.partly_on_gpu": "Seuls {percent} % du traducteur tiennent sur la carte graphique : la traduction sera lente. Fermez les autres programmes qui utilisent la carte graphique.",
    "translator.failed": "{detail}",
    "ocr.model_missing": ("La partie qui lit le japonais est absente. Double-cliquez sur install.cmd dans le dossier de TASlation. Les pages déjà traduites s'affichent toujours."),
    "ocr.error": "{detail}",
    "ocr.one_reader": "La lecture du japonais fonctionne en version de base. Double-cliquez sur install.cmd pour l'améliorer.",
    "layout.classical": "Le texte sur le dessin est recherché de façon basique. Double-cliquez sur install.cmd pour en trouver davantage.",
    "health.ollama_down": ("Le programme de traduction ne tourne pas, les nouvelles pages ne peuvent donc pas être traduites. TASlation essaie de le démarrer à la page suivante ; si cela persiste, redémarrez le PC. Les pages déjà traduites restent lisibles."),
    "health.ollama_not_installed": "Le programme de traduction n'est pas installé. Double-cliquez sur install.cmd dans le dossier de TASlation.",
    "health.ollama_no_answer": ("Le programme de traduction n'a pas démarré. Redémarrez le PC, puis rouvrez TASlation. Les pages déjà traduites restent lisibles."),
    "health.model_missing": ("Le modèle de traduction {model} n'est pas installé. Exécutez de nouveau install.cmd "
                             "pour l'installer."),
    "health.chosen_model_missing": ("Le modèle {model} choisi dans les réglages n'est pas installé dans Ollama. "
                                    "Exécutez dans un terminal : {command}"),
    "health.ocr_missing": ("La partie qui lit le japonais est absente. Double-cliquez sur install.cmd dans le dossier de TASlation. Les pages déjà traduites s'affichent toujours."),
    "health.other_model": ("{wanted} n'est pas installé dans Ollama ; traduction avec {used} en attendant. Exécutez "
                           "de nouveau install.cmd pour installer {wanted}."),
    "health.chosen_other_model": ("{wanted}, choisi dans les réglages, n'est pas installé dans Ollama ; traduction "
                                  "avec {used} en attendant. Pour installer {wanted}, exécutez dans un terminal : "
                                  "{command}"),
    "pipeline.no_text": "Pas de texte sur cette page.",
    "rename.unreadable": "{path} ne peut pas être lu. Sortez-le de {folder}, puis réessayez.",
    "rename.busy": "{path} ne peut pas être ouvert pour l'instant. Fermez le programme qui le retient, puis réessayez.",
    "rename.in_way": "{path} gêne. Sortez-le de {folder}, puis réessayez.",
    "rename.no_name": "Ce nom ne désigne aucun livre ; donnez au livre un nom à lui.",
    "rename.same_name": "Le livre s'appelle déjà {book}.",
    "store.protected": "Protégés : {files:fichier enregistré|fichiers enregistrés}. Désormais, seul cet utilisateur Windows peut les ouvrir, sur cet ordinateur.",
    "store.not_protected": "Pas encore protégés : {files:fichier enregistré|fichiers enregistrés}, qu'un autre programme utilise. TASlation réessaiera au prochain démarrage.",
    "store.not_here": "Cet utilisateur Windows ne peut pas ouvrir sur cet ordinateur {files:fichier enregistré|fichiers enregistrés} : enregistrés par un autre utilisateur Windows ou sur un autre ordinateur, ou endommagés. TASlation ne les écrase jamais : un tel livre repart de zéro, et son fichier est gardé à côté sous un nouveau nom. Pour amener ici les traductions d'un livre, exportez-les là où elles ont été enregistrées (Menu > Traductions enregistrées... > Exporter (chiffré)...) et importez ce fichier ici (Importer...).",
    "store.set_aside": "Cet utilisateur Windows ne peut pas ouvrir sur cet ordinateur un fichier enregistré de ce livre : il a été enregistré par un autre utilisateur Windows ou sur un autre ordinateur, ou il est endommagé. Il est gardé sous le nom {path}, et le livre repart de zéro ici. Pour amener ici ses traductions, exportez-les là où elles ont été enregistrées (Menu > Traductions enregistrées... > Exporter (chiffré)...) et importez ce fichier ici (Importer...).",
    # the translation model the target language chooses (translate/models.py, translate/plamo.py)
    "translator.model_missing": "Le modèle de traduction pour cette langue, {name}, n'est pas installé. Exécutez de nouveau install.cmd pour l'installer.",
    "translator.other_model": "Le modèle de traduction pour cette langue, {name}, n'est pas installé ; traduction avec {used} en attendant. Exécutez de nouveau install.cmd pour installer {name}.",
    "plamo.cannot_write": "Le modèle choisi dans les réglages ne peut pas traduire vers cette langue. Retirez ollama_model du fichier de réglages : TASlation choisira alors lui-même le bon modèle.",
}

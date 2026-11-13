"""Per-feature catalogs of the window's strings: a module per feature (``caches.py``, ``reading.py``, ...), each with

    TEXTS: dict[str, dict[str, str]] = {
        "The English string as the code passes it to _()": {"ja": "...", "es": "...", ..., "th": "..."},
    }

every language of the window but English (ja, es, pt, fr, de, it, nl, pl, ru, tr, id, vi, zh, zh-tw, ko, th), the
placeholders ({n}, {title}, ...) as in the English key. `taslation.i18n` finds the modules here with
`pkgutil.iter_modules` and adds their strings to its catalogs after the positional lists of `taslation.locales`.
"""

"""The editor's consistency pass: renderings replaced in the cached translations (`taslation glossary apply --rename`)."""
from __future__ import annotations

import json

from taslation.cache import CacheStore, CachedBubble, CachedPage
from taslation.cli import main
from helpers import store_json


def test_cache_rename_is_whole_word(tmp_path):
    cache = CacheStore(tmp_path).open("Book 1", "m")
    cache.add(CachedPage("a" * 80, 0.7, [CachedBubble((0.1, 0.1, 0.2, 0.2), "Piyo! Piyo's here, Noowa. Piyoko stays."),
                                          CachedBubble((0.3, 0.1, 0.4, 0.2), "Nothing here")], seq=0))
    assert cache.rename([("Piyo", "Pyo"), ("Noowa", "Nowa"), ("same", "same")]) == 1
    assert cache.pages[0].bubbles[0].text == "Pyo! Pyo's here, Nowa. Piyoko stays."
    assert cache.rename([("Piyo", "Pyo")]) == 0


def test_renames_given_apply_to_the_series_caches_with_a_backup(tmp_path, monkeypatch, capsys):
    from taslation import netguard

    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    try:
        from taslation.config import Settings

        s = Settings()
        cache = CacheStore(s.cache_dir).open("Series 1", "m")
        cache.add(CachedPage("a" * 80, 0.7, [CachedBubble((0.1, 0.1, 0.2, 0.2), "Noowa hears Piyo and Hja.")], seq=0))
        cache.save()
        assert main(["glossary", "apply", "Series"]) == 0
        assert "nothing to rename" in capsys.readouterr().out
        assert main(["glossary", "apply", "Series", "--rename", "Noowa=Nowa", "--rename", "Hja=Hya", "--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "Noowa -> Nowa" in out and "would change" in out
        assert "Noowa" in store_json(cache.path)["pages"][0]["bubbles"][0]["text"]
        assert main(["glossary", "apply", "Series", "--rename", "Noowa=Nowa", "--rename", "Hja=Hya"]) == 0
        text = store_json(cache.path)["pages"][0]["bubbles"][0]["text"]
        assert text == "Nowa hears Piyo and Hya."
        backups = list(cache.path.parent.glob(cache.path.stem + ".before-apply.*.json"))
        assert len(backups) == 1
        # the backup is not listed as a book of its own, and a second apply keeps the first backup untouched
        assert [b["file"] for b in CacheStore(s.cache_dir).list()] == [str(cache.path)]
        first = backups[0].read_bytes()
        assert main(["glossary", "apply", "Series", "--rename", "Hya=Hyahyo"]) == 0
        assert backups[0].read_bytes() == first
    finally:
        netguard.uninstall()

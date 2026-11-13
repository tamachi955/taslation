"""The legal notice: in every window language with a part per country, the reader's choices remembered, the
dialog that chooses country and language, and `taslation notice`."""
from __future__ import annotations

import io
import json

import pytest

from taslation import i18n, jurisdictions, netguard, notice
from taslation.cli import main
from taslation.i18n import CATALOGS, UI_LANGUAGES, load_ui_language, save_ui_language

# Article 47-6 as each language cites it; the others write "47-6"
ARTICLE_47_6 = {"ja": "第47条の6", "zh": "第 47 条之 6", "zh-tw": "第 47 條之 6", "ko": "제47조의6"}


def test_every_window_language_and_nothing_else():
    for table in (notice.TEXTS, notice.TITLES, notice.BUTTONS, notice.CHECKBOX, notice.COUNTRY_LABEL,
                  notice.LANGUAGE_LABEL, jurisdictions.OTHER_TEXTS, jurisdictions.OTHER_NAMES):
        assert set(table) == set(UI_LANGUAGES)
    for code in UI_LANGUAGES:
        text = notice.text(code)
        for needle in ("30", ARTICLE_47_6.get(code, "47-6"), "README"):
            assert needle in text, (code, needle)
        assert "Ollama" not in text and "taslation notice" not in text, code  # a reader's words: no program, no command
        assert notice.title(code) and notice.checkbox(code) and all(notice.buttons(code))
        assert notice.country_label(code) and notice.language_label(code) and notice.other_name(code)
    assert notice.text("xx") == notice.text("en") and notice.wraps_by_character("ja") and not notice.wraps_by_character("de")


def test_every_country_has_an_english_part_and_window_languages():
    assert jurisdictions.JURISDICTIONS and jurisdictions.OTHER not in jurisdictions.JURISDICTIONS
    for code, j in jurisdictions.JURISDICTIONS.items():
        assert code == j.code and len(code) == 2 and code.isupper() and j.label().startswith(j.name)
        assert j.sections.get("en") and set(j.sections) <= set(UI_LANGUAGES), code
        assert j.languages and set(j.languages) <= set(UI_LANGUAGES), code
        assert jurisdictions.default_language(code.lower()) == j.languages[0]
    names = [j.name for j in jurisdictions.sorted_jurisdictions()]
    assert names == sorted(names) and jurisdictions.default_language("other") is None


def test_full_text_is_the_general_part_around_the_country_part(monkeypatch):
    gb = jurisdictions.JURISDICTIONS["GB"]
    first, _, rest = notice.text("en").partition("\n\n")
    full = notice.full_text("en", "GB")
    assert full.startswith(first + "\n\n")  # the introduction first
    assert full.endswith("\n\n" + rest)  # then the rest of the general part
    body = gb.sections["en"][len("United Kingdom. "):]
    assert "\n\nUnited Kingdom\n" + body + "\n\n" in full  # under its heading, the name not said twice
    assert full.index(body) < full.index(rest)
    assert notice.country_heading("GB", "en") == "United Kingdom"
    assert notice.country_heading("JP", "en") == "Japan"
    assert notice.country_heading("JP", "ja") == "日本"
    assert notice.country_heading("GB", "de") == "Vereinigtes Königreich"
    ja = notice.full_text("ja", "jp")
    assert "\n\n日本\n" + jurisdictions.JURISDICTIONS["JP"].sections["ja"][len("日本。"):] in ja
    assert "日本。著作権" not in ja
    for country in (None, "", "XX", jurisdictions.OTHER):
        assert notice.country_heading(country, "fr") == notice.other_name("fr")
        assert notice.full_text("fr", country).count(jurisdictions.OTHER_TEXTS["fr"]) == 1
    us_de = jurisdictions.JURISDICTIONS["US"].sections["de"]
    assert notice.console_text("de", "US").count(us_de[len("Vereinigte Staaten. "):]) == 1


def test_every_country_part_begins_with_its_name():
    langs = ["en", "ja", "es", "pt", "fr", "de", "it", "nl", "pl", "ru", "tr", "id", "vi", "zh", "zh-tw", "ko", "th"]
    for j in jurisdictions.sorted_jurisdictions():
        for lang in langs:
            heading = notice.country_heading(j.code, lang)
            assert 0 < len(heading) <= 40 and ":" not in heading and "：" not in heading, (j.code, lang, heading)
            assert notice.full_text(lang, j.code).count("\n\n" + heading + "\n") == 1, (j.code, lang)


def test_country_is_remembered(tmp_path):
    assert notice.country(tmp_path) is None
    notice.save_country(tmp_path, "jp")
    assert notice.country(tmp_path) == "JP"
    notice.save_country(tmp_path, None)
    assert notice.country(tmp_path) == jurisdictions.OTHER
    notice.save_country(tmp_path, "XX")  # no longer listed: chosen again
    assert notice.country(tmp_path) is None
    notice.notice_path(tmp_path).write_text("not json", encoding="utf-8")
    assert notice.country(tmp_path) is None


def test_a_save_never_goes_through_a_fixed_temporary_name(tmp_path):
    """Two processes saving at once used to share notice.tmp, and a file of the reader's of that name was written
    over; the JSON looks as before."""
    stray = tmp_path / "notice.tmp"
    stray.write_text("a file of the reader's", encoding="utf-8")
    notice.save_country(tmp_path, "DE")
    notice.dismiss(tmp_path, "ja")
    assert stray.read_text(encoding="utf-8") == "a file of the reader's"
    raw = notice.notice_path(tmp_path).read_bytes()
    assert raw == json.dumps(json.loads(raw), ensure_ascii=False, indent=1).encode("utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["notice.json", "notice.tmp"]
    assert notice.country(tmp_path) == "DE" and notice.dismissed(tmp_path)


def test_default_country_is_a_listed_one_or_none():
    assert notice.default_country() in set(jurisdictions.JURISDICTIONS) | {None}


def test_dismiss_and_reset(tmp_path):
    assert not notice.dismissed(tmp_path)
    notice.save_country(tmp_path, "DE")
    notice.dismiss(tmp_path, "ja")
    assert notice.dismissed(tmp_path)
    data = json.loads(notice.notice_path(tmp_path).read_text(encoding="utf-8"))
    assert data["dismissed"] == notice.NOTICE_VERSION and data["language"] == "ja" and data["when"]
    assert notice.reset(tmp_path) and not notice.dismissed(tmp_path)
    assert notice.country(tmp_path) == "DE"  # the country stays
    assert not notice.reset(tmp_path)  # nothing left to reset


def test_print_once(tmp_path):
    out = io.StringIO()
    assert notice.print_once(tmp_path, "de", "DE", stream=out) is True
    assert notice.print_once(tmp_path, "de", "DE", stream=out) is False
    assert out.getvalue().count(notice.console_text("de", "DE")) == 1 and notice.printed(tmp_path)
    assert notice.full_text("de", "DE") in out.getvalue()  # the country part sits inside the general part
    assert jurisdictions.JURISDICTIONS["DE"].sections["de"][len("Deutschland. "):] in out.getvalue()
    assert not notice.dismissed(tmp_path)  # printing is remembered apart from the window's choice
    notice.reset(tmp_path)
    assert notice.print_once(tmp_path, "de", "other", stream=out) is True
    assert out.getvalue().count(jurisdictions.OTHER_TEXTS["de"]) == 1


def test_an_old_version_or_a_broken_file_shows_it_again(tmp_path, monkeypatch):
    from taslation.ui.app import notice_due

    path = notice.notice_path(tmp_path)
    assert notice_due(tmp_path)  # the first start
    path.write_text('{"dismissed": 0}', encoding="utf-8")
    assert not notice.dismissed(tmp_path)
    path.write_text(json.dumps({"dismissed": notice.NOTICE_VERSION - 1, "printed": notice.NOTICE_VERSION - 1}),
                    encoding="utf-8")
    assert not notice.dismissed(tmp_path) and not notice.printed(tmp_path)
    for broken in ("not json", '["dismissed"]', '{"dismissed": "soon"}'):
        path.write_text(broken, encoding="utf-8")
        assert not notice.dismissed(tmp_path)
    notice.dismiss(tmp_path, "en")
    assert notice_due(tmp_path)  # dismissed, but no country chosen yet: shown once more
    notice.save_country(tmp_path, "other")
    assert not notice_due(tmp_path)
    monkeypatch.setattr(notice, "NOTICE_VERSION", notice.NOTICE_VERSION + 1)  # a new notice
    assert not notice.dismissed(tmp_path) and notice_due(tmp_path)


def shown_text(d) -> str:
    """The text in the notice's box without the line breaks the dialog added to fit it (its "soft" ranges)."""
    ranges = [str(index) for index in d.text.tag_ranges("soft")]
    parts, start = [], "1.0"
    for first, last in zip(ranges[0::2], ranges[1::2]):
        parts.append(d.text.get(start, first))
        start = last
    parts.append(d.text.get(start, "end-1c"))
    return "".join(parts)


def _shows(d, lang: str, country: str) -> bool:
    # The dialog breaks the text into lines itself (the box does not wrap); without those breaks it is the notice.
    return (d.title() == notice.title(lang) and shown_text(d) == notice.full_text(lang, country)
            and str(d.text.cget("wrap")) == "none"
            and d.country_label.cget("text") == notice.country_label(lang)
            and d.language_label.cget("text") == notice.language_label(lang)
            and d.never_box.cget("text") == notice.checkbox(lang) and d.ok_btn.cget("text") == notice.buttons(lang)[0]
            and d.language_box.get() == UI_LANGUAGES[lang] and d.country == country)


def _choose(box, value: str) -> None:
    box.current(list(box.cget("values")).index(value))
    box.event_generate("<<ComboboxSelected>>")


def test_the_dialog_in_the_window(tmp_path, monkeypatch, hidden_root):
    from taslation.ui.app import NoticeDialog

    monkeypatch.setattr(notice, "default_country", lambda: None)  # this computer's region plays no part
    d = NoticeDialog(hidden_root, tmp_path, "ja")
    assert _shows(d, "ja", jurisdictions.OTHER) and str(d.text.cget("state")) == "disabled"
    assert d.country_box.get() == notice.other_name("ja") and d.leave_btn.cget("text") == notice.buttons("ja")[1]
    hidden_root.tk.eval(d.protocol("WM_DELETE_WINDOW"))  # the window's X counts as quit: nothing is saved
    assert not d.accepted and not notice.dismissed(tmp_path) and notice.country(tmp_path) is None
    assert load_ui_language(tmp_path) is None

    monkeypatch.setattr(notice, "default_country", lambda: "DE")  # the region setting suggests the country ...
    d = NoticeDialog(hidden_root, tmp_path, None)
    assert _shows(d, "de", "DE")  # ... and the country its language
    _choose(d.country_box, jurisdictions.JURISDICTIONS["JP"].label())
    assert _shows(d, "ja", "JP")  # a country brings its language along ...
    _choose(d.language_box, UI_LANGUAGES["en"])
    assert _shows(d, "en", "JP")
    _choose(d.country_box, jurisdictions.JURISDICTIONS["GB"].label())
    assert _shows(d, "en", "GB")  # ... until the language is chosen by hand
    _choose(d.country_box, notice.other_name("en"))
    assert _shows(d, "en", jurisdictions.OTHER)
    _choose(d.country_box, jurisdictions.JURISDICTIONS["FR"].label())
    d._acknowledge()  # the box not ticked: the app starts, the notice shows again next time
    assert d.accepted and not notice.dismissed(tmp_path) and i18n.current() == "en"
    assert notice.country(tmp_path) == "FR" and load_ui_language(tmp_path) == "en"

    d = NoticeDialog(hidden_root, tmp_path, "fr")  # the remembered country, not the region's
    assert _shows(d, "fr", "FR") and not d.never_var.get()
    d.never_var.set(True)
    d._acknowledge()
    assert d.accepted and notice.dismissed(tmp_path) and i18n.current() == "fr"
    d = NoticeDialog(hidden_root, tmp_path, "fr")
    assert d.never_var.get()  # the box shows what was chosen; clearing it shows the notice again
    d.never_var.set(False)
    d._acknowledge()
    assert not notice.dismissed(tmp_path) and notice.country(tmp_path) == "FR"


def test_the_dialog_keeps_its_size(tmp_path, monkeypatch, hidden_root):
    from taslation.ui.app import NoticeDialog

    monkeypatch.setattr(notice, "default_country", lambda: None)
    d = NoticeDialog(hidden_root, tmp_path, "en")
    d.withdraw()  # measured, never shown
    d.update_idletasks()
    size = (d.winfo_reqwidth(), d.winfo_reqheight())
    longest = max(jurisdictions.sorted_jurisdictions(), key=lambda j: len(j.label())).label()
    for lang in UI_LANGUAGES:
        _choose(d.language_box, UI_LANGUAGES[lang])
        for country in (longest, jurisdictions.JURISDICTIONS["JP"].label(), notice.other_name(lang)):
            _choose(d.country_box, country)
            d.update_idletasks()
            assert (d.winfo_reqwidth(), d.winfo_reqheight()) == size, (lang, country)
    assert int(d.text.cget("width")) == 88 and int(d.text.cget("height")) == 31


def test_the_dialog_from_the_language_menu(tmp_path, monkeypatch, hidden_root):
    from taslation.ui.app import NoticeDialog

    monkeypatch.setattr(notice, "default_country", lambda: "JP")
    d = NoticeDialog(hidden_root, tmp_path, "ko", startup=False)
    assert _shows(d, "ko", "JP") and d.leave_btn.cget("text") == CATALOGS["ko"]["Close"]
    assert str(d.wm_transient()) == str(hidden_root)  # modal over the window, which stays
    _choose(d.language_box, UI_LANGUAGES["en"])
    assert d.leave_btn.cget("text") == "Close"
    d._quit()  # Close: nothing changes
    assert not d.accepted and notice.country(tmp_path) is None and load_ui_language(tmp_path) is None


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.chdir(tmp_path)
    yield tmp_path / "state"
    netguard.uninstall()


def test_notice_command_prints_it_without_the_network(state, capsys):
    guard = netguard.install()
    blocked = len(guard.blocked)
    netguard.record_allowed(True)
    try:
        assert main(["notice"]) == 0
    finally:
        netguard.record_allowed(False)
    assert not guard.allowed and len(guard.blocked) == blocked
    out = capsys.readouterr().out
    assert notice.title("en") in out and notice.text("en").partition(chr(10) * 2)[0] in out
    country = notice.default_country() or jurisdictions.OTHER  # none chosen yet: the region setting's
    assert notice.full_text("en", country) in out
    assert not notice.printed(state) and not notice.dismissed(state)  # asked for, so not remembered


def test_notice_command_speaks_the_window_language(state, capsys):
    save_ui_language(state, "fr")
    assert main(["notice"]) == 0
    assert notice.title("fr") in capsys.readouterr().out
    assert main(["--ui-language", "ko", "notice"]) == 0
    assert notice.title("ko") in capsys.readouterr().out


def test_notice_command_country(state, capsys):
    assert main(["notice", "--country", "gb"]) == 0
    assert notice.full_text("en", "GB") in capsys.readouterr().out
    save_ui_language(state, "ja")
    assert main(["notice", "--country", "JP"]) == 0
    assert notice.full_text("ja", "JP") in capsys.readouterr().out
    for code in ("xx", "other", "Other"):  # not in the list: the "other" part, no failure
        assert main(["notice", "--country", code]) == 0
        assert notice.full_text("ja", jurisdictions.OTHER) in capsys.readouterr().out
    notice.save_country(state, "US")  # the one chosen in the window, unless --country says otherwise
    assert main(["notice"]) == 0
    assert notice.full_text("ja", "US") in capsys.readouterr().out
    assert main(["notice", "--country", "de"]) == 0
    assert notice.full_text("ja", "DE") in capsys.readouterr().out
    assert notice.country(state) == "US"  # --country is for this print only


def test_notice_reset(state, capsys):
    assert main(["notice", "--reset"]) == 0
    assert capsys.readouterr().out.strip() == "Nothing to reset."
    notice.save_country(state, "GB")
    notice.dismiss(state, "en")
    assert main(["notice", "--reset"]) == 0
    assert capsys.readouterr().out.strip() == "The notice will show again on the next start."
    assert not notice.dismissed(state) and notice.country(state) == "GB"


def test_reading_an_image_prints_it_once(state, tmp_path, capsys):
    notice.save_country(state, "GB")
    missing = str(tmp_path / "missing.png")
    with pytest.raises(SystemExit):
        main(["translate", missing, "--translator", "none"])
    captured = capsys.readouterr()
    assert notice.title("en") in captured.err and notice.title("en") not in captured.out and notice.printed(state)
    assert notice.full_text("en", "GB") in captured.err
    with pytest.raises(SystemExit):
        main(["translate", missing, "--translator", "none"])
    assert notice.title("en") not in capsys.readouterr().err

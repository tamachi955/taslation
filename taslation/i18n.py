"""Languages of the window itself (not of the translation).

The English strings in the code are the keys; ``tr(text)`` returns the text
in the chosen language and falls back to English for anything missing. The
choice is made on the first start, kept in ``~/.taslation/ui.json`` and can
be changed from the Language menu at any time. The command line stays
English.

The catalogs are the Japanese one here (``JA``), the positional lists of
`locales`, and then the modules of `locales.features`, one per feature
(`load_features`, `merge_features`).
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path
from types import ModuleType

from .atomic import write_atomic
from .locales import CATALOGS as _MORE
from .locales import KEYS as _KEYS
from .locales import NAMES as _MORE_NAMES
from .locales import features as _features

UI_LANGUAGES: dict[str, str] = {"en": "English", "ja": "日本語", **_MORE_NAMES}
DEFAULT = "en"
_current = DEFAULT

JA: dict[str, str] = {
    # toolbar
    "Viewer:": "ビューア:",
    "Book:": "書名:",
    "To:": "翻訳先:",
    "Translate (F5)": "翻訳 (F5)",
    "Read whole book...": "1冊まるごと読む...",
    "Stop (Esc)": "停止 (Esc)",
    "Set area...": "範囲設定...",
    "Clear area": "範囲解除",
    "Show original": "原文を表示",
    "Always on top": "常に手前に表示",
    "Saved translations...": "保存した翻訳...",
    "Reader": "読者",
    "Series sheet...": "シリーズ設定...",
    "Reading order": "読み順",
    "Finish order": "読み順を確定",
    "Skip page": "このページを除外",
    "Translate again": "訳し直す",
    "Book settings...": "この本の設定...",
    "Language": "言語",
    "OK": "OK",
    # status line
    "Starting...": "起動中...",
    "Window capture needs Windows; use `taslation translate IMAGE` on this OS.":
        "ウィンドウのキャプチャは Windows 専用です。この OS では `taslation translate 画像` を使ってください。",
    "Pick the viewer window first (open your e-book viewer, then choose it in the Viewer list).":
        "先にビューアのウィンドウを選んでください（電子書籍ビューアを開いてから「ビューア」の一覧で選びます）。",
    "Getting the Japanese reader ready (the first time takes a few seconds)...": "日本語の読み取り機能を準備しています（初回は数秒かかります）...",
    "\n\nPages already translated still show; new pages cannot be read.":
        "\n\n翻訳済みのページは表示できますが、新しいページは読めません。",
    "Ready. Turn the pages here with the page keys, or click the page. F5: translate this page now · F11: reading mode.":
        "準備完了。このウィンドウでページ送りのキーを押すか、ページをクリックしてめくります。F5: このページを今すぐ翻訳・F11: 読書モード",
    "Viewer: {title}": "ビューア: {title}",
    "Viewer: {error}": "ビューア: {error}",
    "Translating...": "翻訳中...",
    "Storing your changes...": "変更を保存中...",
    "Dropping the region...": "領域を削除中...",
    "Stopping the whole-book run...": "1冊まるごと読み取りを停止しています...",
    "Whole-book run starting...": "1冊まるごと読み取りを開始します...",
    "Whole-book mode: this page is not translated yet. Turn the pages at your own pace: TASlation reads each page you turn, and translates the book when you press Finished reading. Stop ends the run.":
        "1冊まとめて翻訳: このページは未翻訳です。ご自分のペースでページをめくってください。TASlation はめくられたページを読み取り、「読み終えた」を押すと本を翻訳します。「停止」で終えられます。",
    "Sent {key} to the viewer...": "ビューアに {key} を送信...",
    "The viewer did not change (end of book, or the key means nothing there).":
        "ビューアの表示が変わりません（巻末か、そのキーが効かない画面です）。",
    "Area cleared: TASlation looks for the page in the viewer's window by itself again (the whole window when it finds none).": "範囲を解除しました: TASlation がビューアのウィンドウ内のページを再び自動で探します（見つからなければウィンドウ全体を読みます）。",
    "Reading order cancelled.": "読み順の設定を取り消しました。",
    "Reading order: click the regions in the order they are read, then press Finish order (Esc cancels).":
        "読み順: 読む順番に領域をクリックし、「読み順を確定」を押してください（Esc で取り消し）。",
    "Reading order saved for {n} region(s). Translate again applies it.":
        "{n} 領域の読み順を保存しました。「訳し直す」で反映されます。",
    "Page marked as skipped: nothing on it is translated.": "このページを除外しました: 何も翻訳しません。",
    "Page no longer skipped.": "ページの除外を解除しました。",
    "Translate this page again? Its present translations are replaced.":
        "このページを訳し直しますか？ 今の訳文は置き換えられます。",
    "Translate a page first (the book needs a name).": "先にページを翻訳してください（書名が必要です）。",
    "Reader mode: keys and clicks on the page go to the viewer.": "読者モード: ページ上のキーとクリックはビューアに渡されます。",
    "Could not record the rectangle: give the book a name first (the Book field).":
        "矩形を記録できません: 先に書名を入力してください（「書名」欄）。",
    "Text rectangle added; reading and translating it...": "文字の矩形を追加しました。読み取って翻訳します...",
    "Could not keep the translation: give the book a name first (the Book field).":
        "訳文を保存できません: 先に書名を入力してください（「書名」欄）。",
    "Give the book a name first (the Book field).": "先に書名を入力してください（「書名」欄）。",
    # batch dialog
    "Read the whole book": "1冊まるごと読む",
    "Start": "開始",
    "Cancel": "キャンセル",
    "Close": "閉じる",
    "Save": "保存",
    # area dialog
    "Set area - drag over the page, then press Enter": "範囲設定 - ページの上をドラッグして Enter",
    "Drag the handles to resize the area, drag inside it to move it, or drag elsewhere to draw a new one. Keep only the page inside it: the browser's tabs and address bar would otherwise be read as part of the page. Enter = use it, Esc = cancel.":
        "ハンドルをドラッグすると範囲の大きさが変わり、内側をドラッグすると移動、外側をドラッグすると新しく描けます。範囲にはページだけを入れてください。ブラウザのタブやアドレスバーを含めると、ページの一部として読み取られます。Enter = 確定、Esc = 取り消し。",
    # edit region dialog
    "Edit region": "領域の編集",
    "Read as: ": "読み取り結果: ",
    "Speaker:": "話者:",
    "Kind:": "種別:",
    "Sentence continues in the next bubble": "文が次の吹き出しに続く",
    "Hint for the model (a pun, who is addressed):": "モデルへのヒント（だじゃれ、誰への言葉か）:",
    "Translation (what is drawn in the region):": "訳文（領域に描かれる文字）:",
    "Drop this region": "この領域を削除",
    # series sheet dialog
    "Series sheet - {series} [{language}]": "シリーズ設定 - {series} [{language}]",
    "Facts the model is told before translating: names and terms with their renderings, who the characters are and how they talk, and how the series should read. Never lines of the book.":
        "翻訳前にモデルへ伝える前提情報: 名前・用語とその表記、登場人物と話し方、作品の読み味。本文の台詞は入れません。",
    "File: {path}": "ファイル: {path}",
    "Terms": "用語",
    "Characters": "登場人物",
    "Style guide": "文体ガイド",
    "Term (as in the book)": "用語（原文表記）",
    "Rendering": "訳語・表記",
    "Note": "注記",
    "Term": "用語",
    "Add / update": "追加 / 更新",
    "Remove selected": "選択項目を削除",
    "A term and its rendering are needed.": "用語とその表記を入力してください。",
    "Name": "名前",
    "Name (as in the book)": "名前（原文表記）",
    "Gender": "性別",
    "Age": "年齢",
    "First person": "一人称",
    "Speech style": "話し方",
    "Role / relationships": "役割 / 関係",
    "Calls others (name=form; ...)": "他者の呼び方（名前=呼称; ...）",
    "Add / update character": "人物を追加 / 更新",
    "A character needs a name.": "人物には名前が必要です。",
    "Honorifics:": "敬称:",
    "How honorifics such as -san and -chan are carried over.":
        "「さん」「ちゃん」などの敬称の訳し方です。",
    "Tone:": "トーン:",
    "House rules, one per line (short policies, never lines of the book):":
        "ハウスルール（1 行に 1 つ。短い方針のみ、本文の台詞は不可）:",
    "Save style guide": "文体ガイドを保存",
    "Could not save the series sheet: {error}": "シリーズ設定を保存できません: {error}",
    # files written and read
    "All files": "すべてのファイル",
    "Could not write the file: {error}": "ファイルを書き込めません: {error}",
    "Could not import: {error}": "取り込めません: {error}",
    # book settings dialog
    "Book settings": "この本の設定",
    "(yours: {value})": "（自分の設定: {value}）",
    "Apply to this book": "この本に適用",
    "Clear all": "すべて消去",
    # caches dialog
    "Each file holds translated text and bubble positions, matched to each page by a short code made from its picture; no picture is kept, and no original text.":
        "各ファイルには訳文と吹き出しの位置が入っています。ページとの対応は、ページの絵から作った短い符号で取ります。絵は保存せず、原文も保存しません。",
    "Book": "書名",
    "Pages": "ページ",
    "Bubbles": "吹き出し",
    "Updated": "更新日時",
    "Delete selected translations": "選択した翻訳を削除",
    "Open folder": "フォルダを開く",
    "Delete the saved translations of {book}?": "{book} の保存した翻訳を削除しますか？",
    "Series sheet updated; changed in {n} translated line(s). New translations use it.": "シリーズ設定を更新しました。翻訳済みの {n} 行を変更しました。これからの翻訳にも使われます。",
    "You wrote \"{new}\" where the series sheet says \"{old}\". Use \"{new}\" from now on?": "シリーズ設定では「{old}」ですが「{new}」と書きました。以後「{new}」にしますか？",
    "Lettering font:": "描画フォント:",
    "(a font installed on this computer, by family name, e.g. Comic Neue; empty = automatic)": "（このパソコンにインストールされているフォントのファミリー名。例: Comic Neue。空欄 = 自動）",
    "Installed here: {file}": "この PC にあります: {file}",
    "Not installed on this computer: the automatic font is used instead.": "この PC には入っていません。代わりに自動選択のフォントを使います。",
    " - the suggested font \"{font}\" is not installed": " - 提案フォント「{font}」が未インストール",
    "Lettering by kind (text marked as thought, shout, narration, handwritten or sound effect; stressed words marked *like this* are set in bold italic):": "種類ごとの書体（心の声・叫び・ナレーション・手書き・効果音として印を付けた文字。*このように* 印を付けた語は太字斜体になります）:",
    "italic": "斜体",
    "bold": "太字",
    "(font family per kind; empty = the lettering font above)": "（種別ごとのフォントファミリー。空欄 = 上の描画フォント）",
    "Note to the reader (a pun, a reference the translation cannot carry):": "読者への訳注（訳文に乗せきれない言葉遊びや文化参照）:",
    "Notes for the reader: ": "読者への訳注: ",
    "Review...": "レビュー...",
    "Review this page": "このページのレビュー",
    "Regions flagged for a look, untranslated, or with a note for the reader. Double-click one to edit it.": "要確認の印が付いた領域、未訳の領域、読者への訳注がある領域です。ダブルクリックで編集します。",
    "Region": "領域",
    "Why": "理由",
    "Translation": "訳文",
    "Edit...": "編集...",
    "untranslated": "未訳",
    "note for the reader": "読者への訳注",
    "Ask again": "もう一度訳す",
    "Asking the model...": "モデルに問い合わせ中...",
    "Nothing to undo.": "取り消すものはありません。",
    "Edit taken back.": "編集を取り消しました。",
    "The model gave no other translation.": "モデルから別の訳は得られませんでした。",
    "Legal notice...": "法的な注意事項...",
    "Export (encrypted)...": "暗号化して書き出す...",
    "Import...": "取り込む...",
    "Passphrase:": "パスフレーズ:",
    "Repeat the passphrase:": "パスフレーズ（確認）:",
    "Wrong passphrase or damaged file.": "パスフレーズが違うか、ファイルが壊れています。",
    "Exported {book} to {path}": "{book} を {path} に書き出しました",
    "Imported {pages} page(s) into {book}": "{book} に {pages} ページを取り込みました",
    "Typesetting... ({seconds} s)": "写植中...（{seconds} 秒）",
    "reading {n} line(s)": "{n} 行を読み取り中",
    "finding the bubbles": "吹き出しを検出中",
    "asking the model": "モデルに問い合わせ中",
    "Translating... ({seconds} s)": "翻訳中...（{seconds} 秒）",
    "Translating... {stage} ({seconds} s)": "翻訳中... {stage}（{seconds} 秒）",
    "Reading mode": "読書モード",
    "View": "表示",
    "TASlation blocked {blocked} attempt(s) to reach the internet. Nothing left this computer; you need do nothing.":
        "TASlation はインターネットへの接続の試みを {blocked} 回止めました。このパソコンから外には何も出ていません。何もする必要はありません。",
    "Offline guard: off.": "オフライン保護: 無効。",
    "Offline guard: on. Only this computer's port {port} (Ollama) can be reached; {blocked} other connection attempt(s) were blocked.":
        "オフライン保護: 有効。接続できるのはこのパソコンのポート {port}（Ollama）だけで、他への接続の試み {blocked} 件を遮断しました。",
    "TASlation - translating...": "TASlation - 翻訳中...",
    "This viewer cannot be read behind the reading window; press Esc": "このビューアは読書モードの画面の裏では読み取れません。Esc を押してください",
    "Reading mode translates page by page; the whole-book scan waits until you leave it (Esc).":
        "読書モードでは1ページずつ翻訳します。1冊まるごと読み取りは読書モードを抜けるまで待ちます（Esc）。",
    "Reading mode waits for the whole-book run to finish (Stop ends it).": "読書モードは1冊まるごと読み取りが終わるまで待ちます（「停止」で中断できます）。",
    "Reading mode: page keys turn the viewer's pages; F11 or Esc leaves it.":
        "読書モード: ページ送りキーでビューアのページをめくります。F11 か Esc で戻ります。",
    "{done} of {total} line(s) done": "{total} 行中 {done} 行完了",
    "getting the Japanese reader ready": "日本語の読み取り機能を準備中",
    "Translating... {stage}": "翻訳中... {stage}",
    "Typesetting...": "写植中...",
    # added with the flowing toolbar, the menus, the empty-window hint and the import messages
    "Page":
        "ページ",
    "Tools":
        "ツール",
    "Translator":
        "翻訳者",
    "Open your book in its viewer (a desktop viewer, or a browser-based viewer in a browser window of its own). TASlation finds it by itself - or pick its window in the Viewer list above.":
        "本をビューアで開いてください（デスクトップのビューア、またはブラウザのビューアを専用のウィンドウで）。TASlation が自動で見つけます。見つからないときは上の「ビューア」一覧から選んでください。",
    "found":
        "検出済み",
    "no text read":
        "文字を読み取れず",
    "not Japanese":
        "日本語ではない",
    "not lettering":
        "文字ではない",
    "no longer matches this page":
        "このページと合わなくなりました",
    "Japanese reader missing":
        "日本語の読み取り機能がありません",
    "dropped":
        "削除済み",
    "The passphrase holds a broken or control character; type it again.":
        "パスフレーズに壊れた文字か制御文字が含まれています。入力し直してください。",
    "This file was written by a newer version of TASlation; update TASlation to import it.":
        "このファイルは新しいバージョンの TASlation で書き出されています。取り込むには TASlation を更新してください。",
    "The file is larger than TASlation reads; nothing was imported.":
        "ファイルが TASlation の読み込める大きさを超えています。何も取り込んでいません。",
    "Not imported: the file for this book already holds another book's translations (their names give the same file name). Move that file out of its folder, then import again.":
        "インポートしませんでした: この本のファイルには別の本の訳文がすでに入っています（2つの書名から同じファイル名ができます）。そのファイルを今のフォルダーの外に移してから、もう一度インポートしてください。",
    "Could not import: the file is damaged or is not a TASlation backup.":
        "インポートできません: ファイルが壊れているか、TASlation のバックアップではありません。",
    "has a translation":
        "訳文あり",
}

FEATURE_LANGUAGES = tuple(code for code in UI_LANGUAGES if code != DEFAULT)  # what a feature module translates into


def load_features(package: ModuleType = _features) -> dict[str, dict[str, dict[str, str]]]:
    """The strings of every module of *package* (`locales.features`), found with pkgutil.iter_modules, by module
    name in name order: each module's ``TEXTS`` (English key -> {language code: translation})."""
    found: dict[str, dict[str, dict[str, str]]] = {}
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        found[info.name] = dict(getattr(module, "TEXTS", {}))
    return found


def merge_features(catalogs: dict[str, dict[str, str]], features: dict[str, dict[str, dict[str, str]]]) -> list[str]:
    """Add the feature modules' strings to *catalogs*, after the positional lists. A key that the lists or an earlier
    feature module have already keeps its first translations, and the clash is returned (the tests report it)."""
    owner = {key: "the positional lists" for key in (*_KEYS, *JA)}
    clashes: list[str] = []
    for name, texts in features.items():
        for key, translations in texts.items():
            if key in owner:
                clashes.append(f"{key!r} is in {owner[key]} and in features/{name}.py")
                continue
            owner[key] = f"features/{name}.py"
            for code, text in translations.items():
                if code in catalogs and code != DEFAULT:
                    catalogs[code][key] = text
    return clashes


FEATURES = load_features()
# copies: JA and the lists' catalogs stay as they are, the features are added to these
CATALOGS: dict[str, dict[str, str]] = {"en": {}, "ja": dict(JA), **{code: dict(texts) for code, texts in _MORE.items()}}
FEATURE_CLASHES = merge_features(CATALOGS, FEATURES)


def set_language(code: str) -> str:
    """Select the window language; unknown codes fall back to English."""
    global _current
    _current = code if code in UI_LANGUAGES else DEFAULT
    return _current


def current() -> str:
    return _current


def tr(text: str) -> str:
    """The text in the chosen language (English, the key itself, when there is no translation)."""
    return CATALOGS.get(_current, {}).get(text, text)


_ = tr


def ui_settings_path(state_dir: Path) -> Path:
    return Path(state_dir) / "ui.json"


def _ui_settings(state_dir: Path) -> dict:
    """What ui.json holds ({} when it is missing or unreadable)."""
    try:
        with open(ui_settings_path(state_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_ui_settings(state_dir: Path, data: dict) -> None:
    path = ui_settings_path(state_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
    except OSError:
        pass


def load_ui_language(state_dir: Path) -> str | None:
    """The remembered choice, or None on the first start."""
    code = _ui_settings(state_dir).get("language")
    return code if code in UI_LANGUAGES else None


def save_ui_language(state_dir: Path, code: str) -> None:
    """Remember the window's language (written all or nothing, like every file TASlation keeps; the other choices
    in the file stay)."""
    data = _ui_settings(state_dir)
    data["language"] = code
    _save_ui_settings(state_dir, data)


def load_ui_flag(state_dir: Path, name: str) -> bool:
    """A yes-or-no choice kept in ui.json under *name* (False when it is missing or not a boolean)."""
    return _ui_settings(state_dir).get(name) is True


def save_ui_flag(state_dir: Path, name: str, value: bool = True) -> None:
    """Remember a yes-or-no choice in ui.json; the language and the other choices stay."""
    data = _ui_settings(state_dir)
    data[name] = bool(value)
    _save_ui_settings(state_dir, data)


def _table(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}


def load_ui_table(state_dir: Path, name: str) -> dict[str, str]:
    """A table the window keeps in ui.json under *name* (short strings by short strings: the name last given to a
    book in each viewer), oldest entry first; {} when there is none."""
    return _table(_ui_settings(state_dir).get(name))


def save_ui_entry(state_dir: Path, name: str, key: str, value: str | None, keep: int = 0) -> None:
    """Remember *value* under *key* in the table *name* of ui.json (`load_ui_table`) as its latest entry (None
    forgets it); with *keep*, only the latest *keep* entries stay. The language and the other choices stay."""
    data = _ui_settings(state_dir)
    table = _table(data.get(name))
    table.pop(key, None)
    if value is not None:
        table[key] = value
    while keep > 0 and len(table) > keep:
        table.pop(next(iter(table)))
    if table:
        data[name] = table
    else:
        data.pop(name, None)
    _save_ui_settings(state_dir, data)


__all__ = ["UI_LANGUAGES", "DEFAULT", "CATALOGS", "tr", "_", "set_language", "current", "load_ui_language",
           "save_ui_language", "load_ui_flag", "save_ui_flag", "load_ui_table", "save_ui_entry",
           "ui_settings_path", "FEATURES", "FEATURE_CLASHES", "FEATURE_LANGUAGES", "load_features", "merge_features"]

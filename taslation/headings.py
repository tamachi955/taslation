"""The headings of a book's parts: chapter labels and the words of its contents, wherever they stand.

A chapter's label (第3話, 第十二章, 其ノ弐, 最終話, 番外編, ...) and a contents page's word (目次) are lettering to
translate, set across or down, on a band, beside a page number or alone. Their shape is the shape of print (a short
line set across, digits beside the kanji, no kana and no mark of speech), and the judging rules that leave print, a
credit and a drawing's reading untranslated would leave them too (`taslation.pipeline.Pipeline._judge`). A reading
that is one of these is never judged by its shape (`heading`), and a block that holds several of them is a contents
list, read row by row (`labels_in`). The patterns are here, in one place.

What counts (NFKC first, so full-width digits are digits; spaces, and a rule, a bracket or an arrow before it, are no
part of it):

* a counter: 第 and a number (Arabic digits, 3.5 too, or kanji numerals, old forms 壱弐参 and 拾 too) and one of
  `COUNTERS` (第3話, 第十二章, 第2部, 第一夜, 第5幕, 第1楽章, 第4巻); the number and the counter alone with Arabic
  digits (3話, 12章); その, 其の or 其ノ and a number (その1, 其ノ弐); エピソード and a number;
* a word of `WORDS`: the contents (目次, もくじ), the prologue and the epilogue (プロローグ, 序章, 終章, ...), the last
  chapter (最終話, 最終回, ...), an extra or special one (番外編, 特別編, 外伝, 読み切り, 描き下ろし, おまけ, 総集編,
  ...), a part (前編, 中編, 後編, 上巻, 下巻, 完結編), an interlude (幕間, 間章, 閑話), the words round the story
  (あとがき, まえがき, はじめに, おわりに, 登場人物, 人物紹介, 次巻予告).

A heading may run on into its title on the same line (第3話 雨の日, 目次: the label first); `heading` asks for the label
at the start of the reading, `labels_in` counts the labels anywhere in it.

What stays print, whatever it begins with (`PRINTED`): a reading with a price or a currency, a shop's or a sale's word
(購入, 無料, 試し読み, ポイント, 価格, 予約, 発売, 配信), an address (http, www, .com, .jp, @), a year of four digits, an
issue (12号, 月号) or the words of the record of where a chapter first ran (掲載, 初出, 収録): a viewer's panel, an
advertisement, a colophon's block and its list of first printings (第1話 月刊... 2019年5月号) are left as they are, as
before. `taslation.pipeline.looks_like_print` asks the same.

Left out, and why: the end marks 完, 終 and おわり (one or two characters a drawing is read as easily, and nothing to
lose when one is left as it is); 初出 and 初出一覧 (the colophon's, which stays untranslated); 上, 中 and 下 alone
(too common as single kanji); 解説 (a common word as much as an essay's heading); counters a chapter is seldom
numbered by (限, 試合, 日目: a school period, a match, a day are words of dialogue as often); labels in Latin letters
(Chapter, Episode, Vol., Act, CONTENTS: not Japanese, left as they are) and page numbers (digits alone)."""

from __future__ import annotations

import re
import unicodedata

# 第 and a number and one of these is a chapter's (or a volume's, a part's, a night's, ...) label
COUNTERS = ("楽章", "話", "章", "巻", "部", "幕", "夜", "回", "節", "編", "篇", "集", "場", "羽", "譚")
WORDS = (
    "目次", "もくじ",
    "プロローグ", "エピローグ", "序章", "終章", "序幕", "終幕", "序話", "終話", "前日譚", "後日譚", "前日談", "後日談",
    "最終話", "最終回", "最終章", "最終巻", "最終幕", "最終夜",
    "番外編", "番外篇", "特別編", "特別篇", "外伝", "総集編", "総集篇", "特別読切", "特別読み切り", "読切", "読み切り",
    "描き下ろし", "描きおろし", "書き下ろし", "書きおろし", "巻末おまけ", "おまけ",
    "前編", "中編", "後編", "前篇", "中篇", "後篇", "上巻", "中巻", "下巻", "完結編", "完結篇",
    "幕間", "間章", "閑話", "断章", "インタールード", "インターミッション",
    "あとがき", "後書き", "まえがき", "前書き", "はじめに", "おわりに",
    "登場人物", "人物紹介", "キャラクター紹介", "次巻予告",
)
_NUMBER = r"(?:[0-9]+(?:\.[0-9]+)?|[〇零一二三四五六七八九十百千壱弐参肆伍陸漆捌玖拾]+)"
_COUNTER = "(?:" + "|".join(COUNTERS) + ")"
_LABEL = re.compile(
    "(?:第" + _NUMBER + _COUNTER + "|[0-9]+(?:\\.[0-9]+)?" + _COUNTER + "|(?:その|其の|其ノ)" + _NUMBER
    + "|エピソード" + _NUMBER + "|" + "|".join(sorted(WORDS, key=len, reverse=True)) + ")")
# what may stand before a label without being part of it: rules and dashes, dots, brackets, quotes, arrows, marks
_LEAD = re.compile(r"^[\-‐-―ー〜~・･.:|()\[\]「」『』【】〈〉《》〔〕<>※*←→◆◇■□●○▲△▼▽☆★♪♡♥\"']+")
# print, whatever else is in the reading (NFKC): a price, a shop's or a sale's word, an address, a year, an issue, the
# record of a first printing
PRINTED = re.compile(r"[円¥$€£]|税|購入|無料|試し読み|ポイント|価格|予約|発売|配信|http|www|\.com|\.jp|@"
                     r"|[0-9]{4}|月号|[0-9]+号|掲載|初出|収録", re.IGNORECASE)


def _plain(text: str) -> str:
    """*text* NFKC-normalised (full-width digits and letters half-width, the full-width space a space), without its
    spaces."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def printed(text: str) -> bool:
    """Whether a reading holds what only print holds (`PRINTED`: a price, a shop's word, an address, a year, ...)."""
    return bool(PRINTED.search(_plain(text)))


def heading(text: str) -> bool:
    """Whether a reading is a heading: it begins with a chapter's label or a word of the contents (see the module),
    after any rule, dot, bracket or arrow before it, its title may follow on; one that holds what only print holds is
    none (`printed`)."""
    plain = _plain(text)
    lead = _LEAD.sub("", plain)
    if lead[:1] == "一" and _LABEL.match(lead[1:]):
        lead = lead[1:]  # (a contents list's rule before the label, read as the kanji it looks like)
    return bool(_LABEL.match(lead)) and not PRINTED.search(plain)


def labels_in(text: str) -> int:
    """How many chapter labels and contents words a reading holds, anywhere in it (a contents list read as one block
    holds one a row)."""
    return len(_LABEL.findall(_plain(text)))


__all__ = ["COUNTERS", "PRINTED", "WORDS", "heading", "labels_in", "printed"]

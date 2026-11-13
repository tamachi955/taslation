from __future__ import annotations

import sys

import numpy as np
import pytest
from PIL import Image

from taslation.pipeline import is_real_translation
from taslation.regions import TextRegion
from taslation.render import display_form, letter_text, find_font, fit_text, load_font, script_of, wrap_lines

SAMPLES = {
    "lgc": "Hello there, how are you?",
    "sc": "你好，今天天气真不错。",
    "kr": "안녕하세요, 오늘 날씨 좋네요.",
    "jp": "こんにちは、いい天気ですね。",
    "thai": "สวัสดี วันนี้อากาศดีจัง",
    "arabic": "مرحباً، الطقس جميل اليوم",
    "hebrew": "שלום, מזג האוויר יפה היום",
    "devanagari": "नमस्ते, आज मौसम अच्छा है",
}


@pytest.mark.parametrize("script,text", SAMPLES.items())
def test_script_detection(script, text):
    assert script_of(text) == script


def test_han_resolution_uses_language_hint_and_kana():
    assert script_of("今天", "Chinese (Traditional)") == "tc"
    assert script_of("今天", "Chinese (Simplified)") == "sc"
    assert script_of("今日は", "Chinese (Simplified)") == "jp"
    assert script_of("Привет, как дела?") == "lgc"
    assert script_of("Xin chào, bạn khỏe không?") == "lgc"


@pytest.mark.parametrize("script,text", SAMPLES.items())
def test_a_font_is_found_for_every_script(script, text, tmp_path):
    spec = find_font("", tmp_path, text)
    if sys.platform == "win32":
        assert spec.path, f"no font for {script}"
    font = load_font(spec.path, 20, spec.bold_variation)
    assert font.getlength(text) > 0


def test_cjk_and_thai_wrap_between_characters():
    spec = find_font("", None, SAMPLES["sc"])
    font = load_font(spec.path, 20, spec.bold_variation)
    lines = wrap_lines(SAMPLES["sc"], font, 80)
    assert len(lines) >= 2
    assert all(font.getlength(ln) <= 80 + 20 for ln in lines)  # a closing mark may hang
    assert not any(ln[0] in "，。" for ln in lines)
    spec = find_font("", None, SAMPLES["thai"])
    font = load_font(spec.path, 20, spec.bold_variation)
    assert len(wrap_lines(SAMPLES["thai"], font, 70)) >= 2


def test_rtl_display_keeps_numbers_and_mirrors_brackets():
    shown = display_form("שלום (123) עולם", "hebrew")
    assert shown.startswith("םלוע") and shown.endswith("םולש")
    assert "(123)" in shown  # digits keep their order; the brackets are mirrored so they look right
    assert display_form("plain", "lgc") == "plain"
    arabic = display_form(SAMPLES["arabic"], "arabic")
    assert len(arabic) >= len(SAMPLES["arabic"]) - 4  # reshaped presentation forms


def test_draw_every_script_into_a_bubble(tmp_path):
    for script, text in SAMPLES.items():
        img = Image.new("RGB", (300, 260), (255, 255, 255))
        mask = np.full((200, 240), 255, np.uint8)
        region = TextRegion(30, 30, 270, 230, mask, (30, 30, 270, 230))
        spec = find_font("", tmp_path, text)
        size = letter_text(img, region, text, spec.path, 9, 60, bold_variation=spec.bold_variation).size
        assert size >= 9, script
        assert np.asarray(img)[30:230, 30:270].min() < 128, f"nothing drawn for {script}"


def test_translation_check_accepts_chinese_but_not_kana():
    assert is_real_translation("大丈夫だよ", "没事的", "Chinese (Simplified)")
    assert is_real_translation("こんにちは", "안녕하세요", "Korean")
    assert not is_real_translation("大丈夫だよ", "大丈夫だよ", "Chinese (Simplified)")
    assert not is_real_translation("こんにちは", "こんにちは (hola)", "Spanish")
    assert is_real_translation("今日", "今天", "Chinese (Simplified)")


def test_fit_text_handles_long_cjk_without_spaces():
    text = "这是一个非常非常长的句子用来测试自动换行和字号调整功能是否正常工作"
    spec = find_font("", None, text)
    font, lines, size = fit_text(text, spec.path, 120, 160, 9, 60, bold_variation=spec.bold_variation)
    assert len(lines) >= 3 and size >= 9
    assert all(font.getlength(ln) <= 120 + size for ln in lines)

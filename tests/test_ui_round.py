"""What a run through the window as a reader found: the lines it showed were not what had happened."""

from types import SimpleNamespace

from PIL import Image

from taslation.messages import Message
from taslation.pipeline import summary
from taslation.ui.progress import busy_line, progress_line


def page(*statuses):
    return SimpleNamespace(fingerprints=["f"], translated=[], error="",
                           regions=[SimpleNamespace(status=s) for s in statuses])


def test_a_page_nothing_can_read_does_not_say_it_has_no_text():
    assert summary(page("ocr-unavailable")).code == "ocr.model_missing"
    assert summary(page("ocr-empty")).code == "pipeline.no_text"
    assert summary(page()).code == "pipeline.no_text"


def test_the_reading_pass_of_a_run_is_not_called_translating():
    reading = Message("pipeline.stage_reading", done=2, total=7)
    assert "Translating" in busy_line(reading, 3)
    assert "Translating" not in busy_line(reading, 3, reading=True) and busy_line(reading, 3, reading=True)
    assert "Translating" in progress_line(reading)
    assert "Translating" not in progress_line(reading, True) and progress_line(reading, True)


def test_the_preview_window_has_the_applications_icon(monkeypatch):
    from taslation.ui import preview

    given = []
    monkeypatch.setattr(preview, "apply_icon", lambda root: given.append("default"))
    monkeypatch.setattr(preview, "give_icons", lambda root: given.append("sizes"))
    monkeypatch.setattr(preview.tk.Tk, "mainloop", lambda self, n=0: self.destroy())
    preview.show_preview(Image.new("RGB", (40, 40)))
    assert given == ["default", "sizes"]

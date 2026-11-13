"""A stand-in e-book viewer for testing: shows the synthetic test pages in a window.

Left arrow = next page, Right arrow = previous page (right-to-left book), like
most Japanese e-book viewers. Used to exercise window capture, page turning and
batch reading end to end without any real book.

    python tools/fake_viewer.py [--title "Fake Viewer - Test Book"]
"""

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


class Viewer(tk.Tk):
    def __init__(self, pages: list[Image.Image], title: str):
        super().__init__()
        self.title(title)
        self.geometry("900x1100+40+40")
        self.configure(bg="#2b2b2b")
        self.pages = pages
        self.index = 0
        self.canvas = tk.Canvas(self, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._photo: ImageTk.PhotoImage | None = None
        self.bind("<Left>", lambda _e: self.show(self.index + 1))
        self.bind("<Right>", lambda _e: self.show(self.index - 1))
        self.bind("<Configure>", lambda _e: self.show(self.index))
        self.after(50, lambda: self.show(0))

    def show(self, index: int) -> None:
        self.index = max(0, min(len(self.pages) - 1, index))
        page = self.pages[self.index]
        w, h = max(1, self.canvas.winfo_width() - 40), max(1, self.canvas.winfo_height() - 40)
        scale = min(w / page.width, h / page.height)
        shown = page.resize((max(1, int(page.width * scale)), max(1, int(page.height * scale))), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(shown)
        self.canvas.delete("all")
        self.canvas.create_image(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2, image=self._photo)
        self.canvas.create_text(10, 10, anchor="nw", fill="#888888", text=f"page {self.index + 1}/{len(self.pages)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Fake Viewer - Test Book")
    args = ap.parse_args()
    p1 = Image.open(FIXTURES / "sample_page.png").convert("RGB")
    p2 = Image.open(FIXTURES / "sample_page2.png").convert("RGB")
    pages = [p1, p2, p1.transpose(Image.FLIP_LEFT_RIGHT)]
    Viewer(pages, args.title).mainloop()


if __name__ == "__main__":
    main()

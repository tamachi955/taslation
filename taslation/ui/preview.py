"""The canvas that shows a page, and a minimal image preview window (used by the CLI). Nothing is written to disk.

Text on the canvas (and in the legal notice) is broken into lines by `wrap.wrap_line`: Tk breaks lines only at
spaces, which leaves a Japanese or Chinese sentence in one piece and splits "TASlation" where it meets one."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

from PIL import Image, ImageTk

from . import area
from .layout import apply_icon, give_icons, set_app_id
from .wrap import is_cjk, wrap_line, wrap_text  # noqa: F401 - importable from here as before

BADGE_FONT = ("TkDefaultFont", 12, "bold")  # the busy badge's line
LABEL_FONT = ("TkDefaultFont", 11, "bold")  # translator mode's labels on the regions
NOTE_FONT = ("TkDefaultFont", 10)
MESSAGE_FONT = ("TkDefaultFont", 14)
HINT_FONT = ("TkDefaultFont", 13)
DARK = "#202020"  # the badge's and the labels' boxes: white text on it reads over a white page and a black one
BADGE_EDGE = "#6a6a6a"  # the badge's outline, so that it shows on the dark canvas around the page as well
HANDLE_FILL, HANDLE_EDGE = "#ffd400", "#202020"  # a handle: yellow with a dark edge, seen on white and on dark
# Translator mode's lines over the page are two-tone: a dark stroke EDGE_EXTRA px wider runs under the coloured one,
# so that the yellow frame (1.4:1 on white alone) and the blue of a new region (2.6:1) show on a white page, and the
# colour itself on a black one. The dark strokes are tagged "edge" beside the item's own tags.
EDGE = "#202020"
EDGE_EXTRA = 2
HANDLE_EDGE_WIDTH = 2  # a handle's dark edge, in pixels
# translator mode's reading-order badges: each region's place in the page's reading order, small, white on dark
BADGE_TAG = "order-badge"
ORDER_FONT = ("TkDefaultFont", 9, "bold")
ORDER_EDGE = "#c8c8c8"  # the badge's outline: light, so that it shows on the dark canvas and tells it from a label


def rounded_box(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, radius: float, **options) -> int:
    """A rectangle with rounded corners on *canvas* (a smoothed polygon: Tk has no such item)."""
    r = max(0.0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    points = (x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y0 + r, x1, y1 - r, x1, y1 - r,
              x1, y1, x1 - r, y1, x1 - r, y1, x0 + r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y1 - r, x0, y0 + r,
              x0, y0 + r, x0, y0)
    return canvas.create_polygon(points, smooth=True, **options)


class ImageCanvas(tk.Canvas):
    """Canvas that shows one PIL image scaled to fit, re-fitting on resize (*inset* pixels clear of its edges, for
    handles drawn on the picture's edges). Over the picture it can show outlined boxes (a page filling in), a busy
    badge with a turning spinner in the top right corner, a band across its middle in the badge's style, and a short
    note at the bottom; a message can take the picture's place, and with no picture a hint says what to do."""

    SPIN_MS = 100  # the spinner turns about ten times a second

    def __init__(self, master: tk.Misc, **kwargs):
        super().__init__(master, highlightthickness=0, **kwargs)
        self._image: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._shown: tuple[float, float, float, float] | None = None  # where the picture is drawn (canvas pixels)
        self._job: str | None = None
        self._note_job: str | None = None
        self._spin_job: str | None = None
        self._angle = 90
        self.scale = 1.0
        self.offset: tuple[float, float] = (0, 0)
        self.overlay: list[tuple[tuple[int, int, int, int], str, str]] = []  # (box in image pixels, colour, label)
        self.edged_tags: set[str] = {"chosen"}  # the tags `draw_frame` and the like draw two-tone (the selection)
        self.outlines: list[tuple[tuple[int, int, int, int], str, bool]] = []  # (box in image pixels, colour, dashed)
        self.enlarge = False  # a picture smaller than the canvas is enlarged too (the reading window)
        self.crop: tuple[int, int, int, int] | None = None  # the part of the image shown (image pixels); None = all
        # with no crop: a frame whose ground round the page is plain is drawn as the page alone (`area.page_bounds`),
        # the boxes found joined while the frames keep their size, so that the page stays put from page to page
        self.trim = True
        self._trims: list[tuple[Image.Image, tuple[int, int, int, int] | None]] = []  # (image, its page) lately
        self._trim_joined: tuple[tuple[int, int], tuple[int, int, int, int] | None] = ((0, 0), None)
        self.inset = 0  # canvas pixels kept clear around the picture
        self.message = ""  # shown in the middle instead of the picture
        self.hint = ""  # shown in the middle while there is no picture and no message
        self.note = ""  # a short line at the bottom, over the picture
        self.banner = ""  # a band over the middle of the picture, in the busy badge's style (what the reader must do)
        self.band: Callable[[], str] | None = None  # the busy badge's line, asked for at every turn of the spinner
        self.badge = False  # the busy badge is on show
        self.on_redraw: Callable[[], None] | None = None  # draws more over the picture after every redraw
        self.bind("<Configure>", self._on_configure)

    def set_image(self, image: Image.Image | None) -> None:
        self._image = image
        self._redraw()

    def from_image_coords(self, x: float, y: float) -> tuple[int, int]:
        return (int(self.offset[0] + x * self.scale), int(self.offset[1] + y * self.scale))

    def shown_box(self) -> tuple[int, int, int, int]:
        """The part of the image on show, in image pixels: the crop, or all of it."""
        if self._image is None:
            return (0, 0, 0, 0)
        whole = (0, 0, self._image.width, self._image.height)
        if self.crop is None:
            trimmed = self._trimmed(self._image) if self.trim else None
            return trimmed if trimmed is not None else whole
        box = area.clamp(self.crop, self._image.size)
        return box if box[2] > box[0] and box[3] > box[1] else whole

    def _trimmed(self, image: Image.Image) -> tuple[int, int, int, int] | None:
        """The part of *image* drawn when nothing is cropped: the page on its plain ground (`area.page_bounds`),
        joined with the pages of the frames of its size before it; None (all of it) when it shows no page on a plain
        ground. Remembered for the last few images."""
        for img, box in self._trims:
            if img is image:
                return box
        try:
            found = area.page_bounds(image)
        except Exception:  # noqa: BLE001 - a frame that cannot be looked at is drawn whole
            found = None
        size, before = self._trim_joined
        if size != image.size:
            before = None
        box = area.joined(before, found) if found is not None else None
        if box is not None:
            self._trim_joined = (image.size, box)
        self._trims = [(image, box), *self._trims[:3]]
        return box

    def inside(self, x: float, y: float) -> bool:
        """Whether the canvas point (x, y) is on the picture."""
        b = self._shown
        return b is not None and b[0] <= x < b[2] and b[1] <= y < b[3]

    def in_busy_band(self, x: float, y: float) -> bool:
        """Whether the canvas point (x, y) is on the busy badge."""
        b = self.bbox("busy") if self.band is not None else None
        return b is not None and b[0] <= x <= b[2] and b[1] <= y <= b[3]

    def edged_rectangle(self, x0: float, y0: float, x1: float, y1: float, colour: str, tags: str | tuple[str, ...],
                        width: int = 2, dash: tuple[int, ...] | str = "", edge_tags: tuple[str, ...] = ()) -> int:
        """A rectangle outlined *width* px in *colour* over a dark stroke (`EDGE`) a little wider, seen on a white page
        and a black one; the dark one is tagged *edge_tags* (else the rectangle's own tags) and "edge". Returns the
        coloured item."""
        own = (tags,) if isinstance(tags, str) else tuple(tags)
        self.create_rectangle(x0, y0, x1, y1, outline=EDGE, width=width + EDGE_EXTRA,
                              tags=(*(edge_tags or own), "edge"))
        return self.create_rectangle(x0, y0, x1, y1, outline=colour, width=width, dash=dash, tags=own)

    def _handle(self, hx: float, hy: float, tag: str) -> None:
        half = area.HANDLE / 2
        self.create_rectangle(hx - half, hy - half, hx + half, hy + half, fill=HANDLE_FILL, outline=HANDLE_EDGE,
                              width=HANDLE_EDGE_WIDTH if self._edged(tag) else 1, tags=tag)

    def _edged(self, tag: str) -> bool:
        return tag in self.edged_tags

    def draw_frame(self, box: tuple[float, float, float, float], tag: str, colour: str = "#ff5050",
                   with_handles: bool = True) -> None:
        """A rectangle (*box* in image pixels), 2 px wide, with its eight handles, tagged *tag*; two-tone (over a dark
        stroke, with handles edged 2 px) when *tag* is one of `edged_tags` (translator mode's selection)."""
        x0, y0, x1, y1 = area.box_to_canvas(box, self.scale, self.offset)
        if self._edged(tag):
            self.edged_rectangle(x0, y0, x1, y1, colour, tag)
        else:
            self.create_rectangle(x0, y0, x1, y1, outline=colour, width=2, tags=tag)
        if with_handles:
            for hx, hy in area.handles((x0, y0, x1, y1)).values():
                self._handle(hx, hy, tag)

    def room(self) -> tuple[float, float, float, float]:
        """The canvas's own extent, in its pixels (where a handle can be shown and taken hold of)."""
        return (0.0, 0.0, float(self.winfo_width()), float(self.winfo_height()))

    def draw_turned_frame(self, corners: list[tuple[float, float]], tag: str, colour: str = "#ff5050",
                          with_handles: bool = True) -> None:
        """A frame through its four *corners* (image pixels; an upright one is a box), 2 px wide, with its eight
        handles on it, tagged *tag*: an upright frame drawn as `draw_frame` draws its box."""
        points = [area.to_canvas(x, y, self.scale, self.offset) for x, y in corners]
        flat = [v for p in points for v in p]
        if self._edged(tag):
            self.create_polygon(*flat, outline=EDGE, fill="", width=2 + EDGE_EXTRA, tags=(tag, "edge"))
        self.create_polygon(*flat, outline=colour, fill="", width=2, tags=tag)
        if with_handles:
            for hx, hy in area.frame_handles(points).values():
                self._handle(hx, hy, tag)

    def draw_rotate_handle(self, corners: list[tuple[float, float]], tag: str, colour: str = "#ff5050") -> None:
        """The rotate handle of the frame through *corners* (image pixels): a small round handle a little way out
        from the middle of its top side in the frame's own up, joined to it by a short line (`area.rotate_handle`)."""
        points = [area.to_canvas(x, y, self.scale, self.offset) for x, y in corners]
        (sx, sy), (kx, ky) = area.rotate_handle(points, room=self.room())
        r = area.ROTATE_RADIUS
        edged = self._edged(tag)
        if edged:
            self.create_line(sx, sy, kx, ky, fill=EDGE, width=1 + EDGE_EXTRA, tags=(tag, "edge"))
        self.create_line(sx, sy, kx, ky, fill=colour, width=1, tags=tag)
        self.create_oval(kx - r, ky - r, kx + r, ky + r, fill=HANDLE_FILL, outline=HANDLE_EDGE,
                         width=HANDLE_EDGE_WIDTH if edged else 1, tags=tag)

    def draw_outline(self, points: list[tuple[float, float]], tag: str, colour: str = "#ff5050") -> None:
        """A closed dashed line through *points* (image pixels), tagged *tag*: a slanted region's own frame."""
        flat = [v for x, y in points for v in area.to_canvas(x, y, self.scale, self.offset)]
        self.create_polygon(*flat, outline=colour, fill="", width=2, dash=(6, 3), tags=tag)

    def set_note(self, text: str, ms: int = 0) -> None:
        """A short line at the bottom over the picture ("" removes it); with *ms* it goes by itself after that."""
        if self._note_job is not None:
            self.after_cancel(self._note_job)
            self._note_job = None
        self.note = text
        self._draw_note()
        if text and ms > 0:
            self._note_job = self.after(ms, self._clear_note)

    def set_banner(self, text: str) -> None:
        """A band across the middle of the canvas, dark with white text like the busy badge, over the picture ("":
        none): what the reader must do while the picture cannot follow the viewer."""
        self.banner = text
        self._draw_banner()

    def set_busy(self, line: Callable[[], str] | None) -> None:
        """The busy badge in the top right corner, its text asked of *line* at every turn of the spinner (the page
        stays in view, and the badge reads over any page); None removes it."""
        self.band = line
        self.badge = line is not None
        if self._spin_job is not None:
            self.after_cancel(self._spin_job)
            self._spin_job = None
        self._draw_busy()
        if line is not None:
            self._spin_job = self.after(self.SPIN_MS, self._spin)

    def destroy(self) -> None:
        for job in (self._job, self._note_job, self._spin_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self._job = self._note_job = self._spin_job = None
        super().destroy()

    def _on_configure(self, _event: tk.Event) -> None:
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(120, self._redraw)

    def _extent(self) -> tuple[int, int]:
        """The canvas's size (the size asked for while it is not on screen yet)."""
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2:
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        return w, h

    def _redraw(self) -> None:
        self._job = None
        self.delete("all")
        self._shown = None
        w, h = self.winfo_width(), self.winfo_height()
        if w >= 2 and h >= 2:
            if self.message:
                self.create_text(w / 2, h / 2, text=self._lines(self.message, MESSAGE_FONT, max(200, w - 80)),
                                 fill="#e0e0e0", font=MESSAGE_FONT, justify="center")
            elif self._image is not None:
                self._draw_picture(w, h)
            elif self.hint:
                self.create_text(w / 2, h / 2, text=self._lines(self.hint, HINT_FONT, max(160, min(720, w - 80))),
                                 fill="#ffffff", font=HINT_FONT, justify="center", tags="hint")
        self._draw_banner()
        self._draw_busy()
        self._draw_note()

    def _draw_picture(self, w: int, h: int) -> None:
        assert self._image is not None
        box = self.shown_box()
        part = self._image if box == (0, 0, self._image.width, self._image.height) else self._image.crop(box)
        size, (x, y) = area.fit(part.size, (w, h), self.inset, self.enlarge)
        shown = part if size == part.size else part.resize(size, Image.LANCZOS)
        self.scale = shown.width / part.width
        self._photo = ImageTk.PhotoImage(shown)
        self.offset = (x - box[0] * self.scale, y - box[1] * self.scale)
        self._shown = (x, y, x + shown.width, y + shown.height)
        self.create_image(x, y, anchor="nw", image=self._photo)
        boxes = []
        for (bx0, by0, bx1, by1), colour, label in self.overlay:
            cx0, cy0 = self.from_image_coords(bx0, by0)
            cx1, cy1 = self.from_image_coords(bx1, by1)
            self.edged_rectangle(cx0, cy0, cx1, cy1, colour, "overlay", edge_tags=("overlay-edge",))
            boxes.append((cx0, cy0, cx1, cy1))
        placed: list[tuple[float, float, float, float]] = []  # the labels drawn so far: the next one covers none
        for i, ((_box), colour, label) in enumerate(self.overlay):
            if label:
                others = [b for j, b in enumerate(boxes) if j != i] + placed
                placed.append(self._draw_label(boxes[i], label, colour, others, self._shown))
        for (bx0, by0, bx1, by1), colour, dashed in self.outlines:
            cx0, cy0 = self.from_image_coords(bx0, by0)
            cx1, cy1 = self.from_image_coords(bx1, by1)
            self.edged_rectangle(cx0, cy0, cx1, cy1, colour, ("outline", "outline-dashed" if dashed else "outline-solid"),
                                 dash=(6, 4) if dashed else "", edge_tags=("outline-edge",))
        if self.on_redraw is not None:
            self.on_redraw()

    def _lines(self, text: str, font: tuple, width: int) -> str:
        """*text* broken into lines of at most *width* pixels in *font* (`wrap_line`: Tk itself would break only at
        spaces)."""
        measure = tkfont.Font(root=self, font=font).measure
        return "\n".join(line.rstrip(" ") for lines in wrap_text(text, width, measure) for line in lines)

    def _draw_label(self, region: tuple[float, float, float, float], text: str, colour: str,
                    others: list[tuple[float, float, float, float]],
                    bounds: tuple[float, float, float, float] | None) -> tuple[float, float, float, float]:
        """A region's label (translator mode) beside its box *region* (canvas pixels): white on a small dark box edged
        in the region's colour, readable on a white page and a black one; outside the region where it covers none of
        *others* (the other regions, the labels drawn before it) and stays on the picture (*bounds*), above it first,
        else wherever covers least (`area.place_label`). Returns the label's box, for the next one to leave free."""
        item = self.create_text(0, 0, text=text, anchor="nw", fill="#ffffff", font=LABEL_FONT,
                                tags=("overlay", "overlay-label"))
        tx0, ty0, tx1, ty1 = self.bbox(item)
        pad_x, pad_y = 4, 1  # the box round the text
        size = (tx1 - tx0 + 2 * pad_x, ty1 - ty0 + 2 * pad_y)
        if bounds is None:
            bounds = (0.0, 0.0, float(self.winfo_width()), float(self.winfo_height()))
        lx, ly = area.place_label(size, region, others, bounds)
        self.move(item, lx + pad_x - tx0, ly + pad_y - ty0)
        box = rounded_box(self, lx, ly, lx + size[0], ly + size[1], 4, fill=DARK, outline=colour, width=1,
                          tags=("overlay", "overlay-label-box"))
        self.tag_raise(item, box)
        return (lx, ly, lx + size[0], ly + size[1])

    def draw_badges(self, badges: list[tuple[tuple[float, float, float, float], str]]) -> list[tuple[float, ...]]:
        """Small badges beside regions (*badges*: each region's box in image pixels and its text, a place in the
        reading order), tagged `BADGE_TAG` (the ones before go first): white on a small dark box, placed as a label is
        (`area.place_label`) clear of every other region of *badges*, of the labels on show (`_draw_label`) and of
        the badges placed before it, else wherever it covers least. Returns their boxes (canvas pixels)."""
        self.delete(BADGE_TAG)
        regions = [area.box_to_canvas(box, self.scale, self.offset) for box, _text in badges]
        labels = [tuple(float(v) for v in self.bbox(i)) for i in self.find_withtag("overlay-label-box")]
        bounds = self._shown or (0.0, 0.0, float(self.winfo_width()), float(self.winfo_height()))
        placed: list[tuple[float, float, float, float]] = []
        for i, (_box, text) in enumerate(badges):
            item = self.create_text(0, 0, text=text, anchor="nw", fill="#ffffff", font=ORDER_FONT,
                                    tags=(BADGE_TAG, "order-badge-text"))
            tx0, ty0, tx1, ty1 = self.bbox(item)
            height = ty1 - ty0
            size = (max(tx1 - tx0 + 6, height), height)  # a round badge for one digit, longer for two
            others = [b for j, b in enumerate(regions) if j != i] + labels + placed
            lx, ly = area.place_label(size, regions[i], others, bounds, gap=2)
            self.move(item, lx + (size[0] - (tx1 - tx0)) / 2 - tx0, ly - ty0)
            box = rounded_box(self, lx, ly, lx + size[0], ly + size[1], size[1] / 2, fill=DARK, outline=ORDER_EDGE,
                              width=1, tags=(BADGE_TAG, "order-badge-box"))
            self.tag_raise(item, box)
            placed.append((lx, ly, lx + size[0], ly + size[1]))
        return placed

    def _draw_busy(self) -> None:
        """The busy line in a dark badge with rounded corners in the top right corner of the canvas (clear of the
        page when there is room beside it), with a turning spinner at its left."""
        self.delete("busy")
        if self.band is None:
            return
        w, _h = self._extent()
        margin, pad, r = 10, 9, 8  # from the canvas's edge; inside the badge; the spinner's radius
        right, top = w - margin, margin
        text = self.create_text(right - pad, top + pad - 1, text=self.band(), anchor="ne", fill="#ffffff",
                                font=BADGE_FONT, justify="left", width=max(120, w - 2 * margin - 2 * r - 3 * pad),
                                tags=("busy", "busy-text"))
        tx0, ty0, _tx1, ty1 = self.bbox(text)
        cy = (ty0 + ty1) / 2
        cx = tx0 - 8 - r
        box = rounded_box(self, cx - r - pad, top, right, max(ty1, cy + r) + pad - 1, 8, fill=DARK,
                          outline=BADGE_EDGE, width=1, tags="busy")
        self.create_arc(cx - r, cy - r, cx + r, cy + r, start=self._angle, extent=270, style="arc", outline="#ffffff",
                        width=3, tags=("busy", "busy-arc"))
        self.tag_raise("busy-text", box)
        self.tag_raise("busy-arc", box)

    def _draw_banner(self) -> None:
        """The band: its text broken into lines (`wrap_line`) at most 640 px wide, in the badge's bold font, on a dark
        box with rounded corners in the middle of the canvas, clear of the badge in the top right corner."""
        self.delete("banner")
        if not self.banner:
            return
        w, h = self._extent()
        pad = 12
        text = self.create_text(w / 2, h / 2, text=self._lines(self.banner, BADGE_FONT, max(160, min(640, w - 80))),
                                fill="#ffffff", font=BADGE_FONT, justify="center", anchor="center",
                                tags=("banner", "banner-text"))
        x0, y0, x1, y1 = self.bbox(text)
        box = rounded_box(self, x0 - pad, y0 - pad + 2, x1 + pad, y1 + pad - 2, 8, fill=DARK, outline=BADGE_EDGE,
                          width=1, tags="banner")
        self.tag_raise(text, box)

    def _spin(self) -> None:
        self._spin_job = None
        if self.band is None:
            return
        self._angle = (self._angle - 30) % 360
        try:
            self._draw_busy()  # the badge follows the line's length
        except tk.TclError:  # the canvas is gone
            return
        self._spin_job = self.after(self.SPIN_MS, self._spin)

    def _clear_note(self) -> None:
        self._note_job = None
        self.note = ""
        try:
            self._draw_note()
        except tk.TclError:
            pass

    def _draw_note(self) -> None:
        self.delete("note")
        if not self.note:
            return
        w, h = self._extent()
        text = self.create_text(w / 2, h - 12, text=self._lines(self.note, NOTE_FONT, max(120, w - 60)), anchor="s",
                                fill="#e8e8e8", font=NOTE_FONT, justify="center", tags="note")
        x0, y0, x1, y1 = self.bbox(text)
        box = self.create_rectangle(x0 - 10, y0 - 4, x1 + 10, y1 + 4, fill="#000000", outline="#3a3a3a", tags="note")
        self.tag_lower(box, text)

    def to_image_coords(self, x: int, y: int) -> tuple[int, int]:
        if self._image is None or self.scale <= 0:
            return (0, 0)
        ix = int((x - self.offset[0]) / self.scale)
        iy = int((y - self.offset[1]) / self.scale)
        return (max(0, min(self._image.width, ix)), max(0, min(self._image.height, iy)))


def show_preview(image: Image.Image, title: str = "TASlation") -> None:
    set_app_id()
    root = tk.Tk()
    apply_icon(root)
    give_icons(root)
    root.title(title)
    w = min(image.width, root.winfo_screenwidth() - 120)
    h = min(image.height, root.winfo_screenheight() - 160)
    root.geometry(f"{max(400, w)}x{max(300, h)}")
    canvas = ImageCanvas(root, bg="#202020")
    canvas.pack(fill="both", expand=True)
    canvas.set_image(image)
    root.bind("<Escape>", lambda _e: root.destroy())
    root.mainloop()

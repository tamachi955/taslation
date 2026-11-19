# Changelog

What changed for someone who uses TASlation, newest first. The version is under Help → "About TASlation", and
`update.cmd` shows it before it updates.

## 0.4.0 - 2026-11-19

Reading

* "Reading mode" is now called "Full screen" (Japanese フルスクリーン) on its button, in the help, in the settings and in
  every language. `taslation gui --full-screen` starts in it, and `--reading` still works.
* The full screen keeps the role you chose. The Reader role is as before. In the Translator role the page keeps its
  frames and marks, and the pointer and keys are the Translator's: a click selects a region, a drag moves or resizes it,
  a double click opens the editor. No click goes to the viewer there, the page keys still turn the viewer's pages, and
  Auto stays as you set it. Esc first lets go of a selected region, then leaves; F11 always leaves.
* Starting a whole-book run by its key on the full screen says to leave the full screen first.

Translating

* Chapter labels and the words of a contents page are translated wherever they stand, a contents list row by row.
* Japanese that was read surely beside digits or Latin letters is translated; before, such a reading was taken for a
  drawing. A Japanese heading with a subtitle in Latin letters is translated too.
* A paragraph set across, as on an explanation page, is read and lettered as one region instead of in pieces.
* Prices, addresses, colophons, a viewer's own panels and a title page's title and author stay as they are.

Other

* The README is short: what TASlation is, its features, what it does not do, installing in three steps and the
  requirements. The installer's questions and steps are now in `docs/INSTALL.md`, and the legal position, country by
  country, in `docs/LEGAL.md`.

## 0.3.0 - 2026-11-19

Lettering

* Where the original letters part of a bubble larger than the rest, that part of the translation is lettered larger
  too, by the original's ratio and at most twice the size. The words of the translation never change. The rest of the
  bubble keeps at least four fifths of its size; where both sizes do not fit so, the part is set less larger, then not
  at all, and a bubble whose part is not found in the translation is lettered at one size as before.
* The region editor shows the part in larger text, and "Set larger" and "One size" set it on the selected words or
  clear it. Find and replace keeps the part where it does not touch it.
* The setting "Set larger what the original sets larger" (on by default, `size_emphasis`) turns it off.

Saved files

* A saved translation keeps the place of its larger part. Versions 0.1.0 and 0.2.0 read these files and letter them
  at one size.

## 0.2.0 - 2026-11-19

Reading

* A new page is read from its first frame, without a fixed wait after the turn. A turn during a translation takes the
  old lettering off at once and starts the new page.
* A page translated at one window size is shown from the saved translations at another size, and at another display
  scale, without being translated again.
* The status line and the busy badge speak of the page on show only.
* After the viewer's window is given another size, the page shows as fast as any new frame.
* While a whole-book run reads or translates, a page turned in the viewer shows on the window at once.
* On a viewer that draws a page soft first, saved lettering goes on the sharp picture, once, and nothing read from
  the soft picture is kept once the sharp one comes.
* The bubble under the pointer shows its other side, its Japanese can be selected and copied, and F3 and Shift+F3 go
  from bubble to bubble.
* A book's reading direction is set in Book settings.
* In the Translator role too, resting the pointer on a translated bubble shows its original, in a panel beside it
  or in the bubble itself; a click still selects the region. F2, Shift+F2, Ctrl+F2, F3 and Shift+F3 work there too.
* A page key is no longer lost when the viewer is slow for a moment: the viewer keeps the focus until it has taken
  the key. On a desktop viewer TASlation does not know yet, every press turns one page.

Translating

* A whole-book run translates while the pages are still being read, and the window follows the viewer meanwhile.
* A short line translated before in the book or its series is given that translation again.
* A page translated alone spells names as the series sheet spells them.
* Names rendered in more than one way are offered for a single spelling.
* A translation written by the person is marked as theirs and kept by Translate again.
* "Lines to review..." lists every line of the book worth a look.
* Find and replace and the series sheet can rename across all volumes of a series.

Lettering

* A translation is set along its bubble's body, each target language hyphenates by its own patterns, Thai breaks
  between words, and Hindi and Bengali are shaped with HarfBuzz.
* Outlined lettering on the art is erased with its ring, and a region moved or resized is erased on its paper alone.
* The lettering size goes up to 200 %, and the panel's text size is a setting.
* Translations of bubbles that touch or overlap are not lettered over each other: each keeps the part of the shared
  space nearest to its own text. Pages translated before look right when shown again.
* Two bubbles joined into one shape are read and translated as two when their texts sit apart, and a paragraph on
  the page that came apart in pieces is read as one.
* A rectangle you draw on the drawing, or a region you move or resize there, is no longer wiped as a flat box: only
  its lettering is erased and the drawing under it is filled in.
* On a computer with an NVIDIA GPU and the two page models installed, the layout model finds the lettering by
  default, together with the inpainting (`detect_model = "auto"`): lettering on the drawing is found far more often.
  A computer without a GPU, or without the two models, detects as before, and a settings file that says
  `detect_model = "off"` keeps it off.

Speed and memory

* The translation model loads while the window starts, and the OCR readers run on the GPU where it has room, on a
  6 GB card too beside the layout model and the inpainting. The inpainting gives back the GPU memory it leaves idle.
* When the GPU runs out of memory, the OCR readers, the layout model and the inpainting go on on the CPU only until
  the GPU memory is next let go, no longer until TASlation is closed.
* Ollama runs only while TASlation needs it, unless the person runs it themselves. Tools → "Release the model now" gives
  the GPU memory back at once.

Saved files

* The saved files with text of a book are protected for the Windows user (Windows DPAPI).
* An export can hold several books with their page information and series sheets; an import keeps the reader's
  corrections.
* The Saved translations list shows sizes, sorts, and takes several rows at once.
* A new volume starts from its series' defaults.

Other

* The window can be dark, following Windows' app mode.
* Text typed through an input method (Japanese, Chinese, Korean) shows in the box while it is being composed.
* Help → "About TASlation" shows the version of the program files that run. It no longer lists the offline lines; "Copy details"
  carries the offline guard's state.
* The translation model is pinned to its publisher's revision of November 9, 2026.

## 0.1.0 - 2026-11-15

The first public version.

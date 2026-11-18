# Changelog

What changed for someone who uses TASlation, newest first. The version is under Help → "About TASlation", and
`update.cmd` shows it before it updates.

## 0.2.0 - 2026-11-19

Reading

* A new page is read from its first frame, without a fixed wait after the turn. A turn during a translation takes the
  old lettering off at once and starts the new page.
* A page translated at one window size is shown from the saved translations at another size, and at another display
  scale, without being translated again.
* The status line and the busy badge speak of the page on show only.
* After the viewer's window is given another size, the page shows as fast as any new frame.
* While a whole-book run reads or translates, a page turned in the viewer shows on the window at once.
* On a viewer that draws a page soft first, saved lettering goes on the sharp picture, once.
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

Speed and memory

* The translation model loads while the window starts, and the OCR readers run on the GPU where it has room.
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
* Help → "About TASlation" shows the version of the program files that run.
* The translation model is pinned to its publisher's revision of November 9, 2026.

## 0.1.0 - 2026-11-15

The first public version.

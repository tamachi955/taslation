# Changelog

What changed for someone who uses TASlation, newest first. The version is under Help → "About TASlation", and
`update.cmd` shows it before it updates.

## 0.9.6 - 2026-11-22

Translating a whole book

* A whole-book run could read a page from the soft picture a viewer draws first and never read its sharp one: when
  the sharp picture arrived while the soft one was being read, it was kept but not read. The run now throws that
  reading away - nothing of it is translated or stored - and reads the page again from the sharp picture. Seen once
  in 13 runs on the test computer, and more often on a slower one. (With `context_mode` off, the run that reads page
  by page, this is not changed yet.)

For developers

* The stand-in viewer run and the benchmark also run on GitHub's machines, in parallel jobs, for a push to a branch
  named `ci/...` (`.github/workflows/gpu-checks.yml`): about 20 minutes beside the test suite's six. The developer's
  computer is needed only for the timing figures.

## 0.9.5 - 2026-11-22

Lettering

* Lettering turned a quarter turn (text that runs down or up the page) sat half a pixel off and came out slightly
  blurred: the turned picture was made one pixel too large. It is now placed exactly; the words, their size and the
  line breaks are unchanged. With OpenCV 5.1, which a new installation gets, the old fault also moved the erased
  shape by a pixel.

For developers

* The whole test suite runs on GitHub's own machines in eight parallel jobs for a push to a branch named `ci/...`
  (`.github/workflows/tests.yml`, `tools/test_shards.py`), in about six minutes. Nine tests that depended on the
  developer's computer (its fonts, its GPU, its package versions, its speed) no longer do.

## 0.9.4 - 2026-11-21

Documents

* The README shows the introduction video at its top (49 seconds: the idea, what happens inside, the speed and the
  features). The earlier recording is no longer in the repository.

## 0.9.3 - 2026-11-21

Translating

* When the translation program (Ollama) takes a request and sends nothing back, TASlation no longer waits for up to
  15 minutes. After 30 seconds without an answer (counted over the pages you turn meanwhile; longer for a long
  request) it says so and asks again on a new connection. If that gets nothing either, it starts the translation
  program again and goes on with the page - only a program TASlation started itself, and at most once in ten
  minutes. A translation program you run yourself is never stopped: TASlation then says that it does not answer and
  asks you to restart it and press F5.
* This was seen once in 33 long test runs with Ollama 0.40.16: the program logged the requests but none reached the
  model, while it still answered other questions. With the change the run went on by itself.

## 0.9.2 - 2026-11-21

Other

* The name is spelt out as "Tool Assisting Self-translation of manga" (before: "Tool Assisting Self-translation") in
  the window's title, under Help → "About TASlation", in the README and in the project's description on GitHub.
* The README links a 49-second video that shows the idea, what happens inside TASlation, its speed and its
  features. The video is a file attached to this version's release on GitHub, not a part of the program.

## 0.9.1 - 2026-11-21

Updating

* The "Check for updates" dialog is placed again when the answer makes it taller: it no longer hangs below the window,
  and on a low screen its buttons stay on the screen (a long list of changes then shows fewer lines and scrolls). It
  no longer takes the focus when the answer comes.
* The changes in that dialog are shown as paragraphs the box wraps itself, each change with a bullet, in place of the
  changelog's short broken lines.
* Looking for a new version also works with a server that closes the connection after its answer; such an answer made
  it say that GitHub could not be asked. (GitHub does not answer that way today.)

Other

* The README and the project's description on GitHub call what TASlation does real-time translation (before:
  on-the-fly translation).
* The README's recording is new: made with version 0.9.0, and 1.4 MB where the old one was 7.5 MB. It is made by a tool
  in the repository now (`tools/intro_video.py`), so that it can be made again for a later version.

## 0.9.0 - 2026-11-21

Updating

* Help → "Check for updates..." asks GitHub whether a newer version is out, only when you choose it, and shows both
  versions with what changed. "Update now" closes TASlation, downloads the new version, updates the program files and
  starts TASlation again. It asks once before it starts, and the installation that follows still asks before any
  download of its own.
* The files an update replaces are kept in the folder `.previous`, and `update.cmd -Back` goes back to the version
  before. An update that stops no longer leaves you without the old version.
* The installer asks once whether TASlation may look for a new version when it starts (Enter means no). If you say
  yes, it looks at most once a day, while nothing is being read or translated; a newer version is named in the Help
  menu and in one line of the status bar, never in a dialog. Tools → "Settings..." → System changes it later
  (`update_check`).
* What is asked of GitHub is the first 16 KB of the project's `CHANGELOG.md`, by a small program of its own
  (`check_update.py`); the window itself still connects to nothing but Ollama on this computer. Nothing about you,
  your computer, the installed version or your books is sent; GitHub sees your IP address and the time, as any site
  you open does. Nothing is downloaded or installed without asking.
* Double-clicking `update.cmd` first asks whether to look on GitHub (Enter means no; it then takes a ZIP you
  downloaded yourself, as before).
* A TASlation of version 0.8.1 or earlier has none of this yet: update it once with the ZIP and `update.cmd`, as
  before.

Other

* The Settings dialog fits a 1366 x 768 screen in every language: a page that is too tall scrolls, and Save and Close
  stay on the screen. Before, the dialog was taller than such a screen.
* The boxes of choices in the Settings dialog are as wide as their longest choice in Japanese, Korean and Chinese
  too; some of them cut their text.
* The notice at the start names updating and the look for a new version where it says when the network is used. It is
  shown once more to everyone, because that sentence changed.
* The README's requirements say that the network is used only when installing and updating.

## 0.8.1 - 2026-11-20

Reading

* The reading order is right on more pages. A speech bubble under another in the same panel is read after it, even
  where a tall bubble beside them used to pull it forward; and two panels whose gutter is crossed by a figure or by
  effect lines are now told apart. On the public sample pages the order the translator gets is wholly right on 163
  of 193 pages instead of 159, and no page got worse. The order decides which lines the translator sees before a
  line, and the order in which the bubbles of a page fill in.

## 0.8.0 - 2026-11-20

Speed and memory

* The page on show when you start TASlation, and a page you turn to just as the window becomes ready, get their first
  bubble sooner: the code of the model that finds the bubbles now loads while the Japanese reader loads, not when the
  first page needs it. On the test computer the first page's first bubble comes 1.3 to 3.0 seconds sooner, and a page
  turned to right as the window becomes ready after 6.3 seconds instead of 8.4 (recorded with TASlation starting
  Ollama itself; in a trace with the turn forced 40 ms after "ready", 2.6 seconds instead of 7.1). With the OCR on
  "auto" the window says it is ready about 0.4 seconds later.
* On a viewer that draws a page blurred first, TASlation no longer starts reading the blurred picture: it waits for
  the sharp one (a page with little on it no longer than it always waited). On those turns the first bubble comes
  about 0.1 to 0.2 seconds sooner.

Reading

* A page you turned to while TASlation was still starting could be read from its blurred first picture without the
  check that keeps nothing from such a picture; it now gets that check like any other page.

Saved files

* The notice at the start says in four short sentences that no page image is saved, what is kept of a book and where
  the help lists it all, and when the network is used. It is shown once more to everyone, because the earlier text
  left some of this out. Help → "Your data" also names the window's settings and the error log, and the whole-book
  dialog says that no page image is written to disk.

Other

* The manual, the install guide, the legal notes and `taslation --help` say what is true of the cache (the colophon's
  details and reused short lines are kept), of the model download you agree to, and of the network (while it reads,
  the only peer is the Ollama server on this computer). The README names the two articles of Japan's Copyright Act it
  relies on and points to the notes on 30 countries, and says which changes Ctrl+Z takes back.
* The repository no longer holds a developer's script that turned a viewer's pages and saved its screens, and the
  package no longer holds two functions only that script used (a real click at a screen position, an ALT tap to
  take the foreground). The program never called them.

## 0.7.0 - 2026-11-20

Speed and memory

* After a whole-book run in the window, the translation model stays loaded when Auto goes back on, so the next
  untranslated page does not wait for the model to load again: its first bubble comes after about 1.5 seconds instead
  of 4.3 on the test computer. With Auto off it is released at once, as before.
* A page you turn away from before it is finished keeps the bubbles translated by then. Coming back, they show at
  once and only the rest is translated (2 requests instead of 11 on the test pages). Stop and Esc keep nothing, as
  before.
* While you read a page, the window has Ollama prepare the beginning of the next page's first request where Ollama
  does not hold it, so that request does not take a second or more. Nothing is read ahead, and a page turn never
  waits for it. The requests are the same; the model may word about one line in ten otherwise, at the same score.

## 0.6.1 - 2026-11-20

Other

* The README is shorter: it says in one sentence which viewers TASlation works with (every viewer a screenshot can
  be taken of), and it no longer carries the benchmark's figures, the note on which languages were measured, or the
  long note under the recording. Nothing in the program changed.

## 0.6.0 - 2026-11-20

Speed and memory

* Translating is about a quarter faster where TASlation starts Ollama itself. The server keeps the cache of PLaMo's
  whole window (`LLAMA_ARG_SWA_FULL=1`) and 256 MB of earlier requests in RAM (`LLAMA_ARG_CACHE_RAM=256`), so a
  request no longer goes back over the lines before it. Measured on the sample dataset with a 6 GB GPU: 413 to 294
  seconds page by page (29 % less), 400 to 296 seconds for the whole book (26 % less); without a GPU, 1.28 to 0.98
  seconds a line. The translations score the same.
* It takes 132 MB more GPU memory (220 MB with the f16 cache) and about 1 GB less RAM. Where those MB would move
  the OCR readers from the GPU to the processor, TASlation starts Ollama as before: this is decided at each start,
  and the System page and `taslation doctor` say which.
* The new setting `ollama_window_cache` ("auto", "off", "on"; also on the System page) chooses it.
* The rule that places the OCR readers counts the translation model's GPU memory as measured for the server's
  settings; it counted too much before.
* An Ollama that was running before TASlation is left as it is. `docs/INSTALL.md` says how to set the two variables
  for your own Ollama.

## 0.5.0 - 2026-11-20

Installing

* The installer stops at a no to a licence, to Python, to Ollama or to the translation model: nothing is downloaded
  or installed, and running `install.cmd` again asks again.
* A download that fails is tried 3 times, 15 seconds apart, and then the installation stops; a server that refuses
  the download stops it at once. What was already downloaded is kept, and running `install.cmd` again goes on from
  there.
* An installation that stopped makes no Start-menu shortcut and says that TASlation is not installed yet, what failed
  and how to go on (`docs/INSTALL.md`, "If the installation stops").

Lettering

* English is hyphenated by American English patterns (hyph-utf8): a word broken over two lines in a narrow bubble
  breaks where English breaks it (for-ward, hyphen-ation), not between any two letters.

Translating

* Translating with PLaMo asks less of Ollama: a page's lines are held for the next request as Ollama computed them,
  so the next request goes on from the last one. On the sample dataset the translation takes 6 to 7 % less time at the
  same quality.
* A page whose reading was taken back (a viewer that draws a page soft first) no longer leaves its lines in what the
  translation model is given as the story so far.

Other

* Messages that asked you to name the book first pointed at a Book field the tool bar no longer has; they now point
  at the Series field (and the volume beside it), in every language.
* The spelling check is off by default: its word lists are an optional extra that TASlation does not install. Turned
  on without them, the region editor says so once and tells you where to turn it off; it no longer asks you to run pip.

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

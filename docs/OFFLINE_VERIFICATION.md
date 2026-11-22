# Offline verification

This is the developer's log of measurements and decisions, kept with the
source. Its entries are dated and stay as they were written; a later entry
records what changed. It also records practices of the development that the
program does not do: screens of a book the developer owns were saved on the
developer's computer to measure against, by a developer's tool that turned
the viewer's pages (`tools/dev_snapshots.py`, from "Text blocks and the
drawing around them (2026-10-28)" on; the tool was taken out of the
repository after version 0.7.0, and `tools/dev_frames.py` only reads what
was saved),
and on 2026-10-29 cut-out pieces of those screens were transcribed and judged
by a cloud model, with the owner's permission ("A cloud model as the judge,
and a gold set (2026-10-29)"). The program keeps no page image, turns no
page and sends nothing to a cloud service; what it keeps and when it uses
the network are in docs/MANUAL.md and in its legal notice.

The sections below begin with how the program's own process is kept off the
network, how to check it yourself, and the results of the verification run
made on 2026-10-24 on the machine the project was built on (Windows 11,
Python 3.13.2, torch 2.14.1+cpu, transformers 5.20.2, manga-ocr 0.1.16).

## How the program's own process is kept off the network

What follows holds for TASlation's own process (the window and the
`taslation` commands). Ollama is a program of its own, which TASlation starts
when it is not running and asks to load, release and run the translation
model on 127.0.0.1; what else Ollama does is not under TASlation's control.
The installer, `setup_models.py` and `check_update.py`, which use the network, run
without the guard.

1. **Socket allowlist in the process** (`taslation/netguard.py`). Installed by
   every entry point before any heavy import. It patches
   `socket.getaddrinfo`, `gethostbyname*`, `socket.connect`, `connect_ex` and
   `sendto`, and adds a CPython audit hook that repeats the same checks at the
   C level. Allowed: loopback addresses on the Ollama port (11434 by
   default). Everything else, including a DNS lookup, raises
   `NetworkBlocked`.
2. **Offline environment**: `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`,
   `HF_DATASETS_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY`, `DO_NOT_TRACK` are set;
   `HTTP(S)_PROXY` variables are removed; `NO_PROXY=*`.
3. **Models by local path**: the OCR models are read from their folders under
   `models/` with `safetensors`. `transformers` (and with it `huggingface_hub`)
   is installed, for the layout model, which it reads from its local folder
   only (`local_files_only=True`, `trust_remote_code=False`,
   `taslation/detect/layout.py`); LaMa is read with torch from its local file.
   Sections below that name manga-ocr, `ocr_device` or `transformers` for the
   OCR are the record of the OCR before 2026-11-01; see "The OCR model
   (2026-11-01)".
4. **Loopback-only Ollama client** (`taslation/translate/ollama.py`): rejects
   any URL whose host is not loopback, and uses a `urllib` opener with proxies
   disabled.
5. **Separate download scripts**: the code a user runs that uses the network
   is the installer (`install.cmd` / `install.ps1`, also run by `update.cmd`)
   and `setup_models.py`, which the installer runs and which the window and
   the command line run as a separate process when the person agrees to
   download a translation model, and `check_update.py`, which the window
   (Help > Check for updates..., and at most once a day at its start for who
   turned that on) and `update.cmd` run as a separate process to ask GitHub
   for the newest version and, when the person updates, to download that
   version's ZIP ("Looking for a new version and updating (2026-11-21)");
   the developer tool `tools/fetch_openmantra.py` (one download of a sample
   dataset, see "OpenMantra as the sample dataset (2026-10-30)") is the
   other. The application imports none of them.
6. **No image persistence**: there is no code path that writes a captured or
   translated page to disk. The on-disk cache (`~/.taslation/cache/*.json`)
   holds translated text, normalised bubble geometry, 320-bit page
   fingerprints, the colophon's details (title, volume, author, publisher,
   ISBN) and the translations of short lines kept for reuse under a keyed
   hash of the line (HMAC-SHA-256, `taslation/linememo.py`), never the line's
   Japanese.
7. **Saved files protected at rest** (`taslation/protect.py`): the caches,
   annotations and series sheets (and the copies kept beside them) are written
   only in their protected form, Windows DPAPI for the Windows user who saved
   them, so a copy taken off the computer or opened by another Windows user
   reads as nothing. Any program running as that same Windows user can open
   them, as TASlation does. An earlier version's plain files are converted at
   the start; `taslation audit` ends with the count of any left plain.

## Check it yourself

After an installation with `install.cmd`, the program is
`.venv\Scripts\taslation.exe` in the folder that holds `install.cmd` (it is
not on PATH, and pytest is not installed). In PowerShell, in that folder:

```powershell
.\.venv\Scripts\taslation.exe doctor          # guard status, models, font, Ollama
.\.venv\Scripts\taslation.exe audit tests\fixtures\sample_page.png --translator echo   # detection and OCR + every network call: none
.\.venv\Scripts\taslation.exe audit tests\fixtures\sample_page.png   # the same with Ollama: only 127.0.0.1, port 11434
.\.venv\Scripts\taslation.exe cache protect    # saved files: protected, plain, opened here (counts only)
```

The audit's last part, `--- saved files (at rest) ---`, counts the files with
text of a book in the state folder and ends with "plain files with text of a
book: none" when every one is protected; it changes nothing.

Then disconnect (Wi-Fi off / cable out) and use the window normally. Ollama
keeps answering on loopback; the models load from disk.

In a source checkout with the development tools (`pip install -e .[dev]`),
the same commands are `taslation ...`, and the tests check the guard and the
protection:

```bash
python -m pytest tests/test_netguard.py -q          # guard tests incl. a raw-socket subprocess
python -m pytest tests/test_protect.py -q           # the protection, with real DPAPI in a temporary folder
```

## Results of the verification run (2026-10-24)

### Test suite

`python -m pytest -q`: **72 passed** (about 25 s). This includes:

* `tests/test_netguard.py`: DNS lookups, direct IP connects, UDP `sendto`,
  loopback on a non-allowed port and `urllib.request.urlopen("http://example.com")`
  all raise `NetworkBlocked`; a loopback connection on an allowed port
  succeeds; a subprocess using the raw `_socket` module (bypassing the Python
  wrapper) is stopped by the audit hook.
* `tests/test_offline_real_ocr.py`: the real manga-ocr model, loaded under
  the guard, reads the synthetic page correctly; the full pipeline with a
  dictionary translator runs with zero blocked attempts (i.e. nothing even
  tried to reach out) and the second, smaller view of the page is served from
  the cache.
* `tests/test_ollama_client.py`: the client talks to a stub server on a
  loopback port, falls back from schema to plain JSON mode, refuses non-loopback
  URLs, and is blocked by the guard on a non-allowed port.

### `taslation doctor`

```
taslation 0.1.0  python 3.13.2  win32
Network guard: ON (loopback:11434 only; 0 attempt(s) blocked)
  torch         2.14.1+cpu
  transformers  5.20.2
  manga_ocr     0.1.16
  cv2           5.0.0
  numpy         2.5.4
  PIL           13.0.0
OCR model: ready in C:\TASlation\models\manga-ocr-base
Font: C:\TASlation\models\fonts\ComicNeue-Bold.ttf
Ollama: reachable at http://127.0.0.1:11434 (v0.40.10); 1 model(s) installed
  configured model 'hf.co/XpressAI/shisa-v2.1-qwen3-8b-GGUF:Q4_K_M': installed
Translation cache: ...\cache (0 book(s); text only, no images)
Capture: 6 window(s) visible
Result: ready
```

### `taslation audit tests/fixtures/sample_page.png` (real Ollama)

```
[ 0] translated    こんにちは  =>  Hi
[ 1] translated    ありがとう  =>  Thanks
[ 2] translated    どこへ行くの  =>  Where are you going?
[ 3] translated    今日はいい天気だね  =>  Nice weather today
[ 4] translated    大丈夫だよ  =>  I'm okay
[ 5] translated    まだ終わってない  =>  It's not over yet
timings: fingerprint 0.04s, detect 0.03s, ocr 0.99s, translate 6.35s, render 0.04s

--- network audit ---
Network guard: ON (loopback:11434 only; 0 attempt(s) blocked)
allowed calls (all loopback):
  getaddrinfo -> '127.0.0.1':11434
  socket.getaddrinfo -> '127.0.0.1':11434
  socket.connect -> 127.0.0.1:11434
blocked attempts: none
```

With the real translator the only network activity of the whole run is the
loopback connection to Ollama (the same call is listed twice because both the
Python-level patch and the C-level audit hook record it).

### `taslation audit tests/fixtures/sample_page.png --translator echo`

```
page units: 1  cache hits: 0  misses: 1
[ 0] translated    こんにちは  =>  こんにちは
[ 1] translated    ありがとう  =>  ありがとう
[ 2] translated    どこへ行くの  =>  どこへ行くの
[ 3] translated    今日はいい天気だね  =>  今日はいい天気だね
[ 4] translated    大丈夫だよ  =>  大丈夫だよ
[ 5] translated    まだ終わってない  =>  まだ終わってない
timings: fingerprint 0.04s, detect 0.03s, ocr 1.08s, translate 0.00s, render 0.04s

--- network audit ---
Network guard: ON (loopback:11434 only; 0 attempt(s) blocked)
allowed calls: none (no network call at all)
blocked attempts: none
```

Detection, OCR (real model) and rendering made **no network call at all**;
the guard recorded nothing allowed and nothing blocked.

### Live window test (`tools/fake_viewer.py`)

A Tk stand-in viewer showing the three synthetic pages was batch-read with
`taslation batch --window "Fake Viewer"` using the real OCR model and the
real translation model (Shisa V2.1 8B through Ollama, GTX 1660 Ti 6 GB):

```
Page 1: 6 bubble(s)  [7s]
Page 2: 6 bubble(s)  [16s]
Page 3: 6 bubble(s)  [25s]
Batch finished: 3 page(s), 18 bubble(s) - no change after turning the page twice (end of book)
```

About 8-9 s per page (OCR ~1 s, translation ~7 s at 14 tok/s). Window
capture (`PrintWindow`), synthetic Left-arrow page turns (`SendInput`),
end-of-book detection and the cache all worked; the cache file holds the
English lines only ("Hey", "Thanks", "Where you headed?", ...). A fresh capture
of a cached page afterwards is composited from the cache in about 0.1 s.
(The third test page is mirrored on purpose; its OCR noise was translated into
nonsense, which is the expected behaviour for unreadable text.)

### Context-aware batch (2026-10-25)

The same fake viewer (3 pages) was batch-read in the default context mode
with `qwen3:30b-a3b-instruct-2507-q4_K_M`:

```
Scanned page 1: 6 bubble(s)  [2s]
Scanned page 2: 6 bubble(s)  [3s]
Scanned page 3: 6 bubble(s)  [5s]
Reading the story: notes 1/1...
Notes ready: 3 character(s), 5 term(s)
Translating chunk 1/1 (18 bubbles)...
Translated chunk 1/1: 18 bubble(s) so far  [79s]
Batch finished: 3 page(s), 18 bubble(s) - no change after turning the page twice (end of book)
```

The cache received coherent English ("Wait here", "Hurry up", "You're really
going?", "I'll be back tomorrow", ...), the series notes file was written for
"Fake Story" (volume marker "1巻" stripped from the book name), and the GUI
composited the cached page on F5. A chunk-sized request (60 bubbles + 40
look-ahead bubbles + notes, 2.7K prompt tokens) takes about 105 s on this
machine (prompt 125 tok/s, output 16 tok/s).

### Other target languages

The synthetic page was translated and rendered into Chinese (Simplified),
Korean, Thai and Arabic with the default model: the Noto fonts were picked per
script, Chinese/Thai wrapped between characters, and Arabic was laid out
right-to-left with joined letters. Spanish, Chinese and Korean output read
naturally; Arabic was noticeably weaker (one line mistranslated).

### A real book (2026-10-25)

The owner opened a purchased manga volume in a browser-based viewer (Chrome,
1936x1048 window, two-page spreads on a black background). Findings and the
changes they led to:

* `PrintWindow` captures the Chrome window fine. The reader hides its toolbar
  after a moment, so fixed margins were wrong; the page area is now found as
  the large non-background blobs (toolbars and buttons are short and are
  ignored), with only the browser's tab and address bars excluded by a 85 px
  top margin saved for that window.
* Spreads have no gap between the pages; a landscape unit is now split in the
  middle (right page first).
* Real pages have dialogue outside closed bubbles. A second, classical
  detector now finds columns of glyph-sized marks on light areas; hand-drawn
  sound effects (short katakana) are skipped and glyph clusters that OCR reads
  as almost nothing are dropped as noise. Text running into dark artwork is
  still missed.
* A five-screen batch (ten pages) scanned 31 bubbles in 15 s, extracted notes
  (3 characters, 3 terms) and translated everything in one chunk; 2.5 minutes
  in total. The cache file holds the English lines and bubble geometry only.
* The whole volume (101 screens, 202 pages) was then batch-read: the scan
  found 690 bubbles in about 6 minutes, the notes pass produced 5 characters
  and 6 terms, and translation ran at 53-60 bubbles per ~115 s chunk. Chunk 6
  of 12 stalled (Ollama request timed out at 900 s, most likely a looping
  generation) and the batch stopped there with 324 bubbles on 68 page units
  cached. Two fixes followed: the output length is now capped per request
  (`num_predict` from the input size), and a failed chunk is retried in halves
  and skipped only as a single page, so the batch carries on. Re-running the
  batch re-scans the book (fast) and translates only what is not cached yet.
* While the scan was running the viewer flickered through loading screens and
  ended on the reader's end-of-book page; once the synthetic page turns
  stopped, the monitor went to power saving ("No Signal") until the owner
  moved the mouse. GPU telemetry and the event log showed no fault. Batches
  now keep the PC awake (and the display on during the scan).
* The batch was then re-run from the first page with 150-bubble requests and
  a 32K context: the scan skipped the cached pages (102 screens, 409 new
  bubbles in about 6 minutes), the notes grew to 6 characters and 6 terms (9
  noise entries dropped), and the remaining 394 bubbles were translated in 3
  runs. Every run needed retries: one timed out at 900 s and several replies
  looped ("no way, no way, ..." style repetition) until the output cap cut
  them off, after which the halving retries finished all but 2 page units;
  78 minutes in total. The cache ended at 161 page units and 718 bubbles for
  the whole volume. Follow-up changes: replies cut off by the cap are salvaged
  up to the cut, only the unfinished pages are asked for again, the cap is
  tighter, error messages no longer carry model output, and the default run
  size is 100 bubbles.
* Reading check: with the whole volume cached, the GUI was pointed at the
  reader on a content spread and F5 composited the 10 cached translations of
  both pages in 0.2 s, bubbles erased and lettered in place, sound effects left
  as drawn. One dense narration column next to a black figure was not
  translated (not detected), the known limitation. The reader's end-of-book
  panel, when it was on screen, was translated as if it were a page (its
  labels are Japanese); horizontal lines with Latin letters or digit strings
  are now skipped as print.

### OCR versus glyph size

Twenty short lines of vertical Japanese were rendered with Yu Gothic Bold at
12, 14, 16, 20 and 28 px and read with manga-ocr as is and enlarged 2x / 3x
with Lanczos:

| glyph | 1x exact | 2x exact | 3x exact | mean similarity |
|---|---|---|---|---|
| 12 px | 17/20 | 16/20 | 16/20 | 0.97 |
| 14 px | 17/20 | 15/20 | 15/20 | 0.97 |
| 16 px | 17/20 | 18/20 | 18/20 | 0.97-0.99 |
| 20 px | 17/20 | 17/20 | 17/20 | 0.98 |
| 28 px | 16/20 | 17/20 | 17/20 | 0.98 |

Accuracy is flat across the range the browser-based viewer produces (12-16
px), and upscaling does not help, so crop upscaling is off by default and
capturing at a higher zoom was not pursued. (Windows also clamps a window,
Chrome's or Tk's, to the screen height, so an oversized viewer window cannot
be captured either.)

### Detection survey on real spreads (2026-10-25)

Six spreads (twelve pages) of the volume were scanned and the annotated
captures inspected by eye (counts only; no text was recorded):

* about 35 dialogue blocks, 33 found: the misses were a small two-character
  black bubble and a large exclamation drawn as a sound effect on the art;
* light-on-dark bubbles and loose dialogue columns were found by the new
  inverted and text-block passes;
* before the last round of rules, 4-5 regions that were never text (the
  mascot's face twice, two tiny highlights, a fragment at the page edge) were
  read as 1-6 Japanese characters and would have been translated as junk.

OCR confidence (geometric mean of the generated tokens' probabilities, beam
search aware) separated the two groups cleanly on this sample: real dialogue
scored 0.66-1.00, the junk regions and hand-drawn sound effects 0.08-0.47,
synthetic text 1.00 and synthetic scribbles 0.31-0.36. The default threshold
is 0.55. Together with the blob rule (solid eye-like pieces are not glyphs),
the tiny-region rule and the "standard Japanese characters" share, all the
junk regions in the survey are now dropped before translation.

### Stale cache entries and the shared cache file (2026-10-25)

* With the rules above in place the whole volume was re-scanned from page 1
  (a "re-sync"): 102 screens in about 6 minutes, 184 cached bubbles that no
  longer matched a text region dropped, 119 new bubbles translated in two
  requests (15 minutes); 215 page units and 1049 bubbles in the cache.
* The first chapter's title spread still showed junk afterwards: the mascot's
  face erased and lettered "Then...", and a five-letter word on its body.
  Probing the live spread showed both regions already rejected by OCR
  confidence (0.36 each, from 36 and 5 dark pieces), and a dry run of the
  re-sync on that spread dropped exactly those two bubbles and would have
  replaced the right entries (fingerprint distance 0, same sequence numbers).
* The cause was elsewhere: a GUI started earlier in Auto mode (an older build,
  cache loaded before the batch) had processed frames during the batch and
  saved its stale in-memory copy of the cache 18 seconds after the batch
  finished, undoing the pruning. The cache is therefore now merged on every
  save (the file is re-read and only the pages this process changed are
  applied on top; appended pages never share a sequence number), a cache miss
  re-reads the file first, and a re-synchronised page replaces the entry it
  matched even when the live fingerprint has drifted a few bits
  (`tests/test_cache_merge.py`).
* Two detection rules came out of the probe: a region with many dark pieces
  but hardly any characters read (fewer than a fifth of the pieces in a
  bubble, a quarter in loose text) is noise whatever its confidence (the face:
  36 pieces, 6 characters), and widely spaced horizontal lines in one text
  block (a contents page: line pitch above 1.8 line heights) are split into
  one region per line instead of being translated as a single run-on sentence.

### The book's tab switched away (2026-10-26)

A Chrome window is found by its title, which is the active tab's title: when
the owner browsed in other tabs of the same window, the reader was "not
found" and a batch could not be started, and an Auto-mode GUI would have
read whatever tab was in front. Now the window's title is checked against the
title it was picked by (same book name; page numbers in the title ignored):
the batch and Auto mode wait and say so while another tab is in front, F5 and
forwarded keys are held back, and `taslation batch --wait` waits for the
window to appear at all. The helper was checked against a live Chrome window
(title read back exactly; a chat tab is not the reader's tab). The
recommended setup is a Chrome window of the book's own (README, "Browser
readers: give the book its own window").

### Reader-made premises and the bilingual window (2026-10-26)

Translator mode (text rectangles, speaker / kind / continuation / note per
region, reading order, skipped pages, per-book detection settings, the
series sheet with glossary, character sheets and style guide) was verified
with unit tests against the pipeline, the Ollama request builder (the bubble
facts appear as fields of the JSON the model receives) and the stores, and
the window was built headlessly with every dialog opened once. The store
files are asserted to have no field that could carry a line of the book. The window's language (English / 日本語) was checked by
building it in Japanese and switching to English while it was open: labels
changed, the page, the book name and the status line stayed. Nothing in any
of this touches the network.

### A translator's pass over the real volume (2026-10-27)

Acting as the translator, the build session wrote the series sheet for the
test volume (six characters with gender, age, speech style and how they
address each other; eight glossary terms; a style guide with an honorifics
policy and five house rules) and applied it to what was already translated.
The model's own notes had read the heroine's given name wrongly and the
cached translations spelled the mascot three ways (81 + 26 + 50 occurrences
of three spellings for two mascots); `glossary apply` renamed them in 180
bubbles and in 8 note entries, after which every name has one spelling.
What the sheet does for the local model was then measured without the book:
`tools/premises_eval.py` translates 24 lines written for the test (an
invented cast with speech styles and how they address each other; speakers,
kinds and continuations recorded as a reader would; the cast, the setting
and the lines were written anew on 2026-11-12, testing the same things) with
and without the premises and scores 45 checks (names and terms rendered as
the sheet says, the pronoun a narration needs when only the sheet knows the
character's gender, honorifics kept, a split sentence left open, a rough
speaker not made polite). With `qwen3:30b-a3b-instruct-2507-q4_K_M`, two runs
each, on the lines of the time:

| | checks passed |
|---|---|
| without premises | 26 of 45 (58%) |
| with the series sheet and per-bubble facts | 40.5 of 45 (90%) |

Without premises the model read the heroine's name wrongly, misspelt the
mascot and the sidekick, gave the authority figure another title, translated
literally a kanji word the sheet keeps as a word, and turned a thought that
is a name into an English phrase; with the sheet all of these are right. The
four remaining misses were a narration that avoided a pronoun, a capitalised
term, a lower-case cry and one dropped word.

Translating the volume again with the sheet (`batch --retranslate`) was not
possible in the session: the store's subscription loan of the volume had ended
while stray batch processes (four at once, from duplicated waiting jobs)
drove the reader, and one of their clicks opened another book. That led to
the lock (one batch per viewer window), the stop when pages change shape,
and a scratch-job cleanup.

### The volume translated again with a checked series sheet (2026-10-27)

Once the volume was borrowed again, the translator's pass was finished on the
book itself.

* **Checking the facts.** The first sheet (v1) had been built on the model's
  own notes. Checked against the book (the table of contents' furigana and the
  characters' self-introductions), three of its facts were wrong: the
  reading of the heroine's family name, the reading of the sidekick's name,
  and the student council president's gender and title (a girl; 会長 is
  "President", not a male "Chairman"). The mascot's name as the sheet had it
  was right and the model's spelling with an extra vowel wrong; the OCR read
  the name's small kana as a full-size one in 10 of 95 places. Sheet v2 holds
  the checked facts, the first persons of three characters and a "meaning
  first, add nothing" rule.
* **Translating again.** `batch --retranslate` translated the whole volume
  with v1 and again with v2 (97 screens, 632 and 625 bubbles, about 50 minutes
  each on the local 30B model).
* **Comparing on the book's pages.** One more pass read all 101 screens (645
  text regions, source lines in memory only) and paired each region's three
  translations: no premises (the cache before any sheet), v1 and v2. 554
  regions had all three; 85 had no translation before the re-scan (the gain
  there comes from the current detector, not from the sheet).

| names in the 554 regions | verified spellings | wrong spellings |
|---|---|---|
| no premises | 0 | 208 |
| sheet v1 | 135 | 46 |
| sheet v2 | 166 | 0 |

| blind A/B judgement by the local model | first better | second better | same | mean score (1-5) |
|---|---|---|---|---|
| line alone: no premises vs v1 (466 differing) | 45% | 44% | 11% | 3.65 / 3.62 |
| line alone: no premises vs v2 (468 differing) | 43% | 46% | 11% | 3.90 / 3.98 |
| in context, verified facts given: no premises vs v2 | 36% | **51%** | 12% | 4.01 / **4.31** |
| in context, verified facts given: v1 vs v2 (406 differing) | 47% | 42% | 10% | 4.22 / 4.18 |

When the version without premises lost in context, the judge named the main
problem as the name (100), naturalness (68), meaning (36) or voice (34); errors
of meaning were about as frequent in v2 (37), so the gain is in names, voice and
phrasing in context, not in reading the Japanese better. The unchecked sheet
(v1) was no better than no sheet at all when each line was judged alone; the
checked one (v2) was. The two sheets' translations were judged about equal in
context (the difference is within run-to-run variation), although only v2 has
every name right. A visual check of the chapter-1 title spread showed the
translations in place, the mascot's face clear of the old "Then..." and
"Orion" junk, and the mascot's cry spelt one way; one narrow bubble on the next
spread still shows part of its Japanese column beside the English (its text
box missed a column; fixed in "Lettering against the outline" below).

Fixes made on the way: `--retranslate` replaces the entry a page matched
instead of adding a second one; `glossary apply` writes a time-stamped backup
and never overwrites an earlier one, the cache listing ignores backups, and an
alternative-style rendering ("A / B") is never written into translations; the
batch's shape guard learns the page shape from six pages before it judges, so
a cover or a single page does not end a run.

### Lettering against the outline (2026-10-28)

The narrow bubble that kept part of its Japanese column was not a one-off.
A glyph that touches a bubble's outline (in narrow bubbles the columns run
close to the curve) is joined to the outline by its anti-aliasing, so it is
not a hole of the bubble's white area: the detector left it out of the text
box and out of the erase mask. It stayed on the page next to the
translation, the OCR crop did not fully cover it, and the translation was
laid out in the narrower space that was left (words broken over lines).

The bubble detector now takes such lettering in (`recover_edge_text` in
`taslation/detect/bubbles.py`). Around each bubble it tells the inside from
the outside: what can be reached from the window's border without crossing a
dark pixel or the bubble's edge is outside, and dark pieces touching the
outside are the outline. Of the pieces inside, those that look like the
bubble's own lettering and lie against its white area are erased and read
with the bubble, then the rest of their column and the small marks beside
them. Where the outline is open nothing changes. Tests:
`tests/test_edge_text.py` (a column joined to the outline by a light-gray
fringe, on gray and white pages and in a dark bubble; a glyph outside the
outline; a mark beyond a crack in the outline; a hairline broken into dashes
and a dot tone next to the white area; an open outline).

Measured on the whole volume, rendered from the cache with the old and the
new detector (101 screens, 640 translated bubbles; counts only):

| | old detector | new detector |
|---|---|---|
| bubbles with Japanese left inside their outline | 40 | 8 |
| dark pieces left inside those outlines | 209 | 38 |
| bubbles whose erase mask grew | | 104 (13 by more than 30%) |
| translated bubbles that still match their cached translation | 640 | 640 |
| regions a batch run would send for translation | 38 | the same 38 |

Every bubble whose mask grew by more than 30% was looked at, and every one
that had leftovers before: the columns are gone and the translation is laid
out in the whole bubble instead of a strip beside the leftover Japanese. Of
the eight with leftovers, four lost most of them (a bubble framed by ink
splashes, one in speed lines, two with a column against the outline), one
keeps a "!!" that does not lie against the white area, and three small ones
keep a glyph or two: their text is cut down to its neighbourhood (see below)
and the rest of the missed column lies outside the cut.

Three safeguards came out of checking the first versions on the volume:

* **Only lettering-like pieces.** A first version took every dark piece
  against the white area; on one page it took the dashes of a hairline
  across a large white shape, which stretched the text box, and the shape
  then lost part of its tone. Pieces now have to look like the bubble's own
  lettering (at least a fifth of its typical piece's ink, at least 3 px
  thick); dots, dakuten and thin strokes are taken only beside such pieces.
* **Taking lettering in does not decide what is text.** Listing the regions
  a batch run would newly send for translation found artwork that the OCR
  filters had always rejected, read as a few characters once its box was
  wider: the pattern on a locker door, a character's vest found as a dark
  bubble with its buttons for text. The OCR stage now judges a region on its
  text box as detected before lettering was taken in, and uses the completed
  reading only when both readings pass.
* **Large white areas stay cut down.** The same list had a large white area
  of the drawing (a floor with a small figure on it), cut down to its
  lettering until then, whose text box had grown with blobs of a dark tone
  against its edge: no longer cut down, it would have been erased whole.
  Whether and where a large white area is cut down is now decided on the text
  as detected before, and lettering is only taken in inside the cut.

Bubbles whose text box grew were read again (old and new text box, in
memory) with a first version of the detector: 69 read longer with the new
box, and their 31 cached translations were dropped. A normal batch run (a
re-sync, not `--retranslate`) then scanned the volume again with the final
detector (97 screens, about 7 minutes) and translated those bubbles and two
other pending ones in one request, with the series sheet and the volume's
context (33 bubbles, about 3.5 minutes); it removed one cached bubble that no
text region matched any more. The cache went from 957 to 958 bubbles.

### Text blocks and the drawing around them (2026-10-28)

Text lettered straight onto the page (found by the text-block detector) was
erased with a mask made of the light pixels around the text, the whole text
box and a 5x5 closing. The closing took in every line up to 4 px wide that
bordered the light area, and dot screens with it; the filled text box took
whatever crossed it. Checking the narrow-bubble fix showed a mascot wiped
next to a block of narration. Measured on the whole volume, the erase cut
into dark pieces around 102 of the 114 translated text blocks, most of them
parts of the drawing.

The mask (`block_mask` in `taslation/detect/textblocks.py`) now holds the
lettering, its anti-aliasing and the light background connected to it. The
lettering is the block's pieces, the dark pieces inside its text box and
small marks set in line right next to a glyph (in two steps, for the dots of
an ellipsis). Everything else is the drawing: the mask never holds one of its
pixels, and a hole is filled only when it holds none (the counter of a glyph,
a speck of anti-aliasing). A block sometimes takes in part of a drawing; that
shows as a piece in its text box that is no glyph (longer than 56 px and than
2.5 of its glyphs, not one of its pieces and not set in one of its lines of
lettering), and then only what lies within one and a half glyphs of a line
counts. The translation is set into the room around the lettering: besides
the centred rectangle, a rectangle grown out of the lettering one pixel at a
time on every side that stays clear (`grown_rect` in
`taslation/render/typeset.py`), whichever fits the larger font. It grows from
the box of the lettering, not from the text box, which can span a drawing.

Measured on the whole volume (101 screens, 114 translated text blocks,
rendered from the cache with the old and the new mask; counts only):

| | old mask | new mask |
|---|---|---|
| blocks with a dark piece partly erased, or a long one erased whole | 102 (74,455 px) | 25 (2,895 px), all of them glyphs or marks of the lettering that reach past the block's region |
| glyph-sized pieces left inside the text box | 0 | 56 in 4 blocks: three drawings a block had taken in (a mascot, a fist, a costume) and one stroke of a hum written across a face |
| regions found, and the cache matches | 114 | the same 114 (identical on every screen) |
| font size of the translations, median / mean | 16 / 19.1 | 17 / 18.8 (47 smaller, 24 of them by 3 points or more; 39 larger) |

Every block was looked at, the original beside the new rendering. Outlines of
open and sketchy bubbles, hair, faces, fingers, mascots and dot screens that
the old mask cut into stay; the translation is set into the white of the
bubble or beside the drawing, smaller where the drawing comes close.

What checking the first versions on the volume taught:

* **Lines only where a drawing shows.** Versions that judged every block by
  its lines of lettering (pieces chained into columns or rows) kept more of
  the drawing but left Japanese on the page in a quarter of the blocks: an
  ellipsis, ruby, wavy dashes, glyphs of mixed sizes and the contents page do
  not chain up reliably. Lines now decide only in blocks whose text box holds
  a piece that is no glyph.
* **The reading direction as the detector decides it.** Choosing it by the
  direction that puts more ink into chains failed on two columns whose glyphs
  line up in rows. Columns are chosen when the pieces' centres fall into no
  more columns than rows.
* **A long dash in a line is lettering.** A wavy dash between a column's
  glyphs is longer than any glyph; it is not taken for a sign of a drawing.
* **Set the translation where the lettering was.** Grown from the text box,
  the rectangle went onto a drawing that a block had taken in.

Still open: a small drawing made of glyph-sized pieces among the text (a
mascot on one page) is taken for lettering and erased with it, as before.
Regions that translated the same text twice now overlapped instead of one of
them being set over the erased drawing; that is fixed in the next section.

From this round on the screens of the volume were saved once with
`tools/dev_snapshots.py` (101 screens, about 4 minutes) and every comparison
ran from those files (about a minute a run instead of a walk of the viewer).
The tool is for development only: the application never imports it, releases
leave it out, and `wipe` removes the files. Tests: `tests/test_block_mask.py`
(a thin-line mascot beside text on light and dark pages, a line crossing the
text box between the columns, a dot screen beside the text, a dash after the
last glyph, erasing and lettering that leave every pixel of the drawing, the
grown rectangle, a drawing taken into a block, a long dash inside a column).

### One translation per text (2026-10-28)

With the drawing kept, two old faults became visible as two translations of
the same text lettered over each other. Both are in the detection order, not
in the book:

* **A text block took in a bubble's lettering.** Text blocks were looked for
  on the whole page and merged with the bubbles afterwards, dropping a block
  only when its centre fell inside a bubble. A block made of a drawing next to
  a bubble plus the bubble's lettering had its centre on the drawing, so both
  were read and translated. Text blocks are now looked for outside the
  lettering of the bubbles found before (pieces inside a bubble's mask are
  left out; only regions closed by an outline count, not white areas cut down
  to their text).
* **A white area around a bubble was found as a bubble too.** Its holes are the
  bubble, outline and lettering, so it passed as a bubble with the same text.
  Of two regions where one lies inside the other with its text, the outer one
  now gives way when it holds nothing glyph-like outside the inner one's text
  box (its mask would take the bubble's outline); otherwise the inner one is
  part of the outer one's text and gives way (`drop_nested`).

Measured on the saved screens of the volume (101 screens, rendered from a
read-only copy of the cache; then `scan()` with the OCR engine as a batch run
would do it; counts only):

| | before | after |
|---|---|---|
| text lettered twice | 4 places | none |
| translated regions | 641 | 637, the 4 duplicates removed and nothing else |
| cached bubbles a batch run would drop | 9: 8 on the last two screens, which the last batch run did not reach, and 1 where the saved screen shows no region | 13: the same 9 and the 4 duplicates |
| regions a batch run would send for translation | 7 | 11: the same 7 and 4 found anew |

The four found anew had all been part of a block that took in a bubble's
lettering. Three of those blocks had been dropped with the bubble, so a line
of dialogue in an open bubble, a caption and a sound effect were never
translated; the fourth is what is left of a duplicate once the bubble's
lettering is left out: a small drawing with a sound effect, still taken for
lettering (see the previous section). All other changes are in regions that
were never translated and that a batch run still would not send (17 gone,
30 found). Tests: `tests/test_duplicates.py` (a
bubble's lettering is left to the bubble while narration beside it is still
found; a white area around a bubble gives way to it; a region inside the text
of another gives way; separate regions stay).

### The rest of the list (2026-10-28)

Worked from the saved screens of the volume, in the order they were listed:

* **The batch stopped four screens before the end.** The last batch run read
  97 of the volume's 101 screens and stopped at a white page with a short
  notice: page units are cropped to the ink, so that page looked like a narrow
  column and the guard took it for something that is not the book. The guard
  now judges such a frame by its paper (`paper_box`: the bright page on the
  viewer's dark background, its background read from the left and right edges
  of the capture only), which is where the book's pages always are. Paper that
  reaches well past where it has been means a panel opened over the pages (the
  viewer's end-of-book panel) and stops the batch. Run over the saved screens,
  the old guard stops at screen 98 like the real run did; the new one reads
  all 101. The end-of-book panel itself is covered by a test only: it could
  not be captured while the browser was in use.
* **Lettering reaching past a block's region.** A dash ending a column or a
  big hand-drawn glyph was erased only up to the region's edge (25 blocks,
  2,895 dark pixels left as stubs). The region is now widened to the lettering
  (a few rounds, as marks further out only show once it is wider), and a block
  never takes pieces of another block, which had made a widened region swallow
  its neighbour on the contents page. Stubs: 25 blocks to none; every widened
  region still matches its cached translation (overlap 0.69 or more, 637
  translated regions before and after). One block's translation had been set
  over a stroke of the drawing: when no centred rectangle fits, `inner_rect`
  falls back to one around the centre whatever is there, and that fallback is
  no longer used for text on the page.
* **Nested bubbles.** Of a white area around a bubble and the bubble, the
  white area now gives way when at least three quarters of its glyph-sized ink
  lies inside the bubble's outline (its convex hull); a thought bubble's
  outline drawn in short strokes and its small circles are little ink. Glyphs
  inside the outline that the bubble's mask left out are taken into the
  bubble. The thought bubble that kept its first glyph and lost its outline
  now keeps outline and circles and loses all of its lettering.
* **Smaller translations beside the drawing.** Besides the centred rectangle
  and the balanced growth, rectangles grown with a preference for width and
  for height are tried. Of 112 text blocks, 37 are set larger and none
  smaller; blocks set 3 points or more smaller than with the old mask went
  from 20 to 15, and the mean size from 18.7 to 19.4 (the old mask, which
  erased the drawing to make room: 18.8).
* **Small drawings among the lettering.** A piece far bigger than the glyphs
  that closes round two or more others (a small figure's head round its eyes
  and mouth) is drawing, with what it encloses. It changes four blocks, all
  for the better (a face beside dialogue keeps its eyes and mouth; three
  blocks over artwork lose less of it), and no lettering. A figure drawn with
  open lines next to a sound effect (screen 30) is still taken for lettering.
* **The contents page** is still one block. Its lines are 1.39 line heights
  apart, close to ordinary horizontal lines (about 1.2 to 1.3), and its page
  numbers are not part of the block, so neither the spacing nor a gap between
  entry and page number tells it apart; a rule loose enough to split it would
  split horizontal captions and messages too, and was left out.

Tests: `tests/test_batch_guard.py` (a page of text is still the book; the
end-of-book panel stops the batch), `tests/test_block_mask.py` (text on the
page is never set over the drawing; a small face among the lettering stays),
`tests/test_duplicates.py` (a broken outline and its circles stay and a missed
glyph joins the bubble).

### Lines along the bubble's shape (2026-10-28)

Measured on the saved screens, a fifth of the translations were set at the
minimum font size, and 41 of 637 did not fit even then: English is longer
than the Japanese it replaces, and the translation was set into the largest
rectangle of the bubble's own proportions that fits inside it, which in a
round or oval bubble wastes the widest part.

The lines are now laid out along the bubble's shape (`shape_layout` in
`taslation/render/typeset.py`): the bubble's interior is shrunk by a small
margin, each line takes the width of the interior at the rows it covers, the
block of lines sits as close to the centre as the fit allows, and the largest
font size at which all of the text fits wins; the rectangle (and, for text on
the page, the rectangles grown out of the lettering) is still tried, and the
larger of the two sizes is used. Words stay whole above the minimum size, as
before; characters wrap one by one for Chinese, Japanese and Thai, and
right-to-left scripts are drawn as before.

| 637 translations, saved screens of the volume | rectangle | along the shape |
|---|---|---|
| set at the minimum size (9 px) | 131 | 52 |
| of which the text does not fit at all | 41 | 4 |
| under 12 px | 241 | 101 |
| font size, median / mean | 13 / 15.6 | 17 / 19.2 |
| set larger / smaller than before | | 562 / 0 |
| rendering, per screen (20 screens, 114 translations) | 339 ms | 386 ms |

Sixteen of the changed bubbles were looked at (the largest gains and a
sample from the middle): the text follows the bubble, stays off the outline
and is readable where it was not. The four that still do not fit are tiny
regions (38 by 23 px up to 68 by 75 px) holding 19 to 69 characters of
translation; only a shorter translation would fit those (a length budget
passed to the model is the next step, and needs the translation re-run).
Tests: `tests/test_typeset.py` (a long text in an oval bubble gets a larger
font than the rectangle gives, every line lies inside the mask, words stay
whole and the block sits around the centre; words break only at the minimum
size; Chinese wraps by character and no line starts with a stop).

### Telling the model the room (2026-10-28)

Four translations still did not fit their bubbles after the lines were laid
along the shape, and 52 were set at the minimum size: too much English for a
tiny bubble. Two things were added. The model is told, with each bubble that
has little room, how many characters it has space for at the size of its
original lettering ("room", from `text_room`: the characters of ordinary
words that fit along the shape; sent only where that is less than about twice
the Japanese character count, as a translation usually runs to). And after a
translation comes back, each one is set on its mask (`layout_text`, the same
layout the renderer uses, rebuilt from the cached outline in the batch) and
those that would be set under `readable_font_size` (11 px) are asked for
again with a hard room at that size (`shorten`); a shorter version is taken
when it is a real translation that is set larger. Both run in live mode and
in the batch (one extra request per chunk, for the few that need it).

Tried with the local model on the saved screens (cache read only): the 40
pages with a translation under the readable size were read again and
translated again with the room hints, then shortened where still too small,
and compared with the cached translations; a blind judge (the same model,
order randomised) rated the fidelity of the translations that changed.

| 357 translations on 40 pages | cached | with room and shorten |
|---|---|---|
| set under the readable size | 78 | 71 |
| bubbles told their room | | 140 |
| shorter versions asked / taken | | 81 / 14 |
| characters per translation | 35.4 | 34.4 |
| fidelity of the 63 changed ones (1-5, blind judge) | 3.89 | 4.13 (new better 31, old better 25) |

A modest gain: this model keeps most of its wording whatever it is told, and
most shorter versions were not shorter or not set larger, so only 14 of 81
were taken; what remains is dense lettering in tiny bubbles. Nothing got
worse by the judge's account, and the extra request costs seconds per chunk,
so the feature stays on; `readable_font_size = 0` turns it off. Tests:
`tests/test_room.py` (a small bubble gets the hint and the shorter version, a
large one neither; a shorter version that copies the Japanese is not taken;
off means nothing is asked; the batch's regions rebuild their mask from the
outline; the room estimate), `tests/test_ollama_client.py` (the hint and the
shorten request through the stub server), `tests/test_typeset.py`
(`text_room`).

### Lighter models compared (2026-10-28)

The owner asked whether a lighter model would do, as long as the context
window stays decent. Four candidates were pulled and measured against the
default on the saved screens of the real volume (Japanese read by OCR and
kept in memory, the cache read only, the default model and the cache
untouched): Hy-MT2 7B and 1.8B (`kaelri/hy-mt2`, translation-only models that
take one user message in a fixed shape, for which `ollama_prompt_style =
"mt"` was added), Shisa V2.1 Qwen3 8B and Qwen3 4B Instruct 2507, all
Q4_K_M. Three measurements:

1. Speed on one realistic request: 40 bubbles with the series premises
   (5,392 characters), 20 earlier pairs and 10 upcoming lines, 3,800 prompt
   tokens.
2. Quality on 16 pages (162 lines) spread over the volume, each translated as
   the batch does it; a blind judge (the default model, order randomised)
   rated the candidate's line and the cached line for fidelity (1-5) and said
   which reads better. The judge is the model that wrote the cached lines, so
   a preference for its own wording is possible.
3. The premises check (`tools/premises_eval.py`: 24 lines, 45 checks, with
   the notes).

| Model (Q4_K_M), context | Size | 40 bubbles | Decode tok/s | On the GPU | Real translations of 162 | Fidelity cand. / cached | Judge cand. / cached / same | Premises checks |
|---|---|---|---|---|---|---|---|---|
| `qwen3:30b-a3b-instruct-2507` (default until 2026-10-29), 32768 | 18 GB | 125 s | 10.7 | 19% | (cached) | | | 41/45 |
| same, 8192 | | 91 s | 16.7 | 21% | | | | |
| `kaelri/hy-mt2:7b`, 8192 | 4.6 GB | 113 s | 7.3 | 66% | 126 | 3.85 / 4.15 | 49 / 66 / 11 | 17/45 |
| `kaelri/hy-mt2:1.8b`, 8192 | 1.1 GB | 15 s | 96.5 | 100% | 162 | 3.52 / 4.10 | 51 / 103 / 8 | 41/45 |
| `shisa-v2.1-qwen3-8b`, 8192 / 16384 | 5.0 GB | 202 / 245 s | 5.5 / 4.5 | 66% / 54% | 162 | 3.87 / 4.02 | 72 / 74 / 16 | 37/45 |
| `qwen3:4b-instruct-2507`, 8192 / 16384 | 2.5 GB | 32 / 84 s | 55.5 / 14.0 | 100% / 79% | 162 | 3.77 / 4.07 | 63 / 89 / 10 | 39/45 |
| same, 16384, KV cache q8_0 | | 32 s | 56.9 | 100% | | | | |

What the numbers say:

* The Hy-MT2 7B answers with valid JSON but merges bubbles: 24-26 distinct
  ids of 40, 8-9 duplicated, so 14-16 bubbles come back empty. The same shows
  in the quality run (126 of 162) and in the premises check (17 of 45 with or
  without the notes). It would need a few bubbles per request, and it is the
  slowest of the four here (it spills to the CPU).
* The 1.8B keeps the ids (31-40 of 40 over four runs) and follows the
  premises as well as the default, but translates clearly worse: fidelity
  3.52 against 4.10, the cached line preferred 103 to 51, and 32 of its lines
  set under the readable size against 15.
* Shisa 8B matches the default by the judge (72 to 74) but does not fit the
  6 GB card with a working context: 4.5-5.5 tok/s, half the default's speed
  here (the 14.3 tok/s of 2026-10-25 was measured with a short context).
* Qwen3 4B is the lighter model that holds up: 39 of 45 premises checks,
  fidelity 3.77 against 4.07, the default's line preferred 89 to 63. The
  batch's real requests (`chunk_bubbles = 100`: about 10,000 tokens with the
  reply) need a 16K context, which pushes a fifth of the model to the CPU
  (14 tok/s, still faster than the default at its 32K); with Ollama's KV
  cache quantised (`OLLAMA_KV_CACHE_TYPE=q8_0`, flash attention on, tried on
  a temporary second server on port 11435) the whole 16K context stays on
  the GPU at 57 tok/s, four times the default's speed, 3.9 GB in all. A 24K
  context is 86% on the GPU (31 tok/s). An 8K context with
  `chunk_bubbles = 40` is the other way to keep it on the GPU.

Decision (2026-10-29): the owner chose Qwen3 4B. The default became
`qwen3:4b-instruct-2507-q4_K_M` with `ollama_num_ctx = 16384` (config,
example file, README), and the 30B, the two Hy-MT2 and the Shisa models were
removed with `ollama rm` (47 GB free, from 20). Later that day a knockout
among the 4B-class models (below) made `qwen3.5:4b` the default instead. The volume's cache, written
by the 30B, stays readable: the cache file is per book and only records the
model. The KV-cache setting of the Ollama app is the owner's to make.
Scripts: `model_speed.py`, `model_quality.py`, `kv_probe.py` in the session
scratchpad; they print counts only.

### Renderings checked after translation (2026-10-29)

With the 4B as the default, the premises check (24 lines, 45 checks) lost
two to four checks against the 30B, and the misses were the sheet's own
words: a glossary term rendered in other words, a full name written as a
first name, two pronouns. The sheet says exactly what a Japanese term or
name must become, so a plain check was added (`taslation/terms.py`): after a
page or chunk is translated, every translation is compared with the
renderings the sheet requires for its Japanese: glossary terms written in
it, the form the speaker uses for someone they address, the full rendering
of a full name written out, and, when the sheet keeps honorifics, the name
with its honorific ("Kashido-san" for 樫戸さん; the name before the honorific
is one the sheet knows, or the start or end of a full name with a two-word
rendering, family name first unless the sheet shows otherwise). The match
is exact, with two allowances: uppercase lettering, and a capital on a
lowercase rendering at the start of a sentence ("Magical Girls" in
mid-sentence does not pass). The translations that miss one go back to the
model with the renderings to use (`revise`), and a revised version is taken
when it contains them all and is a real translation; a shorter version from
the size pass that loses a rendering is not taken either.
`enforce_terms = false` turns it off. The check runs wherever translations
come back: live mode, the batch, and `tools/premises_eval.py --terms`.

| Premises check, three runs each | With premises | With the renderings checked |
|---|---|---|
| Qwen3 4B, terms and names only: checks passed of 45 (mean) | 38.3 | 40.3 |
| Qwen3 4B: translations asked again / taken, per run | | 3 / 2 |
| Qwen3.5 4B, with honorifics and the exact case: checks passed of 45 (mean) | 39.0 | 43.0 |
| Qwen3.5 4B: translations asked again / taken, per run | | 2-5 / all |
| extra time per run | | 1-5 s |

With honorifics and the exact case checked, Qwen3.5 4B passes 43 of the 45
checks, more than the 30B did on its own (41). The remaining two are the
pronouns: a subject the Japanese leaves out, which no string check can
decide. A per-bubble note naming the people a line mentions, with their
gender and age from the sheet, was tried for them (`mentions_eval.py`, six
runs each way): 42.3 of 45 with the notes against 43.0 without, the pronoun
misses 1.0 against 0.7, so it was not adopted. Temperature 0 instead of 0.2
changed nothing (38.0 and 40.0 with Qwen3 4B) and was not adopted. Tests: `tests/test_terms.py` (what is
required, the case allowances, name parts and the name order read off the
sheet, honorifics, what counts as a miss, which revision is taken, the
pipeline asking and not asking, a shorter version that loses a rendering),
`tests/test_ollama_client.py` (the revise request through the stub server).

### A knockout among the 4B models (2026-10-29)

The owner asked for the promising models to be tried in turn, the best kept
and the losers removed. Four 4B-class builds that fit the 6 GB GPU with the
batch's 16K context were measured on the saved screens (Japanese read by
OCR and kept in memory, the cache read only): the default of the morning
(Qwen3 4B Instruct 2507 at Q4_K_M), the same model at Q6_K
(`hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q6_K`), Qwen3.5 4B
(`qwen3.5:4b`, thinking switched off per request) and TranslateGemma 4B
(`translategemma:4b`). The 30B is gone from this machine, so there was no
judge; its cached translations stand in: each candidate translated the
pages as the batch does it (premises, its own earlier pairs as context, the
next page upcoming) and its lines were scored against the cached ones with
chrF (character n-grams 1-6, beta 2). Closer is better on average, not line
by line. The premises check ran with the renderings checked
(`tools/premises_eval.py --terms`). Round 1: 16 pages, 162 lines, the
premises check twice; round 2 for the three Qwen builds: 40 pages, 401
lines, the premises check four times. Ollama's KV cache was quantised
(q8_0) throughout.

| Model (ctx 16384) | Size | 40 bubbles | Decode tok/s | On the GPU | Real of 162 | chrF, 162 lines | chrF, 401 lines | s/page | Premises of 45, with the check |
|---|---|---|---|---|---|---|---|---|---|
| `qwen3:4b-instruct-2507-q4_K_M` | 2.5 GB | 32 s | 57.8 | 100% | 162 | 41.4 | 44.5 | 11.5 | 39.8 |
| `...Qwen3-4B-Instruct-2507-GGUF:Q6_K` | 3.3 GB | 57 s | 23.4 | 84% | 162 | 42.2 | 46.2 | 16.9 | 39.2 |
| `qwen3.5:4b` | 3.3 GB | 30 s | 60.5 | 100% | 161 | 41.9 | 45.7 | 9.6 | 39.0 |
| `translategemma:4b` | 3.3 GB | 24 s | 68.1 | 100% | 112 | 23.5 | | 8.5 | 35.0 |

TranslateGemma does not follow the structured request (one real translation
of 40 in the big request, 112 of 162 on pages) and went out in round 1. The
three Qwen builds follow the sheet alike (39-40 of 45 with the renderings
checked; the differences between runs are as large). On closeness to the
30B, the Q6_K build and Qwen3.5 are ahead of the Q4_K_M build in both rounds
(by 1.2-1.7 chrF over 401 lines, a small but consistent step) and level with
each other (0.5 apart, within the noise). Qwen3.5 is the fastest of the
three and the only one of the two closer builds that stays wholly on the
GPU (the Q6_K build spills a sixth of itself and runs at 23 tok/s); it also
set the fewest translations under the readable size (37 of 401 against 39
and 42; the 30B's cached lines 41). The notes-extraction request was tried
with it on three pages and came back well-formed.

Decision: `qwen3.5:4b` became the default (config, example file, README,
THIRD_PARTY); the Q4_K_M and Q6_K builds of Qwen3 4B and TranslateGemma
were removed with `ollama rm`. Its vision weights went unused until the second-reader rule (below), turned off again by default after a gold transcription ("A cloud model as the judge, and a gold set"); at 4B
they cost little. Prompt variants tried on the premises set at the same time
(a rule to supply the subject English needs, a rule to write names exactly
as rendered) did not beat the prompt as it is (40.7 of 45 with the renderings
checked, against 38.7-40.0) and were not adopted; neither was temperature 0.
Scripts: `knockout.py`, `variant_eval.py`, `notes_check.py` in the session
scratchpad; they print counts only.

Index-Translate (2026-10-29, at the owner's request): Bilibili's translation
family (`hf.co/IndexTeam/Index-Translate-2B-GGUF:Q4_K_M`, 1.7 GB, and
`...-9B-GGUF:Q4_K_M`, 6.4 GB; built on Qwen3.5, 150 languages, a
constrained-translation prompt of its own with a source block and numbered
constraints, thinking off, greedy decoding recommended) was given that format
as a third prompt style (`ollama_prompt_style = "index"`) and measured in
the same round-1 setting at temperature 0, with Qwen3.5 4B measured again
at temperature 0 beside it. Both builds answered every style with 40 real
translations of 40 on the big request.

| Model, ctx 16384, temperature 0 | Decode tok/s | On the GPU | Real of 162 | chrF, 162 lines | s/page | Premises of 45, with the check |
|---|---|---|---|---|---|---|
| Index-Translate 2B, index style | 118 | 100% | 145 | 38.8 | 6.4 | 41.0 |
| Index-Translate 2B, chat style | 120 | 100% | 139 | 38.5 | 4.1 | 41.0 |
| Index-Translate 9B, index style | 8.6 | 60% | 161 | 43.6 | 49.3 | 40.0 |
| `qwen3.5:4b` | 60.7 | 100% | 162 | 44.2 | 9.9 | 43.0 |

The 2B is the fastest model tried but leaves one line in eight without a
real translation on pages and is the furthest from the 30B; it follows the
sheet well by itself (41) but its revisions are not taken (41 after the
check). The 9B does not fit the card (60% on the GPU, 8.6 tok/s: five
times slower than Qwen3.5 and slower than the 30B was), is no closer to the
30B than Qwen3.5, and writes long (48.8 characters a line against 42; 29
lines under the readable size against 16). Both were removed; the `index`
prompt style stays, tested through the stub server, for whoever tries a
later Index-Translate. Qwen3.5 4B stays the default.

### A sheet from the model's notes (2026-10-30)

The renderings check needs a series sheet, which until now only the reader
could make; on a new series the model's own notes (names with the spelling
it chose, terms) sat beside it unused. The pipeline now turns those notes
into a sheet of their own (`sheet_from_notes`; never saved) and checks
translations against the reader's sheet filled up with it, the reader's
renderings winning (`Pipeline.set_notes`, `check_sheet`); the batch hands
the notes over as soon as it has read the volume.

A/B on the saved screens with the default model, as if the volume were a
new series (no reader's sheet, no reader-made facts): the notes were
extracted from the first 16 pages (4 characters, 5 terms), the next 16 pages
(168 lines) translated with those notes as the premises. A = the
translations as they came back, B = the same after the check against the
notes-derived sheet.

| 168 held-out lines | A | B |
|---|---|---|
| lines missing a rendering of the notes sheet | 20 | 3 |
| asked again / taken | | 20 / 17 |
| chrF against the cached 30B lines | 45.4 | 44.6 |
| 30B judge, blind, on the 17 changed lines: fidelity | 4.18 | 4.24 |
| judge's preference | 9 | 8 |

The check makes the model keep to its own notes (one line in eight was
straying; one in fifty-six after), at no cost in fidelity by the judge's
account. The chrF dip is not a quality signal here: the 30B's cached lines
use the reader's renderings, which differ from the model's own choices for
two of the four characters, so lines pulled toward the notes move away from
the cache. Tests: `tests/test_terms.py` (the notes become a sheet, later
volumes override spellings but keep facts; the pipeline asks when the
reader has no sheet; the reader's rendering wins over the notes and the
reader's sheet is not written to).

### The leftovers counted again (2026-10-30)

The known leftovers were counted once more on the saved screens, rendered
from the cache (`leftover_snap.py`: dark pieces inside a translated bubble's
enclosed area that the rendering did not touch; bubbles whose centred
rectangle does not fit): of 373 translated bubbles, 6 are flagged and none
falls back to a rectangle (the three that did were text on the page, which
no longer uses the fallback). Of the six, two are the art inside the bubble
(the spikes of an ink splash, radial speed lines), one is a 2 by 6 px mark,
and three are lettering fused with or drawn over something that is not the
bubble's white: a "!!" joined to the outline at a spike, a column whose first
glyphs are outlined lettering over black hair, and two columns of outlined
lettering over the tone of a black panel. A guess that the stored outline
(a polygon at 1% of the perimeter) was cutting spikes off was measured and
refuted: the rendered masks equal the detector's (IoU 1.000 over all 373).
Erasing lettering over art would mean repainting the art, so the three stay
as they are.

### Flags for the reader, and renderings learnt from edits (2026-10-30)

Every translation now gets review flags that need no judgement to set
(`taslation/review.py`): set under the readable size even after the shorter
version was asked for; missing a rendering of the sheet even after the
revision was asked for; far longer than the Japanese (more than 3.5
characters per Japanese character plus ten) or far shorter (under half);
the OCR unsure of the Japanese (confidence under 0.6: on this volume the
median confidence is 0.98, 8.6% of the lines are under 0.7 and 2.7% under
0.6, which is where the threshold was put). The flags are stored with the
translation in the cache and cleared when the reader edits the line;
`taslation review --book NAME` lists the flagged lines page by page, and
translator mode outlines them in red with a "?". On the volume's cache as it
is (637 translations by the 30B, made before the renderings check and the
room hint existed), 172 would be flagged: 94 for a rendering, 78 for size,
17 for the OCR, 1 for length. Translations made now go through the checks
first, so fewer carry a flag.

When the reader changes a translation in translator mode and the change
replaces a rendering the sheet asks for (the old line had it, the new one
has other words exactly in its place, found by diffing the two), TASlation
offers to make the new words the sheet's rendering; on yes the sheet is
saved, the cached translations are renamed to it (`BookCache.rename`) and
the premises are refreshed. A rewrite that swallows more than the rendering
("a magical girl" to "one of them") is not offered. Tests:
`tests/test_review.py` (each flag; the flags through the cache file and the
listing; live mode flagging its translations; which edits are offered).

### A larger context for the 4B (2026-10-30)

Qwen3.5's attention keeps a long context cheap, so the batch could show the
model more: A/B on the saved screens (16 warm-up pages, 16 held-out pages,
168 lines, temperature 0 in both arms so only the context differs;
`context_ab.py`), the 30B pulled back for the day as the blind judge.

| | A: 40 earlier pairs, 60 upcoming, ctx 16384 | B: 100 pairs, 100 upcoming, ctx 32768 |
|---|---|---|
| chrF against the cached 30B lines | 49.7 | 48.7 |
| real translations of 168 | 167 | 166 |
| s/page, decode tok/s, on the GPU | 18.2, 60.0, 100% (3.4 GB) | 23.6, 57.5, 100% (3.7 GB) |
| 30B judge, blind, 80 of the 116 lines that differ: fidelity | 4.03 | 3.85 |
| judge's preference | 40 | 36 (4 same) |

The larger context fits the card but brings nothing: the lines are no closer
to the 30B's, the judge rates them a little lower, and each page takes a
third longer. The settings stay as they are.

### A second look at the drafts (2026-10-30)

A/B of a review pass (`review_ab.py`): the same 16 held-out pages, temperature
0; A = the translations as they come back, B = the same after a second
request per page that shows the model the Japanese and its draft and asks it
to correct only what is wrong (a mistranslation, dropped or added meaning, a
wrong speaker, pronoun, name or register) and to leave a good draft exactly
as it is. The 30B judged the lines that changed, blind.

| 168 held-out lines | A: drafts | B: after the review |
|---|---|---|
| chrF against the cached 30B lines | 49.7 | 50.1 |
| lines changed | | 5 |
| 30B judge on the 5: fidelity | 3.20 | 4.60 |
| judge's preference | 0 | 4 (1 same) |
| time per page | 18.2 s | + 13.7 s |

The model changes one line in thirty-four and, by the judge, makes it right
nearly every time and never worse; it reads every line to find them, so a
page takes three quarters longer. The pass is in (`review_pass`): on in the
batch, where time is not watched, off in live mode by default ("always" puts
it there too, "off" removes it). It runs before the renderings check and the
size pass, and a correction is taken only when it is a real translation.
Tests: `tests/test_review.py` (the pass corrects a draft in the batch and
not live by default; the Japanese echoed back is not taken),
`tests/test_ollama_client.py` (the request through the stub server). The 30B
was removed again afterwards (`ollama rm`; 49 GB free).

### The 30B's translations as examples for the 4B (2026-10-29)

The owner asked about distillation: teaching the small model from the
30B's cached translations. The cheapest form, showing the 4B the 30B's lines
as its "earlier bubbles" instead of its own, was measured on the saved
screens (`seed_eval.py`): 16 warm-up pages, then 16 held-out pages (168
lines) scored by chrF against the cached lines, with three context
policies. Own pairs (as the batch does it): 47.7. The 30B's pairs of the
preceding pages: 47.0. The 30B's pairs of the warm-up pages as a seed, then
own pairs: 48.6. All within a point of each other, within the noise of 168
lines: the model's wording does not move toward the 30B's by example, so
nothing was changed. Training on the cache (a LoRA on the 4B) would be the
next step up; it needs a CUDA PyTorch, bitsandbytes and PEFT on this
machine, fits a 6 GB card only at batch size 1 with short sequences, and
has only the volume's 637 pairs to learn from, so it was left for later.

### Notes for the reader (2026-10-29)

A translation may now carry a note for the reader (a pun, a wordplay or a
cultural reference the translation cannot carry): the model's JSON reply has
an optional "note" per bubble, the note is cleaned (one line, at most 120
characters, never a line of the book), kept in the cache with the
translation (`CachedBubble.note`), shown under the page with a dagger,
editable in the region editor, and listed by `taslation review --notes`.

Measured on the 16 held-out pages used by the other A/B tests (168 lines,
the reader's premises, the default `qwen3.5:4b`): with the optional key and
a rule that most bubbles get none, the model wrote 0 notes; with the key
required ("" for almost every bubble) it wrote "" 168 times. chrF against
the cached 30B lines was 48.4 and 48.2, within the run-to-run spread. So, as
with the stressed words, the default model does not use the field; the
mechanism stays for the translator (type a note in the editor) and for any
model that writes them. A larger model was not tested.

### The translation model as a second reader (2026-10-29)

Asked whether anything on the machine reads the lettering better than
manga-ocr, the one candidate was the translation model itself: `qwen3.5:4b`
takes images, and its vision weights had gone unused. Asked for a plain
transcription of one region's pixels (the whole region, enlarged twice when
narrower than 300 px; thinking off, temperature 0), it reads a crop in
0.87 s against manga-ocr's 0.18 s. On synthetic crops (clean, small,
outlined, over a tone) the character error rates were 1.1 / 0.9 / 5.4 /
0.0% for manga-ocr and 0.4 / 0.0 / 0.4 / 0.4% for the model, and the
leftover bubbles of "The leftovers counted again" that manga-ocr misread,
the model read right. Synthetic lettering is not the book, so the two were
run on every text region of the 101 saved screens of volume 1.

648 regions (everything manga-ocr judged to be text). The two readings are
identical on 243 (38%) and differ on 405; the mean character error rate
between them is 19.2%. Identical by kind: bubble 115 of 338, dark bubble 12
of 37, text 24 of 105, text-dark 3 of 16, text-on-dark 16 of 30,
text-on-page 73 of 122. Identical by manga-ocr's confidence: under 0.6, 0 of
18; 0.6 to 0.9, 19 of 147; 0.9 and above, 224 of 483. By length: five
characters or fewer 60 of 121, six to thirty 167 of 439, longer 16 of 88.

Which is right where they differ, with no ground truth: two larger
image-capable models were pulled for the day as judges, `qwen3.5:9b`
(6.6 GB) and `gemma3:12b` (8.2 GB), each transcribing 300 of the 405
differing regions and 60 of the identical ones; the reading closer to the
judge's own (CER, 0.02 margin) wins. The identical regions measure the
judges: both engines read them the same, so the reading is almost certainly
right, and qwen3.5:9b differs from it by 3.0% CER, gemma3:12b by 27.6%.
Gemma does not read manga lettering well enough to judge (its readings
differ from Qwen's by 108% CER on average: it writes something else), so its
verdicts (118 for the model, 113 for manga-ocr, 69 ties) count only as a
direction check. Under qwen3.5:9b the score is manga-ocr 136, the model 123,
ties 40 (one left empty); mean CER against the judge 20.5% for manga-ocr and
19.4% for the model. A draw, and a same-family judge might lean towards the
4B. The two judges are unanimous on 74 regions for manga-ocr and 75 for the
model.

The split by manga-ocr's confidence (the buckets were fixed before the run)
is not a draw, and runs the same way under both judges: where manga-ocr's
confidence is 0.9 or more it wins 110 to 58 (Gemma: 79 to 67); under 0.9
the model wins 65 to 26 (Gemma: 51 to 34). By kind, bubbles go to manga-ocr
(86 to 59) and free text on the page to the model (31 to 18; text-dark 7 to
2); by length the short readings go to the model (25 to 15), the middle to
manga-ocr (100 to 76), the long ones are even.

The rule adopted, `ocr_reader = "auto"` (the default) with
`ocr_reread_below = 0.9`: manga-ocr reads every region and judges whether
it is text; where its confidence is under 0.9 the model reads the region
too, and its reading replaces manga-ocr's when it is Japanese, not a
refusal and within proportion (0.4 to 2.5 times the length). On the duel's
sample this takes the better reading in 175 of the 259 decided regions
(68%), against 136 (53%) for manga-ocr alone and 123 (47%) for the model
alone under qwen3.5:9b; under Gemma 130 against 113 and 118. One region in
four is under 0.9 (165 of 648), so the model reads one in four: about 1 s
each, 1.6 s per screen.

The threshold is one of the bucket edges fixed beforehand, but which bucket
to cut at was decided on these screens, so the rule was then run as
shipped, through the pipeline's own code path, on the same screens, and
every region it changed was put to qwen3.5:9b again (the 165 unsure
regions; the 483 sure ones unchanged, as they must be). By count the rule
won clearly, 86 regions closer to the judge against 34 further away and 45
the same; by mean character error rate it lost, 41.1% against manga-ocr's
35.5%, and in the 0.75 to 0.9 band the rate doubled, 20.8% to 41.4%, while
the count there was 38 to 19 for the rule. One region explains the whole of
that: a three-character text that the model read as one character repeated
64 times (a CER of 20.67 on its own, 12 points of the mean), let through by
the length gate because that gate only applied to readings of four
characters or more. Capped at 1 per region (a wrong bubble is a wrong
bubble) the rule was already the better one, 27.0% against 32.4%, with 78
regions read right (CER 0.1 or under) against 57, and 37 read wrong (0.5 or
over) against 46.

The gate was then refined on the per-region numbers of that run (lengths,
runs and error rates; no text was kept): the upper length bound applies to
every reading, and a reading that runs in a loop is not taken
(`pipeline.looping`: one character repeated more than four times and more
than two beyond manga-ocr's own longest run, or more than half of its
three-character pieces repeated). Tried on the same numbers and not taken:
the padded text-box crop instead of the whole region (worse: 62 right and
49 wrong), taking the model's reading only when its readings of the two
crops agree (more wins lost than losses avoided), a tighter length band, a
limit on the distance to manga-ocr's reading, and a lower threshold (0.75
or 0.8 wins by the uncapped mean only through the one loop, and loses
capped). With the gate as shipped the rule takes the model's reading on 115
of the 165 unsure regions and rejects 9 (six worse than manga-ocr's, three
marginally better and wrong either way): mean CER 27.8% against manga-ocr's
35.5% (capped 25.7% against 32.4%), 83 regions closer to the judge against
28 further, 81 read right against 57, 35 wrong against 46. By confidence:
under 0.6, 12 to 3 (CER 70.1% to 38.4%); 0.6 to 0.75, 33 to 12 (46.3% to
43.2%); 0.75 to 0.9, 37 to 13 (20.8% to 15.3%). By kind: bubbles 34 to 12,
text blocks on the page 30 to 9 (read right 4 to 15, wrong 32 to 23),
text-dark 5 to 0, text-on-page 10 to 4, the six dark bubbles 1 to 2. An
oracle that always took the best of the three readings would reach 20.1%
capped: there is room left, but no signal the pipeline has at run time
finds it. The gate was chosen on the same 165 regions it is scored on, so
the last numbers flatter it a little; what the pre-set buckets of the duel
and the one runaway support is the shape of the rule (confidence under 0.9,
the whole region, a length and a loop gate), not the last decimal.

`"model"` has the model read every region (not better overall; there for a
book whose lettering manga-ocr reads badly), `"manga-ocr"` none (a
text-only model, or speed; a model that takes no images is never sent
pixels: the client asks the server). The judges were removed afterwards;
the 4B is the only model on the machine again.

Superseded the same night: judged by a cloud model against a blind transcription
of the lettering, the rule reads worse than manga-ocr alone, and the
default went back to manga-ocr (next section).

### A cloud model as the judge, and a gold set (2026-10-29)

The owner asked whether a cloud model should be the judge instead of the pulled
models, and allowed the crops to leave the machine for that (training
opt-out on their account; the application itself gets no such feature,
since an end user's opt-out cannot be guaranteed). Two blind passes over
the 101 saved screens, with nothing of the book in the logs: counts, and
the transcription itself, which went into the gold file.

Pass 1, a transcription of every region manga-ocr judged to be text (648)
and every region it dropped as low-confidence (285), from numbered contact
sheets of the crops alone, enlarged, with no engine reading in sight. That
is the gold set, kept with the snapshots as `ocr_gold.json` (933 items on
97 screens, 736 of them holding text, 13,082 characters; flags for sound
effects, cut-off or partial lettering and uncertain characters). Judge
noise: on the 243 regions both engines read the same, the transcription
differs from them by 0.9% CER (235 identical). Pass 2, a blind A/B verdict
on each of the 405 disagreements, the crop shown with the two readings in a
hidden random order, with 40 planted controls among them (a region both
engines agree on, one copy with a character dropped, swapped or
substituted): 39 of the 40 controls right.

The duel under this judge: manga-ocr 272, the model 115, ties 18 of 405
(both wrong on 15). By confidence: under 0.6, 8 to 7; 0.6 to 0.75, 28 to
24; 0.75 to 0.9, 34 to 35; 0.9 to 0.97, 62 to 20; 0.97 and above, 140 to
29. In the unsure band under 0.9, where the shipped rule used the model, 70
to 66: a coin flip, against the 65 to 26 for the model that qwen3.5:9b had
given. The same-family judge leaned towards its sibling as feared, and the
Gemma direction check was too noisy to catch it.

Against the gold set (CER on the 642 text regions manga-ocr read):
manga-ocr alone 6.9% (546 read right at a CER of 0.1 or under, 35 wrong at
0.5 or over); the model alone 16.0% (447 right, 49 wrong); the shipped rule,
"auto" at 0.9, 8.2% (536 right, 42 wrong), fixing 4 regions and breaking 9.
The only band where the model's reading is better by CER is 0.55 to 0.6 (17
regions: 41.6% to 35.0%, one fixed, none broken); from 0.65 up it breaks
more than it fixes (0.65: 1 fixed, 2 broken; 0.75: 3 and 5; 0.9: 4 and 9).
"auto" at 0.6 scores 6.7% (546 right, 33 wrong): within noise of manga-ocr
alone. By kind the model helps only on light lettering on dark (text-dark,
16 regions: 19.7% to 10.4% at 0.9) and hurts bubbles and text on the page.
An oracle taking the better of the two readings per region would reach 4.3%
(584 right, 19 wrong): the room is there, but no signal the pipeline has at
run time finds it. The A/B verdicts and the CER verdicts agree on 79% of
the disagreements; the model's wins are mostly small (71 of 114 under a
0.15 CER gap), manga-ocr's often large (101 of 272).

The regions manga-ocr drops as low-confidence: 285, of which 94 hold
lettering but only 27 are dialogue-like (the rest sound effects, cut-off or
partial lettering); manga-ocr's own reading of them is useless (CER 54% to
130% by band, 3 right of 94), and a rescue by the model fails too: asked to
read them, the model gives a reading for 284 of the 285, including all 191
that hold no text at all, and the gate lets 74 of those through against 68
real ones, reading the real ones right 6 times and wrong 45 times. A vision
model reads lettering into any crop it is given. That is why a text-only
model is never sent pixels, and why no rescue rule was added.

Decision: `ocr_reader = "manga-ocr"` is the default again. `"auto"` stays
as an option with `ocr_reread_below = 0.6`, the measured-neutral setting
(0.9 made the reading worse), `"model"` for a book whose lettering
manga-ocr reads badly. `tools/ocr_gold.py score` runs the pipeline's own
OCR path over the saved screens against the gold set and prints the same
numbers (manga-ocr: 6.9%, 546 right, 35 wrong, 101 screens in 485 s; "auto" at 0.6: 6.7%, 546 and 33; at 0.9: 8.2%, 536 and 42), so a
night batch can re-measure any change to detection, the OCR or the reader
rule without a judge. The sheets and the engines' readings were deleted;
the gold file stays with the snapshots and goes with them.

### The two residuals once more: lettering beyond a bubble's interior (2026-10-29)

The remaining residuals of "The leftovers counted again" were taken up: a
column of white lettering outside a dark bubble's interior (the blob is not
closed where the column stands, so the detector's interior and text box stop
short of it: the OCR never saw the column, the translation lacks its words
and the erase leaves it), and outlined glyphs over the black hair that
reaches into a white bubble (the OCR read the crop with the hair in it
badly: 9 characters, the first and last words missing).

For the first, `detect/beyond.py` grows a dark bubble's text box, region and
erase mask over a column of lettering that goes on past the interior on the
bubble's own black: at least three glyph-shaped pieces (not thin, not long,
not hollow) stacked within a glyph's pitch, one column wide, on a flat ground
of the interior's own level, with no strokes between the pieces, never inside
another bubble, and only where the bubble's text already reaches the edge of
its interior. The pipeline then keeps the column only when the OCR's reading
with it is the reading without it plus at least two characters (a drawing
adds nothing, or garbles the rest). On the 101 saved screens the rules
shrank from 123 bubbles grown (the first draft: art on black everywhere) to
2: the column of the residual, now read in full (34 characters, the missing
words present), and one false one, a strip of speed lines beside a dark
bubble that manga-ocr reads as ten characters of text with a confidence of
0.99, so no gate on the reading tells it apart. One true for one false is
not good enough to run everywhere: the step is off by default and a book may
switch it on (`take_columns_beyond`, in the book settings), for a volume
whose dark bubbles are badly closed.

For the second, the OCR of a light bubble whose text box reaches over the
drawing gets a prepared crop: outside the mask everything is white but the
outlined glyphs' strokes, which are black (`beyond.ocr_view`: dark pixels
within six pixels of a thin light ring). The residual bubble now reads 10
characters with the last word present, the first (two glyphs whose rings
merge with the hair's highlights) still missing. The erase paints the white
rings of outlined glyphs that lie against the drawing's dark with that dark's
colour (`erase.erase_rings`), so closed rings on black vanish; the rings
whose outer side touches the hair's white strands stay, as does the one
glyph painted as a flat white bar by the stray-lettering fill (its ground
there is the bubble's own white outside the mask). Painting rings against
any dark was tried and dropped: it blackened hairlines and tone dots next to
the lettering (five edge-lettering tests failed).

### Outlined lettering, and the lettering that ran past the bubble (2026-10-29)

Two things for text that meets the drawing. A translation set on art or a
tone (a text block outside the bubbles, mostly) now gets a contour in the
opposite colour (`typeset.busy_under`: the grey-level spread under the lines
above 35), one pixel per twelve of the size; on a flat ground nothing
changes. And the glyph-sized pieces of lettering that lie inside a bubble's
text box but outside its interior mask (the lettering that ran onto hair, a
tone, or across the outline) are painted with the colour of the drawing
around them (`erase.erase_stray`: the median of a band beyond the piece, the
interior and the other pieces left out; large components such as the outline
or the hair are never painted). Inpainting was tried first and dropped: it
pulled the outline's black into the columns next to it (six of the
edge-lettering tests failed) and left white blots on black hair.

Measured on the saved screens of volume 1 ("The leftovers counted again"
below: 373 bubbles): bubbles with leftovers 6 before, 5 after; one of the
three real residuals is gone (the "!!" fused with an outline), one is
partly better (over the black hair, one glyph's ring is now a flat white bar
because the ground beside it is the bubble's own white outside the mask, and
the other glyph's strokes merge with the hair, so nothing separates them),
and one is untouched: a column of white lettering outside a dark bubble lies
outside the detected text box, so it is a detection miss, not an erasing one.
The synthetic cases (outlined strokes on a black ground inside the text box,
a piece outside the box, a text block whose mask is the lettering itself) are
tests.

### Lettering by kind, and stressed words (2026-10-29)

What changed: the series sheet's style guide gained a lettering per kind
(thought, shout, narration, handwritten, sfx: a font family, italic, bold;
thoughts italic and shouts heavier unless the sheet says otherwise), on top
of the lettering font the sheet may suggest. Italic and bold are the family's
own cuts when this computer has them (found by the names in the font files;
a face of a collection as `path#index`), else a synthetic lean (0.21,
rendered at twice the size and brought back so the strokes keep their
weight) or a stroke (1 px from size 12, 2 from 36). A word marked *like this*
in a translation is set in bold italic and the asterisks are never drawn; the
typesetter measures the stressed runs in their own face, so the lines still
fit. Stressed words in a bold region keep its weight (the heavy cut leant
rather than a lighter italic cut).

Checked on this computer: Comic Neue Bold, the only cut `setup_models.py`
fetched until now (`--font` now also fetches Bold Italic), gets a synthetic
italic and bold; Arial Bold finds its Bold Italic and Black cuts; Segoe UI
Bold its Bold Italic, Black and Black Italic; the Noto Sans variable font a
Bold Italic cut and weight 900 for bold; Yu Gothic UI is `YuGothB.ttc#1`. A
sheet of the eight combinations (plain, italic, bold, both, for two families)
was rendered and looked at, and the series sheet dialog was built without a
screen with the new rows, checked the fonts and saved the lettering.

Measured, the model's marking: the chat prompt was given a rule to mark one
stressed word per bubble `*like this*` (most bubbles none). On the 16
held-out pages used in the earlier A/B tests (168 lines, the reader's
premises) the default `qwen3.5:4b` marked 1 line of 168, with an unpaired
asterisk; a reworded rule with examples (絶対, 本当に, まさか, a repeated
word; "about one bubble in ten") marked 0 of 168. chrF against the cached
30B lines was 45.7 without the rule and 48.2 and 48.8 with the two rules, a
spread that is run-to-run variation (120 of 168 lines differ in wording
between any two runs at the default temperature), so the rule changes
nothing measurable. Decision: the prompt carries no such rule. The markers
are the translator's tool (type `*word*` in the edit dialog) and work with
any model that writes them, and an unpaired asterisk is dropped before a
translation is kept, so a stray one never stresses half a line.

### OpenMantra as the sample dataset (2026-10-30)

The synthetic `sample_page*.png` fixtures show that the pipeline runs; they
say nothing about real pages, and the real volume measured so far cannot be
shared. At the owner's request a public sample took their place for
development: OpenMantra, the evaluation set of "Towards Fully Automated Manga
Translation" by Ryota Hinami, Shonosuke Ishiwatari, Kazuhiko Yasuda and Yusuke
Matsui (AAAI 2021), published by Mantra Inc. under CC BY-NC 4.0: five Japanese
manga series, 214 pages and 1,592 text regions, each with a box, the Japanese
text and professional English and Chinese translations. The licence keeps it
out of an MIT repository, so `tools/fetch_openmantra.py` (standard library
only, never imports the application; the owner approved the download) fetched
the GitHub archive of the dataset's main branch once: 35,917,476 bytes,
SHA-256 `028b9b893edc7babfd29c0c6a40ccbb6a01c53d679e7675a18b67566f0987ee7`,
one top folder; 217 files extracted (the annotation, the dataset's README and
`LICENSE.md`, 214 Japanese page images of 824-836 by 1170 px; the archive holds
no English or Chinese page images), 36.9 MB in
`~/.taslation/datasets/openmantra/` with `SOURCE.md` (the URL, the date, the
hash, the licence, the BibTeX). `annotation.json` is a list of series
(`book_title`, `pages`); a page has `page_index` (from 1), `image_paths`
(`ja` only), `frame` (the panels) and `text`: boxes `x, y, w, h` in page pixels
with `text_ja`, `text_en` and `text_zh` (6 boxes have no Japanese). The boxes
enclose the text with a margin: larger than TASlation's lettering box, smaller
than most bubbles. A region is therefore paired with a gold box (one to one,
largest overlap first, IoU 0.5) by the better of its two boxes; on the first
5 pages of every series (194 gold boxes) the lettering box alone paired 26% of
them, the bubble box 62%, the better of the two 66%.

`tools/openmantra_eval.py`, default settings (margins 0, manga-ocr on the CPU),
all 214 pages, numbers only; detection is scored on the regions the pipeline
reads as Japanese text, "proposed" on every region before the OCR judged it,
and the OCR on crops of the gold boxes (apart from detection) and on the
pipeline's own readings of the matched regions, CER normalised as in
`tools/ocr_gold.py` (mean over lines / all edits over all characters):

| Series | Pages | Gold | Read as text | Matched | P % | R % | F1 % | Proposed: matched (R %) | CER %, gold boxes | CER %, matched regions |
|---|---|---|---|---|---|---|---|---|---|---|
| tojime_no_siora | 46 | 334 | 284 | 263 | 92.6 | 78.7 | 85.1 | 279 (83.5) | 2.0 / 1.8 | 2.0 / 1.9 |
| balloon_dream | 38 | 314 | 261 | 223 | 85.4 | 71.0 | 77.6 | 237 (75.5) | 3.4 / 1.9 | 1.8 / 1.7 |
| tencho_isoro | 40 | 311 | 272 | 227 | 83.5 | 73.0 | 77.9 | 233 (74.9) | 2.9 / 1.8 | 2.8 / 2.5 |
| boureisougi | 36 | 274 | 219 | 192 | 87.7 | 70.1 | 77.9 | 206 (75.2) | 3.2 / 3.0 | 1.6 / 1.4 |
| rasetugari | 54 | 359 | 291 | 246 | 84.5 | 68.5 | 75.7 | 260 (72.4) | 5.6 / 4.5 | 3.8 / 3.3 |
| all | 214 | 1592 | 1327 | 1151 | 86.7 | 72.3 | 78.9 | 1215 (76.3) | 3.5 / 2.5 | 2.4 / 2.1 |

manga-ocr read 1,443 of the 1,586 gold boxes with Japanese right (CER 0.1 or
under) and 36 wrong (0.5 or over), against 6.9% on the real volume's gold
set, which also holds sound effects and cut-off lettering. 20 minutes with
another run beside it (about 3 s a page alone). The 441 gold boxes missed, counted by a
breakdown script in the session scratchpad: 209 lie mostly inside a region read
as text that holds another gold box too (two texts read as one region: a
bubble with two groups of columns, which the annotation boxes apart, or two
bubbles that touch; the region is still translated, as one), 136 are covered
by no region, 81 by a region the OCR's judgement left out (40 low-confidence,
29 noise, 12 not Japanese), 15 by a region read as text that is too large or
shifted to pair. 102 of the 441 hold one or two characters (an exclamation,
an ellipsis), which the noise rules dropped by design at the time; the
next section keeps the ones that are a bubble's short line. Of the 176 regions read as text that
pair with no gold box, 142 overlap one (the rest of a merge or a split) and 34
none: sound effects and signs, which the annotation leaves out and TASlation
translates (`translate_sfx`).

Translation of the gold Japanese (whitespace removed, as the OCR hands it
over) with `qwen3.5:4b` and the default settings, no series sheet, as the
whole-book batch does it: the model's notes of each series (13 characters and
18 terms over the five, 10 entries dropped by the plausibility check), then
runs of about 100 lines through `BatchReader._translate_units` with the 40
previous pairs and the next 60 lines as context, the review pass, the
renderings and the size checks; each line set in the detected region that matched its gold
box (1,215 boxes) or else in the gold box. chrF (character n-grams 1-6, beta
2, as in the knockouts) against the professional English, a line without a
real translation counting 0; the review's flags (the optional spelling
dictionary is not installed here, so no spelling flags):

| Series | Lines | Real | chrF | Flagged % | Small | Long | Short | Rendering |
|---|---|---|---|---|---|---|---|---|
| tojime_no_siora | 333 | 328 | 29.9 | 8.7 | 3 | 16 | 6 | 4 |
| balloon_dream | 314 | 307 | 28.2 | 8.9 | 5 | 18 | 6 | 1 |
| tencho_isoro | 308 | 304 | 35.6 | 1.3 | 2 | 2 | 0 | 0 |
| boureisougi | 273 | 268 | 34.8 | 3.7 | 6 | 4 | 0 | 0 |
| rasetugari | 358 | 357 | 23.0 | 12.0 | 11 | 22 | 9 | 2 |
| all | 1586 | 1564 | 29.9 | 7.2 | 27 | 62 | 21 | 7 |

46 minutes (1.8 s a line with the notes, the review pass and the retries); 12
requests were counted as failed and 21 pages kept a line without a real
translation (22 lines), which the batch would leave for live reading; the next
section but one found the cause and removed both. The
professional English is a localisation, not a gloss, so chrF against it runs
far below the 42 to 50 the same model scored against the 30B's lines on the
real volume (30.4 over the real translations, median line 22.2); it compares
models, prompts and settings on this set, nothing more. The quick pass, all three parts in one process on
the first 4 pages of every series (`--pages 4`, 20 pages, 140 gold boxes, 400
s): detection P 78.1%, R 63.6%, F1 70.1%; CER 5.0% / 4.9% on the gold boxes,
3.2% / 2.8% on the matched regions; chrF 34.5 over 139 lines (136 real), 1.4%
flagged.

The window on real pages: the QA driver's copy ran the real `App` in a
scratch state (no cache) on a fake viewer showing one page under an 85 px
toolbar, with manga-ocr reading and a dictionary translator built from the
gold English (a reading is lettered with the gold line it is closest to, at a
CER of 0.5 or under, else with a marker); the screenshots, of TASlation's own
window only, were looked at and deleted. boureisougi page 3 (black and white,
9 gold boxes): 12 regions, 7 read and lettered in place (6 paired with a gold
box, 5 readings exactly the gold Japanese), the Japanese erased cleanly and
nothing lettered over the drawing; missed were a cloud bubble holding two
groups of columns (two gold boxes, one region, lettered with the marker) and a
two-character bubble left as noise; the smallest lettering was 9 px (a line
standing free at the bottom) and 10 px (a narration box), the two lines the
status bar sent to review. tencho_isoro page 4 (colour, 12 gold boxes): 16
regions, 10 lettered, 5 paired. The first panel is clean; in the second two bubbles each hold two
groups (four gold boxes, two regions), and in one of them the fill erase ran
out of the bubble: a white rectangle over the cream background at its upper
left, with a stretch of the outline gone (the background is lighter than
`white_threshold`); in the third a bubble holding a line and a shout (two
gold boxes) became one region, a small line beside the first bubble has no
gold box of its own and got the marker, and a drawn sound effect (not in the
annotation) was erased and lettered.

Tests: `tests/test_openmantra.py` (the fetcher on a synthetic archive: what
is extracted, `SOURCE.md`, the refusals, `--force` removing only its own
files; the loader on a synthetic annotation in the real format; the matcher;
the scores and their aggregation); with the dataset fetched and
`TASLATION_REALDATA=1`, a real page's detection finds at least half of its
gold boxes and the OCR on its gold boxes stays under 0.4 CER.

### The OCR's judgement, rule by rule (2026-10-30)

`Pipeline._judge` decides whether a reading is dialogue to translate or why it
is not. Each rule was scored on all 214 OpenMantra pages by what its dropped
regions would be if kept: a hit (pairs with a gold box that has words), marks
(a gold box of marks only, where dropping keeps the original lettering, which
is right), part (overlaps a gold box without pairing) or none.

| Rule | Dropped before (hit / marks / part / none) | After |
|---|---|---|
| not-japanese | 322 (1 / 11 / 16 / 294) | same |
| low-confidence (`ocr_min_confidence` 0.55) | 318 (22 / 1 / 16 / 279) | same |
| noise: many dark pieces | 16 (0 / 0 / 3 / 13) | 13 (0 / 0 / 0 / 13) |
| noise: 1-2 characters under `min_short_bubble` | 55 (29 / 0 / 19 / 7) | 9 (1 / 0 / 1 / 7) |

The 29 would-be hits of the size rule all read exactly (CER 0): small bubbles
cut down to their lettering by the focus step become regions of about 45x50
px, under the 60 px of the rule. 18 of the 19 "part" lie wholly inside an
unpaired gold box with the same number of characters: the annotation boxes
the whole bubble, the region only its lettering. The would-be hits of the
confidence rule read badly (CER 30 %, 6 of 22 right).

The one change: `_short_line` exempts a reading from the two size rules when
it has one or two characters, a confidence of 0.95 or more, a hiragana or a
kanji first and only standard Japanese, at most 3 dark pieces a character,
and comes from a region with an outline of its own (bubble, dark-bubble,
text-on-page, text-on-dark). Katakana, small kana, long-vowel marks,
symbols, text blocks and readings under 0.95 are judged as before.

| | Matched | Read as text | P % | R % | F1 % |
|---|---|---|---|---|---|
| OpenMantra before | 1,151 | 1,327 | 86.7 | 72.3 | 78.9 |
| OpenMantra after | 1,179 | 1,376 | 85.7 | 74.1 | 79.5 |

Of the 49 newly read regions, 28 pair with a gold box, 18 lie wholly inside
an unpaired gold box (the same text, read exactly; the metric counts them as
false), 3 overlap one (2 small bubbles' lines, 1 the start of a longer
column), none lies outside every gold box.

On the test volume (101 screens, 1,252 regions) exactly 6 regions moved from
noise to translated: 5 small bubbles with a complete exclamation or question,
1 the first two characters of a longer column in a narrow caption. The
gold-set scores are unchanged (642 of 736 text items read, OCR CER 6.9 %).

Measured and left as it is: `ocr_min_confidence`. Lowering it to 0.50 adds 7
matched and 9 false regions on OpenMantra; raising it to 0.60 loses 17 gold
lines of the test volume. Per-kind thresholds (bubbles at 0.50, text blocks
at 0.65-0.80) helped one set and hurt the other. Not-japanese only ever sees
readings with no kana or kanji; on the test volume 202 of its 288 are the
OCR's three dots for an empty crop, and the rest Latin lettering in the art,
page numbers and imprint lines.

Tests: `tests/test_judge.py` (the four outlined kinds, the 0.95 boundary,
text blocks, katakana, small-kana, long-vowel and symbol leads, the pieces
cap, the other verdicts unchanged, one test through `_ocr_regions`).

### Joined bubbles and the cut-down's margin (2026-10-30)

Of the 441 gold boxes the baseline missed on OpenMantra, the 136 covered by
no region and the 209 read merged into another region were classified first
(numbers from crops, kept in memory only).

| Uncovered gold boxes | all |
|---|---|
| A bubble region existed, but the cut-down to its text was smaller than the gold box | 44 |
| Found, then dropped: centre outside the page unit (dark bands at the page's edge) | 27 |
| In an accepted white area, region lost later | 5 |
| In a white area the bubble detector rejected (dots or solid marks 11, two texts far apart 9, long dashes 4, a single glyph 4, holes 3, ...) | 38 |
| In no closed white area (dark background 6, art or tone 6, light-grey sky, gradients, grey bubbles 10) | 22 |

| Merged gold boxes (209, in 112 regions) | regions | boxes |
|---|---|---|
| two bubbles joined by a neck | 24 | 46 |
| two overlapping bubbles, notches at the junction | 64 | 118 |
| two texts within a glyph of each other | 12 | 21 |
| two blocks, no junction | 12 | 24 |

About 183 of the 209 are a real error (two bubbles, or two separate texts,
read and translated as one); about 26 are one bubble with two groups of
columns, which is right as one region.

Two changes in `detect/bubbles.py`. `split_lobes` cuts a white area into one
part per bubble where the white narrows to a neck between blocks of lettering
(`lobe_neck`) or where two dominant notches mark the overlap of two outlines
(`lobe_notch`; every other bend at most half as deep, so tails, clouds and
spiky shouts are not cut); only in the light pass, only when at most 20 % of
the ink is in strokes longer than 2.5 glyphs, and only when every part is
convex (solidity 0.85); when a part's lettering fails the checks on its own,
the area is read whole as before. On OpenMantra these guards keep 102 of 104
true two-bubble splits and 3 of 14 false ones. And `focus_window` /
`focus_oversized` keep a glyph of room on every side of the text
(`FOCUS_MARGIN`): all ink lies inside the text box, so only white of the same
area is added, and a short line in a small bubble is no longer a sliver under
`min_short_bubble`.

| Series | P % | R % | F1 % | merged | uncovered | judged out | partial |
|---|---|---|---|---|---|---|---|
| tojime_no_siora | 92.6 → 96.3 | 78.7 → 92.8 | 85.1 → 94.5 | 33 → 6 | 17 → 6 | 18 → 10 | 3 → 2 |
| balloon_dream | 85.4 → 94.1 | 71.0 → 85.7 | 77.6 → 89.7 | 45 → 11 | 25 → 16 | 20 → 18 | 1 → 0 |
| tencho_isoro | 83.5 → 89.6 | 73.0 → 85.5 | 77.9 → 87.5 | 51 → 18 | 21 → 16 | 9 → 8 | 3 → 3 |
| boureisougi | 87.7 → 96.2 | 70.1 → 83.6 | 77.9 → 89.5 | 34 → 0 | 31 → 24 | 16 → 17 | 1 → 3 |
| rasetugari | 84.5 → 96.1 | 68.5 → 88.9 | 75.7 → 92.3 | 46 → 0 | 42 → 24 | 18 → 14 | 7 → 1 |
| **all** | **86.7 → 94.4** | **72.3 → 87.5** | **78.9 → 90.8** | 209 → 35 | 136 → 86 | 81 → 67 | 15 → 9 |

Regions read as text 1,327 → 1,475, matched 1,151 → 1,393, read as text but
matching no gold box 176 → 82. Step by step: the margin alone gives F1 81.9,
the split 90.4, `lobe_link` 0.6 90.8. Losses: one gold box now judged
low-confidence after its lobe was cut off, one two-character lobe uncovered,
one partial. Of the 35 still merged, about 13 regions are one bubble with two
groups and 5 are separate bubbles or texts. Detection takes 130 ms a page
instead of 113 (worst 230 instead of 184). The "after" numbers come from the
same worker that reproduced the baseline exactly; the official tool agreed on
the 7 pages it finished while the machine was loaded, and should be run again
when it is free.

On the test volume (101 screens): 1,252 → 1,247 regions, five screens with one
region fewer, each a text block over the drawing that a neighbouring bubble's
wider cut-down window now covers; the split fires nowhere; against the
volume's gold set dialogue 661 of 661 kept, sound effects 75 of 75 kept,
regions without text 197 → 193. An intermediate version that also split dark
areas and stretches of page put regions on sparkle marks, a mascot's face and
the black beside the page on two screens, hence the light-only and convexity
guards.

Left for later: the 27 boxes on pages whose unit (`fingerprint.analyze`)
covers only part of the page because of dark bands at its edge; a real page
with a dark bleed at its edge loses its text the same way, and the fix changes
cache keys.

Tests: `tests/test_joined_bubbles.py` (overlap, neck and pipeline splits into
two regions with non-overlapping masks read right to left; a single bubble
with two blocks, a tail, a cloud, a spiky shout and a stretch of page not cut;
the parts share out the area; the fallback; the margin; the setting and its
TOML loading).

### Lines left without a translation (2026-10-30)

The baseline run above left 21 lines on 20 pages without a translation and
counted 12 requests as failed. Instrumented (codes and counts only), the cause
was not the model: every line left was a line of punctuation alone (an
ellipsis, "!?"), which the model gave back as it is and `is_real_translation`
rejected as a copy. Each such page was then asked for again whole, up to four
times, each retry with its own review pass (39 extra requests, 583 lines
translated again, 58 review passes instead of 19), and a retry whose pages
still missed such a line counted as failed. The professional English is the
identical string for 23 of the 34 such gold lines. The length checks in the
pipeline never see a translation: they gate the model's OCR reading against
manga-ocr's; applied to the professional English they would reject 24 % of the
lines, so they stay where they are.

| Failure kind, first attempt (all 214 pages) | before | after, run 1 | after, run 2 |
|---|---|---|---|
| HTTP error, timeout, reply not JSON, wrong shape | 0 | 0 | 0 |
| replies with the wrong number of items (ids left out) | 5 (13) | 3 (7) | 7 (11) |
| empty answer | 1 | 0 | 1 |
| the Japanese copied | 25 (all punctuation) | 0 | 0 |
| punctuation-only lines kept as their own translation | - | 28 | 25 |
| lines asked for again (requests) | - | 7 (3) | 12 (8) |
| requests counted as failed | 10 | 0 | 0 |
| lines left without a translation | 21 | 0 | 0 |
| pages left incomplete | 20 | 0 | 0 |
| chrF | 29.8 | 33.0 | 30.0 |
| flagged % | 6.9 | 5.5 | 7.4 |
| requests to the model | 160 | 78 | 90 |
| translation time | 2,875 s | 1,924 s | 2,002 s |

Four changes. `is_real_translation` takes an output identical to its source
for a copy only when the source has kana or kanji. `translate/base.py`'s
`ask_for_missing` asks again only for the lines a reply left without a usable
translation: runs of consecutive lines, at most 4 a request, with 10 translated
lines before and 6 after as context, the notes and each line's facts, then
each line still missing alone; a reply with nothing usable is an answer, not a
failure; no re-asking after a timeout, an unreachable Ollama or a missing
model. The batch's `_translate_units` commits every page a reply completed,
then re-asks the missing lines (tightened, one small review pass) instead of
retrying whole pages; a failed request on several pages is still halved. The
Ollama client reads replies leniently but safely: past a reasoning block, a
code fence, a stray prefix or suffix, trailing commas, the list under another
key or keyed by number, the text under another key; ids counted from 0 are
moved back (the old code put each translation one line off); a repeated id
keeps its first item and the leftover line is asked again; a reply cut off
keeps every complete item, notes included. The 21 recovered lines average
chrF 89 to 94. Between runs of the same code chrF moves by about 1.5 overall
and by up to 8 points per series (the sampled notes), so differences under
that are noise: use two runs, or a fixed `options.seed`. The live path with
the real model (`--mode page --pages 4`): 139 of 139 lines, 0 failed, 90 s.

Length ratio English / Japanese on the gold set (p5 / p50 / p95): 2
characters 1.0 / 2.5 / 6.0; 4-5: 0.8 / 2.2 / 5.0; 9-12: 1.1 / 2.3 / 3.9;
19-26: 1.5 / 2.3 / 3.5; a linear fit gives English about 2.4 times the
Japanese. The review flags were set from this: "long" flagged 31 of the
professional lines (2.0 %) and now flags 12 (0.8 %); "short" flagged 6 and
now 1.

Tests: `tests/test_reask.py` (46: `ask_for_missing`, the copy rule, the
lenient reading, each failure kind on a live page through the fake server, a
punctuation copy kept, Stop during a re-ask, no fan-out after a timeout, a
single batch page whose reply was unreadable).

### The erase within the outline (2026-10-30)

A GUI pass on OpenMantra's colour pages showed a white rectangle over a cream
background with a gap in the bubble's outline. The cause was not a leaking
mask: the bubble's thin brown outline breaks into pieces where its
anti-aliasing is lighter than the dark threshold, one arc lay mostly inside
the text box and passed for a stray glyph piece, and it was painted with the
median of the band around it. The same mechanism painted glyph-sized light
pieces of a pale ground dark ("rings of outlined glyphs") and broke outlines
next to hair on black-and-white pages too.

Measure, per erased region: (a) pixels changed outside the region's own
interior (the bubble's outline closed and filled, or the text box plus 4 px),
(b) changed pixels more than ΔE 6 from the original paper around them, (c)
pixels of long dark pieces turned light (a broken outline).

| | a | b | c | regions with a ≥ 25 / b ≥ 50 / c ≥ 10 |
|---|---|---|---|---|
| OpenMantra, 1,327 regions, old erase | 104,594 | 115,549 | 15,601 | - |
| OpenMantra, new erase | 12,310 | 24,265 | 136 | - |
| test volume, 648 regions, old erase | 67,624 | 79,915 | 13,398 | 162 / 151 / 58 |
| test volume, new erase | 19,882 | 40,467 | 166 | 61 / 86 / 4 |

On the test volume the new erase does less damage on 78 of the 89 screens
with erased regions, the same on 11 and more on none; lettering left inside
a mask stays 0, and glyph-sized ink left in text boxes outside the masks rises
slightly (9,101 to 9,822 px; by eye outline and drawing pieces the old erase
painted over, no Japanese). Two regressions found on the way were fixed: thick
brush strokes wider than the outline seal counted as paper (ink is now also
anything far darker than the paper), and the seal cut off the end of a column
set across the outline onto hair (a part holding lettering in the text box is
never cut). The new erase is the default for every page (`erase_mode` fill and
inpaint); `erase_mode = "classic"` is the old erase, byte-identical on all 214
OpenMantra pages and all 101 screens of the test volume, erased and lettered.
Cost: about 70 ms more per colour page, 0.1 ms per region on black-and-white.

Tests: `tests/test_erase_colour.py` (cream page with a gapped outline, a mask
leaking through a gap, a cream bubble on white, light judged against the
paper, a gradient bubble, a dark bubble, outlined lettering over hair still
erased, pale panes that are not rings, lettering on a patterned ground, the
cases on black-and-white pages too, classic mode against the old erase
rebuilt from its parts, the default keeping what classic painted over).

### OpenMantra after the quality round (2026-10-30, evening)

The official tool (`tools/openmantra_eval.py`, all 214 pages, book mode with
notes, `qwen3.5:4b`, the merged code of the day: the short-line judgement,
the joined-bubble split and the cut-down margin, the re-asked lines and the
lenient reply reading, the erase within the outline, the batched OCR) against
the morning's baseline in the section above.

| | Baseline (morning) | After |
|---|---|---|
| Detection, precision | 86.7 % | 94.5 % |
| Detection, recall | 72.3 % | 88.2 % |
| Detection, F1 | 78.9 % | 91.2 % |
| Gold boxes matched | 1,151 of 1,592 | 1,404 of 1,592 |
| manga-ocr CER on the gold boxes, corpus | 2.5 % | 2.5 % |
| manga-ocr CER on the matched regions, corpus | 2.1 % | 1.8 % |
| Lines with a real translation | 1,564 of 1,586 | 1,586 of 1,586 |
| chrF against the professional English | 29.9 | 30.8 |
| Lines the review flags | 7.2 % | 4.2 % |
| Detection and OCR | - | 266 s |
| Translation | 2,792 s | 1,694 s |

Per series after: tojime_no_siora F1 94.7, balloon_dream 89.8, tencho_isoro
87.5, boureisougi 90.9, rasetugari 92.6; chrF 31.0 / 27.9 / 38.1 / 34.4 /
24.2. chrF moves by about 1.5 between runs of the same code, so 29.9 to 30.8
is within noise; the gains that are not noise are the matched boxes, the
lines without a translation (none left) and the flags. The results file is
kept with the dataset (`results/`).

### OCR batch sized to the GPU (2026-10-30, night)

With Ollama's model and a browser open the GTX 1660 Ti had 923 MB free, less
than the 1.1 GB a pass of 8 regions needs, so "auto" used to put the OCR
model on the CPU. Now it takes the largest batch that fits (here 5). 64
OpenMantra text regions, the same texts 64/64 at every batch and on the CPU;
confidences within 9e-7 between GPU batches and 2.3e-6 between CPU and GPU.

| Regions a pass | ms per region | Need (MB) | Peak reserved (MiB) |
|---|---|---|---|
| 2 | 72.7 | 680 | 534 |
| 4 | 51.5 | 816 | 578 |
| 5 | 46.5 | 884 | 592 |
| 8 | 36.8 | 1,088 | 678 |
| CPU, 8 | 117.6 | - | - |

The driver's free count dropped from 1,071 to 507 MB when the model loaded
(564 MB, against the 558 MB torch reports), which is why a later raise of the
batch counts the model's own memory as available again.

### The cost of following a browser window (2026-10-31)

Does TASlation's following of the viewer (WinEvent hooks, a look at the window on each event) load the browser?
Measured on the development machine as the CPU time of every browser process over 60 s, the same tabs open and the
viewer's page unchanged: 1.9 s with TASlation following the window (hooks on, the page cached, nothing to
translate) against 4.8 s with TASlation closed. The difference is the browser's own activity in other tabs; the
hooks' cost is below that noise, under 2 % of one core either way. No change needed.

### OCR precision on the GPU (2026-10-31)

`ocr_precision` says what the OCR model computes in on the GPU: "fp32",
"fp16" (`model.half()`, inputs in fp16, the same beam search and batches) or
"auto". The CPU always computes in fp32. The same 64 OpenMantra text regions
as the batch measurement above (the first 64 with Japanese text, in page
order), GTX 1660 Ti, torch 2.14.1 with CUDA 12.6, best of three runs, the
allocator held to each batch's need, with Ollama's model and other programs
holding part of the GPU. The two precisions were run one after the other
while the GPU had no other work:

| Regions a pass | fp32 ms per region | fp16 ms per region | fp32 peak reserved (MiB) | fp16 peak reserved (MiB) |
|---|---|---|---|---|
| 2 | 74.4 | 180.5 | 534 | 274 |
| 5 | 47.3 | 111.4 | 592 | 310 |
| 8 | 40.7 | 98.3 | 678 | 362 |

Two more fp16 runs gave 160.7 to 177.7, 104.0 to 117.1 and 98.1 to 99.8 ms;
an fp32 run while another program used the GPU gave 85.1 and 53.3 ms at 2
and 5. The weights take 222 MiB in fp16 against 480 MiB in fp32. The texts
were the same in both precisions, 64 of 64 at every batch (and on the three
crops of the built-in check); the confidences differ by up to 6.7e-4 (fp32
against fp32 at another batch: 3e-7).

fp16 is two to 2.4 times slower on this card. It has no tensor cores, and
cuBLAS's fp16 matrix products ran at a seventh of fp32's speed there (0.3 to
0.6 TFLOPS against 2.3 to 4.5 for the shapes of the model's layers). So the
default stays "fp32", and "auto" means fp32 on this generation of GPUs. The
rule "auto" follows (`taslation.ocr.manga.fp16_pays`): fp16 is tried only on
a GPU with tensor cores, meaning compute capability 7.0 or above but not one
of the Turing chips without them (GeForce GTX 16xx, MX450/MX550,
T400-T2000). Even there it is kept only when the built-in check (manga-ocr's
own example image, whole and in two halves) reads the same texts in fp16 on
the GPU as in fp32 on the CPU. Otherwise the model goes back to fp32 for the
session, on the GPU when fp32's need fits and else on the CPU, still looked at
again by `retry_gpu`. Nobody has measured fp16's speed on such a GPU yet.

Memory needs in fp16 (`gpu_need_mb(batch, "fp16")`): 240 MiB for the weights,
52 per region of a pass and the same 64 MiB margin, so 720 MiB at 8 and 408 at
2 (fp32: 1,088 and 680). A region whose pass generates to the 300-token limit
works in up to 44 MiB in fp16 against 59 MiB in fp32. Most of that is the
fp32 scores of every step, which half precision does not shrink. Held to
720 MiB, a pass of 8 regions that all generate to the limit still read (574
MiB allocated at the peak, 716 reserved). A model in fp16 is loaded on the
CPU and halved there before it moves, so the GPU never holds its fp32
weights. A CUDA failure moves it to the CPU in fp32. Tests:
`tests/test_ocr_precision.py` (the setting, the choice and the engine with
stand-ins; with `TASLATION_GPU_TESTS=1` the real model reads the same texts
in fp16 as in fp32, in passes of 8 and 5 and through `read()`, and falls back
to the CPU in fp32).

### Recognising a book after the window was resized (2026-10-31)

A book's start offers the book whose cache holds the page on screen when the
viewer's title names none (`bookid.recognise`). Earlier the same day a page
re-fitted to a taller window seemed to land 78-93 bits from its cached
fingerprint in every capture area, as if a resize made the book
unrecognisable. Measured on the October volume's 101 walked screens (1920x1032,
a dark viewer, the page panel 1330x945 at x 295, y 87; 100 screens with pages,
199 pages): the panel re-fitted into windows 0.8, 0.9, 1.0, 1.1 and 1.25
times as wide and as tall below the browser's bars, independently (24 sizes;
the page keeps its aspect and fills the height, as the viewer re-fits it;
area-averaged down, cubic up, on the viewer's black), fingerprinted as
recognising fingerprints a frame (the hand-set area, the whole capture, the
panel found) and compared with the page's fingerprint at the original size.

| 4,776 pages re-fitted | median | p90 | p95 | p99 | max | within 6 | within 20 |
|---|---|---|---|---|---|---|---|
| the unit as analyze finds it | 1 | 5 | 8 | 45 | 128 | 93.1 % | 98.2 % |
| the original unit's box, mapped (resampling alone) | 0 | 3 | 4 | 6 | 20 | 99.4 % | 100 % |

So a resize costs a bit or two, and where it costs more the unit moved, not
the pixels: the edges cut to the ink and the gutter of a spread land some
pixels elsewhere (of the 330 pages over 6 bits, the left edge moved most in
140). The aspect check is not it: the units' aspect changed by a median 0.02 %
(p99 3.4 %), beyond the 12 % tolerance for 8 pages. Per frame, the closest page
of a spread was within 6 bits in 99.4 % of the 2,400 frames, and within 19 in
all.

The 78-93 bits came from the cache, not the resize: its fingerprints predate
this morning's page unit (the paper on a dark viewer grown through the page's
black panels). At the original size 19 of the 198 fingerprints the walk
recorded on 2026-10-28 are more than 6 bits from what analyze gives now, 17 of
them more than the 36 bits a cache lookup allows (70 to 165 bits: 79, 83, 92,
110, 115 ...); analyze without growing the paper (`analyze(grow=False)`) gives
all 198 exactly. The owner's own cache of the volume (219 pages, kept in
several areas) is met within 6 bits by 158 of today's 199 units, and by 172
of the 198 units as found before. Recognition now fingerprints each unit both
ways (`bookid.page_groups`); for the pipeline see the last paragraph.

The rule: a page within 6 bits (`cache.INDEXED_WITHIN`) of a cached page, as
before; or, after a resize, two pages on screen each within 16 bits
(`bookid.AGREE_WITHIN`) of another cached page of the same book (two frames of
one page count once). Recognised frames:

| Cache, rule | 100 screens as walked | 2,400 frames re-fitted |
|---|---|---|
| kept today, 6 bits | 100 | 99.38 % |
| kept today, 6 bits or 16 on two pages (chosen) | 100 | 99.58 % |
| kept today, 6 bits or 24 on two pages | 100 | 99.79 % |
| kept before 2026-10-31, today's units only, 6 bits | 97 | 94.63 % |
| kept before 2026-10-31, both units, 6 bits | 100 | 96.17 % |
| kept before 2026-10-31, both units, 6 bits or 16 on two pages (chosen) | 100 | 96.38 % |

The rest of the old cache's misses are re-fitted dark pages whose unit as
found before (the large blobs only) is found differently at another size: that
unit was unstable, which is why it changed. The two-page rule gains little
(5 frames: two screens at 0.8 of the height are left, one with its pages at
22 and 7 bits, the other at 80 and 19); 12, 16 and 20 bits gain the same.

False matches. The fingerprints of different pages - the October volume in
every area and both units (433), the dark-page spread of the other dev
snapshot (8), the 10 pages of another book's cache - make 101,190 pairs: none
within 20 bits; the closest are a page near the October volume's start
(screen 2) and one near its end (screen 98: 21 bits; the next pair 37), the
closest across books 52. With every frame's own screen left out of the cache
(every match would then be another page), none of the 2,500 frames (re-fitted
and as walked) was recognised at any of the rules above.
16 bits stays 5 below the closest two different pages. With the axes stretched
independently (the page's aspect changed by up to 12 %, 1,000 frames, which a
viewer does not do) 93.1 % are recognised at 6 bits and 93.3 % with the rule.

The search off the window's thread. Recognising the book at a start took
117 ms on the Tk thread for the start's two frames against 2,000 cached pages
(median of four pairs of the volume's frames; 112 ms of it the fingerprints in
every area, 4.4 ms the search; `CacheStore.identities` 0.6 ms, kept across
starts since the worker reads it at startup, 71 ms the first time). It runs in
the worker now (`_recognise_then`; the dialog opens on the "recognised" event,
with a name typed into the Book box meanwhile kept), 165 ms there with both
units fingerprinted (boxes met in several areas fingerprinted once); the Tk
thread only takes the request and opens the dialog. Gated tests:
`tests/test_realdata_frames.py` (every third screen at four sizes, a cache
kept before the unit grew); synthetic: `tests/test_bookid.py`,
`tests/test_start_flow.py`.

The pipeline's lookup. The same change had cost old caches their dark pages: a
page whose unit grew missed its entry and was translated again. So a lookup
that misses now tries the units as found before (`analyze(grow=False)`, made
once per capture and only on a miss: 16 ms on a full-HD capture, on top of the
seconds a new page takes). A unit of those that lies in the missed unit and is
kept within 6 bits (`Pipeline._lookup_before`; not the lookup's 36: at the size
it was read at, that unit gives the very fingerprint kept) is served, and
re-keyed at once: its bubbles moved from the old unit's box to today's, under
today's fingerprint and its first sequence number, the old entry removed, the
file saved (a merging save replays removals, so a batch in another process
does not bring the old entry back); two old units in one unit (the upper panels
split as a spread) become one page. Afterwards the page is found as any other,
and an edit lands on it. On the owner's real cache of the October volume (219
pages, read only for the measurement), the volume's 199 units in the hand-set
area: 160 hit before, 172 now, as many as the units found the old way (12
re-keyed, 11 at 0 bits and one at 2; the other 27 are found neither way).
On a cache of the walk's fingerprints, 17 pages are served this way; with each
screen's own pages left out of it, none (no other page gets re-keyed). The
reader's annotations are kept by fingerprint too and are not re-keyed.

### OpenMantra through the window (2026-11-01)

All five series read as a reader would: the real window, the Windows image viewer in full screen, Batch from page 1,
Back to page 1 at the end. Every series reached its last page and came back to its first; no callback error, no
empty translation, no first draft left. Pages, seconds: 46, 467; 38, 422; 40, 391; 36, 377; 54, 521. The official
tool on the same code, all 214 pages:

| | Before (evening of 2026-10-30) | Now |
|---|---|---|
| Detection, precision | 94.5 % | 94.5 % |
| Detection, recall | 88.2 % | 89.7 % |
| Detection, F1 | 91.2 % | 92.0 % |
| Gold boxes matched | 1,404 of 1,592 | 1,428 of 1,592 |
| manga-ocr CER on the gold boxes, corpus | 2.5 % | 2.5 % |
| Lines with a real translation | 1,586 of 1,586 | 1,586 of 1,586 |
| chrF against the professional English | 30.8 | 31.8 |
| Lines the review flags | 4.2 % | 4.4 % |
| Detection and OCR | 266 s | 315 s |
| Translation | 1,694 s | 1,741 s |

chrF moves by about 1.5 between runs of the same code. The tool's book mode translates and reviews in chunks and does
not run the window's drafts-then-revision path, so these numbers do not measure that path.

### Read first, translate all at once (2026-11-02)

The owner's decision: a whole-book run no longer translates while the pages turn. All 214 OpenMantra pages, the real
model, one run at a time, on the same code but for the flow; "Before" drives the window's old path (each page drafted
with what is known so far, the notes, the drafts revised in runs of 100), which `openmantra_eval.py` did not measure
until now. Its book mode now calls `BatchReader._translation_pass` itself.

| 1,586 lines | Before: drafts + revision | Runs of 100, one request | Runs of 100 + review | Runs of 12 | Runs of 30 | Runs of 30, as built |
|---|---|---|---|---|---|---|
| chrF | 35.4 | 27.7 | 28.7 | 34.2 | 34.6 | 34.2 |
| Against "Before", per line (95 % interval, pages resampled) | | -7.8 (-9.9, -5.8) | -6.7 (-8.7, -4.7) | -1.3 (-2.2, -0.3) | -0.8 (-1.8, +0.3) | -1.2 (-2.4, -0.1) |
| Lines the review flags | 5.1 % | 8.8 % | 9.9 % | 3.4 % | 1.8 % | 2.2 % |
| Lines with a translation | 1,585 | 1,586 | 1,586 | 1,585 | 1,584 | 1,585 |
| Requests failed | 2 | 0 | 0 | 0 | 0 | 0 |
| Translation, notes included | 1,859 s | 1,037 s | 1,812 s | 1,483 s | 1,156 s | 1,255 s |

Runs of 100 are the trap: page by page, chrF holds for part of a run, falls to about 9 for the rest of it and recovers
at the next run's first line, on the two series that lost most (balloon_dream 38.2 to 23.7); that is the shape of a
reply drifted off its lines, not of a lack of context, and the long and short flags double with it. The earlier
official numbers (30.8, 31.8) were taken with such runs; the "Before" column did not suffer because its first drafts
came a page at a time. A review request in the same run (the old `review_pass = "batch"` on new lines) adds 1.0, within
the noise of 1.5, for 75 % more time. The pass keeps a sliding window of pairs: the stepped window of the old drafts pass (`ContextWindow`) brought no
time here (1,337 s) and chrF 33.2. So `chunk_bubbles` is 30, and a new line has one request; a review over cached first
drafts stays, and `review_pass = "always"` puts it on every line. Against "Before": chrF 1.2 lower in the build (0.8
in the same flow's other run), under the noise between runs though the interval just misses 0; flags more than halved;
a third less model time, all of it after the page turns. These pages are short works; the notes may weigh more in a
whole volume, which this set cannot say.

Memory: 60 real pages scanned gave 489 lines; what stays per page unit (`ScannedUnit`, polygons included) comes to 22.6 KiB a
page, 4.4 MiB per 200 pages, of which the text is some 54 KB. It stays in memory only: `tests/test_batch_read_first.py`
looks through the state folder for it after a Stop.

### Single-screen operation

Keys posted to a Chrome window's render widget (`PostMessage`, no focus
change) were verified against a background Chrome window: three posted
Down keys scrolled the page while the foreground window stayed the same.
This is what lets TASlation sit on top of the viewer on one screen and turn
its pages from the arrow keys.

### Window capture through Windows.Graphics.Capture (2026-10-31)

`PrintWindow` with `PW_RENDERFULLCONTENT` did not follow a Chromium page even
when it was topmost. Windows.Graphics.Capture (package `windows-capture` 2.0.1,
MIT, by window handle) followed a Chromium page and the Windows image viewer
while they lay fully behind other windows: a page changing each second gave 7
distinct frames in 6 s, still updating after 25 s; a covered image viewer
enlarged with `SWP_NOACTIVATE` gave 1426x746 then 1906x1025 with the foreground
unchanged. A frame comes only when the window changes, and with the display off
none comes (the window keeps the display on).

The package makes no network calls of its own: a real session under the
installed network guard ended with `0 attempt(s) blocked`. Frames stay in
memory, the latest one only.

Measured on the Windows image viewer (read only, numbers only, nothing saved):
window (104, 104, 1544, 857), extended frame bounds (111, 104, 1537, 850),
client area at (112, 104) of 1424x745, frame 1426x746: the frame is the bounds.
Crop (1, 0, 1425, 745) equals `PrintWindow`'s client area to 0.02 grey levels
but for row 0, the window's top border. The viewer draws its title bar inside
the client area: 48 rows, the height of its `InputNonClientPointerSource`
child; without them the crop is (1, 48, 1425, 745), image 1424x697. In the
viewer's full screen the bar is gone though the child stays: (0, 0, 1920, 1080)
whole. An Edge window: window (300, 200, 1200, 800), bounds (307, 200, 1193,
793), frame 886x593; maximised, window (-8, -8, 1928, 1040), bounds and client
(0, 0, 1920, 1032), frame 1920x1032.

First frame 259 ms after the first call (`start_free_threaded` itself 274 ms on
an earlier run), a capture after that 5.9 ms (1426x746, converted to an RGB
image), a frame's copy in the callback 1.0 ms, closing a session 16 ms.

Posted keys, on a test window of the image viewer: `InputSiteWindowClass` took
every key, at all times, in front, fully behind and in full screen, one key one
page; the other children and the top window took them only for a while after
the window had been activated, so the one target is the input site. Keys
posted to all children at once turned one page, on this viewer; TASlation
posts to one window only all the same.

Posted keys on a Chromium window: an Edge `--app` test page counting `keydown`
took none of them, neither uncovered in the background nor covered, at the top
window or at its children, also after a real click and a real key in it (its
frames did not change either); it had no render widget child at that time. The
Chrome window of "Single-screen operation" took them. Such a viewer gets the
real key after page_turn_wait_ms as before; on the real browser reader this
still has to be tried.

### A viewer raised for a look (2026-10-31)

A Chromium page behind other windows is `hidden`, and `requestAnimationFrame`
stops; a viewer that draws there does not update however it is captured. When a
covered viewer's frame did not change after a key, or only a blank one exists,
it is made topmost with `SWP_NOACTIVATE` for up to page_turn_wait_ms, which
draws it, and put back. On a test window of the image viewer: the foreground
stayed where it was, the window was topmost and in front while raised, not
topmost afterwards, and back behind the others. Its hidden IME window moves up
with it, so the window to go back under is the nearest shown one that is not
its own. In a whole-book read the end of the book is concluded only after such a
look shows no change.

### The viewer's own full screen (2026-10-31)

On a test window of the image viewer: the real F11 took 50 ms with the foreground
handed back at once, the window filled (0, 0, 1920, 1080) by the next look and
stayed so behind other windows, posted keys turned its pages there, and the key
pressed again put it back on (135, 135, 1575, 888) in 111 ms, again with the
foreground back. A browser window ignores a posted F11, which is why the key is
real. Not tried on a browser window here: the owner's was left alone.

### Model choice

The first default was chosen by benchmark (JP-TL-Bench JA→EN) among text-only
open models that run on an ordinary PC: see README "Choosing the model". On
this machine `qwen3:30b-a3b-instruct-2507-q4_K_M` (19 GB, most of it in RAM)
decodes at 17.5 tok/s with a short context and translates a 10-line page in
17 s. On 2026-10-29 the default became `qwen3:4b-instruct-2507-q4_K_M` after
the comparison in "Lighter models compared (2026-10-28)", and the 30B was
removed from this machine at the owner's request; the same day a knockout
among the 4B-class models ("A knockout among the 4B models (2026-10-29)")
made `qwen3.5:4b` the default.
`hf.co/XpressAI/shisa-v2.1-qwen3-8b-GGUF:Q4_K_M` managed 14.3 tok/s and
`qwen3.5:9b` (multimodal, spills to the CPU) 8.3 tok/s; both were removed
again at the owner's request. For the four lighter models measured against
the default on the real volume, see "Lighter models compared (2026-10-28)".

### GUI

`taslation gui --window "Fake Viewer" --book "Dict Book"` was started, the
viewer was moved to page 1 and F5 was sent to the TASlation window by a
synthetic key press. The window showed the page with the six cached
translations composited into the bubbles and the status line
`6 bubble(s) from cache in 0.1s`, with `Network guard: ON (loopback:11434 only;
0 attempt(s) blocked)` in the status bar.

### Physical offline test

Not performed by the build session (disabling the network adapter would have
cut the build session itself). The in-process evidence above covers the same
property; please run the GUI once with Wi-Fi off to confirm on your machine.

## The OCR model (2026-11-01)

manga-ocr-charspot-small replaced manga-ocr as the only OCR, on the owner's decision. Its weights are CC BY-NC-SA 4.0:
`docs/THIRD_PARTY.md`. Everything above that names manga-ocr, `ocr_device`, `ocr_batch`, the GPU sizing or
`transformers` is the record of the OCR before this date.

**The PyTorch path.** Upstream's CPU route is ONNX Runtime, not used here (its official builds send telemetry from
native code that `netguard` cannot see). On 300 gold crops `taslation/ocr/charspot.py` read the same characters in the
same order as upstream's `model.onnx` on all 300; the largest gap in a box was 0.05 px, in a score 0.0001.

**Both OCRs through the real pipeline, on the CPU**, the same code but for the OCR, run the same day:

| | manga-ocr | charspot |
|---|---|---|
| Gold set: gold text items read as text, of 736 | 639 | 652 |
| Gold set: mean CER of those | 6.9 % | 5.3 % |
| Gold set: right / wrong (CER <= 0.1 / >= 0.5) | 542 / 35 | 566 / 26 |
| Gold set: gold non-text regions read as text | 7 | 6 |
| Gold set: text regions outside the gold set | 37 | 51 |
| Gold set: a screen, detection and OCR | 3,455 ms | 930 ms |
| OpenMantra (held out): detection F1 | 92.0 % | 92.2 % |
| OpenMantra: precision / recall | 94.5 / 89.7 % | 93.9 / 90.6 % |
| OpenMantra: corpus CER on the gold boxes | 2.5 % | 2.1 % |
| OpenMantra: corpus CER on the matched regions | 1.8 % | 1.7 % |
| OpenMantra: right / wrong on the gold boxes | 1,443 / 36 | 1,452 / 38 |
| Import + load | 6.5 s | 3.6 s |
| Memory after load (working set / private) | 1,088 / 1,624 MB | 253 / 477 MB |
| Memory, peak while reading | 1,231 MB | 951 MB (one very long crop) |

Start-up and memory are from a fresh process, the old OCR in the CUDA environment of the machine, the new one in a
fresh CPU environment (torch 2.15.0+cpu, 0.8 GB on disk). OpenMantra was the held-out check: nothing was tuned on it,
and it did not need to be.

**What was retuned.** `ocr_min_confidence` from 0.55 (a token probability) to 0.7 (the characters' mean score) with the
gate `charspot_accepts`, both chosen on the gold set: at 0.7 and a size ratio of 3 the set above; 0.6 keeps 23 more text
items at 8.1 % CER and 17 non-text regions instead of 6, and 3 against 2.5 keeps 9 more text items and the same 6.
`OCR_UNSURE` (the review flag) from 0.6 to 0.8: under it the mean CER is 31 %, above it 12 % at most; 5.7 % of the read
items are flagged (2.7 % before). `_short_line` and the rest of `_judge` were left as they were. Lines of one character
are lost on purpose; a region the reader adds skips every gate.

**Speed.** 47 ms a crop on 8 threads (median 46, p90 54), first crop 73 ms; 4 threads were no slower. CUDA does not pay:
the same crops one at a time on a GTX 1660 Ti took 85 ms on average (median 66; 50 MiB allocated), slower than the CPU,
so PyTorch is CPU only. A CUDA build left by an earlier install is kept, and the OCR runs on the CPU there too.

## Three OCR readers (2026-11-02)

charspot, manga-ocr-nar-small and manga-ocr-base-CPT-flex, by the rule in `taslation/ocr/readers.py`: charspot's gate
first, then charspot and nar; when they differ, CPT too and the medoid. Through the real pipeline (`tools/ocr_gold.py
score`, `tools/openmantra_eval.py --no-translate`), counts only:

| | charspot alone | three readers |
|---|---|---|
| Gold set: gold text items read as text, of 736 | 664 | 664 |
| Gold set: mean CER of those | 5.3 % | 4.5 % |
| Gold set: right / wrong (CER <= 0.1 / >= 0.5) | 577 / 27 | 584 / 18 |
| Gold set: gold non-text regions read as text | 6 | 1 |
| Gold set: text regions outside the gold set | 51 | 40 |
| Gold set: a screen, detection and OCR | 1,092 ms | 2,169 ms |
| OpenMantra: detection F1 | 92.2 % | 92.5 % |
| OpenMantra: precision / recall | 93.7 / 90.7 % | 94.4 / 90.8 % |
| OpenMantra: mean / corpus CER on the gold boxes | 3.1 / 2.1 % | 2.8 / 1.9 % |
| OpenMantra: right / wrong on the gold boxes | 1,452 / 38 | 1,467 / 35 |
| OpenMantra: mean / corpus CER on the matched regions | 2.1 / 1.7 % | 1.8 / 1.5 % |
| Page of 8 lines, 8 threads, machine at about 20 % | 365 ms | 1.7 to 2.1 s |
| Import + load | 2.6 s | 2.8 s |
| Memory after the first pages (working set / private) | 0.6 / 1.2 GB | 1.3 / 1.9 GB |
| Download | 44 MB | 705 MB |

On the crops of the page test charspot took 31 ms a crop, nar 114, CPT 204; CPT read 36 of 96 lines. The ports read
the same as the study's copies of upstream's code on the first 30 gold crops, both models.

The gate stays charspot's, and the others are asked only about what passed it (and about every region the reader
added). The chosen text is judged again; charspot's boxes and scores stay. A region's confidence is now mean heat times
mean classifier probability. **What was retuned**, on 736 text and 197 non-text gold crops, pad 0:

* `ocr_min_confidence` 0.7 to 0.65. All gates on: 666 text and 1 non-text (672 and 5 on the heat at 0.7). 0.6 alone
  keeps 674 and 4; 0.6 on top of the heat at 0.7 keeps 668 and 1, for two thresholds instead of one.
* `GATE_SURE_SCORE` 0.9 to 0.7: oversized crops without text reach 0.58 at most, oversized lettering runs from 0.66.
* `USUAL_MIN_SCORE` 0.8 to 0.75: the usual size moves 1 % on average over the 89 screens.
* `OCR_UNSURE` stays 0.8: in the pipeline the mean CER is 24 % under it and 6 % at most above it. 51 of 664 lines
  are flagged (7.7 %; 37, 5.6 %, before).
* `SHORT_LINE_CONFIDENCE` stays 0.95: 9 short text readings and no non-text (9 and 1 on the heat).
* `SPLIT_DISTANCE` 0.2: all three pairs that far apart flag the line. 18 of the 664 lines (2.7 %), mean CER 36 %, 5 of
  the 18 wrong lines; 16 of them were under `OCR_UNSURE` anyway.
* The pad and the size ratio are as they were. No budget for short crops: it was not measured in the pipeline.

## Ollama's prompt cache in RAM (2026-11-14)

Ollama 0.40 runs the model in llama.cpp's server (`llama-server.exe`), which keeps earlier prompts in RAM to reuse
them: up to 8 GiB, unless `--cache-ram` says otherwise, or `LLAMA_ARG_CACHE_RAM` when the command line does not (the
command line Ollama gives it has no `--cache-ram`). For PLaMo 3 Translate 2B a saved prompt carries its context
checkpoints, and a long one takes 1.5 to 2 GB; after a whole-book run the server reported `cache state: 11 prompts,
8060.077 MiB (limits: 8192.000 MiB, 8192 tokens, 14731 est)`. TASlation passes 0 to the Ollama server it starts itself
when the variable is set nowhere (`taslation/ollama_start.py`, `server_env`); install.ps1 sets `LLAMA_ARG_CACHE_RAM=0`
for the user only for an Ollama that was there before the install, since one it installs runs only while TASlation
needs it ("Ollama only while TASlation needs it" below).

**How it was measured.** Whole-book runs through the pipeline API without a window (the read-first batch, the code of
8b1261f, a scratch `TASLATION_STATE_DIR`), on the development machine (Intel Core i7-9700F, 48 GB, GeForce GTX 1660 Ti
6 GB, Ollama 0.40.16, PLaMo 3 Translate 2B Q4_K_M, context 8192). Each run had a second Ollama server of its own on
127.0.0.1:11435, with the variables under test in that server's environment only; the owner's server and the user's
environment were not touched. With the GPU: 50 two-page screens of OpenMantra (100 pages, 674 lines, 649 requests) and
`OLLAMA_KV_CACHE_TYPE=q8_0`, as this machine has it. Without the GPU (`CUDA_VISIBLE_DEVICES=-1` and the other backends
off, no KV setting): the first 8 screens (16 pages, 106 lines, about 100 requests). The working set and the commit of
`llama-server.exe` and of TASlation's process were sampled every 0.5 s. One run each (n = 1); the 2026-11-13 columns
are the runs the README's hardware figures came from (the GPU one on the owner's server, same settings).

With the GPU:

| | 8 GiB (default), 2026-11-13 | 8 GiB (default) | 0 (the install's) |
|---|---|---|---|
| llama-server, peak working set / commit | 9,757 / 11,878 MB | 9,787 / 11,907 MB | 1,737 / 3,838 MB |
| TASlation, peak working set / commit | 2,442 / 3,813 MB | 2,431 / 3,797 MB | 2,433 / 3,806 MB |
| Translation pass | 247.2 s | 249.3 s | 250.5 s |
| A line | 0.367 s | 0.370 s | 0.372 s |
| Generation | 117.0 tok/s | 115.3 tok/s | 115.5 tok/s |
| Prompt tokens the server evaluated (time) | | 52,460 (168.3 s) | 53,311 (170.6 s) |

Without the GPU:

| | 8 GiB, 2026-11-13 | 8 GiB | 2 GiB | 0 |
|---|---|---|---|---|
| llama-server, peak working set / commit | 7,349 / 7,442 MB | 7,366 / 7,460 MB | 5,715 / 5,806 MB | 4,046 / 4,135 MB |
| TASlation, peak working set / commit | 1,594 / 2,399 MB | 1,588 / 2,400 MB | 1,599 / 2,400 MB | 1,590 / 2,397 MB |
| Translation pass | 155.8 s | 160.0 s | 158.6 s | 173.2 s |
| A line | 1.47 s | 1.51 s | 1.50 s | 1.63 s |
| Generation | 16.3 tok/s | 15.8 tok/s | 16.0 tok/s | 15.7 tok/s |
| Prompt tokens the server evaluated (time) | | 6,307 (106.3 s) | 6,293 (105.5 s) | 7,338 (119.4 s) |

The server's log says which: `srv    load_model: prompt cache is enabled, size limit: 8192 MiB` (or 2048) with the cache,
``srv    load_model: prompt cache is disabled - use `--cache-ram N` to enable it`` with 0. Its GPU memory was 1,951 MB
both ways.

**Where the time goes.** In each run with a cache, one request found an earlier prompt in it (`found better prompt with
f_keep = 1.000, f_sim = 0.970` on the CPU) and did not evaluate 850 to 1,050 tokens again. On the GPU that is about 2 s
of 250; on the CPU, where a long prompt takes 10 to 13 s, it is the whole difference: 8 % on 16 pages. How often such a
hit comes on other books was not measured. Between the two days the same settings differed by 1 % on the GPU and 3 % on
the CPU, so the GPU's 0.5 % is no difference.

**Decision.** 0 on every computer: the cache costs about 8 GB of RAM with a GPU for no speed, and 3.3 GB without one
for about 8 %. A 2 GiB cache would have kept that 8 % for 1.7 GB.

**How the variable reaches the server.** Read from the processes' environment blocks: the owner's Ollama tray app and
the server it started have every variable of the user (`HKCU\Environment`), `OLLAMA_KV_CACHE_TYPE=q8_0` among them;
`ollama serve` started with `LLAMA_ARG_CACHE_RAM=0` passed it on to its `llama-server.exe`, whose command line has no
`--cache-ram`. Not shown here, because it needs the owner's environment or the owner's Ollama: the variable set for
the user reaching the tray app when Windows starts it, the installer's restart of the tray app, and programs started
from the Start menu before Explorer reads the change (tests with fakes only). TASlation no longer starts the tray app:
the server it starts itself is shown with the variable in the next section. No computer with 8 GB of RAM was tried.

## Ollama only while TASlation needs it (2026-11-14)

The owner's decision: Ollama runs only while TASlation needs it, unless the person runs it themselves. TASlation starts
`ollama.exe serve` itself, hidden (never Ollama's tray app, whose first start makes Ollama start with Windows), writes
down that it did (`ollama-started.json` in the data folder: the server's pid, path and start time, the address and the
TASlation processes using it; no book text), and stops it when it ends, but only while it is still that process, no
other TASlation the record names runs, and Ollama lists no loaded model but TASlation's own. install.ps1 leaves an
Ollama it installs not running and not starting with Windows, and imports the model through a hidden `ollama serve` of
its own; an Ollama there before stays as it is, but for one question, default no, when it starts with Windows.

**How it was tried.** On the development machine (GeForce GTX 1660 Ti 6 GB, Ollama 0.40.16), with TASlation's own
routines (`server_env`, `find_ollama`, `launch`, the record, `finish_all`) on a second Ollama server of its own:
`OLLAMA_HOST=127.0.0.1:11435`, a scratch `OLLAMA_MODELS` holding a copy of qwen3.5:4b, also under a second name that
TASlation does not know (`foreign-test`, for "another program's model"), on the CPU (`CUDA_VISIBLE_DEVICES=-1`), and a
scratch data folder. `startable` keeps any address but 11434 out of `OllamaStarter.start`, so the record was written as
`start` writes it after its launch. The owner's server on 11434 was only looked at (its process and start time before
and after). One run each (n = 1).

| | TASlation's model (qwen3.5:4b) | Another program's model (foreign-test) |
|---|---|---|
| `server_env` adds | `LLAMA_ARG_CACHE_RAM=0`, `OLLAMA_KV_CACHE_TYPE=q8_0` (6 GB GPU) | the same |
| The server answers after | 2.0 s | 2.0 s |
| In the environment block of `ollama.exe`, `llama-server.exe` and their consoles | both variables | both variables |
| `finish_all` | `STOPPED`, 0.25 s | `FOREIGN` (names 1 model, foreign-test:latest), 0.02 s |
| Processes left | none; the record gone | all four; the record gone, so TASlation no longer stops it |

The stop was Ollama's own: the helper attached to the server's console and its CTRL_BREAK was delivered in 0.05 s, and
the server and the model's server were gone 0.16 s later, so `terminate` found nothing left to end. The server left in
the second run was then ended by `stop_server` (0.22 s), as a test step. Afterwards nothing listened on 11435, the
scratch store and data folder were deleted, and the owner's server was the same process as before, still answering.

**Not shown here.** The tray app's first start making the Startup shortcut after a winget install, and install.ps1
removing it (the install check shows it on a fresh runner, with winget), a crash of TASlation and the next start's
adoption of the record (tests with fakes), and a person starting Ollama themselves while the server TASlation started
runs (the address is taken by then; TASlation's end leaves that server running only when a model other than
TASlation's is loaded in it).

## A translator's hint and PLaMo (2026-11-15)

The region editor's "Hint for the model" (a pun, who is addressed) went to the chat translator only (Qwen3.5 4B and a
model of the reader's own: the bubble's "note"). PLaMo 3 Translate 2B, the model of every other target language, has
no field for it in its PFML3 prompt, and the hint was dropped without a word, also on Ask again. The one place its
prompt has for free text is the reference ``context`` block, so the hint was tried there.

**How it was measured.** `tools/hint_eval.py` on the development machine (GeForce GTX 1660 Ti 6 GB), requests only to
the owner's Ollama (0.40.16, PLaMo 3 Translate 2B Q4_K_M, the app's options: temperature 0.2, context 8192), seeds 1
to 3. 26 Japanese lines written for the test, each with a hint that settles what the line leaves open and a pattern
that a translation following the hint matches: who did it (3 lines), he or she (3), to whom (2), one or many (4), how
a name is read (6), what a title means here (3), how politely (2), what is meant (3); 78 answers a condition. Beside
them 10 lines with a hint that should change nothing, 10 shouts, 10 sound effects and 10 long lines for the room.

| ``context`` of the line | Hint followed (of 78) | Of the answers wrong without it: mended | Spoilt |
|---|---|---|---|
| none (the prompt the app sends) | 17 | | |
| the hint alone | 38 | 21 of 61 | 0 |
| "Note: " and the hint | 36 | 19 of 61 | 0 |
| "About this line: " and the hint | 34 | 17 of 61 | 0 |
| "Translator's note on the line: " and the hint | 32 | 15 of 61 | 0 |
| the same, the hint written in Japanese | 35 | 18 of 61 | 0 |
| a made-up series sheet alone | 21 | | |
| the sheet, then "Translator's note on the line: " and the hint | 36 | 15 of 57 | 0 |
| the sheet, then the hint alone (what the app sends with a series sheet) | 36 | 15 of 57 | 0 |

The counts are those of the tool's run; the requests of the rows but the last, asked once before (the same prompts and
seeds, the server answering other requests as well), gave 18 of their 624 answers other words and moved one count by
one (the "note" row had 31, 14 mended).

With the hint alone, by what it settles (without a hint in brackets): how a name is read 15 of 18 (12), a title 6 of 9
(0), he or she 5 of 9 (0), one or many 6 of 12 (3), who did it 3 of 9 (0), what is meant 3 of 9 (2), to whom 0 of 6
(0), how politely 0 of 6 (0). A name the hint gives another reading kept the model's: 海 came back "Umi" after "the
Sea", never "Kai". The hints that should change nothing left the words as they were in 23 to 25 of 30 answers (25
with the hint alone), the rest a synonym ("already" for "soon"); no answer held words of a hint. A line of ``context`` also made the model end
a sentence with a full stop where it left it out without one ("Be quiet" / "Be quiet.").

The kind and the room, as one line of ``context`` each: "Kind of line: shout" gave 3 of 30 shouts an exclamation mark
or capitals (1 without it); "Kind of line: sound effect (sfx)" changed 17 of 30 answers, 14 of them from a romanisation
to an English sound word (ガシャン "Gashan" to "Crash", ゴクリ "Gokuri" to "Gulp") and 3 to a wrong one (ザーッ, rain,
to "Zzzz"); "Room: the translation must fit in N characters", N being 60 % of the answer without it, brought none of
30 answers within it, either way (60.7 and 59.5 characters on average).

**Decision.** A first reading of these numbers left PLaMo without the hint: it was followed in fewer than half of the
answers, best where the series sheet settles it every time (a name, a term: the PLaMo glossary), and never for to
whom or how politely. It was decided the other way: a reader who writes a hint and presses Ask again is asking for
exactly this attempt, and mending a third of the answers that were wrong without it, spoiling none that were right,
is better than ignoring what they wrote. So the hint goes into the ``context`` of its own line, alone, after the
speaker (`PlamoTranslator._context`): with nothing else it is the "hint alone" prompt above, with a series sheet the
"sheet, then the hint alone" one (`tests/test_plamo.py` holds the app's prompt to the measured one). Asked through
the app's own path (`PlamoTranslator.translate_page` with the region's note, seed 1), the 26 lines came back word for
word as measured in 24 answers and followed the hint as often (12). A line without a hint goes as before, byte for
byte; the kind and the room stay out.

The hint of one line never reaches another line's prompt: the earlier pairs are the Japanese and the translations,
the Japanese after a line is only the Japanese, and a run of bubbles joined into one request (a sentence that goes on
in the next bubble) carries no hint, since it would be the reference of the run's other bubbles as well; when the
joined answer does not split back and each bubble is asked by itself, the hinted bubble's request carries it, and Ask
again asks one bubble. The answer to a line with a hint is, like every answer, an earlier pair of the lines after it.
A hint can change the wording of its own line where it need not (5 of the 30 neutral answers with the hint alone: a
synonym, a full stop added), and the manual says so.

The translator says how far its model follows a hint (`hint_support`: "sometimes" for PLaMo, "follows" for the chat
translator), and the region editor says under the hint, in every window language, that this model follows a hint
only sometimes (about half the time in a test), best for how a name or term is read and who or how many are meant,
and that names and terms that must always come out the same belong in the series sheet. The line takes two or three
lines of text (34 to 49 pixels) and leaves the editor's width as it is in every window language.

**Not shown here.** Lines of real books, other target languages than English, more seeds or another wording of the
hints; a hint after a speaker ("Speaker of the line: ...", the prompt of a line the reader gave a speaker) or before
the Japanese that follows a line (a bubble that goes on, asked by itself); the patterns are rough (a "she" anywhere
passes). The kind "sfx" may help a sound effect the reader asks to be
translated (sound effects are left as drawn by default, `translate_sfx`), but 3 of the 17 changes were wrong, and it
was not tried on sound effects of real pages: not shipped.

## Line reuse (2026-11-15)

The owner's decision: a short line already translated in the book or its series takes that translation again, without
a request (`taslation/linememo.py`, the setting `reuse_lines`), for speed and so that the same line reads the same. The
rule was chosen on OpenMantra: its five works, 214 pages, 1,547 lines with a word in them (the gold transcription's
lines of punctuation alone left out). Each work is a book here, so "within a book" is within one work, and nothing was
measured across the volumes of a series. The scripts printed counts only, never a line.

**(a) Repeats within a book.** A later occurrence is a line whose key (`linememo.normalise`: NFKC, no whitespace, a run
of dots one ellipsis, of long-vowel marks, dashes and tildes one long-vowel mark, of ! and ? one mark, a symbol written
twice once, a trailing full stop or comma off) came earlier in the same work; length in characters of the key.

| Length | Lines | Later occurrences | Share of the lines |
|---|---|---|---|
| 1-2 | 101 | 25 | 24.8 % |
| 3-4 | 297 | 25 | 8.4 % |
| 5-6 | 225 | 10 | 4.4 % |
| 7-10 | 330 | 1 | 0.3 % |
| 11-15 | 329 | 0 | 0 |
| 16+ | 265 | 0 | 0 |
| All | 1,547 | 61 | 3.9 % |

The key's merges add 3 later occurrences to the 58 of the bare text without whitespace (40 keys repeat instead of 38).
Repeats grow with the book: 2.5 % of the lines of each work's first half were met before in it, 5.4 % of its second
half. 22 keys occur in two or more works (never reused: they are other books).

**(b) The professional translations of a repeated line.** For each later occurrence, whether the dataset's English and
Chinese for it are those of the first occurrence (English lower-cased, punctuation off; Chinese letters and digits
only), and the chrF of its English against the first one's.

| Length | Later occurrences | English the same | Chinese the same | Both | chrF against the first |
|---|---|---|---|---|---|
| 1-2 | 25 | 64.0 % | 68.0 % | 48.0 % | 66.9 |
| 3-4 | 25 | 36.0 % | 68.0 % | 24.0 % | 52.4 |
| 5-6 | 10 | 40.0 % | 90.0 % | 40.0 % | 46.9 |
| 7-10 | 1 | 0 | 0 | 0 | 0 |
| All | 61 | 47.5 % | 70.5 % | 36.1 % | |

By kind: kana of up to three (35 later occurrences) 48.6 % / 62.9 % the same, longer kana (10) 40.0 % / 90.0 %, with a
kanji or other characters (16) 50.0 % / 75.0 %. So the translators gave a repeated line the same English only half the
time: the reply fitted to its scene ("Huh?" here, "What?" there) as much as another sense, and this cannot tell the two
apart. Hence (c) judges reuse against the reference, not against the first occurrence.

**(c) Our model on identical lines.** The app's translator (PLaMo 3 Translate 2B through the owner's Ollama,
`taslation-plamo3-translate-2b`, requests only) on every line with the gold geometry, as the whole-book run translates
(`BatchReader._translation_pass`, two runs) and page by page (`Pipeline._translate_regions`, one run), with no reuse
(the evaluation's pipelines have no cache). For each later occurrence: whether the model's translation equals its
translation of the first occurrence (normalised as above), and the chrF against the professional English of the fresh
translation and of the first occurrence's (what reuse would have set), paired, with a 95 % bootstrap interval (2,000
resamples of the later occurrences). In the whole-book table each later occurrence counts twice, once per run.

Whole-book run:

| Length | Later occurrences | The same as the first | chrF fresh | chrF reused | Reused - fresh (95 %) |
|---|---|---|---|---|---|
| 1-2 | 50 | 98.0 % | 44.3 | 44.8 | +0.5 (-0.0, +1.2) |
| 3-4 | 50 | 84.0 % | 37.4 | 39.2 | +1.9 (-4.1, +8.7) |
| 5-6 | 20 | 100 % | 40.9 | 37.2 | -3.6 (-9.1, +0.0) |
| 7-10 | 2 | 0 | 29.5 | 31.3 | +1.8 |
| All | 122 | 91.0 % | 40.7 | 41.1 | +0.4 (-2.2, +3.2) |
| Kana of up to three | 70 | 94.3 % | 41.7 | 41.5 | -0.1 (-2.1, +1.3) |
| Longer kana | 20 | 85.0 % | 27.0 | 36.3 | +9.3 (-0.0, +23.3) |
| With a kanji or other | 32 | 87.5 % | 46.9 | 43.0 | -4.0 (-10.2, +0.2) |

Page by page (one run):

| Length | Later occurrences | The same as the first | chrF fresh | chrF reused | Reused - fresh (95 %) |
|---|---|---|---|---|---|
| 1-2 | 25 | 84.0 % | 56.1 | 48.7 | -7.4 (-20.6, +2.9) |
| 3-4 | 25 | 76.0 % | 42.5 | 40.6 | -1.9 (-14.4, +9.0) |
| 5-6 | 10 | 100 % | 46.1 | 42.5 | -3.6 (-10.9, +0.2) |
| 7-10 | 1 | 0 | 36.2 | 30.6 | -5.5 |
| All | 61 | 82.0 % | 48.6 | 44.1 | -4.5 (-11.4, +2.3) |
| Kana of up to three | 35 | 85.7 % | 47.6 | 44.3 | -3.3 (-10.9, +3.6) |
| Longer kana | 10 | 80.0 % | 32.2 | 41.6 | +9.4 (-0.0, +28.0) |
| With a kanji or other | 16 | 75.0 % | 60.8 | 45.0 | -15.8 (-32.9, -0.3) |

("The same" compares letters and digits; chrF also sees punctuation, so a line "the same" can still differ a little.)
The means rest on a few lines. Of the 57 later occurrences within the rule below, the model translated 4 and 5
otherwise than the first time in the two whole-book runs and 10 page by page; most of those move chrF by less than 5,
and the means are set by a handful that match the reference word for word one way and not the other (about 90 points
each): page by page, one two-character line with a kanji, met twice more, whose first translation missed and whose
later ones matched (the whole -15.8 of that kind), and in every run one longer kana line the other way (its +9.3 and
+9.4). Pooled over the three runs, within the rule: -0.4 (-3.3, +2.5), n = 171; kana alone +0.9 (-2.2, +4.3), with a
kanji -4.4 (-11.0, +0.1).

Between the two whole-book runs, 84.6 % of all lines got the same translation in the same place, and 96.0 % of the
repeated ones (the page-by-page flow had one run): the model's answer to a short line hardly changes from run to run.

**The rule.** At most 10 characters once normalised (`MAX_CHARS`), of any kind: within that length a reused
translation is as close to the reference as a fresh one, within the noise in each flow and pooled, and longer lines
hardly repeat (one later occurrence in 7-10 characters, none beyond). The one interval that misses 0 (page by page,
with a kanji) is one line, so lines with a kanji are not left out. That line shows what reuse risks: a first
translation that misses is repeated wherever the line comes back, where fresh requests would have varied; a correction
in translator mode, made once, then reaches them all. Not a line that continues in the next bubble or from the one
before (`translate.continuation`: a piece of a sentence; 327 of the 1,547 lines, 4 of the 61 later occurrences). The
speaker and the kind the reader gave are part of the key, and a line with a hint for the model is never reused:
OpenMantra has neither, so that is a choice of caution, not a measurement. The scope is one translator, model and
target language. Only merges that change no reading: hiragana against katakana, small kana, ! against ?, and a
trailing ellipsis stay apart. What is kept is the answer as the page got it, spelt as the series sheet spells
(`terms.spelt_right`, which both ways of translating apply to a fresh answer); before it is set again, a kept
translation is held to the sheet as it is now (a near spelling of a rendering put right by the same function, one
still missing a rendering asked for again). The series is the one the series sheet goes by (`notes.sheet_key`: the
Series field, so "Some Title 3巻" kept before the two fields and "Some Title 4" are one series).

**What is stored, and what it reveals.** In the book's cache file (`lines`, before the pages), sealed with it: per
translator, model and language, HMAC-SHA-256 of the key with a random 32-byte secret of the book's own, cut to 16 bytes,
and the translation, marked when a person wrote it; the secret is in the same file. Never the Japanese:
`tests/test_linememo.py` looks for it in the file's bytes and in the opened file. Whoever can open the file (its Windows
user, or anyone with an export and its passphrase) sees the translations, which the cache holds anyway, how many short
lines were kept, and, holding the secret, can test whether a line they guess was in the book; a short exclamation is
easy to guess. Without the secret, two hashes of one line in two books cannot be told to be the same line. The file is
listed, deleted, exported, imported and renamed as the cache is; an import into a cache that has lines of its own adds
only those it lacks.

**End to end, page by page.** The page-by-page flow once more with reuse on (the evaluation's pipeline given a cache
that holds only a `LineMemo`, one per work), so that a page with a reused line sends the model a request without it:
PLaMo then answers the page's other lines without the reused pair in their history (`PlamoTranslator.translate_page`
carries the request's own lines done so far). Each line against the same line of the run without reuse:

| Lines | n | The same as without reuse | chrF without | chrF with | With - without (95 %) |
|---|---|---|---|---|---|
| Reused | 61 | 83.6 % | 48.6 | 45.0 | -3.5 (-10.5, +2.9) |
| Asked, on a page with a reused line | 330 | 83.9 % | 39.2 | 39.1 | -0.1 (-0.8, +0.6) |
| Asked, on a page with none (run to run) | 1,156 | 83.7 % | 39.6 | 39.8 | +0.3 (-0.1, +0.7) |

The lines asked beside a reused one differ from the run without reuse as often as the lines of pages with none, which
are the run-to-run noise: leaving the reused pair out of the request costs them nothing measurable, so the request is
left as it is. 62 lines were reused, 54 of them those the rule counted above; the other 8 are lines the pipeline's
own judgment of a continuing sentence and its key let through where the analysis's approximations did not.

**What it saves** (the whole-book row from the runs without reuse, the time of a request of a repeated line from the
run's own timing of that line, else the run's mean; the page-by-page row measured with reuse on, its time from that
run's own timing of the lines' first occurrences):

| | Lines reused | Requests saved | Translation time saved |
|---|---|---|---|
| Whole-book run | 54 of 1,547 (3.5 %) | 54 of 1,434 (3.8 %) | 3.4 % and 3.5 % (about 20 s of 600 s, 35 s of 983 s) |
| Page by page | 62 of 1,547 (4.0 %) | 63 of 1,607 (3.9 %) | 3.8 % (about 26 s of 698 s) |

(A reused line is never part of a joined run, so each one is a request of its own saved.) These works are short (some 40
pages); in a volume of some 200 pages, and across a series, more lines come back. The gain in time is small; what the
rule buys is the same line read the same (the model rendered 9 % of the later occurrences otherwise in the whole-book
runs, 18 % page by page), at no measured cost. So it is on by default.

Requests took 0.42 s and 0.69 s on average in the two whole-book runs, and 0.54 s and 0.44 s page by page (without and
with reuse): the GPU was shared with other work in some runs, so the shares are each run's own and the runs' times are
not compared with each other.

**Not shown here.** Lines across the volumes of a series; the speaker and kind in the key; a real volume's time; the
whole-book run with reuse on, end to end (its saving above is counted from the runs without).
`tests/test_linememo.py` covers the store (sealed, no Japanese in the file before or after it is opened), a later page,
a line repeated within a page or a request, a correction winning and its Undo, Translate again and the whole book again,
another model, language or series, volumes of one series under old and new spellings of their names, fresh answers
kept as the sheet spells them and the sheet changed since, the setting off, export, import, delete, and the whole-book
run. The region editor with the note that a translation was reused under its header and the line on how far the model
follows a hint under the hint field: as wide as without the note in all 16 window languages, one or two lines taller
(21 to 36 pixels; the tallest, Indonesian, 897 pixels against 861).

## The erase on the art (2026-11-15)

Three changes to `taslation/render/artwork.py`, kept because they measured better on the whole (their costs are named
below), and the ideas tried beside them that did not, with their numbers.

**What was wrong.** A text block's lettering box is drawn round the strokes (`detect/textblocks.py`); the white
outline of outlined lettering lies past it. `art_mask` cut its hole at that box, so a ring of white stayed round the
hole and LaMa, continuing what it saw, drew the glyphs back as grey shapes. `plain_ground`, judged within the same box,
saw only that white ring: lettering on a drawing passed for lettering on white paper and the paper fill painted it
white. And outlined lettering on a flat grey panel, which is no art (`on_art`), went to the paper fill, which took a
thick white ring for paper and left it, or painted the strokes white.

**What changed.** (1) The hole is each stroke with its anti-aliasing and white ring wherever these lie within
`reach_of` past the box (`with_ring`, `around`), grown by `GROW` 2 px more. (2) `plain_ground` is judged on the band
round that whole hole, with no box, and on such a ground the hole is painted with the surface fitted to the band
(`fill_ground`) before the paper fill does the rest. (3) Lettering on a flat ground (not `on_art`) whose strokes are
ringed has its hole painted so too (`FLAT_RINGS`); the paper fill alone otherwise, as before.

**How it was measured.** A new set of `tools/erase_eval.py`, `--set grounds`: mattes of real lettering (clean gold
crops of OpenMantra) drawn black on clean grounds whose truth is the ground: flat grey (120, 200), four gradients,
twelve screentones (pitch 4-8 px, 15-50 %), six of line art, four of white line art on black (white lettering on them
when there is no outline), and 40 crops of real art each, dense drawing and light tone, of 640 px; each without an
outline, with one of 3 px and with one of 6 px; 408 samples. The region is made as a text block would have it: its box
round the strokes alone. The numbers: MAE (RGB, 0-255) in the lettering's exact mask (strokes and outline); "outside",
the MAE in its box and 8 px round it outside the mask (what the erase damaged); "left", the share of the mask more
than 40 off; "ink", stroke pixels still ink-dark and 40 darker than the ground; "ghost", outline pixels still white and
40 lighter; "bias", the mean lightness off in the mask; "step", the lightness step at the edge of what the erase
changed against the ground's own (a visible seam). The variants were tried on a scratch bench built the same way
(other mattes and crops, its own seed, 408 samples; "in" is the MAE in the mask, "psnr" in it too), patched into the
module; the tool's set gave the before and after. The development machine (GeForce GTX 1660 Ti 6 GB, torch 2.14.1 with
CUDA 12.6, LaMa in fp32 as `lama.py` runs it); one run each. Other programs shared the GPU during some runs, so the
times are rough.

`tools/erase_eval.py --set grounds`, the erase with LaMa ("lama" arm), before (the code of 9c7bf8e) and after:

| | MAE | outside | left | ink px | ghost px | bias | step |
|---|---|---|---|---|---|---|---|
| all 408, before | 46.44 | 15.00 | 30.0 % | 135 | 502 | +14.68 | 18.04 |
| all 408, after | **34.52** | **14.64** | **23.2 %** | 164 | **167** | **-4.62** | **7.17** |
| flat grey | 21.93 / 0.06 | 0.42 / 0.00 | | | 896 / 0 | | |
| gradients | 36.27 / 0.58 | 8.04 / 0.26 | | | 871 / 0 | | |
| screentones | 25.71 / 18.52 | 10.15 / **12.51** | | 47 / 40 | 219 / 52 | | 8.93 / 3.47 |
| line art | 84.99 / 77.01 | 33.62 / 34.09 | | 202 / **278** | 735 / 345 | | 47.97 / 28.10 |
| white on black | 67.06 / 58.54 | 36.00 / 36.80 | | 317 / **410** | 550 / 198 | | 31.32 / 3.37 |
| real art, dense | 58.35 / 42.58 | 14.75 / 14.64 | | 212 / **255** | 575 / 203 | | 18.23 / 8.41 |
| real art, light | 35.76 / 28.73 | 11.22 / 10.01 | | 96 / 113 | 405 / 192 | | 14.58 / 4.73 |
| no outline | 50.97 / 47.77 | 21.55 / 21.42 | | | | | 20.43 / 13.22 |
| outline 3 px | 35.15 / 28.13 | 13.02 / **13.90** | | | | | 15.81 / 3.89 |
| outline 6 px | 53.19 / 27.65 | 10.43 / 8.62 | | | | | 17.87 / 4.39 |

(Rows by ground or outline: before / after.) The lama arm's regions went to LaMa 309 times before and 354 after, to
the paper fill on a plain ground ("ground") 55 and 10 times. The paper fill alone ("paper" arm) is unchanged: MAE
65.38.

Two numbers got worse. The damage round lettering on screentone rose from 10.15 to 12.51 (and round 3 px outlines from
13.02 to 13.90): the hole now takes the ring and 2 px of tone round it, which LaMa draws on in phase but not dot for
dot. And "ink" rose by 29 px a region: on the bench the stroke pixels LaMa made dark were as many as the outline pixels
it made dark, where there never was ink (line art 12.3 and 12.3 %, real dense 8.4 and 7.6 %, real light 3.1 and
2.7 %, tones 1.3 and 1.0 %), so that is the drawing it makes up over a larger hole, not glyphs drawn back. By eye on
the bench's galleries (scratch files, deleted): the grey ghost glyphs round outlined lettering are gone, screentone
goes on through the hole in phase (no smear), and dark smudges are left only where a stroke stayed out of the hole.

`tools/erase_eval.py`'s other two sets (the whole pipeline, detection and OCR first, real mattes on real pages; the
lama arm, before / after; the paper fill alone is unchanged, 51.36 and 40.64):

| | MAE | plain | light tone | dense | outside | left | regions to LaMa |
|---|---|---|---|---|---|---|---|
| plain (300 pairs, 180 regions) | 57.16 / **55.44** | 11.3 / 11.2 | 80.9 / 76.5 | 79.3 / 78.6 | 2.80 / **3.59** | 36.3 / 35.5 % | 70 / 99 |
| outlined, 2-4 px (295 pairs, 267 regions) | 30.43 / **29.25** | 3.8 / 3.8 | 26.0 / **27.3** | 61.0 / 56.1 | 7.49 / **10.12** | 21.1 / 20.1 % | 157 / 194 |

Here the cost is plainer: what the erase changed round the lettering rose by 0.8 and 2.6, and the MAE on light tone
with an outline by 1.3. The hole takes the light pixels within `LIGHT_REACH` 6 px of a stroke as its ring, so round a
2-4 px outline on a light ground it takes some of the ground too, and LaMa draws it anew. A ring of 4 px measured
better on the bench (in 34.88, out 14.95 against 35.41 and 16.01) but left most of an 8 px outline (in 50.91 against
29.96, ghost 1,662 px against 432); 5 px: 35.04 and 15.63, 8 px outlines not tried. Telling the outline's width per
region (where the light stops) would take both; not tried.

**The hole** (bench, the routing as it was):

| | in | out | left | ink px | ghost px | step | psnr |
|---|---|---|---|---|---|---|---|
| as it was (ring cut at the box) | 46.54 | 16.13 | 30.7 % | 151 | 605 | 7.87 | 14.96 |
| the same rule, not cut at the box | 41.59 | 17.54 | 28.0 % | 173 | 463 | 8.18 | 16.03 |
| that, grown 2 px (kept) | 40.69 | 18.77 | 27.5 % | 172 | 486 | 3.26 | 16.14 |
| that, grown 4 px | 39.69 | 19.05 | 27.1 % | 171 | 455 | 3.55 | 16.24 |
| the strokes grown 2 / 4 / 6 / 8 px, no ring | 57.88 / 49.89 / 40.38 / 40.86 | 16.74 / 16.54 / 16.63 / 18.59 | | | 1127 / 872 / 353 / 514 | 12.53 / 10.24 / 6.17 / 3.51 | |
| ring by connection (light pixels joined to a stroke, 10 px), grown 2 px | 40.75 | 19.49 | 27.9 % | 179 | 474 | 3.86 | 16.08 |
| grown 3 px on a busy ground, 8 px on an even one | 39.95 | 18.84 | 27.1 % | 172 | 461 | 3.53 | 16.22 |

A hole that ends on the ring's anti-aliasing leaves a seam (step 8.18); 2 px more takes it (3.26). 4 px took a point
more inside for twice the band of drawing repainted; the adaptive growth was no better than 2 px everywhere. The hole
is not taken past `reach_of`: room for the rings of the pieces followed to its edge took more of the drawing they are
mostly part of (out +6.5 on white on black, +3.2 on line art, +1.4 on real dense art); and the pieces that continue a
stroke past the box keep their ring (taking them without it: in 35.42 against 35.41, out 15.91 against 16.01).

**Where the plain ground is judged** (bench, the hole grown 2 px):

| | in | out | left | ghost px | step | psnr | LaMa |
|---|---|---|---|---|---|---|---|
| within the lettering box (as it was) | 40.69 | 18.77 | 27.5 % | 486 | 3.26 | 16.14 | 300 |
| within the box and 10 px round it | 38.27 | 16.94 | 26.5 % | 374 | 3.13 | 16.54 | 353 |
| no box | 38.19 | 16.90 | 26.5 % | 371 | 3.11 | 16.58 | 356 |
| within the box, the hole painted with the fitted surface | 38.00 | 18.10 | 26.1 % | 239 | 3.26 | 18.14 | 300 |
| no box, painted (kept), and `FLAT_RINGS` | **35.41** | **16.01** | **23.5 %** | **178** | 3.11 | **18.87** | 356 |

On flat grey the MAE went from 32.31 to 0.01, on gradients from 20.32 to 0.89.

**Tried and dropped** (bench, on the kept hole and routing unless said):

- *Matching LaMa's tone to the ring round the hole.* LaMa does shift what it re-renders: on flat grounds of 120-240
  the hole came out 2.5 to 3.4 levels darker, on near black (25) 2.9 lighter, on gradients 2.4 darker; on tones and
  real art inside the hole -2.0 to +1.7, and there it does not follow the ring right round the hole (correlation 0.04
  over 325 runs). Flat grounds and gradients now go to the fitted surface, not to LaMa. An offset, or a gain and an
  offset, fitted on a ring 1-6 or 6-18 px outside the hole (offset at most 8, gain 0.9-1.1, at least 64 pixels), and a
  gate (64 ring pixels within 12 levels of its median, the channels' offsets no more than 4 apart, at most 24): MAE in
  35.50 at best 35.05 (gain, ring 1-6), step 3.18 to 2.79, but the lightness in the hole on real light art from +1.2
  to +3.1 and on line art from +2.5 to +3.7; the gate 35.32. Under half a level, for a hole further off in lightness
  on the real art: not kept.
- *A feathered edge of 1 or 2 px.* Step 3.18 to 3.01 and 2.93, but out 16.48 to 16.66 and 16.79 and the gradient
  mismatch at the edge 50.8 to 53.4 and 54.9.
- *A smaller window for LaMa* (512 px at least now): the box and 64 px round it 36.40 (73 ms a region against 134),
  64 px with 256 at least 36.11, half the box's long side (24-80 px) 36.91, 128 px 35.60 (85 ms), 192 px 35.44
  (138 ms), against 35.50; on screentone 19.98, 20.44, 19.25 against 19.42, on line art 75.93, 78.13, 74.67 against
  75.00. Less context is worse; 128 px round the box is as good within noise at about a third less time, not changed
  here.
- *Small pieces the hole encloses* (glyph remnants, specks up to 150 or 400 px) added to it: 35.60 and 35.72 against
  35.41. (What strokes and outline are left, counted as pieces of 4 px or more, went from 17.0 to 15.0 a region with
  the kept changes; on flat grounds, where a missed island would show most, from 2.8 to 0.)
- *A higher grey level for the white ring* (`LIGHT` 215 or 230 against 190): 35.36 and 35.41, out 15.85 and 15.70,
  psnr 18.54 and 18.44 against 18.87.
- *Paper tolerances relative to the page's noise* (1.5 times the 92nd percentile of the flattest tiles' deviation,
  6 to 20) against the fixed `FLAT_GROUND` 6 and `GROUND_FIT` 8: on the bench made noisy (scaled to 90 % and back,
  grain of sigma 2.5, JPEG quality 60) the fixed values sent every flat ground and gradient where they went on the
  clean bench; the relative ones changed no region's route. What noise did change was the lettering found on tones
  (6 of 48 to the paper fill as too little), not the thresholds.
- *Half precision.* `lama.py` runs fp32; fp16 weights and autocast both gave black (the FFT in half precision).
- *Outlines of 8 px* (beyond the set's 6): in 29.96 against 30.29 for 6 px, ghost 432 against 428, the hole 4.5
  levels light against 2.5: the ring is taken about as well.
- *Less growth* (`GROW` 1 or 0 against 2): in 35.03 and 36.22, out 15.22 and 14.69, but the step at the edge 4.13 and
  7.85 against 3.11: the seam comes back.

**Not shown here.** The live window and a whole book on the viewer; the gated volume tests that read the owner's
development snapshots (`tests/test_realdata_models.py`); lettering of colour.

## Lines planned over the bubble's body (2026-11-15)

The automatic lettering along a bubble's shape was rebuilt (`render/typeset.py`, `shape_layout`): the tail is cut off
by an opening before the bubble is measured, two bubbles joined at a neck are also tried one at a time, every line is
as wide as the body over the rows its ink covers round one shared centre axis, with a margin of 0.3 of the size (at
least 3 px) instead of 5 % of the bubble, and at each size the words are shared out by a dynamic programme over break
points (an oval block in an oval, breaks priced by the language: free after a sentence, dearer inside a clause, after
an English article, preposition or conjunction, inside a name, at a hyphenation point, before a lone short word). The
size is found from an upper bound and may give up to a fifth for a block with fewer defects (lone words, hyphens, an
hourglass), but not for a column of a word or two a line, where those are the way a narrow bubble is set, nor for text
a cap holds. The rescue at the limit hyphenates two letters before and three after a point, and takes one hyphen at
most where the text fits whole at a smaller size, else at most as many as its first size needs. In Japanese and
Chinese a mark that may not start a line still hangs past the end of the line before, but only as far as the margin
allows: the line is centred with it, and a full-width mark hung whole ran past the outline. The automatic
lettering now also says what is still wrong with it (`lettering_flags`): the review list names letters at the
bubble's edge, a block off the bubble's centre, a hyphenated word, a word of three letters or fewer alone on a line,
an hourglass (both but in a column) and letters hard to see on their ground.

**How it was measured.** `tools/typeset_eval.py` (rewritten for this): a fixed, seeded corpus of 240 synthetic
cases, 60 invented lines (English of 1 to 40 words, long words, invented names, punctuation, stressed words; long
German, Spanish and French words; two Japanese lines; one Arabic line) in four of six bubble shapes each (ellipses,
round-cornered boxes, clouds, ellipses with a tail, two bubbles joined at a neck, narrow tall ones), set by
`letter_text` as `Pipeline._set_text` calls it, on the comic lettering font of the development machine. *size/fit* is
the size against the largest at which the text fits at all (every word whole, each line anywhere in its rows, 0.3 em
off the outline, any number of lines). Base: the code of 9c7bf8e (`git archive`), the same yardstick; both run one
after the other on the development machine (the CPU only), twice.

| All 240 cases | Base | Now |
|---|---|---|
| size / largest that fits (mean) | 1.021 | 0.993 |
| cases under 0.9 of it (joined bubbles: 37.5 % / 65.0 %) | 9.2 % | 12.5 % |
| cases with ink outside the bubble / nearer the outline than 0.25 em | 3 / 7.1 % | 1 / 0.4 % |
| words hyphenated (in all cases) | 45 | 28 |
| first / inner / last line a lone short word (of cases on 2+ lines) | 28.1 / 24.5 / 22.4 % | 25.0 / 17.2 / 19.3 % |
| English line ends on a weak word (per 100) | 18.0 | 11.0 |
| lines starting with punctuation of the line before | 4 | 0 |
| hourglass / widest line first or last (round bubbles, 3+ lines) | 29.2 / 16.8 % | 17.6 / 11.9 % |
| distance of the line widths from an oval's | 0.159 | 0.147 |
| block's centre off the body's centroid, x / y (mean) | 4.4 / 5.3 % | 1.9 / 3.1 % |
| cases more than 5 % off | 30.8 % | 18.8 % |
| ms per layout, mean / 95th percentile (three pairs of runs; the first two before the last changes) | 7.3 / 25.8, 8.4 / 27.6, 8.3 / 28.2 | 8.4 / 23.2, 9.2 / 25.0, 9.2 / 24.4 |
| pages of six: 90th / 10th percentile of size, largest / median | 1.738, 1.241 | 1.751, 1.251 |

| By shape: size/fit, hourglass, off > 5 % | Base | Now |
|---|---|---|
| ellipse | 1.019, 15.6 %, 17.5 % | 1.007, 6.2 %, 20.0 % |
| round-cornered box | 1.046, -, 12.5 % | 1.043, -, 7.5 % |
| cloud | 1.022, 14.7 %, 10.0 % | 1.007, 16.7 %, 10.0 % |
| ellipse with a tail | 1.012, 6.2 %, 22.5 % | 1.008, 6.5 %, 10.0 % |
| two joined at a neck | 0.919, 42.9 %, 100 % | 0.868, 3.2 %, 52.5 % |
| narrow | 1.110 (17.5 % too tight), 65.7 %, 22.5 % | 1.027 (none), 51.4 %, 12.5 % |

The size is a little lower than before for two reasons, both meant: the margin grows with the size (before, 5 % of
the bubble let large lettering run within a few pixels of the outline: 7.1 % of the cases too tight, 17.5 % of the
narrow ones), and a translation for two joined bubbles is set in one of them rather than across the neck (the
yardstick's largest size spans the neck; the review list now says "text set off the bubble's centre" there, for the
reader to share the text out). The lettering checks flag 22.9 % of these cases (off the centre 10.8 %, nearly all
joined bubbles; a hyphenated word 10.0 %, the corpus being heavy in long words; an hourglass 1.7 %, a lone word
1.2 %, letters at the edge 0.4 %) and cost about 0.5 ms a drawn bubble. On the first fixture page three bubbles come
out at 52, 60 and 56 points instead of 58, 64 and 58, on the second at 62, 60 and 56 instead of 64, 64 and 58 (the
margin), the rest at their sizes; `tests/test_ink.py`'s pixel digests were made again on the new code.

The room a translator is told a small bubble has (`text_room`, at the size of the original lettering) asks the same
body whether the probe words fit, every word whole, without planning the block and without the last resort (which,
3 px off the outline, would count room the lettering does not use: a 60 x 40 box at 17 px held 12 characters that
way, 6 as set). It is 15 to 25 % larger than before with the new margin and far quicker, which a page pays once per
bubble before its first request:

| Mask, size | Base: characters, ms | Now: characters, ms |
|---|---|---|
| box 60 x 40, 11 / 17 px | 12, 13.1 / 6, 1.0 | 18, 9.1 / 6, 1.3 |
| box 400 x 300, 11 / 17 px | 1386, 1777 / 588, 357 | 1716, 29 / 714, 14 |
| ellipse 200 x 260, 11 / 17 px | 450, 58.5 / 174, 31.8 | 540, 15.1 / 204, 8.0 |
| ellipse 400 x 500, 11 / 17 px | 1854, 1434 / 762, 336 | 2220, 91 / 876, 36 |

(Planned in full, as `shape_layout` before, the new body layout took 159 and 678 ms for the two ellipses at 17 px, and
a test that cancels a line asked again after one second, `tests/test_reask.py`, found it not yet asked.)

**Tried and not kept** (each measured on the corpus): a margin of 0.35 to 0.45 em (lower sizes, no better blocks);
dearer lone words (`COST_LONE` 0.25: no change), weak line ends (`COST_WEAK` 0.2) or clause breaks (0.04: no gain);
a lone word counted only where it fills under half its line's room or under 0.25 to 0.5 of the widest (more sizes
kept, but lone first lines in ovals came back); a smaller price per defect in the trade (`TRADE_PER_DEFECT` 0.07:
worse blocks) and no trade at all (size/fit 0.999, but lone first lines 26.6 %, hourglasses 22.6 %); the column rule
at 1.6 words a line instead of 2 (more narrow bubbles set smaller, by eye no better); the column rule also in the
choice between a joined bubble's lobes (the whole body won with a text along the neck); a page cap of 1.2 or 1.25
times the median instead of 1.3 (the page spread falls to 1.18 / 1.21 largest over median, but nothing here says
whether readers want large bubbles held that close, so the cap stays). The name rule (no break inside a name) is
not applied in a rectangle, where no language is known, nor in German, where every noun has a capital. A lone
character on a Japanese or Chinese line priced like a lone word took "か。" off the end of an oval block but broke
inside a word instead (今日はと / ても), as the rule against it in CJK foresaw; not kept.

**Not shown here.** A real book's pages (the corpus is synthetic; the earlier OpenMantra series, `--openmantra`, was
not run again), Arabic in a tiny cloud (the one case that still overflows: its measured ink is a Latin font's),
Japanese in an oval that now ends on one character and its full stop (the block follows the oval, and nothing in a
script wrapped by character tells a word from the next), and whether the review list's new reasons help or only add
to it on real pages.

## What a PLaMo request costs the server (2026-11-20)

Every translation request of the PLaMo translator is one /api/generate with a raw PFML3 prompt: the dataset tag, the
``context`` (the premises; for some lines a speaker, a hint or the Japanese that follows), the earlier pairs, a
``glossary`` when the line names one, then the line. Ollama 0.40 runs the model in llama.cpp's server, which keeps the
tokens of the last request (its prompt and the answer it wrote) and computes again only what the next prompt does not
repeat of them. How much that is, and what else a request costs, was read from Ollama's own counters
(``prompt_eval_duration``, ``eval_duration``; ``prompt_eval_count`` is the whole prompt, whatever the server took from
the request before) and from the server's log, which names the tokens it computed.

**How it was measured.** The development machine (Intel Core i7-9700F, 48 GB, GeForce GTX 1660 Ti 6 GB, Ollama
0.40.16, PLaMo 3 Translate 2B Q4_K_M, context 8192), a second Ollama server of its own on 127.0.0.1:11435 with the
variables under test in its environment only (the owner's server and the user's environment untouched),
`OLLAMA_KV_CACHE_TYPE=q8_0` as this machine has it unless a column says otherwise. The model, by its GGUF: 24 layers,
21 of them with a sliding window of 2,048 tokens and 3 with full attention; the server keeps the windowed layers'
cache at 3,072 cells and, to go back in a prompt, keeps "context checkpoints" of them (24 MB each with q8_0, up to 32,
two made by every request). The probes: invented lines, a history built by asking 40 lines one after another (prompts
of 1,100 to 2,300 tokens), then three requests of each kind; the prompt's milliseconds, the mean of three.

| request | default (RAM cache 8 GiB) | RAM cache 0 (the Ollama TASlation starts) | f16 KV cache | full-size window cache | full-size window cache, cache reuse |
|---|---|---|---|---|---|
| extends the last prompt and answer | 124 | 124 | 141 | 75 | 76 |
| the same prompt again | 85 | 85 | 101 | 42 | 41 |
| the last pair's answer otherwise | 127 | 129 | 141 | 75 | 74 |
| the last pair left out | 125 | 126 | 143 | 53 | 52 |
| a pair in the middle otherwise | 3,162 | 3,173 | 3,124 | 2,061 | 2,029 |
| ``context`` otherwise (a line's own) | 4,327 | 4,334 | 4,295 | 4,250 | 4,220 |
| the request after it | 221 | 4,387 | 235 | 142 | 144 |
| a ``glossary`` / the request after it | 166 / 232 | 170 / 239 | 186 / 258 | 99 / 147 | 103 / 151 |
| a request beside (same pairs, another line) / the one after | 110 / 97 | 110 / 100 | 130 / 122 | 58 / 54 | 58 / 55 |
| a joined run / the request after it, its pairs one by one | 128 / 239 | 130 / 243 | 145 / 255 | 102 / 195 | 102 / 194 |
| the oldest third of the pairs cut | 3,653 | 3,671 | 3,666 | 3,386 | 122 |

An answer of 7 tokens took 55 to 60 ms in every column (9.4 ms a token with q8_0; prompts of 1,000 tokens and more are
computed at 400 to 470 tokens a second).

**What the server does.** A request whose prompt extends the last one exactly still goes back to the newest checkpoint
before the end of what the server holds (four tokens before the last prompt's end) and computes from there, in two
batches with a checkpoint between them: 28 to 31 tokens, 124 ms, more than an answer of seven tokens. A prompt that
parts from the last one within its last few pairs (an answer set otherwise, a pair left out, a glossary, a joined
run's pairs one by one) goes back to the checkpoint before the parting and costs the tokens from there, about 0.1 s
more. One that parts further back (a pair in the middle, the oldest pairs cut) finds no checkpoint and is computed from
its start ("forcing full prompt re-processing" in the log), about 2.2 s per 1,000 tokens. A request whose ``context``
differs is computed from its start, and so is the one after it, unless the prompt cache in RAM gives back the state
before it: 221 ms then, 4.4 s without (the Ollama TASlation starts gets `LLAMA_ARG_CACHE_RAM=0`: "Ollama's prompt
cache in RAM" above, decided before the pairs only grew, when no saved prompt matched a later one). A request beside
the main ones with the same pairs and another line costs its tail, and so does the main request after it. The KV
cache's precision is not the cost (f16 is slower here). The server's log, at the verbosity Ollama gives it, holds
counts and no text of a prompt. Every request also logs "Added a BOS token to the prompt as specified by the model
but the prompt also starts with a BOS token. So now the final prompt starts with 2 BOS tokens": the server adds the
beginning-of-sequence token that `pfml_prompt` puts first for raw mode (not changed here; what one BOS instead of two
does to the translations was not measured).

The fixed cost is the checkpoints'. With a full-size cache for the windowed layers (`LLAMA_ARG_SWA_FULL=1`, which
llama.cpp's server reads and Ollama passes on: "using full-size SWA cache" in its log; 132 MB more GPU memory, 1,981 MB
in all) the server makes none, an extending request takes 75 ms, and a pair changed in the middle costs the tokens
from there (2.06 s here) rather than the whole prompt. A cut stays a whole prompt unless the server may also move the
pairs it holds (`LLAMA_ARG_CACHE_REUSE=64`: 122 ms against 3.4 s), which gives the pairs kept the cache of a prompt that
still held the ones cut: not what computing them again gives, so the translations would change. TASlation sets
neither; both are options of the server.

**The OpenMantra pages, request by request.** `tools/prompt_replay.py` with the gold English as the answers (both ways
of translating, the 1,586 lines, 1,421 requests), what parts each request from the one before:

| reason | page by page, before | after | whole book, before | after |
|---|---|---|---|---|
| extends | 1,219 | 1,367 | 1,220 | 1,369 |
| after a joined run (its pairs one by one) | 145 | 0 | 148 | 0 |
| the oldest pairs cut | 28 | 25 | 23 | 22 |
| ``context`` (the Japanese after the line) | 10 | 13 | 11 | 14 |
| a line asked again (romanised, re-asked) and the request after it | 10 | 7 | 10 | 7 |
| a glossary | 4 | 4 | 4 | 4 |
| the first of a series | 5 | 5 | 5 | 5 |

With the model (`--answers live`, four pages of every series, 139 lines, 124 requests, seed 1, the server's own
counters): before, a request after a joined run took 287 to 292 ms of prompt against 101 ms for one that extends, and
the prompts took 15.7 s in all page by page; after, 105 ms, 13.6 s.

**The change.** A page's (or a whole-book run's) request hands the caller the pairs as it computed them
(`PlamoTranslator._computed`, `base.SentPair`, `base.grown_pairs`): a joined run as one pair with a line per bubble,
and the answer as the model wrote it, unless the page sets it otherwise than by spaces and stray asterisks (a name
respelt as the series sheet spells it: then the page's line, as before, at the cost of a tail); the next request's
prompt holds those. Before, a joined run's answer came back as its bubbles' pairs one by one and the next prompt parted
from the server's there. A request beside the page (where a bubble's larger lettering is in its translation) takes the
pairs it is given whole instead of the newest 60, which after a page that took them past 60 made it begin otherwise
and be computed in full. `tools/openmantra_eval.py --seed 1`, the official arm, on the second server (default column
above), the code before (fa94887) and after:

| | whole book, before | after | page by page, before | after |
|---|---|---|---|---|
| chrF | 40.95 | 41.18 | 41.06 | 41.37 |
| paired difference, 95 % interval | | +0.23 (-0.15 to +0.57) | | +0.31 (-0.03 to +0.78) |
| lines that end open (340) | 38.16 | 38.50 | 38.06 | 37.89 |
| untranslated | 0 | 0 | 0 | 0 |
| flagged | 2.9 % | 2.5 % | 2.5 % | 2.3 % |
| requests | 1,413 | 1,415 | 1,414 | 1,416 |
| translation | 396.9 s | 369.4 s | 397.6 s | 374.6 s |
| prompts / answers (the server's) | 261.0 / 93.1 s | 233.5 / 93.2 s | 263.2 / 92.5 s | 239.9 / 92.6 s |
| prompts computed again (0.6 s or more) | | 47 (56.2 s) | 55 (67.1 s) | 45 (62.4 s) |

One seed per arm, the same in both; a seed's own noise is about 0.45 chrF, so the difference is none, and the time
-6.9 % and -5.8 %. The prompts are 3 to 6 % longer in tokens: a joined run is one pair now, so the bound of 60 pairs
and the newest 20 kept at a cut hold a few more lines than before.

`tools/standin_e2e.py --scenario a` (the real window on the stand-in viewer, the owner's Ollama, nine turns, two runs
of each): the first lettered bubble 1.40 and 1.41 s after the sharp frame (the median) before, 1.68 and 1.67 s after;
the finished page 4.75 and 4.75 s, 4.85 and 4.84 s. Turn by turn, the difference is where the cut falls: three
requests in every run were computed in full (1.25 to 1.65 s of the server's time before, 1.55 to 1.70 s after, the
pairs kept holding more lines), and after the change they fall on other turns (two turns 1.5 s slower to their first
bubble, one 1.0 s faster); the other turns took the same time to the 0.1 s.

The same code, whole book, on a server with the full-size window cache (`LLAMA_ARG_SWA_FULL=1`, nothing else
changed): translation 296.2 s (prompts 161.0 s, answers 93.7 s), chrF 40.99 (-0.18 against the default server, 95 %
interval -0.69 to +0.39: the same computation in other batches), no line untranslated; the 47 prompts computed again
still took 56.0 s, the other 1,371 requests 77 ms of prompt each. That is a quarter off the time before the change,
from an option of the server that TASlation does not set (for the Ollama it starts it could, as it sets
`LLAMA_ARG_CACHE_RAM`; with no checkpoints a saved prompt is then the cache alone, some 40 MB for 1,700 tokens).

**Left as it is.** The Japanese after a line that goes on (`FOLLOW_OPEN`) or is asked alone (`FOLLOW_ALONE`) is the one
``context`` that changes from line to line: 13 or 14 requests a run, each computed in full (2 to 4 s), and the request
after each in full too where the RAM cache is 0. They serve the lines whose sentence goes on (chrF 38.2 against 40.4
for the rest) and the lines asked again; leaving their neighbours out was not tried, since the 20 or so lines of a run
it touches would not show a difference within the noise. A speaker the reader gives a line, or a hint, makes that
line's prompt begin otherwise in the same way. The cut (to the newest 20 once past 60) costs 22 to 28 prompts of about
700 tokens a run; counting a joined run's lines against the bound, as the bound counted them before, was not tried.
The format has no place for a line's own reference after the earlier pairs, so none of these can move behind them.

**Not shown here.** A real book's pages, a series sheet (no name is respelt without one, so the page's line never came
in), the translator role with speakers, a request beside a page in a run (the official arm asks none; the tests show
its prompt extends the page's last one), a computer without a GPU (where a whole prompt takes 10 to 13 s), and the
server's options in a run of the app.

## The full-size window cache (2026-11-20)

PLaMo 3 Translate 2B has 24 layers, 21 of them with a sliding window of 2,048 tokens. llama.cpp's server, which runs
the model inside Ollama, keeps those layers' cache at 3,072 cells and, to go back in a prompt, saves "context
checkpoints" of it; a request that extends the last one still goes back to the newest checkpoint, and one that parts
from it further back than the checkpoints reach is computed from its start ("What a PLaMo request costs the server"
above). With `LLAMA_ARG_SWA_FULL=1` the server keeps the windowed layers' cache full-size and needs no checkpoints:
each request computes only what the last one did not hold. The Ollama TASlation starts now gets it, with
`LLAMA_ARG_CACHE_RAM=256` instead of `0`, unless the extra GPU memory would move the OCR readers off the GPU
(`taslation/ollama_start.py`, `server_setup`; the setting `ollama_window_cache`).

**How it was measured.** The development machine (Intel Core i7-9700F, 48 GB, GeForce GTX 1660 Ti 6 GB, Ollama
0.40.16, PLaMo 3 Translate 2B Q4_K_M, context 8192), with nothing of the owner's loaded in the Ollama on 11434 before
or after any run. First a second server of the developer's own on 127.0.0.1:11435, the variables under test in its
environment only (the configurations below), `OLLAMA_KV_CACHE_TYPE=q8_0` as this machine has it unless a row says f16;
then the path a person gets: `tools/openmantra_eval.py --start-ollama 11436` and `tools/standin_e2e.py --start-ollama
11436`, where TASlation's own starter starts Ollama on a spare port with the environment it chooses and stops it at
the end, the environment of the server and of llama.cpp's server read back from their processes (the install check's
reader of a process's environment block). OpenMantra, the official arm (the gold Japanese in the gold order, every
line set where the detection put it: one geometry scan for every run), seed 1, all 214 pages, 1,586 lines; the
server's memory sampled every 0.5 s (the card's used memory by NVML, llama.cpp's server's working set and commit by
the system's own counters); chrF's difference paired by series (`tools/compare_runs.py`).

| configuration | `LLAMA_ARG_SWA_FULL` | `LLAMA_ARG_CACHE_RAM` | KV cache |
|---|---|---|---|
| C0 (TASlation until now) | - | 0 | q8_0 |
| C1 | 1 | 0 | q8_0 |
| C2-256 (what the Ollama TASlation starts now gets) | 1 | 256 | q8_0 |
| C2-1024 | 1 | 1024 | q8_0 |
| C0-256 | - | 256 | q8_0 |
| F0, F2-256 (a GPU of more than 6 GB: Ollama's own KV cache) | -, 1 | 0, 256 | f16 |

**On a server of the developer's own.** Translation seconds (the official arm's whole pass), the prompts' and the
answers' time by Ollama's own counters, the requests computed from their start (the eval's count, and their prompt
seconds), chrF and its difference from C0 of the same mode (95 % interval), the lines no request translated:

| run | translation s | prompts s | answers s | computed from the start | chrF | difference from C0 | untranslated |
|---|---|---|---|---|---|---|---|
| C0, whole book | 400.6 | 264.5 | 93.8 | 59, 91.0 s | 41.18 | | 0 |
| C0-256, whole book | 397.9 | 262.1 | 93.7 | 59, 89.0 s | 41.19 | +0.01 [0.00, +0.04] | 0 |
| C1, whole book | 317.4 | 181.5 | 93.8 | 51, 78.3 s | 41.09 | -0.08 [-0.31, +0.14] | 0 |
| C2-256, whole book | 296.3 | 160.4 | 93.4 | 47, 55.6 s | 40.99 | -0.18 [-0.55, +0.24] | 0 |
| C2-1024, whole book | 294.4 | 159.7 | 92.8 | 47, 55.4 s | 40.99 | -0.18 [-0.55, +0.24] | 0 |
| F0 (f16), whole book | 415.8 | 280.6 | 93.5 | 61, 92.9 s | 41.06 | | 0 |
| F2-256 (f16), whole book | 294.8 | 158.1 | 93.9 | 47, 55.9 s | 40.89 | -0.17 [-0.60, +0.22] from F0 | 0 |
| C0, page by page | 412.2 | 278.9 | 92.5 | 66, 109.4 s | 41.40 | | 0 |
| C1, page by page | 351.3 | 216.4 | 93.5 | 64, 115.0 s | 41.56 | +0.16 [-0.13, +0.46] | 0 |
| C2-256, page by page | 299.3 | 161.2 | 94.2 | 43, 52.8 s | 41.22 | -0.19 [-0.45, +0.16] | 0 |

The answers take the same time in every row: the full window cache saves prompt time only, and C2-256 takes 26 %
(whole book) and 27 % (page by page) off the translation. The RAM cache alone does nothing (C0-256); with the full
window it gives back the state before a request whose ``context`` differs (the requests computed from the start fall
from 51 to 47 and their time from 78 to 56 s), and 1,024 MiB gain nothing over 256. Between 203 and 215 of the 1,586
lines changed their wording (a request computed on another cache, the same seed); every difference from C0 is within
what one run to the next varies.

Without a GPU (a server that sees none: `CUDA_VISIBLE_DEVICES=-1` and its kin; one series, 4 pages, 29 lines, page by
page; C0 twice): 37.1 and 37.5 s (1.28 s a line), C1 32.5 s (1.12), C2-256 28.3 s (0.98 s a line, 24 % less); the
server's working set 2.39 GB, 2.29 GB and 2.29 GB at its peak. The chrF of 29 lines of one series (39.87, 42.65,
42.60) says nothing either way.

**What the model takes.** Loaded alone by one short request, nothing else on the server, PLaMo added to the card's
used memory and `/api/ps` gave:

| KV cache, window | added to the card (MiB) | `/api/ps` size (bytes) | `place.KNOWN_TRANSLATORS` (MiB added, `/api/ps` MiB) |
|---|---|---|---|
| q8_0, checkpoints (C0) | 1,933 | 1,912,550,194 | 2000, 1824 |
| q8_0, full window (C1, C2) | 2,065 | 2,050,500,853 | 2100, 1956 |
| f16, checkpoints (F0) | 2,009 | 1,972,759,429 | 2100, 1882 |
| f16, full window (F2) | 2,229 | 2,203,446,149 | 2300, 2102 |

Qwen 3.5 4B (the translator for Brazilian Portuguese and Turkish) has no windowed layers: 3,939 MiB with and without
`LLAMA_ARG_SWA_FULL`. llama.cpp's server held at its peak (working set / commit, whole book): C0 1,986 / 4,091 MB (the
checkpoints are kept in RAM), C1 684 / 2,924, C2-256 937 / 3,172, C2-1024 1,706 / 3,940, F2-256 931 / 3,324.

**Where the OCR readers go.** `taslation.ocr.place` puts two of the three readers on the GPU when the room left at
TASlation's peak - the card, less what other programs hold, less the CUDA context (120 MiB), the translation model,
LaMa (680 MiB; 970 on a screen taller than 1,440 px), the layout model (430) and the readers (500) - is 1,024 MiB or
more. Until now it counted PLaMo at 2,000 MiB before it was seen loaded and, once seen, at its `/api/ps` size times
1.25: 2,280 MiB with checkpoints, but 2,444 with the full window (and 2,351 for f16 with checkpoints on a larger
card), more than the 2,065 and 2,009 it adds. So it now counts the figure measured for the server's KV cache and
window (`known_translator`; a KV type not measured as f16), and a model seen loaded at the smallest of those figures
whose `/api/ps` size holds it (`known_for_size`; a model larger than every one, as before). Where the readers go on a
6 GB card, by what other programs hold:

| other programs (MiB), screen up to 1,440 px | 717 | 1,024 | 1,290 | 1,291 to 1,390 | 1,391 |
|---|---|---|---|---|---|
| without the window cache (2,000 counted) | GPU | GPU | GPU | GPU | CPU |
| with it (2,100 counted) | GPU | GPU | GPU | CPU | CPU |
| with it as the old count learnt it (2,444) | GPU | CPU | CPU | CPU | CPU |

On a taller screen the band is 1,001 to 1,100 MiB; on an 8 GB card with f16, about 3,140 to 3,340 MiB, which other
programs do not hold here. The rule's "auto" for the window cache (`ollama_start.window_choice`) asks the placing rule
once as it starts the server, both ways on one snapshot of the card, and leaves the window cache out only in the band.
Two readers on the processor cost 0.66 to 0.73 s a page here (40 pages, the readers alone).

**The path a person gets.** `tools/openmantra_eval.py --start-ollama 11436`, with `ollama_window_cache` "off" and with
the default: TASlation's starter started Ollama, chose its environment, logged it, and stopped the server at the end
(no process left, the record gone). What the server and llama.cpp's server got, read back from their processes:
`LLAMA_ARG_CACHE_RAM=0` and no `LLAMA_ARG_SWA_FULL` with "off"; `LLAMA_ARG_SWA_FULL=1` and `LLAMA_ARG_CACHE_RAM=256`
with the default; `OLLAMA_KV_CACHE_TYPE=q8_0` (this user's own) in both. Other programs held 1,247 to 1,258 MiB of the
card when the server started, so the default's rule found the readers' room 1,174 and 1,074 MiB (whole book), 1,156
and 1,056 MiB (page by page) without and with the window cache: on the GPU either way ("the OCR readers run in the
same place either way"), and the window cache on.

| run | translation s | prompts s | answers s | computed from the start | chrF | difference from "off" | untranslated | server's peak, working set / commit (MB) | card's used memory at most (MiB) |
|---|---|---|---|---|---|---|---|---|---|
| "off", whole book | 399.8 | 264.7 | 93.5 | 61, 92.6 s | 41.18 | | 0 | 1,986 / 4,090 | 3,205 |
| default, whole book | 295.6 | 160.9 | 93.7 | 47, 56.1 s | 40.99 | -0.18 [-0.55, +0.24] | 0 | 939 / 3,170 | 3,332 |
| "off", page by page | 412.6 | 279.4 | 92.4 | 65, 109.3 s | 41.40 | | 0 | 1,894 / 3,999 | 3,193 |
| default, page by page | 293.6 | 160.5 | 93.0 | 43, 52.6 s | 41.22 | -0.19 [-0.45, +0.16] | 0 | 939 / 3,173 | 3,323 |

26.1 % and 28.8 % less time, the same scores as on the server of the developer's own (every request is the same with
the same seed), 203 and 209 lines worded otherwise. The start of Ollama took 4.4 s with "off" and 10.3 s with the
default (below).

**The window on the stand-in viewer.** `tools/standin_e2e.py --start-ollama 11436`, scenario a (slow reading: 9 turns
6 to 8 s apart), twice for each setting, where the window's own starter starts Ollama at the window's start, beside
the OCR models' load. Other programs held 1,235 to 1,250 MiB of the card before the stand-in's browser opened, which
holds some of it too: here the rule found the readers' room 1,063 and 963 MiB, then 1,058 and 958 MiB, without and
with the window cache, so in this setting this computer is in the band. The first bubble is from the stand-in's sharp
frame to the first lettered bubble of the page; "finished in time" counts the pages lettered in full before the next
turn, of 18, and their median time.

| `ollama_window_cache`, `ocr_runs_on` | what the starter chose | where the readers read (each run) | first bubble, median (range), ms | finished in time, median ms | card's used memory at most (MiB) |
|---|---|---|---|---|---|
| default ("auto"), "auto" | no window cache: with it the readers would leave the GPU | GPU, GPU | 1,668 (1,138 to 3,172) | 9, 5,421 | 4,512, 4,522 |
| "off", "auto" | no window cache | CPU, GPU | 2,035 (1,205 to 3,572) | 6, 5,242 | 4,021, 4,523 |
| "on", "auto" | the window cache | CPU, CPU | 2,481 (1,689 to 3,521) | 9, 5,570 | 4,291, 4,296 |
| default, "gpu" | the window cache (the readers' place is set) | GPU, GPU | 1,346 (1,039 to 3,023) | 16, 5,375 | 4,649, 4,646 |
| "off", "gpu" | no window cache | GPU, GPU | 1,641 (1,117 to 3,125) | 10, 5,530 | 4,503, 4,514 |

Here the rule kept the settings of before, and the window was as fast as with "off" while its readers held the GPU
(1.67 against 1.64 s); with the window cache forced on, the readers read on the processor from the start (2.48 s).
Where the readers' place does not hang on it (set to the GPU: what a computer outside the band gets), the window cache
took the first bubble from 1.64 to 1.35 s and finished 16 pages of 18 before the next turn instead of 10, for about
140 MiB more of the card at its peak (1,495 MiB were left). In one of the two "off" runs the readers found no room at
the window's start either: other programs at the edge of the margin (the browser's share of the card moves by tens of
MiB). Each run stopped the server it started, with no model left loaded in it.

Two faults of the first version of the change were found on this path and mended. Before the runs above: the two
looks of the rule each read this process's own part of the card anew while the readers moved to the GPU on the
start's other thread (1,063 and 1,463 MiB in one run: the window cache came on, and the readers then left the GPU at
the model's load, 2.67 s to the first bubble); they now share one `place.snapshot`, the card and this process's part
of it read together. After them: each look asked the server about to be started what it had loaded, which Windows
takes about 2 s to refuse, so the start of Ollama took 10.3 s in the benchmark instead of 4.4 s with "off"; the
start's looks no longer ask (the same choice; 6.5 s, of which about 2 s are torch's import in a process that had not
loaded it). The times above are of the translation and of the turns, after the start.

## Where a page's time goes in the window (2026-11-20)

**How it was measured.** The development machine (Intel Core i7-9700F, 48 GB, GeForce GTX 1660 Ti 6 GB, Ollama
0.40.16, PLaMo 3 Translate 2B Q4_K_M), the window on the stand-in viewer: `tools/standin_e2e.py --scenario c,a,e,w,x
--start-ollama 11436 --seed 1`, with `--ocr-runs-on gpu` and with `auto`, two runs of each, one after the other. The
server is the one TASlation starts (the full-size window cache, `LLAMA_ARG_CACHE_RAM=256`, q8_0), on a spare port,
stopped at the end of each run; the owner's Ollama on 11434 had no model loaded before or after any run. The scenarios:
turns while the window starts and the model loads (c), slow reading (a: nine turns 6 to 8 s apart, the same waits in
every run), turning back (e: three turns back and two on, 3 s apart), a whole-book run, then reading beside it and
after it (w, w2), and requests cancelled in flight (x). A turn counts when the page stays 2 s or more (31 or 32 a run);
the first bubble and the finished page are timed from the stand-in's sharp frame. The tool records each page job's
stages, the requests computed in full and why, the cuts of the earlier pairs, the pages come back to and the page after
a run (`fd1fb87`).

**The split.** The slow reading's pages that the model translated, 0.6.1 (21e454c), the median of each stage:

| stage | OCR on the GPU (14 turns), ms | "auto" (12 turns), ms |
|---|---|---|
| the sharp frame to the job's start (the look, the frame's gate) | about 290 | about 290 |
| page fingerprint | 52 | 52 |
| detection | 180 | 174 |
| OCR | 564 | 1,104 |
| the first request (its prompt / its answer) | 114 (68 / 31) | 109 (69 / 30) |
| its answer to the lettered bubble | 90 | 84 |
| **the first lettered bubble** | **1,305** | **1,828** |
| the page's requests (prompts / answers) | 2,089 (978 / 1,031) | 2,329 (1,104 / 1,010) |
| the spread's second page read, between its requests | 324 | 1,024 |
| rendering | 401 | 364 |
| **the page finished** | **4,467** | **5,113** |

Up to the first bubble the OCR is the largest part (43 % on the GPU; 60 % with "auto", where on this card two of the
readers read on the processor); the model's first request is a tenth of a second. Three things made a turn slower than
this: after a whole-book run the model had been released, so the next untranslated page waited for its load (first
bubble 4.1 to 4.4 s, the page finished in 11.9 to 12.9 s); a first request computed in full, one or two a run (3.4 to
4.1 s after a run, the load included; 1.1 s where the earlier pairs were cut back to the newest 20); and a page left
before its end and come back to, whose request's lines were all asked again (11 requests, 1.2 to 1.7 s).

**Three changes**, one commit each, kept because the runs after it (the same scenarios and seed) show the gain:

* `45893f7`: after a whole-book run in the window the model stays loaded when Auto goes back on, as after a page
  translated one by one (`ollama_keep_alive`, "5m"); with Auto off it is released at once, and the `taslation`
  commands release it at their end, as before. It was released at the end of `BatchReader.run` (the model "is not
  needed again until a page is"), which a whole-book run in the window shares with the commands. Nothing else is held:
  the GPU budget of the OCR readers' placing rule already counts the model loaded (`place`), and a run's model is the
  one a page loads.
* `a0ef427`: while the reader reads and nothing is translated, the window has the server compute the beginning of the
  next page's first request (the premises and the pairs it will be given) when the server may hold none of it - after
  a cut, a request beside the page's, a cancelled one: `PlamoTranslator.warm_prefix`, from `Pipeline.warm_soon`. What
  the server may hold is the translator's last 16 prompts, each grown in place (a cancelled one's too: the server
  finishes a prompt it was sent), none after a load; when one covers that beginning nothing is sent. Otherwise steps of
  at most 128 tokens (about 0.2 s each), each extending the one before and ending on an element, with the very options
  a line sends and one token asked for; nothing is drawn or kept. Any request, the next page and a release stop it
  between two steps; only for a model held wholly on the GPU; never during a whole-book run or while a job runs.
* `c16311b`: a page the reader turns away from (the window's cancel then: `pipeline.turn_away`; Stop and Esc keep
  nothing, as before) keeps the lines answered by then, set as a page done whole sets them, the earlier pairs grown with
  them as the request computed them, and the page is stored marked incomplete: coming back to it, they are lettered at
  once and only the rest is read and asked for (`_keep_answered`, `_add_completed`). A frame never confirmed keeps
  nothing (`Provisional`), a sharper picture of the page puts back the entry as it was (`PageWork.replaced`), and a
  marked page is never shown from memory as if whole.

| code | OCR | first lettered bubble, ms (median / p90 / slowest) | page finished, ms (median / p90 / slowest) | finished before the next turn | first requests computed in full (ms) | the page come back to: requests (asked again, ms) | the first page after a run: first bubble / finished, ms | requests |
|---|---|---|---|---|---|---|---|---|
| 0.6.1 | GPU | 1,130 / 2,256 / 4,353 | 2,634 / 8,495 / 12,868 | 19 of 32 | 2 of 13: 4,094, 1,139 | 11 (11, 1,295) | 4,300 / 12,868 | 238 |
| 0.6.1 | GPU | 1,084 / 2,279 / 4,357 | 2,631 / 8,442 / 12,693 | 19 of 32 | 2 of 13: 4,069, 1,119 | 11 (11, 1,303) | 4,357 / 12,693 | 238 |
| 0.6.1 | auto | 1,465 / 3,265 / 6,614 | 2,324 / 11,770 / 12,060 | 16 of 32 | 2 of 12: 3,421, 1,131 | 11 (11, 1,653) | 4,372 / 12,060 | 223 |
| 0.6.1 | auto | 1,504 / 3,115 / 6,655 | 2,119 / 11,763 / 11,854 | 16 of 32 | 1 of 12: 3,420 | 11 (11, 1,249) | 4,095 / 11,854 | 222 |
| model kept after a run | GPU | 1,150 / 1,705 / 4,360 | 2,604 / 6,544 / 8,519 | 19 of 31 | 1 of 14: 1,144 | 11 (11, 1,289) | 1,530 / - | 244 |
| model kept after a run | GPU | 1,084 / 1,717 / 4,266 | 2,682 / 6,625 / 8,429 | 19 of 32 | 1 of 14: 1,120 | 11 (11, 1,337) | 1,530 / - | 244 |
| model kept after a run | auto | 1,431 / 3,050 / 6,632 | 2,503 / 7,149 / 11,849 | 17 of 32 | 1 of 12: 1,215 | 11 (11, 1,206) | 2,915 / 5,610 | 230 |
| model kept after a run | auto | 1,452 / 2,843 / 6,486 | 2,388 / 7,277 / 11,568 | 16 of 31 | 1 of 12: 1,121 | 11 (11, 1,685) | 2,752 / 5,482 | 231 |
| and warming | GPU | 1,103 / 1,701 / 4,331 | 2,631 / 6,597 / 8,487 | 19 of 31 | 1 of 14: 1,005 | 11 (11, 1,295) | 1,583 / - | 244 |
| and warming | GPU | 1,153 / 1,828 / 4,253 | 2,646 / 6,668 / 8,413 | 19 of 32 | 1 of 14: 741 | 11 (11, 1,314) | 1,644 / - | 243 |
| and warming | auto | 1,550 / 3,322 / 6,671 | 1,714 / 6,169 / 12,319 | 16 of 32 | 0 of 10 | none | 2,677 / 5,354 | 213 |
| and warming | auto | 1,474 / 2,933 / 6,681 | 1,828 / 7,244 / 11,919 | 17 of 31 | 0 of 12 | 11 (11, 1,232) | 2,783 / 5,621 | 228 |
| and the lines kept | GPU | 1,139 / 1,877 / 4,538 | 2,082 / 5,455 / 8,711 | 22 of 31 | 0 of 14 | none | 1,326 / 2,465 | 223 |
| and the lines kept | GPU | 1,075 / 1,873 / 4,110 | 2,054 / 5,469 / 8,286 | 22 of 32 | 0 of 14 | none | 1,326 / 2,459 | 222 |
| and the lines kept | auto | 1,468 / 3,205 / 6,617 | 1,802 / 6,575 / 11,862 | 18 of 32 | 1 of 12: 1,160 | 2 (2, 762) | 2,820 / 5,497 | 210 |
| and the lines kept | auto | 1,473 / 3,142 / 6,817 | 1,830 / 6,211 / 12,066 | 18 of 32 | 1 of 12: 1,160 | 2 (2, 767) | 2,787 / 5,558 | 210 |

The slowest first bubble is in every run the first page after the window's start, while the OCR models load. "-": the
page was still filling at the next turn.

*The model kept after a run.* The first page after it: the first bubble 1.53 s (GPU) and 2.75 to 2.92 s ("auto")
instead of 4.10 to 4.37 s, the page finished in 5.5 to 5.6 s ("auto") instead of 11.9 to 12.1 s; the first request
computed in full there (3.4 to 4.1 s) is gone, the one at a cut (1.1 to 1.2 s) stays; the p90 of a finished page 6.5 to
7.3 s instead of 8.4 to 11.8 s.

*Warming.* With "auto", no first request was computed in full any more (one before, 1.1 to 1.2 s); with the GPU the one
left, after a run, came shorter (1,005 and 741 ms against 1,120 and 1,144: a warming the turn stopped after one or two
steps). The turn to the first page of the cancelled-in-flight scenario ("auto"): the first bubble 1,595 and 1,597 ms
instead of 2,706 and 2,678, the page finished in 1,846 and 1,828 ms instead of 2,961 and 2,926, its first request 126
and 109 ms instead of 1,263 and 1,170. Each run warmed 34 to 37 times, 33 to 35 of them sending nothing (the server
held the beginning), in 20 or 21 steps of 190 ms (median); no first request waited for a step. The OCR stage (median /
p90 of the rested turns) stayed where it was: GPU 284 / 806 and 297 / 803 ms against 286 / 787 and 289 / 791, "auto"
358 / 1,949 and 440 / 1,927 against 422 / 2,050 and 430 / 1,896; on the two turns where a step was in flight as the
reader turned, the detection took 250 and 324 ms instead of 172 to 180 (the card shared with the step). A first version
that took the server's state after a cancelled request as unknown warmed what the server held already and so kept its
prompt cache in RAM from giving back the state the next page needed: two first requests a run computed in full (1.2 to
3.3 s); mended before the commit. `tools/prompt_replay.py --mode page` with the gold answers, with and without
`--warm`: the 1,421 requests' prompts are the same (one digest), and the first requests of a page that parted from
the server's state at a cut fell from 25 to 0. With the model's own answers (`--answers live --start-ollama 11436`,
seed 1) the 369 first requests of a page took 30.4 s of the server's prompt time instead of 61.5 s (0.5 s or more: 2
instead of 28). The answers are not all the very same, though: the warming has the server compute the same beginnings
in other batches, and with the same seed an answer can come out otherwise (the first one on page 10 of the first
series), and the prompts after it with it. `tools/openmantra_eval.py --mode page --warm` (the official arm, seed 1,
against the same without `--warm`): chrF 41.12 against 41.22, -0.09 [-0.47, +0.23], 162 of the 1,586 lines scored
otherwise, none untranslated, flagged 2.5 % against 2.6 %: the same kind of change as the full-size window cache's
above (a request computed on another cache), within what one seed to the next varies.

*The lines kept.* The page come back to (in the turning back, a spread whose second page was left before its end in the
slow reading): 2 requests instead of 11 (the line whose request was under way at the turn, and its asking again for a
bare romanisation: 762 and 767 ms instead of 1,232 to 1,314), and the page finished at the first return (1,828 and
1,868 ms), where before it was still filling at the next turn 2.7 s later and was finished only at the second return
(2,459 to 2,646 ms). With the GPU the page was even finished before it was left (5,455 and 5,469 ms of the 5.9 s): the
lines kept of a page left earlier (page 8) moved the cut back to the newest 20 pairs onto page 20's first request,
which the warming had computed before it, from the middle of page 20's request (1.1 s). With the GPU they also moved a cut
onto the first request of page 14, which a warming stopped by the turn had computed in part (that prompt 385 ms): the
first bubble 1,945 and 1,878 ms instead of 1,600 and 1,514, the page finished in 5,356 and 5,227 ms instead of 6,597
and 6,668. With "auto" they moved a cut onto the first request of page 22, turned to straight from page 20 with no
time to warm: that turn's first bubble 3,634 and 3,678 ms instead of 2,425 and 2,489. A cut costs the same wherever it
falls; whether it falls before a page's first
bubble depends on how many lines the pairs hold, which is now what was translated. Over the runs: pages finished before
the next turn 22 instead of 19 (GPU) and 18 instead of 16 or 17 ("auto"), requests 222 and 223 instead of 243 and 244,
and 210 instead of 213 and 228, requests computed in full 3 instead of 6 (GPU) and 5 as before ("auto"). In every run:
soft frames left in the cache 0, results kept from a frame other than the sharp one 0, stale lettering 0.

**The benchmark.** `tools/openmantra_eval.py --seed 1`, the official arm, whole book, on the server TASlation starts
(`--start-ollama 11436`), one geometry scan for both, 0.6.1 against the three changes:

| code | chrF | paired difference, 95 % interval | lines with the same chrF | untranslated | flagged | detection F1 | translation |
|---|---|---|---|---|---|---|---|
| 0.6.1 | 40.99 | | | 0 | 2.65 % | 97.19 | 295.9 s |
| the three changes | 40.99 | +0.00 [+0.00, +0.00] | 1,586 of 1,586 | 0 | 2.65 % | 97.19 | 294.4 s |

A whole-book run asks the same requests as before (no warming in a run, no page turned away from), and the shared code
(the request, the asking again of a bare romanisation) translates every line as it did.

**Not built.** Warming at the window's start: until the first page is recognised neither the book nor its series sheet
is known, so neither is the beginning of the first request; without a sheet it is the dataset tag and 25 tokens, about
0.07 s. A cut inside a spread's request (its second page's lines after the cut) cannot be computed ahead without
changing the prompts.

**Found on the way.** In one run of a first version of the lines kept (which did not keep a line asked again for a bare
romanisation before the turn), the window's process started 1.4 s later than in the other runs and was ready at 7.74 s instead of 4.8 s, 40 ms
after the stand-in turned to the third page; the job on that page's soft frame then held the worker, and the page's
first bubble came 21.6 s after its sharp frame. It looked like the gate's `GATE_LIMIT_S` (15 s); it was not: the cause
is in the next section. The run is not in the table above.

## The first page at the start, soft frames, and the first request before the OCR ends (2026-11-20)

**How it was measured.** The machine and the server of the section above. The stand-in viewer:
`tools/standin_e2e.py --scenario a,e,x --start-ollama 11436 --seed 1` (the slow reading, the turning back, requests
cancelled in flight), with `--ocr-runs-on gpu` and with `auto`, two runs of each per code, one after the other; the
scenario c (turns while the window starts) for the start. With one seed every run draws the same soft pictures for the
same time, so a turn is also compared with the same turn under the other code. The window's start was traced (the
window's methods, `PageGate`, the worker's spans) with a turn forced to come 40 ms after the window is ready. The
owner's Ollama on 11434 had no model loaded before or after any run. One run that another program slowed (its OCR
stage 20 to 40 % longer on turns the change does not touch, ready at 7.05 s) was run again and left out.

**The wait at the start (`2035ef2`).** A page turned to as the window became ready was the first to use the layout
model, so its detection imported the model's code and loaded it: 5.2 s (4.4 s the import of
`RTDetrV2ForObjectDetection`, 0.5 s `from_pretrained`, 0.09 s to the GPU, 0.4 s the first forward), where no cancel
reaches a job. The soft frame's gate was dropped 56 ms after the sharp frame came, but the dropped job held the worker
until that load ended, and the sharp frame's job began about 6 s late - about 19 s in the run found on the way above,
whose window started on a slow minute. No gate waited: the 15 s was not `GATE_LIMIT_S`. The trace showed a second
hole: the look that runs a page queued while the models loaded (`_look`) took the frame the follow had captured tens
of ms before as settled, so a soft frame could be read with no gate.

Now the start imports the layout model's code on a thread of its own while the OCR readers load, when the settings
use the model (`pipeline.layout_wanted`, `layout.prepare`: nothing is loaded, no GPU memory taken); the weights load
where they did. The look leaves a frame its follow is settling to the follow, which starts it early with a gate of
its own (`_settle_now`).

| | 0.7.0 | `2035ef2` |
|---|---|---|
| a turn 40 ms after ready (two runs): the first bubble, from the sharp frame | 7.17 s, 7.13 s | 2.56 s, 2.59 s |
| the same: the page finished | about 11.2 s | about 6.6 s |
| the layout model's first load, in that page's job | 5.2 s | 0.65 s |
| the dropped soft-frame job leaves the worker, after the turn | 6.0 s | 1.29 s |
| scenario c, the turn while the models load (its third): the first bubble, GPU | 4.36 s, 4.27 s | 2.18 s |
| the same, "auto" | 6.63 s, 6.49 s | 4.30 s |
| the page on show at the start (a, e, x): the first bubble, GPU | 12.3 s / 14.0 s | 10.2 to 10.4 s / 12.2 to 12.4 s |
| the same, "auto" | 14.2 s / 16.2 s | 11.2 to 11.7 s / 13.1 to 13.3 s |
| that page's detection | 6.0 to 6.3 s | 3.4 to 3.9 s (GPU), 1.8 to 2.2 s ("auto") |
| ready, after the window's launch, GPU | 4.74 to 4.95 s (9 of 10 runs; one 7.74 s) | 4.73 to 5.04 s (7 runs) |
| the same, "auto" | 6.08 to 6.20 s (10 runs) | 6.41 to 7.31 s, median 6.54 s (7 runs) |

The page on show at the start: from the stand-in showing it, which it does either as the window is launched or 2 s
before (the two values). The cost is at the start: the readers' load shares the processor with the import. In a
process of its own, `load_readers` took 2.69 to 2.77 s alone and 3.44 to 3.54 s beside the import with "auto", 3.07
to 3.09 s and 3.73 to 3.92 s on the GPU (three of each); the import thread at below-normal priority changed nothing
(3.50 to 3.58 s, 3.84 to 3.99 s). In the window the GPU's ready did not move (its start waits for other things
meanwhile) and "auto"'s came about 0.4 s later; the page on show then letters 1.6 to 2.1 s (GPU) and 2.5 to 3.0 s
("auto") sooner all the same.

*Recorded again for a video, the same day.* `tools/promo_video.py record --turn-at-ready` and `--from-start`
(`--start-ollama 11436 --ocr-runs-on gpu --layout spread`, 0.7.0 through `--package`), three runs a side, nothing of
the window held back: the turn came 0.09 to 0.17 s after the window's own "ready", which came 4.5 to 4.8 s after the
window appeared.

| | 0.7.0 | 0.8.0 |
|---|---|---|
| a turn as the window becomes ready: the first bubble, from the stand-in's draw of the page | 8.37, 8.55, 8.42 s | 6.18, 6.29, 6.46 s |
| the same, from the sharp frame | 8.04, 8.23, 8.09 s | 5.85, 5.96, 6.14 s |
| the same: the last bubble | 11.39, 11.61, 11.58 s | 9.28, 9.42, 9.49 s |
| the page on show at the start: the first bubble, from the window's appearance | 14.09, 13.41, 13.43 s | 12.07, 12.19, 11.32 s |
| the same: the last bubble | 17.58, 16.71, 16.76 s | 15.50, 15.97, 14.69 s |

The gain is 2.1 s here (25 % of the time to the first bubble), not the 4.5 s of the trace above. Why the two differ
is not established. In these recordings the Ollama that TASlation started was still loading the translation model as
the turn came, and both versions waited for it; the trace's turn came later in the start. The page on show at the
start is 1.5 to 2 s slower here on both sides than in the table above, perhaps for the recorder's own load (about
14 pictures a second); that is not established either. What a person who turns at once will see is nearer to this
table.

*The same wait at other moments.* The import is paid once in a process, now at the start. The weights (0.65 s, no
cancel there either) load again on the first page after anything that lets the page models go, which happens before
every load of the translation model: after the keep-alive ran out, "Release the model now", Auto off after a
whole-book run, another model or language. A soft frame's job dropped in that detection holds the worker up to that
long (a detection of 0.7 to 0.8 s on such a turn in the runs before 0.7.0); unchanged, and on a viewer that draws soft
first that frame is no longer started (below). Leaving the full screen, choosing the viewer again, a resize and a
whole-book run with Auto back on let nothing go: in scenarios r, t, z, f2, w and w2 (four runs of 0.7.0 and the full
set once) no detection took 0.7 s or more.

*Tests.* `tests/test_gate_at_ready.py`: the window ready 0 to 380 ms after a turn to a page drawn soft first (20
cases, and two with the frames not counted): the job on the soft frame has a gate and keeps nothing, the sharp frame's
page is kept; a sharp frame seen while the models loaded starts with a gate as they are ready and is kept after the
fixed time; 22 of the 23 cases fail on 0.7.0. `tests/test_model_at_start.py`: the layout code is imported on
its own thread at the start, before the weights, and a page does not wait for it; nothing is imported when the model
is not used (the import stood in for by a module that takes 0.4 s).

**Soft frames on a viewer that draws soft first (`586424e`).** Measured first, on `2035ef2`: on the turns with a job
on the soft frame the sharp frame's job began 294 ms (GPU) and 300 ms ("auto") after the sharp frame was drawn
(median); the sharp job's own detection and OCR took as long as where the soft frame was not started (below:
detection 165 to 176 ms, the OCR within 10 ms), so the cost was the wait for the dropped job to end, not a slower
sharp job. 11 to 14 jobs a run were started on soft frames; on the GPU one a run sent a request.

Now `_early_start` leaves a frame that `_looks_soft` says is soft (only on a viewer `_drew_soft` has seen draw a page
soft first, for a page the cache does not hold whole); the frame is looked at every step and the sharp frame is
started at its first look. A frame that stays as it is - a page low in detail - is started once it has stayed
settle_ms, when the settle path takes a page, with a gate as before; a page turned to while a job ran (that job
cancelled once the frame stayed LEFT_PAGE_MS, as before) waits no longer than that either. A viewer never seen to draw
soft first measures nothing and goes as before; the gates are untouched.

| code | OCR | jobs on soft frames a run | requests from a soft frame | sharp frame to its job, ms (median / p90 / slowest) | first lettered bubble, ms (median / p90 / slowest) | page finished, ms (median / p90 / slowest; pages finished before the next turn) |
|---|---|---|---|---|---|---|
| `2035ef2` | GPU | 14, 14 | 1, 1 | 292 / 356 / 421 | 1,308 / 2,025 / 2,135 | 3,832 / 5,906 / 6,090 (20) |
| `586424e` | GPU | 5, 5 | 0, 0 | 219 / 496 / 544 | 1,264 / 1,948 / 2,042 | 3,652 / 6,110 / 6,442 (20) |
| `2035ef2` | auto | 12, 11 | 0, 0 | 287 / 393 / 470 | 2,278 / 3,579 / 4,451 | 4,490 / 5,771 / 7,022 (13) |
| `586424e` | auto | 4, 4 | 0, 0 | 224 / 390 / 455 | 1,921 / 3,623 / 4,310 | 4,484 / 6,997 / 7,402 (14) |

24 turns over the two runs of each: in each run the slow reading's nine and the three pages of the cancelled-in-flight
scenario that the cache does not hold (the turning back's pages all come from the cache), timed from the stand-in's
sharp frame.

Turn for turn: the soft frame is no longer read on 6 of the 9 slow-reading turns on the GPU and 4 with "auto"; there
the sharp frame's job began 116 and 119 ms sooner (median; sooner on every one) and the first bubble came 131 ms (5 of
6 sooner) and 229 ms (3 of 4) sooner. The jobs left on soft frames: the first turn after the start (the viewer not yet
seen to draw soft first), and soft pictures drawn for settle_ms or longer (409 ms on one turn with the GPU, and the 708 to
720 ms of the cancelled-in-flight scenario's pages), started at settle_ms as the settle path takes a page. The one drawn
409 ms was started just before the sharp frame came, and its detection, which no cancel reaches, held the worker: that
turn's first bubble 1,871 ms instead of 1,609 (GPU). A first
version that started a held frame as soon as a cancelled job had left the worker still read 5 to 7 soft frames a run;
the commit holds that one too. In every run: soft frames left in the cache 0, results kept from a frame not the sharp
one 0, stale lettering 0.

*Tests.* `tests/test_early_start.py`: on a viewer that draws soft first, the soft frame (shown 0.15, 0.3 or 0.38 s)
starts nothing and the sharp frame starts at its first look; a frame that looks soft and stays starts at settle_ms,
no later; the same two for a page turned to while a job runs; a frame not counted is looked at every step; a viewer
never seen to draw soft first starts every frame at once (no crispness measured). The soft pictures drawn longer than
settle_ms are started at settle_ms and never kept, as the test of them asks.

**The first request before the page's OCR ends: measured, not built.** The question: could a page's first request go
out as soon as its lines are certain to be first in the final order and certain to be lettering to translate, before
the rest of the page is read? Measured with the real pipeline (the layout model, the three readers, the window's
settings) on the 214 OpenMantra pages, one page and two to a screen, the readers on the GPU and on the processor; a
page's job stopped where its first request would go out (`_translate_regions`), the time of each region's verdict
(the fill's "read" event), each reader's calls, and the first request's lines (the first line to translate, the run
it opens, the line after it, whose box decides the join, and those after an open run). 8 pages were left out (no line
to translate, or a first-request line with no reading event of its own); numbers only.

| OCR on | screen | pages | OCR before the first request, ms (median / p90) | every candidate read once for the page's size | the first line judged | the first request's lines judged | sooner, were its lines known then, ms (median / p90) | sooner, its lines certain, ms (median / p90) |
|---|---|---|---|---|---|---|---|---|
| GPU | one page | 206 | 601 / 963 | 335 | 377 | 419 | 184 / 371 | 7 / 16 |
| GPU | two pages | 102 | 597 / 912 | 330 | 370 | 410 | 191 / 357 | 7 / 15 |
| processor | one page | 206 | 1,261 / 2,027 | 558 | 658 | 772 | 505 / 956 | 8 / 19 |
| processor | two pages | 102 | 1,309 / 1,970 | 568 | 659 | 776 | 516 / 934 | 8 / 19 |

(Medians, ms from the OCR's start. Two pages to a screen: the page read first, the right one; the other is read
beside its requests already.)

The first line in the final order is the first line judged on 202 of the 206 pages, but its verdict waits for the
reading every candidate gets first, for the page's usual character size (`_usual`: so that no region's fate hangs on
the order of reading), and the first request's lines are all judged at 60 to 70 % of the OCR (419 of 601 ms on the
GPU, 772 of 1,261 ms on the processor). Even had those lines been known at that moment, the request would have gone out 184 ms sooner on the GPU
(median) and 505 ms sooner on the processor. They are not known then: the final order is made over the regions read
as text alone, with the panels found from their lettering (`_order_read`, `order_on_page`), and lines become print or
titles, or are read again as a paragraph, by rules over all the page's regions (`printed_lines`, `_titles`, `_prose`).
A region judged later can so put another line first, join two, or take the first one out; the first request's lines
are certain only once the last region is judged, 7 to 8 ms (median) before the request goes out now. By the brief's
rule (a median gain of 0.2 s or more) it was not built; a request sent on a guess and taken back would change what a
request holds.

What the OCR's time is spent on, the same runs (214 pages, one to a screen):

| reader | crops | ms a crop, GPU | ms a crop, processor | share of the OCR, GPU / processor |
|---|---|---|---|---|
| charspot | 3,909 | 15.7 | 28.3 | 48 % / 41 % |
| nar | 1,601 | 25.6 | 82.3 | 32 % / 49 % |
| CPT (on the processor in both) | 102 | 107.1 | 120.7 | 8.5 % / 4.5 % |

A page has 18 candidates (median; p90 27), of which 8 become lines to translate (p90 12) and 7 are left out as the
same lettering as one read before (the layout model's box and the classical region of one bubble). Every crop is read
on its own; nothing is batched. What else would shorten the OCR's share, and what each could give at most:

* Fewer candidates read that are thrown away: the readers spend 168 ms a page on the GPU (median, 32 % of their time)
  and 306 ms on the processor on candidates that end as no line, 118 and 214 ms of it on those left out as repeats,
  which charspot reads in the pass for the page's size before the repeat is seen. Leaving them out of that pass
  changes the samples the page's size is taken from, so it needs the benchmark to show the same verdicts.
* The third reader only where the first two differ: so it is already (`readers.agree`): CPT reads 102 of the 1,601
  lines nar reads, 6 %, and takes 8.5 % of the OCR with the others on the GPU. On the GPU it would take less, for its
  440 MB of weights kept there for a few crops a page.
* Crop batching: charspot's 15.7 ms and nar's 25.6 ms a crop on the GPU are for crops read one by one; reading the
  pass for the page's size as one batch is the largest single share (335 of 601 ms). The readers were built without
  padded batches; not measured.
* The placing on this 6 GB card: with "auto" the rule finds no room for charspot and nar beside the model the window
  keeps loaded ("no_room"), and all three read on the processor; the OCR stage of the stand-in turns above was 854 ms
  ("auto") against 452 ms (GPU), and the first bubble 2,278 ms against 1,308 (median). Every GPU run here read on the
  GPU with no error recorded; the rule's margin on such a card is the largest lever, and needs the card's peak memory
  measured with the readers there before it is moved.

**Every scenario at the end.** `tools/standin_e2e.py --scenario all --start-ollama 11436 --seed 1` ("auto") on
`586424e`: exit 0; in every segment stale lettering 0, results from a soft frame 0, wasted requests 0; soft frames
left in the cache 0, results kept from a frame not the sharp one 0.

## The reading order: a region under another, and art across a gutter (2026-11-20)

**How it was measured.** On the OpenMantra pages, the annotation's order of a page's text taken as the truth, on
`4bebb97` and with the two commits: `tools/reading_order_eval.py --no-pipeline` (the gold boxes as regions, the panels
found from them), and the pipeline's own regions before reading (the tool's default, the classical detector; and the
layout model, `--detect-model auto`), scored on the regions that match a gold box. A page is wholly right when no pair
of its boxes is out of order; the first box right and the boxes out of place (a page's boxes less its longest run in
the true order) were scored on the same sequences by a script of the tool's functions. The order after the OCR, as the
translator gets it (the window's settings: the layout model and the three readers on the GPU), from the scans of the
two benchmark runs below (`--scan`, in a scratch folder: per page the matched regions read as text in the order handed
over); which change moved a page there, from the same pipeline on those pages with one change taken out. The finder
alone: the fastest of five calls on each of the 214 pages, two runs of each code, one after the other. Numbers only.

**A region under another (`9c789d9`).** Inside a panel, and on a page without panels, the rows' order stays, but a
region under another - the two overlap side to side by more than half the narrower one's width, and its centre is
lower - comes after it, also where a tall region beside them put the two in one row and the lower one is further
right, which right first would read first (`bubbles._over`, `_in_rows`): each time, the first region in the rows' order
with none over it still to come.

**Art across a gutter (`2aa7238`).** A part of a page with no cut, level or slanted, is looked at once more with level
gutter lines that art may cover for up to a fifth of their length in place of 4 % (`RELAXED_FOREIGN`: a figure that
breaks the frames across the gutter, effect lines over it), where the run of such lines has a frame along both sides:
ink within 3 work-scale pixels beyond both of its edges along half of it (`panels.relaxed_cuts`). Measured so first,
the pass broke one page (boureisougi p36): two panels side by side over a strip with no frame, whose top a bubble
hanging under the right panel kept with them; the cut between the two ran on past both frames into the strip, and the
strip's bubble went with the right panel, before the left one's. Now the run must also have ink beyond one edge or the
other near both of its ends. That test acts on this one page and costs none of the pages the pass puts right; with the
gold boxes as the lettering the pass cuts 8 times, on 7 of the 214 pages. Not built: frame lines counted as gutter in
that pass (7 pages better and 2 worse in the study, but the finder's precision 61 %, and the panel box limits the room
of lettering on the art), a pairwise "right first" rule, columns first inside a panel; the order of the panels, right
first within a row and the row chaining (without it 12 pages fewer right) are as they were.

| regions | pages | wholly right | first box right | boxes out of place | pairs out of order |
|---|---|---|---|---|---|
| gold boxes, panels found: `4bebb97` | 199 | 160 (80.4 %) | 196 | 48 | 88 |
| the same, a region under another alone | 199 | 162 | 196 | 46 | 85 |
| the same, art across a gutter alone (without the test at the ends) | 199 | 164 (163) | 196 | 42 (43) | 78 (79) |
| the same, both | 199 | 165 (82.9 %) | 196 | 41 | 76 |
| the pipeline's regions before reading, classical detector | 193 | 160 (82.9 %) -> 163 (84.5 %) | 189 -> 189 | 42 -> 38 | 78 -> 71 |
| the same, the layout model | 197 | 161 (81.7 %) -> 165 (83.8 %) | 194 -> 195 | 46 -> 40 | 87 -> 78 |
| after the OCR, as the translator gets them | 193 | 159 (82.4 %) -> 163 (84.5 %) | 190 -> 190 | 44 -> 38 | 87 -> 78 |

Per series, pages wholly right (gold boxes / after the OCR): tojime_no_siora 37 -> 40 of 43 / 36 -> 39 of 42,
boureisougi 12 -> 13 of 31 / 13 -> 14 of 31, balloon_dream 30 -> 31 of 36 / 30 of 34, rasetugari 49 of 50 / 47 of 48,
tencho_isoro 32 of 39 / 33 of 38. Pages put right on the gold boxes: by the first change tojime_no_siora p4 and p8, by
the second tojime_no_siora p2 and p8, balloon_dream p4 and boureisougi p11; none worse. After the OCR six pages changed,
none for the worse: tojime_no_siora p4 and p18 right and boureisougi p12 better by the first change, tojime_no_siora p2
and boureisougi p11 right and boureisougi p21 better by the second. Before reading, with the layout model, one page went
wrong (tencho_isoro p25): a candidate that matches no gold box, a box across two bubbles, stood over a third bubble's
region, which then came after the bubble beside it; the OCR leaves that candidate out, and after the OCR the page is
right as before.

The finder against the gold panels: 1057 to 1082 panels found, 821 to 839 paired, recall 76.8 to 78.5 %, precision 77.7
to 77.5 %; its time 9.9 and 10.4 ms a page (mean; median 6.5 and 6.8) to 11.4 and 11.3 (median 7.7 and 7.4); the order
of a page's regions 0.04 to 0.06 ms. The panels the window finds once the page is read (from the lettering of the
regions read as text alone; the same pipeline, the second pass on and off in one run): the panel box changes for 31 of
the 1,590 regions, on 6 pages, 3 of whose order changes; 25 of the 31 are the layout model's lettering on the art, whose
room `_art_room` grows up to its panel's edge, and that room changes for 3 of them at most (every glyph counted large),
smaller now, ending at the frame found. Not lettered and looked at.

**The benchmark.** `tools/openmantra_eval.py --seed 1 --start-ollama 11437` (TASlation's own server, KV cache q8_0,
full window), once on each code: every number the same, and the same 11,218 tokens generated in 1,418 requests.
Detection F1 97.2 % (P 96.0, R 98.5), 1,590 regions read as text, 1,526 matched; CER 1.9 % (corpus) on the gold boxes,
1.4 % on the matched regions; chrF 41.0, 1,586 of 1,586 lines translated, 2.6 % flagged. (On the Ollama already
running on the machine, with its own settings, the same command gave 41.2 and 2.5 % on `4bebb97`: the server
differs, not the code.) The official arm translates the gold
text in the gold order, each line set in its matched region's box, mask, text box and lettering box, so neither the
order nor the panel box reaches it; the order the window hands the translator is the row "after the OCR" above.

*Tests.* `tests/test_detect.py`: a region under another and a little further right, put in one row by a tall one
beside them, comes after it, mirrored for left-to-right books and inside a panel, while one that overlaps it by less
than half the narrower width keeps right first. `tests/test_panels.py`: a figure across the gutter between a tall
panel and two stacked ones is cut there and the order follows the panels, art over more than a fifth of the gutter is
not; a pale band between two figures with no frame is not cut, the same band with a frame along both edges is; a gutter
that runs on past both frames into a strip with no frame is not cut, the same gutter where the panels end with their
frames is. All five fail on `4bebb97`. `test_lettering_on_a_gutter_does_not_hide_it` now draws lettering over more than
a fifth of the gutter's lines: what it covered before, about 4 %, the second pass now cuts through.

## Looking for a new version and updating (2026-11-21)

**What was added.** `check_update.py`, a program of its own beside `setup_models.py` (standard library only, never
imported by the package); `update.ps1 -Download`, `-Version`, `-WaitFor`, `-Confirmed`, `-Restart` and `-Back`;
Help > Check for updates... with its "Update now"; the setting `update_check` ("off" by default, "daily"); the
installer's one question. TASlation's own process is as before: it starts the program as a process of its own and
reads its one line of JSON. `taslation/netguard.py` is unchanged but for its docstring.

**What goes to GitHub, and when.** The look: one GET of the project's `CHANGELOG.md` on raw.githubusercontent.com
with `Range: bytes=0-16383`, so the request stays the same 16 KB however long the changelog grows. Its headers are
Host, a fixed User-Agent (`TASlation-update-check`: no version, no system), Accept, Accept-Encoding and Range; no
query string, no cookie, nothing of the person, the computer, the installed version or the books. It is sent when
Help > Check for updates... is chosen (not again within 60 seconds of an answer), and with `update_check = "daily"`
at most once a day, 30 seconds or more after the window is ready and while nothing is read or translated; never in a
folder that is a git clone. The download: one version's ZIP from github.com (which sends it on to
codeload.github.com), only on "Update now" or a yes in `update.cmd`. A redirect is followed to those three hosts
only; an answer over 1 MB (the look) or 60 MB (the ZIP) ends the run; the look ends after 10 seconds. The ZIP's every
entry is read back before it is used, and it must hold the version that was announced, newer than the installed one.

**How it was checked.**

- On a loopback server, with no request leaving the computer: `tests/test_check_update.py` (the request as the
  server saw it, the Range, a part cut inside a line or an entry, a server that ignores Range, redirects to another
  host, answers too large, broken off or slow, a wrong version string, a ZIP joined from two builds),
  `tests/test_updates_window.py` (the menu item, the dialog's states, the once-a-day rule with a made-up clock, no
  dialog and no focus taken by the look at the start, the 60 seconds, a git clone; with the guard on, the window's
  process made no connection while the program beside it asked: blocked none, allowed none),
  `tests/test_update_script.py`, `tests/test_install_scripts.py` (the question asked once, Enter is no).
- `tests/test_update_now_run.py`: the command line the window builds is really started through cmd.exe in a scratch
  folder whose path holds a space, parentheses and an ampersand: the wait for the closing window, the download from
  a stand-in, `.previous` with its note, the new files, a stand-in installer run with `TASLATION_UPDATING=1`, the
  restart. The run found one fault, fixed before the release: the restarted TASlation inherited the update's own two
  variables.
- Against GitHub itself, four looks and one download: from a folder at the public version "up to date", from a scratch
  copy marked 0.8.0 "newer" with the 0.8.1 entry (548 characters), both again after the request was cut to its
  first 16 KB with the same answers, and the ZIP of 0.8.1 once (4,602,405 bytes, 607 entries, every entry read
  back).
- The whole suite: 5,206 passed, 22 skipped. `tools/standin_e2e.py` (every scenario, 335.5 s): 0 wasted requests, 0
  stale lettering, 0 soft frames confirmed or left in the cache, the whole-book run finished its 5 pages. The
  official benchmark: F1 97.2, 1,586 of 1,586 lines translated, chrF 41.2, 2.5 % flagged, as for 0.8.1. Its
  translation took 372.8 s where 294 s was measured before: no file on the translation's way changed since 0.8.1,
  the same 47 requests were computed again (56.8 s) and the answers took the same 94.5 s, but the prompts ran at
  6,635 tokens a second instead of about 9,800 while other programs of the desktop used the GPU that morning.

**Not checked.** "Update now" on a real installation: on the development computer the installer that follows would
change the Ollama settings of a program in use, so the chain was run in scratch folders with a stand-in installer
only. A computer that reaches the network through a proxy only: the program uses none and says that GitHub could
not be asked; the ZIP by hand works as before.

## A request without an answer, on a real server (2026-11-21)

The rule for a request without an answer (`translate.ollama`, `NoAnswer`) on its own, without the work behind the
reader. It came from a stop seen in the stand-in runs: Ollama 0.40.16 took every request and passed none to its model
process for 2 min 28 s, /api/ps answering all the while, and a reader who turned every 8 s cancelled each request
after 6 to 7 s, before its own 30 s. The wait for a first byte is therefore counted over the requests in a row that
got none (`_Waits`), the time with none under way left out, and any byte of any request to the model starts it again.
On the stand-in server of `tests/test_no_answer.py`, which takes every request and sends nothing, at the module's own
bounds: a reader turning every 7 s, 2 s between pages, was told `ollama.no_answer` at 30.0 s waited in all, on the
fifth page; turning every 6 s, the fifth request reached 30 s as its turn cancelled it and the sixth was ended at once,
told 30.1 s. Before, no request at either pace reached its own 30 s.

Then a real Ollama 0.40.16 on a port of its own (11435; the default port's server was never asked), with the window's
translator (`make_translator`, PLaMo) and `OllamaStarter`'s revive and restart hung on it as the window hangs them, on
a page of six made-up lines: after the second line was answered the server's model process (`llama-server.exe`) was
suspended - not ended. Ollama does not wait for a model process that stops: it starts another and loads the model in
it, /api/ps answering. With the first process alone suspended, the new one answered the third line 25.4 s later and
the rule was not needed. With every model process of that server suspended as it came:

| | a start record names the server | no start record (a server the person runs) |
|---|---|---|
| model process suspended | 10.9 s | 10.4 s |
| told it did not answer for 30 s (`ollama.no_answer`) | 41.0 s (30.1 s) | 40.5 s (30.1 s) |
| the request asked again on a new connection: its load | 41.0 s | 40.6 s |
| the second silence: the load past its bound | 101.0 s (60.0 s) | 100.6 s (60.1 s) |
| told it is started again (`ollama.restarting`) | 101.0 s, once | never |
| stopped; started again and answering | 0.1 s; 3.5 s | never touched |
| the model loaded again | 3.9 s | - |
| the page | finished at 109.1 s, 6 of 6 lines | ended at 100.6 s with `ollama.not_answering` |

Before the last change the load of the request asked again had no bound but /api/ps, which answered: it was waited
for `WARM_UP_TIMEOUT`, 300 s, and the page ended with `ollama.timeout` after 330.5 s, the server never started again.
A load within an incident now has `NO_ANSWER_LOAD_S` (60 s, or three times the longest load measured), and the
sentence that the program is started again is said once a restart is under way only: it had been said of a server the
person runs too, which is left as it is. After each run no model process of the test was left, the server started
again was stopped as TASlation's own end stops it, and the default port's server was as before.

The rule changes no answer: the official benchmark (`tools/openmantra_eval.py --seed 1 --start-ollama 11435`) on this
branch and on v0.9.2, the same server set up the same way: 1,586 of 1,586 lines translated, every line with the same
chrF, 41.0 both (the same 1,418 requests and tokens; 293.2 and 294.7 s); detection F1 97.2. The 41.2 of the release
notes for 0.9.0 came from the server on the default port, which is set up otherwise.

The window on the stand-in viewer (`tools/standin_e2e.py --scenario all --start-ollama 11435`, every scenario of
this line's tool: c, a, b, d, e, r, t, t2, o, z, w, w2, x, f, f2) ran to its end in 334.5 s with no request
without an answer, no warning or error in the log, nothing refused by the guard and only the stand-in chosen; the
server it started was stopped at the end.

## Pages turned past go on being read (2026-11-20)

**What changed.** In normal reading, a page the reader turned past while its job was still at work goes on being read
and translated from the capture that job read, in memory, while nothing of the page on show runs
(`taslation/backlog.py`). A page is caught only through its job's gate: confirmed (its frame stayed 0.8 s from the
window's look), not a frame that looked soft on a viewer seen to draw pages soft first, its take-back time over, and
not confirmed while the frames still changed unless a look 0.8 s later still found it on show. What is kept: the read
text and geometry when the job had read the whole screen, else the frame, packed without loss until the backlog's own
read has read it (at most 256 MB of frames and 1000 page units). The page on show always comes first; a step behind
the reader stops at the next job (between two regions of a read, between two line requests of a translation, the
request in flight cancelled) and the lines answered by then are stored. Auto off, Stop and "Release the model now"
pause it; another book, another viewer window and a whole-book run drop it. The window is told by events
(`page_stage`, `page_on_show`, `backlog`), which the indicator beside the page now draws.

**How it was measured.** The development machine of the sections above, a second Ollama server of the tool's own on
127.0.0.1:11435 (the owner's server untouched), the stand-in viewer with the OpenMantra pages, `--seed 1`, the OCR
readers placed by "auto" (on this 6 GB card they read on the processor beside the loaded model: every OCR read of
these runs was on the processor). Scenario k (`tools/standin_e2e.py --scenario k --k-read 10`): at each of three paces
20 pages flipped past (0.5, 1 and 2 s a page), then a jump back to the first of them and 10 of them read at 8 s a page.
Five configurations: the stand-in drawing each page soft first (its own soft time) or sharp at once, in the wide window
(spreads) and in the narrow one (single pages); and the soft wide one with nothing caught (`--k-backlog off`), the
baseline of the same turns. A run takes 6 to 7 minutes; none overlapped another program's run.

**What is caught.** "Stayed" is the stand-in's own log of how long each flipped page's sharp frame was on show.

| configuration | pace | stayed 0.8 s or more | caught | finished while on show | caught or finished = stayed |
|---|---|---|---|---|---|
| soft first, wide | 0.5 s | 0 | 0 | 0 | 20 of 20 |
| | 1 s | 4 | 2 | 0 | 18 of 20 |
| | 2 s | 20 | 19 | 1 | 20 of 20 |
| sharp at once, wide | 0.5 s | 0 | 0 | 0 | 20 of 20 |
| | 1 s | 20 | 20 | 0 | 20 of 20 |
| | 2 s | 20 | 19 | 1 | 20 of 20 |
| soft first, narrow | 0.5 s | 0 | 0 | 0 | 20 of 20 |
| | 1 s | 3 | 1 | 1 | 19 of 20 |
| | 2 s | 20 | 18 | 2 | 20 of 20 |
| sharp at once, narrow | 0.5 s | 0 | 0 | 0 | 20 of 20 |
| | 1 s | 20 | 16 | 3 | 19 of 20 |
| | 2 s | 20 | 15 | 5 | 20 of 20 |

The pages of the soft runs that disagree all stayed 800 to 830 ms by the stand-in's log: the window counts the 0.8 s
from its first look at the frame, which comes 60 to 130 ms after the stand-in drew it (with soft first the sharp frame
is seen later still), so such a page had stayed 680 to 760 ms from the look. The one page of the narrow sharp run
that disagrees (the same page in three runs, on show 994 to 1,006 ms) is low in detail: the run's first segments had
the stand-in draw soft first, the window had learnt that this viewer does, and it took the page's sharp frame for a
soft one (`_looks_soft`), started it once it had stayed settle_ms, with a gate marked soft (the tool records the gate:
`soft_gate`) - and such a page is never caught. The same pace alone (`--scenario k1`, other pages) caught 19 and finished 1 of 20, 20 of 20. The
first run of the soft wide configuration, before `5a44a2c`, caught 2 pages at 0.5 s a page and 4 at 1 s a page that
had been on show 0.16 to 0.77 s: the live view confirms the frame there is once the frames have kept changing for
SETTLE_TRIES looks; since `5a44a2c` such a page is not caught (since `37e24b7`, unless a look 0.8 s after that
confirmation still finds it on show), and no run caught one.

*What every run kept to.* In every run and at every pace: results kept from a frame not confirmed or soft 0 (the
tool's `kept_from_unsettled_frames`), stale lettering 0, frames held after their read 0, bytes held at the end 0,
thumbnails at most 96 px high and with a screen's first event only, peak frames held at most 24.8 MB (the cap is
256 MB), no error logged. Two things the tool counts were seen once each, in the narrow soft run, both from the window
as it was before: a page job whose frame changed before its confirmation had shown two bubbles and was discarded
(nothing kept), and a page the backlog had translated was drawn from the cache on its soft picture for 644 ms when
read back (`_take_at_once` did not find that picture soft); with the backlog more pages come back from the cache, so
this shows more often.

**The page on show while a backlog exists.** The 30 pages read back of the soft wide configuration, turn for turn
against the same turns with nothing caught (ms from the stand-in's sharp frame to the first lettered bubble):

| history | median | p90 | slowest | first requests computed in full | paired difference, median / mean |
|---|---|---|---|---|---|
| nothing caught | 2,052 | 3,462 | 4,107 | 3 | |
| story order | 2,141 | 3,083 | 5,043 | 4 | -22 / -53 |
| order of work | 2,002 | 2,968 | 3,611 | 1 | -66 / -170 |

By pace (median / p90): 0.5 s 2,337 / 3,755 with nothing caught, 2,514 / 2,901 story, 2,281 / 2,968 work; 1 s 2,096 /
3,462, 2,537 / 3,373, 2,284 / 2,970; 2 s 913 / 2,265, 667 / 1,993, 866 / 2,063. (Pages flipped past at 2 s had their
first lines answered and stored before the turn, so their first bubble comes from the cache at once in every column.)
The slow reading of scenario a in the same setting, for reference: 2,837 / 3,235. Ten turns a pace is few: the 188 ms
of the order of work at 1 s a page (median) is within what one turn moves.

What a turn waits for: a step under way stops at the next job, its request in flight cancelled; the worker was free 3
to 277 ms after the stop (max per pace and run), and the page's next request waited at the server 2 to 557 ms (max).
Background requests computed in full: 0 to 9 per pace and run (of 9 to 108), page requests in full 0 to 11 (of 38 to
167), as with nothing caught (5 to 7).

**History: story order or order of work.** With story order (`backlog.HISTORY` "story"), a page the reader turned away
from while its job ran and that the backlog then finished behind the reader put its pairs into the middle of the
reader's history: the reader's next request was computed again from there. On two of the 30 pages read back its first
prompt took 2.6 and 2.1 s (0.17 and 0.07 s in order of work; "context block" by `prompt_replay.why`), and after the
flips at 1 s a page the first bubble came 441 ms later (median) than on the same turns with nothing caught, 188 ms in
order of work. Pages caught ahead of the reader (flipped past, then read back) extend the reader's history in either
order. OpenMantra, `tools/openmantra_eval.py --mode page --behind 4` (a reader who flips four pages past at a time and
reads the page after them, the pages behind translated after it):

| arm | chrF | flagged | translated | requests computed again (their prompt time) | prompt time in all | translation time |
|---|---|---|---|---|---|---|
| page mode, in order (official) | 41.22 | 2.6 % | 1586 of 1586 | 43 (52.4 s) | 159.9 s | 293.5 s |
| behind, story order | 40.82 | 2.6 % | 1586 of 1586 | 49 (76.6 s) | 189.8 s | 322.8 s |
| behind, order of work | 40.90 | 3.0 % | 1586 of 1586 | 47 (70.8 s) | 177.8 s | 312.7 s |

(One run each, seed 1. The official book mode on the same code: F1 97.2, CER 1.9 %, chrF 40.99, 1586 of 1586, 2.6 %
flagged, 294.8 s - as on `4bebb97`.) Story order gives the pages behind the reader no better translation here (-0.08
chrF against the order of work, within what one run moves) and costs the server more. The order of work became the
default; story order, then kept as an internal switch, has since been taken out (the next section).

**How long the backlog takes.** From the jump back until the backlog held nothing, while the reader read on at 8 s a
page (the page on show first). The whole-book run of scenario w on the same code took 36.2 s for its 5 screens in the
wide window, 7.2 s a screen; set beside it, the backlog's screens at most:

| configuration | pace | screens held at most | until empty | its own steps | the whole-book run for as many |
|---|---|---|---|---|---|
| soft first, wide | 1 s | 6 | 94.8 s | 23.2 s | 43.4 s |
| | 2 s | 19 | 115.7 s | 64.7 s | 137.6 s |
| sharp at once, wide | 1 s | 20 | 123.1 s | 55.9 s | 144.8 s |
| | 2 s | 19 | 103.5 s | 57.8 s | 137.6 s |
| soft first, wide, order of work | 1 s | 5 | 91.3 s | 22.8 s | 36.2 s |
| | 2 s | 20 | 119.6 s | 67.4 s | 144.8 s |
| soft first, narrow | 2 s | 18 | 45.6 s | 31.9 s | |
| sharp at once, narrow | 1 s | 16 | 43.6 s | 31.4 s | |
| | 2 s | 15 | 45.3 s | 33.2 s | |

With 15 to 20 screens caught the backlog was empty after 0.75 to 0.85 times what the whole-book run would take for as
many (wide; the narrow window's single pages 2.5 to 3.0 s each, the whole-book run not measured there), the reader's
ten pages read on meanwhile. With few caught (5 or 6 screens, after the flips at 1 s a page with soft first) it took
2.2 and 2.5 times as long: the reader's own pages come first, and in the wide window a page read back took most of
its 8 s (none of them came from the cache: the backlog then read the pages it held in the order they were first seen
and translated them after, so the reader read them before it got to them; it now works nearest the reader first, as
the next section says). The backlog's own steps took 0.39 to 0.63
times the whole-book run's time in every wide run.

**A computer without a GPU.** `CUDA_VISIBLE_DEVICES=-1` with `--ocr-runs-on cpu` hides the GPU from TASlation's own
models but not from Ollama: in that run the model was in video memory. With `--ollama-num-gpu 0` as well (the setting
`ollama_num_gpu = 0`) everything ran on the processor (the System page: detect, OCR, translation and erase on the
CPU). Scenario k2 with 6 pages flipped past at 2 s and 3 read back at 30 s a page (`--k-turns 6 --k-read 3
--k-read-ms 30000 --k-soft off`): 6 of 6 caught, the pages on show finished in 11.2 to 31.6 s, the first bubble of a
page read back 0.58 to 2.68 s (median 0.74 s), the backlog empty 152.9 s after the jump back (its own steps 80.9 s,
13.5 s a page), nothing stale, no error. A request took 0.84 s (median), 1.7 s (p90) and 9.8 s at most for a page,
0.98 / 2.0 / 9.2 s for the backlog; the slowest two were history cuts, computed in full (8.5 and 8.6 s of prompt).
One step was stopped by a turn: the worker was free 249 ms after, and the page's next request waited 29 ms at the
server. Whether a turn could wait for a stopped request's prompt on the processor was measured on its own
(a server of its own, the model on the processor, filler text): a short request sent as the client of a 500- or
900-token prompt (5.8 s and 12.2 s alone) went away 0.5 or 1.5 s into it took 235 to 265 ms, the same as alone (237
and 256 ms): Ollama stops a prompt whose client has gone. So a turn waits for one region's read or the cancel of one
request, a quarter of a second here, not for a step; the steps stay as they are on a computer without a GPU, and the
backlog works there too, never while the page on show is worked on.

**Every scenario at the end.** `--scenario all` on the final code (332 s, the order of work): every segment with 0
wasted requests, 0 stale lettering, 0 lettered on a soft frame, 0 soft frames confirmed or left in the cache, no
error; 60 requests behind the reader; the whole-book run finished its 5 pages; old lettering after a turn at most 379
ms (2 of 28 turns with no job over 250 ms; 1 of 11 with a job running).

*Tests.* `tests/test_backlog.py` (35 at the time): what is caught and what is not (a soft frame, a frame confirmed
while the frames still changed, a frame that changed before its confirmation, a moment, no gate, the caps), what is
kept (the read units, or the frame packed until read, then dropped), the order of the work, a step stopped by the
next page with its answers stored, a page job that ends otherwise giving back what was held for its page, the drops
and pauses, the events and their handlers, the history (the order of work), and the six guarantees of the design,
one test each. `tests/test_early_start.py`: frames that keep changing confirm the frame there is, which
is told as having stayed only when a look 0.8 s later still finds it.

## Pages turned past: nearest the reader first, and their read taken on show (2026-11-21)

**What changed.** In `taslation/backlog.py`, the page job and the live view:

- *The order of work.* The backlog's next step is chosen anew at each step (`Backlog._next`): the page with the
  smallest place in the order of first sight past the screen on show (or the one last on show), else the smallest of
  all - the page the reader is likeliest to turn to next -, and all it needs in order, its read (or its read units
  made) and then its translation, before the next page. The caps are as they were.
- *The read taken on show.* A page the backlog has read, shown again, is not read again (`Backlog.lend`, at the job's
  start once its units are known): when the frame is of the same page units as the capture the read came from (their
  fingerprints within `fingerprint_max_distance`), of its pixel size, and nothing a read depends on has changed
  (`Pipeline.read_signature`: the settings, the reader's annotations of its units, the reading direction, the
  detectors and the OCR reader), the page job takes copies of the regions as read (`PageWork.reuse`), finds and reads
  nothing on the frame on show, letters the lines stored at once and asks for the rest only; the misreadings
  corrected since that read are applied, as to a page read on show. A read of the backlog's stopped by a turn to that
  very page leaves its detection and the units read by then: the page job takes them and reads the rest from the frame
  on show. Such a page goes the way of a page the cache does not hold whole (`ui.live._early_start`, with its gate): on
  a viewer seen to draw a page soft first a frame that looks soft is not started, the sharp one is; a frame that
  changes drops the job and puts back what it did; what it stores lasts once the frame is confirmed; a request in
  flight at a turn is cancelled as before. A page the cache holds whole goes as ever (`_take_at_once`: no gate, not on
  a frame that looks soft). The copies take 0.41 ms for a page of six regions, the signature 0.02 ms.
- *A drop told at once.* `Backlog.drop` tells the window `backlog` with *dropped* True (pages and lines 0) before
  anything else, when anything was there; the screens are then numbered from 1 again.
- *Story order taken out.* Every request, the backlog's as the page on show's, gets the pairs in the order the
  requests were made (the pipeline's one `GrowingContext`): `StoryContext`, `backlog.HISTORY`, `SWITCH_HOLD_S`,
  `SWITCH_PAIRS` and `tools/openmantra_eval.py --history` are gone (the section before: no better translation, more of
  the server's time). `--behind 4` stays: its order, the page read after four flipped past and then those four
  smallest first, is the order the backlog works them in now when none of them lies ahead of the reader.
- *A page judged by its own sharp picture as well.* A frame of a page the window has seen sharp and drawn soft first
  is soft when it is less crisp than `PAGE_SHARP_SHARE` (0.85) of that page's sharp picture (`batch.SharpSeen`, by the
  fingerprint of the first page unit and the picture's size, the newest 256 in memory, cleared with another viewer
  window), besides the frames the viewer's soft and sharp pictures of all pages find soft, as before. The first wide
  soft-first run of this round showed why: the soft picture of a page with much fine detail passed for sharp by the
  viewer's pictures, and what the cache held of it was lettered on that soft picture for 531 ms on the way back. The
  page's own picture first took the place of the viewer's pictures where it was kept; it now only adds soft frames
  (`52dffe2`), so no frame is taken for sharp that round 1's rule took for soft. That change was made for a page of
  scenario t lettered on its soft picture in `--scenario all` (188 ms), read then as the page's own picture passing
  it; the run after the change showed the same in another turn with every judgement of the window right (below):
  both came the settle path's way, not by the page's own picture.

What still tells "skipped" in normal reading: a page the backlog read with no line on it to translate and nothing of
it in the cache (`Backlog._read`), and a page job done with no line translated (`Tracking.finished`): a page with no
text. A page job stopped without a turn (Stop, the close) leaves its stages "waiting".

**How it was measured.** As in the section before: the same machine, a server of the tool's own on 127.0.0.1:11435,
the stand-in viewer with the OpenMantra pages, `--seed 1`, every OCR read on the processor beside the loaded model
("auto" placed the readers there in every run). Scenario k in the four configurations, each with the backlog and with
nothing caught (`--k-backlog off`, the same turns), with the indicator beside the page (in the wide window the spread
leaves it the room of the rail only); the 1 s pace alone (`--scenario k1`) twice more for each of the eight; the wide
soft-first and the narrow sharp configurations once more with the indicator off, the narrow sharp one with the rail;
scenario w (the whole-book run) in both windows; the benchmark arms; the computer without a GPU; `--scenario all` at
the end. The runs are on the code before `52dffe2` (the page's own sharp picture only adding soft frames, below) but
for the narrow sharp run with the backlog, the soft narrow 0.5 s pace again each way, the quiet wide whole-book run,
the soft-first runs again with the backlog (below), the second narrow whole-book run and the last `--scenario all`;
for a viewer that draws sharp at once the change makes no difference, and in the runs after it the tool's count of
the window's judgements found none it changed. Two other agents worked on
this computer in the same hours, running short test files of their own (no model, no Ollama): their tests overlapped
the narrow sharp run with nothing caught and the one with the indicator off, the second and third 1 s runs of the
sharp wide configuration and its second with nothing caught, the second soft wide 1 s run with nothing caught, the
third soft narrow one with nothing caught, the second narrow sharp 1 s runs, both whole-book runs of the first pair,
the official page-mode benchmark, both `--scenario all`, the soft-first runs again and the second narrow whole-book
run.

**What is caught.** As in the section before ("stayed": the stand-in's own log of how long each flipped page's sharp
frame was on show), one run each with the backlog:

| configuration | pace | stayed 0.8 s or more | caught | finished while on show | caught or finished = stayed |
|---|---|---|---|---|---|
| soft first, wide | 0.5 s | 0 | 0 | 0 | 20 of 20 |
| | 1 s | 3 | 2 | 0 | 19 of 20 |
| | 2 s | 20 | 20 | 0 | 20 of 20 |
| sharp at once, wide | 0.5 s | 0 | 0 | 0 | 20 of 20 |
| | 1 s | 20 | 20 | 0 | 20 of 20 |
| | 2 s | 20 | 20 | 0 | 20 of 20 |
| soft first, narrow | 0.5 s | 0 | 0 | 0 | 20 of 20 |
| | 1 s | 5 | 1 | 1 | 17 of 20 |
| | 2 s | 20 | 18 | 2 | 20 of 20 |
| sharp at once, narrow | 0.5 s | 0 | 0 | 0 | 20 of 20 |
| | 1 s | 20 | 16 | 3 | 19 of 20 |
| | 2 s | 20 | 16 | 4 | 20 of 20 |

The 1 s pace over its three runs: 11 stayed, 3 caught, 52 of 60 agree (soft wide); 60, 60, 60 of 60 (sharp wide);
10, 2 and 1 finished, 53 of 60 (soft narrow); 60, 54 and 5 finished, 59 of 60 (sharp narrow). Every page that
disagrees is of the two kinds the section before named: with soft first, pages on show 801 to 858 ms by the
stand-in's log and 684 to 730 ms from the window's look; in the narrow sharp runs the one page low in detail whose
sharp frame the window takes for soft (the tool's count: its three looks at it in the last run, the only frames it
misjudged there).

**How each page read back began.** Ten pages read back per pace (thirty at 1 s, over its three runs); "caught": those
of them the backlog held when the reader came back.

| configuration | pace | wholly from the cache | read reused | read in part reused | read again: still a frame | read again: not caught / soft gate | caught, begun with no new read |
|---|---|---|---|---|---|---|---|
| soft first, wide | 0.5 s | 0 | 0 | 0 | 0 | 7 / 3 | none caught |
| | 1 s | 0 | 0 | 1 | 0 | 25 / 4 | 0 of 1 |
| | 2 s | 9 | 0 | 0 | 1 | 0 | 9 of 10 |
| sharp at once, wide | 0.5 s | 0 | 0 | 0 | 0 | 10 / 0 | none caught |
| | 1 s | 2 | 5 | 8 | 15 | 0 | 7 of 30 |
| | 2 s | 7 | 1 | 1 | 1 | 0 | 8 of 10 |
| soft first, narrow | 0.5 s | 0 | 0 | 0 | 0 | 8 / 2 | none caught |
| | 1 s | 0 | 0 | 0 | 0 | 22 / 8 | none caught |
| | 2 s | 9 | 1 | 0 | 0 | 0 | 10 of 10 |
| sharp at once, narrow | 0.5 s | 0 | 0 | 0 | 0 | 10 / 0 | none caught |
| | 1 s | 27 | 0 | 0 | 1 | 2 / 0 | 26 of 27 |
| | 2 s | 9 | 1 | 0 | 0 | 0 | 10 of 10 |

No page was read again for another size. The first bubble (from the stand-in's sharp frame), median per run and pace:
wholly from the cache 485 to 951 ms, read reused 132 to 696 ms, read in part reused 924 to 2,179 ms, read again 1.0
to 3.0 s. In the wide window at 1 s a page the reader read back took most of its 8 s on show (12 to 17 requests a
page), so the worker was idle for the backlog for some 0.3 s a page: its read of the next page was stopped by the
turn, in its detection 15 times of 30 (nothing to lend: "still a frame") and after it 8 times (detection and the units
read by then lent: "in part"). A stopped read starts again from the start at the backlog's next step: the stopped steps
took 2.1 to 20.8 s of the worker per run (reads 0.3 to 16.7 s), most of it in the wide sharp and soft runs. (Since
then the backlog's next step on that page takes up what the stopped read had, its detection and the units read by
then, under the conditions of the lending - `Backlog._resume_of`, tested in tests/test_backlog.py; the tool counts
these reads, `reads_after_a_stop`. Not measured on the stand-in yet.)

**The first bubble of a page read back**, with the backlog and with nothing caught, median / p90 in ms, one run each
(the 1 s pace also over its three runs, thirty pages each way):

| configuration | pace | with the backlog | nothing caught | difference of the medians |
|---|---|---|---|---|
| soft first, wide | 0.5 s | 2,373 / 3,144 | 2,873 / 4,192 | -500 |
| | 1 s | 2,571 / 2,962 | 2,492 / 3,874 | +79 |
| | 1 s, three runs | 2,270 / 3,183 | 2,154 / 3,809 | +116 |
| | 2 s | 726 / 898 | 828 / 2,147 | -102 |
| sharp at once, wide | 0.5 s | 2,543 / 3,410 | 2,601 / 3,877 | -58 |
| | 1 s | 2,220 / 3,475 | 2,054 / 3,764 | +166 |
| | 1 s, three runs | 1,934 / 3,672 | 1,985 / 3,367 | -51 |
| | 2 s | 968 / 1,170 | 924 / 2,355 | +44 |
| soft first, narrow | 0.5 s | 2,328 / 3,068 | 2,009 / 3,099 | +319 |
| | 0.5 s, again | 2,456 / 3,658 | 2,146 / 3,599 | +310 |
| | 1 s | 1,413 / 1,935 | 1,844 / 2,092 | -431 |
| | 1 s, three runs | 1,798 / 2,541 | 1,914 / 2,701 | -116 |
| | 2 s | 552 / 782 | 921 / 2,030 | -369 |
| sharp at once, narrow | 0.5 s | 2,047 / 2,953 | 2,210 / 3,017 | -163 |
| | 1 s | 518 / 601 | 1,244 / 1,989 | -726 |
| | 1 s, three runs | 541 / 640 | 1,598 / 2,578 | -1,057 |
| | 2 s | 604 / 728 | 754 / 2,080 | -150 |

All paces of the four runs with the backlog against the four with nothing caught: wide 1,966 / 3,144 against 2,098 /
3,874 (60 pages each), narrow 750 / 2,356 against 1,502 / 2,855 (58). The soft narrow 0.5 s pace is higher with the
backlog in both its runs: nothing is caught at that pace there, in either run (no catch, no step: the code run is that
of the runs with nothing caught), and page by page the eighteen pages differ by +70 ms (median of the pairs); the median
of nine pages moves by some 300 ms between neighbouring values. The sharp wide run at 1 s (+166) is -51 over its
three runs.

**What a turn waits for.** A step under way stops at the next job; the worker was free 29 to 144 ms after the stop
(median per run and pace) and 334 ms at most (126 stops over all the runs with the backlog), a turn to the very page
the backlog was reading 60 to 154 ms (median) and 304 ms at most (28 such turns, all in the wide window). The page's
next request then waited at the server 4 to 941 ms at most per run (941 ms in a run another agent's tests overlapped;
304 ms at most in the runs they did not).

**Memory.** At most 24.8 MB of frames held (sharp wide; the cap is 256 MB), 1.6 MB of regions kept, no frame held
after its read, 0 bytes at the end of every run; the longest a frame waited for its read, from its catch: 120.9 s
(wide, the reader reading ten pages at 8 s first), 73.9 s in the narrow window.

**How long the backlog takes, a screen.** The whole-book run of scenario w on the same code: 37.6 s for its 5 screens
in the wide window (7.5 s a screen; 42.3 s in the run another agent's test overlapped), 18.9 and 19.2 s in the narrow
one (3.8 s a screen; both runs overlapped).
The backlog's own steps, per screen it held at most:

| configuration | pace | screens held at most | until empty | its own steps | a screen |
|---|---|---|---|---|---|
| soft first, wide | 1 s, three runs | 6 / 2 / 1 | 90.3 / 0 / 7.8 s | 22.5 / 4.0 / 7.9 s | 3.8 / 2.0 / 7.9 s |
| | 2 s | 20 | 111.1 s | 94.8 s | 4.7 s |
| sharp at once, wide | 1 s, three runs | 20 / 20 / 20 | 131.7 / 123.6 / 128.1 s | 70.9 / 64.6 / 62.5 s | 3.5 / 3.2 / 3.1 s |
| | 2 s | 20 | 109.5 s | 86.5 s | 4.3 s |
| soft first, narrow | 1 s, three runs | 1 / 0 / 2 | 8.1 / - / 14.7 s | 5.6 / 0 / 9.1 s | 5.6 / - / 4.6 s |
| | 2 s | 18 | 47.8 s | 35.7 s | 2.0 s |
| sharp at once, narrow | 1 s, three runs | 16 / 19 / 19 | 42.3 / 77.1 / 62.4 s | 33.4 / 66.0 / 51.9 s | 2.1 / 3.5 / 2.7 s |
| | 2 s | 16 | 40.3 s | 32.0 s | 2.0 s |

A screen took the backlog less than it takes the whole-book run in every wide run and in the narrow window with 16 or
more screens; with one or two screens caught in the narrow soft runs at 1 s it took more (5.6 and 4.6 s a screen):
their reads were started in the moments the worker was idle during the flips and stopped by the next page 7 and 6
times (1.7 and 1.5 s of the worker), each started again from the start. The rerun below with three screens caught
took 3.7 s a screen.

**The soft-first runs again, on the final code** (both overlapped by another agent's tests). Wide: caught 0, 3 and
20 of 0, 4 and 20 that stayed (0.5 / 1 / 2 s), 20, 17 and 20 of 20 agree; of the pages read back 9 of the 10 caught
at 2 s began with no new read (1 caught at 1 s, in part reused); the first bubble 2,586 / 3,219, 2,233 / 3,084 and
804 / 916 ms against 2,873 / 4,192, 2,492 / 3,874 and 828 / 2,147 with nothing caught (-287, -259, -24); the worker
free 22 to 60 ms after a stop (median), 327 ms at most; 3.8 and 4.6 s of the backlog's steps a screen (7 and 20
held). Narrow: caught 0, 3 (and 1 finished) and 18 (and 2) of 0, 4 and 20 that stayed, 20, 18 and 20 of 20 agree;
the two caught pages read back at 1 s and all ten at 2 s began with no new read; the first bubble 2,295 / 3,333,
872 / 2,116 and 576 / 692 ms against 2,009 / 3,099, 1,844 / 2,092 and 921 / 2,030 (+286, -972, -345); the worker free
56 and 101 ms after a stop (median), 189 ms at most; 3.7 and 2.2 s a screen (3 and 18 held). The window's
judgements of frames: 149 and 189, none missed; nothing lettered on a soft frame, nothing kept from one, nothing
stale, no error. The soft narrow 0.5 s pace came out higher with the backlog a third time (+286); over its five
runs, the median of each page's runs with the backlog against that of its runs with nothing caught differs by +31
ms (the nine pages: -315 to +267): the median of nine pages falls on pages 4, 5 and 8, which came 30 to 270 ms
later with the backlog, at a pace where nothing is caught and no step runs. In the narrow run at 1 s the tool tied
one screen to the page before (a screen is tied to a flip by the moment it is told on show, which may come just
after the next turn): it counted page 26 (596 ms on show) caught and read back "caught, nothing held"; it was page 27
(787 ms on show by the stand-in's log), read back wholly from the cache, that was caught. The figures above are
corrected for it.

**The two sides together.** The indicator beside the page drawn from normal reading's events, looked at from the
window as they came (68 to 272 looks a run): in every run every screen told had its cell or rail mark in the state
last told, the screen on show was outlined at every look, every screen that went by was drawn as missed (20 to 60 a
run), and after the drop that ends scenario k no screen was left and none drawn. In the wide window the spread leaves
the column no room: the indicator draws its rail there (the column was looked at in the narrow runs). The event pump
(`_poll_events`) and the first bubble:

| run | indicator | `_poll_events` median / p99 / longest (ms) | first bubble, median at 0.5 / 1 / 2 s (ms) |
|---|---|---|---|
| soft first, wide | column (drawn as the rail) | 0.10 / 45.0 / 145.8 | 2,373 / 2,571 / 726 |
| | off | 0.15 / 49.6 / 140.4 | 2,282 / 2,246 / 799 |
| sharp at once, narrow | column | 0.09 / 10.7 / 125.0 | 2,047 / 518 / 604 |
| | rail | 0.10 / 13.2 / 49.8 | 1,923 / 502 / 634 |
| | off | 0.11 / 13.1 / 75.7 | 2,235 / 514 / 568 |

The indicator off has both the shortest and the longest of the slowest pumps; the first bubbles move as one run moves.

**Benchmark.** OpenMantra, seed 1, on the final history (the story arm on the code before its removal):

| arm | chrF | flagged | translated | requests computed again (their prompt time) | prompt time in all | translation time |
|---|---|---|---|---|---|---|
| page mode, in order (official) | 41.22 | 2.6 % | 1586 of 1586 | 43 (52.6 s) | 160.8 s | 296.5 s |
| book mode (official) | 40.99 | 2.6 % | 1586 of 1586 | 48 (57.4 s) | 163.5 s | 301.2 s |
| behind 4 | 40.90 | 3.0 % | 1586 of 1586 | 49 (73.9 s) | 181.4 s | 323.2 s |
| behind 4, story order | 40.82 | 2.6 % | 1586 of 1586 | 48 (77.0 s) | 191.4 s | 325.0 s |

F1 97.2 and CER 1.9 % in every arm. `--behind 4` still models the app: with nothing ahead of the reader the backlog
takes the pages behind smallest first, the order `behind_order` gives them.

**A computer without a GPU.** `CUDA_VISIBLE_DEVICES=-1 --ocr-runs-on cpu --ollama-num-gpu 0` (the System page:
detect, OCR, translation and erase on the CPU), scenario k2 with 6 pages flipped past at 2 s and 3 read back at 30 s
a page: 6 of 6 caught; two of the three pages read back took the backlog's read (first bubble 720 and 861 ms), the
third was still a frame (3.06 s); the backlog empty 155.1 s after the jump back (its own steps 92.7 s, 15.5 s a
screen); two steps stopped by a turn, the worker free 250 and 351 ms after, the page's next request waiting 309 and
610 ms at the server; a request took 0.90 s (median), 1.75 s (p90) and 9.9 s at most for a page, 1.04 / 2.0 / 9.5 s
for the backlog; nothing stale, no error.

**Every scenario at the end.** `--scenario all` on the final code (333 s; another agent's tests overlapped it): 0
wasted requests, 0 stale lettering, 0 soft frames confirmed or left in the cache, nothing kept from a frame not
settled, no error; 84 requests behind the reader; the whole-book run finished its 5 pages; old lettering after a
turn at most 374 ms (2 of 28 turns with no job over 250 ms; 1 of 12 with a job running). One page the cache held was
lettered on its soft picture, for 172 ms (scenario e, the turning back), as one was in the run before the change
above (188 ms, scenario t). The tool's count of the window's judgements (`soft_looks`: 86, of which 0 missed) shows
how: the frame was judged soft and not taken at once; the stand-in kept that soft picture on show 373 ms (389 ms in
the run before), and the window, whose capture still had it 400 ms after it first saw it, took it as settled
(settle_ms 400), as the settle path takes any frame that stays, so that a page low in detail whose sharp frame
looks soft is read at all; the sharp frame was read 1.1 s after the turn and lettered over it. Five turns of the run
to a page the cache held drew it soft for 370 to 401 ms; this one was taken so; the round-1 run at the end had none
taken. A soft picture
that stays as long as settle_ms is taken as before round 2; waiting longer on a frame that looks soft would cost
the page low in detail as long.

**What every run kept to.** In every run and at every pace: results kept from a frame not confirmed or soft 0, stale
lettering 0, frames held after their read 0, bytes held at the end 0, thumbnails at most 96 px high and with a
screen's first event only, no error logged. Requests sent for nothing: none of the backlog's; with soft first at 1 s
two to five of the page on show's own early requests (`dropped`: its frame changed within 0.8 s of the look, the
reader turned on), with the backlog as with nothing caught (2 and 3 there). A page job whose frame changed before its
confirmation, its lines answered by then, was discarded once (nothing kept, nothing lettered meanwhile).

**A run that stopped translating.** Twice in the soft-first runs of this round (once wide, once narrow) translation
stopped partway: requests were begun and none answered, those at a turn were cancelled, the server unloaded the model
after its five minutes, and the run never ended (stopped by the plan's time limit). It came back in none of the 40 runs
after; its cause is not known. The tool now writes every thread's stack when a request stays under way 20 s without
going out or 60 s at all (`stacks.txt`) and keeps the server's own log (`ollama_server.log`, no prompt or answer in
it); neither wrote anything in the runs since.

*Tests.* `tests/test_backlog.py`: the order nearest the reader (ahead first, then the smallest; read before
translate, the choice made again at each step), what a page job takes of the backlog's read and when not (other units,
size or read signature; a read stopped half-way), the drop told first and the numbering from 1 again, a page job
stopped without a turn left waiting. `tests/test_follow.py`: a page judged by its own sharp picture, which only adds
soft frames.

## Pages left at work, a page done read again, and the stop that did not come back (2026-11-21)

Three things another agent's recordings showed on a computer without a GPU (a stand-in viewer of its own, single
pages, the page turned by TASlation's page key handed on), each found again with `tools/standin_e2e.py`, then the
hunt for the stop of the section before.

**What changed.**

- *A page turned by TASlation's page key while a job ran.* The turn was taken as a page that settled
  (`ui.live._await_change`): queued, and started with no gate once the job before was cancelled. A page with no gate
  is never caught when turned past, and its job's cancel told the window nothing, so the stages it had told "working"
  stayed so for good. The turn now goes as one the viewer made while the job ran (`_look_over_job`: the job cancelled
  once the frame has stayed LEFT_PAGE_MS, the page started early once the worker is free, a gate of its own).
- *Never left at work.* A page job that ends with its page neither done nor caught tells each stage it told
  "working" what came of it (`backlog.Tracking._left`): "waiting" when it was stopped or its confirmation taken back,
  "failed" when it failed; a page with no gate turned past is told missed, and one the backlog still has an entry of
  is told waiting.
- *A page done keeps its read.* A page the backlog finished, or one finished on show (`Tracking._keep_read`), keeps
  its regions as read with the capture's units, size and read signature (`Backlog.keep_done`, DONE_CAP_MB 64, the
  oldest out first, dropped with the backlog); shown again, the page job takes them (`Backlog.lend`), finds and reads
  nothing and letters from the cache. Before, that read was let go with the page done, and the page job read the page
  again (3.4 s on the processor in the recording) while its bar went back to "reading" over a page shown translated.
  A stage told done or skipped is never told at work again while the page is on show (`Tracking._progress`), and a
  page with nothing to read is told read at once (`Pipeline.process`).
- *The tool.* `--k-keys` releases each turn of scenario k by the window's next page key once the window hands it on
  (the stand-in's new `u` step waits for the control file's "turns"; the window's raise of the viewer before a key
  is left out, the stand-in drawing while covered); `--k-stay-ms` keeps the last page flipped to that long (a page
  read afresh on show while the pages turned past wait); k3, 3 s a page; per run the screens left told at work at
  the end and the stages told at work again after done (`told`); per pace the backlog's first step after a page job
  that showed its page (`first_steps`).

**How it was measured.** `CUDA_VISIBLE_DEVICES=-1 --ocr-runs-on cpu --ollama-num-gpu 0`, the tool's server on
11435, scenario k at 1 s and 3 s a page (k1, k3), 5 pages flipped past and 5 read back at 8 s, sharp at once, single
pages, the stand-in drawing while covered (`--standin-draws-covered`), seed 1; once with the stand-in's own turns and
once by the page key with the last page flipped to kept 8 s (`--k-keys --k-stay-ms 8000`), each on c101f13 (with the
new tool) and on the final code. No other run overlapped them.

| turns | code | screens left at work | stages at work again after done | page jobs with no gate | caught at 1 s / 3 s | read back: reused / read again / from the cache |
|---|---|---|---|---|---|---|
| the stand-in's own | before | 0 | 1 | 1 of 24 | 4 / 5 of 5 | 8 / 2 / 0 |
| | final | 0 | 0 | 1 of 24 | 4 / 5 | 9 / 1 / 0 |
| the page key | before | 2 | 6 | 12 of 24 | 1 / 0 | 0 / 6 / 4 |
| | final | 0 | 0 | 1 of 24 | 2 / 5 | 8 / 2 / 0 |

The one job with no gate in each run is a page the window took at once (the first page; a page the cache held
whole), as it should. With the stand-in's own turns the tool's scenario k never took the key's way, which is why
the first runs of this round saw none of it. By the key at 1 s, 2 of the 5 pages flipped past were not caught in
the final run (1 finished on show): their jobs ran 0.64 and 0.74 s before the turn, short of the 0.8 s a
confirmation takes (the stand-in's log: 972 and 1,010 ms on show; the stand-in turns once it has looked at its
control file, every 100 ms, after the key reached it 34 to 46 ms after it was pressed). The first bubble of a page read back, median at 1 s / 3 s:
286 / 492 ms before and 292 / 474 ms after with the stand-in's turns; 1,096 / 784 ms before and 350 / 473 ms after by
the key.

**The backlog's first step after the page on show.** In the four runs it came within 40 ms of the page job's end,
but where the job ended less than 2 s after its confirmation: there it came 0 to 60 ms after the confirmation and 2 s
(6 such jobs of 22). That is the take-back hold: the stand-in drew its first page soft, the window has seen it draw
soft first, and the stores of a page job done within TAKE_BACK_MS of its confirmation stay open that long for a
sharper picture of the page (`Pipeline.decide_kept`); the worker decides it before any other job, so a step of the
backlog then would close it at once. A job's own time after showing its page was at most 0.62 s (its wait for its
confirmation at most 0.52 s, the lettering ahead for the page's next showing, `keep_shown`, at most 92 ms). In the
two-turn recording the step came 1.2 s after the page on show was told done, some 10 s after its confirmation: not
the hold; it did not come here, nor the 7 s of the four-turn recordings (those are not kept). A change that left
out the lettering ahead while pages turned past waited was taken out again, as `keep_shown` costs that little here.

*Tests.* `tests/test_early_start.py`: a page turned by a key handed on while a job runs starts with a gate of its
own (failed before: no gate). `tests/test_backlog.py`: a job stopped, cancelled with its confirmation taken back,
turned past with no gate, or failed leaves no stage at work; a page the backlog finished, shown again, is read
nowhere and told done throughout (failed before: read again, told "reading"). `tests/test_standin_viewer.py`: the
steps and times of `--k-keys` and `--k-stay-ms`.

**The stop hunted.** Scenario k as in the section before (0.5, 1 and 2 s, 20 pages flipped past, 10 read back at 8
s, soft first), seeds 1 to 10, the tool's server on 11435, on a frozen copy of c101f13, the stand-in drawing while
covered from the third pair on; with the backlog and with nothing caught (`--k-backlog off`), wide and narrow. The OCR
read on the processor in 32 of the 33 runs ("auto" found no room beside the model on this 6 GB card).

| backlog | window | runs | translation stopped | read back lettered | left incomplete in the cache | bytes held at the end |
|---|---|---|---|---|---|---|
| on | wide | 10 | 0 | 300 of 300 | 0 | 0 |
| on | narrow | 10 | 0 | 289 of 300 | 0 | 0 |
| off | wide | 5 | 1 | 141 of 150 | 35 | 0 |
| off | narrow | 3 | 0 | 87 of 90 | 4 | 0 |

Two runs with the backlog on (narrow) are counted apart: the owner's windows lay over the stand-in, which stopped
drawing, and the window's capture kept its last frame (19 of 30 read back lettered each; no request went unanswered):
a browser wholly covered by windows that hide what lies under them stops drawing, and nothing in the window notices
it on the capture's way. Two runs covered the stand-in on purpose with a window of the tool's own for 60 s: its
frames stood still 9.5 s; with the stand-in drawing while covered, not at all. One narrow run another agent's
recording slowed (26 of 30 lettered) was run again; two wide runs it overlapped are counted (slower, nothing else).
The page not lettered at 0.5 s in every narrow run is the same page each time, with nothing caught as with the
backlog. Of the runs with nothing caught, two the other agent's recording overlapped were run again; the stop came
in a rerun no other run overlapped.

**What the stop is.** In that run (wide, nothing caught, at 2 s, the pages read back) the server sent nothing to any
request for 2 min 28 s. Its log shows where: the last request answered (HTTP 200) had its task in the model's runner
cancelled after the answer (as 2 to 13 requests in every run of the hunt had, with nothing after); from the next
request on, Ollama took each request (`/api/generate`
logged, and "aborting completion request due to client closing the connection" when TASlation gave up) but none
reached the runner - no line of the runner for any of the 12 requests, the runner telling all its slots idle -,
while `/api/ps` answered in 1 to 2 ms with the model loaded on the GPU. TASlation's no-answer rule (a request with no
byte for 30 s asked again on a new connection, then the server started again) came only once a request had waited
30 s: the reader turned every 8 s, and each of the first 10 requests was cancelled by the turn after 6 to 7 s with
nothing. The rule then asked again (30 s more, nothing) and started the server again (3.7 s): the next request was
answered and the run went on to its end. So the stop is the server's (Ollama 0.40.16, between its own server and its
runner), not the backlog's, and not TASlation's request: the requests reached the server, on new connections too.
The round's other 32 runs had no such stretch (requests that never reached the runner: only the first and last of a
run and ones cancelled within a second at the 0.5 s pace).

Not done, a proposal: the 30 s counted over the requests in a row that got nothing (a request cancelled with no byte
leaving its silence to the next one, the time with no request under way not counted), so that a reader who turns on
does not hide a server that has stopped; here it would have come some 70 s sooner. The two stops of the section
before had the same look (requests begun, none answered, cancelled at the turns); their server logs were not kept.

Done on 2026-11-21 (`ollama._Waits`): the wait for a first byte is counted over the requests in a row that got none,
the time with none under way left out, and any byte of any request to the model, or any answer, starts it again. On
the stand-in server of `tests/test_no_answer.py`, which takes every request and sends nothing, at the module's own
bounds: a reader turning every 7 s, 2 s between pages, was told `ollama.no_answer` at 30.0 s waited in all, on the
fifth page (the request then asked again on a new connection); turning every 6 s, the fifth request reached 30 s as
its turn cancelled it and the sixth was ended at once, told 30.1 s. Before the change no request at either pace
reached its own 30 s, so the rule could not come (the test of it, scaled to 0.6 s and turns of 0.12 s, fails there in
15 pages). A look at `/api/ps` is no request to the model and changes nothing of the count.

## The viewer kept under TASlation's window, and the pages turned past on 0.9 (2026-11-22)

The work of the sections before, on 0.9.3: pages turned past go on being read (`taslation/backlog.py`) and the
indicator beside the page, now with the window order, a read of the backlog's allowed in the hold of a page job, and
a fix to the end of TASlation while its server is being started.

**What changed.**

- *The viewer kept under TASlation's window* (`ui/order.py`, `capture.keep_viewer_under`): while a window of
  TASlation's is the one in front, a window of another program that lies between it and the viewer is put under the
  viewer by moving the viewer up (SetWindowPos with SWP_NOACTIVATE: no activation, no change of the foreground, no
  key, no click), at once when TASlation came to the front, then every 0.5 s, at most 5 times in such a spell. A
  browser hidden wholly by windows that hide what lies under them stops drawing, and no page turned is seen then.
  Under a topmost TASlation the viewer goes to HWND_TOP, the top of the windows that are not topmost (after a topmost
  window it would become topmost itself).
- *One switch for which windows send the viewer up* (`order.PARTLY_COVERED_TOO`, no setting): True, as built, any
  window that hides some of the viewer - a note or a dictionary the person laid over a part of it goes under it at
  each click on TASlation; False, only once other programs' windows that hide what lies under them hide all of it,
  and one over a part of it stays where the person put it. The log names the windows that went under by class only
  (and says when one was another window of the viewer's own program), never a title.
- *The viewer's location change announced* once it is put up (`NotifyWinEvent` EVENT_OBJECT_LOCATIONCHANGE for its
  window: an event to the programs listening for window events, nothing sent to the viewer). Chromium's occlusion
  tracking looks again at window events, not at a change of the order alone: on the stand-in, wholly covered and so
  drawing nothing, then put over the window that covered it with no such event, it once drew nothing for 13.7 s more.
- *A read of the backlog's in the hold of a page job* (`Pipeline.behind_reads_allowed`): in the 2 s in which the
  window may still take a page job's confirmation back on a viewer that draws a page soft first, the backlog may read
  a page turned past from its capture (or make its regions units), which asks the translator nothing and changes
  nothing that job stored; a translation still waits for the decision, and the read holds the decision off while it
  runs and stops as the time is up (`steps_in_hold` in the tool's report).
- *TASlation's end while its Ollama is being started* (`ollama_start`): the end counts (`_ends`), and a start under
  way across one launches nothing after it and gives up at once what it launched or adopted meanwhile. Seen on the
  stand-in: a run stopped 1.5 s into its window left the server it had started on its port running. The two tests in
  `tests/test_ollama_start.py` fail on the code before (checked).
- *The tool.* `--cover` lays a plain window of the tool's own over the stand-in (`--cover-style noactivate` the old
  one), `--cover-part F` over the left F of its width only, `--order-partly on/off` sets the switch for the run,
  `--front-for-order own` lets the window keep the stand-in under it as with TASlation in front, and
  `--cover-front-s S` puts TASlation's window at the top of the order (no activation) S seconds after the cover came;
  each look while the cover is up notes what the order said, whether the cover lies over the stand-in, whether the
  stand-in is topmost, and whether the window was busy with the viewer.

**How it was measured.** The same machine (GTX 1660 Ti, 6 GB), a server of the tool's own on 127.0.0.1:11435
(the owner's on 11434 untouched), the stand-in viewer with the OpenMantra pages, `--seed 1`, on `046959e` (the code of
`601f7e0` and the tool's last notes). The covered runs started only after 30 s with no input to the computer, for at
most 2 min, and the person was at the computer during most of them (idle 0 to 60 s at their starts); the timing runs
(the stand-in drawing while covered, `--standin-draws-covered`) did not wait. Another agent's short tests (no model)
overlapped the first covered run and one other; no timing run was overlapped.

**The covered runs.** The tool's cover over the stand-in for 20 to 40 s, TASlation's window counted as in front
(`--front-for-order own`) and, in the runs marked *own to top*, put at the top of the order 10 to 25 s after the
cover came (until then the cover's program counts as in front, as when the person has just clicked another program):

| run | turns | cover | switch | TASlation in front from | viewer put up | windows that went under it | frames stood still |
|---|---|---|---|---|---|---|---|
| a, own to top | the stand-in's own | whole, plain | on | 33.14 s | 33.22 s | the cover | none |
| r (TASlation's full screen, topmost), own to top | the stand-in's own | whole, plain | on | 30.83 s | 30.83 s, then 4 more | the cover; another program's Chrome_WidgetWin_1 (5 times, came back each time) | none |
| k1 by the key, own to top | the window's page key handed on | whole, plain | on | 30.58 s | 30.69 s | the cover | none (22 turns while covered, all shown) |
| a, own to top | the stand-in's own | whole, noactivate | on | 46.74 s | 46.75 s | the cover | 20.0 s from 26.85 s (2 turns not shown); frames back 0.9 s before the viewer was put up |
| a, part | the stand-in's own | left 40 %, plain | on | 30.82 s | 30.82 s | the cover | none |
| a, part | the stand-in's own | left 40 %, plain | off | 30.65 s | never (said "partly" at all 386 looks) | none: the cover stayed over the viewer | none |
| a, whole | the stand-in's own | whole, plain | off | 31.50 s | 31.51 s | the cover | none |

In the topmost-TASlation run the stand-in was never topmost (0 of 420 looks), nor in any other run: HWND_TOP with
SWP_NOACTIVATE lifts the viewer under a topmost TASlation, and it stays a window that is not topmost. The other
program's window that came back between them (in the spell at the start as well, 5 placements in 2.2 s and the cap)
was not topmost by a read-only look at the order afterwards; most likely the person's own window in front at the
time, which the tool's `--front-for-order own` keeps out of the count of the window in front - with TASlation really
in front it would not be. Earlier runs of the round (before the announcement) agreed: placed 50 ms after the cover
came under a topmost TASlation, the cover under the viewer in all 342 looks; with TASlation really the window in
front (no `--front-for-order`), placed 450 ms after the cover came.

*The announcement, not settled.* The stand-in drew on under the tool's plain cover in most runs (every turn while
covered shown), so they show nothing of it. It stopped drawing in three runs: with the announcement twice (frames back
0.9 s and 0.8 s *before* the viewer was put up: something else made the browser look again, with the person at the
computer), without it once (`no_announce.py`, a scratch wrapper that leaves the call out: frames back 1.5 to 1.9 s
after the viewer was put up, a fresh capture 1.3 s after it still showing the old page). The 13.7 s seen before the
change did not come again. All three stalls came while the person was at the computer; a third pair, each way, on a
computer with no input for 52 minutes stalled in neither run (every turn while covered shown). The call is an event of the viewer's own window and changes nothing else; whether it is
what brings the frames back is not shown by these runs.

*The status line, a false alarm.* In every covered run with a plain cover the window said "The viewer is hidden behind
other windows and has stopped drawing" 1 to 4 times while the stand-in drew on: the line counts frames that stand
still for 3 s while the viewer is hidden wholly, and a page that does not change gives no frame at all; each frame
that came took the line back and started a new spell. Changed after the round (*After the review*, below): the line is
said only when a page key the window handed on to the viewer brought no frame for 3 s while it was hidden wholly
(then it has surely stopped), and otherwise not; the wording of the key stays.

**Scenario k on 0.9.** As in the sections before (20 pages flipped past at 0.5, 1 and 2 s, 10 read back at 8 s, one
run each with the backlog and with nothing caught, `--k-backlog off`), the stand-in drawing while covered. Two runs
were overlapped by another agent's short test files (no model): the sharp wide one with the backlog and both sharp
narrow ones.

| configuration | pace | stayed 0.8 s or more | caught | finished while on show | agree | caught and read back, begun with no new read |
|---|---|---|---|---|---|---|
| soft first, wide | 0.5 s | 0 | 0 | 0 | 20 of 20 | none caught |
| | 1 s | 4 | 1 | 0 | 15 of 20 | none of them read back |
| | 2 s | 20 | 20 | 0 | 20 of 20 | 9 of 10 (1 its read in part reused) |
| sharp at once, wide | 0.5 s | 0 | 0 | 0 | 20 of 20 | none caught |
| | 1 s | 20 | 20 | 0 | 20 of 20 | 3 of 10 (7 still a frame) |
| | 2 s | 20 | 20 | 0 | 20 of 20 | 9 of 10 (1 still a frame) |
| soft first, narrow | 0.5 s | 0 | 0 | 0 | 20 of 20 | none caught |
| | 1 s | 3 | 0 | 0 | 17 of 20 | none caught |
| | 2 s | 20 | 17 | 3 | 20 of 20 | 10 of 10 |
| sharp at once, narrow | 0.5 s | 0 | 0 | 0 | 20 of 20 | none caught |
| | 1 s | 20 | 16 | 3 | 19 of 20 | 8 of 9 (1 in part reused) |
| | 2 s | 20 | 16 | 4 | 20 of 20 | 9 of 9 |

The pages that disagree are of the kinds the sections before named (soft first at 1 s: pages on show just over
0.8 s by the stand-in's log and under it from the window's look). Sharp wide at 1 s: 20 caught, and the reader came
back before the backlog had read 7 of the 10 (each page read back took most of its 8 s on show, the worker idle for
the backlog a few tenths of a second a page), as in the section before (7 of 30 there).

*Steps in a page job's hold.* 1 to 27 steps per pace began in the hold where pages were caught (sharp wide 21 and 20,
soft wide 19 at 2 s, soft narrow 21, sharp narrow 19 and 27), most of them stopped as the hold ended (reads 0 to 4 and
units made 0 to 6 finished there); a stopped read was taken up where it stopped at a later step (`reads_after_a_stop`:
2 to 16 per pace, finished there 1 to 5 times, stopped again the rest).

*The first bubble of a page read back*, median / p90 in ms:

| configuration | pace | with the backlog | nothing caught | difference |
|---|---|---|---|---|
| soft first, wide | 0.5 s | 3,052 / 3,714 | 2,551 / 3,751 | +501 |
| | 1 s | 2,410 / 3,208 | 2,052 / 3,732 | +358 |
| | 2 s | 372 / 689 | 1,130 / 2,105 | -758 |
| sharp at once, wide | 0.5 s | 2,582 / 3,408 | 2,604 / 3,875 | -22 |
| | 1 s | 2,149 / 3,453 | 2,086 / 3,259 | +63 |
| | 2 s | 490 / 1,083 | 1,392 / 2,346 | -902 |
| soft first, narrow | 0.5 s | 1,944 / 3,179 | 2,656 / 3,840 | -712 |
| | 1 s | 1,504 / 1,921 | 1,928 / 2,366 | -424 |
| | 2 s | 292 / 449 | 928 / 2,925 | -636 |
| sharp at once, narrow | 0.5 s | 2,132 / 3,406 | 1,960 / 2,876 | +172 |
| | 1 s | 247 / 288 | 1,232 / 1,896 | -985 |
| | 2 s | 253 / 442 | 584 / 1,150 | -331 |

All paces together: wide 2,074 / 3,453 against 2,074 / 3,732 (60 pages each), narrow 523 / 2,451 against 1,542 /
2,925 (58). The soft wide run at 0.5 and 1 s caught nothing or one page: the pages read again for not being caught
began in 2,478 and 2,252 ms (median) against 2,551 and 2,004 ms with nothing caught, and 3 against 2 of them (1 against
1) went through the soft gate, which takes longer; a turn waited for the backlog's step 58 and 85 ms (median), 295 ms
at most. One run each, ten pages: the median of ten moves by some 300 ms between neighbouring values.

*What a turn waits for.* The worker was free 36 to 157 ms after the backlog's step stopped (median per run and pace),
295 ms at most; a turn to the very page the backlog was reading 31 to 181 ms (median), 288 ms at most.

*The guarantees.* In all eight runs: 0 stale lettering, 0 results kept from unsettled frames, 0 soft frames left in the
cache, 0 frames held after their read, 0 bytes held at the end, at most 24.8 MB of frames held; no request of the
backlog's wasted (the requests "dropped" - 5 with the backlog and 4 with nothing caught in the soft narrow runs, 1 with
nothing caught in the soft wide - are page jobs' on pages flipped past at 1 s, their gate dropped; one of them had
lettered two lines on the sharp frame before the turn, and what it stored went back with it). One page job in the
soft wide run took a page the cache held whole on a frame the stand-in drew soft (no gate, as a page the cache holds
whole goes): it asked nothing, lettered nothing and stored nothing.

*How long the backlog takes, a screen* (its own steps, per screen held at most), against the whole-book run of
scenario w on the same code - 37.7 s for its 5 screens in the wide window (7.5 s a screen), 19.5 s in the narrow one
(3.9 s): wide 4.96 (soft, 2 s), 3.89 and 4.76 s (sharp, 1 and 2 s), 1.55 to 3.8 s with 2 to 5 screens; narrow 3.0 s
(soft, 2 s), 2.48 and 2.46 s (sharp, 1 and 2 s). Below the whole-book run in every run.

*The soft narrow 0.5 s pace in pairs* (higher with the backlog in both runs of the section before): three runs more
each way (`--scenario k5`), not overlapped, with the k runs four a side. The medians of the runs with the backlog
1,944, 2,093, 2,109 and 1,970 ms, with nothing caught 2,656, 1,938, 2,125 and 2,133 ms; pooled 2,052 / 3,084 against
2,200 / 3,112 ms (36 pages each), -148 ms; page by page (the median of each page's runs, nine pages) -16 ms. Nothing
was caught at that pace in any of the runs, and the backlog took no step there.

**`--scenario all`** on the same code, not overlapped: 0 wasted requests, 0 stale lettering, 0 soft frames confirmed,
taken back or left in the cache, 0 lettering on a soft frame, old lettering after a turn 249 ms at most (no job: 227
ms), the page before after a turn 460 ms at most (1 of 53 over 250 ms), the whole-book run finished its 5 pages, no
error.

**The benchmark** (`tools/openmantra_eval.py`, all 214 pages, the tool's server on 11435, each with a state folder of
its own): page by page twice (seeds 1 and 2), page by page with one beginning-of-sequence token instead of two
(`om_one_bos.py`, a scratch wrapper: the client's `<|plamo:bos|>` taken off the front of every prompt and beginning,
the server adding its own as the model's file asks), and in the order behind the reader (`--behind 4`):

| arm | chrF, run 1 / run 2 | mean | translation | prompt tokens, run 1 |
|---|---|---|---|---|
| page by page, two BOS (as built) | 41.22 / 40.56 | 40.89 | 294.6 / 290.5 s | 1,478,518 |
| page by page, one BOS | 41.34 / 40.93 | 41.14 | 293.7 / 289.2 s | 1,476,653 |
| behind the reader (`--behind 4`) | 40.90 | | 316.5 s | |

Detection F1 97.19, CER 1.87 %, 1,586 of 1,586 lines translated in every arm. One BOS is 0.25 above two on the mean,
inside what two runs of the same arm differ by (0.4 to 0.7), and no faster: not changed. Behind the reader is 0.32
below page by page's first run (within 0.5).

**The tests.** The whole suite on `046959e`: 5,467 passed, 22 skipped (the real-data tests without their data), in
32 min 13 s.

**After the review** (on `810ccad`, the branch moved onto 0.9.5). Four things put right, each with tests on fakes
(`tests/test_window_order.py`, `test_covered_viewer.py`, `test_backlog.py`): the covered line is said only when a page
key handed on to the viewer brought no frame for 3 s while it was hidden wholly - counted from the frame count before
the key (`ui.order.turn_asked`, from `_pass_on`), taken back at the next frame or once the viewer is in sight, never
for a still page under a cover; a page turned past within the hold whose confirmation is then taken back is told as
not caught ("missed"), where before it was only let go of, its stages left as they were; the pairs answered before a
step of the backlog is stopped reach the pages' pairs for a translator that does not grow its own (they were lost on
the way out); a page job with no gate turned past - F5, the sharper frame of a page read again, a frame taken as
settled where the early start is not allowed, Translator mode's completions (the list is in `backlog`'s docstring) -
is told as waiting for its next showing, never as gone by too fast, and still never caught (its frame was never
confirmed).

The covered runs in which the line had come, again, the same commands: the cover over the viewer 30 s from 4 s in
with TASlation's window brought up 12 s in, 0 lines (2 before); the same brought up 25 s in without activation, 0 (3);
pages turned by the window's own keys at 1 s under a 40 s cover, brought up 10 s in, 0 (1), 22 turns under the cover;
scenario r under a 24 s cover, brought up 10 s in, 0 (2). Every turn while covered was shown in all four (in the last
one before, one was not).

Scenario k, soft first and narrow, once each way (first bubble of the pages read back, median / p90 in ms):

| pace | caught | with the backlog | nothing caught | difference |
|---|---|---|---|---|
| 0.5 s | 0 | 2,131 / 3,086 | 2,191 / 3,070 | -60 |
| 1 s | 1 (4 stayed 0.8 s or more) | 1,334 / 1,903 | 1,614 / 2,002 | -280 |
| 2 s | 18, 2 more finished while on show | 158 / 251 | 462 / 1,212 | -304 |

At 2 s the 10 pages read back all began with no new read. Both runs: 0 stale lettering, 0 results kept from
unsettled frames, 0 soft frames left in the cache, 0 frames held after their read, 0 bytes held at the end (6.5 MB of
frames at most); 4 requests dropped each way, page jobs' on pages flipped past at 1 s whose gate the window dropped,
and in each one such job that had lettered on the sharp frame before the turn (what it stored went back with it), as
in the round. The page jobs with no gate in these runs (9) were the pages read back that the cache held whole, none
turned past while at work, and the translator there grows its own pairs: the last three fixes are shown by the tests
only. The whole suite on the same code: 5,478 passed, 22 skipped, in 26 min 34 s.

**Not verified.** The real viewer (the stand-in only); with TASlation really the window in front, the covered runs
beyond the one before the announcement; what the announcement does (above); a window between that is itself topmost
(not met); more than one screen with the viewer on another; a viewer run as administrator (Windows refuses the
placement: logged, nothing else); Firefox.

## The whole-book run removed (2026-11-22)

On the owner's decision there is one way of reading: each page is read and translated when it is on show (Auto, F5),
and the pages turned past go on being read and translated behind the reader ("Pages turned past go on being read"
and the sections after it), which does what the whole-book run was for. The run is gone with what served it alone:
"Read whole book..." and its dialog, "Finished reading", the band and the page strip under the page, the run's view
of the page it worked on, its taskbar progress and sound, its questions at Stop and at closing, `taslation batch`
(with `--retranslate` and `--wait`) and `gui --mode`, and the settings `context_mode`, `chunk_bubbles`,
`lookahead_bubbles`, `batch_max_pages`, `batch_memory_mb`, `scan_mode`, `flash_when_done` and `sound_when_done` (a
taslation.toml that still holds them loads without a word; they do nothing). Stop (Esc) stops the page being
translated, as before; the indicator beside the page is shown by its setting at all times. Translations a run cached
stay valid and show as any cached page. The sections above stay as they were written.

**What no longer has a counterpart.** The measurements above taken with the run or with its way of translating:

- *The batch of October 2026* (`taslation batch` on the viewer, the pages read first and translated in chunks with
  the story so far as context): "Live window test" and "Context-aware batch" (2026-10-24 and 2026-10-25: the fake
  viewer read by the batch, in context mode), "A real book" (2026-10-25: the volume read by the batch, its chunks
  timed), the batch in a second process of "Stale cache entries and the shared cache file" (2026-10-25), `batch
  --wait` in "The book's tab switched away" (2026-10-26), `batch --retranslate`, one batch per viewer window and the
  stop when pages change shape in "A translator's pass over the real volume" and "The volume translated again with a
  checked series sheet" (2026-10-27), the batch runs of "Lettering against the outline", "One translation per text"
  and "The rest of the list" (2026-10-28: what a batch run would send or drop, where the batch stopped), and the end
  of the book in a whole-book read in "A viewer raised for a look" (2026-10-31).
- *The size and the context of a run's requests*: `chunk_bubbles` at 100 or 40 against a 16K or an 8K context in
  "Lighter models compared" (2026-10-28), the 4B models translating as the batch did with its 16K context in "A
  knockout among the 4B models" (2026-10-29), the batch's longer context in "A larger context for the 4B"
  (2026-10-30), and the runs of 100, 12 and 30 lines that set `chunk_bubbles` to 30 in "Read first, translate all at
  once" (2026-11-02). No trial of `lookahead_bubbles` is in this log.
- *The memory a run held*: what a scanned page unit kept, 22.6 KiB a page and 4.4 MiB per 200 pages, in "Read first,
  translate all at once" (2026-11-02).
- *Whole-book run times*: the five series read in the window in "OpenMantra through the window" (2026-11-01); the
  translation pass of a read-first batch (100 pages with the GPU, 16 without) with and without the server's prompt
  cache in RAM in "Ollama's prompt cache in RAM" (2026-11-14, the runs of 2026-11-13 the README's hardware figures
  came from among them); the whole-book table and row of "Line reuse" (2026-11-15); the whole-book columns of "What a PLaMo request costs the server" and the "whole book"
  rows of "The full-size window cache" (2026-11-20), whose page-by-page rows stay comparable.
- *The benchmark's book mode*: `tools/openmantra_eval.py` translated as the whole-book batch did from "OpenMantra as
  the sample dataset" (2026-10-30) on, through `BatchReader._translation_pass` itself from 2026-11-02, so every
  official chrF, share of lines flagged and translation time in this log is that mode's, from "OpenMantra after the
  quality round" (2026-10-30) to the "book mode (official)" rows of the sections on pages turned past (2026-11-20 and
  2026-11-21). The benchmark now translates page by page (`--mode page`, `Pipeline._translate_regions`). Detection F1
  and the OCR's CER do not depend on the mode (F1 97.2 and CER 1.9 % in every arm on 2026-11-21); chrF does (41.22
  page by page and 40.99 in book mode on the same code that day).
- *Stand-in scenarios w and w2* (`tools/standin_e2e.py`): in "Where a page's time goes in the window" and "The first
  page at the start, soft frames, and the first request before the OCR ends" (2026-11-20), in the runs of every
  scenario on 2026-11-21, and as the yardstick of how long the backlog takes in the sections on pages turned past
  (2026-11-20 to 2026-11-22: 36.2 to 37.7 s for the 5 screens of scenario w in the wide window). On GitHub's runners
  the third group of stand-in scenarios is now t, t2 and k's three paces ("t-t2-k5-k1-k2").

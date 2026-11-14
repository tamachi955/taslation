# Offline verification

TASlation must work with the network unplugged and must never talk to
anything but the local Ollama server. This document records how that is
enforced, how to check it yourself, and the results of the verification run
made on 2026-10-24 on the machine the project was built on (Windows 11,
Python 3.13.2, torch 2.14.1+cpu, transformers 5.20.2, manga-ocr 0.1.16).

## How "nothing leaves the machine" is enforced

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
   `models/` with `safetensors`; no Hugging Face library is installed. Sections below that name manga-ocr, `ocr_device` or
   `transformers` are the record of the OCR before 2026-11-01; see "The OCR
   model (2026-11-01)".
4. **Loopback-only Ollama client** (`taslation/translate/ollama.py`): rejects
   any URL whose host is not loopback, and uses a `urllib` opener with proxies
   disabled.
5. **Separate download scripts**: `setup_models.py` is the only code a user
   runs that uses the network; the developer tool `tools/fetch_openmantra.py`
   (one download of a sample dataset, see "OpenMantra as the sample dataset
   (2026-10-30)") is the other. The application imports neither.
6. **No image persistence**: there is no code path that writes a captured or
   translated page to disk. The on-disk cache (`~/.taslation/cache/*.json`)
   holds translated text, normalised bubble geometry and 320-bit page
   fingerprints only.
7. **Saved files protected at rest** (`taslation/protect.py`): the caches,
   annotations and series sheets (and the copies kept beside them) are written
   only in their protected form, Windows DPAPI for the Windows user who saved
   them, so a copy taken off the computer or opened by another Windows user
   reads as nothing. Any program running as that same Windows user can open
   them, as TASlation does. An earlier version's plain files are converted at
   the start; `taslation audit` ends with the count of any left plain.

## Check it yourself

```bash
taslation doctor                                   # guard status, model, font, Ollama
taslation audit tests/fixtures/sample_page.png --translator echo   # full pipeline + list of network calls
taslation audit tests/fixtures/sample_page.png     # same, with Ollama: only 127.0.0.1:11434 appears
python -m pytest tests/test_netguard.py -q          # guard tests incl. a raw-socket subprocess
taslation cache protect                            # saved files: protected, plain, opened here (counts only)
python -m pytest tests/test_protect.py -q           # the protection, with real DPAPI in a temporary folder
```

The audit's last part, `--- saved files (at rest) ---`, counts the files with
text of a book in the state folder and ends with "plain files with text of a
book: none" when every one is protected; it changes nothing.

Then disconnect (Wi-Fi off / cable out) and use the GUI normally. Ollama keeps
answering on loopback; the OCR model loads from disk.

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
were removed with `ollama rm`. Its vision weights went unused until the second-reader rule (below), turned off again by default after a gold transcription ("Claude as the judge, and a gold set"); at 4B
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

Superseded the same night: judged by Claude against a blind transcription
of the lettering, the rule reads worse than manga-ocr alone, and the
default went back to manga-ocr (next section).

### Claude as the judge, and a gold set (2026-10-29)

The owner asked whether Claude should be the judge instead of the pulled
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

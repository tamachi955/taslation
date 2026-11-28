# Development tools

## Setting up by hand

```bash
python -m venv .venv
.venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
# or, with an NVIDIA GPU, the build install.cmd takes there: whl/cu126 (driver 528.33+), whl/cu130 for Blackwell (580+)
pip install -e .[dev,backup]
python setup_models.py --font --fonts   # asks you to agree to the OCR model's licence (non-commercial, CC BY-NC-SA 4.0)
ollama pull qwen3.5:4b
taslation doctor
```

`backup` brings `cryptography`, needed only for encrypted cache exports. `--font` fetches Comic Neue Bold and Bold Italic for English
lettering, `--fonts` the Noto Sans family for other scripts (both SIL Open Font License); without them Windows' own fonts are used.

The scripts under `tools/` are for developing TASlation. They are not part of the application, never ship in a
release, and are the only code in the repository allowed to write page images to disk or to use the network.

## Snapshots of a book's screens

A developer may keep screens of a book they own under `~/.taslation/dev-snapshots/<book>/` (PNG files and a
`manifest.json`), so that detection and typesetting can be tuned without turning pages in the viewer at every
experiment. Nothing in the repository saves them: `tools/dev_frames.py` reads them for the other scripts and the
gated tests, lists them, and `python tools/dev_frames.py wipe --all` deletes every snapshot. The snapshots stay
on the development machine: they are pages of a book the developer owns, and they are never copied anywhere,
committed or attached to a report. A frame that exposes a bug is kept beside a `.json` of the expected facts and read
by a gated test (`tests/test_realdata_frames.py`, run with `TASLATION_REALDATA=1`).

## Scoring the OCR against a transcription

`python tools/ocr_gold.py score --book "<name>"` compares the OCR with a hand-made transcription
(`ocr_gold.json` in the book's snapshot folder) and prints the character error rate and counts only, never the text.
The transcription is the book's own text and stays with the snapshots.

## OpenMantra, the sample everyone can use

The evaluation dataset of "Towards Fully Automated Manga Translation" (Ryota Hinami, Shonosuke Ishiwatari, Kazuhiko
Yasuda, Yusuke Matsui; AAAI 2021), published by Mantra Inc.: five Japanese manga, 214 pages, 1,592 text regions with
frames, Japanese text and professional English and Chinese translations. Its licence is CC BY-NC 4.0 (non-commercial,
with attribution), which the MIT-licensed TASlation cannot carry, so the dataset is neither in the repository nor in a
release (the README's video, which shows pages of one of its titles being translated and is credited there, is an
attachment kept by GitHub, not a file of the repository): `python tools/fetch_openmantra.py` downloads it once into `~/.taslation/datasets/openmantra/` (the archive is
inspected and only what is needed is extracted; the provenance goes to `SOURCE.md` there). The application itself
never reads it. `python tools/openmantra_eval.py` prints numbers only: detection precision, recall and F1 at IoU 0.5,
the OCR character error rate, chrF of the default model's translation against the professional English, and the share
of lines the review flags (`--pages 4` for a quick run, `--no-translate` without Ollama); results go to the dataset
folder's `results/`. It detects with the app's default `detect_model`, "auto" since 0.2.0: on a computer with a CUDA
GPU and both page models installed its numbers are the layout model's, elsewhere the classical detectors' as before;
`--detect-model off` gives the classical detectors' on any computer, the default of earlier versions. The measurements so far are in
`docs/OFFLINE_VERIFICATION.md`. Work that uses the dataset cites
the paper.

### Comparing two settings fairly

One translation run is one draw. Ollama samples at temperature 0.2, so one early reply shifts the rest of a series
(about 1.2 chrF of run-to-run SD per series). A chrF
difference between two single runs of about 1 point can be noise alone, and a bootstrap over pages calls it
significant because the noise moves whole series, not separate pages. To compare two settings (arm A and arm B):

1. Fix the sampling with `--seed S`. It goes to Ollama as `options.seed` (only in the eval; the app sends no seed).
2. Repeat with `--runs N` (3 or more). Run k uses seed S + k - 1. Detection and OCR are computed once, and every run's
   numbers are kept in `translation.run_results`.
3. Compare with `python tools/compare_runs.py a.json b.json`, or `--a a1.json a2.json --b b1.json` to pool several
   files per arm. The arms are paired by series. The tool prints B - A with a 95 % interval from a bootstrap over
   series and runs (not pages), and the run-to-run SD of each arm. It does not call a difference significant with
   fewer than 3 runs per arm unless both arms ran the same fixed seeds, and the output says so.

```
python tools/openmantra_eval.py --runs 3 --seed 1 --out a.json
python tools/openmantra_eval.py --runs 3 --seed 1 --detect-model off --out b.json
python tools/compare_runs.py a.json b.json
```

A fixed seed makes a run repeatable, but any setting that changes a prompt (a different detector changes the
geometry and so the room hints) still draws a different series, so several seeds are still the better measure. With
only five series the series bootstrap is coarse, and `--geometry gold` keeps detection changes out of a translation
comparison altogether. `--warm` translates with the warming the window does between pages
(`Pipeline.warm_soon`): the prompts stay the same, but the server computes their beginnings in other batches, so a
fixed seed can still draw some answers otherwise.

`python tools/openmantra_merge.py part1.json part2.json ... --out all.json` joins the results of the eval run on parts
of the dataset (`--series`: a title or several a part, say each in a job of its own) into those of the whole. The page
rows are pooled and scored again as the eval scores them, so the "all" row is the pooled one, never a mean of the
parts', and `compare_runs.py` reads the joined file as a run of the whole. Parts that share a title or were run
otherwise (the options but `--series`, the model, the settings, the dataset) are refused; `--force` joins them and
the file lists what differs. A title's context never reaches another title; what still differs from one
run of the whole is that a line asked for before in another title is drawn anew there, and that each part's server
starts without the caches of the titles before it.

## Whether a frame shows a page of a book

A browser window picked in the viewer chooser is read only once a frame under its tab is judged a page of a book
(`taslation/bookpage.py`, from the frame's layout alone: drawing in panels, lettering in bubbles, no grid of cards and
no colour off a page laid on a ground) - unless it is a viewer known on this computer, which is never on trial
(`ui.viewers.ViewerMixin._known_viewer`: a capture area set by hand for it, in profiles.json under the viewer's name
its title gives; or a book read in it before by what viewers.json remembers - its tab title chosen before, a viewer's
part learned at its start or end, or a title ending as one chosen before did). Translate pressed reads the frame on
show whatever it was judged. "not" is only for a blank tab or a page of text with no picture: a black page (a quarter
of the area at level 16 or darker), colour, a picture in grey tones, a column of squares of one size give "unsure" at
the most. `python tools/bookpage_eval.py` measures the judgement, all drawn in memory and nothing written:
OpenMantra's 214 pages as a viewer shows them (on a dark, white and black ground, as spreads, as the capture area
itself, in a window narrower than the page, and as a soft first picture), the made-up book pages of
`tools/make_sample_page.py` (alone, beside a black page, and a black page alone), a book's first five screens made up
(`tools/book_screens.py`: the cover alone, a dark page beside a black one holding a plate, a colour spread with a
column of squares, a grey page beside a black one holding a picture, a grey spread running off the window's foot;
each in both letterings, whole, with the browser's bar trimmed and in an area set about the spread), and made-up pages
of no book (pages of text in Latin letters and in Japanese, light and dark, with a picture in colour or in grey, a
table or two columns; a document; a shop's grid of cards, bordered, dark, with outlined buttons and one item's page;
shelves of covers in colour and grey; grids of pictures; a forum; blank tabs; the stand-in's other tab), each in
several window sizes and seeds; `--set made` only the made-up pages (no dataset needed), `--holdout` other window
sizes and seeds than the rules were set on. It prints per kind how many came out "book", "not" and
"unsure", the false accepts (a page of no book judged "book"), the false rejects (a page of a book judged "not") and
the time a judgement took. The measurements so far:

| Set | Pages of books | False rejects | Unsure | Pages of no book | False accepts | "not" | Unsure |
|---|---|---|---|---|---|---|---|
| The rules' set | 1,576 | 0 | 271 (17.2 %; 65 of 214 soft first pictures, the 30 frames of the five screens) | 252 | 0 | 109 | 143 |
| Hold-out | 846 | 0 | 100 (11.8 %) | 315 | 0 | 141 | 174 |

With the rules as they were before (a black page, colour and a picture no reason for "unsure"), the new frames gave
2 false rejects - a black page alone, and the dark page beside a black one with the bar trimmed - and the pages of no
book 115 "not" (146 in the hold-out): the 6 (5) more were pages of text with a picture and a shop's pages.
A page of text, a document, a blank tab and the stand-in's other tabs come out "not" (the right pane says so at once,
but where the window waits a pale or blank frame out as a page still loading: then after PICK_NOTHING_S, as for
"unsure"); a page of text with a picture, a shop, covers, a gallery or a forum "unsure" (nothing read, the right pane
says so after PICK_NOTHING_S). A column of squares raises the grid only on a frame of long lines (where a page of text
has its lines): a column of panels of one size on a page of a book with none is not one. One shelf of
grey covers came out "book" before a page with panels of lines only and no closed frame needed BUBBLES_LINES bubbles; a
judgement took some 25-30 ms (100 ms at the most) on a 1900 x 915 frame.

## Sound words

`taslation/soundwords.py` is the program's own list of Japanese sound words (some 680 base forms in katakana, written
from general knowledge of the language, no dictionary or site copied; their lengthened, repeated, small-tsu, hiragana
and voiced forms come by rule, `skeleton` and `KNOWN`). `Pipeline._sound_word` uses it on lettering set on the page
whose reading to translate is short kana: what the readers read alike stands (a sound word of the list makes the
region's kind "sfx"; one that is none is no reading to set right), and only where each reader read another thing is
one of theirs taken, or one with a kana they mix up changed (`CONFUSABLE`); where then none is a sound word the region
is left as drawn (the interim rule: neither erased nor lettered).

It was measured on OpenMantra's 214 pages at full size and 1000 px high, through the whole pipeline with no
translation, each region `_sound_word` saw noted in memory (numbers only; the readings and the gold lines never
written), and the regions it touched cut out in scratch, looked at by eye and deleted:

| At full size / 1000 px high | Regions |
|---|---|
| Sound words found (as the readers read them / set right) | 20 (19 / 1) / 14 (14 / 0) |
| ... hand-lettered sound words or cries, by eye (full size) | 19 of the 20 (one was drawing that the gate had passed as a line before) |
| Short kana read alike that is no sound word, left as read | 3 / 3 (at full size a sign and two lines of narration, gold lines all three) |
| Left as drawn, each reader read another thing (the interim rule) | 0 / 1 (a hand-lettered sound word in outline, no gold line) |

What was tried and dropped, on the same pages at full size:

* Readings the gate drops (``ocr-noise``, ``low-confidence``) asked again of the other readers, and taken as sound words
  where two of them read alike: 82 regions, of which by eye 14 were sound words or cries (4 of them in bubbles), 2
  other lettering (part of a sign, a question mark) and 66 drawing - hair, hatching, speed lines, faces. Lettering them
  would have erased the drawing in 66 places for 14 sound words; they stay as the gate leaves them.
* A reading set right where the readers read alike: of the 11 readings changed in a first version, 4 changed one kana
  of what the readers had read alike into a word of the list (a line of narration, a muffled sound, a sniff and a
  rustle, the last three now on the list as read), 6 only the marks (dots, a long mark) and 1 took the reading the
  other two readers shared. The readers' agreement now stands, and a reading counts as set right only where its
  skeleton changes.
* A confusion table from the shapes alone (ソ and ン, シ and ツ and the like): the readers never mixed those up on the
  sample set's sound words. The table is what they did mix up: on the 33 regions of hand-lettered sound words among those
  read as short kana, ウ and カ 4 times and ジ and バ twice; against the gold lines' sound words, ウ and ラ twice and ワ and
  ア once. A small vowel read for a large one, as common, is folded by `skeleton`. The pairs between readers on the rest
  (ン and ー, イ and ハ, ...) came from drawing read as kana.

The audit (`tools/audit_render.py`, from version 8) counts per set and scale the sound words found, set right and
left as drawn, and the damage codes on the sound effects lettered (`sound_lines`). From version 9 its summary goes by
the owner's levels, S1 to S4, the worst first (`CODE_LEVELS`: each code's level), with the regions a neighbour's
erase, lettering or patch took lettering from (`OVER_OTHER`, S2) and the specks of lettering left joined to a line the
erased page keeps or beside an outline two bubbles share (`LEFT_BY_LINE`, `LEFT_SHARED`, S3); an outline counts as cut
only where the erase broke it (`LINE_CUT` on `line_cut`: not a glyph joined to it erased where it goes on past it); the
made-up layouts 18 and 19 are bubbles joined in pairs.

`soundwords.RENDERINGS_TEXT` holds an English rendering and a short meaning for the 395 base forms PLaMo 3 Translate
gets wrong as a sound effect into English, written for the program like the list (no dictionary or site copied);
`tools/sfx_eval.py words` and `renderings` (after earlier pairs, as the app asks) are how they were found, and
docs/OFFLINE_VERIFICATION.md, "Sound effects, the kind of a line and PLaMo", has the numbers. A base form gets an
entry only where the model's own answer is wrong: run `words` and `renderings` again for a model or a list that
changes, judge the answers by eye, and add or drop entries; `rendering` looks a reading up by its `long_form` (the
lengthening kept: ガン is a clang, ガーン a shock), so two entries must not share one.

## The analysis log

`taslation/analysis.py` writes one JSON line per page read or shown from the cache to `<state dir>/analysis.jsonl`
(4 MB, then it starts again, the one before kept as `analysis.1.jsonl`), and lines of what the person saw (`"type":
"ui"`, written by `ui/measure.py` as the next page comes) and of each change they made (`"type": "edit"`, from the
history's steps). **Numbers only**: no page text, no reading, no translation, no title, no file or window name, no
pixel. Every key and every string value is one of the program's own names (lowercase ASCII, `analysis.NAME`); anything
else becomes "other" as it is written (`analysis.clean`), and `tests/test_analysis_log.py` puts random marker texts,
titles and names into every field of random pages and checks that none reaches the file.

It is on by default when TASlation runs from a source checkout (a `.git` beside the package) and off in an installed
copy (the release's ZIP has no `.git`); `analysis_log = "on"` or `"off"` in taslation.toml forces either. It is in no
dialog. The stand-in's runs write it too (`tools/standin_e2e.py` copies it into its `--out` folder with its tables,
`analysis.txt`). A page's line holds its stages' and helpers' times (`analysis.timed`, `analysis.timing`), what the
helpers counted, how many regions each helper CHANGED the outcome for (`analysis.acted`: not how often it ran), the
regions counted by status, kind, tier, fit and flag, the page's coarse look on a 64 x 64 grid of its pixels (colour,
ink, dark ground, drawn), the time to its first lettering, the GPU's free memory where torch has CUDA up already, and
what the log itself cost (`self_ms`). Measured on the made-up screens on the processor (pages of about 95 ms): about
1 ms a page, all of it counted, the writing of the line included; on a real page of one to several seconds that is
well under 1 %.

Every defect the log counts carries its level, the owner's scale of how bad it is for the reader (`analysis.LEVELS`);
how often it happens is what the log measures, and nothing that prevents an S1 or S2 defect is removed for being
rare:

| Level | What | Found by the log |
|---|---|---|
| S1 reading fails | a bubble not translated, its original shown where a translation exists, a translation on the wrong page, keys or panes keeping the person from reading, a page over 15 s with a GPU (45 s without) | `not_translated`, `bubble_left_as_drawn` (read as Japanese with confidence in a bubble, left as drawn), `patch_not_shown` (the window: a lettered region not on show for no meant reason), `keys_not_back`, `page_slow`; the person's own changes: a region added (`edit_add`), one with no translation given one |
| S2 content lost or damaged | a translation cut, covered or out of sight; the drawing destroyed by an erase; a false region lettered over the art | `lettering_cut`, `unsure_lettered_on_art`; a translation retyped, the page asked again, a region deleted that had been lettered over the art |
| S3 readable but hard | under the readable size, hyphenated, specks or ghosts, an outline or a line cut, lettering over an outline | `small`, `hyphenated`, `overrun`, `unsure_left_as_drawn`, the review flags; a region moved, resized or deleted |
| S4 cosmetic | a slant, a face, a size a little off, a pane a little far | `turned`, the lettering's checks, a region's kind or direction changed |

S1 and S2 cases are written one by one with their numbers (the region's index, box, kind, tier, confidence and the
helpers that acted on it), S3 and S4 counted. `python tools/analysis_summary.py [FILE or FOLDER]` prints the tables:
the defects by level first (S1 and S2 case by case with the page's number in the session, S3 and S4 with their rates),
then the stages and helpers (total, share, median and 95th percentile per page), the slowest pages with their facts,
the regions each helper changed, the counts, the window's lines and the edits. Copy a report gets the same tables as an
`[analysis]` section while the log is on.

### A page's time budget and the helpers' risks

Every page read has a time budget (`taslation/budget.py`): `PAGE_BUDGET_S`, 15 s, where torch has CUDA up, and
`PAGE_BUDGET_CPU_S`, 45 s, without a GPU - past it the page is an S1 defect. The page's thread holds it, and the threads
that work for the page (the drafts' lettering, the next unit read beside) adopt it. What grows with what a page holds
is bounded by it:

* **LaMa** takes no new window once the page has spent `LAMA_UNTIL` (60 %) of its budget, past `LAMA_PAGE_WINDOWS` (12)
  windows on the page, past `LAMA_PAGE_PX` of their pixels (4 million on the GPU, 1.5 million on the processor: some
  0.5 s and 5.4 s a million pixels there), or past holes of `LAMA_PAGE_HOLE` (12 %) of the page's area; the page's first
  window is never refused for its pixels or its hole. A refused window is filled by OpenCV's inpainting
  (`artwork.telea`, milliseconds, a smoother fill). Each window is scaled down to `LAMA_PART_PX` (768 x 768 on the GPU)
  or `LAMA_PART_CPU_PX` (512 x 640 on the processor) before LaMa and its fill scaled back, only the hole pasted (the
  hole widened 5 x 5 before the scaling, so the cubic scaling back takes nothing of the lettering into it).
* **The tone fill** looks at no window of more than `TONE_MOST_PX` (900,000 px) and tries `TONE_ROUNDS` (400) rounds of
  shifts at the most.
* **Large unsure lettering on a colour picture** is left as drawn (`Pipeline._big_unsure`): a region not in a bubble,
  read with a confidence under 0.8, its characters 2.5 times the body lettering or more (the smallest of the page's
  usual size, the book's median and a thirtieth of the page's height), on a colour picture (a ring round it with 35 %
  of its pixels in colour or more, and not flat). It is a cover's title or the picture itself read as lettering more
  often than dialogue, and erasing it on the drawing is the dearest erase there is; it is counted as S3,
  `unsure_left_as_drawn`, acted `big_unsure`.
* `erase.line_pixels` works on a window round the box and each line, not on the whole region's padding: the same
  pixels in 300 made-up cases, 45 ms a call instead of 77.

The layout model's and LaMa's first loads are timed (`layout_model.load`, `lama.load`), and so is the wait for the layout
model while another thread holds it (`layout_model.wait_ms`); what LaMa was refused is counted (`lama.refused.time`,
`.windows`, `.pixels`, `.hole`; `lama.scaled`; `lama.cpu_windows_with_gpu` where it ran on the processor with a GPU
there). A page read for the window over its budget writes one warning in `log.txt`: its seconds against the budget,
its slowest stage, its slowest helper (with the analysis log on) and what LaMa was refused; the analysis log has the
page as an S1 case, `page_slow`. `tests/test_page_budget.py` reads the made-up screens of `tools/book_screens.py` (the
cover, the colour spread, the grey spread and `hard_cover`: a saturated picture with six pieces of large outlined
lettering in several colours, 40 to 90 px, and a bubble) on the processor, each stage against its own budget scaled
by how fast the computer runs a fixed piece of work, and the harder cover with a slow stand-in for LaMa against the
page's budget; the runners' bw-walk group says each screen's seconds by stage and judges each screen read inside its
budget.

Measured on the GTX 1660 Ti computer (2026-11-28; the error is the mean difference, 0 to 255, from the drawing as it was
before the lettering was put on it, over the pixels the erase changed):

| Page or function | Before | After |
|---|---|---|
| the made-up screens on a warm GPU: cover, colour spread, a big title, the harder cover | 0.14, 0.20, 0.14, 0.95 s | the same |
| the harder cover as a session's first page, the layout model and LaMa on the processor | 8.40 s (the layout model's load 4.1 s, the wait for it 3.3 s, LaMa 2.7 s for 2 windows) | 8.37 s |
| the harder cover drawn 2.2 times as large, LaMa on the processor | 1.25 s | 1.08 s |
| 16 regions of outlined lettering on a drawing, processor | 20.0 s, 16 LaMa windows, error 10.7 | 7.9 s, 5 LaMa and 11 OpenCV, error 13.4 |
| the same, GPU | 3.24 s, error 10.7 | 2.73 s, 12 LaMa and 4 OpenCV, error 11.3 |
| one large region (a box of some 760 x 690), processor | 3.63 s, error 7.8 | 2.51 s, error 8.9 |
| the same, GPU | 1.22 s, error 7.8 | 1.11 s, error 7.8 |
| `line_pixels`, 300 made-up cases | 77 ms a call | 45 ms a call, the same pixels |

A cover that took 80 s with a GPU (its detection 23 s, its erase and lettering 53 s) was not reproduced with made-up
pages: the slowest here was the harder cover as a session's first page with both models on the processor, 8.4 s. What the numbers point to is LaMa on the
processor with nothing bounding it per page or per window (some 5.4 s a million pixels; a cover's large lettering on a
colour picture gives windows of a million pixels and more) and the layout model's first load; both are now bounded or
timed, and the next such page says its stage and helper.

`tools/analysis_summary.py` ends the time tables with each helper's risk line: the level of the defect it prevents,
how often it changes a region's outcome (per 100 regions; "n/c" where that is not counted), the level of the defect it
can cause, and its ms a page read (the 95th percentile of the pages it ran on). A helper that prevents only S3 or S4
and changes under `CANDIDATE_EFFECT` (1 per 100 regions), or costs `CANDIDATE_MS` (100 ms) a page or more, is marked
"candidate for removal" - only marked: nothing is removed before the owner's read-through numbers on real books. On
the sample set's 214 pages (GPU, a canned translator; 2,272 regions; 187.2 s in all, the slowest page 1.88 s; 38 LaMa
windows, none refused or scaled, so the same as with no budget; nothing left as drawn by the large-unsure rule;
defects S1 17, S2 12, S3 211, S4 129):

| Helper | Prevents | Per 100 | Can cause | ms a page (p95) |
|---|---|---|---|---|
| layout_model | S1 | 70.9 | S2 | 84.5 (100) |
| bubbles, text_blocks | S1 | 29.1 | S2 | 2.7 (9), 0.2 (5) |
| paper_fill, fill_paper | S1 | 68.3 | S2 | 60.6 (120), 9.6 (19) |
| letter | S1 | 70.0 | S3 | 90.9 (170) |
| telea | S1 | 0.0 | S3 | 0.0 |
| lama, art_mask | S2 | 1.7 | S3 | 25.4 (286), 4.3 (10) |
| on_art | S2 | 26.5 | S2 | 10.0 (23) |
| keep_lines, line_pixels | S2 | 0.0 | S3 | 11.8 (29), 24.5 (58) |
| see_through, closed_room | S2 | 0.1, 0.3 | S3 | 0.4 (38), 0.3 (11) |
| big_unsure | S2 | 0.0 | S3 | 0.0 |
| sound_word | S2 | 1.0 | S1 | 0.0 |
| fit_frames, fit_rescue | S2 | 9.4, n/c | S3 | 44.2 (114), 19.1 (67) |
| ground_fill | S3 | 24.7 | S2 | 8.1 (19) |
| tone_fill (with tone_look) | S3 | 0.0 | S3 | 10.6 (282) - candidate |
| closed_interior | S3 | n/c | S3 | 9.0 (21) |
| left_out | S3 | 1.6 | S2 | 0.0 |
| whole_glyphs | S3 | 0.1 | S2 | 0.0 (2) - candidate |
| stray_erase | S3 | 0.5 | S2 | 1.6 (4) - candidate |
| ring_erase | S3 | 0.0 | S2 | 7.8 (24) - candidate |
| page_caps, slant, slant_doubtful | S4 | n/c | S3, S4, S4 | 38.9 (73), 48.2 (87), 0.1 |

The sample set has no colour pages and few tones; a helper that changes nothing there may still prevent its defect
on a real book, which is why the candidates wait for the read-through.

### A spread's next unit, the readers and the watch

A page's line keeps each page unit's reading (``read_units``: read beside the unit before or not; its reading's, its
wait's and its translation's start, end and ms from the page's start; the crops; each reader's calls, ms and longest
call on the GPU and on the processor, those on the processor while a request to the translator ran apart; its passes
with no CUDA graph; the ms it waited for the readers' graphs) and the translator's requests that began in the page's
time (``requests``). `tools/analysis_summary.py` tables unit 0 against unit 1, the time from the first unit's last
request to the next unit's first with the slowest spreads, and the see-through watch's duty from the window's counts
(its compare ms a second, looks and frames a second, frames not compared). `tools/screens_read.py` reads screens kept
on this computer (a measuring session's frames, or any folder of screen pictures) as the window reads them, at their
own pixel size, with a translator of its own, and prints the same numbers, nothing else.

Measured on a made-up spread at 1920 x 1032 (21 bubbles a page, 44 crops a unit; GTX 1660 Ti; PLaMo on an Ollama of
the run's own answering requests of three lines back to back; the unit read on a thread of its own; the computer
shared with other work then, so the processor's figures vary between runs - CPT 213 to 964 ms a call at normal
priority):

| A unit's reading | ms | charspot / nar ms a crop | CPT ms a call | a request |
|---|---|---|---|---|
| alone (GPU) | 2,137 | 15.1 / 24.5 | 214 | - |
| beside the requests, on the processor during each (the rule before), normal priority | 20,995 | 182 / 487 | 790 | 296 ms |
| beside the requests, on the GPU with the graphs, normal priority | 4,961 | 18.6 / 39 | 964 | 366 ms |
| the same, below normal (as the reading beside ran) | 20,995 | 24.8 / 44 | 5,644 | 313 ms |
| with the drafts' lettering and the watch's compare at 40 a second too, processor during requests, normal | 64,586 | 577 / 1,576 | 1,815 | - |
| the same on the GPU with the graphs, normal | 8,879 | 20.6 / 39 | 2,152 | 348 ms |
| the same on the GPU, below normal | 38,598 | 36 / 48 | 11,337 | 319 ms |
| on the GPU without graphs (the plain pass), beside the requests, normal | 3,163 | 23.4 / 47 | 270 | 419 ms |
| the translator alone | - | - | - | 296 ms |

So: a reader whose copy has its CUDA graphs reads on the GPU through a request (`place.graphed`; a copy without them
- the start short of room - still reads on the processor then), and the reading beside keeps the page's priority
(`pipeline.READ_BESIDE_PRIORITY`). What it can cause: a request while a unit is read on the GPU beside it takes some
24 % longer (366 ms against 296), for the seconds the reading lasts. The plain pass on the GPU beside the requests was
measured fast too (the 687 ms a crop of before was not seen again), but it is the case of a card with too little room
for the graphs, where the driver moves memory: left as it was. The watch decides a frame whose rows of the client
area hold the very bytes of the frame compared last, with the same sets, box and DPI, as that frame was decided,
by a memcmp (`seethrough.same_rows`, `SeeThrough._decide`): a change of any byte there is compared at the frame that
shows it, as before.

## Developer measuring

A switch on top of the analysis log, for the owner's own measurements on their own computer, and the one exception to
"no page image and no page text on disk": Menu > Developer measuring > Measure (`ui/measure.py`,
`taslation/devmeasure.py`). It exists only in a source checkout: an installed copy has no entry for it and
`devmeasure.Session` refuses to start there (`devmeasure.Refused`; tested on a folder with no `.git`). Its words are
English and Japanese only, never put into the 16 languages: no reader of an installed copy sees them. It is off at
every start and never remembered; switched on, it asks once, in a plain box that says what is kept and where; while it
is on the right pane's lasting rows begin with "DEV".

While it is on, under `<state dir>/dev-measure/<the session's start>/` (outside the repository; a `README.txt` beside
the sessions says what they hold and that they are private), for every page read: `pNNNN-frame.png` (the frame as
captured), `pNNNN-erased.png`, `pNNNN-lettered.png` (the whole lettered page: the frame with every patch composed in,
as seen over the viewer), `pNNNN.json` (every region: its boxes, kind, tier, each reader's reading and charspot's
confidence - nar and cpt give none -, the settled reading, the translation, the flags, the helpers that acted, the fit
taken; the page's analysis line; the requests made for it), each later finished state after an edit or Ask again
(`pNNNN-sK-lettered.png`, `pNNNN-sK.json`); `requests.jsonl` (the prompt's parts, the prompt and the raw answer of each
request), the session's `analysis.jsonl`, `log.txt` (the session's lines of the program's log) and `input.jsonl`.

* **No cache.** Every page is read, translated, erased and lettered afresh (`Pipeline.measuring`): the normal cache is
  neither read nor written - the pipeline gets a cache of the session's own, deleted when the mode ends -, no line is
  reused, nothing is read ahead (the backlog's work would be thrown away), and the series sheet and the book's marks
  are read and never written (`devmeasure.ReadOnly`: a change made to them while measuring lasts until the mode ends).
* **The input record** (`input.jsonl`): which page the person asked for and when (ms), so that `tools/analysis_summary.py
  SESSION_FOLDER` can time each turn from the press to its first lettering and to its end (median, 90th percentile, the
  10 slowest with their page's facts). Its limits are not negotiable: keys are recorded only while the viewer's window
  or one of TASlation's is the foreground window, and only their kind (left, right, up, down, space, page up, page
  down, home, end, enter, escape, Insert, Delete; every other key "other", with nothing of which it was) - never a
  character, never while another program is in front; of the mouse, the presses on TASlation's lettering and side
  panes with their place and button, and the wheel's ticks over the viewer. They are seen through Windows' low-level
  hooks (`WH_KEYBOARD_LL`, `WH_MOUSE_LL`), installed on a thread of their own with a message loop only while the mode
  is on and the viewer or TASlation is in front (looked at every 100 ms) and removed otherwise; each event is looked at
  again against the window in front when it comes. Their cost: while installed, every key and mouse event of the
  desktop passes through a few microseconds of Python (the window in front looked at, the kind appended,
  `CallNextHookEx`), plus the wait for Python's interpreter lock where another thread holds it (handed over every 5 ms);
  nothing at all while they are not installed.
* **Never read again, never sent, never exported.** The program never reads the folder afterwards; the offline guard
  holds as ever; an export of the books never includes it (`backup.NEVER_EXPORTED`; tested). The tools never open the
  kept pictures or texts: `tools/analysis_summary.py` reads `analysis.jsonl` and `input.jsonl` alone.
* Menu > Developer measuring > Open the folder, and Delete all sessions... (asked first; the session under way stays);
  `python tools/dev_measure.py list | delete NAME... | delete --all | open` does the same from a shell.
* `tools/standin_e2e.py --dev-measure` switches it on at the start with nothing asked (the stand-in's made-up pages
  only) and moves the session's folder into its `--out` folder. Its turns are posted to the stand-in, never typed, so
  the hooks see none of them and such a session has no turns to time (the summary says so).

## A setting in the Settings dialog

Settings... (`taslation/ui/dialogs/settings.py`) takes another part's setting in one line of `EXTRA_ROWS`:
`SettingRow(key, label, tip, section="window", choices=(), page=False)`, with *key* a field of `config.Settings`
(also in `taslation.toml.example`), *label* and *tip* in English with their 16 languages in
`taslation/locales/features/settings_dialog.py`, *section* "lettering" or "window" (the section labelled Dialogs),
*choices* `((value, label), ...)`
for a list instead of a checkbox, and *page* when a change must letter the page on show again. The row shows only
where `Settings` has the key, Save writes it into taslation.toml and sets it on the running program's settings at once
(`App._settings_saved`); the part reads `settings.<key>` whenever it acts. `tests/test_settings_rows.py` checks the
rows' languages.

## Other scripts

* `tools/make_sample_page.py` draws the synthetic test pages in `tests/fixtures/` (no real book is in the repository);
  `--layout edges` a page whose bubbles are cut by its four edges, for a case reproduced on the stand-in (`--pages`);
  `--layout pairs` bubbles joined in pairs, each drawn over the one before it (two tall narrow ones side by side, a
  narrow one over another's upper corner, over a side, over a foot; the lettering audit's layout 18 with its layers).
* `tools/fake_viewer.py` shows those pages in a window of its own, so the whole flow can be tried without a viewer.
* `tools/book_screens.py` draws a book's first five screens made up, as a browser-based reader shows them in a
  maximised window (the cover alone; a dark page beside a black one holding a plate; a colour spread with a column of
  squares; a grey page beside a black one holding a picture; a grey spread running off the window's foot, a bubble cut
  by the content's top), with glyphs of strokes or a font's made-up lines for lettering: shared by
  `tests/test_see_book_walk.py`, `tests/test_bookpage.py`, `tools/bookpage_eval.py` and the stand-in's scenario bw
  (`--out DIR` writes them as PNG); beside them a harder cover (`hard_cover`: a saturated picture, six pieces of
  large outlined lettering in several colours, a bubble) for `tests/test_page_budget.py`.
* `tools/page_area.py` prints what the page-area detector finds in a window, for tuning.
* `tools/room_eval.py` letters the regions of OpenMantra's pages (or of a book's dev snapshots, `--frames`) with
  canned English and counts, numbers only, the regions whose rooms or lettering run into each other's, fragments of
  one block of text read as several regions, and gold texts merged into one region or split over several; `--pictures`
  draws the worst cases and a sample of ordinary regions into a scratch folder, `--compare` the lettering sizes of two
  runs.
* `tools/premises_eval.py` measures the effect of the series sheet on the translations (`tools/premises_eval_set.json`); `--long-sheet 200` measures the entries the premises block cuts, block alone against those entries after the bubbles.
* `tools/hint_eval.py` measures whether PLaMo 3 Translate follows a region's hint for the model, its kind or its room put in its PFML3 ``context`` block, on lines written for the test (in several wordings, ``bare`` being the one the app sends; against the prompt without a hint; seeds 1 to 3; the answers kept in a JSON file to go on from).
* `tools/prompt_replay.py` replays OpenMantra's pages through PLaMo's way of translating page by page, and counts
  for every request whether its prompt extends the last request's prompt and answer, and
  where and why it parts from it (the context block, a joined run, a pair changed or gone, the glossary, a cut, a
  request beside the page, a line asked again), with the tokens that then have to be computed again, numbers only.
  A stand-in model answers with the gold English (no Ollama, about 30 s); `--answers live --url` asks a server of
  the developer's own instead and adds Ollama's own counters per reason (`--start-ollama PORT`: the server
  TASlation's own starter starts on a spare port, stopped at the end). `--warm` does after every page
  what the window does while the reader reads (`Pipeline.warm_soon`) and says whether the page requests' prompts
  are the very same with it and without it (their number and a digest of them in their order).
* `tools/make_icon.py` draws the window's icon with Pillow alone.
* `tools/demo_video.py` made a recording of a whole-book run (`docs/media/whole-book-demo.gif` by default; the README's
  recording until November 15, 2026): the real window, the real OCR and the real translator over OpenMantra pages in a
  stand-in viewer of its own, pictures of TASlation's own window only, a scratch state folder, no other window touched.
  From then to November 21, 2026 the README's recording, `docs/media/taslation-intro.gif`, was made with this tool's
  guard and scratch state by a longer script that is not in the repository; since then it is made by
  `tools/intro_video.py` (the next entry), the first time with version 0.9.0. Each of these recordings holds
  CC BY-NC 4.0 material. From version 0.9.4 to 1.0.1 the README showed a video instead (an attachment kept by GitHub)
  and the repository held no recording; since the one mode it holds the GIF `tools/intro_video.py` makes (the next
  entry). With the whole-book run gone (2026-11-22) this tool only says so and ends (exit code 2).
* `tools/intro_video.py` makes the README's introduction, `docs/media/taslation-intro.gif` (a dev tool, never part
  of a release; the repository holds that GIF again since the program's one mode). `record --out SCRATCH/intro.zip`
  is a run of `tools/standin_e2e.py` on a scenario of its own: the stand-in viewer on OpenMantra pages drawn sharp at
  once, the real program in English with its lettering over the stand-in and its two side panes, the translator's
  server started by TASlation's own starter on a port of its own (`--start-ollama`, 11435 by default), a scratch
  state; TASlation starts editing (`--editing`) and asks for the viewer (`--chooser`), the stand-in remembered in the
  scratch state as the viewer chosen before, so that the chooser comes over it with it preselected. It acts eight
  scenes - the viewer chooser answered through its own object, Reader mode checked, a page the stand-in turns by its
  own script filling in, the side panes, the right pane's foot, the list of languages opened and closed with no
  change, the pointer resting on a bubble past the hover delay (the original in its place, the bubble's block in the
  right pane), Reader mode unchecked with a box clicked (selected), double-clicked (the region editor, closed again),
  dragged and dragged back and its number plate clicked (the place entry, given up) - with a pointer of its own (the
  see-through window is told where it is: the real pointer never moves) and clicks and drags posted to TASlation's own
  windows only; nothing is sent to the stand-in or to any other window. The stand-in goes on monitor 2
  (`--standin-monitor`) at the top left of its work area: the tool refuses to start where a window of another program
  lies on that place, and gives the take up as soon as one meets the stand-in's window while it runs (every shown
  top-level window, looked at with every frame and four times a second, no title read). Nothing takes the foreground
  from another program's window: the stand-in's browser opens without taking it (as in every stand-in run: below),
  what TASlation would take it with acts only while one of ours is in front, Windows' lock on foreground changes is
  asked for, and a take in which the foreground came to ours from another program's is given up. Its frames are
  copies of the screen in the stand-in's client area, each kept only when no other program's window lies over the
  stand-in and, outside where TASlation's own windows draw, it shows the stand-in's own frame of that moment (as the
  stand-in run's pane shot is checked); a frame that fails is never kept, and six in a row stop the run with the
  recording deleted. It says how long the screen was in use. A recording keeps no page text. `render FILE --out GIF`
  makes a 960x620 GIF of about 30 to 60 s - a title card, the numbered scenes with the tool's pointer drawn in, a
  closing card - where git ignores it or outside the repository (it is copied to `docs/media` by hand), refuses one
  over 5 MB (`--allow-large`), with `--fit` takes the first of a few settings (fewer frames where only the picture
  changes, fewer colours, fewer frames a second) that keeps it within the size of the GIF it replaces, and deletes the
  recording once the GIF is written; `render --sample` renders made-up frames. The recording and the GIF hold CC BY-NC
  4.0 material. Each card line and step names the sentences of docs/MANUAL.md it follows, or is marked as the tool's
  own words; `tests/test_intro_video.py` fails when one of those sentences no longer stands word for word, so change
  the line with the document.
* `tools/judge_order_check.py` reads pages with each region judged as soon as it is read and with all of a unit's
  regions read first (`pipeline.JUDGE_AT_READ`), with one pipeline and the book's sizes put back between the two, and
  compares every field of every region, the progress told and the book's sizes after, counts only: the repository's
  test pages, `--sets openmantra` and `gold` (the dev snapshots that hold `ocr_gold.json`), `--detect on,off`;
  `--flag slants` compares the slants measured as each region's turn comes with all of a unit's measured first
  (`pipeline.SLANTS_AS_READ`) the same way.
* `tools/cached_turn_profile.py` times, stage by stage, a page whose translations are cached, from the settled frame to
  the page drawn, on a stand-in viewer in memory.
* `tools/standin_e2e.py` checks the real program end to end on a browser-type stand-in viewer, in its one mode (the
  lettering laid over the stand-in's own window, TASlation's own window hidden)
  (`tools/standin_viewer/`: a local page the browser shows in an app window of its own, with a scratch profile; it
  fetches nothing and turns its pages by its own script: soft first, spreads, black frames, a spinner, a band whose
  cells say the page). The window chooses that window alone (the others are not listed, a guard stops the run when
  any other is chosen), reads and translates with the real OCR and Ollama's default model (`--canned`: a made-up
  answerer in its place; the server at `--ollama-url`, 127.0.0.1:11435 by default - a second server of the
  developer's own -, or one TASlation's own starter starts, `--start-ollama PORT`; Ollama's usual port 11434, where
  the person's own server is likely to be, is refused by this tool and by `tools/promo_video.py` without
  `--usual-port`), and the tool writes numbers (the sharp frame to the first request, the first lettered
  bubble and the finished page; the requests sent for nothing, for frames that changed, with what they cost; the
  lines sent to the translator as they were read (`streamed_lines`: those sent early, those that stood and those
  taken back - a unit's first line among them - and why, the requests so thrown away, counted apart from those sent
  for nothing, how long a taken-back lettering stayed on show, and that nothing of one was in a page's lines or on
  show at its result: the runners' summary fails a run on that; `units_taken_back`: each unit that took a run back,
  its counts, why, what became of the regions of the first run taken back once the unit was read (`taken_back_as`)
  and the page jobs of its requests; `lines_held`, `held_ms`: the lines held back by a candidate
  not read yet or by the order foreseen, and how long after the rule before 2026-11-22 would have sent them;
  `order_ms`: what foreseeing a unit's order cost it, on the reading's thread); where each page job's time went
  (`stage_split`: among its stages the time between a spread's two units' translations and what the worker did in
  it - the wait for the unit read beside, `between_beside_wait`, the store, the order, the rest -, the model's idle
  time between the job's requests, `requests_idle`, and the slants the worker measured, `slants`, those before the
  first request apart; with `TASLATION_STAGE_TIMELINE` set each job's spans, the readers' reads with their device,
  and its requests, in ms from the job's start: times and labels only); the page jobs cancelled
  past their page
  (`jobs_cancelled_past_their_page`: the cancel after the result, the job's end after the cancel); jobs kept
  from a frame that was not the sharp one; jobs cancelled per scenario; stale pages; where the OCR ran; which capture
  gave the stand-in's frames, Windows.Graphics.Capture or PrintWindow where it gave none (`capture_route`); the pages the
  cache held as they were stored at another window size only, met right after a change of size or on a turn back, with
  the page units the cache gave and did not and the requests sent for them, a page alone and a page of a spread told
  apart; each page unit looked for in the cache, with the frame's size, the capture area and the distance of the page
  found and of the nearest one, and the capture areas in force; each look for a page the cache did not hold as found,
  as it reads at other sizes, with the readings it went through, their time and what they found; how long after a turn
  the page before stayed on the page area, and its lettering; how long lettering showed on a soft picture of the page, and how far the boxes of a page read from
  a soft frame lie from those its sharp frame gives, in pixels; for the pages the cache held, drawn soft first or sharp
  at once, when their lettering came after the turn, when the lettering read from the sharp frame did, and how often
  and how long lettering left the page and came back; each frame the window judged soft or sharp, by the page's own
  sharp picture and by the viewer's pictures of all pages, against what the stand-in drew, `soft_looks`) and pictures of TASlation's own window to the `--out`
  folder (one of them 3 s after each change of the stand-in's size, its page at the new size; there too
  `stacks.txt` when a request to the translator stays under way 20 s without going out, or 60 s at all, or the Tk
  thread is silent 20 s - each thread's stack, its files, lines and functions only, with what the server answers just
  then to /api/version and /api/ps -, the report's `no_answer` (each line of the rule for a request without an
  answer and of the backlog's pause for it, a silence with what the server answered just then), the report's
  `frame_stalls` (a sharp page the stand-in kept 6 s that none of the window's frames showed while it went on taking
  them: what covered the stand-in by program file name, the window's capture session, the first frame of a session of
  the tool's own, the seconds since anyone's input), `server_priority` (the server TASlation started lowered for the
  backlog's work and set back, how many of the backlog's requests were computed low, and every other request
  computed while it was low - a failure in `.github/gpu-checks/summarise.py`) and `input_spells` (when the computer
  got input from anyone: a run
  with a person at the machine, whose windows may cover the stand-in, is told apart), the app's log in `app_log/` when
  the run had a stop, a stall or a request without an answer (unless it holds Japanese script), `--cover
  SEGMENT:AT:FOR` laying a window of the tool's own over the stand-in on purpose (the stand-in, a browser, stops
  drawing under it, as under any window that hides it wholly), `--standin-draws-covered` keeping it drawing under
  any window (a run that does not depend on the windows of a person at the machine), and with
  `--start-ollama` the server's own log `ollama_server.log`,
  at Ollama's default level, with no prompt and no answer in it),
  each with the part of the frame the page view draws against the page the stand-in drew there (rows of the browser's
  title bar and of the band drawn, the ground round the page) and the reading's page units in the capture area and
  outside it, with their fingerprints' distance; no key or click is sent, the state folder is a scratch one, and the
  profile, the state and the model it loaded are gone at the end. Scenarios by `--scenario` (all by default: c, a,
  b, d, e, x and f2): c, the turns while the model loads; a, slow reading; b, fast flipping; d, black flashes and
  spinners; e, turning back to cached pages; x, a request cancelled in flight at the translator (pages of one or two
  lines of text, by the annotation's counts, drawn soft for `--cancel-soft-ms` at half resolution, so that the window
  reads the soft frame and asks on it before the sharp one comes; needs the dataset); f2, the narrow window; f3, never
  in all, a's slow reading in that narrow window (nine screens of one page where f2 has two; after f2 when both are
  asked, else the stand-in made narrow first); s, never in all and refused with `--standin-profile`, the page pressed
  and slid along with the pointer, as a viewer that moves the whole page with a drag does (the stand-in's steps `rN`
  and `lN` slide it to the right or left edge over N ms, `rN-D` only D CSS px; `o` lets go: at the edge the next or
  the previous screen, else the page snaps back; `oN` draws that answer N ms after the release, the page left as it
  was held meanwhile; each frame of a slide has its cells say "slide"): to the edge and let go, 150 px and let go -
  the page snapped back 400 ms after the release, as a viewer on a busy computer answers it (the job of the page on
  show must go on: `live.RELEASE_ANSWER_MS`) -, to the other edge, and a slow slide held long. The tool's own pointer and button follow
  each slide (`SeeWatch._follow_slides`: the window reads them, the real ones never move), and on the hold of the
  slide to the left the press is moved over the left pane's lettering plate and let go there (posted to TASlation's
  own pane). The report's `see_through.slides` gives per slide the panes' hidden spells from the press and why, the
  panes' draws while pressed, the patches of slide frames shown after the release and the plate's probe (nothing may
  fire, nothing stay stuck), and the jobs, requests and pictures made of slide frames (none should be). The
  scenarios of TASlation's own window went with it in 2.0.0 (r and t
  with t2, its full screen in the two roles; o, over the book; z, its text size at 150 %; f, its dark theme). And k, never in all: on pages no scenario before turned to, `--k-turns` pages (20) flipped past at 0.5,
  1 and 2 s a page (k5, k1, k2; `k` is the three, each once the backlog of the one before has nothing left; k3, 3 s
  a page, only by its name), then a
  jump back to the first of them and `--k-read` of them read at `--k-read-ms` a page (8 s); the tool tells, per pace,
  how long each page flipped past had its sharp frame on show and whether the backlog caught it, how each page read
  back began (wholly from the cache, from what the backlog had read, or read again on show and why: another size, not
  caught, a soft gate, its entry still a frame), its first lettered bubble, what a turn to the page being worked on
  waited for the worker, how long the backlog held each frame and the most it held, its steps and their requests,
  the backlog's first step after a page job that showed its page (from the page shown and from the job's end) and
  how long each such job went on after showing its page; and for the run (`told`) the screens left told at work at
  the end (`left_working`: none should be) and how often a stage told done was told at work again.
  `--k-soft off` draws every page sharp at once, `--k-narrow` places the stand-in at the narrow size first (single
  pages), `--k-backlog off` catches nothing (the baseline of
  the same turns), `--k-stay-ms` keeps the last page
  flipped to that long (a page read afresh on show while the pages turned past wait); `--ocr-runs-on` and
  `--ollama-num-gpu` set those settings (`CUDA_VISIBLE_DEVICES=-1 --ocr-runs-on cpu --ollama-num-gpu 0` is a computer
  without a GPU). The report gives the event pump's times (`poll_events_ms`). `--wait-done CAP_S` keeps each scenario's meaning on a slower computer (GitHub's
  runners): each rest of a, d, e, x, f2 and f3, the one at a scenario's end too, is held until the page on
  show is finished, or the window rests with it unfinished, or CAP_S have passed (the stand-in waits at an `hN` step
  of its script until the tool's word), and x's soft frames stay on show until the window has asked on them (15 s and
  CAP_S at most); the report keeps the holds and their reasons (`waits`). Without it the script and the stand-in's
  control file are the same as ever. A turn's rest ends at the next turn or where the tool changed the window for the
  next scenario (the stand-in's size: the report's
  `driver_acts`), whichever comes first, and the page at rest is what the window showed then; a job cancelled as the
  window took its page at a new size of the stand-in is not one cancelled with its page on show (`resized_away`). The
  tool does not start while another TASlation runs on the computer - a person's own window (`pythonw.exe -m taslation
  gui`), or another run of it, of `intro_video.py` or `promo_video.py` recording, or of `screens_read.py`: one line
  and exit code 3, nothing started (`standin_viewer.refuse_beside_running`; those tools do the same) -, unless told to
  with `--beside-a-running-one`. The tool never changes the foreground (but between its own windows with `--start-behind` and `--chooser`: below). The
  stand-in's browser opens without taking it either: started minimised and not activated (STARTUPINFO, which Chrome
  does not take for its first window), with Windows' lock on foreground changes set while its window comes
  (`standin_viewer.lock_foreground`: a change is possible only once the person has given no input for a while, and
  then the tool may set the lock; it is lifted as the window is shown, at the close, or by any key or click of the
  person's), its window then shown without activation; should it take the foreground all the same, it is minimised
  and shown again without activation (Windows hands the foreground to the window behind). A window that does not
  come within 20 s (on the runners, now and then) is waited for on, up to 45 s, while the browser still gets on (a
  process or a window more or less in the last 10 s); then the browser is closed and started once more on a profile
  of its own, waited for 45 s, before the run gives up. The report's `browser_start` says what came
  (`took_the_foreground`, where, whether the lock was taken; `window_s`, the seconds from the browser's start to its
  window, `own_window_s` to its first window titled or not, the processes then and a `timeline` of their changes;
  `no_window`: what was there when it did not come - processes, its own windows' classes and titles, its log's
  severities and last error lines, the token and the home folder left out; `started_again`: why, after how long,
  and the first start's facts; `program`: the browser's version folders and an update pending), and a job's summary
  says it in a line (a window later than 10 s, or a second start, among the speed notes). A run thus starts with
  the person's window in front: whatever needs the stand-in in front gets it where TASlation gives the viewer the
  foreground (a region editor's closing) or by the tool's guarded steps below. The run's end waits for a scene the
  see-through watch is acting (`SeeWatch.acting`: the pointer on a bubble, editing's clicks and drags, Add area), so that
  its measures are not cut.
  `--scale 1.5` draws the stand-in as on a display
  of that scale (the browser's `--force-device-scale-factor`) and sets TASlation's text size (its dialogs') to it; no system setting
  changes. OpenMantra pages from the datasets folder, or `--synthetic`. The window runs with the app's defaults, so on
  a computer with a CUDA GPU and both page models installed it loads the layout model as well as LaMa (since 0.2.0):
  its times are not comparable with runs of earlier versions there.
  `--soft-first off` makes the stand-in draw every turn sharp at once and nothing after it, so that no wait of the
  viewer's is in what is timed: the published timing figures (the README's and the installation guide's table of a
  screen's time and the first bubble) are measured with it, `--scenario a,f2 --wait-done 120` on a quiet computer
  (screens of two pages from a, of one page from f2; `a,f2,f3` adds f3's nine), from the report's `timing`: per screen of one page and of
  two, over the turns rested on to a page the cache did not hold, the first lettered bubble and the finished page from
  the turn and from the sharp picture's draw (the same in this mode), the first request, and the way from the turn to
  the finishing job's start (the window's first capture, its first capture of the sharp picture, from there to the
  job, the job's wait for its worker). The window starts in a process of its own on a scratch state and a browser
  window it has never seen, and what it learns of a viewer that draws soft first is held for that window in memory
  only; `timing` says that the stand-in drew nothing soft and how often the window learnt it all the same (never, or
  the figures are not sharp mode's). x needs soft frames: it is left out of all and refused by name. The correctness
  runs, here and on the runners (`.github/gpu-checks`), keep the default, `on`.
  `--standin-slider 1` gives the stand-in a page slider under its page (`slider=1` in its page's query; off by default,
  so the scenarios and their figures stay as they were; `2` also draws the pages as the knob moves): a bar with a
  round knob, the first page at its right end, as a web reader's slider takes the pointer - the canvas listens to
  `pointerdown`, `pointermove` (its coalesced events counted), `pointerup`, `pointercancel` and `lostpointercapture`,
  and to the DOM's `click`; a press on the knob or the bar takes the pointer (`setPointerCapture`), the release goes
  to the page at the knob's place (a press on the bar without a move jumps there), a cancel or a lost capture goes
  back to the page it came from. Its log says each jump (`ev=jump`: from, to, by drag or click, the moves), every
  press elsewhere and every click. The page area leaves the bar out (`fingerprint.page_box`: background lies between
  it and the page) and the reading finds no page unit in it.
  `--standin-profile dark|light` has the stand-in behave as one of two kinds of web viewer, read from the owner's
  screen recordings of two real ones (30 fps, 1920 x 1080); only the behaviour is copied, never the look: no name,
  mark, colour or text of theirs, the sample pages only. Off by default, so every scenario and its figures stay as
  they were. In both the band stands for the browser's own tabs and address bar and is drawn only while the window
  does not fill the screen; under it the viewer's area, the page fitted to its height, a spread centred on the ground
  (1918 x 946 in a window: the spread about 1332 wide, about 294 of ground each side; the browser's full screen
  1920 x 1080: about 1524 and 198), the cover and a last page alone and centred; a turn drawn at once (no slide, no
  fade; the soft first only with `--soft-first on`, off by default with a profile); bars that lie OVER the page (it
  is neither moved nor resized) and fade in and out over 0.2 s; a slider in the bottom bar, right to left, that takes
  a drag of the knob and a click on the bar. The browser's own full-screen notice is not drawn (it comes by itself
  in a real browser): a scenario in the full screen has to expect it.
  `dark`: black ground; a white top bar of 94 px (a back mark, a mark in the middle, three controls; a title and a
  button under them) and a white bottom bar of 56 px (the slider's line with a knob and a few dots, "page/pages,
  percent" under it); white tabs with an arrow at the very left and right edges, 32 x 70, shown on a pointer move and
  gone 3 s later, apart from the bars, none for back on the first screen; a jump by the slider draws the viewer's
  area black with a small spinner for 0.5 to 1.1 s (as measured: 1.03, 0.73, 1.10, 0.53 s), the bars staying over it,
  and once in four jumps (seeded; seen once) one page of the spread first and the other 2 s later, its half black; a
  resize (the full screen in or out) the same black for 0.4 to 0.5 s. The bars come while the pointer is in the top
  bar's band or the bottom bar's (`bars=edge`) and go a second after it leaves - the owner's recollection ("probably"),
  not measured; a key turn hides them (seen once). Turns: the arrow keys, the side arrows, and a click anywhere on the
  ground beside the page (left of it the next page, right of it back; full height, but the bars while shown), as far
  as the owner remembers.
  `light`: white ground; see-through grey bars of 40 px (small marks and the title in the top one; a zoom figure and
  two zoom marks, the slider in the middle and "page/pages" beside it in the bottom one), shown on any pointer move
  and gone 3 s after the last (`bars=move`); round dark arrows of 30 px set 180 px in from the viewer's edges, shown
  always while the page can be turned that way; no black at a jump or a resize; a jump draws the target washed out
  and soft for 0.2 s, then sharp (`preview=1`; the 1.7 s picture seen once is not built). The second recording was a
  novel: no page geometry is taken from it, so the geometry is the first one's.
  Every part has its own name, given by `--standin-option NAME=VALUE` (again for more; `profile=` and the same names
  in the page's query): `ground` black|white, `cover` 1|0, `bars` none|edge|click|move, `bar_top`, `bar_bottom` (px),
  `bar_style` solid|glass, `bar_fade_ms`, `bar_hide_ms` (empty: edge 1000, move 3000), `bar_key_hide`, `arrows`
  none|edge|inset, `arrow_show` move|always, `arrow_hide_ms`, `arrow_inset` (px), `page_clicks` (a click on the page's
  left or right third turns it), `ground_clicks`, `jump` plain|spinner, `jump_ms` (A-B), `jump_half` (a share),
  `half_ms`, `preview` 1|0, `preview_ms`, `resize` plain|spinner, `resize_ms` (A-B), `focus_black` (the black of the
  focus, off with a profile), `counter` percent|pages. Not known, so an option with a default chosen here: whether a
  click ON the page turns it (`page_clicks`: off for dark, on for light), the clicks on the ground in light (off),
  whether a key hides light's bars (no), how long the bars and the arrows stay (above), whether the arrows fade (they
  do not), the arrows' inset in light (180 px, from the novel's recording: to be checked on a manga). The page says
  each event with its time: `turn` with its cause (`by=key|arrow|ground|page|script`) and a click's place, `key`,
  `bars`/`bars_done`, `arrows`, `spinner` (`why=jump|resize`), `preview`, `draw` (`kind=half|preview`, both coded
  soft for the e2e tool's decoder; the black with the spinner decodes as `spinner`, or black in the full screen),
  `size` (`full=`, `band=`), `pointer` and `click`, and its own frame times: `anim` as a bar fade or a spinner ends
  (its frames, and the median, p90 and longest gap between them) and `painted` after every turn's draw, also
  without a profile (until the frame after the one that showed it). Its script has `vN` (the bars for N ms) and `a` (the side arrows),
  and its n and p hide the bars as a key does. Scenario q (by its name only) is written for a profile: turns, two
  jumps, the bars at rest and just after a turn, the arrows.
  `tools/standin_selfcheck.py --out SCRATCH` drives the stand-in alone, no TASlation, in a headless browser (no
  window on the screen, no input of the system's: the browser's debugging protocol on a loopback port gives the
  page trusted pointer and key events, sets its window to 1918 x (946 + band) and its full screen to 1920 x 1080, and
  takes its pictures): in each profile, and then with a few parts switched, a turn by key, by the side arrow and by a
  click on the ground or the page, the bars in and out, a drag of the knob and a click on the bar (the spinner, the
  washed-out picture), the full screen and back. It prints the page's log and PASS or FAIL for each check, with what
  the e2e tool's decoder reads in each picture (into SCRATCH/shots: the sample pages, scratch only).
  The window is in its one mode, see-through (the lettering laid over the viewer's own window by a click-through
  window of TASlation's, `capture/seethrough.py`; `--see-indicators off` with the indicators' pane switched off,
  `Settings.see_through_indicators`; the option `--see-through` of 1.0.1 went with the setting), and
  `tools/standin_seethrough.py` watches it from the tool's own thread, nothing sent to any window: the time from the
  stand-in's change of screen (its spinner, its washed-out picture or its draw) to the see-through window showing none
  of the old page's patches, from its own notes; which window `WindowFromPoint` gives on the patches shown, on the
  page and on the ground (always the stand-in's); who was in front, and each change, with the activations of
  TASlation's own windows from before its window is made (a CBT hook of the tool's Tk thread that refuses none: the
  window starts with a decoy as Tk's first window, `ui.seethrough.quiet_start`, so 0 is expected) and how its main
  window was on the screen once a second (`hidden_window`: it is never on the screen - its handle
  read with `capture.seethrough.window_facts`, "off" when it lies on no monitor, at alpha 0, an application's window
  with its taskbar button (no tool window, owned by none) titled "TASlation" and not minimised, "not shown" before Tk
  first shows it; once shown it stays shown in Windows' sense, since Tk's dialogs need a master in its normal state -
  every look "off" (or "not shown") is expected, with what `keep_hidden` put back, how often the foreground went
  back to the viewer (and how often a dialog's closing gave it back at once, `closing_gave_back`), the log of the
  foreground's counts and newest lines (`foreground`, `foreground_lines`: kinds only, a line to a window of TASlation's
  ending in what it did just before; `foreground_notes` the changes the hook brought, `foreground_polled` those first
  seen at a tick; `guarded`: how often the guard of the keys gave the foreground back, by what was in front, and
  `woke`: how often a press on the lettering or a pane made the viewer the foreground window), what the window being
  in front gave instead (`front`: a dialog brought up, the chooser, the
  Menu at the pointer, the viewer - after a click on its taskbar button, which only the owner's own click makes),
  how many dialogs of the process were on a monitor at each look, and when the viewer chooser and the banner's
  dialog came and went). The tools choose the stand-in with `App(settings, window_query=browser.token, ...)`, as
  `gui --window` does: a viewer named that way brings no viewer chooser (the dialog the person chooses the viewer in
  at every start), so no dialog of TASlation's takes the foreground in a tool's run (but with `--chooser`: below).
  `--no-viewer-s S` gives the
  window no viewer to find for its first S seconds (the window looks for the stand-in named every 2 s and chooses it
  once it is listed: `run.no_viewer`; no chooser comes meanwhile), and `--book-asked` starts it with a name that names no book, so that Auto's first page
  asks it in the start dialog, which the driver answers 1.5 s after it is on the screen through the dialog's own
  object (`run.book_asked`: whether it was on a monitor, topmost, and whether it had the foreground).
  `--start-behind MODE` has the stand-in out of sight before the window is made, as a viewer behind the reader's
  other windows is when TASlation starts: covered by a plain window of a process of its own (`tools/standin_cover.py`,
  another program's to the window, which tells its own windows by the process) over all of it (`cover`), its left
  half (`part`), its monitor's work area (`max`, as a maximised window), or over all of it and in front (`front`: the
  foreground taken from the stand-in only), or minimised (`minimised`); `--behind-before-s S` so long first.
  `--behind-s S` after the window chose it, it is back in sight (`--behind-end close`: the cover goes; `raise`: the
  stand-in put over the cover and given the foreground as a click on it does, only while the stand-in, the cover or
  TASlation is in front - over a window the person uses meanwhile nothing is raised, the cover only goes). Scenario
  `h` (by its name only) is two turns once it is back. `--chooser` names no viewer: the viewer chooser comes and the
  driver answers it through its own object, first giving it the foreground (only while the stand-in or the cover is
  in front). Scenario `fg` (by its name only) is the start and one turn, then 20 s with nothing done, for where the
  keys are (`run.keys`, `keys_report`): from KEYS_GRACE_MS after the start (the chooser answered, or the window
  ready) and after each turn's first frame until the next, the windows that were in front (looked at every 10 ms)
  and the longest spell of the stand-in in front without its page having the keys (the stand-in's page says so by
  itself every KEYS_LOOK_MS, `keys on=`: nothing is pressed for it); a moment is ok when only the stand-in, a dialog
  or a menu of TASlation's - or anything while a dialog of TASlation's is on the screen - was in front and the page
  never without its keys for KEYS_LAG_MS. `--standin-bars-held MS` has a stand-in with a profile come with its bars up for MS ms (with
  `--standin-option bar_key_hide=0` its turns leave them up). The side panes are looked at every 0.25 s (wanted,
  shown, visible, topmost, above the stand-in; their ground and the room beside the page; the lettering; the windows
  over the viewer; who is in front) and `run.behind` keeps them as they changed, with the time from back in sight to
  both panes on the screen (`panes_back_ms`). These are the only times the tool moves the foreground, between its own
  windows. `--see-edit`
  keeps the book's role as editing, the program's default (every other run sets Reader mode), so that the left
  pane's Reader mode is off from the start (`ui/see_edit.py`: the overlay takes the mouse over the whole client area,
  the viewer the keys alone), and from some 14 s in measures it in place of the patch under the pointer (`edit`:
  messages POSTED to TASlation's own windows, no input of the system's, its look at the physical button left out for
  them): on a region of the page on show, whether the window takes the mouse, which window `WindowFromPoint` gives
  on the box, beside every box and at the client area's bottom corner (the see-through window each time) and just
  above the client area (the stand-in's frame), the pointer on it (outlined; after the hover delay its patches give
  way to the original, the others stay; the right pane holds the bubble's block), a click (`select`: the ms until the
  region is chosen, in the window and in the marks, and no editor comes), a double click - two clicks posted at once,
  past the system's double-click time after the first - (the ms until the region editor is on the screen, beside the
  box or over it, on the box's monitor,
  whether it took the keys and holds that region; a WM_CLOSE posted to it, and the ms until the stand-in is in front
  again), a drag of the box by 24 x 12 px (handed over as a move, outlined at its new place meanwhile, the ms until
  the page's marks have it there, the fewest patches shown meanwhile) and one of its bottom right corner (a resize);
  then a click on the number plate of the last region of the page's first unit (handed over as a "plate", the ms until the
  place entry shows and has the keys), "1" and Enter posted to the entry's own window (the ms until it is gone and the
  stand-in is in front again, the job and its end; whether the region is first now, the others in their order, the
  history's newest change an "order", the marks with its box first), a click on the empty ground (a "ground": no
  editor, no change, nothing chosen after it) and a rectangle drawn there (a "draw": a region of the reader's at the
  rectangle, and the others still in the order typed); last, that region chosen by a click and the Delete key's
  WM_HOTKEY POSTED to the lettering's own window (`delete`: the ms until the key is TASlation's, until the region is
  dropped, the change in the history, and until the key is let go of after); then, with another program in front - a
  small window of the tool's own over a fifth of the stand-in (`tools/standin_cover.py --part 0.2`, its word "front"
  made the foreground window only while the stand-in has it) -, a press and its release POSTED to the lettering's
  window on a box and on the empty ground (`wake`: per spot whether the other program was in front, the ms until the
  stand-in is the window in front, whether the press was handed over and as what - the one on the ground as nothing -,
  the layer's "woke" notes, and whether the stand-in's page had the keys after it). Meanwhile what the stand-in's page said of the pointer (`standin_said_meanwhile`: bars,
  presses, clicks - none expected, the whole client area being the overlay's - and its turns). In every run the
  right pane's foot rows are looked at once a second (`panes.foot`: their tops in the client area, one per frame
  size, `constant`). `--editing` keeps the role as editing as `--see-edit` does, but does nothing on the page (the
  patch under the pointer measured as in Reader mode): for timing runs of editing against Reader mode (the report's
  `role_kept`). With `--see-edit` or `--see-add` the measure is on the first page done and the first scenario is
  released only once it is over (`SeeWatch.scene_pending`), so best with scenario `g`; `--see-edit` runs on the
  runners only (the group g-see-edit), its region editor taking the keys from whatever window is in front.
  In every run the page on show's lettered regions whose patch did not show are counted once a second
  (`run.see_through.unshown`, from `ui.seethrough.unshown_tick`; not by a look the window made before the page's
  newest patches reached it, `SeeThrough.presented`): per page the looks, the regions' boxes, the kinds
  summed over the looks - "no match" (the frame on show is not the page read: its distance over the limit), "bars" (a
  bar of the viewer's over it or by it), "covered", "no patch", ... -, those of the last look with the page's distance
  against the limit and the rows of the bars; "hover" and "original" are the pointer's and the editor's doing,
  `pages_with_unmeant` counts the pages where any other kind was seen (must be 0). `--pages A.png,B.png` shows
  made-up pages of the developer's instead (`tools/make_sample_page.py --layout edges`: bubbles cut by the page's
  four edges, their text 5 px from it), and `--standin-option band_line_ms=700` (a profile's) has the band's line
  just over the page drawn in another shade every 700 ms, the page as it is. With `--standin-profile dark` and
  scenario `f2` on the edge pages, the bubble touching the page's top was "differs:top" on 4 pages when each patch
  was compared by its own margin, and every region shown after.
  `--see-add` measures adding text areas in place of both (`add`; editing with `--see-edit`, Reader mode without; best with
  scenario `g`, one page held long): once a page is done and on show, the left pane's Add area and the Insert key
  (its WM_HOTKEY POSTED to the lettering's own window: no key of the system's is pressed), each followed by a
  rectangle dragged on the page's empty space - the ms until the row shows pressed and the whole page takes the mouse,
  which window `WindowFromPoint` gives there, the drag handed over as an "add", the ms until the page has a region of
  the reader's there, and in Reader mode until every click is the viewer's again -, then each way of giving it up (the
  row again, the key again, a right click); meanwhile who is in front every 50 ms against whether the key is held
  (read only: the tool moves no foreground) and the hot key's registrations, releases, failures and presses
  (`SeeThrough.counts`);
  each time the
  bars went from a page read under
  them, the pages carried over to the frame without them and the bubbles left out (`carries`: those cut by a bar,
  read and asked for again); the stand-in's frames a second
  while its bars fade or its spinner turns; the process's CPU at rest and while following; what the run
  cost (`cost`: the working set, the CPU of the stand-in's processes together - its sandboxed ones too, read with
  `NtQuerySystemInformation` -, the GPU memory of this process and of the stand-in's from Windows' own counter, and
  PyTorch's peak); the stand-in's own frame times (`viewer_frames`: its `anim` and `painted` lines, and each change's
  draw to the first frame captured after it); the Tk thread's steps (`tk_steps`: see-through mode's tick, the
  patches handed over - `seethrough.make_patches` itself runs on the patch thread, `ui.seethrough.Patcher`, and is
  timed in `pipeline` as `make_patches_ms` -, the panes' rows, sizes and pictures, the hidden window's redisplay and its canvas' picture, which
  draw nothing on the screen - each call's ms, and the per cent of a processor each took at rest, while a job
  ran and while following); each change of screen's first patches and whole page over the viewer (`on_screen`); and, from the
  see-through window's notes, why it hid what it showed and the page's distance it decided by at each new frame
  (`distances`: those of the frames shown and the nearest of the frames hidden; `seethrough.PAGE_TOL` lies between
  them). The side panes (`taslation/panes.py`, at the capture area's two outer edges or nearer the page, 300 px at
  the most from the widest page seen at the frame's size) are watched once a second (`panes`): shown or hidden with
  a single page or a spread, the most px each shared with the page box (0 expected), their gaps to it (`gaps_px`:
  beside a single page after a spread as far as the spread left them), their px to their edge of the area (8 at
  100 % where the page leaves that near enough), their columns in the client (the same with a single page and a
  spread once a spread was seen; one move at the first spread after a single page) and their sizes, and which
  window `WindowFromPoint` gives on the right pane (the stand-in: click-through), on a control of the left one (the
  pane) and between two of its rows (the stand-in); some 8 s in,
  the lettering's switch on the left pane is clicked twice by a press and a release POSTED to the pane's own window
  (no input of the system's: the lettering off and on again), with the time until it changed and the window in front
  looked at every 5 ms meanwhile (the stand-in throughout). The see-through window's reading of the pointer is the
  tool's for the whole run (`capture.seethrough.cursor_pos` put in its place: none, so the real pointer, wherever it
  rests, changes nothing; the tool never moves it); some 14 s in, it is put on a patch shown and off it again five
  times (`hover`: the ms until the patch is gone - once the pointer has rested `hover_delay_ms` on it, `delay_ms` -
  and until it is back, the other patches staying, the ms until the right pane holds the bubble's block, and whether
  the block stays once the pointer has left the patch) and then at the edge of a patch with no other one near that
  side (4 px off hides it, 10 px off keeps it hidden, 12 px off shows it again, 5 px off keeps it shown, 4 px off
  hides it again, at 100 %; each point held 0.3 s and the delay). `--see-pane-shot` keeps one copy of the
  stand-in's place on the screen the first time both panes show with a spread whose page is done and the copy shows
  nothing of another program's (outside where TASlation's windows draw it must be the viewer's own frame: a
  notification lies in a band of the window order that `cover_rects` does not walk; else put off to a later look,
  `shot_put_off`, or, where those pixels lie in the bottom third only, cut 32 px above them with both panes whole and
  the rest looked at again pixel by pixel but for an 8 px rim, `shot_rows_cut`) (SCRATCH/shots: a sample page, delete it after). `--see-truth` adds copies of the
  stand-in's place on the screen every 33 ms, in memory, checked for patches
  of another page than the one the copy shows (an old patch counts when its lettering's ink is on the screen and not
  in the viewer's own frame of that moment) and for how the page's own patches lie (0 px off at 100 %); two of them,
  of a page lettered in full, go into SCRATCH/shots (the sample pages: delete them after). `--standin-size WxH` gives
  the stand-in's window another size (1904x1024 for a 1920 x 1080 screen) and `--standin-full-screen` starts it in
  the browser's own full screen (the reader's area then the whole frame). `--standin-monitor N` starts the stand-in
  at the top left of monitor N's work area (1 the primary, the default; the others left to right, then top to
  bottom) and `--standin-maximised` maximised there (refused on the primary: a run never covers the person's main
  screen). Two scenarios, never in all, take the stand-in round the monitors as they are - no display setting is
  changed (`tools/standin_monitors.py`): m, the window where it starts (m0), moved to the other monitor (m1), with its
  middle on the edge the two share (m2), maximised on the second (m3) and back where it started (m4), each place
  with every dialog and menu opened through its own object and measured (the viewer chooser, the region editor,
  Settings, the Menu and the language list, the GPU box, the legal notice, the book-name dialog, a plate's place
  entry: the monitor each lies on against the viewer's, the scale it took), the foreground locked meanwhile and who
  is in front read before and after each; and resize, the window resized as a drag of its edge gives it (the tool's
  own button held from before its first size to after its last, 45 sizes over 1.5 s): narrower (r1; with
  `--editing` the region editor open on the page's first region), wider (r2), taller (r3), by its corner to too little
  room for the panes beside a spread (r4, then the Menu from a click on the taskbar button, `seethrough.front_tick`),
  and without a button half the screen (r5), maximised (r6), restored (r7) and by its corner (r8). A sampler looks
  at the stand-in and TASlation's windows every 50 ms (15 ms while the window changes); the report's
  `run.monitors` gives per step the lettering's offset from the client area and its looks at a stale place or
  scale (how long after the look that saw the client so, with patches on show or the editing ground alone), the
  panes and why each was hidden (no ground yet, no room, off the screen, covered by a window above the viewer such
  as the region editor, the viewer sized with the button held on its border), the scales, the hidden root's monitor; per resize the lettering hidden and back at the new
  size, the jobs started while the button was held and on the sizes between, the capture area found again, the
  marks, an open editor's place and its region carried to the page at the new size, and a timeline (numbers only);
  the hover on the stand-in's monitor; and how far a region read at one size lies from the same region read at
  another (`region_fit`). The tab scenarios, never in all and by their names only ("tab" asks for tab1-tab6), give
  the stand-in's browser window a second tab through the page's own script - no key, no click (standin.html's "the
  tabs": the window's title is the active tab's, its frames that tab's page, the band stays; the other tab a plain
  page with a neutral title or one of made-up Japanese lines with a made-up Japanese title): another tab shown and
  the book's again (tab1, tab2 the Japanese one), the other tab closed (tab3), shown 0.7 s into the page's job (tab4),
  the titles late - the other tab's 0.4 s after its page, the book's 0.4 s before its page - (tab5), and the book's
  tab moved out into a window of its own (tab6, always last: a second browser of the same program on a throwaway
  profile, opened at the start right behind the first and covered by it - a browser's window opened later in a run,
  or restored from minimised, took the foreground -, drawing all the same - its browser's occlusion tracking off, as
  `--standin-draws-covered` has it: hidden from its start, it was taken for a window out of sight even once raised,
  its page went on minutes late and no frame of it came -, and brought above it without activation at the move).
  `--standin-start-tab plain|japanese` starts the window with the other tab on show (with tab0, which brings the
  book's tab back after 3 s; with `--chooser` the chooser is answered while it shows: the window picked on trial
  with that tab, whose title is then the one chosen - the right pane's lines of the pick and when the one that the
  tab shows no page of a book came in `run.tabs.pick`, the frames' verdicts in `run.tabs.tk_rows` -, the book's tab
  back being another tab to it). `run.tabs`
  (`tools/standin_tabs.py`) gives per spell away from the book's tab what was captured, read, asked, looked up,
  learned and said while it lasted, the lettering's, the editing ground's and the mouse's looks over the other tab
  (and the last of the lettering and of the mouse taken there, in ms after its title came; a look lies on the window
  whose client area's origin is the lettering's, the book's own window lying within the first one's place), the
  panes, the right pane's line, the window followed, and the ms from the book's page drawn again to the panes and to
  the lettering (tab6: to the book's own window followed, and lettered there).
* `tools/promo_video.py` makes short videos of the time from a page turn to the lettered page. `record` pictures
  TASlation's own window, so it runs only a package before 2.0.0 (`--package` another checkout's; from 2.0.0 on the
  window is hidden and such a package, this checkout's too, is refused before anything starts): the real
  window in English, page by page, over OpenMantra pages on the browser-type stand-in viewer (the guard, the scratch
  state and the offline guard of the two tools above; no key or click is sent) and starts only once the model is
  loaded and a page that is not shown has been translated; then it turns N pages at a set pace and keeps pictures of
  TASlation's own window, each with its time, in a recording file (`--ollama` another server on this computer,
  `--package` another checkout of the package, `--label` for each; `--start-ollama PORT` with
  `--ollama-window-cache` and `--ocr-runs-on`: the window's own starter starts Ollama on a spare port, as
  `standin_e2e.py --start-ollama` does, and the recording keeps what it chose and where the OCR readers read while
  the pictures were taken). `render` makes a video of one recording or two
  side by side at real speed: only a pause between pages may be shortened, and the caption says so; per page a
  stopwatch from the turn to the last bubble lettered and the count of bubbles lettered, both sides starting each
  page together; title and end cards; the sample pages' credit on every frame. MP4 (H.264 by Media Foundation through
  OpenCV, read back to check) or else a GIF of at most 15 MB. `info` prints a recording's pages and times; `sample`
  renders made-up frames to check the layout. The videos go to `promo/` (listed in `.git/info/exclude`: never
  committed, never shipped) or another folder git ignores; recordings go to a scratch folder outside the repository.
  The start can be recorded too: `record --from-start` takes pictures from the window's first one on and times the
  page the stand-in shows at the launch from the window's appearance (its first picture not of one colour) to its
  first and last bubble (`--turns 0`: that page alone); `record --turn-at-ready` turns the stand-in's page right
  after the window has handled its "ready" event and times that turn as any other. The window opens at its recorded size and place
  from its first picture. `render` then starts both sides' clocks at the appearance (from the start) or at the turn
  (at ready, each window shown from its appearance), adds the first bubble's time and the start's own clock to each
  side, and shows the quiet stretch of the start `--start-speed` times faster (4 by default, 1 in full) with a badge
  ("x4") on the pictures and the caption saying so; the clocks show real seconds throughout.

## The README and the manual

`README.md`, `docs/MANUAL.md`, `docs/INSTALL.md` and `docs/LEGAL.md` are in English, for the public repository;
`README.ja.md`, `docs/MANUAL.ja.md`, `docs/INSTALL.ja.md` and `docs/LEGAL.ja.md` are the Japanese originals, and the English says that the Japanese prevails where the two differ. Each file links to the
other in its first lines. A change goes into the Japanese text and the English one together, in the same commit: the
same headings in the same order, the same tables, commands, file names, numbers and caveats, and the legal sections'
hedges exactly as strong. The English takes the window's labels from the app's English strings (the `_()` source
strings), not from a translation of the Japanese labels. `tests/test_translator_install.py` checks that both READMEs
carry the PLaMo credit and the download sizes. The README is kept short (what it is, its features, what it does not
do, installing in three steps, the requirements as a table); the long explanations live in `docs/INSTALL` (every
question and step of the installer, updating, uninstalling, the measurements) and `docs/LEGAL` (the legal position,
country by country, what is left out on purpose).

## The install check

`.github/workflows/install-check.yml` installs TASlation from scratch on a fresh Windows runner of GitHub
(`windows-2025`: Windows Server 2025, which has winget, and no GPU) and shows that it works. It is started by hand
(Actions > Install check > Run workflow) and once a week by itself (Monday 07:00 in Japan), so that a file withdrawn
or changed where the installer downloads it is noticed within days; it downloads about 5 GB and takes about half an
hour. GitHub e-mails the owner when the weekly run fails, and stops weekly runs after 60 days without activity. It unpacks the
repository as "Download ZIP" gives it (`git archive`, so `.gitattributes` applies), hides the runner's own Python from
the installer (the input `hide_python`), and runs `install.cmd -Yes` in it. Then it checks, one step each, what the
installer made (`.venv`, the three OCR models, the translation model in Ollama's model folder, the Start-menu shortcut,
and Ollama's lifetime: Ollama runs only while TASlation needs it, so no process of Ollama is left, nothing answers on
11434, Ollama does not start with Windows, `.ollama-by-install` is there, and neither `LLAMA_ARG_CACHE_RAM` for the
user nor `.cache-ram-by-install`), `taslation doctor` (ready, with Ollama started for its check and stopped again),
the server TASlation starts (`.github/install-check/hold-ollama.py`, run by the installed `.venv`, starts it with
`OllamaStarter` as the window does and loads the model; while it holds it, the workflow checks the server's process
against TASlation's record and reads `LLAMA_ARG_CACHE_RAM=0` from the environment blocks of Ollama's server and
llama.cpp's server, or says that a runner does not show them; then it lets the helper end, which must say that it
stopped the server and leave no process), a `taslation translate` of `tests/fixtures/sample_page.png` with Ollama not
running before (counts only, and that it started and stopped Ollama), `uninstall.cmd -DryRun -Yes` and
`uninstall.cmd -Yes`. The lifetime checks are for an Ollama the installer installed: on a runner without winget, where
the workflow installs Ollama itself, they are not shown. The job summary lists every check, the installer's step times and the sizes, and what the check
does not cover (a GPU, the questions a person answers, a real viewer, Windows 10 and 11); the console output is kept
as the artifact `install-check-output`. Its helpers are in `.github/install-check/`. `.gitattributes` leaves `.github`
out of GitHub's ZIP, and `update.ps1` never copies it. `tests/test_install_check_workflow.py` checks the workflow
without running it.

`-Yes` never agrees to a licence by itself. The workflow sets `TASLATION_AGREE_OCR_LICENCE` to
`I agree to CC BY-NC-SA 4.0` and `TASLATION_AGREE_PLAMO_LICENCE` to `I agree to the PLaMo Community License`, which
install.ps1 counts as agreement only with `-Yes` and only as these exact sentences, and the comment beside them records
that the repository owner has read both licences and agrees to them for this non-commercial check. Whoever runs the
workflow in a copy of the repository agrees through those lines too, so reads the two licences first.

## The GPU computer's checks on GitHub's runners

`.github/workflows/gpu-checks.yml` runs the two checks that need the developer's computer for their timings,
`tools/standin_e2e.py` and `tools/openmantra_eval.py`, for their verdicts on GitHub's Windows runners
(`windows-2025`: 4 processors, 16 GB, no GPU, so the OCR, the layout model and PLaMo run on the CPU). The GPU computer
keeps only the timing figures (the stand-in's times from the sharp frame to the finished page, the benchmark's seconds
per stage and tokens a second); what must hold on any computer is judged on the runners. It runs for every push to a
branch named `ci/...` (one push starts it and `tests.yml`), for a push to `main` (the caches alone, see below), and
when started by hand (Actions > GPU checks on runners > Run workflow), with inputs: which checks (both, stand-in,
benchmark or none), the stand-in's groups and the benchmark's titles, Ollama's release (the pinned `v0.40.17`;
`latest` or another tag only by hand, after a run on `main` has made its caches), the benchmark's `detect_model`
(`on`, the layout model, as a GPU computer's default has it) and pages, the stand-in's `--wait-done` cap (90 s; 0
runs the scenarios as written), `--timeout` (600 s) and `--cancel-soft-ms`, and the runner's screen (1920x1080 for
the session where the display offers it; the job's summary says which it had).

The job `prepare` plans the jobs and looks for four caches: Ollama's standalone files of its pinned release
(`ollama-windows-amd64.zip` from its release on GitHub, checked against the SHA-256 the workflow fixes for it,
GitHub's digest of the file and the release's `sha256sum.txt` where that lists it, and unpacked into
`%LOCALAPPDATA%\Programs\Ollama`, where TASlation's starter looks for `ollama.exe`; no installer runs), Ollama's model
store with PLaMo imported by `setup_models.py --translator-for English` (its licence agreed through
`TASLATION_AGREE_PLAMO_LICENCE` in that step alone, with the owner's agreement written beside it, as in the install
check), the models folder and pip's downloads (`tests.yml` reads those two as well). Only a run on `main` makes them:
a `ci/` branch reads main's (GitHub lets a branch read the default branch's caches), saves nothing, and its `prepare`
stops at once with an error naming what is missing when main has not made them. GitHub deletes a cache not used for 7
days; a run started by hand on `main` (checks none) makes it again.

Then thirteen stand-in jobs (the scenarios in groups: c-a-b; d-e-x-f2, e turning back to d's pages; k5-k1-k2, k's
three paces; and of those by their names only, the ones a runner's one monitor can show: tab1-...-tab6, another tab
shown; r1-...-r8, the window resized, r6 maximised on the primary monitor, as the tool may on a runner,
`GITHUB_ACTIONS`; s, the page slid with the pointer; h, with `--start-behind cover`; m0-m4 need a second monitor;
c-a-b-editing, c, a and b again in editing; g-see-edit, editing on the page measured with `--see-edit` on the
first page done, then g's one page held long; and tab0-pick and tab0-pick-plain, tab0 with the window picked in the
viewer chooser while the stand-in's other tab is in front - made-up Japanese lines, grey bars -, judged on nothing of
that tab read or learnt and the right pane's line that it shows no page of a book (both tabs are pale pages the window
waits out as pages still loading, so the line comes after PICK_NOTHING_S, and tab0 begins no sooner after the pick:
`Director.pick_waited`); and fg-keys, scenario fg in editing with `--chooser --book-asked` (the viewer chooser and
the start's dialog for the book's name answered as a person would, then a turn), judged on where the keys were; and
bw-walk, scenario bw in editing with `--chooser` at 1900 x 1000 (a book's first five screens, `tools/book_screens.py`,
in a font's made-up lines, on the dark profile with no bars nor arrows, the stand-in's band 3 px into the capture area
set by hand), judged on each screen read and translated, no frame read as one with no page, no trial nor "no page"
said (the stand-in is known by its area), the panes never over the page, every patch on show, what was read with
low confidence left as drawn and each screen's page inside its time budget, its stages' seconds summed
(`run.book_walk`; the summary's table gives each screen's most seconds by stage); each with `--wait-done`, which
holds no rest of k; seven at a time).
Each group states its role in `STANDIN_GROUPS` - Reader mode, the tool's own, or editing (`--editing`: where
TASlation starts for a new book), judged as a criterion of its own -, the stand-in's size - the tool's 1300 x 900
leaves no room for the side panes beside a spread, so the groups whose criteria look at the panes (the tabs, the
resizes, s, h) run at 1900 x 1000, the others at the tool's size, as the GPU computer's timings have it - and what
it measures besides (`measure`: "edit" runs `--see-edit` in place of `--editing`; "pick" and "pick-plain" run
`--chooser --standin-start-tab japanese` or `plain`). `--see-edit` runs there and
nowhere else: the region editor its double click opens takes the keys, which a runner has no person's window to
take them from; with it (and with `--see-add`) the first scenario is released only once the measure is over, so
that no turn comes under its drags and the jobs they start. And five
benchmark jobs (a title a job, `--series`; at most five at a time) run beside `tests.yml`'s eight, each restoring the
caches, fetching OpenMantra from its publisher (never cached, never uploaded) and letting TASlation's own starter
start Ollama on port 11435. Scenario k runs in a short form there, `--k-turns 6 --k-read 3` (6 pages flipped past at
each pace, 3 read back): each pace waits until the backlog has nothing left, and on the CPU a caught page takes some 20
to 30 s to read and translate, so that 20 pages at the 2 s pace would take near the scenario's `--timeout`. A stand-in
job fails when a criterion of correctness fails, and only then (`.github/gpu-checks/summarise.py`'s `correctness`: the
run went through, the window chose the stand-in alone, nothing was kept or shown from a frame that was not the sharp
one where the sharp frame came in time, no request was sent for nothing outside x and k - in k only page jobs' asked
before their frame was confirmed and dropped as the page was flipped past, none on a soft frame, none of the
backlog's -, a page translated at rest came back without a request, no rested page was left unfinished with the
window at rest, the narrow window's page was read at its new size, the
backlog held no frame after its read and, the window at rest at the end, nothing at all and no screen told at work;
while another tab showed no page job on a frame of it, nothing asked, stored or learnt of it, no lettering and no mouse
taken over it a second after its title came, the right pane's line, the book's tab followed into its own window;
while the window was sized with the button held no job and no request, at no look a side pane outside the window,
each pane back at rest or hidden for want of room; no side pane hidden on a slide; both panes on the screen once the
stand-in was back in sight, and there they stayed; with `--see-edit` a region of a page done found and the overlay
taking the mouse over it, a click choosing it with no editor, a double click opening its editor on it, the drags,
the plate and the rectangle handed over as what they are, a click on the empty ground choosing, opening and
changing nothing, the Delete key's message dropping the region chosen as a change of the history and the key let
go of after, a press on the page with another program in front making the stand-in the window in front and one on the
empty ground doing nothing else; in fg the start and the turn looked at, after each the window in front the viewer's,
its page with the keys, unless a dialog of TASlation's was open, and the stand-in's page saying where its keys were,
...); what depends on the computer's speed is reported beside it (`speed`: rests too short for a page,
holds at their cap, pages left half done, ...; for k the pages caught, how the pages read back began and their first
bubble, the time the backlog took to empty; editing's times, `edit_figures`: the jobs a drag, a place typed or a
rectangle start, the Delete key held, which needs the stand-in really in front), with what each scenario was meant
to show and whether it still did. A benchmark job
fails when its title's F1, CER or chrF leaves its tolerance around
the runners' own figures in `.github/gpu-checks/benchmark-expected.json` (a run of fewer pages or another
`detect_model` is not compared); the expected figures are the first run's, each run's own are kept beside them
(`seen`, two runs so far: F1 and CER the same, chrF up to 0.83 apart on a title), and the tolerances stay wide until
more runs show the spread. The job `Summary` joins the titles (`tools/openmantra_merge.py`), compares the pooled
scores with the expected ones, and puts every job's minutes (waiting, setting up, the run, after it: GitHub's step
times), both checks' verdicts and tables and the repository's caches against GitHub's 10 GB on the run's page. The
artifacts are the tools' reports, their console output and the summaries, numbers only, never the stand-in's pictures.
`tests/test_gpu_checks_workflow.py` checks the workflow without running it.

## Releases

What people download is GitHub's source ZIP of `main`, and `install.cmd` or `update.cmd` in it does the rest. Nothing is
built. So every push to `main` that changes what a person installs is a release and carries a new version:

* the version is `X.Y.Z`, written in two places that must agree: `version` in `pyproject.toml` (what `update.cmd` and
  the installer read from a copy) and `__version__` in `taslation/__init__.py`;
* `Z` goes up for a push that only fixes or speeds up, `Y` (and `Z` back to 0) for one that adds or changes what a
  person sees or does; `X` stays 0 until the saved files are promised to stay readable;
* `CHANGELOG.md` gets an entry for the version at its top, `## X.Y.Z - YYYY-MM-DD`, in the words of someone who uses the
  program; what only a developer meets (tests, tools, notes) is left out;
* the commit that is pushed is tagged `vX.Y.Z`, and the tag is pushed with it.

`tools/version_check.py` says before a push whether this was done: it compares the working tree with the newest version
tag and fails when a file a person installs differs while the version has not gone up, or when the changelog has no
entry for it. `tests/test_version.py` keeps the two places and the changelog's top entry in step. `.gitattributes`
keeps CRLF for `*.cmd` and `*.ps1` in the ZIP, and leaves `docs/media` and `.github` out of it.

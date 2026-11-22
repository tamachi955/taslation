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

## A setting in the Settings dialog

Tools > Settings... (`taslation/ui/dialogs/settings.py`) takes another part's setting in one line of `EXTRA_ROWS`:
`SettingRow(key, label, tip, section="window", choices=(), page=False)`, with *key* a field of `config.Settings`
(also in `taslation.toml.example`), *label* and *tip* in English with their 16 languages in
`taslation/locales/features/settings_dialog.py`, *section* "lettering" or "window", *choices* `((value, label), ...)`
for a list instead of a checkbox, and *page* when a change must letter the page on show again. The row shows only
where `Settings` has the key, Save writes it into taslation.toml and sets it on the window's settings at once
(`App._settings_saved`); the part reads `settings.<key>` whenever it acts. `tests/test_settings_rows.py` checks the
rows' languages.

## Other scripts

* `tools/make_sample_page.py` draws the synthetic test pages in `tests/fixtures/` (no real book is in the repository).
* `tools/fake_viewer.py` shows those pages in a window of its own, so the whole flow can be tried without a viewer.
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
  CC BY-NC 4.0 material. Since version 0.9.4 the README shows a video instead (an attachment kept by GitHub) and the
  repository holds no recording. With the whole-book run gone (2026-11-22) the tool only says so and ends (exit code 2).
* `tools/intro_video.py` records the README's introduction again from the code its checkout holds (a dev tool, never
  part of a release). `record --out FILE` runs the real window in English beside a stand-in viewer of its own (a Tk
  window of a child process showing OpenMantra pages, turned only by the page key the window passes on to it), with
  the real OCR and PLaMo through an Ollama that TASlation's own starter starts on a spare port (`--start-ollama`, 11438
  by default; 11434 to 11437 refused) and stops at the end. Its scenes come from a table (`record --list`, `--scenes`),
  each acted on the window's own Tk widgets with no system-wide input (the pointer is drawn in afterwards); it uses
  `tools/demo_video.py`'s guard and a scratch state folder, touches no other window, and keeps no page text in the
  recording. `render FILE --out GIF` makes a 960x540 GIF of about 90 to 140 s - a title card, the numbered steps and
  cards whose figures come from the code's constants - refuses one over 5 MB (`--allow-large`), and deletes the
  recording once the GIF is written; `render --sample` renders made-up frames. The recording and the GIF hold CC BY-NC
  4.0 material. Each card line and step names the sentences of README.md, docs/MANUAL.md or docs/THIRD_PARTY.md it
  follows, or is marked as the tool's own words; `tests/test_intro_video.py` fails when one of those sentences no
  longer stands word for word, so change the line with the document.
* `tools/cached_turn_profile.py` times, stage by stage, a page whose translations are cached, from the settled frame to
  the page drawn, on a stand-in viewer in memory.
* `tools/standin_e2e.py` checks the real window end to end on a browser-type stand-in viewer
  (`tools/standin_viewer/`: a local page the browser shows in an app window of its own, with a scratch profile; it
  fetches nothing and turns its pages by its own script: soft first, spreads, black frames, a spinner, a band whose
  cells say the page). The window chooses that window alone (the others are not listed, a guard stops the run when
  any other is chosen), reads and translates with the real OCR and Ollama's default model (`--canned`: a made-up
  answerer in its place), and the tool writes numbers (the sharp frame to the first request, the first lettered
  bubble and the finished page; the requests sent for nothing, for frames that changed, with what they cost; jobs kept
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
  the tool's own, the seconds since anyone's input) and `input_spells` (when the computer got input from anyone: a run
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
  profile, the state and the model it loaded are gone at the end. Scenarios by `--scenario` (all by default, about 6
  minutes): c, the turns while the model loads; a, slow reading; b, fast flipping; d, black flashes and spinners; e,
  turning back to cached pages; r, the full screen in the Reader role, entered and left by F11's own handler; t, the
  full screen in the Translator role (the toolbar's Translator, then F11's handler; at rest a region selected by a
  click on the page and the region editor opened by a double click - Tk's own pointer events on the page - and closed
  by its Esc, the selection let go by Esc, the page turned by the window's next page key and, t2, back by its
  previous one - Tk's key events on the page, the key the window hands to the stand-in noted and never sent, its
  turn released by it -, the full screen left by Esc and the Reader role chosen again; t and t2 come together); o,
  over the book (the stand-in
  made to fill its monitor, View > Over the full-screen viewer, the status bar's Move TASlation there, the Full screen
  button, the full screen left by the F11 hot key); z, TASlation's text size at 150 %; x, a request cancelled in flight
  at the translator (pages of one or two lines of text, by the annotation's counts, drawn soft for `--cancel-soft-ms`
  at half resolution, so that the window reads the soft frame and asks on it before the sharp one comes; needs the
  dataset); f, the dark theme, then f2, the narrow window (f brings f2 with it; f2 alone is that window without the
  dark theme). And k, never in all: on pages no scenario before turned to, `--k-turns` pages (20) flipped past at 0.5,
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
  the same turns), `--k-keys` releases each turn by the window's next page key once the window hands it on (the reader
  turning by TASlation's keys: pressed on its page, the window's raise of the viewer before a key left out, with
  `--standin-draws-covered`; per pace, the keys handed on and after how long), `--k-stay-ms` keeps the last page
  flipped to that long (a page read afresh on show while the pages turned past wait); `--ocr-runs-on` and
  `--ollama-num-gpu` set those settings (`CUDA_VISIBLE_DEVICES=-1 --ocr-runs-on cpu --ollama-num-gpu 0` is a computer
  without a GPU). `--side-indicator column|rail|off` sets the indicator beside the page (the app's column by default);
  when it is not off the tool looks at it from the window as normal reading's events come - every screen told has its
  cell or rail mark in the state last told, the screen on show is outlined, a screen that went by is drawn as missed
  -, and after scenario k drops the backlog as another book does and looks that nothing is left, with pictures after
  the flips, after the reads back and on each side of the drop; the report gives the event pump's times
  (`_poll_events`) either way. `--wait-done CAP_S` keeps each scenario's meaning on a slower computer (GitHub's
  runners): each rest of a, d, e, r, o, z, x, f and f2, the one at a scenario's end too, is held until the page on
  show is finished, or the window rests with it unfinished, or CAP_S have passed (the stand-in waits at an `hN` step
  of its script until the tool's word), and x's soft frames stay on show until the window has asked on them (15 s and
  CAP_S at most); the report keeps the holds and their reasons (`waits`). Without it the script and the stand-in's
  control file are the same as ever. A turn's rest ends at the next turn or where the tool changed the window for the
  next scenario (a mode left or entered, the theme, the text size, the stand-in's size: the report's
  `driver_acts`), whichever comes first, and the page at rest is what the window showed then; a job cancelled as the
  window took its page at a new size of the stand-in is not one cancelled with its page on show (`resized_away`). Its global hot keys are never
  registered with Windows: the tool holds them, notes which the window held, and hands it a press as Windows would.
  Over the book the window gives the stand-in the foreground from its own window, as the mode does; the tool itself
  never changes it. `--scale 1.5` draws the stand-in as on a display
  of that scale (the browser's `--force-device-scale-factor`) and sets TASlation's text size to it; no system setting
  changes. OpenMantra pages from the datasets folder, or `--synthetic`. The window runs with the app's defaults, so on
  a computer with a CUDA GPU and both page models installed it loads the layout model as well as LaMa (since 0.2.0):
  its times are not comparable with runs of earlier versions there.
  `--soft-first off` makes the stand-in draw every turn sharp at once and nothing after it, so that no wait of the
  viewer's is in what is timed: the published timing figures (the README's and the installation guide's table of a
  screen's time and the first bubble) are measured with it, `--scenario a,f --wait-done 120` on a quiet computer
  (screens of two pages from a and f, of one page from f2), from the report's `timing`: per screen of one page and of
  two, over the turns rested on to a page the cache did not hold, the first lettered bubble and the finished page from
  the turn and from the sharp picture's draw (the same in this mode), the first request, and the way from the turn to
  the finishing job's start (the window's first capture, its first capture of the sharp picture, from there to the
  job, the job's wait for its worker). The window starts in a process of its own on a scratch state and a browser
  window it has never seen, and what it learns of a viewer that draws soft first is held for that window in memory
  only; `timing` says that the stand-in drew nothing soft and how often the window learnt it all the same (never, or
  the figures are not sharp mode's). x needs soft frames: it is left out of all and refused by name. The correctness
  runs, here and on the runners (`.github/gpu-checks`), keep the default, `on`.
* `tools/promo_video.py` makes short videos of the time from a page turn to the lettered page. `record` runs the real
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

Then four stand-in jobs (the scenarios in groups: c, a and b; d, e, r and x, e turning back to d's pages; t with
t2, then k's three paces; o, z and f with f2; each with `--wait-done`, which holds no rest of k) and five
benchmark jobs (a title a job, `--series`) run, at most nine at a time beside `tests.yml`'s eight, each restoring the
caches, fetching OpenMantra from its publisher (never cached, never uploaded) and letting TASlation's own starter
start Ollama on port 11435. Scenario k runs in a short form there, `--k-turns 6 --k-read 3` (6 pages flipped past at
each pace, 3 read back): each pace waits until the backlog has nothing left, and on the CPU a caught page takes some 20
to 30 s to read and translate, so that 20 pages at the 2 s pace would take near the scenario's `--timeout`. A stand-in
job fails when a criterion of correctness fails, and only then (`.github/gpu-checks/summarise.py`'s `correctness`: the
run went through, the window chose the stand-in alone, nothing was kept or shown from a frame that was not the sharp
one where the sharp frame came in time, no request was sent for nothing outside x and k - in k only page jobs' asked
before their frame was confirmed and dropped as the page was flipped past, none on a soft frame, none of the
backlog's -, a page translated at rest came back without a request, no rested page was left unfinished with the
window at rest, each scenario's mode was entered and left, its page keys handed on, the
backlog held no frame after its read and, the window at rest at the end, nothing at all and no screen told at work,
...); what depends on the computer's speed is reported beside it (`speed`: rests too short for a page, holds at their
cap, pages left half done, ...; for k the pages caught, how the pages read back began and their first bubble, the
time the backlog took to empty), with what each scenario was meant to show and whether it still did. A benchmark job
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

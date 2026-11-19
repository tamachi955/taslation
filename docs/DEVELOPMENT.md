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

`python tools/dev_snapshots.py` saves the viewer's screens of a book under `~/.taslation/dev-snapshots/<book>/`, so
that detection and typesetting can be tuned without turning pages in the viewer at every experiment. Nothing is
saved unless the script runs; `python tools/dev_snapshots.py wipe --all` deletes every snapshot. The snapshots stay
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
release (the one exception in the repository is the README's recording, `docs/media/taslation-intro.gif`, which shows
twelve of its pages being translated, credited there and left out of every ZIP of the repository by `.gitattributes`): `python tools/fetch_openmantra.py` downloads it once into `~/.taslation/datasets/openmantra/` (the archive is
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
comparison altogether.

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
* `tools/prompt_replay.py` replays OpenMantra's pages through PLaMo's two ways of translating, page by page and the
  whole-book run, and counts for every request whether its prompt extends the last request's prompt and answer, and
  where and why it parts from it (the context block, a joined run, a pair changed or gone, the glossary, a cut, a
  request beside the page, a line asked again), with the tokens that then have to be computed again, numbers only.
  A stand-in model answers with the gold English (no Ollama, about 30 s); `--answers live --url` asks a server of
  the developer's own instead and adds Ollama's own counters per reason.
* `tools/make_icon.py` draws the window's icon with Pillow alone.
* `tools/strip_demo.py` runs the page strip in the real window with a made-up whole-book run (`tests/fake_strip.FakeRun`)
  and measures the Tk loop's lateness and the strip's memory; no viewer is chosen and no other window is touched.
* `tools/demo_video.py` makes a recording of a whole-book run (`docs/media/whole-book-demo.gif` by default; the README's
  recording until November 15, 2026): the real window, the real OCR and the real translator over OpenMantra pages in a
  stand-in viewer of its own, pictures of TASlation's own window only, a scratch state folder, no other window touched.
  The README's recording since then, `docs/media/taslation-intro.gif`, was made with this tool's guard and scratch state
  by a longer script that is not in the repository: the real window beside an image viewer the script opened on the
  sample pages, with translator mode's actions sent to TASlation's own widgets (the pointer is drawn in afterwards),
  followed by cards of facts. Both recordings hold CC BY-NC 4.0 material.
* `tools/cached_turn_profile.py` times, stage by stage, a page whose translations are cached, from the settled frame to
  the page drawn, on a stand-in viewer in memory (`--ahead`: erased ahead first, as a whole-book run leaves them).
* `tools/standin_e2e.py` checks the real window end to end on a browser-type stand-in viewer
  (`tools/standin_viewer/`: a local page the browser shows in an app window of its own, with a scratch profile; it
  fetches nothing and turns its pages by its own script: soft first, spreads, black frames, a spinner, a band whose
  cells say the page). The window chooses that window alone (the others are not listed, a guard stops the run when
  any other is chosen), reads and translates with the real OCR and Ollama's default model (`--canned`: a made-up
  answerer in its place), and the tool writes numbers (the sharp frame to the first request, the first lettered
  bubble and the finished page; the requests sent for nothing, for frames that changed, with what they cost; jobs kept
  from a frame that was not the sharp one; jobs cancelled per scenario; stale pages; where the OCR ran; the pages the
  cache held as they were stored at another window size only, met right after a change of size or on a turn back, with
  the page units the cache gave and did not and the requests sent for them, a page alone and a page of a spread told
  apart; each page unit looked for in the cache, with the frame's size, the capture area and the distance of the page
  found and of the nearest one, and the capture areas in force; each look for a page the cache did not hold as found,
  as it reads at other sizes, with the readings it went through, their time and what they found; how long after a turn
  the page before stayed on the page area, and its lettering, by what a whole-book run did then - reading the pages,
  translating, none; how long lettering showed on a soft picture of the page, and how far the boxes of a page read from
  a soft frame lie from those its sharp frame gives, in pixels; for the pages the cache held, drawn soft first or sharp
  at once, when their lettering came after the turn, when the lettering read from the sharp frame did, and how often
  and how long lettering left the page and came back) and pictures of TASlation's own window to the `--out`
  folder (one of them 3 s after each change of the stand-in's size, its page at the new size),
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
  button, the full screen left by the F11 hot key); z, TASlation's text size at 150 %; w, a whole-book run on a short
  stretch, started as the dialog's Start starts it, then Finished reading, with w2, the window beside the run as the
  stand-in turns back to the run's pages and on past them (w and w2 come together); x, a request cancelled in flight
  at the translator (pages of one or two lines of text, by the annotation's counts, drawn soft for `--cancel-soft-ms`
  at half resolution, so that the window reads the soft frame and asks on it before the sharp one comes; needs the
  dataset); f, the dark theme, then f2, the narrow window (f brings f2 with it; f2 alone is that window without the
  dark theme). Its global hot keys are never registered with Windows: the tool holds them, notes which the window
  held, and hands it a press as Windows would. Over the book the window gives the stand-in the foreground from its
  own window, as the mode does; the tool itself never changes it. `--scale 1.5` draws the stand-in as on a display
  of that scale (the browser's `--force-device-scale-factor`) and sets TASlation's text size to it; no system setting
  changes. OpenMantra pages from the datasets folder, or `--synthetic`. The window runs with the app's defaults, so on
  a computer with a CUDA GPU and both page models installed it loads the layout model as well as LaMa (since 0.2.0):
  its times are not comparable with runs of earlier versions there.

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

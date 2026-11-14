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
release (the one exception in the repository is the README's recording, `docs/media/whole-book-demo.gif`, which shows
eight of its pages being translated, credited there and left out of every ZIP of the repository by `.gitattributes`): `python tools/fetch_openmantra.py` downloads it once into `~/.taslation/datasets/openmantra/` (the archive is
inspected and only what is needed is extracted; the provenance goes to `SOURCE.md` there). The application itself
never reads it. `python tools/openmantra_eval.py` prints numbers only: detection precision, recall and F1 at IoU 0.5,
the OCR character error rate, chrF of the default model's translation against the professional English, and the share
of lines the review flags (`--pages 4` for a quick run, `--no-translate` without Ollama); results go to the dataset
folder's `results/`. The measurements so far are in `docs/OFFLINE_VERIFICATION.md`. Work that uses the dataset cites
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
* `tools/premises_eval.py` measures the effect of the series sheet on the translations (`tools/premises_eval_set.json`); `--long-sheet 200` measures the entries the premises block cuts, block alone against those entries after the bubbles.
* `tools/make_icon.py` draws the window's icon with Pillow alone.
* `tools/strip_demo.py` runs the page strip in the real window with a made-up whole-book run (`tests/fake_strip.FakeRun`)
  and measures the Tk loop's lateness and the strip's memory; no viewer is chosen and no other window is touched.
* `tools/demo_video.py` makes the README's recording (`docs/media/whole-book-demo.gif`): the real window, the real OCR and
  the real translator on a whole-book run over OpenMantra pages in a stand-in viewer of its own, pictures of TASlation's
  own window only, a scratch state folder, no other window touched. The recording holds CC BY-NC 4.0 material.
* `tools/cached_turn_profile.py` times, stage by stage, a page whose translations are cached, from the settled frame to
  the page drawn, on a stand-in viewer in memory (`--ahead`: erased ahead first, as a whole-book run leaves them).

## The README and the manual

`README.md` and `docs/MANUAL.md` are in English, for the public repository; `README.ja.md` and `docs/MANUAL.ja.md` are
the Japanese originals, and the English says that the Japanese prevails where the two differ. Each file links to the
other in its first lines. A change goes into the Japanese text and the English one together, in the same commit: the
same headings in the same order, the same tables, commands, file names, numbers and caveats, and the legal sections'
hedges exactly as strong. The English takes the window's labels from the app's English strings (the `_()` source
strings), not from a translation of the Japanese labels. `tests/test_translator_install.py` checks that both READMEs
carry the PLaMo credit and the download sizes.

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

A release is a git tag: bump `__version__` in `taslation/__init__.py`, commit, tag. GitHub's source ZIP of the tag is
what people download, and `install.cmd` in it does the rest. Nothing is built. `.gitattributes` keeps CRLF for `*.cmd`
and `*.ps1` in that ZIP, and leaves `docs/media` and `.github` out of it.

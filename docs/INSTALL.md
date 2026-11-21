# Installation and requirements

日本語: [INSTALL.ja.md](INSTALL.ja.md)

This is a translation. The Japanese text, [INSTALL.ja.md](INSTALL.ja.md), is the original, and it prevails where the two differ.

## Requirements

* Windows 10/11 (64-bit)
* About 7.5 GB of free disk space (about 9.0 GB when you translate into Portuguese (Brazil) or Turkish; of the translation models, PLaMo 3 Translate 2B takes about 1.8 GB (about 3.8 GB only while it is being imported), and Qwen3.5 4B, used for Portuguese (Brazil) and Turkish, about 3.3 GB; only one of the two is installed, whichever your target language needs).
  On a computer with an NVIDIA GPU, PyTorch's GPU build needs about 3.7 GB more (and, during the installation only, about 2.6 GB more again)
* 16 GB of RAM recommended (measured: TASlation itself used up to about 2.5 GB, and Ollama, which does the translating, up to about 2 GB with a GPU and about 4 GB without one. Those are the figures with Ollama's cache switched off (TASlation sets it so for the Ollama it starts). With the cache, Ollama used up to about 10 GB with a GPU and about 7.4 GB without. When you close TASlation, the Ollama it started stops too, and that RAM is free again. It has not been tried on a computer with 8 GB)
* An NVIDIA GPU (6 GB of memory) recommended. Measured: the translation model used about 1.9 GB and the model that erases lettering on the art about 0.5 GB, besides what Windows and your other programs use. A 4 GB GPU works too, but when less than about 3 GB of its memory is free, part of the translation model runs on the CPU and translation is about 1.5 times slower. It also runs without a GPU (translation is then about 4 times slower). AMD and Intel GPUs are not used (it runs on the CPU).
* A viewer that shows the book (an app or a browser)

| Step | With a GPU | Without a GPU |
|---|---|---|
| One screen showing one page (about 10 lines) | about 6 s (3 to 8) | about 23 s (12 to 30) |
| One screen showing two pages (about 16 lines) | about 9 s (6 to 14) | about 30 s (19 to 45) |
| The first page after starting | nothing more once the translation model has loaded, which it does while TASlation starts (about 6 s from the start); with Load the translation model at start off, 4 to 5 s more | the same |
| Reading and translating a whole book (190 pages) | about 15 to 20 min | about 35 min to 1 h |

The computer used for the measurements has an Intel Core i7-9700F (8 cores), 48 GB of RAM and a GeForce GTX 1660 Ti (6 GB). They were made on sample manga pages shown on a 1920×1080 screen. The whole-book times are estimates, calculated from 100 pages actually measured with the GPU and 16 pages without. The time you take to turn the pages is not included. Pages with more lines take longer (translating one line takes about 0.4 s with the GPU and about 1.5 to 1.8 s without). These figures were measured with the reading of the pages (OCR) on the CPU (about 3 s for one two-page screen). On an NVIDIA GPU that has room for them, two of the three OCR readers run on the GPU (`ocr_runs_on`, docs/MANUAL.md, "The OCR models and their licence"). On the measuring computer, a page's OCR then took a median of 564 ms, against 1,104 ms with the readers on the CPU (docs/OFFLINE_VERIFICATION.md, "Where a page's time goes in the window").

## Installation

1. On GitHub, download it with "Code" → "Download ZIP", and **extract all** of the ZIP. Do not move the folder after the installation.
2. Double-click `install.cmd`. If a warning appears, go on with "More info" → "Run anyway".
3. First it asks for the language to translate into (a number or the English name; Enter takes the language shown). This language decides the translation model.
   Next it asks, once only, for your agreement to the terms of use of the three OCR models (about 700 MB in all) (non-commercial only, CC BY-NC-SA 4.0). TASlation cannot read pages without these models,
   so if you do not agree, it does not install. If the target language is neither Portuguese (Brazil) nor Turkish, it also asks for your agreement to the licence (the PLaMo Community License) of the translation model PLaMo 3 Translate 2B (about 1.8 GB), and if you do not agree, it does not install either (those two languages use Qwen3.5 4B, about 3.3 GB, whose licence needs no agreement).
   The main points of PLaMo's licence (as revised on November 9, 2026): free for non-commercial use with no registration, 18 or older or a guardian's consent, the rights needed for what goes in and what comes out are yours to secure, and what you must say when you give a translation to someone or make it public (`docs/THIRD_PARTY.md`; TASlation asks you not to publish translations). If you answer the remaining questions with Enter, this computer gets everything it needs.
   When Python, Ollama or the translation model is missing and you answer No to the question whether to install it, TASlation could not run or could not translate, so the installation also stops then and there, with nothing installed. Running `install.cmd` again asks again.
   If you answer Y to the questions whether to install Python and Ollama, you also agree to the terms of use shown by winget (Windows' package manager), which installs them (so that winget does not ask you partway through).
   It also asks whether to install the two models that find and erase lettering on the drawing (a layout model, about 170 MB, and an inpainting model, LaMa, about 200 MB).
   On a computer with an NVIDIA GPU, Enter installs them ([Y/n]; TASlation uses both on the GPU by default),
   and on a computer without a GPU, Enter does not ([y/N]; on such a computer they are models not used by default). A run without a console, and `-Yes`, do not install them on either kind of computer.
   The questions are shown in Japanese if Windows' display language is Japanese, and in English otherwise.
4. Start it from "TASlation" in the Start menu.

PyTorch (the component TASlation uses for the OCR and LaMa) is installed as the GPU build (the CUDA build; a download of about 2.6 GB, or about 2.0 GB for the newest GPUs such as the RTX 50 series) on a computer with an NVIDIA GPU,
and as the CPU build (about 0.13 GB) on a computer without one. Whether there is a GPU is found out only by asking `nvidia-smi`, which comes with NVIDIA's driver (no network is used), and you are asked nothing about it.
The sizes of the downloads are shown during the questions, before any download starts. The GPU build needs NVIDIA driver 528.33 or later (580 or later for the RTX 50 series and the like);
with an older driver, it says so and installs the CPU build (update the driver and run install.cmd again to get the GPU build). After installing the GPU build, it checks it by computing once on the GPU,
and if it did not run on the GPU, it says so in one line, installs the CPU build and goes on with the installation. When the GPU build could not be downloaded in three attempts, the installation stops, as for any other download
(a CPU build already installed stays as it is). AMD and Intel GPUs are not counted as GPUs.
A GPU build already installed is left as it is. On a computer where a version before this one installed the CPU build, running install.cmd again replaces it with the GPU build (`update.cmd` does not replace it).

Ollama runs only while TASlation uses it. An Ollama you started yourself is left running.

* When the installer installs Ollama, it keeps it from starting with Windows, and leaves nothing of Ollama running after the installation.
  Ollama's app sets itself to start with Windows when it first starts; the installer removes that, and writes so into `.ollama-by-install` in this folder.
  TASlation starts Ollama when it translates and stops it when it ends. To use Ollama yourself, start it from the Start menu.
* An Ollama that was there before is left as it was, running or not. When it starts with Windows, the installer asks once whether to stop that
  (the default is "No"; `-Yes` never answers it). After a "Yes" it writes what it removed into `.ollama-autostart-by-install`, and `uninstall.cmd` puts it back.
  The Ollama running now keeps running until you quit it or sign out.
* When it puts the translation model into Ollama and Ollama is not running, the installer starts `ollama serve` in a hidden window (never Ollama's app),
  and stops it before its final check.

There are two settings for Ollama. TASlation gives both to the Ollama it starts, so the installer sets nothing for this Windows user for them.
For an Ollama that was there before, the installer makes both without asking. Each is made only when its environment variable is not set yet, neither for this Windows user nor in the window running the installation,
and Ollama is restarted once afterwards. A value that is already there is left as it is. Only when the restarted server answers does it say "ok"; otherwise it warns
and tells you to start Ollama from the Start menu or restart the PC (the settings are saved and apply from its next start).

* The environment variable `LLAMA_ARG_CACHE_RAM=0`. Without it, Ollama uses up to 8 GB of RAM
  for a cache of earlier requests. In TASlation's measurements that cache made translation faster only without a GPU, by about 8 %
  (while Ollama then used about 3.3 GB more RAM). When the installer sets it for this user, it applies to the Ollama this user runs, and to any other
  program of this user that reads llama.cpp's `LLAMA_ARG_*` environment variables.
* If the NVIDIA GPU has 6 GB of memory or less, it also sets `OLLAMA_KV_CACHE_TYPE=q8_0`. Ollama then uses less GPU memory, so the translation model fits on the GPU more easily.

`uninstall.cmd` removes each value the installer set if it still has that value. To undo one by hand, search the Start menu for "environment variables",
open "Edit environment variables for your account", delete the variable and restart Ollama.

The Ollama TASlation starts also gets the full window cache: `LLAMA_ARG_SWA_FULL=1`, and `LLAMA_ARG_CACHE_RAM=256` instead of `0`
(the setting "Translator's window cache" in Tools > Settings... > System, `ollama_window_cache` in `taslation.toml`). As above, a variable that is already set
(in TASlation's environment, or kept by Windows for this user or this computer) is passed on as it is.
With it, llama.cpp keeps the cache of the translation model's whole window, so that each request goes on from the one before instead of computing its whole prompt again,
and keeps 256 MB of earlier requests in RAM. By default ("On, unless the OCR then leaves the GPU") TASlation decides each time it starts Ollama:
it leaves the window cache out when its extra GPU memory would move two of the OCR readers from the GPU to the processor
(on a 6 GB GPU, only when other programs hold about 1.3 to 1.4 GB of it). "Off" never uses it, "Always on" always does.
The window and `taslation doctor` say in the translation's row whether the Ollama TASlation started has it.

For an Ollama you run yourself, neither the installer nor TASlation sets these two variables. To use the window cache there,
set `LLAMA_ARG_SWA_FULL=1` and `LLAMA_ARG_CACHE_RAM=256` for your account as above and restart Ollama; they apply to every model that Ollama runs.
What TASlation measured with its translation model (PLaMo 3 Translate 2B, the 214 pages of the OpenMantra dataset, Ollama 0.40.16, an NVIDIA GPU with 6 GB;
docs/OFFLINE_VERIFICATION.md, "The full-size window cache"):

| | Without (`LLAMA_ARG_CACHE_RAM=0`) | With (`LLAMA_ARG_SWA_FULL=1`, `LLAMA_ARG_CACHE_RAM=256`) |
|---|---|---|
| Translating the whole book | 401 s | 296 s |
| Translating page by page | 412 s | 299 s |
| Without a GPU, per line | 1.28 s | 0.98 s |
| GPU memory of the loaded model, `OLLAMA_KV_CACHE_TYPE=q8_0` | 1,933 MB | 2,065 MB |
| GPU memory of the loaded model, Ollama's default KV cache (f16) | 2,009 MB | 2,229 MB |
| RAM of the model's server at its peak (whole book) | 2.0 GB | 0.9 GB |

The translations scored the same (chrF 41.18 and 40.99 for the whole book; the difference is within what one run to the next varies).
For a model with windowed layers and a long context, the full window cache can take much more GPU memory than it does here.

When a download fails, it is tried again after 15 seconds, three times in all (it says what failed, which attempt it was and how long it waits).
When all three fail, the installation stops. When the publisher's server refused a download or no longer has the file
(HTTP 401, 403, 404, 410), trying again will not help, so it stops at once and tells you to update TASlation (download its newest copy and run `update.cmd`)
or to see the project's issues page. What a stop means is under "If the installation stops" below.

When the installation gets to its end but TASlation cannot translate yet (the final check found something missing, or Ollama could not be installed because there is no winget),
its last line says so, and what to do. Any warnings are listed before it.

The network is used during the installation: Python, Ollama and the translation model are downloaded, with your agreement, if they are missing.
After that, TASlation connects to nothing outside this computer, except to download a translation model when you agree to it (the window offers this when the language you translate into needs a model that is not installed),
and to look for a new version only if you turn that on or choose Help → "Check for updates..." (then `check_update.py`, a program of its own, asks GitHub; see "Updating" below).

All the questions come first. Once you have answered them, you can leave the computer. Depending on your connection, it takes about 15 to 60 minutes.
Download progress is shown in percent and MB. If the connection breaks partway, it goes on from where it broke off.

`install.cmd -Yes`, for runs nobody watches, never agrees to a licence by itself. Agreeing beforehand is only for automated checks of the installation: someone who has read both licences sets `TASLATION_AGREE_OCR_LICENCE` and `TASLATION_AGREE_PLAMO_LICENCE` to the exact sentences in install.ps1's help, and setting them is that person's agreement (to install TASlation for yourself, answer the questions).
A `-Yes` run without that agreement stops too, with nothing installed. A failed download gets the same three attempts.

### If the installation stops

When the installation stops, its last lines say that TASlation is not installed yet (in a folder installed before, that the installation was not finished)
and what happened. A stopped installation makes no Start-menu shortcut. Its exit code is not 0.

* Stopped after a No to a question (exit code 3): nothing was installed. Running `install.cmd` again asks again.
* Stopped after a download or an installation failed three times (exit code 1): check the network and the disk space, and run `install.cmd` again.
  Everything installed and downloaded so far is kept, and it goes on from there. The OCR models, the page models, the fonts and PLaMo's file
  go on from what was downloaded of them.
* The publisher's server refused a download or no longer has the file (exit code 5): running it again will not help.
  Update TASlation, or see the project's issues page.
* Stopped for any other reason (exit code 1): the `error:` line says what happened and what to do.

When it stops in a folder installed before, the Start-menu shortcut stays only if TASlation starts as it is now (it says so).
If it does not start, the shortcut is removed, and the installation makes it again when it gets to its end.

## Updating

The easiest way is Help → "Check for updates..." in TASlation's window. Only when you choose it, a program of its own, `check_update.py`, asks GitHub (raw.githubusercontent.com) for the first 16 KB of one file, `CHANGELOG.md`: the request stays this small however long the list of changes grows.
Nothing about you, this computer, the installed version or your books is sent; GitHub sees your IP address and the time, as any site you open does.
It shows this version and the new one with their dates, and what changed. "Update now" closes TASlation, and `update.cmd` runs in a window of its own:
it downloads the new version's ZIP (about 5 MB) from GitHub, keeps the files it replaces or deletes in the folder `.previous`, copies the new files,
goes on with the same installation as `install.cmd` (if the new version needs anything more, it asks before downloading), and starts TASlation again once that has got to its end.
The window of `update.cmd` stays open so that you can read what it did (Enter closes it). "Update now" during a whole-book run asks what closing asks.
When `update.cmd` cannot be started, the window says so and TASlation stays open.

When you install, the installer asks once whether TASlation should look for a new version when it starts (the default is No). With Yes, it asks at most once a day,
30 seconds or more after the window is ready and while no page is read or translated. A newer version is named in the Help menu's item (as "Check for updates... (0.9.0 is available)")
and in one line at the bottom of the window: no dialog, and nothing over the page in full screen. When it could not ask, it says nothing.
Nothing is downloaded or installed without asking you. Tools → "Settings..." → System, or the box in the "Check for updates..." window, changes it later
(`update_check` in `taslation.toml`). In a git clone there is no look at the start, and "Check for updates..." only says to update it with git.

A double-click on `update.cmd` first asks whether to look on GitHub for the newest version (the default is No). With Yes, it shows the versions and what changed, asks once to confirm,
downloads it and updates. With No, it asks for a ZIP you downloaded yourself, as below.

TASlation 0.8.1 and earlier have no "Check for updates...", and their `update.cmd` cannot download. Update such a version once with a ZIP you downloaded yourself, as below;
from then on "Update now" works.

### Updating with a ZIP you downloaded yourself

1. Download the new ZIP ("Code" → "Download ZIP" on GitHub) and close TASlation.
2. Double-click `update.cmd` in the TASlation folder and answer its question about GitHub with Enter (No).
3. When it asks where the new ZIP is, drag the ZIP file (or the extracted folder) onto the window and press Enter.
   If it is the newest `taslation*.zip` in your "Downloads" folder, Enter alone chooses it.
4. It shows the current version and the new version (with their dates) and asks once to confirm. Then it copies the new files and goes on with the same installation as `install.cmd`
   (if the new version needs anything more, it asks before downloading).

When that installation stops, the new version's files are already copied over the old version's, and the old version's files are kept in the folder `.previous` (its last lines say so).
The Start-menu shortcut stays only if TASlation starts as it is now. Running `update.cmd` again with the same ZIP goes on from there
(a ZIP that "Update now" downloaded is kept then, and its place is said; after a No to a question, it asks again).

The installation after an update uses the PyTorch already installed, as it is. When the CPU build is installed although there is an NVIDIA GPU (installed by a version before this one),
it does not start a download of about 2.6 GB without asking; it says so instead. To get the GPU build, run `install.cmd`.
The installation after an update also makes the Ollama settings above (so an Ollama that was there before gets `LLAMA_ARG_CACHE_RAM` too, on a computer installed with a version before this one).

`taslation.toml`, `.venv`, `models` and the data folder (`~/.taslation`) stay as they are. The program folder `taslation\` gets the same contents as the new version
(files that are not in the new version are deleted); no other file is deleted.
`update.cmd` uses the network only when it is asked to look for and download a new version ("Update now", a Yes to its first question, `-Download`):
then `check_update.py` asks raw.githubusercontent.com for the first 16 KB of `CHANGELOG.md` and downloads that version's ZIP from github.com (GitHub sends it on to codeload.github.com).
Given a ZIP or a folder, it uses no network and reads only what it was given.
You can also check the current version and its date under Help → "About TASlation".

To copy by hand, close TASlation, copy the **contents** of the `taslation-main` folder in the ZIP into the folder that holds `install.cmd`
(do not copy the folder itself; when asked, choose "Replace"), and run `install.cmd`.

### Going back to the earlier version

`update.cmd` keeps the program files it replaces or deletes in the folder `.previous` in the TASlation folder, with a note of their version and of the files the update added.
It keeps only the version just before: the next update replaces it, and an update to the same version leaves it as it is.
To go back, close TASlation and run `update.cmd -Back` in a Command Prompt (the end of an update prints the line to use).
It puts the kept files back and deletes the files the update added. What the newer version's installation put into `.venv` stays; if TASlation does not start, run `install.cmd`.
`uninstall.cmd` removes `.previous` too. In a git clone, `update.cmd` neither updates nor goes back, and says to use git.

## Uninstalling

Double-click `uninstall.cmd`: it shows a list of what will be removed and asks you to confirm (the default is "No"). It also asks, then and there, whether to delete data such as the translation cache (the default is to keep it).
It removes the Ollama environment variables the installer set (`LLAMA_ARG_CACHE_RAM`, `OLLAMA_KV_CACHE_TYPE`) if they still have that value. A value you have set again yourself stays. An Ollama that is running keeps the old settings until it restarts.
An Ollama that TASlation started and left running is stopped (not while another program has a model loaded in it). To remove Ollama's models when Ollama is not running, it starts `ollama serve` in a hidden window and stops it when done.
When Ollama is kept, an Ollama you stopped from starting with Windows with a "Yes" during the installation starts with Windows again, as before.
An Ollama installed for TASlation is left not starting with Windows, and it tells you how to change that. Finally, delete the folder.

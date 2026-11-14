# Third-party projects: what was used, what was only studied

TASlation is MIT licensed. The rule applied throughout: code from MIT /
Apache-2.0 / BSD projects may be used with its notice kept; GPL projects are
studied for ideas only and no code is copied from them; projects without a
clear license are design references only.

Licenses were checked on 2026-10-24 through the GitHub license API
(`https://api.github.com/repos/<owner>/<repo>/license`) and the Hugging Face
model API.

| Project | License | What was looked at | Code taken? |
|---|---|---|---|
| [muscgab/manga-ocr-charspot-small](https://huggingface.co/muscgab/manga-ocr-charspot-small) (code) | Apache-2.0 | The OCR's model definition, preprocessing and decoding. | **Adapted in `taslation/ocr/charspot.py`** (the notice kept at the head of the file, what changed said there; licence text in `docs/licenses/Apache-2.0-manga-ocr-charspot-small.txt`). |
| [muscgab/manga-ocr-charspot-small](https://huggingface.co/muscgab/manga-ocr-charspot-small) (model weights), revision `72ca2920` | **CC BY-NC-SA 4.0: non-commercial use only** | The OCR model itself; TASlation cannot read pages without it. | **Not in this repository, never bundled, never downloaded by the application.** `setup_models.py` fetches it into `models/manga-ocr-charspot-small` with its `LICENSE_MODEL` and `NOTICE.md`, checked against `SHA256SUMS`, after a person agreed to the terms (`install.ps1` asks; `-Yes` does not agree). See "The OCR model's licence" below. |
| [muscgab/manga-ocr-nar-small](https://huggingface.co/muscgab/manga-ocr-nar-small) (code, revision `81ff4f33`) | Apache-2.0 | The second reader's model definition and preprocessing; its encoder is upstream's re-implementation of [MonkeyOCRv2-S](https://huggingface.co/zenosai/MonkeyOCRv2-S) (Apache-2.0). | **Adapted in `taslation/ocr/nar.py`** (the notice kept at the head of the file, what changed said there; licence text in `docs/licenses/Apache-2.0-manga-ocr-nar-small.txt`). |
| [muscgab/manga-ocr-nar-small](https://huggingface.co/muscgab/manga-ocr-nar-small) (model weights), revision `81ff4f33` | **CC BY-NC-SA 4.0: non-commercial use only** | The second OCR reader. | **Not in this repository, never bundled, never downloaded by the application.** `setup_models.py` fetches it into `models/manga-ocr-nar-small` with its `LICENSE_MODEL`, `NOTICE.md` and `THIRD_PARTY_LICENSE_MONKEYOCRV2`, checked against `SHA256SUMS`, after a person agreed. |
| [muscgab/manga-ocr-CPT](https://github.com/muscgab/manga-ocr-CPT) (code) | Apache-2.0 | The third reader's model definition and preprocessing, a re-implementation of the mangaOCR architecture without `transformers`. | **Adapted in `taslation/ocr/cpt.py`** (the notice kept at the head of the file, what changed said there; licence text in `docs/licenses/Apache-2.0-manga-ocr-CPT.txt`). |
| [muscgab/manga-ocr-base-CPT-flex](https://huggingface.co/muscgab/manga-ocr-base-CPT-flex) (model weights), revision `9cc15742` | **CC BY-NC-SA 4.0: non-commercial use only** | The third OCR reader. Initialised from [kha-white/manga-ocr-base](https://huggingface.co/kha-white/manga-ocr-base) (Apache-2.0 by its model card, which lists Manga109-s as training data). | **Not in this repository, never bundled, never downloaded by the application.** `setup_models.py` fetches it into `models/manga-ocr-base-CPT-flex` with its `LICENSE_MODEL` and `NOTICE.md`, checked against `SHA256SUMS`, after a person agreed. |
| [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator) | GPL-3.0 | Overall pipeline shape (detect, OCR, translate, erase, render), batching a page's bubbles into one translation request, handling vertical right-to-left reading order; its detection/OCR options (inverted detection for light-on-dark text, thresholds for non-bubble text, minimum text length, text filtering) informed the equivalent switches here. | **No.** Design reference only (README and option descriptions); TASlation is an independent implementation. |
| [dmMaze/BallonsTranslator](https://github.com/dmMaze/BallonsTranslator) | GPL-3.0 | Typesetting: automatic font-size fitting inside a bubble, centred lines, drawing after erasing. | **No.** Design reference only (`taslation/render/typeset.py` is original). |
| [dmMaze/comic-text-detector](https://github.com/dmMaze/comic-text-detector) | GPL-3.0 | Neural text-region detection model. | **No.** Not used at all; TASlation detects bubbles with classical OpenCV operations and a permissively tagged layout model instead (`taslation/detect/`). Adopting this model would make TASlation GPL-3.0; it was not adopted. See "Decisions left open" below. |
| [ramjke/Translumo](https://github.com/ramjke/Translumo) | Apache-2.0 | Capturing a chosen window by handle, polling it and re-running only when the picture changes, letting the user pick a capture area. | **No** (C# project). Approach reference only; `taslation/capture/windows.py` is a ctypes implementation written for this project. |
| [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) | AGPL-3.0 | Considered as a detector backbone. | **No.** AGPL; rejected for license reasons. |

## The OCR models' licence

TASlation's own code is MIT. The weights of all three OCR models are CC BY-NC-SA 4.0 (the same `LICENSE_MODEL` file,
byte for byte), and TASlation cannot read pages without them, so **using TASlation needs the models' terms:
non-commercial use only**, with attribution. Commercial use needs separate permission from the models' authors. Copying
or changing TASlation's code under the MIT licence is not touched by this; the weights are simply not part of what the
MIT licence covers. The models were trained in part on data under the same licence; `NOTICE.md`, saved next to each
model's weights, says what it was trained on.

ONNX Runtime, the models' own CPU route, is deliberately not used: its official builds send telemetry from native code,
which `taslation/netguard.py` cannot see. The OCR does not use `transformers` either: `taslation/ocr/nar.py` and
`cpt.py` are plain PyTorch.

## The OCR models' training data

As published on 2026-11-02, all three OCR models were trained with AnimeText-OCR, and that dataset does not state where
its source images come from. TASlation did no training and adds no data to these models. Their licence above is a
separate matter and applies whatever the data's origin.

## The layout model and the inpainting model

Two more models find lettering on the drawing and take it out (`taslation/detect/layout.py`,
`taslation/render/artwork.py`, `taslation/render/lama.py`). Neither is in this repository, neither is ever bundled or
fetched by the application: `setup_models.py` fetches them from fixed revisions, checks each file, and does so only
after a person said yes (install.ps1 asks; run by hand, the script asks), with the terms and the unstated origin of
their training images shown first. Enter is yes where TASlation will run the inpainting model on the GPU (install.ps1:
an NVIDIA GPU the GPU build of PyTorch runs on; by hand: PyTorch has CUDA) and no elsewhere; a run without a console
never agrees. TASlation works without them, as it did before them. Once installed, the inpainting model is used by
default where PyTorch has a CUDA GPU (`art_erase = "auto"`; `"lama"` uses it on the CPU too, `"off"` never); the layout
model is off by default (`detect_model`).

| Model | Licence, as its repository states it | Lineage | Training data |
|---|---|---|---|
| [ogkalu/comic-text-and-bubble-detector](https://huggingface.co/ogkalu/comic-text-and-bubble-detector), revision `16e8a622` | Apache-2.0 | RT-DETR v2 r50vd fine-tuned for text and speech bubbles. Read by `transformers` from its two local files (safetensors, no remote code). | About 11k manga, webtoon, manhua and Western comic images, says its card; where they come from is not stated. |
| [dreMaz/AnimeMangaInpainting](https://huggingface.co/dreMaz/AnimeMangaInpainting) `lama_large_512px.ckpt`, revision `2953a4e9` | MIT | Big LaMa ([advimman/lama](https://github.com/advimman/lama), Apache-2.0) fine-tuned on manga and anime. The checkpoint holds tensors only; `setup_models.py` reads it once with `torch.load(weights_only=True)` and keeps the generator as safetensors. | 300k manga and anime style images, says its card; where they come from is not stated. |

The inpainting model chosen in the measurements was [ogkalu/lama-manga-onnx-dynamic](https://huggingface.co/ogkalu/lama-manga-onnx-dynamic)
(Apache-2.0), an ONNX export of the checkpoint above. Its weights are the checkpoint's: of the checkpoint's 837 tensors,
452 are in the export under their names bit for bit, and the other 385 are its 77 convolutions with their batch norms,
which the export folded into one; folded the same way, they match to 1e-6. TASlation runs the checkpoint itself, in
PyTorch, so no ONNX Runtime is needed.

`taslation/render/lama.py` is written for TASlation from the architecture of the LaMa paper (Suvorov et al., WACV 2022)
and of its authors' Apache-2.0 repository (the big-lama generator: fast Fourier convolutions, 18 residual blocks) and
from the checkpoint's own tensor names and shapes. No code of a GPL project is in it. It is the network as trained:
the ONNX export differs from it in one place, the inverse FFT of its Fourier units, which mirrors each row's spectrum
one bin off (W+1 terms where `torch.fft.irfftn` takes W). TASlation follows the original. On the synthetic sets of
`tools/erase_eval.py` the two score 29.76 and 29.80 (outlined lettering) and 56.69 and 56.49 (plain), the original first.

An unstated training set is disclosed here and is no reason to leave a model out.

## The translation models

TASlation translates with one model at a time, run by Ollama on this computer, and only the one the target language
needs is installed (TASlation offers the other when the language changes, and removes only a model it installed
itself; `taslation/translator_install.py` keeps the record, `translator_models.json` in the data folder). Neither is in
this repository or bundled: `setup_models.py --translator-for LANGUAGE` installs it, after a person said yes (install.ps1
asks, the window and the command line ask when the language changes).

| Model | Licence | Lineage | Training data |
|---|---|---|---|
| [PLaMo 3 Translate 2B GGUF](https://huggingface.co/pfnet/plamo-3-translate-2b-GGUF) (`plamo-3-translate-2b-Q4_K_M.gguf`, 1.81 GB), revision `4f672106`; every target language but the two below | [PLaMo Community License](https://plamo.preferredai.jp/info/plamo-community-license-en) ([Japanese](https://plamo.preferredai.jp/info/plamo-community-license-ja)); its English and Japanese texts are in the repository's `LICENSE/` folder and saved next to the Modelfile | Preferred Networks (PFN). Built on PLaMo 3 NICT, a pretrained model of joint research by PFN and the National Institute of Information and Communications Technology (NICT), then trained further for translation; quantized for llama.cpp by PFN. | "Tens of billions of tokens of translation-focused data", says its card; where that data, or PLaMo 3 NICT's, comes from is not stated there. |
| [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) (Alibaba; Ollama library `qwen3.5:4b`, about 3.3 GB); Portuguese (Brazil) and Turkish | Apache-2.0 | Alibaba's Qwen3.5 family; Ollama's own build. | Not reviewed for this table; see its card. |

PLaMo is downloaded from Hugging Face as that one file at that revision, checked against its SHA256
(`1ffd9073...69e0276c13`, 1,807,203,040 bytes), imported into Ollama as `taslation-plamo3-translate-2b` with a
Modelfile beside it (the GGUF, `num_ctx`, the stop tokens `<|plamo:tag|>` and `<|plamo:bos|>`; no template: TASlation
sends its prompts raw), and the GGUF is then deleted: Ollama's copy is the one used. The licence texts saved beside it
come from the same revision. The name has "PLaMo" in it, as article 4 of the licence asks of a model made from it.

The revision pinned before, `f2b4599d` (SHA256 `2c288ecc...c4cc060787`, 1,807,192,480 bytes), is refused by Hugging
Face's storage since PFN's revision of November 9, 2026, which moved the chat template into system messages and
revised the licence. Its file and the new one hold the same tensors and the same metadata byte for byte, but for the
embedded chat template, which TASlation does not use: a model imported from the old file stays as it is, needs no new
download, and translates the same (504 OpenMantra lines, 445 requests with context, glossary and earlier lines: the
same answer to each).

What the PLaMo Community License, as revised on November 9, 2026, means here, in short (the licence itself decides):

* personal and other non-commercial use is free, with no registration; commercial use needs registering with PFN first
  (article 3; free up to 1 billion yen of yearly revenue, a separate contract above). The licence counts as commercial
  also the use "for developing ... products, services", so developing TASlation itself with PLaMo may count as such:
  the owner's call;
* the user must be 18 or older, or of age where they live, or have a parent's or guardian's consent (article 2): the
  agreement step says so;
* the user is responsible for having the rights, permissions and consents needed for what they put into it and for
  what comes out, and the licence gives no licence to anyone else's rights in them (article 9): the agreement step
  says so; for a book, that is what the legal notice is about;
* "Built with PLaMo" is shown where TASlation is described: Help > About TASlation and the README. Article 4 asks it,
  with a copy of the licence and "PLaMo" in a model's name, of whoever provides the model or a model made from it to
  others (since the revision, no longer of whoever provides outputs). TASlation provides neither, as each computer
  downloads the file from Hugging Face itself, and keeps the credit all the same;
* a translation made with it may be published without a note that it is PLaMo's output (article 5 (2): PLaMo 3
  Translate is a "conversion model"), but one published as all or a large part of a book or another long standalone
  publication must say, in a reasonable place such as the colophon, that PLaMo was used; and whoever is given a
  translation, or can see it made public, must be told that models trained on it fall under the licence (article 5
  (4)). The legal notice says so in every language, besides asking never to publish or share translations at all;
* the model and its output come as is, without any warranty, and the user is responsible for how they use them
  (article 7);
* the agreement is asked for before anything is downloaded, in install.ps1, in the window (a tick and a button of its
  own) and at the console, and written down with its time, the revision and the licence texts' SHA256 in
  `translator_models.json`; a changed licence is asked about again before PLaMo is next installed.

A revised licence: PFN may change it, and tells "the modification details and the effective date" in the way it
chooses by that date (article 12). The revised terms then apply to whoever agreed before as well; the licence asks no
new agreement of them. TASlation therefore leaves a PLaMo already installed as it is and does not ask about the
revision then; its record of the agreement names the earlier texts, so the revised one is shown and asked about the
next time PLaMo is installed (a language change back to it, a new computer).

Qwen3.5 4B is Apache-2.0: no step of its own beyond the yes to the download.

## Runtime dependencies (all permissive, but for NVIDIA's libraries in torch's GPU build)

| Package | License | Role |
|---|---|---|
| numpy | BSD-3-Clause | arrays |
| Pillow | MIT-CMU (HPND) | image I/O, text rendering |
| opencv-python | Apache-2.0 | connected components, morphology, inpainting (this build rather than the headless one because windows-capture requires it, and the two would share one `cv2` folder) |
| [windows-capture](https://github.com/NiiightmareXD/windows-capture) 2.0.1 | MIT | the viewer's frames through Windows.Graphics.Capture (native extension, Windows only; no network) |
| torch: the CPU build, or on a computer with an NVIDIA GPU the GPU build (CUDA 12.6, or 13.0 for the newest GPUs) | BSD-3-Clause; the GPU build also holds NVIDIA's CUDA libraries (cudart, cuBLAS, cuDNN, cuFFT, cuRAND, cuSOLVER, cuSPARSE, CUPTI), which come under NVIDIA's own licence terms for them, not BSD, and whose texts the wheel does not carry | OCR inference and the inpainting model; with the GPU build both on the GPU. install.ps1 fetches the build from the official PyTorch index (`download.pytorch.org`) on the computer it runs on; TASlation's repository and releases hold neither. |
| safetensors | Apache-2.0 | loads the OCR models' weights |
| transformers | Apache-2.0 | the layout model's definition; reads local files only |
| jaconv | MIT | full-width marks in what the OCR reads |
| arabic-reshaper | MIT | joins Arabic letters into their contextual forms for rendering |
| cryptography (optional: the `backup` extra, or `pip install cryptography`) | Apache-2.0 or BSD-3-Clause | AES-256-GCM for the encrypted export of the translation cache |
| Tkinter | Python Software Foundation License | GUI (ships with Python) |

Optional assets fetched by `setup_models.py --font` / `--fonts`:

| Asset | License | Role |
|---|---|---|
| Comic Neue Bold (google/fonts) | SIL Open Font License 1.1 (OFL.txt is saved next to the font) | English lettering |
| Noto Sans, Noto Sans SC/TC/JP/KR/Thai/Arabic/Hebrew/Devanagari/Bengali (google/fonts) | SIL Open Font License 1.1 (OFL-NotoSans.txt saved alongside) | lettering for other scripts |

External program and models (not bundled, not required to install TASlation):

| Program / model | License | Role |
|---|---|---|
| [Ollama](https://github.com/ollama/ollama) | MIT | runs the translation model locally; reached only at `127.0.0.1:11434` |
| [PLaMo 3 Translate 2B](https://huggingface.co/pfnet/plamo-3-translate-2b-GGUF) (PFN; imported as `taslation-plamo3-translate-2b`) | PLaMo Community License | default translation model (see "The translation models" above) |
| [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) (Alibaba; Ollama tag `qwen3.5:4b`) | Apache-2.0 | translation model for Portuguese (Brazil) and Turkish, pulled through Ollama |
| [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) (Alibaba; Ollama tag `qwen3:4b-instruct-2507-q4_K_M`) | Apache-2.0 | documented text-only alternative of the same size |
| [Qwen3-30B-A3B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507) (Alibaba; Ollama tag `qwen3:30b-a3b-instruct-2507-q4_K_M`) | Apache-2.0 | documented higher-quality option (about 20 GB of RAM) |
| [Shisa V2.1 8B](https://huggingface.co/shisa-ai/shisa-v2.1-qwen3-8b) (GGUF by [XpressAI](https://huggingface.co/XpressAI/shisa-v2.1-qwen3-8b-GGUF)) | Apache-2.0 | documented alternative for English (Japanese-English tuned) |

## Decisions left open for the project owner

* **Neural text detection.** Settled on 2026-11-03: the layout model above (Apache-2.0 by its tag), which keeps the
  whole project's licence. comic-text-detector (GPL-3.0) and YOLO (AGPL) stay unused.

## OpenMantra (development only, not shipped)

The evaluation dataset of Hinami, Ishiwatari, Yasuda and Matsui, "Towards Fully Automated Manga Translation" (AAAI
2021), published by Mantra Inc. under CC BY-NC 4.0. It is downloaded by `tools/fetch_openmantra.py` into the
developer's own folder for measurements (`docs/DEVELOPMENT.md`); the dataset is not in the repository or in a release.
The README's recording, `docs/media/whole-book-demo.gif` (`tools/demo_video.py`), shows eight pages of one of its titles
(バルーンドリーム by Mitsuki Kuchitaka, 朽鷹みつき, as its title page credits it) while
TASlation translates them (the Japanese erased, an English translation set in its place: the pages are changed). The
recording is under CC BY-NC 4.0 with that credit, not under TASlation's MIT licence, and `.gitattributes` leaves
`docs/media` out of every ZIP of the repository.

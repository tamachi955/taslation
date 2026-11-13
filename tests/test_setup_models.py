"""setup_models.py and the OCR models: a person agrees first, and only files that pass their checksum end up in place."""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import io
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_module():
    spec = importlib.util.spec_from_file_location("setup_models", ROOT / "setup_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def setup(monkeypatch):
    module = load_module()
    files: dict[str, dict[str, bytes]] = {}
    models = []
    for model in module.OCR_MODELS:
        ours = {name: f"{model.dirname} {name}".encode() for name in (*model.required, *model.notices)}
        sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in ours.items()).encode()
        ours["SHA256SUMS"] = sums
        files[model.repo] = ours
        models.append(dataclasses.replace(model, sums_sha256=hashlib.sha256(sums).hexdigest()))
    module.OCR_MODELS = tuple(models)
    module.PAGE_MODELS = ()  # (tests of their own below)
    module.fetched = []

    def fetch(url: str, dest: Path) -> None:
        name = url.rsplit("/", 1)[1]
        model = next(m for m in models if url.startswith(f"https://huggingface.co/{m.repo}/resolve/{m.revision}/"))
        module.fetched.append(model.dirname)
        dest.write_bytes(files[model.repo][name])

    monkeypatch.setattr(module, "_fetch", fetch)
    module.files = files
    return module


def test_each_model_lands_in_its_folder_only_once_it_is_whole(setup, tmp_path):
    assert setup.main(["--models-dir", str(tmp_path), "--agreed"]) == 0
    for model in setup.OCR_MODELS:
        folder = tmp_path / model.dirname
        assert {p.name for p in folder.iterdir()} >= {*model.required, *model.notices}
        assert not (tmp_path / (folder.name + ".part")).exists()
    assert (tmp_path / setup.OCR_MODELS[1].dirname / "THIRD_PARTY_LICENSE_MONKEYOCRV2").is_file()


def test_a_file_that_fails_its_checksum_installs_nothing_of_that_model(setup, tmp_path):
    nar = setup.OCR_MODELS[1]
    setup.files[nar.repo]["model.safetensors"] = b"something else"
    with pytest.raises(SystemExit, match="failed its checksum"):
        setup.main(["--models-dir", str(tmp_path), "--agreed"])
    assert not (tmp_path / nar.dirname).exists()


def test_other_sums_install_nothing(setup, tmp_path):
    setup.files[setup.OCR_MODELS[0].repo]["SHA256SUMS"] += b"x"
    with pytest.raises(SystemExit, match="not the expected one"):
        setup.main(["--models-dir", str(tmp_path), "--agreed"])
    assert not (tmp_path / setup.OCR_MODELS[0].dirname).exists()


def test_an_old_install_gets_the_two_it_lacks(setup, tmp_path):
    first = setup.OCR_MODELS[0]
    (tmp_path / first.dirname).mkdir()
    for name in first.required:
        (tmp_path / first.dirname / name).write_text("kept")
    assert setup.main(["--models-dir", str(tmp_path), "--agreed"]) == 0
    assert first.dirname not in setup.fetched and {*setup.fetched} == {m.dirname for m in setup.OCR_MODELS[1:]}
    assert (tmp_path / first.dirname / "config.json").read_text() == "kept"


def test_with_all_three_there_nothing_is_asked_or_fetched(setup, tmp_path, monkeypatch):
    assert setup.main(["--models-dir", str(tmp_path), "--agreed"]) == 0
    setup.fetched.clear()
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("asked"))
    assert setup.main(["--models-dir", str(tmp_path)]) == 0 and not setup.fetched


def test_check_wants_all_three(setup, tmp_path):
    assert setup.main(["--models-dir", str(tmp_path), "--agreed"]) == 0
    assert setup.main(["--models-dir", str(tmp_path), "--check"]) == 0
    (tmp_path / setup.OCR_MODELS[2].dirname / "model.safetensors").unlink()
    assert setup.main(["--models-dir", str(tmp_path), "--check"]) == 1


def test_run_by_hand_it_asks_and_a_no_downloads_nothing(setup, tmp_path, monkeypatch, capsys):
    class Console:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Console())
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert setup.main(["--models-dir", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "non-commercial" in out and "CC BY-NC-SA 4.0" in out and not list(tmp_path.iterdir())
    for model in setup.OCR_MODELS:
        assert model.dirname in out


def test_without_a_console_nobody_agreed(setup, tmp_path, monkeypatch):
    class NoConsole:
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", NoConsole())
    assert setup.main(["--models-dir", str(tmp_path)]) == 1


def test_the_real_table_is_pinned():
    for model in load_module().OCR_MODELS:
        assert len(model.sums_sha256) == 64 and len(model.revision) == 40 and "LICENSE_MODEL" in model.notices


class Response(io.BytesIO):
    """A server's answer that ignores Range: always the whole file, 200."""
    status = 200

    def __init__(self, data: bytes, length: int | None):
        super().__init__(data)
        self.headers = {} if length is None else {"Content-Length": str(length)}


@pytest.fixture
def plain():
    """setup_models.py with its own `_fetch`, and urlopen for a test to replace (a dropped connection tried again at
    once)."""
    spec = importlib.util.spec_from_file_location("setup_models_plain", ROOT / "setup_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RETRY_WAIT_S = 0.0
    return module


def test_a_font_cut_short_is_not_put_in_place(plain, tmp_path, monkeypatch):
    monkeypatch.setattr(plain.urllib.request, "urlopen", lambda request, timeout: Response(b"short", 100))
    dest = tmp_path / "Font[wght].ttf"
    with pytest.raises(OSError, match="incomplete"):
        plain._fetch("https://example.invalid/f", dest)
    assert [p.name for p in tmp_path.iterdir()] == ["Font[wght].ttf.part"]  # (the part, for the next run to go on)


def test_the_next_run_fetches_it_again(plain, tmp_path, monkeypatch):
    dest = tmp_path / "Font.ttf"
    monkeypatch.setattr(plain.urllib.request, "urlopen", lambda request, timeout: Response(b"short", 100))
    with pytest.raises(OSError):
        plain._fetch("https://example.invalid/f", dest)
    monkeypatch.setattr(plain.urllib.request, "urlopen", lambda request, timeout: Response(b"x" * 100, 100))
    plain._fetch("https://example.invalid/f", dest)
    assert dest.read_bytes() == b"x" * 100 and [p.name for p in tmp_path.iterdir()] == ["Font.ttf"]


def test_a_whole_file_without_a_length_lands_too(plain, tmp_path, monkeypatch):
    monkeypatch.setattr(plain.urllib.request, "urlopen", lambda request, timeout: Response(b"data", None))
    dest = tmp_path / "Font.ttf"
    plain._fetch("https://example.invalid/f", dest)
    assert dest.read_bytes() == b"data" and [p.name for p in tmp_path.iterdir()] == ["Font.ttf"]


@pytest.mark.parametrize("error", [urllib.error.URLError("no network"), TimeoutError("timed out"), OSError(28, "No space left on device")])
def test_no_network_is_one_line_and_no_traceback(plain, tmp_path, monkeypatch, capsys, error):
    def fail(request, timeout):
        raise error

    monkeypatch.setattr(plain.urllib.request, "urlopen", fail)
    assert plain.main(["--models-dir", str(tmp_path), "--agreed"]) == 1
    out = capsys.readouterr().out
    assert "The download failed:" in out and "the network and the disk space" in out and "Traceback" not in out


def test_the_installers_run_says_only_the_downloads(setup, tmp_path, capsys):
    assert setup.main(["--models-dir", str(tmp_path), "--agreed", "--brief"]) == 0
    assert capsys.readouterr().out == ""  # `_fetch` is the fixture's here, and it is what says the file names
    setup._brief = False


@pytest.mark.parametrize("answer", ["y", "YES", "\uff59", "\u306f\u3044"])
def test_by_hand_a_japanese_keyboard_agrees_too(setup, tmp_path, monkeypatch, answer):
    class Console:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Console())
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    assert setup.main(["--models-dir", str(tmp_path)]) == 0


@pytest.fixture
def paged(monkeypatch):
    """setup_models with the layout and inpainting models alone, their files stand-ins with right checksums."""
    module = load_module()
    contents = {}
    models = []
    for model in module.PAGE_MODELS:
        ours = {name: f"{model.dirname} {name}".encode() for name, _sha in model.files}
        contents[model.repo] = ours
        models.append(dataclasses.replace(model, files=tuple((n, hashlib.sha256(d).hexdigest()) for n, d in ours.items())))
    module.PAGE_MODELS = tuple(models)
    module.OCR_MODELS = ()
    module.urls = []

    def fetch(url: str, dest: Path) -> None:
        module.urls.append(url)
        repo = next(m.repo for m in models if url.startswith(f"https://huggingface.co/{m.repo}/resolve/{m.revision}/"))
        dest.write_bytes(contents[repo][url.rsplit("/", 1)[1]])

    monkeypatch.setattr(module, "_fetch", fetch)
    import taslation.render.lama as lama

    module.converted = []
    monkeypatch.setattr(lama, "convert", lambda src, dst: (module.converted.append(src.name), dst.write_bytes(b"tensors")))
    module.contents = contents
    return module


def test_the_page_models_come_from_their_revisions_each_into_its_folder(paged, tmp_path):
    assert paged.main(["--models-dir", str(tmp_path), "--agreed"]) == 0
    for model in paged.PAGE_MODELS:
        assert not model.missing(tmp_path) and not (tmp_path / (model.dirname + ".part")).exists()
    assert len(paged.urls) == 3
    assert paged.converted == ["lama_large_512px.ckpt"]
    lama = paged.PAGE_MODELS[1]
    assert sorted(p.name for p in (tmp_path / lama.dirname).iterdir()) == ["lama-manga.safetensors"]  # no checkpoint kept


def test_a_page_model_that_fails_its_checksum_is_not_installed(paged, tmp_path):
    model = paged.PAGE_MODELS[0]
    name = model.files[0][0]
    paged.contents[model.repo][name] = b"something else"
    with pytest.raises(SystemExit, match="failed its checksum"):
        paged.main(["--models-dir", str(tmp_path), "--agreed"])
    assert not (tmp_path / model.dirname).exists()


def test_the_page_models_wait_for_a_person_and_a_no_is_no_failure(paged, tmp_path, capsys):
    assert paged.main(["--models-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert paged.urls == [] and "MIT" in out and "works without them" in out


def test_they_can_be_left_out_and_those_there_stay(paged, tmp_path):
    assert paged.main(["--models-dir", str(tmp_path), "--agreed", "--skip-page-models"]) == 0
    assert paged.urls == []
    assert paged.main(["--models-dir", str(tmp_path), "--agreed"]) == 0
    assert len(paged.urls) == 3
    assert paged.main(["--models-dir", str(tmp_path), "--agreed"]) == 0
    assert len(paged.urls) == 3


class _Console:
    def isatty(self):
        return True


@pytest.mark.parametrize("gpu, answer, fetched", [
    (True, "", True), (True, "y", True), (True, "n", False), (True, "いいえ", False),
    (False, "", False), (False, "n", False), (False, "y", True), (False, "はい", True),
], ids=["gpu-enter", "gpu-y", "gpu-n", "gpu-iie", "cpu-enter", "cpu-n", "cpu-y", "cpu-hai"])
def test_by_hand_enter_is_yes_only_where_the_gpu_runs_the_inpainting(paged, tmp_path, monkeypatch, capsys, gpu, answer,
                                                                     fetched):
    monkeypatch.setattr(sys, "stdin", _Console())
    monkeypatch.setattr(paged, "gpu_here", lambda: gpu)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or answer)
    assert paged.main(["--models-dir", str(tmp_path)]) == 0
    assert prompts == [f"Download them on these terms? {'[Y/n]' if gpu else '[y/N]'} "]
    assert (len(paged.urls) == 3) is fetched
    out = capsys.readouterr().out
    assert "where its training images come from" in out  # the terms, whatever the default
    assert ("so Enter here means yes" in out) is gpu
    assert ("Not agreed" in out) is not fetched


def test_without_a_console_a_gpu_agrees_to_nothing_and_torch_is_not_asked(paged, tmp_path, monkeypatch):
    class NoConsole:
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", NoConsole())
    monkeypatch.setattr(paged, "gpu_here", lambda: pytest.fail("torch asked"))
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("asked"))
    assert paged.main(["--models-dir", str(tmp_path)]) == 0 and paged.urls == []


def test_agreed_fetches_them_on_any_computer_without_a_question(paged, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _Console())
    monkeypatch.setattr(paged, "gpu_here", lambda: pytest.fail("torch asked"))
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("asked"))
    assert paged.main(["--models-dir", str(tmp_path), "--agreed"]) == 0 and len(paged.urls) == 3


@pytest.mark.parametrize("cuda", [True, False])
def test_the_gpu_here_is_torch_s_answer_as_art_erase_auto_asks_it(monkeypatch, cuda):
    import taslation.devices as devices

    monkeypatch.setattr(devices, "cuda_available", lambda: cuda)
    assert load_module().gpu_here() is cuda


def test_a_torch_that_does_not_import_is_no_gpu(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)  # import torch raises ImportError
    assert load_module().gpu_here() is False


def test_each_revision_is_a_full_commit_and_each_file_has_its_sum():
    from taslation.config import PAGE_MODELS

    for model in PAGE_MODELS:
        assert len(model.revision) == 40 and all(len(sha) == 64 for _name, sha in model.files)

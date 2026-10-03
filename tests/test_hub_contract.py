"""Signal Hub contract: importable UI entry point, Streamlit only under ui/, slug-namespaced keys, Hub mode.

Written by signal-hub/scripts/scaffold_app.py and extended for Rival Signal's pages. Rival Signal has no live
collection or AI call to switch off in the Hub; Hub mode only adds a note that the project lives in the session.
"""

import ast
import builtins
import io
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
from streamlit.testing.v1 import AppTest

from rivalsignal import __version__

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src" / "rivalsignal"
UI = PACKAGE / "ui"
UI_ONLY = {"streamlit", "plotly"}
RENDER = "from rivalsignal.ui import render\n\nrender()\n"
PAGES = ["Overview", "1 · Brief & AI prompt", "2 · Import & review", "3 · Rival map", "4 · Response lab",
         "5 · Compare & export", "Research & limits"]
HUB_NOTE = "this project lives only in your browser session"


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_app_info_matches_the_hub_registry() -> None:
    from rivalsignal.ui import APP_INFO, render

    assert callable(render)
    assert APP_INFO == {"product": "Rival Signal", "version": __version__, "repo": "competitor-analysis",
                        "slug": "rival"}


def test_only_the_ui_package_imports_streamlit_or_plotly() -> None:
    offenders = {str(p.relative_to(PACKAGE)): sorted(_imported_roots(p) & UI_ONLY)
                 for p in PACKAGE.rglob("*.py") if UI not in p.parents and _imported_roots(p) & UI_ONLY}
    assert not offenders, offenders


def test_core_imports_without_streamlit_in_a_fresh_interpreter() -> None:
    code = "\n".join([
        "import importlib, pkgutil, sys",
        f"sys.path.insert(0, {str(ROOT / 'src')!r})",
        "import rivalsignal",
        "for m in pkgutil.iter_modules(rivalsignal.__path__):",
        "    if m.name != 'ui':",
        "        importlib.import_module('rivalsignal.' + m.name)",
        "assert 'streamlit' not in sys.modules and 'plotly' not in sys.modules",
    ])
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


def test_render_never_sets_page_config_or_navigation() -> None:
    for path in UI.rglob("*.py"):
        if path.name in {"signal_theme.py", "signal_font.py"}:
            continue
        source = path.read_text(encoding="utf-8")
        for call in ("st.set_page_config(", "st.navigation(", "st.Page("):
            assert call not in source, (path.name, call)


def test_session_state_and_widget_keys_go_through_the_namespace_helper() -> None:
    source = (UI / "app.py").read_text(encoding="utf-8")
    state_keys = re.findall(r"session_state(?:\[|\.get\(|\.pop\()\s*([^,\])]+)", source)
    widget_keys = [key for key in re.findall(r"\bkey=([^,)\n]+)", source) if not key.startswith("lambda")]  # sorted()
    assert state_keys and widget_keys
    assert all(key.startswith("k(") for key in state_keys), state_keys
    assert all(key.startswith("k(") for key in widget_keys), widget_keys
    assert 'NS = "rival"' in source
    assert "use_container_width" not in source


def test_core_makes_no_network_or_file_calls() -> None:
    """The AI step is a prompt the user copies by hand. urllib is used only to parse source URLs, never to fetch."""
    banned = {"requests", "httpx", "aiohttp", "socket", "http", "smtplib", "ftplib", "webbrowser", "subprocess"}
    for path in PACKAGE.rglob("*.py"):
        if path.name in {"signal_theme.py", "signal_font.py"}:
            continue
        assert not _imported_roots(path) & banned, path.name
        source = path.read_text(encoding="utf-8")
        assert "urlopen" not in source and "urllib.request" not in source, path.name
        for call in ("open(", ".write_text(", ".write_bytes(", ".mkdir(", "sqlite3", "tempfile"):
            assert call not in source, (path.name, call)


def _widgets(app: AppTest) -> list:
    return [*app.radio, *app.selectbox, *app.multiselect, *app.checkbox, *app.button, *app.slider,
            *app.number_input, *app.text_input, *app.text_area, *app.toggle, *app.date_input]


def test_render_runs_without_set_page_config_and_keys_are_namespaced() -> None:
    app = AppTest.from_string(RENDER, default_timeout=120).run()
    assert not app.exception, [e.value for e in app.exception]
    pages = app.sidebar.radio(key="rival:page").options
    assert pages == PAGES
    for page in pages:
        app.sidebar.radio(key="rival:page").set_value(page).run()
        assert not app.exception, (page, [e.value for e in app.exception])
        assert not app.error, (page, [e.value for e in app.error])
        unkeyed = [(type(w).__name__, w.label) for w in _widgets(app) if not (w.key or "").startswith("rival:")]
        assert not unkeyed, (page, unkeyed)
        if page == "5 · Compare & export":
            assert not any(HUB_NOTE in str(m.value) for m in app.markdown)  # standalone: no Hub note
    body = "\n".join(str(item.value) for item in app.markdown)
    assert f"v{__version__}" in body


def test_hub_mode_writes_nothing_and_makes_no_network_calls(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    real_connect = socket.socket.connect

    def no_network(sock, address, *args, **kwargs):
        # asyncio's event loop on Windows builds its self-pipe from a loopback socket pair; that is not network I/O.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return real_connect(sock, address, *args, **kwargs)
        raise AssertionError(f"network call in Hub mode: {address!r}")

    monkeypatch.setenv("SIGNAL_HUB", "1")
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    app = AppTest.from_string(RENDER, default_timeout=120).run()
    # Hub mode opens on the fictional demo, not an empty case.
    assert any("FICTIONAL DEMO" in str(t.value) for t in app.text)
    assert app.session_state["rival:project"]["data"]["claims"]
    for page in app.sidebar.radio(key="rival:page").options:
        app.sidebar.radio(key="rival:page").set_value(page).run()
        assert not app.exception, (page, [e.value for e in app.exception])
        if page == "5 · Compare & export":
            assert any(HUB_NOTE in str(m.value) for m in app.markdown)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert not written, written
    assert os.environ["SIGNAL_HUB"] == "1"


def test_render_reads_no_repo_root_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """Signal Hub installs the release as a normal package: only src/rivalsignal (and its package data) exists there.

    Render every page and record every file opened. Nothing may come from the repository root (assets/, docs/, ...):
    the demo, prompt, schema and references are generated in code, the font is embedded in signal_font.py, and the
    marks ship as package data under rivalsignal/ui/assets/marks.
    """
    opened: list[Path] = []
    real_open = builtins.open

    def spy(file, *args, **kwargs):
        if isinstance(file, (str, os.PathLike)):
            opened.append(Path(os.fspath(file)).resolve())
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    app = AppTest.from_string(RENDER, default_timeout=120).run()
    for page in PAGES:
        app.sidebar.radio(key="rival:page").set_value(page).run()
        assert not app.exception, (page, [error.value for error in app.exception])

    package = PACKAGE.resolve()
    root = ROOT.resolve()

    def from_repo_root(path: Path) -> bool:
        if root not in path.parents or package in path.parents:
            return False
        # Libraries probe for files that don't exist and read project config; neither is app data.
        if not path.is_file() or path.name in {"pyproject.toml", "setup.cfg", "tox.ini"}:
            return False
        # Streamlit's own config and installed-distribution metadata are not app data.
        return ".streamlit" not in path.parts and not any(
            part.endswith((".egg-info", ".dist-info")) for part in path.parts
        )

    outside = sorted({str(path) for path in opened if from_repo_root(path)})
    assert not outside, outside
    # The theme reads its mark from package data. Checked directly: on Python 3.10 pathlib keeps its own reference
    # to io.open, so the spy above does not see Path.read_text calls.
    from rivalsignal.ui import signal_theme

    assert package in Path(signal_theme.ASSETS).resolve().parents
    marks = [path for path in opened if path.name == "rivalsignal-mark.svg"]
    assert all(package in path.parents for path in marks)
    for name in ("rivalsignal-mark.svg", "rivalsignal-mark-32.png", "rivalsignal-mark-64.png"):
        assert (UI / "assets" / "marks" / name).exists()

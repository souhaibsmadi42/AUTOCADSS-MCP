"""Start AutoCAD and get the MCP dispatcher into it, without a person.

Two problems this solves:

1. AutoCAD had to be opened by hand before any call worked.
   -> `ensure_running()` finds acad.exe / acadlt.exe and starts it with a blank drawing, or waits for
      an AutoCAD that is already starting (for example one another tool just opened).

2. autocadss_dispatch.lsp was not loaded in a fresh AutoCAD session, so every call failed.
   -> `install_bundle()` puts an Autoloader bundle in %APPDATA%\\Autodesk\\ApplicationPlugins. AutoCAD
      loads it into every drawing it opens, and that folder is a trusted location, so SECURELOAD shows
      no prompt and no security setting is changed. If AutoCAD was already running before the bundle
      existed, the backend loads the dispatcher from the bundle itself (see FileIPCBackend).

Switch auto-launch off with AUTOCADSS_MCP_AUTO_LAUNCH=0. Pick a specific program with AUTOCADSS_MCP_ACAD_EXE.
"""

from __future__ import annotations

import asyncio
import filecmp
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import structlog

from autocadss_mcp.config import LISP_DIR

log = structlog.get_logger()

BUNDLE_NAME = "AutocadssMCP.bundle"
LISP_FILES = ("attribute_tools.lsp", "autocadss_dispatch.lsp")
PROCESSES = ("acad.exe", "acadlt.exe")
START_WAIT_S = float(os.environ.get("AUTOCADSS_MCP_START_WAIT", "240"))
RETRY_AFTER_FAIL_S = 300.0
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

_last_failed_launch = 0.0

PACKAGE_XML = """<?xml version="1.0" encoding="utf-8"?>
<!-- AutoCAD Autoloader bundle: loads the MCP LISP dispatcher into every drawing.
     Written by autocadss_mcp.launcher. -->
<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="AutoCAD" ProductType="Application"
                    Name="AUTOCADSS MCP dispatcher"
                    Description="Loads autocadss_dispatch.lsp so the AUTOCADSS MCP server can drive AutoCAD (File IPC backend)."
                    AppVersion="0.2.0" Author="AUTOCADSS MCP"
                    ProductCode="{8F3C2D41-6B7A-4E59-9C1D-3A5E7B9F0D62}"
                    UpgradeCode="{1D4E6F80-2A3B-4C5D-8E9F-0A1B2C3D4E5F}">
  <CompanyDetails Name="AUTOCADSS MCP" />
  <Components Description="MCP LISP dispatcher">
    <RuntimeRequirements OS="Win64" Platform="AutoCAD*" SeriesMin="R24.3" />
    <ComponentEntry AppName="AutocadssAttributeTools" Version="0.2.0"
                    ModuleName="./Contents/attribute_tools.lsp"
                    AppDescription="Attribute helpers used by the MCP dispatcher"
                    LoadOnAutoCADStartup="True" PerDocument="True" />
    <ComponentEntry AppName="AutocadssDispatch" Version="0.2.0"
                    ModuleName="./Contents/autocadss_dispatch.lsp"
                    AppDescription="File IPC dispatcher for AUTOCADSS MCP, command (c:autocadss-dispatch)"
                    LoadOnAutoCADStartup="True" PerDocument="True" />
  </Components>
</ApplicationPackage>
"""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def auto_launch_enabled() -> bool:
    return sys.platform == "win32" and os.environ.get("AUTOCADSS_MCP_AUTO_LAUNCH", "1").strip().lower() not in ("0", "false", "no", "off")


# ---------------------------------------------------------------------------
# Autoloader bundle (trusted location, loads into every drawing)
# ---------------------------------------------------------------------------


def bundle_dir() -> Path:
    root = os.environ.get("AUTOCADSS_MCP_PLUGINS_DIR") or str(Path(os.environ.get("APPDATA", str(Path.home()))) / "Autodesk" / "ApplicationPlugins")
    return Path(root) / BUNDLE_NAME


def install_bundle() -> dict:
    """Create or refresh the Autoloader bundle so it matches lisp-code/. Never raises."""
    target = bundle_dir()
    changed: list[str] = []
    try:
        contents = target / "Contents"
        contents.mkdir(parents=True, exist_ok=True)
        xml = target / "PackageContents.xml"
        if not xml.exists() or xml.read_text(encoding="utf-8", errors="replace") != PACKAGE_XML:
            xml.write_text(PACKAGE_XML, encoding="utf-8")
            changed.append("PackageContents.xml")
        for name in LISP_FILES:
            src, dst = LISP_DIR / name, contents / name
            if src.exists() and (not dst.exists() or not filecmp.cmp(src, dst, shallow=False)):
                shutil.copy2(src, dst)
                changed.append(name)
        return {"ok": True, "path": str(target), "updated": changed}
    except OSError as e:
        log.warning("bundle_install_failed", error=str(e))
        return {"ok": False, "path": str(target), "error": str(e)}


def dispatcher_files() -> list[str]:
    """LISP files to load by hand, in order, from the trusted bundle when it exists."""
    contents = bundle_dir() / "Contents"
    base = contents if (contents / "autocadss_dispatch.lsp").exists() else LISP_DIR
    return [str(base / n).replace("\\", "/") for n in LISP_FILES if (base / n).exists()]


# ---------------------------------------------------------------------------
# Finding the program
# ---------------------------------------------------------------------------


def find_acad_exe() -> Path | None:
    """acad.exe / acadlt.exe to start: AUTOCADSS_MCP_ACAD_EXE, else the newest installed."""
    env = os.environ.get("AUTOCADSS_MCP_ACAD_EXE", "").strip().strip('"')
    if env and Path(env).is_file():
        return Path(env)
    if sys.platform != "win32":
        return None
    found: list[tuple[str, Path]] = []
    try:
        import winreg

        for hive in (winreg.HKEY_LOCAL_MACHINE,):
            try:
                root = winreg.OpenKey(hive, r"SOFTWARE\Autodesk\AutoCAD")
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(root)[0]):
                rel = winreg.EnumKey(root, i)
                try:
                    rk = winreg.OpenKey(root, rel)
                except OSError:
                    continue
                for j in range(winreg.QueryInfoKey(rk)[0]):
                    try:
                        pk = winreg.OpenKey(rk, winreg.EnumKey(rk, j))
                        loc = winreg.QueryValueEx(pk, "AcadLocation")[0]
                    except OSError:
                        continue
                    for exe in ("acad.exe", "acadlt.exe"):
                        p = Path(loc) / exe
                        if p.is_file():
                            found.append((rel, p))
    except ImportError:
        pass
    if not found:
        for base in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Autodesk",):
            for d in sorted(base.glob("AutoCAD*"), reverse=True):
                for exe in ("acad.exe", "acadlt.exe"):
                    if (d / exe).is_file():
                        found.append((d.name, d / exe))
    if not found:
        return None
    found.sort(key=lambda t: t[0], reverse=True)          # R26.0 > R25.1 ..., "AutoCAD 2027" > "AutoCAD 2026"
    return found[0][1]


def running_process() -> str | None:
    """Name of a running AutoCAD process, or None."""
    if sys.platform != "win32":
        return None
    for name in PROCESSES:
        try:
            r = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {name}"], capture_output=True, text=True,
                               timeout=20, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError):
            continue
        if name.lower() in (r.stdout or "").lower():
            return name
    return None


def find_main_window() -> int | None:
    """AutoCAD's main window even when no drawing is open (Start tab)."""
    if sys.platform != "win32":
        return None
    try:
        import win32gui

        hits: list[int] = []

        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).lower().startswith("autodesk autocad"):
                hits.append(hwnd)
            return True

        win32gui.EnumWindows(cb, None)
        return hits[0] if hits else None
    except ImportError:
        return None


def _new_drawing_via_com() -> bool:
    """Full AutoCAD on its Start tab: open a blank drawing through COM (not available on LT)."""
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("AutoCAD.Application")
            app.Documents.Add()
            return True
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:  # noqa: BLE001 - best effort only
        log.info("com_new_drawing_failed", error=str(e))
        return False


def _template_for(exe: Path) -> str:
    return "acadltiso.dwt" if exe.name.lower() == "acadlt.exe" else "acadiso.dwt"


def start(exe: Path) -> None:
    """Start AutoCAD as the signed-in user, straight into a blank metric drawing."""
    subprocess.Popen([str(exe), "/nologo", "/t", _template_for(exe)], cwd=str(exe.parent), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=DETACHED, close_fds=True)


# ---------------------------------------------------------------------------
# The one thing callers use
# ---------------------------------------------------------------------------


async def ensure_running(*, launch: bool = True, wait_s: float = START_WAIT_S) -> dict:
    """Make sure an AutoCAD drawing window exists. Returns {ok, hwnd, started, exe, message}.

    - a drawing window exists      -> use it
    - AutoCAD is starting / on Start tab -> wait for it, open a blank drawing via COM if it stays on Start
    - AutoCAD is not running       -> start it (if launch and auto-launch are on) and wait
    """
    global _last_failed_launch
    from autocadss_mcp.backends.file_ipc import find_autocad_window

    install_bundle()                                   # before AutoCAD starts, so it autoloads the dispatcher
    hwnd = find_autocad_window()
    if hwnd:
        return {"ok": True, "hwnd": hwnd, "started": False}

    exe = find_acad_exe()
    proc = await asyncio.to_thread(running_process)
    started = False
    if not proc:
        if not launch or not auto_launch_enabled():
            return {"ok": False, "started": False, "exe": str(exe) if exe else None, "message": "AutoCAD is not running"}
        if exe is None:
            return {"ok": False, "started": False, "message": "AutoCAD is not installed on this PC (no acad.exe / acadlt.exe found)"}
        if time.time() - _last_failed_launch < RETRY_AFTER_FAIL_S:
            return {"ok": False, "started": False, "exe": str(exe), "message": "AutoCAD was started a few minutes ago but never showed a drawing; check the PC for a dialog"}
        log.info("starting_autocad", exe=str(exe))
        await asyncio.to_thread(start, exe)
        started = True

    began = time.time()
    com_tried = False
    while time.time() - began < wait_s:
        await asyncio.sleep(2.0)
        hwnd = find_autocad_window()
        if hwnd:
            await asyncio.sleep(5.0 if started else 1.0)   # let the autoloader finish loading the dispatcher
            return {"ok": True, "hwnd": find_autocad_window() or hwnd, "started": started, "exe": str(exe) if exe else None,
                    "seconds": int(time.time() - began)}
        if not com_tried and find_main_window() and time.time() - began > 20:
            com_tried = True                              # open, but sitting on the Start tab
            await asyncio.to_thread(_new_drawing_via_com)
    _last_failed_launch = time.time()
    return {"ok": False, "started": started, "exe": str(exe) if exe else None,
            "message": f"AutoCAD did not show a drawing within {int(wait_s)} s. It may be waiting on a licence, "
                       "sign-in or recovery dialog on the PC."}

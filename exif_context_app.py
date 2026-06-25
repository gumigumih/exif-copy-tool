"""
EXIF Copy Tool - Windows context menu utility.

Features:
- GUI for editing output formats
- Enable/disable Windows right-click menu with a checkbox
- Register context menu for all files using HKCU\\Software\\Classes\\*\\shell
- Automatically updates context menu when formats are saved while enabled
- Copy EXIF text to clipboard from context menu
- Uses bundled exiftool.exe when present; falls back to exifread/Pillow
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import traceback
import time
import threading
import ctypes
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from tkinter import messagebox, ttk
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import winreg  # type: ignore
except Exception:  # pragma: no cover
    winreg = None  # type: ignore

try:
    import exifread  # type: ignore
except Exception:
    exifread = None  # type: ignore

try:
    from PIL import Image, ExifTags  # type: ignore
except Exception:
    Image = None  # type: ignore
    ExifTags = None  # type: ignore

APP_NAME = "ExifCopyTool"
APP_TITLE = "EXIFコピー"
APP_VERSION = "0.1.3"
APP_USER_MODEL_ID = "gumigumih.exif-copy-tool"
UPDATE_API_URL = "https://api.github.com/repos/gumigumih/exif-copy-tool/releases/latest"
RELEASES_URL = "https://github.com/gumigumih/exif-copy-tool/releases"
INSTALLER_ASSET_NAME = "ExifCopyToolSetup.exe"
GUI_MUTEX_NAME = "Local\\ExifCopyTool_SettingsWindow"
_GUI_MUTEX_HANDLE = None

# Context menu is registered for all filesystem objects and for image/file-type
# associations. Windows 11 is stricter about which registry roots it surfaces in
# the main context menu, so we register multiple compatible roots.
MENU_KEY_ALL_FILES = r"Software\Classes\*\shell\ExifCopyTool"
MENU_KEY_ALL_FILESYSTEM_OBJECTS = r"Software\Classes\AllFilesystemObjects\shell\ExifCopyTool"
MENU_KEY_IMAGE = r"Software\Classes\SystemFileAssociations\image\shell\ExifCopyTool"

STANDARD_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp"]
RAW_EXTENSIONS = [
    # Sony / Canon / Nikon / Fujifilm / Olympus-OM / Panasonic / Pentax / Sigma / Hasselblad / Leica / Phase One / RED etc.
    ".arw", ".srf", ".sr2",
    ".crw", ".cr2", ".cr3",
    ".nef", ".nrw",
    ".raf",
    ".orf", ".ori",
    ".rw2", ".rwl",
    ".pef", ".ptx",
    ".x3f",
    ".3fr", ".fff",
    ".dng",
    ".iiq", ".eip",
    ".r3d",
    ".erf", ".mef", ".mos", ".mrw", ".dcr", ".k25", ".kdc", ".srw", ".bay", ".cap",
    ".raw",
]
DEFAULT_EXTENSIONS = STANDARD_EXTENSIONS + RAW_EXTENSIONS
KNOWN_EXTENSIONS = sorted(set(DEFAULT_EXTENSIONS + [".jpe", ".jfif", ".bmp", ".gif", ".avif"]))

def menu_key_for_system_extension(ext: str) -> str:
    return rf"Software\Classes\SystemFileAssociations\{ext}\shell\ExifCopyTool"

def menu_key_for_direct_extension(ext: str) -> str:
    return rf"Software\Classes\{ext}\shell\ExifCopyTool"

def menu_key_for_progid(progid: str) -> str:
    return rf"Software\Classes\{progid}\shell\ExifCopyTool"

# Backward-compatible alias for older code paths.
def menu_key_for_extension(ext: str) -> str:
    return menu_key_for_system_extension(ext)

ALL_MENU_KEYS = [MENU_KEY_IMAGE] + [menu_key_for_system_extension(ext) for ext in KNOWN_EXTENSIONS]

DEFAULT_SETTINGS = {
    "context_menu_enabled": True,
    "classic_context_menu_enabled": True,
}

DEFAULT_FORMATS = [
    {
        "name": "撮影設定",
        "template": "{Make} {Model}\n{LensModel}\n{FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}\n{DateTimeOriginal}",
    },
    {
        "name": "SNS用",
        "template": "📷 {Make} {Model}\n🔭 {LensModel}\n⚙️ {FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}",
    },
    {
        "name": "Markdown",
        "template": "**Camera:** {Make} {Model}\n**Lens:** {LensModel}\n**Settings:** {FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}\n**Date:** {DateTimeOriginal}",
    },
    {
        "name": "全部ざっくり",
        "template": "File: {FileName}\nDate: {DateTimeOriginal}\nCamera: {Make} {Model}\nLens: {LensModel}\nSettings: {FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}\n35mm: {FocalLengthIn35mmFormat}",
    },
]

EXIFTOOL_TAGS = [
    "DateTimeOriginal",
    "CreateDate",
    "Make",
    "Model",
    "LensModel",
    "LensID",
    "LensInfo",
    "FNumber",
    "ApertureValue",
    "ExposureTime",
    "ShutterSpeedValue",
    "ISO",
    "FocalLength",
    "FocalLengthIn35mmFormat",
    "Artist",
    "Copyright",
    "FileName",
]

COMMON_KEYS = list(dict.fromkeys(EXIFTOOL_TAGS + ["Source", "Error"]))

PREVIEW_SAMPLE_EXIF = {
    "DateTimeOriginal": "2026:06:21 10:30:00",
    "CreateDate": "2026:06:21 10:30:00",
    "Make": "SONY",
    "Model": "ILCE-7M4",
    "LensModel": "FE 35mm F1.4 GM",
    "LensID": "FE 35mm F1.4 GM",
    "LensInfo": "35mm f/1.4",
    "FNumber": "1.8",
    "ApertureValue": "1.8",
    "ExposureTime": "1/250",
    "ShutterSpeedValue": "1/250",
    "ISO": "400",
    "FocalLength": "35 mm",
    "FocalLengthIn35mmFormat": "35 mm",
    "Artist": "Gumi",
    "Copyright": "Gumi",
    "FileName": "sample.jpg",
    "Source": "Preview",
    "Error": "",
}

EXIFREAD_ALIASES = {
    "EXIF DateTimeOriginal": "DateTimeOriginal",
    "Image DateTime": "CreateDate",
    "Image Make": "Make",
    "Image Model": "Model",
    "EXIF LensModel": "LensModel",
    "EXIF LensMake": "LensMake",
    "EXIF FNumber": "FNumber",
    "EXIF ExposureTime": "ExposureTime",
    "EXIF ISOSpeedRatings": "ISO",
    "EXIF PhotographicSensitivity": "ISO",
    "EXIF FocalLength": "FocalLength",
    "EXIF FocalLengthIn35mmFilm": "FocalLengthIn35mmFormat",
    "Image Artist": "Artist",
    "Image Copyright": "Copyright",
}

PIL_TAG_ALIASES = {
    "DateTimeOriginal": "DateTimeOriginal",
    "DateTime": "CreateDate",
    "Make": "Make",
    "Model": "Model",
    "FNumber": "FNumber",
    "ExposureTime": "ExposureTime",
    "ISOSpeedRatings": "ISO",
    "PhotographicSensitivity": "ISO",
    "FocalLength": "FocalLength",
    "FocalLengthIn35mmFilm": "FocalLengthIn35mmFormat",
    "LensModel": "LensModel",
    "Artist": "Artist",
    "Copyright": "Copyright",
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(str(bundled))
    return app_dir()


def app_icon_path() -> Path | None:
    candidates = [
        app_dir() / "ExifCopyTool.ico",
        resource_dir() / "assets" / "ExifCopyTool.ico",
        app_dir() / "assets" / "ExifCopyTool.ico",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def context_menu_icon_path() -> str:
    icon = app_icon_path()
    if icon:
        return str(icon)
    return executable_parts()[0]




def configure_windows_app_identity() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def apply_window_icon(window: tk.Tk) -> None:
    icon = app_icon_path()
    if not icon:
        return
    try:
        window.iconbitmap(default=str(icon))
    except Exception:
        pass


def data_dir() -> Path:
    base = os.environ.get("APPDATA")
    p = Path(base) / APP_NAME if base else app_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def formats_path() -> Path:
    return data_dir() / "formats.json"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def load_formats() -> List[Dict[str, str]]:
    p = formats_path()
    if not p.exists():
        save_formats(DEFAULT_FORMATS)
        return [dict(x) for x in DEFAULT_FORMATS]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return [{"name": str(x.get("name", "")), "template": str(x.get("template", ""))} for x in data]
    except Exception:
        pass
    return [dict(x) for x in DEFAULT_FORMATS]


def save_formats(formats: List[Dict[str, str]]) -> None:
    formats_path().write_text(json.dumps(formats, ensure_ascii=False, indent=2), encoding="utf-8")


def load_settings() -> Dict[str, Any]:
    s = dict(DEFAULT_SETTINGS)
    p = settings_path()
    if p.exists():
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                s.update(loaded)
                legacy_enabled = bool(loaded.get("context_menu_enabled", True))
                if "classic_context_menu_enabled" not in loaded:
                    s["classic_context_menu_enabled"] = legacy_enabled
        except Exception:
            pass
    s["context_menu_enabled"] = bool(s.get("context_menu_enabled", False))
    return s


def save_settings(settings: Dict[str, Any]) -> None:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    merged["context_menu_enabled"] = bool(merged.get("context_menu_enabled", False))
    settings_path().write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def get_context_menu_modes(settings: Dict[str, Any] | None = None) -> Tuple[bool, bool]:
    current = settings if settings is not None else load_settings()
    return (bool(current.get("classic_context_menu_enabled")), False)


def context_menu_mode_label(settings: Dict[str, Any] | None = None) -> str:
    classic_enabled, _ = get_context_menu_modes(settings)
    return "右クリックメニュー" if classic_enabled else "無効"


def executable_parts() -> List[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [str(Path(sys.executable).resolve()), str(Path(__file__).resolve())]


def find_exiftool() -> str | None:
    candidates = [
        app_dir() / "exiftool.exe",
        app_dir() / "exiftool(-k).exe",
        app_dir() / "tools" / "exiftool.exe",
        app_dir() / "tools" / "exiftool(-k).exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("exiftool") or shutil.which("exiftool.exe")


def clean_value(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s in {"0", "None", "null"}:
        return ""
    return s


def read_exif_exiftool(image_path: str) -> Dict[str, str]:
    exe = find_exiftool()
    if not exe:
        raise RuntimeError("exiftool.exe が見つかりません")
    args = [exe, "-j", "-charset", "filename=UTF8"] + [f"-{t}" for t in EXIFTOOL_TAGS] + [image_path]
    kwargs: Dict[str, Any] = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000
    proc = subprocess.run(args, **kwargs)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "ExifTool の実行に失敗しました")
    arr = json.loads(proc.stdout or "[]")
    raw = arr[0] if arr else {}
    out = {k: "" for k in COMMON_KEYS}
    for k, v in raw.items():
        if k == "SourceFile":
            continue
        out[k] = clean_value(v)
    if not out.get("LensModel"):
        out["LensModel"] = out.get("LensID") or out.get("LensInfo") or ""
    if not out.get("DateTimeOriginal"):
        out["DateTimeOriginal"] = out.get("CreateDate", "")
    out["Source"] = "ExifTool"
    return out


def read_exif_exifread(image_path: str) -> Dict[str, str]:
    if exifread is None:
        raise RuntimeError("exifread が利用できません")
    out = {k: "" for k in COMMON_KEYS}
    out["FileName"] = Path(image_path).name
    with open(image_path, "rb") as f:
        tags = exifread.process_file(f, details=False, strict=False)
    for src, dest in EXIFREAD_ALIASES.items():
        if src in tags:
            out[dest] = clean_value(tags[src])
    if not out.get("DateTimeOriginal"):
        out["DateTimeOriginal"] = out.get("CreateDate", "")
    out["Source"] = "exifread"
    return out


def read_exif_pillow(image_path: str) -> Dict[str, str]:
    if Image is None or ExifTags is None:
        raise RuntimeError("Pillow が利用できません")
    out = {k: "" for k in COMMON_KEYS}
    out["FileName"] = Path(image_path).name
    with Image.open(image_path) as img:
        exif = img.getexif()
        tag_map = ExifTags.TAGS
        for tag_id, value in exif.items():
            name = tag_map.get(tag_id, str(tag_id))
            dest = PIL_TAG_ALIASES.get(name)
            if dest:
                out[dest] = clean_value(value)
        # Some tags live in IFD blocks. Try to read them if Pillow exposes them.
        for ifd_name in ("Exif", "GPSInfo"):
            ifd_id = getattr(ExifTags.IFD, ifd_name, None) if hasattr(ExifTags, "IFD") else None
            if ifd_id is None:
                continue
            try:
                ifd = exif.get_ifd(ifd_id)
            except Exception:
                continue
            for tag_id, value in ifd.items():
                name = tag_map.get(tag_id, str(tag_id))
                dest = PIL_TAG_ALIASES.get(name)
                if dest and not out.get(dest):
                    out[dest] = clean_value(value)
    if not out.get("DateTimeOriginal"):
        out["DateTimeOriginal"] = out.get("CreateDate", "")
    out["Source"] = "Pillow"
    return out


def read_exif(image_path: str) -> Dict[str, str]:
    errors: List[str] = []
    for reader in (read_exif_exiftool, read_exif_exifread, read_exif_pillow):
        try:
            d = reader(image_path)
            d.setdefault("FileName", Path(image_path).name)
            d = normalize_exif(d)
            # Accept result if at least one useful field exists.
            if any(d.get(k) for k in ["Make", "Model", "DateTimeOriginal", "FNumber", "ExposureTime", "ISO", "FocalLength", "LensModel"]):
                return d
            errors.append(f"{reader.__name__}: EXIF項目が空でした")
        except Exception as e:
            errors.append(f"{reader.__name__}: {e}")
    d = {k: "" for k in COMMON_KEYS}
    d["FileName"] = Path(image_path).name
    d["Error"] = " / ".join(errors)
    return d


def normalize_exif(d: Dict[str, str]) -> Dict[str, str]:
    for k in COMMON_KEYS:
        d.setdefault(k, "")
    if d.get("FocalLength") and "mm" not in d["FocalLength"].lower():
        d["FocalLength"] = f"{d['FocalLength']} mm"
    if d.get("FocalLengthIn35mmFormat") and "mm" not in d["FocalLengthIn35mmFormat"].lower():
        d["FocalLengthIn35mmFormat"] = f"{d['FocalLengthIn35mmFormat']} mm"
    if d.get("FNumber"):
        d["FNumber"] = d["FNumber"].replace("f/", "").replace("F/", "").replace("F", "").strip()
    if d.get("ISO") and d["ISO"].lower().startswith("iso"):
        d["ISO"] = d["ISO"][3:].strip()
    return d


def render_template(template: str, data: Dict[str, str]) -> str:
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return ""
    text = template.format_map(SafeDict(data))
    lines = [line.rstrip() for line in text.splitlines()]
    bad = {"/ /", "//", "F", "ISO", "Camera:", "Lens:", "Settings: / F / / ISO", "Date:"}
    return "\n".join([line for line in lines if line.strip() and line.strip() not in bad]).strip()


def parse_version(value: str) -> Tuple[int, ...]:
    text = value.strip().lstrip("vV")
    parts: List[int] = []
    for part in text.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)


def fetch_latest_release() -> Dict[str, str]:
    req = urllib.request.Request(UPDATE_API_URL, headers={"User-Agent": APP_NAME})
    with urllib.request.urlopen(req, timeout=8) as res:
        data = json.loads(res.read().decode("utf-8"))

    installer_url = ""
    for asset in data.get("assets", []):
        if not isinstance(asset, dict):
            continue

        name = str(asset.get("name", ""))
        if name == INSTALLER_ASSET_NAME:
            installer_url = str(asset.get("browser_download_url", ""))
            break

    if not installer_url:
        for asset in data.get("assets", []):
            if not isinstance(asset, dict):
                continue

            name = str(asset.get("name", "")).lower()
            if name.endswith(".exe") and "setup" in name:
                installer_url = str(asset.get("browser_download_url", ""))
                break

    return {
        "tag_name": str(data.get("tag_name", "")),
        "html_url": str(data.get("html_url", RELEASES_URL)),
        "name": str(data.get("name", "")),
        "installer_url": installer_url,
    }


def download_and_run_installer(download_url: str) -> Path:
    update_dir = Path(os.environ.get("TEMP", str(Path.home()))) / APP_NAME / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    installer_path = update_dir / INSTALLER_ASSET_NAME

    req = urllib.request.Request(download_url, headers={"User-Agent": APP_NAME})
    with urllib.request.urlopen(req, timeout=60) as res:
        with installer_path.open("wb") as f:
            shutil.copyfileobj(res, f)

    subprocess.Popen([str(installer_path)], cwd=str(update_dir))
    return installer_path


def exit_for_update(app: "App") -> None:
    app.after(0, app.on_close)
    app.after(50, lambda: (_ for _ in ()).throw(SystemExit(0)))


def copy_to_clipboard_tk(text: str, hold_ms: int = 800) -> None:
    """Fallback copy using Tkinter clipboard.

    This is intentionally kept alive for a little longer when launched from
    Explorer's context menu, because very short-lived GUI processes can appear
    to succeed but leave the clipboard unchanged on some Windows environments.
    """
    root = tk.Tk()
    apply_window_icon(root)
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    root.after(hold_ms, root.destroy)
    root.mainloop()


def windows_system_executable(*relative_parts: str, fallback_name: str) -> str:
    if os.name != "nt":
        return fallback_name
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidate = system_root.joinpath(*relative_parts)
    if candidate.exists():
        return str(candidate)
    return shutil.which(fallback_name) or fallback_name


def _run_hidden(args, *, input_text: str | None = None) -> str:
    import subprocess
    cp = subprocess.run(
        args,
        input=input_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout or f"command failed: {args!r}").strip())
    return cp.stdout


def copy_to_clipboard_powershell(text: str) -> None:
    """Copy via PowerShell Set-Clipboard and verify the clipboard content.

    v5 uses this as the primary Windows path. Tkinter can return successfully
    from an Explorer-launched short-lived process while the clipboard remains
    unchanged on some machines. PowerShell's Set-Clipboard is slower but far
    more reliable for this utility.
    """
    if os.name != "nt":
        raise RuntimeError("PowerShell clipboard is only available on Windows")

    powershell_exe = windows_system_executable(
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
        fallback_name="powershell",
    )

    # Read stdin explicitly instead of relying on $input so multiline text is
    # preserved consistently across PowerShell versions and launch contexts.
    _run_hidden(
        [
            powershell_exe,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "$text = [Console]::In.ReadToEnd(); Set-Clipboard -Value $text",
        ],
        input_text=text,
    )

    # Verify with a few short retries because some environments update the
    # clipboard asynchronously after Set-Clipboard returns.
    verify_cmd = [
        powershell_exe,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Get-Clipboard -Raw",
    ]
    for _ in range(4):
        got = _run_hidden(verify_cmd)
        if got.replace("\r\n", "\n").rstrip("\n") == text.replace("\r\n", "\n").rstrip("\n"):
            return
        time.sleep(0.15)
    raise RuntimeError("PowerShellでコピー後の検証に失敗しました")


def copy_to_clipboard_win32(text: str) -> None:
    """Fallback using the native Win32 clipboard APIs."""
    if os.name != "nt":
        raise RuntimeError("Win32 clipboard is only available on Windows")

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    data = ctypes.create_unicode_buffer(text)
    size_in_bytes = ctypes.sizeof(data)

    last_error: Exception | None = None
    for _ in range(6):
        handle = None
        try:
            if not user32.OpenClipboard(None):
                raise ctypes.WinError()
            try:
                if not user32.EmptyClipboard():
                    raise ctypes.WinError()
                handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size_in_bytes)
                if not handle:
                    raise ctypes.WinError()
                locked = kernel32.GlobalLock(handle)
                if not locked:
                    raise ctypes.WinError()
                try:
                    ctypes.memmove(locked, ctypes.addressof(data), size_in_bytes)
                finally:
                    kernel32.GlobalUnlock(handle)
                if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                    raise ctypes.WinError()
                handle = None
                return
            finally:
                user32.CloseClipboard()
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
        finally:
            if handle:
                kernel32.GlobalFree(handle)
    raise RuntimeError(f"Win32 clipboard API failed: {last_error}")


def copy_to_clipboard_clip_exe(text: str) -> None:
    """Last-resort fallback using clip.exe."""
    if os.name != "nt":
        raise RuntimeError("clip.exe is only available on Windows")
    cmd_exe = windows_system_executable("System32", "cmd.exe", fallback_name="cmd")
    clip_exe = windows_system_executable("System32", "clip.exe", fallback_name="clip")
    _run_hidden([cmd_exe, "/c", clip_exe], input_text=text)


def show_toast(title: str, message: str) -> None:
    if os.name != "nt":
        return
    script = """
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipTitle = $args[0]
$notify.BalloonTipText = $args[1]
$notify.Visible = $true
$notify.ShowBalloonTip(3000)
Start-Sleep -Milliseconds 3500
$notify.Dispose()
"""
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script, title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard.

    v5 behavior:
      1. Windows: PowerShell Set-Clipboard + verification
      2. Fallback: native Win32 clipboard API
      3. Fallback: Tkinter clipboard, held briefly
      4. Last resort: clip.exe
    """
    errors: list[str] = []
    if os.name == "nt":
        for fn in (
            copy_to_clipboard_powershell,
            copy_to_clipboard_win32,
            copy_to_clipboard_tk,
            copy_to_clipboard_clip_exe,
        ):
            try:
                fn(text)  # type: ignore[arg-type]
                return
            except Exception as e:
                errors.append(f"{fn.__name__}: {e}")
        raise RuntimeError("クリップボードへのコピーに失敗しました: " + " / ".join(errors))

    copy_to_clipboard_tk(text)


def copy_format(format_name: str, image_paths: List[str]) -> None:
    formats = load_formats()
    fmt = next((f for f in formats if f["name"] == format_name), formats[0] if formats else DEFAULT_FORMATS[0])
    rendered = []
    for p in image_paths:
        data = read_exif(p)
        text = render_template(fmt["template"], data)
        if not text:
            text = f"{Path(p).name}\nEXIF情報を取得できませんでした。"
            if data.get("Error"):
                text += f"\n{data['Error']}"
        rendered.append(text)
    final_text = "\n\n".join(rendered)
    copy_to_clipboard(final_text)
    show_toast(APP_TITLE, f"{len(image_paths)}件のEXIF情報をコピーしました")
    write_context_log(format_name, image_paths, final_text, None)


def write_context_log(format_name: str, image_paths: List[str], text: str, error: str | None) -> None:
    try:
        log = data_dir() / "last_context_run.log"
        lines = [
            f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"argv: {sys.argv!r}",
            f"format: {format_name}",
            f"paths: {image_paths!r}",
            f"text_length: {len(text)}",
            "status: " + ("ERROR" if error else "OK"),
        ]
        if error:
            lines.append(f"error: {error}")
        lines.append("--- copied text ---")
        lines.append(text)
        log.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


def quote_cmd(parts: List[str]) -> str:
    return " ".join(f'"{x}"' for x in parts)


def delete_tree(root: Any, subkey: str) -> None:
    if winreg is None:
        return
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:  # type: ignore
            while True:
                try:
                    child = winreg.EnumKey(key, 0)  # type: ignore
                    delete_tree(key, child)
                except OSError:
                    break
        winreg.DeleteKey(root, subkey)  # type: ignore
    except FileNotFoundError:
        return
    except OSError:
        return


def normalize_extensions(value: Any) -> List[str]:
    if isinstance(value, str):
        raw = value.replace("、", ",").replace(";", ",").replace(" ", ",").split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = DEFAULT_EXTENSIONS
    result: List[str] = []
    for item in raw:
        ext = str(item).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        # Keep this conservative; registry paths should not contain separators.
        if any(ch in ext for ch in ["\\", "/", "*", "?", '"', "<", ">", "|"]):
            continue
        if len(ext) > 16:
            continue
        if ext not in result:
            result.append(ext)
    return result or DEFAULT_EXTENSIONS.copy()


def extension_text(extensions: List[str]) -> str:
    return ", ".join(normalize_extensions(extensions))


def read_default_value(root: Any, subkey: str) -> str:
    if winreg is None:
        return ""
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:  # type: ignore
            value, _ = winreg.QueryValueEx(key, "")  # type: ignore
            return str(value).strip()
    except Exception:
        return ""

def read_named_value(root: Any, subkey: str, name: str) -> str:
    if winreg is None:
        return ""
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:  # type: ignore
            value, _ = winreg.QueryValueEx(key, name)  # type: ignore
            return str(value).strip()
    except Exception:
        return ""

def resolve_progids_for_extension(ext: str) -> List[str]:
    """Return likely Explorer association class names for an extension.

    Windows often shows context-menu verbs from the associated ProgID
    rather than from the extension key itself. RAW formats such as .arw,
    .nef, .cr3 commonly need this path.
    """
    if winreg is None:
        return []
    candidates: List[str] = []

    # UserChoice is the strongest signal on modern Windows.
    user_choice = rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\UserChoice"
    progid = read_named_value(winreg.HKEY_CURRENT_USER, user_choice, "ProgId")
    if progid:
        candidates.append(progid)

    # Per-user class default.
    progid = read_default_value(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}")
    if progid:
        candidates.append(progid)

    # Merged HKCR class default.
    progid = read_default_value(winreg.HKEY_CLASSES_ROOT, ext)
    if progid:
        candidates.append(progid)

    # OpenWithProgids may contain additional class names.
    for root, subkey in [
        (winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}\OpenWithProgids"),
        (winreg.HKEY_CLASSES_ROOT, rf"{ext}\OpenWithProgids"),
    ]:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:  # type: ignore
                idx = 0
                while True:
                    try:
                        name, _, _ = winreg.EnumValue(key, idx)  # type: ignore
                        if name:
                            candidates.append(str(name).strip())
                        idx += 1
                    except OSError:
                        break
        except Exception:
            pass

    result: List[str] = []
    for item in candidates:
        if not item or item in result:
            continue
        # Do not allow path separators into registry paths.
        if any(ch in item for ch in ["\\", "/", "*", "?", '"', "<", ">", "|"]):
            continue
        result.append(item)
    return result

def menu_keys_for_extension(ext: str, include_resolved_progids: bool = True) -> List[str]:
    keys = [menu_key_for_system_extension(ext), menu_key_for_direct_extension(ext)]
    if include_resolved_progids:
        for progid in resolve_progids_for_extension(ext):
            keys.append(menu_key_for_progid(progid))
    # Preserve order and remove duplicates.
    result: List[str] = []
    for key in keys:
        if key not in result:
            result.append(key)
    return result

def registered_menu_keys_from_settings() -> List[str]:
    """Return all keys that this app may have created.

    v12 uses the all-files key only. Older versions used image, extension,
    ProgID and SystemFileAssociations keys, so uninstall/re-register removes
    those as cleanup.
    """
    settings = load_settings()
    previous = normalize_extensions(settings.get("last_registered_extensions", []))
    keys = [
        MENU_KEY_ALL_FILES,
        MENU_KEY_ALL_FILESYSTEM_OBJECTS,
        MENU_KEY_IMAGE,
    ]
    for ext in sorted(set(KNOWN_EXTENSIONS + previous + DEFAULT_EXTENSIONS)):
        keys.extend(menu_keys_for_extension(ext, include_resolved_progids=True))
    result: List[str] = []
    for key in keys:
        if key not in result:
            result.append(key)
    return result


def unregister_context_menu() -> None:
    if winreg is None:
        raise RuntimeError("Windows専用機能です")
    for key in registered_menu_keys_from_settings():
        delete_tree(winreg.HKEY_CURRENT_USER, key)


def register_one_menu(menu_root_key: str, formats: List[Dict[str, str]]) -> None:
    if winreg is None:
        raise RuntimeError("Windows専用機能です")
    exe_parts = executable_parts()
    root = winreg.CreateKey(winreg.HKEY_CURRENT_USER, menu_root_key)
    winreg.SetValueEx(root, "MUIVerb", 0, winreg.REG_SZ, "EXIF情報をコピー")
    winreg.SetValueEx(root, "SubCommands", 0, winreg.REG_SZ, "")
    winreg.SetValueEx(root, "Icon", 0, winreg.REG_SZ, context_menu_icon_path())
    shell_key = winreg.CreateKey(root, "shell")
    for idx, fmt in enumerate(formats):
        key_name = f"format_{idx:02d}"
        k = winreg.CreateKey(shell_key, key_name)
        winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, fmt["name"])
        cmd = quote_cmd(exe_parts) + f' --copy "{fmt["name"]}" "%1"'
        ck = winreg.CreateKey(k, "command")
        winreg.SetValueEx(ck, "", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(ck)
        winreg.CloseKey(k)
    settings_key = winreg.CreateKey(shell_key, "settings")
    winreg.SetValueEx(settings_key, "MUIVerb", 0, winreg.REG_SZ, "フォーマット設定を開く")
    cmd = quote_cmd(exe_parts)
    ck = winreg.CreateKey(settings_key, "command")
    winreg.SetValueEx(ck, "", 0, winreg.REG_SZ, cmd)
    winreg.CloseKey(ck)
    winreg.CloseKey(settings_key)
    winreg.CloseKey(shell_key)
    winreg.CloseKey(root)


def register_context_menu(enable_classic: bool | None = None, _unused_enable_win11: bool | None = None) -> None:
    if winreg is None:
        raise RuntimeError("Windows専用機能です")
    settings = load_settings()
    classic_enabled = get_context_menu_modes(settings)[0] if enable_classic is None else bool(enable_classic)

    unregister_context_menu()
    if not classic_enabled:
        settings["classic_context_menu_enabled"] = False
        settings["context_menu_enabled"] = False
        save_settings(settings)
        return

    formats = load_formats()
    register_one_menu(MENU_KEY_ALL_FILES, formats)
    register_one_menu(MENU_KEY_ALL_FILESYSTEM_OBJECTS, formats)
    register_one_menu(MENU_KEY_IMAGE, formats)
    for ext in DEFAULT_EXTENSIONS:
        register_one_menu(menu_key_for_system_extension(ext), formats)

    settings["classic_context_menu_enabled"] = True
    settings["context_menu_enabled"] = True
    # Keep this so cleanup can remove old v10/v11 extension registrations.
    settings["last_registered_extensions"] = DEFAULT_EXTENSIONS
    save_settings(settings)


def sync_context_menu_enabled(enabled: bool) -> None:
    settings = load_settings()
    classic_enabled, _ = get_context_menu_modes(settings)
    if enabled and not classic_enabled:
        classic_enabled = True
        settings["classic_context_menu_enabled"] = True
    settings["context_menu_enabled"] = bool(enabled)
    save_settings(settings)
    if enabled:
        register_context_menu(classic_enabled)
    else:
        unregister_context_menu()


def is_menu_probably_registered(enable_classic: bool | None = None, _unused_enable_win11: bool | None = None) -> bool:
    if winreg is None:
        return False
    settings = load_settings()
    classic_enabled = get_context_menu_modes(settings)[0] if enable_classic is None else bool(enable_classic)
    if classic_enabled:
        for key in [MENU_KEY_ALL_FILES, MENU_KEY_ALL_FILESYSTEM_OBJECTS, MENU_KEY_IMAGE]:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
                    return True
            except Exception:
                pass
        for ext in DEFAULT_EXTENSIONS:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, menu_key_for_system_extension(ext)):
                    return True
            except Exception:
                pass

    return False


def acquire_gui_single_instance() -> bool:
    """Return True only for the first settings window instance.

    The context-menu "フォーマット設定を開く" action can be clicked repeatedly.
    Multiple settings windows can overwrite formats/settings in unexpected order,
    so the GUI is intentionally single-instance. Copy operations do not use this.
    """
    global _GUI_MUTEX_HANDLE
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, GUI_MUTEX_NAME)
        if not handle:
            return True
        last_error = ctypes.get_last_error()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
            return False
        _GUI_MUTEX_HANDLE = handle
        return True

    # Non-Windows fallback for development.
    lock_path = data_dir() / "settings_window.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
        os.close(fd)
        _GUI_MUTEX_HANDLE = str(lock_path)
        return True
    except FileExistsError:
        return False


def release_gui_single_instance() -> None:
    global _GUI_MUTEX_HANDLE
    if not _GUI_MUTEX_HANDLE:
        return
    if os.name == "nt":
        try:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(_GUI_MUTEX_HANDLE)
        except Exception:
            pass
    else:
        try:
            Path(str(_GUI_MUTEX_HANDLE)).unlink(missing_ok=True)
        except Exception:
            pass
    _GUI_MUTEX_HANDLE = None


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("EXIFコピー 設定")
        apply_window_icon(self)
        self.geometry("920x720")
        self.formats = load_formats()
        self.settings = load_settings()
        self.selected_index = 0
        self._build()
        self._refresh_list()
        self._refresh_status()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # If settings says enabled but registry is missing, repair automatically on launch.
        if self.settings.get("context_menu_enabled") and winreg is not None and not is_menu_probably_registered(*get_context_menu_modes(self.settings)):
            try:
                register_context_menu()
                self.status_var.set(f"右クリックメニューを自動修復しました。({context_menu_mode_label(self.settings)})")
            except Exception as e:
                self.status_var.set(f"右クリックメニュー自動修復に失敗: {e}")
        self.after(1500, self.check_updates_on_startup)

    def on_close(self) -> None:
        release_gui_single_instance()
        self.destroy()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="both", expand=True)

        notebook = ttk.Notebook(top)
        notebook.pack(fill="both", expand=True)

        format_tab = ttk.Frame(notebook, padding=10)
        settings_tab = ttk.Frame(notebook, padding=10)
        notebook.add(format_tab, text="フォーマット編集")
        notebook.add(settings_tab, text="アプリ設定")

        body = ttk.Frame(format_tab)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(left, text="フォーマット").pack(anchor="w")
        self.listbox = tk.Listbox(left, width=24, height=20)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="追加", command=self.add_format).pack(side="left")
        ttk.Button(btns, text="削除", command=self.delete_format).pack(side="left", padx=4)

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="名前").pack(anchor="w")
        self.name_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.name_var).pack(fill="x", pady=(0, 8))
        ttk.Label(right, text="テンプレート（例: {Make}, {Model}, {LensModel}, {FocalLength}, {FNumber}, {ExposureTime}, {ISO}, {DateTimeOriginal}, {FileName}, {Source}, {Error}）").pack(anchor="w")
        self.text = tk.Text(right, height=12, wrap="word")
        self.text.pack(fill="both", expand=True)
        self.text.bind("<<Modified>>", self.on_template_modified)

        tag_frame = ttk.LabelFrame(right, text="EXIFタグ", padding=6)
        tag_frame.pack(fill="x", pady=(8, 0))
        self.tag_var = tk.StringVar(value=EXIFTOOL_TAGS[0])
        self.tag_combo = ttk.Combobox(tag_frame, textvariable=self.tag_var, values=COMMON_KEYS, state="readonly", width=28)
        self.tag_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(tag_frame, text="挿入", command=self.insert_selected_tag).pack(side="left", padx=(6, 0))
        self.tag_combo.bind("<Double-Button-1>", self.insert_selected_tag)
        self.tag_combo.bind("<Return>", self.insert_selected_tag)

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="保存", command=self.save_current).pack(side="left")

        ttk.Label(right, text="サンプルプレビュー").pack(anchor="w")
        self.preview = tk.Text(right, height=12, wrap="word")
        self.preview.pack(fill="both")

        options = ttk.LabelFrame(settings_tab, text="右クリックメニュー", padding=8)
        options.pack(fill="x", pady=(0, 10))
        self.enabled_var = tk.BooleanVar(value=bool(self.settings.get("context_menu_enabled", True)))
        ttk.Checkbutton(options, text="有効にする", variable=self.enabled_var, command=self.on_enabled_changed).grid(row=0, column=0, sticky="w")
        options.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="")
        ttk.Label(options, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(8, 0))

        app_info = ttk.LabelFrame(settings_tab, text="アプリ情報", padding=8)
        app_info.pack(fill="x", pady=(0, 10))
        ttk.Label(app_info, text=f"現在のバージョン: {APP_VERSION}").grid(row=0, column=0, sticky="w")
        ttk.Button(app_info, text="更新確認", command=self.check_updates).grid(row=0, column=1, sticky="e")
        app_info.columnconfigure(0, weight=1)

    def _refresh_status(self) -> None:
        if winreg is None:
            self.status_var.set("Windows以外では右クリック登録不可")
            return
        settings = load_settings()
        enabled = bool(settings.get("context_menu_enabled"))
        modes = get_context_menu_modes(settings)
        registered = is_menu_probably_registered(*modes)
        label = context_menu_mode_label(settings)
        if enabled and registered:
            self.status_var.set(f"有効：登録済み ({label})")
        elif enabled and not registered:
            self.status_var.set(f"有効：未登録（次回起動時に修復） ({label})")
        else:
            self.status_var.set("無効")

    def _auto_update_menu_if_enabled(self) -> None:
        settings = load_settings()
        if settings.get("context_menu_enabled"):
            register_context_menu(*get_context_menu_modes(settings))
            self._refresh_status()

    def _refresh_list(self) -> None:
        self.listbox.delete(0, "end")
        for f in self.formats:
            self.listbox.insert("end", f["name"])
        if self.formats:
            self.selected_index = min(self.selected_index, len(self.formats) - 1)
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(self.selected_index)
            self.load_selected()

    def check_updates_on_startup(self) -> None:
        def worker() -> None:
            try:
                latest = fetch_latest_release()
            except Exception:
                return
            try:
                self.after(0, lambda: self._show_update_result(latest, silent=True))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def check_updates(self) -> None:
        try:
            latest = fetch_latest_release()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                messagebox.showinfo(
                    "更新確認",
                    "GitHub Releases を取得できませんでした。\n\n"
                    f"現在のバージョン: {APP_VERSION}\n"
                    "最新バージョン: 取得できません\n\n"
                    "リポジトリがprivateの場合、アプリから未認証で更新確認できないため404になります。",
                )
                return
            messagebox.showerror(
                "更新確認エラー",
                f"現在のバージョン: {APP_VERSION}\n最新バージョン: 取得できません\n\n{e}",
            )
            return
        except Exception as e:
            messagebox.showerror(
                "更新確認エラー",
                f"現在のバージョン: {APP_VERSION}\n最新バージョン: 取得できません\n\n{e}",
            )
            return

        self._show_update_result(latest, silent=False)

    def _show_update_result(self, latest: Dict[str, str], *, silent: bool) -> None:
        tag = latest.get("tag_name") or "取得できません"
        message = f"現在のバージョン: {APP_VERSION}\n最新バージョン: {tag}"
        if tag != "取得できません" and parse_version(tag) > parse_version(APP_VERSION):
            if not messagebox.askyesno(
                "更新があります",
                message
                + "\n\n最新版をダウンロードして実行しますか？"
            ):
                return

            installer_url = latest.get("installer_url") or ""
            if not installer_url:
                if messagebox.askyesno(
                    "更新を取得できません",
                    "インストーラーのダウンロードURLが見つかりませんでした。\n\n配布ページを開きますか？",
                ):
                    webbrowser.open(latest.get("html_url") or RELEASES_URL)
                return

            try:
                download_and_run_installer(installer_url)
            except Exception as e:
                if messagebox.askyesno(
                    "更新実行エラー",
                    f"インストーラーをダウンロードまたは実行できませんでした。\n\n{e}\n\n配布ページを開きますか？",
                ):
                    webbrowser.open(latest.get("html_url") or RELEASES_URL)
                return

            exit_for_update(self)
            return
        if not silent:
            messagebox.showinfo("更新確認", "最新版です。\n\n" + message)

    def on_enabled_changed(self) -> None:
        try:
            sync_context_menu_enabled(self.enabled_var.get())
            self._refresh_status()
        except Exception as e:
            self.enabled_var.set(False)
            self._refresh_status()
            messagebox.showerror("右クリック設定エラー", str(e))


    def on_select(self, _event: Any = None) -> None:
        sel = self.listbox.curselection()
        if sel:
            self.selected_index = sel[0]
            self.load_selected()

    def load_selected(self) -> None:
        if not self.formats:
            return
        fmt = self.formats[self.selected_index]
        self.name_var.set(fmt["name"])
        self.text.delete("1.0", "end")
        self.text.insert("1.0", fmt["template"])
        self.text.edit_modified(False)
        self.update_preview()

    def current_template(self) -> str:
        return self.text.get("1.0", "end").strip()

    def on_template_modified(self, _event: Any = None) -> None:
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.after_idle(self.update_preview)

    def update_preview(self) -> None:
        text = render_template(self.current_template(), PREVIEW_SAMPLE_EXIF)
        if not text:
            text = "プレビューできる出力がありません。テンプレートに {Make} などのタグを入力してください。"
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)

    def insert_selected_tag(self, _event: Any = None) -> None:
        tag = self.tag_var.get().strip()
        if not tag:
            return
        self.text.insert("insert", "{" + tag + "}")
        self.text.focus_set()

    def save_current(self, show_message: bool = True) -> None:
        if not self.formats:
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("エラー", "名前を入力してください")
            return
        self.formats[self.selected_index] = {"name": name, "template": self.current_template()}
        save_formats(self.formats)
        self._refresh_list()
        try:
            self._auto_update_menu_if_enabled()
        except Exception as e:
            messagebox.showerror("右クリック更新失敗", str(e))
            return
        if show_message:
            messagebox.showinfo("保存しました", "フォーマットを保存しました。有効化済みの場合、右クリックメニューにも自動反映しました。")

    def add_format(self) -> None:
        self.formats.append({"name": "新しいフォーマット", "template": "{Make} {Model}\n{LensModel}\n{FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}"})
        self.selected_index = len(self.formats) - 1
        save_formats(self.formats)
        self._refresh_list()
        self._auto_update_menu_if_enabled()

    def delete_format(self) -> None:
        if len(self.formats) <= 1:
            messagebox.showwarning("削除できません", "フォーマットは最低1つ必要です。")
            return
        del self.formats[self.selected_index]
        self.selected_index = max(0, self.selected_index - 1)
        save_formats(self.formats)
        self._refresh_list()
        self._auto_update_menu_if_enabled()

def main() -> None:
    configure_windows_app_identity()
    try:
        if "--register-context-menu" in sys.argv:
            settings = load_settings()
            settings["classic_context_menu_enabled"] = True
            settings["context_menu_enabled"] = True
            save_settings(settings)
            register_context_menu(True)
            return
        if "--unregister-context-menu" in sys.argv:
            settings = load_settings()
            settings["context_menu_enabled"] = False
            save_settings(settings)
            unregister_context_menu()
            return
        if "--copy" in sys.argv:
            i = sys.argv.index("--copy")
            fmt = sys.argv[i + 1]
            paths = sys.argv[i + 2:]
            try:
                if not paths:
                    raise RuntimeError("画像ファイルが指定されていません")
                copy_format(fmt, paths)
            except Exception as e:
                err = traceback.format_exc()
                write_context_log(fmt if 'fmt' in locals() else '', paths if 'paths' in locals() else [], '', err)
                show_toast(APP_TITLE, "EXIF情報のコピーに失敗しました")
                raise
            return
        if not acquire_gui_single_instance():
            try:
                messagebox.showinfo("EXIFコピー", "設定画面はすでに開いています。")
            except Exception:
                pass
            return
        app = App()
        try:
            app.mainloop()
        finally:
            release_gui_single_instance()
    except Exception as e:
        log = data_dir() / "error.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            messagebox.showerror("EXIFコピー エラー", f"{e}\n\n詳細: {log}")
        except Exception:
            pass


if __name__ == "__main__":
    main()

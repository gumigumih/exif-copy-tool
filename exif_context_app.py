"""
EXIF Copy Tool - Windows context menu utility.

Features:
- GUI for editing output formats
- Enable/disable Windows right-click menu with a checkbox
- Register context menu for all files using HKCU\Software\Classes\*\shell
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
import ctypes
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
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

# Context menu is registered for all filesystem objects and all file types.
# Some Windows/Explorer environments do not show entries registered only under *\shell,
# so we register both *\shell and AllFilesystemObjects\shell. Directory\shell is not used.
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
        except Exception:
            pass
    return s


def save_settings(settings: Dict[str, Any]) -> None:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    settings_path().write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


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


def copy_to_clipboard_tk(text: str, hold_ms: int = 800) -> None:
    """Fallback copy using Tkinter clipboard.

    This is intentionally kept alive for a little longer when launched from
    Explorer's context menu, because very short-lived GUI processes can appear
    to succeed but leave the clipboard unchanged on some Windows environments.
    """
    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    root.after(hold_ms, root.destroy)
    root.mainloop()


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

    # Windows PowerShell 5.1 is available on standard Windows installations.
    # Send text through STDIN to avoid command-line quoting problems with
    # Japanese paths, emoji, braces, and newlines.
    _run_hidden(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "Set-Clipboard -Value $input"],
        input_text=text,
    )

    # Verify immediately. If another clipboard manager races us, this catches it
    # and lets the caller try the Tk fallback.
    got = _run_hidden(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "Get-Clipboard -Raw"],
    )
    if got.replace("\r\n", "\n").rstrip("\n") != text.replace("\r\n", "\n").rstrip("\n"):
        raise RuntimeError("PowerShellでコピー後の検証に失敗しました")


def copy_to_clipboard_clip_exe(text: str) -> None:
    """Last-resort fallback using clip.exe."""
    if os.name != "nt":
        raise RuntimeError("clip.exe is only available on Windows")
    _run_hidden(["cmd", "/c", "clip"], input_text=text)


def copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard.

    v5 behavior:
      1. Windows: PowerShell Set-Clipboard + verification
      2. Fallback: Tkinter clipboard, held briefly
      3. Last resort: clip.exe

    The previous native Win32 GlobalAlloc/GlobalLock implementation is removed
    entirely because it failed on some Explorer context menu launches.
    """
    errors: list[str] = []
    if os.name == "nt":
        for fn in (copy_to_clipboard_powershell, copy_to_clipboard_tk, copy_to_clipboard_clip_exe):
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
    keys = [MENU_KEY_ALL_FILES, MENU_KEY_ALL_FILESYSTEM_OBJECTS, MENU_KEY_IMAGE]
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
    winreg.SetValueEx(root, "Icon", 0, winreg.REG_SZ, exe_parts[0])
    winreg.SetValueEx(root, "AppliesTo", 0, winreg.REG_SZ, "System.FileName:\"*.jpg\" OR System.FileName:\"*.jpeg\" OR System.FileName:\"*.png\" OR System.FileName:\"*.tif\" OR System.FileName:\"*.tiff\" OR System.FileName:\"*.heic\" OR System.FileName:\"*.webp\"")
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


def register_context_menu() -> None:
    if winreg is None:
        raise RuntimeError("Windows専用機能です")
    unregister_context_menu()
    formats = load_formats()
    # Register to both *\shell and AllFilesystemObjects\shell.
    # Some Explorer environments ignore one of them depending on file association.
    register_one_menu(MENU_KEY_ALL_FILES, formats)
    register_one_menu(MENU_KEY_ALL_FILESYSTEM_OBJECTS, formats)
    settings = load_settings()
    settings["context_menu_enabled"] = True
    # Keep this so cleanup can remove old v10/v11 extension registrations.
    settings["last_registered_extensions"] = DEFAULT_EXTENSIONS
    save_settings(settings)


def sync_context_menu_enabled(enabled: bool) -> None:
    settings = load_settings()
    settings["context_menu_enabled"] = bool(enabled)
    save_settings(settings)
    if enabled:
        register_context_menu()
    else:
        unregister_context_menu()


def is_menu_probably_registered() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEY_ALL_FILES):
            return True
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEY_ALL_FILESYSTEM_OBJECTS):
            return True
    except Exception:
        return False


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("EXIFコピー 設定")
        self.geometry("820x640")
        self.formats = load_formats()
        self.settings = load_settings()
        self.selected_index = 0
        self._build()
        self._refresh_list()
        self._refresh_status()
        # If settings says enabled but registry is missing, repair automatically on launch.
        if self.settings.get("context_menu_enabled") and winreg is not None and not is_menu_probably_registered():
            try:
                register_context_menu()
                self.status_var.set("右クリックメニューを自動修復しました。")
            except Exception as e:
                self.status_var.set(f"右クリックメニュー自動修復に失敗: {e}")

    def _build(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="both", expand=True)

        options = ttk.LabelFrame(top, text="右クリックメニュー", padding=8)
        options.pack(fill="x", pady=(0, 10))
        self.enabled_var = tk.BooleanVar(value=bool(self.settings.get("context_menu_enabled", True)))
        ttk.Checkbutton(options, text="有効にする", variable=self.enabled_var, command=self.on_enabled_changed).grid(row=0, column=0, sticky="w")
        options.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="")
        ttk.Label(options, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(8, 0))

        body = ttk.Frame(top)
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

        sample_frame = ttk.Frame(right)
        sample_frame.pack(fill="x", pady=8)
        ttk.Button(sample_frame, text="保存", command=self.save_current).pack(side="left")
        ttk.Button(sample_frame, text="画像でテスト＆コピー", command=self.test_image).pack(side="left", padx=6)
        ttk.Button(sample_frame, text="EXIF診断", command=self.diagnose_image).pack(side="left")

        ttk.Label(right, text="テスト出力 / 診断").pack(anchor="w")
        self.preview = tk.Text(right, height=10, wrap="word")
        self.preview.pack(fill="both")

    def _refresh_status(self) -> None:
        if winreg is None:
            self.status_var.set("Windows以外では右クリック登録不可")
            return
        enabled = bool(load_settings().get("context_menu_enabled"))
        registered = is_menu_probably_registered()
        if enabled and registered:
            self.status_var.set("有効：登録済み")
        elif enabled and not registered:
            self.status_var.set("有効：未登録（次回起動時に修復）")
        else:
            self.status_var.set("無効")

    def _auto_update_menu_if_enabled(self) -> None:
        if load_settings().get("context_menu_enabled"):
            register_context_menu()
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

    def save_current(self, show_message: bool = True) -> None:
        if not self.formats:
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("エラー", "名前を入力してください")
            return
        self.formats[self.selected_index] = {"name": name, "template": self.text.get("1.0", "end").strip()}
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

    def choose_image(self) -> str:
        return filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.tif *.tiff *.heic *.webp"), ("All files", "*.*")])

    def test_image(self) -> None:
        self.save_current(show_message=False)
        path = self.choose_image()
        if not path:
            return
        data = read_exif(path)
        text = render_template(self.formats[self.selected_index]["template"], data)
        if not text:
            text = "EXIF情報を取得できませんでした。\n" + data.get("Error", "")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        copy_to_clipboard(text)
        messagebox.showinfo("コピーしました", "テスト出力をクリップボードにコピーしました。")

    def diagnose_image(self) -> None:
        path = self.choose_image()
        if not path:
            return
        data = read_exif(path)
        lines = [f"{k}: {v}" for k, v in data.items() if v]
        if not lines:
            lines = ["EXIF情報を取得できませんでした。"]
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", "\n".join(lines))


def main() -> None:
    try:
        if "--register-context-menu" in sys.argv:
            settings = load_settings()
            settings["context_menu_enabled"] = True
            save_settings(settings)
            register_context_menu()
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
                write_context_log(fmt if 'fmt' in locals() else '', paths if 'paths' in locals() else [], '', traceback.format_exc())
                raise
            return
        App().mainloop()
    except Exception as e:
        log = data_dir() / "error.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            messagebox.showerror("EXIFコピー エラー", f"{e}\n\n詳細: {log}")
        except Exception:
            pass


if __name__ == "__main__":
    main()

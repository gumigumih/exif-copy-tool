from pathlib import Path


repo_root = Path.cwd()

files = [
    str(repo_root / "dist" / "ExifCopyTool.app"),
    str(repo_root / "packaging" / "macos" / "クイックアクションをインストール.command"),
]

symlinks = {"Applications": "/Applications"}

background = str(repo_root / "packaging" / "macos" / "assets" / "dmg-background.png")
window_rect = ((120, 120), (750, 500))
icon_size = 92
text_size = 12
icon_locations = {
    "ExifCopyTool.app": (130, 250),
    "Applications": (375, 250),
    "クイックアクションをインストール.command": (620, 250),
}

format = "UDZO"
compression_level = 9
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False

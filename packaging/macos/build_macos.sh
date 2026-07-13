#!/bin/zsh
set -euo pipefail

ROOT_DIR=${0:A:h}/../..
cd "$ROOT_DIR"

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "macOS版のビルドにはApple Silicon (arm64) が必要です。" >&2
  exit 1
fi

export MACOSX_DEPLOYMENT_TARGET=13.0

python3 -c 'import tkinter; assert tkinter.TkVersion >= 8.6, "Tk 8.6以降が必要です（古いTkでは画面が白紙になります）"'

rm -rf build/ExifCopyTool dist/ExifCopyTool.app
mkdir -p build/macos
xcrun swiftc \
  -target arm64-apple-macos13.0 \
  -module-cache-path /tmp/exif-copy-tool-swift-module-cache \
  -framework AppKit \
  packaging/macos/ExifCopyService.swift \
  -o build/macos/ExifCopyService

icon_args=()
if [[ -f assets/ExifCopyTool.icns ]]; then
  icon_args=(--icon assets/ExifCopyTool.icns --add-data assets/ExifCopyTool.icns:assets)
fi

data_args=(--add-data build/macos/ExifCopyService:packaging/macos)

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --argv-emulation \
  --target-arch arm64 \
  --name ExifCopyTool \
  --osx-bundle-identifier com.gumigumih.exif-copy-tool \
  "${icon_args[@]}" \
  "${data_args[@]}" \
  exif_context_app.py

codesign --force --deep --sign - dist/ExifCopyTool.app

chmod +x packaging/macos/クイックアクションをインストール.command
rm -f dist/ExifCopyTool-macOS.dmg
python3 -m dmgbuild \
  -s packaging/macos/dmg_settings.py \
  "ExifCopyTool Installer" \
  dist/ExifCopyTool-macOS.dmg

echo "Created dist/ExifCopyTool-macOS.dmg"

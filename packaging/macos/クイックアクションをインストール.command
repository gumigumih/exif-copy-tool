#!/bin/zsh
set -euo pipefail

if [[ ! -d /Applications/ExifCopyTool.app ]]; then
  osascript -e 'display alert "ExifCopyToolが見つかりません" message "先にExifCopyTool.appをApplicationsへドラッグしてください。"'
  exit 1
fi

"/Applications/ExifCopyTool.app/Contents/MacOS/ExifCopyTool" --install-finder-services
/usr/bin/killall sharedfilelistd 2>/dev/null || true
/usr/bin/killall Finder 2>/dev/null || true

osascript -e 'display notification "フォーマットごとの項目をFinderのサービスから利用できます" with title "EXIFコピーをインストールしました"'

ExifCopyTool
================

Windowsの右クリックメニューから、ファイルのEXIF情報をテンプレート形式でコピーするツールです。

■ 普通に使う場合
1. build_windows.bat を実行
2. dist\ExifCopyTool.exe を起動
3. 「有効にする」にチェック
4. 任意のファイルを右クリック → EXIF情報をコピー → フォーマットを選択

■ 右クリック登録
- 登録先は HKCU\Software\Classes\*\shell\ExifCopyTool と HKCU\Software\Classes\AllFilesystemObjects\shell\ExifCopyTool です
- EXIFが無いファイルを選んだ場合は、取得できる情報のみ、または空欄としてコピーされます

■ インストーラーを作る場合
1. Inno Setup 6 をインストール
   https://jrsoftware.org/isdl.php
2. build_windows.bat を実行
3. build_installer.bat を実行
4. installer\ExifCopyToolSetup.exe が作成されます

■ インストーラー版の挙動
- インストール先: %LOCALAPPDATA%\Programs\ExifCopyTool
- Python不要
- Windows起動時に常駐しません
- 右クリックした時だけ ExifCopyTool.exe が起動します
- アンインストール時に右クリックメニューも解除します
- 作者名: ぐみ ( meggumi.com )

■ exiftool.exe について
レンズ名やメーカー独自EXIFを安定して読むには、exiftool.exe を同梱してください。
インストーラー作成時は、このフォルダに exiftool.exe を置いてから build_installer.bat を実行すると同梱されます。


ExifCopyTool v12
================

Windowsの右クリックメニューから、ファイルのEXIF情報をテンプレート形式でコピーするツールです。

■ 普通に使う場合
1. build_windows.bat を実行
2. dist\ExifCopyTool.exe を起動
3. 「有効にする」にチェック
4. 任意のファイルを右クリック → EXIF情報をコピー → フォーマットを選択

■ v12の右クリック登録
- 拡張子指定機能は廃止しました
- デフォルトで「すべてのファイル」に表示します
- 登録先は HKCU\Software\Classes\*\shell\ExifCopyTool です
- フォルダには表示しません
- EXIFが無いファイルを選んだ場合は、取得できる情報のみ、または空欄としてコピーされます

■ インストーラーを作る場合
1. Inno Setup 6 をインストール
   https://jrsoftware.org/isdl.php
2. build_windows.bat を実行
3. build_installer.bat を実行
4. installer\ExifCopyToolSetup_v12.exe が作成されます

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

■ v12変更点
- 拡張子登録機能を削除
- デフォルトですべてのファイルに表示
- .arw などRAWの関連付けクラス問題を回避
- v10/v11で登録した拡張子別メニューは再登録時に削除

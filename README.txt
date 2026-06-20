EXIFコピー ツール
================

写真を右クリックして、登録したフォーマットでEXIF情報をクリップボードにコピーするWindows用ツールです。

前回版からの修正点
----------------
- 右クリック登録を「登録ボタン」ではなく「有効にする」チェックボックスに変更しました。
- チェックONで自動登録、OFFで自動解除します。
- フォーマット保存・追加・削除時、有効化済みなら右クリックメニューも自動更新します。
- 右クリック登録先を image 関連付けだけでなく、jpg/jpeg/png/tif/tiff/heic/webp 拡張子別にも追加しました。
- EXIF取得を ExifTool → exifread → Pillow の順で試すようにしました。
- 「EXIF診断」ボタンを追加しました。取得できている項目を確認できます。

使い方
------
1. Windowsで build_windows.bat を実行します。
2. dist\ExifCopyTool.exe ができます。
3. ExifCopyTool.exe を起動します。
4. 「有効にする」にチェックを入れます。
5. 写真ファイルを右クリックし、「EXIF情報をコピー」からフォーマットを選びます。

重要：EXIF取得について
----------------------
このツールは exifread / Pillow だけでも最低限のEXIFを読めますが、カメラやレンズ情報は写真・メーカーによって取れない場合があります。
一番確実にしたい場合は ExifTool を同梱してください。

ExifTool同梱方法：
- exiftool.exe を ExifCopyTool.exe と同じフォルダに置く
  または
- tools\exiftool.exe として置く

開発実行
--------
python -m pip install -r requirements.txt
python exif_context_app.py

ビルド
------
build_windows.bat

保存場所
--------
フォーマットと設定は以下に保存されます。
%APPDATA%\ExifCopyTool\formats.json
%APPDATA%\ExifCopyTool\settings.json

右クリック登録について
----------------------
管理者権限なしで使えるよう、HKCU配下に登録します。
Windows 11では「その他のオプションを表示」側に表示される場合があります。
表示されない場合は、一度アプリを起動して「有効にする」をOFF→ONしてください。

テンプレート例
--------------
{Make} {Model}
{LensModel}
{FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}
{DateTimeOriginal}

使える主な項目
--------------
{Make}
{Model}
{LensModel}
{FocalLength}
{FocalLengthIn35mmFormat}
{FNumber}
{ExposureTime}
{ISO}
{DateTimeOriginal}
{CreateDate}
{FileName}
{Artist}
{Copyright}
{Source}
{Error}

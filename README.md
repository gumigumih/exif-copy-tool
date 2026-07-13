# Exif Copy Tool

写真のEXIF情報を、右クリックからすばやくコピーできるWindows / macOS向けツールです。

## ダウンロード

最新版はGitHub Releasesからダウンロードできます。

- インストーラー版: https://github.com/gumigumih/exif-copy-tool/releases/latest/download/ExifCopyToolSetup.exe
- macOS版: https://github.com/gumigumih/exif-copy-tool/releases/latest/download/ExifCopyTool-macOS.dmg
- リリースページ: https://github.com/gumigumih/exif-copy-tool/releases/latest

通常はインストーラー版を使ってください。Pythonのインストールは不要です。

## こんな方におすすめ

- X（Twitter）やDiscordで撮影設定を共有したい
- ブログやレビュー記事に撮影データを掲載したい
- 毎回EXIFビューアーを開くのが面倒
- カメラ・レンズ情報を定型フォーマットでコピーしたい

## 特徴

### 右クリックですぐコピー

画像ファイルを右クリックするだけで、登録したフォーマットでEXIF情報をコピーできます。
Windows 11 でも右クリックメニューから利用できます。

### フォーマットを自由にカスタマイズ

撮影日時、カメラ、レンズ、ISO感度、シャッタースピードなど、必要な情報だけを組み合わせて出力できます。

例:

```text
📷 SONY ILCE-7CR
🔭 FE 20-70mm F4 G
⚙️ 70mm / F4 / 1/20 / ISO100
```

### インストール後すぐ使える

面倒な設定は不要です。インストールするだけで右クリックメニューから利用できます。

### Windows / macOS対応

Windows 10 / Windows 11とmacOSに対応します。macOSではFinderの「サービス」から、フォーマットごとのコピー項目を選べます。

## 使い方

1. `ExifCopyToolSetup.exe` をダウンロードしてインストールします。
2. 写真ファイルを右クリックします。
3. 「EXIF情報をコピー」から使いたいフォーマットを選びます。
4. 整形されたEXIF情報がクリップボードへコピーされます。

### macOS

1. `ExifCopyTool-macOS.dmg` を開き、`ExifCopyTool.app` をApplicationsへドラッグします。
2. DMG内の `クイックアクションをインストール.command` を実行します。

インストール後は、Finderで写真を右クリックし、「サービス」から `EXIFコピー：撮影設定` など使いたいフォーマットを選びます。

フォーマットを追加・削除・名前変更して保存すると、Finderのサービスも自動更新されます。

初回起動時にmacOSの警告が表示された場合は、FinderでアプリをControlキーを押しながらクリックして「開く」を選択してください。

## フォーマット編集

設定画面の「フォーマット編集」タブで、コピー内容を自由に編集できます。

よく使うタグ:

- `{Make}`: メーカー
- `{Model}`: カメラ名
- `{LensModel}`: レンズ名
- `{FocalLength}`: 焦点距離
- `{FNumber}`: F値
- `{ExposureTime}`: シャッタースピード
- `{ISO}`: ISO感度
- `{DateTimeOriginal}`: 撮影日時
- `{FileName}`: ファイル名

## 対応ファイル形式

右クリックメニューは拡張子で絞り込まずに表示します。

主な想定ファイル:

- 一般的な画像: JPEG / PNG / TIFF / HEIC / WebP
- RAWファイル: ARW / CR2 / CR3 / NEF / RAF / ORF / RW2 / DNG など

EXIF情報は、ファイルや環境によって取得できる項目が変わります。取得できた項目だけを使ってコピーします。

## 利用シーン

### SNS投稿

撮影設定を添えて写真を投稿したいとき。

### 写真コミュニティ

Discordやフォーラムで撮影データを共有したいとき。

### ブログ執筆

レビュー記事や撮影記録の作成時。

## 動作環境

- Windows 10
- Windows 11
- macOS 13以降（Apple Silicon）

## インストール先と動作

- インストール先: `%LOCALAPPDATA%\Programs\ExifCopyTool`
- Windows起動時に常駐しません。
- 右クリックした時だけアプリが起動します。
- コピー結果はWindows通知で表示されます。
- アンインストール時に右クリックメニューも解除します。

macOSでは設定を `~/Library/Application Support/ExifCopyTool` に保存します。ネイティブFinderサービスは `~/Library/Services` にインストールされます。

## 作者

ぐみ ( meggumi.com )

## 開発者向け

### ローカルビルド

Python と Inno Setup 6 が入っている Windows 環境でビルドできます。

```bat
packaging\windows\build_windows.bat
packaging\windows\build_installer.bat
```

作成されるファイル:

- アプリ本体: `dist\ExifCopyTool\ExifCopyTool.exe`
- インストーラー: `installer\ExifCopyToolSetup.exe`

配布版はセキュリティソフトで警告される場合があります。Python 環境がある場合は、ローカルでビルドするとダウンロード由来の警告を避けられることがあります。ただし、署名なしアプリのため環境によっては自ビルドでも警告される場合があります。

### 配布サイト

macOSでビルドする場合:

```bash
brew install python-tk
python3 -m pip install -r requirements.txt
./packaging/macos/build_macos.sh
```

Tk 8.6以降が必要です。`dist/ExifCopyTool-macOS.dmg` が作成されます。正式配布にはApple Developer IDによる署名と公証を推奨します。

サイト更新:

```bash
npm install
npm run build:site
```

ホットリロード確認:

```bash
npm run dev:site
```

`http://127.0.0.1:4173` で配布サイトを確認できます。

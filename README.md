# Exif Copy Tool

写真のEXIF情報を、右クリックからすばやくコピーできるWindows向けツールです。

## ダウンロード

最新版はGitHub Releasesからダウンロードできます。

- インストーラー版: https://github.com/gumigumih/exif-copy-tool/releases/latest/download/ExifCopyToolSetup.exe
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
Windows 11 では、新しいコンパクト右クリックメニューと「その他のオプション」の両方に登録します。

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

### Windows専用

Windows 10 / Windows 11 対応です。

## 使い方

1. `ExifCopyToolSetup.exe` をダウンロードしてインストールします。
2. 写真ファイルを右クリックします。
3. 「EXIF情報をコピー」から使いたいフォーマットを選びます。
4. 整形されたEXIF情報がクリップボードへコピーされます。

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

## インストール先と動作

- インストール先: `%LOCALAPPDATA%\Programs\ExifCopyTool`
- Windows起動時に常駐しません。
- 右クリックした時だけアプリが起動します。
- コピー結果はWindows通知で表示されます。
- アンインストール時に右クリックメニューも解除します。

## 作者

ぐみ ( meggumi.com )

## 開発者向け

ローカルでビルドする場合:

```bat
build_windows.bat
build_installer.bat
```

`installer\ExifCopyToolSetup.exe` が作成されます。

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

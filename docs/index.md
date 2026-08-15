---
layout: page
title: chatlog
---

**Slack / Discord のチャンネルログを取得して JSON に蓄積し、ブラウザで閲覧するツール。**差分取得で少しずつ追記していき、ログが大きくなったらファイルの分割・統合もできます。

- ソース: [github.com/sekika/chatlog](https://github.com/sekika/chatlog)
- **ライブデモ: [デモを開く]({{ '/demo/' | relative_url }})**（`#general` は Discord、`#random` は Slack のサンプルデータ）

[![chatlog viewer のプレビュー]({{ '/preview.png' | relative_url }})]({{ '/demo/' | relative_url }})

---

## 特徴

- **Slack と Discord の両方**に対応（設定ファイルの `service` で選択）。
- 保存済みの**最新メッセージ以降だけを差分取得**。実行のたびに差分だけが追記される。
- 添付ファイルは**ファイル名だけ**を記録（本体は取得しない）。
- ブラウザ用ビューア付き（チャンネル切替・日付ジャンプ・全ログ・検索）。
- ログが大きくなったら**分割**でき、初期表示が速くなる（いつでも統合して元に戻せる＝可逆）。
- パッケージ不要。`chatlog.py` を直接コマンドから実行するだけ。

## 使い方の流れ

1. **[ログの取得]({{ '/collect/' | relative_url }})** — `chatlog.py` で Slack / Discord のチャンネルを取得し、JSON に蓄積する。
2. **[ログの分割・統合]({{ '/split/' | relative_url }})** — 大きくなった JSON を分割して初期表示を速くする（可逆）。
3. **[ビューア]({{ '/viewer/' | relative_url }})** — 蓄積した JSON をブラウザで閲覧する。
4. **[JSON の形式]({{ '/json/' | relative_url }})** — 蓄積されるデータ構造のリファレンス。

## 動作環境

- Python 3 系
- Slack を取得する場合: Slack API トークン。追加ライブラリは不要。
- Discord を取得する場合: Discord Bot トークンと `discord` ライブラリ（`python3 -m pip install discord`）。`discord` は Discord 取得時にのみ読み込むので、Slack だけ使うなら未インストールで構いません。

## インストール

```
git clone https://github.com/sekika/chatlog.git
cd chatlog
```

続いて **[ログの取得]({{ '/collect/' | relative_url }})** に進みます。

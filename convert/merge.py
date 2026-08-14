#!/usr/bin/env python3
# coding:utf-8
#
# 分割形式(マニフェスト + チャンク)の <channel>.json を単一形式へ統合する。
#   python3 convert/merge.py <path/to/channel.json> [--keep-chunks]
#
# - 入力は分割形式(chunks を持つ)のエントリ JSON のパス。
# - chunks に列挙されたチャンクを ts 順に結合し、エントリ JSON を単一形式
#   (messages を持つ)へ書き換える。
# - チャンクファイルは削除する(--keep-chunks を付けると残す)。
# - split.py で分割したものを元に戻す(可逆)。

import json
import os
import sys


def main(path, keep):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'chunks' not in data:
        print('already merged (single file): ' + path)
        return

    dirname = os.path.dirname(path)
    chunk_files = [c['file'] for c in data.get('chunks', [])]
    messages = []
    for fname in chunk_files:
        with open(os.path.join(dirname, fname), 'r', encoding='utf-8') as cf:
            messages.extend(json.load(cf).get('messages', []))
    messages.sort(key=lambda m: float(m['ts']))

    # エントリ JSON を単一形式へ書き換える。
    single = {
        'channel': data.get('channel', ''),
        'messages': messages,
        'users': data.get('users', {}),
    }
    # どの取得元(slack/discord)で作った JSON かはビューアの描画切替に使うので通す
    if 'service' in data:
        single['service'] = data['service']
    if 'retrievedAt' in data:
        single['retrievedAt'] = data['retrievedAt']
    if 'error' in data:
        single['error'] = data['error']

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(single, f, ensure_ascii=False, indent=2)
        f.write('\n')

    if not keep:
        for fname in chunk_files:
            p = os.path.join(dirname, fname)
            if os.path.exists(p):
                os.remove(p)

    print('merged %s <- %d chunks (%d messages)' % (path, len(chunk_files), len(messages)))


if __name__ == '__main__':
    args = sys.argv[1:]
    keep = False
    path = None
    for a in args:
        if a == '--keep-chunks':
            keep = True
        else:
            path = a
    if path is None:
        print('usage: python3 convert/merge.py <path/to/channel.json> [--keep-chunks]')
        sys.exit(1)
    main(path, keep)

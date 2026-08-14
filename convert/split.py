#!/usr/bin/env python3
# coding:utf-8
#
# 単一形式の <channel>.json を、マニフェスト + 期間チャンクに分割する。
#   python3 convert/split.py <path/to/channel.json> [--by year|month] [--force]
#
# - 入力は単一形式(messages を持つ)のエントリ JSON のパス。
# - エントリ JSON をマニフェスト(chunks を持つ)へ書き換え、
#   本体を <channel>.<period>.json(既定は年単位)へ分割して同じディレクトリに置く。
# - 既に分割済み(chunks を持つ)の場合は何もしない。--force で粒度変更などの再分割ができる。
# - merge.py で元の単一形式へ戻せる(可逆)。
#
# slacklog.py の出力(messages[].ts が Slack のタイムスタンプ文字列
# "1721400000.000100")にそのまま対応する。ts は float() でエポック秒として扱える。

import json
import os
import sys
from datetime import datetime, timedelta, timezone

# 表示は日本時間(JST = UTC+9)。分割の期間・日付も JST で決める。
JST = timezone(timedelta(hours=9))


def jst_dt(ts):
    return datetime.fromtimestamp(float(ts), tz=JST)


def jst_date(ts):
    return jst_dt(ts).strftime('%Y/%m/%d')


# メッセージの ts から所属期間キーを返す(year: "2022" / month: "2022-01")
def period_key(ts, by):
    d = jst_dt(ts)
    if by == 'month':
        return '%04d-%02d' % (d.year, d.month)
    return '%04d' % d.year


# エントリ JSON を読み、(data, 全 messages, 既に分割済みか) を返す。
# 分割済みならチャンクを読んで messages を復元する。
def load_entry(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    dirname = os.path.dirname(path)
    if 'chunks' in data:
        messages = []
        for c in data['chunks']:
            with open(os.path.join(dirname, c['file']), 'r', encoding='utf-8') as cf:
                messages.extend(json.load(cf).get('messages', []))
        return data, messages, True
    return data, data.get('messages', []), False


def main(path, by, force):
    data, messages, was_split = load_entry(path)
    if was_split and not force:
        print('already split: ' + path + ' (use --force to re-split)')
        return

    dirname = os.path.dirname(path)
    base = os.path.basename(path)
    if base.endswith('.json'):
        base = base[:-5]

    # 再分割時は古いチャンクを削除してから作り直す(粒度変更で名前が変わるため)
    if was_split:
        for c in data.get('chunks', []):
            p = os.path.join(dirname, c['file'])
            if os.path.exists(p):
                os.remove(p)

    # 期間ごとに bucketing
    buckets = {}
    for m in messages:
        buckets.setdefault(period_key(m['ts'], by), []).append(m)

    chunks = []
    max_ts = None
    for period in sorted(buckets):
        msgs = sorted(buckets[period], key=lambda m: float(m['ts']))
        fname = base + '.' + period + '.json'
        with open(os.path.join(dirname, fname), 'w', encoding='utf-8') as f:
            json.dump({'messages': msgs}, f, ensure_ascii=False, indent=2)
            f.write('\n')
        dates = sorted({jst_date(m['ts']) for m in msgs})
        chunks.append({
            'file': fname,
            'from': msgs[0]['ts'],
            'to': msgs[-1]['ts'],
            'count': len(msgs),
            'dates': dates,
        })
        if max_ts is None or float(msgs[-1]['ts']) > float(max_ts):
            max_ts = msgs[-1]['ts']

    # エントリ JSON をマニフェストへ書き換える。
    # users / retrievedAt / error は全ビュー共通なのでマニフェストに残す。
    manifest = {
        'channel': data.get('channel', base),
        'format': 2,
        'by': by,
        'users': data.get('users', {}),
        'chunks': chunks,
    }
    # どの取得元(slack/discord)で作った JSON かはビューアの描画切替に使うので通す
    if 'service' in data:
        manifest['service'] = data['service']
    if max_ts is not None:
        manifest['maxTs'] = max_ts
    if 'retrievedAt' in data:
        manifest['retrievedAt'] = data['retrievedAt']
    if 'error' in data:
        manifest['error'] = data['error']

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print('split %s -> %d chunks (%d messages)' % (path, len(chunks), len(messages)))


if __name__ == '__main__':
    args = sys.argv[1:]
    by = 'year'
    force = False
    path = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--by':
            i += 1
            by = args[i]
        elif a.startswith('--by='):
            by = a.split('=', 1)[1]
        elif a == '--force':
            force = True
        else:
            path = a
        i += 1
    if path is None or by not in ('year', 'month'):
        print('usage: python3 convert/split.py <path/to/channel.json> [--by year|month] [--force]')
        sys.exit(1)
    main(path, by, force)

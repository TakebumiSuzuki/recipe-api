#!/bin/sh
# Claude Code から JSON を stdin で受け取り、ステータスライン1行を stdout に出力する。
# 値の組み立て・配色・git ブランチ取得まで全て python 側で行い、シェルの eval を使わない
# (パスやブランチ名にシェルメタ文字が含まれても壊れない/コマンドが実行されないようにするため)。
python3 -c "
import sys, json, subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

try:
    d = json.load(sys.stdin)
except Exception:
    d = {}

# Colors
RESET   = '\033[0m'
CYAN    = '\033[36m'
MAGENTA = '\033[35m'
GREEN   = '\033[32m'
ORANGE  = '\033[38;5;208m'
RED     = '\033[31m'
YELLOW  = '\033[33m'
GRAY    = '\033[90m'

def pct(val):
    if val is None:
        return '--'
    return str(int(val))

BANGKOK_TZ = ZoneInfo('Asia/Bangkok')

def fmt_time(epoch, fmt, miss):
    if not epoch:
        return miss
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(BANGKOK_TZ).strftime(fmt)

def ctx_color(p):
    if p == '--':
        return GRAY
    p = int(p)
    if p >= 80: return RED
    if p >= 50: return ORANGE
    return GREEN

def rl_color(p):
    if p == '--':
        return GRAY
    p = int(p)
    if p >= 80: return RED
    if p >= 50: return ORANGE
    return GRAY

EFFORT_COLORS = {
    'low':   GRAY,
    'medium': CYAN,
    'high':  GREEN,
    'xhigh': ORANGE,
    'max':   RED,
}
EFFORT_LABELS = {
    'low':   'low',
    'medium': 'med',
    'high':  'high',
    'xhigh': 'xhigh',
    'max':   'MAX',
}

cwd = d.get('cwd', '')
model = (d.get('model') or {}).get('display_name', '...')
effort_level = (d.get('effort') or {}).get('level')  # Optional: only present when model supports reasoning

ctx = d.get('context_window') or {}
ctx_pct = pct(ctx.get('used_percentage'))

rl_obj = d.get('rate_limits') or {}
rl = rl_obj.get('five_hour') or {}
rl_pct = pct(rl.get('used_percentage'))
rl_time = fmt_time(rl.get('resets_at'), '%H:%M', '--:--')

rl7 = rl_obj.get('seven_day') or {}
rl7_pct = pct(rl7.get('used_percentage'))
rl7_time = fmt_time(rl7.get('resets_at'), '%-m/%-d %H:%M', '--')

cost_val = (d.get('cost') or {}).get('total_cost_usd')

# Git branch (cwd は引数として安全に渡すので eval/シェル展開は発生しない)
branch = ''
if cwd:
    try:
        branch = subprocess.run(
            ['git', '-C', cwd, 'symbolic-ref', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
    except Exception:
        branch = ''

# Build output
out = '🤖 ' + MAGENTA + model + RESET
if effort_level:
    ecol = EFFORT_COLORS.get(effort_level, GRAY)
    elab = EFFORT_LABELS.get(effort_level, effort_level)
    out += '  ⚡' + ecol + elab + RESET
if branch:
    out += '  ⎇ ' + CYAN + branch + RESET
out += '  📊 ctx:' + ctx_color(ctx_pct) + ctx_pct + '%' + RESET
out += ('  ⏱ 5h:' + rl_color(rl_pct) + rl_pct + '%' + RESET + '(→' + rl_time + ')'
        + ' 7d:' + rl_color(rl7_pct) + rl7_pct + '%' + RESET + '(→' + rl7_time + ')')
if cost_val is None:
    out += '  💰 ' + GRAY + '\$--' + RESET
else:
    out += '  💰 ' + YELLOW + '\${:.4f}'.format(cost_val) + RESET

sys.stdout.write(out)
"

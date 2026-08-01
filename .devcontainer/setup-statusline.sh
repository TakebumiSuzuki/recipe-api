#!/bin/sh
# postCreateCommand から呼ばれ、コンテナ内ユーザースコープに statusLine を配備する。
# - ~/.claude/settings.json に statusLine キーを jq でマージ(既存設定は保持)
# - command にはリポジトリ内スクリプトの絶対パスを直接書く。実体は bind mount 上に
#   あるため、リポジトリ側を編集すれば即反映され、コンテナ再ビルドは不要。
set -e

CLAUDE_DIR="$HOME/.claude"
SETTINGS="$CLAUDE_DIR/settings.json"
STATUSLINE_SRC="/workspaces/cc-dev-container/.devcontainer/statusline-command.sh"

mkdir -p "$CLAUDE_DIR"

STATUSLINE_JSON="{\"type\":\"command\",\"command\":\"bash $STATUSLINE_SRC\"}"
if [ -f "$SETTINGS" ]; then
  tmp=$(mktemp)
  jq --argjson sl "$STATUSLINE_JSON" '.statusLine = $sl' "$SETTINGS" > "$tmp" && mv "$tmp" "$SETTINGS"
else
  jq -n --argjson sl "$STATUSLINE_JSON" '{statusLine: $sl}' > "$SETTINGS"
fi

echo "statusLine setup complete: $SETTINGS -> $STATUSLINE_SRC"

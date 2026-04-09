#!/bin/bash
# cron_runner.sh — invoked by crontab to run a skill in headless mode
#
# Usage: cron_runner.sh <prompt> <job_id>
#
# 1. Runs claude -p with the given prompt
# 2. If Telegram is configured, pushes the output
# 3. Logs to ~/.claude/logs/skill-cron/

set -euo pipefail

PROMPT="$1"
JOB_ID="${2:-unknown}"
CONFIG_FILE="$HOME/.claude/configs/skill-cron.json"
LOG_DIR="$HOME/.claude/logs/skill-cron"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${LOG_DIR}/${JOB_ID}-${TIMESTAMP}.log"

mkdir -p "$LOG_DIR"

echo "[${TIMESTAMP}] Running job: ${JOB_ID}" | tee "$LOG_FILE"

# Run claude in headless mode
OUTPUT=$(claude -p "$PROMPT" --allowedTools "Bash,Read,Glob,Grep" 2>>"$LOG_FILE") || {
    echo "[error] claude -p failed" | tee -a "$LOG_FILE"
    exit 1
}

echo "$OUTPUT" >> "$LOG_FILE"

if [ -z "$OUTPUT" ]; then
    echo "[warn] no output from claude" | tee -a "$LOG_FILE"
    exit 0
fi

# Push to Telegram if configured
if [ -f "$CONFIG_FILE" ]; then
    BOT_TOKEN=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('telegram',{}).get('bot_token',''))" 2>/dev/null)
    CHANNEL_ID=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('telegram',{}).get('channel_id',''))" 2>/dev/null)

    if [ -n "$BOT_TOKEN" ] && [ -n "$CHANNEL_ID" ]; then
        # Truncate to Telegram limit (4096 chars)
        TG_TEXT=$(echo "$OUTPUT" | head -c 4080)

        curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "$(python3 -c "
import json, sys
text = sys.stdin.read()
print(json.dumps({
    'chat_id': '${CHANNEL_ID}',
    'text': text,
    'disable_web_page_preview': True
}))
" <<< "$TG_TEXT")" >> "$LOG_FILE" 2>&1

        echo "[telegram] sent" | tee -a "$LOG_FILE"
    fi
fi

# Cleanup old logs (keep last 50)
ls -t "$LOG_DIR"/${JOB_ID}-*.log 2>/dev/null | tail -n +51 | xargs rm -f 2>/dev/null

echo "[done] ${JOB_ID}" | tee -a "$LOG_FILE"

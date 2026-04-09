# skill-cron — 設計文件

## 解決什麼問題

Claude Code 的 skill 在互動模式下用 `/skill-name` 觸發很方便，但有些 skill 需要定時執行 + 推送通知（如每天追蹤某人的社群貼文並分析）。

**問題：`claude -p` 非互動模式不支援 `/skill` 語法調用。**

官方文件明確說明：

> "User-invoked skills like `/commit` are only available in interactive mode. In `-p` mode, describe the task you want to accomplish instead."

這意味著 crontab 不能直接跑 `claude -p "/banini"`。

## 設計思路

### 職責分離

```
Skill（如 /banini）
  = 純核心功能：爬蟲 + 分析 + 輸出
  = 互動模式用 /banini 觸發
  = 不管排程、不管通知

skill-cron（管理器）
  = 排程管理：註冊/移除/啟停 crontab jobs
  = 通知管理：Telegram bot token 存取
  = 執行橋接：把 skill 的 headless-prompt 餵給 claude -p
```

### headless-prompt 規範

為了讓 skill 支援非互動排程，在 SKILL.md 的 YAML frontmatter 中加入 `headless-prompt` 欄位：

```yaml
---
name: banini
headless-prompt: "Run python3 ~/.claude/skills/banini/scripts/... then analyze..."
---
```

規則：
- **必須使用絕對路徑**（`~` 可以，`${CLAUDE_SKILL_DIR}` 不行 — 非互動模式不展開）
- **不能使用 `/skill` 語法**
- **要包含完整指令**（Claude 在 `-p` 模式下沒有 SKILL.md 的上下文）

### 執行鏈

```
crontab entry
  → cron_runner.sh <prompt> <job_id>
    → claude -p "<prompt>" --allowedTools "Bash,Read,Glob,Grep"
    → 拿到輸出
    → 如有 Telegram config → curl 推送
    → 寫 log
```

## 設定檔位置

`~/.claude/configs/skill-cron.json`

選這個位置的原因：
- `~/.claude/` 已存在（Claude Code 的設定目錄）
- 不會被 git 追蹤（存有 Telegram bot token）
- `configs/` 子目錄語意明確
- 比 `~/.config/skill-cron/` 更貼近 Claude Code 生態系

## Crontab 管理

skill-cron 在系統 crontab 中用標記區塊管理自己的 entries：

```crontab
# 使用者自己的 crontab entries...

# SKILL-CRON-BEGIN — managed by skill-cron, do not edit
7,37 9-12 * * 1-5 /path/to/cron_runner.sh 'prompt...' 'banini-盤中'
3 23 * * * /path/to/cron_runner.sh 'prompt...' 'banini-盤後'
# SKILL-CRON-END
```

這樣不會干擾使用者自己的 crontab entries。

## 日誌

`~/.claude/logs/skill-cron/{job_id}-{timestamp}.log`

每個 job 保留最近 50 筆，自動清理舊的。

## 支援 skill-cron 的 skill 清單

| Skill | headless-prompt | 建議排程 |
|-------|----------------|---------|
| [banini](../banini-tracker/) | Threads 爬蟲 + 反指標分析 | 盤中 `7,37 9-12 * * 1-5`、盤後 `3 23 * * *` |

其他 skill 作者可以在 SKILL.md frontmatter 加入 `headless-prompt` 來支援排程。

## 限制

1. **需要 `claude` CLI 在 PATH 中** — crontab 的 PATH 可能不包含，cron_runner.sh 可能需要指定完整路徑
2. **需要有效的 Claude 訂閱** — `claude -p` 需要認證
3. **本地執行限制** — 排程跑在本地機器上，關機就不跑
4. **Telegram 4096 字元限制** — 超長報告會被截斷

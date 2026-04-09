# banini-tracker Skill — 設計文件

## 為什麼要改寫

### 原始專案

[cablate/banini-tracker](https://github.com/cablate/banini-tracker) 是一個 Node.js + TypeScript 專案，用來追蹤巴逆逆（8zz）的 Threads / Facebook 貼文，透過 LLM API 進行「反指標」投資分析，並將結果推送到 Telegram。

原始架構：

```
Apify API（付費爬蟲平台）
  → 抓 Threads + Facebook 貼文
  → 呼叫 LLM API（DeepInfra / MiniMax-M2.5）
  → 反指標分析
  → Telegram 通知
```

### 原始專案的成本問題

| 項目 | 月費 |
|------|------|
| Apify Threads Scraper | ~$4.5 |
| Apify Facebook Scraper | ~$6 |
| DeepInfra LLM API | ~$1 |
| **合計** | **~$11/月** |

對於一個娛樂性質的追蹤器來說，每月 $11 美元的持續支出不太合理。

### 核心洞察

1. **Apify 本質就是無頭瀏覽器** — 它的 Threads Scraper 底層是 Puppeteer + GraphQL 攔截。這件事我們可以用開源的 Playwright 在本地做到，完全免費。

2. **LLM API 可以省掉** — 如果使用者已經訂閱 Claude Max，Claude Code 本身就是最強的 LLM。把分析邏輯寫成 skill prompt，讓 Claude 直接讀貼文分析，不需要再呼叫外部 LLM API。

3. **Facebook 可以砍掉** — 巴逆逆的 FB 粉專貼文與 Threads 內容高度重複，且 FB 的反爬機制遠比 Threads 嚴格。只追蹤 Threads 就夠了。

---

## 我們做了什麼修正

### 架構改寫

```
原始：Apify（付費）→ LLM API（付費）→ Telegram
改寫：Playwright（免費）→ Claude 直接分析（Max 訂閱內）→ 對話輸出
```

### 具體變更

#### 1. 用 Playwright 取代 Apify（省下 $10.5/月）

- 自寫 `scripts/scrape_threads.py`，使用 Playwright 無頭 Chromium
- 技術原理：導覽到 Threads 個人頁面，攔截背景的 GraphQL 回應，直接 parse 結構化貼文資料
- 不需要任何 API key 或付費服務
- 在家用網路（非 datacenter IP）上穩定運作
- 實測可抓 10-20 篇貼文，足夠分析用

#### 2. 用 Claude 自身取代 LLM API（省下 $1/月）

- 原始專案用 OpenAI SDK 呼叫 DeepInfra 的 MiniMax-M2.5 模型
- 改為 Claude Code skill：Claude 自己讀完貼文直接分析
- 分析品質大幅提升（Claude Opus >> MiniMax-M2.5）
- 不受固定 JSON schema 限制，輸出更靈活詳細

#### 3. 砍掉 Facebook 來源

- 原因：FB 反爬極強，開源方案難以穩定抓取
- 影響：極低，巴逆逆的投資相關貼文在 Threads 上都有

#### 4. 簡化輸出

- 原始專案將結果存為 JSON 檔 + 推送 Telegram
- 改為直接在 Claude Code 對話中輸出分析報告
- 使用者在對話中即可看到完整分析，不需要切到 Telegram

### 保留的核心邏輯

以下從原始專案的 `src/analyze.ts` 中提取並保留：

- **反指標規則表**（買入→可能跌、停損→可能漲、被套→續跌 等）
- **被套 vs 停損的方向區分**（這是原作者特別標注的重要邏輯）
- **連鎖效應推導**（A 漲/跌 → 影響 B → 影響 C）
- **冥燈指數**（語氣篤定程度 → 反指標信號強度）
- **時序意識**（當天貼文最重要，最新的為準）

---

## 成本比較

| | 原始專案 | 本 Skill |
|---|---|---|
| 爬蟲 | Apify ~$10.5/月 | Playwright 本地執行，免費 |
| LLM | DeepInfra API ~$1/月 | Claude Max 訂閱內，免費 |
| 部署 | 需要長駐 Node.js 程式 | 隨時 `/banini` 即跑 |
| 分析品質 | MiniMax-M2.5（中等） | Claude Opus（頂級） |
| **月成本** | **~$11** | **$0** |

---

## 技術選型

### 為什麼用 Playwright 而不是其他方案

| 方案 | 結論 | 原因 |
|------|------|------|
| WebFetch / curl | 不可行 | Threads 是純 client-side rendering，抓到的只有空殼 CSS |
| Meta Threads 官方 API | 可行但麻煩 | 需要申請 Meta 開發者帳號 + OAuth token |
| RSSHub / RSS-Bridge | 不穩定 | Threads bridge 目前被列為 broken |
| Playwright | 採用 | 開源、免費、模擬真實瀏覽器、可攔截 GraphQL |

### 爬蟲的工作原理

1. Playwright 啟動無頭 Chromium
2. 導覽到 `https://www.threads.com/@{username}`
3. 註冊 response 事件監聽器，過濾含 `graphql` 或 `barcelona` 的 URL
4. 自動向下捲動頁面，觸發更多貼文載入
5. 從 GraphQL response 中用 `nested_lookup` 提取 `post` 和 `thread_items` 物件
6. 解析為結構化資料（文字、讚數、回覆數、時間戳）
7. 同時嘗試從 HTML 內嵌的 `<script>` JSON 中提取資料（雙重保險）

### 依賴

| 套件 | 用途 |
|------|------|
| `playwright` | 無頭瀏覽器自動化 |
| `parsel` | HTML 解析（提取 `<script>` 資料） |
| `nested_lookup` | 遞迴搜尋巢狀 JSON 中的特定 key |
| `jmespath` | JSON 查詢（備用） |

---

## 限制與已知問題

1. **Threads 可能改版** — GraphQL 結構或 DOM 改變可能導致爬蟲失效，需要更新 parse 邏輯
2. **IP 封鎖風險** — 高頻抓取可能被 Threads 封鎖 IP，但正常使用（每天幾次）不會觸發
3. **無法抓純圖片內容** — 只能抓文字，圖片中的文字需要 OCR（原始專案透過 Apify 的 FB Scraper 有 OCR）
4. **無自動排程** — 原始專案有 node-cron 排程，本 skill 需手動執行 `/banini`

---

## 參考

- 原始專案：[cablate/banini-tracker](https://github.com/cablate/banini-tracker)
- 爬蟲參考：[vdite/threads-scraper](https://github.com/vdite/threads-scraper)（Playwright + GraphQL 攔截技術）
- Apify 開源 Threads scraper 技術分析：[the-ai-entrepreneur-ai-hub/threads-scraper](https://github.com/the-ai-entrepreneur-ai-hub/threads-scraper)（Puppeteer + CDP 攔截，同原理）

# goals-iterm-skill

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

讓支援 skill 的 coding agent 透過 [goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp) 指揮 iTerm2 中的 Claude Code、Codex 等 CLI，持續監控進度、提供決策建議並驗收任務。

## 透過 coding agent 安裝

將下方提示詞複製給可以存取本機檔案系統的 coding agent，將 `[目標用戶端]` 替換為需要安裝 skill 的用戶端。已有本機儲存庫時，也可以將儲存庫 URL 替換為本機絕對路徑。

```text
請將 goals-iterm-skill 安裝到 [目標用戶端]。
儲存庫網址：https://github.com/lucky-goals/goals-iterm-skill

1. 檢查目標用戶端的現有設定及支援的 skill 安裝機制，依照其文件確認安裝位置
   與適用範圍，不要猜測設定路徑。
2. 取得儲存庫，或使用我指定的本機目錄。檢查 SKILL.md 及其引用檔案；儲存庫
   根目錄就是 skill 套件。
3. 以 goals-iterm-skill 為目錄名稱安裝，保留 SKILL.md、references/ 和 agents/，
   不要只複製 SKILL.md。已有安裝時先比較差異、保留本機修改並在更新前備份，
   不影響其他 skill。
4. 檢查目標用戶端是否已連接 goals-iterm-mcp。安裝 skill 不等於安裝 MCP 服務；
   若缺少，說明前置條件並提供設定指引，不要更動無關的 MCP 設定。
5. 驗證 skill 中繼資料與相對引用。依用戶端支援的方式重新載入，若需手動操作，
   明確告訴我步驟；能夠檢查時，確認目標用戶端確實已辨識此 skill。
6. MCP 可用時，驗證工具探索並僅用 list_sessions 檢查連線。安裝期間不要讀取
   終端內容、傳送輸入、建立視窗或啟動 coding 任務。
7. 回報安裝路徑、skill 辨識狀態、MCP 就緒情況，以及可用的監控模式：宿主排程/
   喚醒，或 agent 目前執行中的輪詢。沒有實際喚醒機制時，不要宣稱支援背景監控。
```

## 前置條件與手動安裝

本儲存庫根目錄就是一個 skill 套件。透過宿主用戶端支援的 skill 安裝機制，將整個目錄安裝為 `goals-iterm-skill`，保留 `SKILL.md`、`references/` 和 `agents/`，確保相對引用有效。安裝位置與重新載入步驟以目標用戶端文件及現有設定為準。

本 skill 不會安裝 MCP 或提供獨立背景服務。使用前需在宿主中連接 goals-iterm-mcp、啟用 iTerm2 Python API，並在目標終端準備好 CLI 及驗證設定。所需工具至少涵蓋工作階段列舉、畫面/歷史讀取、文字/按鍵傳送；新增終端還需要對應的建立工具。

持續監控依賴宿主提供的任務喚醒/排程，或 agent 目前執行中的輪詢。沒有背景喚醒能力的用戶端，無法在 agent 結束執行後繼續自動監控。skill 會要求明確回報這項限制。

## 使用範例

```text
使用 goals-iterm-skill，在 iTerm 中讓 Claude Code 修復 /path/to/project
的登入問題。先診斷再修復，只執行相關測試。每次發出指令後監控回應，
一般技術決策由你判斷，確定網路錯誤已中斷任務且不會自動繼續時恢復任務。
驗收完成後停止監控並彙整修改、測試及剩餘問題。不要發布。
```

也可以指定既有工作階段的暱稱來接手任務。skill 會先列舉並綁定正確的 `session_id`，避免重複派發仍在執行的任務。

## 維護與驗證

入口為 [SKILL.md](SKILL.md)，工具語義見 [iterm-tools.md](references/iterm-tools.md)，監控、恢復及行為驗收情境見 [monitoring.md](references/monitoring.md)。這些指令檔案目前使用簡體中文。工具約定依據 cc-iterm-mcp 的 `src/goals_iterm_mcp/direct.py`；執行時以實際安裝版本的 schema 為準。

修改後驗證 skill frontmatter 與相對引用，並推演監控協定末尾的情境。實際 CLI 驗證應使用專用測試工作階段，確認任務派發、決策、恢復及監控清理；靜態驗證不代表背景排程或實際 CLI 整合已通過。

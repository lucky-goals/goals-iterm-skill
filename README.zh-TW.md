# goals-iterm-skill

Skill 版本: [v0.2.0](https://github.com/lucky-goals/goals-iterm-skill/releases/tag/v0.2.0)

[專案官網](https://lucky-goals.github.io/goals-iterm-skill/)
[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

讓支援 skill 的 coding agent 透過 [goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp) 指揮 iTerm2 中的 Claude Code、Codex 等 CLI，持續監控進度、提供決策建議並驗收任務。

## 必要的 MCP：goals-iterm-mcp

本 skill 使用 **[lucky-goals/goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp)** 操作 iTerm2。請先在**負責協調的 agent 用戶端**中安裝並連接該 MCP，再安裝本 skill，最後使用下方任務提示詞。僅安裝 skill 不會提供終端工具。已有 MCP 連線時驗證即可，不必重複安裝。

準備順序：

1. 在執行終端的 Mac 上安裝並開啟 iTerm2，在 **Settings → General → Magic → Python API** 中啟用 API，並在出現授權視窗時批准連線。
2. 將 goals-iterm-mcp 設定為協調用戶端的本機 stdio 服務。用戶端必須能存取該 Mac；純雲端聊天無法直接操作本機 iTerm2。
3. 在 iTerm2 中安裝並完成 Claude Code、Codex 或其他目標 CLI 的驗證設定，確認新分頁中也能正常啟動。不要將憑證寫進提示詞。
4. 驗證 MCP 工具探索及唯讀的 `list_sessions` 呼叫，再安裝本 skill。執行任務需要寫入工具；`--read-only` 服務只能觀察。

完整步驟與版本更新請參閱 [MCP 安裝指南](https://github.com/lucky-goals/goals-iterm-mcp/blob/main/README.zh-TW.md)。以下範例固定使用其文件中的 `0.1.2`，不表示後續版本不相容。

```text
請在本機 Mac 上為 [目標用戶端] 安裝 goals-iterm-mcp。
儲存庫網址：https://github.com/lucky-goals/goals-iterm-mcp

1. 閱讀專案安裝指南，檢查 macOS、iTerm2 與 uv/uvx。
   若缺少 uv，請依照 uv 官方說明安裝。
2. 使用 Python 3.12 驗證套件可執行：
   uvx --python 3.12 goals-iterm-mcp@0.1.2 --help
3. 備份用戶端現有 MCP 設定，新增或更新一個名為 iterm 的本機 stdio 服務，
   保留無關設定並避免重複設定：
   command：本機 uvx 的絕對路徑
   args：["--python", "3.12", "goals-iterm-mcp@0.1.2", "serve"]
   使用目標用戶端支援的設定格式與位置。
4. 如有需要，指導我啟用 iTerm2 Python API 並批准授權視窗。
   依支援的方式重新載入 MCP；需要手動重新啟動時說明具體步驟。
5. 驗證交握、工具探索及 list_sessions 即可。安裝期間不要讀取終端內容、傳送輸入、
   建立或關閉視窗，也不要啟動 coding 任務。
6. 回報設定位置、固定版本與連線結果，區分獨立服務連通與目標用戶端實際載入工具。
   若有阻礙，說明剩餘步驟；準備完成後繼續依下文安裝 skill。
```

`serve` 是由用戶端透過 stdio 啟動的 MCP 服務入口，不是 coding CLI。安裝 MCP 不會提供 monitor，也不會替目標 CLI 設定驗證資訊。

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

## 更新已安裝的舊版本

除非使用者指定 tag 或 commit，`goals-iterm-skill` 的最新版本就是遠端儲存庫預設分支目前最新的已發布提交。只更新本機原始碼不會更新已複製的安裝目錄。本 skill 不是 PyPI 套件；升級 `goals-iterm-mcp` 的 PyPI 套件也不會更新本 skill。

將下方提示詞交給能存取本機檔案系統的 coding agent，並替換 `[目標用戶端]`：

```text
請更新 [目標用戶端] 實際載入的 goals-iterm-skill。
儲存庫：https://github.com/lucky-goals/goals-iterm-skill
（如需固定版本，請在這裡指定 tag 或 commit。）

1. 先找出目標用戶端實際載入的安裝位置與作用範圍，確認它是 Git checkout、symlink、複製目錄，還是用戶端管理的安裝。不要猜測路徑。回報現有 ref/commit 或檔案狀態與本機修改，並檢查重複安裝；無法確認時明確寫 unknown，不要另裝一份。
2. 將完整安裝目錄及本機修改備份到已發現 skill 目錄之外的明確路徑，避免備份被掃描成第二個 skill。若是 symlink，備份實際目標內容，不能只備份連結本身。保留 audit/runtime 狀態與其他 skills，不要建立重複安裝。
3. 從遠端取得資料並解析遠端儲存庫預設分支的最新提交；除非我指定 tag 或 commit，否則使用該提交，不要假設預設分支叫 main。記錄目標 SHA，不要把舊 checkout 或未提交修改稱為上游最新版。
4. 若是乾淨且正在追蹤預期分支的 checkout，只能 fast-forward 更新。若工作區 dirty、已分叉、detached 或位於其他分支，不要 reset、丟棄修改或強制切換；建立新的 upstream checkout 比對，保留並合併本機修改後再更新，無法合併的衝突要明確回報。
5. 若是 symlink，更新它實際指向的目錄；若是複製安裝，從新的完整 checkout 比對並同步整個 package（包括 SKILL.md、references/、agents/），不要只複製 SKILL.md。備份後只移除已確認屬於 package 且已過時的檔案，不要刪除未知額外檔案；用戶端管理的安裝則使用其支援的更新器。
6. 校驗 skill metadata、相對連結及安裝內容是否對應目標提交，依用戶端支援的方式重新載入；若需要手動操作，說明精確步驟或需建立的新 session。確認用戶端實際發現新 revision 與檔案，不要宣稱目前已開啟的 chat 會 hot-reload。
7. 另外檢查 MCP 連線與工具探索；若要做連線檢查，最多使用唯讀的 list_sessions。更新期間不要讀取終端內容、傳送輸入、建立或關閉視窗或啟動任務。若缺少新工具，分開回報需要升級或重新載入 MCP，不要自動修改其固定版本或無關設定。
8. 回報安裝位置與範圍、安裝方式、備份路徑、更新前後的 ref/commit SHA、本機修改、驗證與重新載入結果，以及保留本機修改的 rollback 方法。
```

手動 fallback：乾淨且追蹤預期分支的 checkout，先確認預期 ref，再執行 `git fetch <remote>` 和 `git pull --ff-only`；其他狀態先建立新的 checkout 比對。複製安裝則在暫存目錄取得目標提交，完成比對、備份後同步完整 package，核對已過時的 package 檔案，再依用戶端方式重新載入；symlink 則更新實際目標。回滾時保留更新後新增的本機修改，恢復備份並重新載入；回滾 skill 不會回滾 MCP 或已執行的終端任務。

## 前置條件與手動安裝

本儲存庫根目錄就是一個 skill 套件。透過宿主用戶端支援的 skill 安裝機制，將整個目錄安裝為 `goals-iterm-skill`，保留 `SKILL.md`、`references/` 和 `agents/`，確保相對引用有效。安裝位置與重新載入步驟以目標用戶端文件及現有設定為準。

本 skill 不會安裝 MCP 或提供獨立背景服務。使用前需在宿主中連接 goals-iterm-mcp、啟用 iTerm2 Python API，並在目標終端準備好 CLI 及驗證設定。所需工具至少涵蓋工作階段列舉、畫面/歷史讀取、文字/按鍵傳送；新增終端還需要對應的建立工具。

持續監控依賴宿主提供的任務喚醒/排程，或 agent 目前執行中的輪詢。沒有背景喚醒能力的用戶端，無法在 agent 結束執行後繼續自動監控。skill 會要求明確回報這項限制。

## 明確的工作階段清理

目前 MCP 原始碼已實作四個清理工具。只有在已安裝的服務提供相應 schema 時才使用；執行時以實際安裝工具的 schema 為準。本節說明目前實作，不表示某個套件已發布，也不涉及版本變更。

- `close_session(session_id OR nickname, force=false, dry_run=false)` 關閉一個工作階段。
- `close_tab(tab_id OR session_id OR nickname, force=false, dry_run=false)` 關閉一個分頁。
- `close_window(window_id OR session_id OR nickname, force=false, dry_run=false)` 關閉一個視窗。
- `clean_all_sessions(force=false, dry_run=false)` 清理伺服器授權範圍內的工作階段。

前三個工具必須且只能提供一個定位參數。ID 必須精確匹配。暱稱會先去除前後空白並進行大小寫折疊，再精確匹配一個 Session；對分頁/視窗工具，它會選取該 Session 所在的容器，不會把暱稱直接當作 Tab。匹配有歧義時拒絕。預設情況下，`clean_all_sessions` 只關閉已確認閒置的工作階段，略過忙碌、等待、未知或其他無法確認安全的工作階段。它不會推斷工作階段「不需保留」或是否有用；負責協調的 agent 必須遵守使用者要求的保留策略與授權範圍。`force=true` 會嘗試初始授權範圍內的所有工作階段（包括忙碌的工作階段），但仍執行 ID、權限、目標變更與恢復安全檢查。一般關閉在預檢發現受影響的工作階段/分頁/視窗中有忙碌或未知工作階段時，會整體拒絕，除非已授權 force。

任何中斷、CLI 退出或原生關閉之前，服務都必須先持久化私有恢復回執，其中記錄目標以及可取得的 CLI/chat UUID、cwd 與恢復中繼資料；初始回執寫入失敗會在終端寫入前停止操作；後續回執更新失敗時可能已有副作用，需核對逐工作階段結果。接著要求 CLI 正常退出，並僅在確認退出後關閉目標。`dry_run=true` 真正唯讀：不傳送終端輸入、不儲存恢復回執、不改名、不中斷、不關閉。

每個工作階段結果都使用公開欄位 `interruption`、`exit`、`closure_status` 與 `cli_sessions`；聊天記錄可能包含 `cli`、`chat_uuid`、`cwd`、身分來源、持久化狀態與恢復資料。有回執時，操作會回傳 `recovery_record_id` 與 `recovery_record_path`。CLI 歷史的 `persistence_status` 為空或未知本身不是阻礙。UUID 身分證據與恢復回執安全防護，和歷史是否實際持久化、能否恢復是不同層次；只有 ID 不保證可恢復。即使 MCP 回應的 `isError=true`，仍要讀取其中的 `status` 以及 `closed_sessions`、`skipped_sessions`、`failed_sessions`、`unknown_sessions` 陣列。

現有監控與稽核流程仍然適用。任務完成不代表終端會自動關閉；清理必須有明確意圖。重用既有授權，不要重複詢問。`clean_all_sessions` 可能影響無關任務，因此只有在已授權範圍與伺服器範圍一致時才呼叫（包括已設定的 allowlist）。詳細流程請參閱[關閉與恢復指南](references/closing-and-recovery.md)。

## 使用範例

```text
使用 goals-iterm-skill，在 iTerm 中讓 Claude Code 修復 /path/to/project
的登入問題。先診斷再修復，只執行相關測試。每次發出指令後監控回應，
一般技術決策由你判斷，確定網路錯誤已中斷任務且不會自動繼續時恢復任務。
驗收完成後停止監控並彙整修改、測試及剩餘問題。不要發布。
```

也可以指定既有工作階段的暱稱來接手任務。skill 會先列舉並綁定正確的 `session_id`，避免重複派發仍在執行的任務。

## 進階範例：使用 Goal 持續推進整個任務

對於多階段任務，如果宿主支援 Goal，建議在負責協調的 Codex 聊天中設定 Goal。iTerm 內的執行 CLI 不必另外設定 Goal。Goal 記錄整體目標，skill 指導協調流程，monitor 負責觀察終端回應。Goal 不能取代 monitor，也不提供獨立背景服務。請參閱 [官方 Goals 指南](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)。

替換下方的預留內容，將提示詞傳送給負責協調的 Codex。宿主不支援 Goal 時，可以刪除建立及完成 Goal 的要求，保留監控與驗收要求。

```text
請建立並啟動一個 Codex Goal，使用 $goals-iterm-skill，
透過 iTerm MCP 持續指揮終端中的 Coding CLI，直到以下任務通過驗收。

專案目錄：[絕對路徑]
執行 CLI：[Claude Code / Codex CLI]
目標工作階段：[既有工作階段暱稱或 ID；沒有則建立專用工作階段]

任務目標：
[描述最終需要實現的結果]

驗收條件：
1. [可檢查的功能或行為]
2. [需要通過的相關測試]
3. [需要交付的檔案、結果或說明]

執行要求：
- 全程同步維護 Markdown 審計台帳，記錄委託、CLI 回應及待決策事項、你的決定與依據、
  實際動作及結果；附時間、外層/CLI 輪次與關聯事件編號。開始時告知路徑，最後附台帳連結。
- 你負責協調、監控、決策及驗收，讓目標 CLI 執行具體開發工作。
- 先檢查工作階段狀態；既有任務正在執行時直接接手監控，不重複派發。
- 每次傳送任務、補充指令、決策或恢復指令後，建立或更新同一個 monitor。
- 使用實際可用的宿主監控機制；沒有背景喚醒能力時，在目前執行中持續輪詢，
  並如實說明限制，不能只承諾「稍後檢查」。
- 一般技術決策結合上下文及專案慣例自主判斷，像 advisor 一樣指導 CLI 繼續。
- CLI 正在執行或自動重試時繼續觀察，不重複傳送任務。
- 只有確認任務已中斷且不會自動繼續時，才核對已完成工作並進行有限次數的恢復。
- 不要將階段回報、閒置輸入框或 CLI 自稱完成視為整個任務已完成。
- 缺少驗收證據時繼續要求補充；滿足全部驗收條件後，停止 monitor，
  將 Goal 標記為完成，並彙整修改、驗證結果與剩餘問題。

限制：
- 遵守專案 AGENTS.md。
- 只執行相關的針對性測試，非必要不執行全量測試。
- 啟動 Python 程序時不使用 --reload。
- 本次不授權發布、推送或破壞性操作。
- 遇到必須由我決定的問題時，提供具體問題、建議及所需操作；
  保留上下文並停止相關自動寫入。
```

## 任務審計台帳

每個委託任務都會在執行過程中同步維護一份 Markdown 審計台帳。協調者記錄委託指令、CLI 回應（含待決策問題與選項）、決策及依據、傳送證據、異常恢復、驗收結果及監控清理。每筆包含帶 UTC 偏移的時間、外層對話輪次、各工作階段的 CLI 輪次，以及關聯事件/決策編號。外層輪次是任務內的使用者訊息計數，不冒充宿主原生聊天 ID。

協調者在開始時告知台帳絕對路徑，結束時附上連結。可指定儲存路徑；預設使用宿主私有狀態目錄，沒有此目錄時使用 `~/.local/state/goals-iterm-skill/audits/`，不會自動提交至專案儲存庫。敏感內容先遮蔽，無變化輪詢可以合併，但關鍵回應與決策必須保留。這是以附加為主的操作記錄，不是防竄改日誌或完整終端錄製。

詳見 [審計協定](references/audit.md) 與 [Markdown 範本](references/audit-template.md)，目前以簡體中文撰寫。傳送前記錄意圖，傳送後附加實際結果。寫入台帳失敗時會回報缺口並暫停新的自動工作指令，不能在沒有審計記錄的情況下默默繼續。

## 維護與驗證

入口為 [SKILL.md](SKILL.md)，工具語義見 [iterm-tools.md](references/iterm-tools.md)，監控、恢復及行為驗收情境見 [monitoring.md](references/monitoring.md)，清理恢復細節見 [closing-and-recovery.md](references/closing-and-recovery.md)。這些指令檔案目前使用簡體中文。工具約定依據 cc-iterm-mcp 的 `src/goals_iterm_mcp/direct.py`；執行時以實際安裝版本的 schema 為準。

修改後驗證 skill frontmatter 與相對引用，並推演監控協定末尾的情境。實際 CLI 驗證應使用專用測試工作階段，確認任務派發、決策、恢復及監控清理；靜態驗證不代表背景排程或實際 CLI 整合已通過。

## 貢獻與支援

歡迎提交問題回報、流程改進與翻譯。提交 PR 前請閱讀 [貢獻指南](CONTRIBUTING.md)，可重現的問題與建議請透過 [Issues](https://github.com/lucky-goals/goals-iterm-skill/issues) 提交。安全漏洞請依照 [安全政策](SECURITY.md) 私下回報，不要公開終端記錄。貢獻與安全文件目前使用英文。

## 授權條款

[MIT 授權條款](LICENSE)，著作權所有：2026 lucky-goals。

# goals-iterm-skill

Skill 版本：[v0.4.0-dev](https://github.com/lucky-goals/goals-iterm-skill/releases/tag/v0.4.0-dev)（預發布）

[專案官網](https://lucky-goals.github.io/goals-iterm-skill/)
[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

透過本 skill 委派、接手或繼續任務時，負責協調的 agent 會擔任根協調者。它透過隨 skill 提供的獨立執行器指揮 iTerm2 中的 Claude Code、Codex 等 CLI，監控進度、自行處理一般決策並驗收結果。請遵循[執行邊界](references/orchestrator.md)：專案寫入、產物、測試、建置、相依套件/設定/服務變更及 Git 修改都交由終端 CLI 執行；唯讀 Git 檢查可以直接進行。根 agent 和原生子 agent 只讀取專案脈絡、驗收條件並進行審查。發布仍須取得明確授權。

預設在目前執行中進行內聯監控。每次等待前，協調者根據最新證據向使用者簡短說明進度，及時回報階段變化和阻礙，不編造百分比或完成時間。只有使用者明確要求且已確認宿主有真正的喚醒/排程控制代碼時，才使用背景監控。詳見[進度旁白協議](references/monitoring.md#progress-narration-before-inline-waits)。

## 本機執行環境

隨 skill 提供的執行器需要本機 macOS 執行環境、已啟用並授權的 iTerm2 Python API，以及 Python 3.12 與 skill 鎖定的最小依賴。沒有本機執行通道的純雲端宿主無法操作本機 iTerm2。在 iTerm2 中安裝並完成目標 CLI 的驗證；不要把憑證寫進提示詞。

在已安裝的 skill 目錄中檢查或準備執行環境：

```sh
scripts/bootstrap.sh --check
scripts/bootstrap.sh --apply
scripts/itermctl capabilities --json
scripts/itermctl doctor --json --live-api-check
```

執行器不需要 MCP 服務、用戶端工具探索或用戶端 MCP 設定。固定策略儲存在 `~/.local/state/goals-iterm-skill/policy.json`；沒有策略時預設唯讀。寫入需明確設定策略，例如 `scripts/itermctl policy configure --allow-writes --session-id SESSION_ID`。不要靜默擴大既有唯讀設定或 Session allowlist。請參閱[執行器契約](references/runtime.md)，了解請求/結果格式、全部 13 項操作、恢復回執及策略規則。

## 透過 coding agent 安裝

將下方提示詞複製給可以存取本機檔案系統的 coding agent，將 `[目標用戶端]` 替換為需要安裝 skill 的用戶端。已有本機儲存庫時，也可以將儲存庫 URL 替換為本機絕對路徑。

```text
請將 goals-iterm-skill 安裝到 [目標用戶端]。
儲存庫網址：https://github.com/lucky-goals/goals-iterm-skill

1. 檢查目標用戶端的現有設定及支援的 skill 安裝機制，依照其文件確認安裝位置
   與適用範圍，不要猜測設定路徑。
2. 取得儲存庫，或使用我指定的本機目錄。檢查 SKILL.md 及其引用檔案；儲存庫
   根目錄就是 skill 套件。
3. 以 goals-iterm-skill 為目錄名稱安裝，保留 SKILL.md、references/、agents/、scripts/ 和 runtime/，
   不要只複製 SKILL.md。已有安裝時先比較差異、保留本機修改並在更新前備份，
   不影響其他 skill。
4. 檢查本機 macOS 執行能力、iTerm2 Python API 及隨 skill 提供的執行器。
   先執行 `scripts/bootstrap.sh --check`；若 runtime 尚未準備或與目前版本不相符，
   在本次安裝授權範圍內執行 `scripts/bootstrap.sh --apply`，再重新執行 `--check`。
   接著執行 `scripts/itermctl capabilities --json` 和
   `scripts/itermctl doctor --json --live-api-check`。live check 只呼叫唯讀 `list_sessions`，
   不讀取 screen/history 正文。若出現授權對話框或需要手動設定，請回報確切操作，不要繞過。
   不要修改用戶端 MCP 設定。
5. 驗證 skill 中繼資料與相對引用。依用戶端支援的方式重新載入，若需手動操作，
   明確告訴我步驟；能夠檢查時，確認目標用戶端確實已辨識此 skill。
6. 安裝期間不要讀取終端內容、傳送輸入、建立視窗或啟動 coding 任務。
   未經明確授權，不要設定寫入策略。
7. 回報安裝路徑、skill 辨識狀態、執行器就緒情況、策略狀態和可用的監控能力。委派任務預設內聯監控；
   背景監控需要使用者明確要求和真正的宿主能力。安裝本身不啟動 monitor；沒有真實排程控制代碼，
   不承諾本次執行結束後繼續檢查。
```

## 更新已安裝的舊版本

除非使用者指定 tag 或 commit，`goals-iterm-skill` 的最新版本就是遠端儲存庫預設分支目前最新的已發布提交。只更新本機原始碼不會更新已複製的安裝目錄。

將下方提示詞交給能存取本機檔案系統的 coding agent，並替換 `[目標用戶端]`：

```text
請更新 [目標用戶端] 實際載入的 goals-iterm-skill。
儲存庫：https://github.com/lucky-goals/goals-iterm-skill
（如需固定版本，請在這裡指定 tag 或 commit。）

1. 先找出目標用戶端實際載入的安裝位置與作用範圍，確認它是 Git checkout、symlink、複製目錄，還是用戶端管理的安裝。不要猜測路徑。回報現有 ref/commit 或檔案狀態與本機修改，並檢查重複安裝；無法確認時明確寫 unknown，不要另裝一份。
2. 將完整安裝目錄及本機修改備份到已發現 skill 目錄之外的明確路徑，避免備份被掃描成第二個 skill。若是 symlink，備份實際目標內容，不能只備份連結本身。保留 audit/runtime 狀態與其他 skills，不要建立重複安裝。
3. 從遠端取得資料並解析遠端儲存庫預設分支的最新提交；除非我指定 tag 或 commit，否則使用該提交，不要假設預設分支叫 main。記錄目標 SHA，不要把舊 checkout 或未提交修改稱為上游最新版。
4. 若是乾淨且正在追蹤預期分支的 checkout，只能 fast-forward 更新。若工作區 dirty、已分叉、detached 或位於其他分支，不要 reset、丟棄修改或強制切換；建立新的 upstream checkout 比對，保留並合併本機修改後再更新，無法合併的衝突要明確回報。
5. 若是 symlink，更新它實際指向的目錄；若是複製安裝，從新的完整 checkout 比對並同步整個 package（包括 SKILL.md、references/、agents/、scripts/、runtime/），不要只複製 SKILL.md。備份後只移除已確認屬於 package 且已過時的檔案，不要刪除未知額外檔案；用戶端管理的安裝則使用其支援的更新器。
6. 校驗 skill metadata、相對連結及安裝內容是否對應目標提交，依用戶端支援的方式重新載入；若需要手動操作，說明精確步驟或需建立的新 session。確認用戶端實際發現新 revision 與檔案，不要宣稱目前已開啟的 chat 會 hot-reload。
7. 先執行 `scripts/bootstrap.sh --check`；未準備或不符時，沿用本次更新授權執行
   `scripts/bootstrap.sh --apply`，再重新檢查。使用 `scripts/itermctl capabilities --json` 和 `scripts/itermctl doctor --json`
   檢查隨包執行器；更新期間不要設定寫入策略或操作終端。
8. 回報安裝位置與範圍、安裝方式、備份路徑、更新前後的 ref/commit SHA、本機修改、驗證與重新載入結果，以及保留本機修改的 rollback 方法。
```

手動 fallback：乾淨且追蹤預期分支的 checkout，先確認預期 ref，再執行 `git fetch <remote>` 和 `git pull --ff-only`；其他狀態先建立新的 checkout 比對。複製安裝則在暫存目錄取得目標提交，完成比對、備份後同步完整 package，核對已過時的 package 檔案，再依用戶端方式重新載入；symlink 則更新實際目標。回滾時保留更新後新增的本機修改，恢復備份並重新載入；回滾 skill 不會回滾已執行的終端任務。將可變執行環境、稽核及恢復狀態保留在 skill 目錄之外。

## 前置條件與手動安裝

本儲存庫根目錄就是一個 skill 套件。透過宿主用戶端支援的 skill 安裝機制，將整個目錄安裝為 `goals-iterm-skill`，保留 `SKILL.md`、`references/`、`agents/`、`scripts/` 和 `runtime/`，確保執行器及相對引用可用；`scripts/` 包含啟動器及工作階段註冊表使用的標準函式庫輔助腳本。安裝位置與重新載入步驟以目標用戶端文件及現有設定為準。

啟用並授權 iTerm2 Python API，在目標終端準備好 CLI 及驗證設定，再使用隨 skill 提供的執行器操作 iTerm。執行器需要本機 Python 3.12 與鎖定的最小執行依賴，不提供 agent 排程器或背景服務。

預設在目前執行中內聯輪詢監控。使用真正且可中斷的宿主 sleep：派發後 10–15 秒，之後每次檢查間隔 30–60 秒，每段不超過 60 秒。單一多工作階段迴圈會檢查所有到期或可執行的工作階段，再只等待最近的下一次檢查。預設不要啟動背景 monitor。只有使用者明確要求且已確認有真正的宿主排程/喚醒控制代碼，才能在本次執行結束後繼續監控；否則應說明限制。

### 短指令＋決策檔案

多行、長文字或包含多項條件的任務、決策與續跑指令，預設由協調者先寫入 CLI 可讀取的私有決策檔案，再傳送包含絕對路徑和唯一派發 ID 的單行短指令。核對輸入後另行提交，持續監控檔案讀取與執行證據。簡單單行回覆可直接傳送，選單依實際選項操作。遇到 `[Pasted text #N]` 不盲目提交或重送；只有確認屬於本協調者且尚未提交的草稿，才能依已知編輯器語義清除後切換。檔案預設不寫入業務儲存庫，傳送後保持不變，並與台帳關聯。範本、路徑要求與恢復步驟見 [檔案派發協議](references/dispatch.md)。

### 工作階段生命週期與持久協調狀態

開始新的 CLI 工作或交接任務前，請遵循[工作階段生命週期指南](references/session-lifecycle.md)。啟動新的 CLI 程序或工作階段前，先檢查隨包執行器回報的操作與就緒狀態。CLI 啟動後、派發新工作前，核對對話持久化狀態以及目前的 Session/Tab/Window 身分。若 transcript 或歷史記錄已停用，必須先透過該 CLI 支援且已驗證的啟動方式修復，再傳送新工作；不要為了修改設定而重啟已經活躍的工作階段。CLI 身分或恢復回執本身不代表歷史已持久化或可恢復。恢復狀態未知時記錄限制，獨立核對正常退出條件，不直接判定必須人工回收。

協調者在 `~/.local/state/goals-iterm-skill/session-registry.json` 維護持久化本機註冊表。使用隨包提供的標準函式庫輔助腳本 `scripts/session_registry.py` 實作鎖、revision 與 generation 防護。註冊表記錄的是宿主觀察結果，不代表授權或真實終端鎖；執行器依據固定本機策略和即時操作檢查執行限制。選用欄位 `monitor_mode` 的值為 `inline`、`background`、`none` 或 `unknown`；舊紀錄缺少此欄位時視為 `unknown`。只有存在真正的宿主控制代碼時，`schedule_status` 才能為 `scheduled`；inline 未排程是常態，記錄的是協調者聲明，並不保證持續存活。跨任務 handoff/重用或工作階段身分/拓撲變更都會使舊的完成狀態失效；同一任務僅更換協調者時，保留已記錄的業務與清理事實（包括 unknown 結果），同時由 generation 防護阻止過期寫入。重新命名 CLI 聊天不會產生新的身分。每個工作階段的任務驗收後，將其置為 `finalizing`：停止負責業務寫入的 monitor，但可在目前執行中透過有界的唯讀觀察、sleep 和複核，繼續執行已授權的清理，直到每個所屬資源實際為 `closed`、明確 `retained`，或 `blocked` 且有可執行的處置方案。任何 `unknown` 清理結果都要保持可見，並先透過唯讀觀察對帳後再改變。本次執行結束後的檢查需要使用者明確要求背景監控且存在真正的宿主控制代碼。子任務在沒有消費者需要後，可以獨立驗收或回收。

業務 monitor 停止後，仍可在目前執行中的收尾階段，經授權進行有界的清理複核和 sleep。只有使用者明確要求背景監控且存在真正的宿主排程/喚醒控制代碼，才能在本次執行結束後檢查。寫入結果未知時，只能透過唯讀觀察進行對帳。預設不得使用 `force` 或全域清掃。最終回覆必須包含資源核算總數及原因、恢復證據和待處理後續事項。

## 明確的工作階段清理

隨包執行器提供 `close_session`、`close_tab`、`close_window` 與 `clean_all_sessions`。使用 `capabilities --json` 查看參數 schema，透過 `list_sessions` 綁定正確 ID。對既有資源執行變更時必須附上最新的 `list_sessions.data.observation`。關閉容器前必須核對所有成員；遇到超出範圍或忙碌/未知的成員時，整體拒絕。dry run 為唯讀，不儲存關閉回執。

`clean_all_sessions` 是在固定策略允許範圍內進行的全域清理。只有使用者授權涵蓋整個已設定範圍、策略允許寫入，且請求頂層包含 `authorization_scope: "all_sessions"` 時才能使用。allowlist 只限制存取，不代表擁有資源或已取得使用者授權。`force=true` 不能繞過策略、身分、所有權、回執或未知結果保護。預設會依閒置狀態篩選並回傳逐工作階段的部分結果；初始快照後才出現的工作階段不在此次操作內。

中斷、CLI 退出或關閉前，執行器會儲存私有恢復回執。初始回執寫入失敗會阻止終端寫入；後續更新失敗可能發生在副作用之後，需檢查逐工作階段結果。受限 SIGINT/SIGTERM 可請求 CLI 退出；只有確認退出後才會關閉目標。結果使用 `schema_version`、`request_id`、`status`、`code`、`data`、`warnings` 與 `side_effects` 信封；請檢查所有欄位及逐工作階段結果。有回執時，引用實際回傳的 `recovery_record_id` 與 `recovery_record_path`。CLI 歷史的 `persistence_status` 為空或未知本身不會阻止清理，也不能證明可恢復。

變更結果未知時，先確認正確的 request ID 和 state location，再以 `operation-status --request-id ID` 查詢，並透過新的唯讀觀察進行對帳。`data: null` 僅表示目前的 state location 沒有該 ID 的記錄，不能證明寫入未曾發生，也不能據此認定任務完成。不要重放變更。完整契約見[執行器說明](references/runtime.md)與[關閉和恢復指南](references/closing-and-recovery.md)。

### 自動回收任務擁有的資源

新建任務專用工作階段預設為 `auto_owned`，包括僅測試啟動的情境；要求啟動工作階段本身不表示要求保留，明確保留須記錄來源。CLI 經已驗證的 `/quit`、`/exit` 或退出鍵結束後，已核實閒置的 shell 可沿用回收授權，透過執行器傳送 `exit`，無須再次確認。shell 的 `exit` 不帶斜線。核驗原 Session/Tab 消失；仍留存時再走受保護的執行器關閉流程。活動診斷可能不完整，但計數不能單獨證明閒置；未知作業、範圍限制及寫入結果不明仍會阻止自動退出。

驗收通過並停止業務 monitor 後，預設按[正常退出協定](references/natural-exit.md)回收任務專用資源：儲存已知恢復資料，提交一次已驗證的 CLI 退出命令，核實退出後再關閉剩餘 shell。僅缺聊天 UUID 不單獨阻止正常退出；使用者明確要求必須可恢復後才關閉時仍優先遵守。CLI 自稱完成不等於驗收通過；借用或使用者要求保留的資源仍按原授權保留。

在建立或明確採用資源時，記錄來源、擁有該資源的任務，以及準確的 Session、Tab、Window ID。選擇最大且安全、互不重疊的任務擁有容器：只有當視窗目前所有後代都屬於本任務，且已完成並符合回收條件時，才使用任務獨占 Window；否則使用任務獨占 Tab；再否則只關閉各個任務擁有且符合條件的 Session。僅為空或看起來獨占，不能證明容器歸屬。保留未獲清理授權的借用父層，以及共享或未知窗格。allowlist 不完整、無法證明容器歸屬時，使用精確的 Session。

正常退出後更新拓撲，對剩餘準確目標做 `dry_run=true` 預演，取得新的 expected observation 後用 `force=false` 關閉；本任務回收不呼叫全域 `clean_all_sessions`。實際忙碌、歸屬/程序不明、身分衝突、策略限制、初始回執失敗與寫入結果未知仍須保留核實。僅活動診斷受限時按正常退出協定補齊獨立證據，不自動 force。退出投遞未知不重送；CLI 退出、終端消失、聊天恢復能力分別驗證，後續 shell 關閉回執不能證明原對話可恢復。

將業務任務完成與清理結果分開記錄。稽核記錄應寫入每個工作階段的 CLI/chat UUID、cwd、恢復中繼資料、恢復回執、request ID 與清理結果。暫停、失敗或取消的任務不自動回收。現有監控與稽核流程仍然適用，隨包執行器契約規定參數與結果。借用資源、全域清理與 force 清理仍需明確授權；重用既有授權，不要重複詢問。`clean_all_sessions` 可能影響無關任務，因此只有使用者授權涵蓋整個已設定策略範圍，且請求包含 `authorization_scope: "all_sessions"` 時才能呼叫。詳細流程請參閱[自動回收與恢復指南](references/automatic-cleanup.md)與[關閉與恢復指南](references/closing-and-recovery.md)。

## 使用範例

```text
使用 goals-iterm-skill，在 iTerm 中讓 Claude Code 修復 /path/to/project
的登入問題。先診斷再修復，只執行相關測試。專案變更都交給 CLI；根 agent 和原生子 agent
只讀檢查脈絡並審查結果。預設在目前執行中內聯監控，
一般技術決策由你判斷，確定網路錯誤已中斷任務且不會自動繼續時恢復任務。
驗收完成後停止負責業務寫入的 monitor，並完成已授權的收尾，直到所屬資源已關閉、明確保留，
或已阻塞並記錄可執行的處置方案。彙整修改、測試、資源核算總數及原因、恢復證據和待處理後續事項。
不要發布。
```

也可以指定既有工作階段的暱稱來接手任務。skill 會先列舉並綁定正確的 `session_id`，避免重複派發仍在執行的任務。

## 進階範例：使用 Goal 持續推進整個任務

只有使用者明確要求且宿主支援時，才在負責協調的 Codex 聊天中建立 Goal。iTerm 內的執行 CLI 不必另外設定 Goal。Goal 記錄整體目標，skill 指導協調流程，內聯監控負責觀察終端回應。Goal 不能取代監控，也不提供獨立背景服務。請參閱 [官方 Goals 指南](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)。

替換下方的預留內容，將提示詞傳送給負責協調的 Codex。宿主不支援 Goal 時，可以刪除建立及完成 Goal 的要求，保留監控與驗收要求。

```text
請建立並啟動一個 Codex Goal，使用 $goals-iterm-skill，
透過隨包執行器持續指揮 iTerm 中的 Coding CLI，直到以下任務通過驗收。

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
- 你作為根協調者。專案寫入、產物、測試、建置、相依套件/設定/服務變更及 Git 修改都透過隨包執行器交給目標 CLI；唯讀 Git 檢查可以直接進行。根 agent 和原生子 agent 只讀取脈絡、驗收條件並審查結果。只有在我明確授權時才發布。若請求只涉及清理，走精簡生命週期路徑，不啟動 coding CLI 或監控迴圈。若請求只涉及復原，只在生命週期需要時啟動/恢復 CLI，不追加業務工作或監控迴圈。
- 先檢查工作階段狀態；既有任務正在執行時直接接手監控，不重複派發。
- 預設在目前執行中內聯監控。派送後使用真正且可中斷的 sleep 10–15 秒，之後每次檢查間隔 30–60 秒（每段不得超過 60 秒）。單一迴圈檢查所有到期/可執行的工作階段，再只等待最近的下一次檢查。預設不要啟動背景 monitor。
- 只有我明確要求且已確認真實宿主排程/喚醒控制代碼時，才啟動背景 monitor。背景監控不可用時，只有前景繼續仍符合我的要求才繼續 inline；如果我要求立即返回，就儲存檢查點並以 unscheduled 如實交接，不承諾未來檢查。上下文變長本身只需要儲存檢查點並正常續接；無法避免的宿主硬限制才可能因此需要交接。
- 驗收後停止業務監控，但可在目前執行中透過有界的唯讀觀察、sleep 和複核完成已授權的清理。本次執行結束後的檢查需要我明確要求且存在真正的排程控制代碼；未排程的 inline monitor 不保證持續存活。
- 一般技術決策結合上下文及專案慣例自主判斷，像 advisor 一樣指導 CLI 繼續。
- CLI 正在執行或自動重試時繼續觀察，不重複傳送任務。
- 只有確認任務已中斷且不會自動繼續時，才核對已完成工作並進行有限次數的恢復。
- 不要將階段回報、閒置輸入框或 CLI 自稱完成視為整個任務已完成。
- 缺少驗收證據時繼續要求補充；滿足全部驗收條件後，停止負責業務寫入的 monitor，
  只完成已授權的收尾：繼續協調清理，並將每個所屬資源記錄為已關閉、明確保留、已阻塞且
  有可執行處置方案，或 unknown。unknown 必須透過唯讀觀察對帳，不得隱藏。只有在沒有任何
  必要工作未完成時，才能將 Goal 標記為完成。若必要工作或清理確實受阻，應如實回報宿主的
  目前狀態與所需動作，遵守宿主的狀態轉換規則；不要強行立即標記 blocked，也不要承諾無限期
  保持 Goal 開放。彙整修改、驗證結果、資源核算總數及原因、恢復證據和待處理後續事項。沒有
  消費者需要時，子任務可以獨立驗收或回收。

限制：
- 遵守專案 AGENTS.md。
- 只執行相關的針對性測試，非必要不執行全量測試。
- 啟動 Python 程序時不使用 --reload。
- 本次不授權發布、推送或破壞性操作。
- 遇到必須由我決定的問題時，提供具體問題、建議及所需操作；
  保留上下文並停止相關自動寫入。
```

## 任務審計台帳

透過本 skill 委派、接手或繼續的每個任務，都會在執行過程中同步維護一份 Markdown 審計台帳。協調者記錄委託指令、CLI 回應（含待決策問題與選項）、決策及依據、傳送證據、異常恢復、驗收結果及監控清理。每筆包含帶 UTC 偏移的時間、外層對話輪次、各工作階段的 CLI 輪次，以及關聯事件/決策編號。外層輪次是任務內的使用者訊息計數，不冒充宿主原生聊天 ID。

協調者在開始時告知台帳絕對路徑，結束時附上連結。可指定儲存路徑；預設使用宿主私有狀態目錄，沒有此目錄時使用 `~/.local/state/goals-iterm-skill/audits/`，不會自動提交至專案儲存庫。敏感內容先遮蔽，無變化輪詢可以合併，但關鍵回應與決策必須保留。這是以附加為主的操作記錄，不是防竄改日誌或完整終端錄製。

台帳按任務時區的**處理日期**拆分：預設每個任務儲存為 `audits/<task-id>/index.md` 和 `audits/<task-id>/YYYY-MM-DD.md`。索引連結各天檔案，跨日延續事件和輪次編號，補記寫入目前處理日並註明原時間。舊單檔記錄保留，續做時連結新日期檔案；按日拆分不會自動刪除歷史，目錄總量仍會累積。

詳見 [審計協定](references/audit.md) 與 [Markdown 範本](references/audit-template.md)，以英文撰寫。傳送前記錄意圖，傳送後附加實際結果。寫入台帳失敗時會回報缺口並暫停新的自動工作指令，不能在沒有審計記錄的情況下默默繼續。

## 維護與驗證

入口為 [SKILL.md](SKILL.md)，執行器契約見 [runtime.md](references/runtime.md)，執行邊界見 [orchestrator.md](references/orchestrator.md)，監控、恢復及行為驗收情境見 [monitoring.md](references/monitoring.md)，清理恢復細節見 [closing-and-recovery.md](references/closing-and-recovery.md)。技能指引檔案統一使用英文，並保留多語言 README。上游來源與授權資訊見 [runtime/UPSTREAM.md](runtime/UPSTREAM.md)。

修改後驗證 skill frontmatter 與相對引用，並推演監控協定末尾的情境。實際 CLI 驗證應使用專用測試工作階段，確認任務派發、決策、恢復及監控清理；靜態驗證不代表背景排程或實際 CLI 整合已通過。

## 貢獻與支援

歡迎提交問題回報、流程改進與翻譯。提交 PR 前請閱讀 [貢獻指南](CONTRIBUTING.md)，可重現的問題與建議請透過 [Issues](https://github.com/lucky-goals/goals-iterm-skill/issues) 提交。安全漏洞請依照 [安全政策](SECURITY.md) 私下回報，不要公開終端記錄。貢獻與安全文件目前使用英文。

## 授權條款

[MIT 授權條款](LICENSE)，著作權所有：2026 lucky-goals。

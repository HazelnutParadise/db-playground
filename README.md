# DB Playground

網址：https://db-playground.hazelnut-paradise.com

贊助我：[PayPal](https://www.paypal.com/paypalme/tingzhen666)

![logo](https://src.hazelnut-paradise.com/dbPlayground-logo.png?content-type=image/png)

## 介紹

**DB Playground** 是一個線上資料庫語法練習平台，你可以在這裡練習 SQL 語法，並且查看執行結果。**DB Playground** 對於輸入的指令長度無限制且具備人性化貼心設計。支援 MySQL、PostgreSQL 等多種資料庫。

## 本機執行

需要安裝 [uv](https://docs.astral.sh/uv/)。在專案根目錄執行：

```sh
uv sync --locked
cd backend
uv run --locked python main.py
```

應用程式會在 `http://localhost:5000` 啟動。資料庫連線使用 Docker Compose 內的服務名稱，本機執行時需另行設定名稱解析與連線。

## 線上人數與聊天室

線上人數統計最近 90 秒內的訪客。同一會員跨裝置只計一人，未登入時以瀏覽器辨識；舊的登入工作階段需重新登入後才會跨裝置合併。統計暫存於單一應用程式程序的記憶體中。

聊天室開放所有人匿名發言。匿名名稱由 Ollama 產生並保留以避免重複，登入會員跨裝置一致，未登入訪客由瀏覽器辨識，清除瀏覽器資料或更換瀏覽器會改變名稱。既有訊息保留原先顯示的名稱直到到期。Ollama 預設使用 `http://ollama:11434`，可用 `OLLAMA_BASE_URL` 調整，服務不可用時無法建立新名稱。訊息保留 7 天，服務運行時定期刪除，服務停止期間到期的訊息會在重啟後清除。為維運而記錄的請求資訊（包括來源位址和瀏覽器資訊）也會定期清除，不包含訊息內容。

聊天室資料預設保存在 `backend/data/chat.sqlite3`，Docker Compose 使用 `chat_data` 持久化儲存。備份或搬移時需保留此資料，匿名名稱才會維持一致。

## 會員登入

會員登入使用 Logto，未設定時仍可使用 SQL 練習功能。建立傳統網頁應用後，在 Logto 設定回呼網址 `https://db-playground.hazelnut-paradise.com/auth/callback`，並在部署環境提供以下變數：

- `LOGTO_APP_ID`：Logto 應用程式 ID。
- `LOGTO_APP_SECRET`：Logto 應用程式密鑰。
- `LOGTO_SESSION_SECRET`：至少 32 個字元的隨機密鑰。
- `LOGTO_REDIRECT_URI`：Logto 應用程式設定的完整回呼網址。

上述四項需全部設定。請將密鑰保存在部署環境，不要提交至版本控制。本機測試可使用 `http://localhost:5000/auth/callback`，並須在 Logto 同時加入該回呼網址。

「登出本站」只結束本站的工作階段，不會登出其他使用同一 Logto 帳號的網站。

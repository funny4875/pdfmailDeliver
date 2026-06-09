# PDF Mail Deliver

PDF Mail Deliver 是一個 Windows 桌面小工具，用來批次拆分薪資、鐘點費或加班費通知單 PDF，從每份通知單中擷取姓名與 Email，產生寄件清單，並可透過教育雲信箱自動寄送附件。

## 主要功能

- 批次選取多個 PDF 檔案
- 依通知單內容自動拆分成個別 PDF
- 從 PDF 文字或表格中擷取姓名、日期與 Email
- 產生「預計寄件清單」
- 可匯入既有寄件清單繼續寄送
- 自動記錄寄送結果
- 寄送成功後自動從待寄清單移除
- 若一小時寄送超過 100 封，會自動放慢寄送間隔

## 本次修正重點

部分 PDF 會把 Email 抽成換行或全形符號，例如：

```text
jc40220＠
mail.edu.tw
```

原本程式只支援一般半形 Email 格式，因此會抓不到該頁 Email，導致拆分流程繼續累積到下一筆資料，最後誤抓下一筆的 Email。

目前已新增 `PDFProcessor.extract_email()`，可處理：

- 全形 `＠` 轉半形 `@`
- 全形句點轉半形 `.`
- Email 中間的換行與空白
- 輸出乾淨的 Email 字串

例如上方資料會正確解析為：

```text
jc40220@mail.edu.tw
```

## 執行需求

建議使用 Python 3.10 以上版本。

需要安裝套件：

```bash
pip install pdfplumber pypdf
```

程式使用的 Python 內建模組包含：

- `tkinter`
- `smtplib`
- `email`
- `threading`
- `json`
- `base64`

## 使用方式

執行：

```bash
python pdfmailDeliver.py
```

操作流程：

1. 點選「選擇原始 PDF」
2. 選取一個或多個 PDF 檔案
3. 程式會自動拆分 PDF，並產生「預計寄件清單」
4. 確認清單後，可選擇是否立即寄送
5. 輸入教育雲信箱帳號與密碼
6. 程式依序寄送附件，並寫入寄送紀錄

也可以選擇「匯入預計寄件清單」，直接依先前產生的清單繼續寄送。

## 輸出檔案

程式會在執行目錄產生：

- `拆分_時間戳記/`：拆分後的個別 PDF
- `預計寄件清單_時間戳記.txt`：待寄送清單
- `寄送資訊.log`：寄送紀錄
- `失敗清單_時間戳記.txt`：寄送失敗資料
- `.user_config`：本機使用者設定

## 寄件清單格式

新格式使用 Tab 分隔：

```text
相對路徑	Email	原始檔名
```

例如：

```text
拆分_2026_0609_0950/陳禹潔.pdf	jc40220@mail.edu.tw	11506-114-2-第9-12週新增鐘點.pdf
```

## 注意事項

- 寄送前請務必確認拆分結果與 Email 是否正確。
- 若 PDF 來源格式改變，姓名或 Email 擷取規則可能需要調整。
- `.user_config` 會儲存寄件帳號與編碼後的密碼，請勿上傳到公開 repository。
- 實際寄送大量信件前，建議先用少量測試資料確認流程。
- 本工具預設 SMTP Server 為 `mail.edu.tw`，連線埠為 `465`。

## 目前 SMTP 設定

```python
SMTP_SERVER = "mail.edu.tw"
SMTP_PORT = 465
```

若改用其他信箱服務，請自行修改程式中的 SMTP 設定。

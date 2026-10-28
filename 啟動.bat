@echo off
rem ============================================
rem  輕量 RAG 問答 — 雙擊啟動
rem  1. 切換到本檔所在資料夾
rem  2. 約 6 秒後自動開啟瀏覽器
rem  3. 啟動 Streamlit（關閉此黑色視窗即結束程式）
rem ============================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [錯誤] 找不到 .venv 虛擬環境，請先依 README.md 完成安裝。
    pause
    exit /b 1
)

echo 正在啟動輕量 RAG 問答，請稍候...
echo 使用完畢後，直接關閉這個黑色視窗即可結束程式。
echo.
start "" cmd /c "timeout /t 6 >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py
pause

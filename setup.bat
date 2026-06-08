@echo off
echo Setting up AI资讯管家...
cd /d D:\Projects\ai-news-digest

echo.
echo Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

echo.
echo Installing dependencies...
pip install fastapi "uvicorn[standard]" jinja2 feedparser httpx readability-lxml chardet scikit-learn openai python-dotenv pyyaml tenacity

echo.
echo Downloading HTMX...
powershell -Command "Invoke-WebRequest -Uri 'https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js' -OutFile 'web\static\htmx.min.js'"
powershell -Command "Invoke-WebRequest -Uri 'https://unpkg.com/htmx.org@1.9.12/dist/ext/sse.js' -OutFile 'web\static\htmx-sse.js'"

echo.
echo Creating desktop shortcut...
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\AI资讯.lnk'); $SC.TargetPath = 'D:\Projects\ai-news-digest\ai-news.bat'; $SC.Save()"

echo.
echo Done! Double-click 'AI资讯' on your desktop to get started.
echo Don't forget to copy .env.example to .env and fill in your API keys.
pause

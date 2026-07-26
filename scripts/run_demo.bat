@echo off
REM Force demo-safe embed settings on Windows.
REM Usage: scripts\run_demo.bat
setlocal
cd /d "%~dp0\.."

set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=

set HOST=127.0.0.1
set PORT=8766
set DEBUG=true
set SIMPLE_RAG_MODE=true
set ENABLE_QUERY_REWRITING=false
set ENABLE_QUERY_ROUTING=false
set CHROMA_ANONYMIZED_TELEMETRY=false
set CHROMA_DISABLE_TELEMETRY=1
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set OPENAI_EMBEDDING_MODEL=hf:BAAI/bge-small-zh-v1.5
set SIMILARITY_THRESHOLD=0.32
set PYTHONPATH=%CD%

if exist ".env" (
  for /f "usebackq tokens=* delims=" %%a in (".env") do (
    echo %%a | findstr /r "^[A-Za-z_][A-Za-z0-9_]*=" >nul && set "%%a"
  )
)
REM re-force after dotenv pollution
set OPENAI_EMBEDDING_MODEL=hf:BAAI/bge-small-zh-v1.5
set SIMILARITY_THRESHOLD=0.32
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1

if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv. Create with uv first.
  exit /b 1
)

echo Demo: http://%HOST%:%PORT%/
echo Embed: %OPENAI_EMBEDDING_MODEL% thr=%SIMILARITY_THRESHOLD%
".venv\Scripts\python.exe" -m uvicorn app.main:app --host %HOST% --port %PORT%

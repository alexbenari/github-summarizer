# github-summarizer

## Prerequisites
- Python 3.10+

## Setup and Run

### 1) PowerShell (Windows)
1. Put this project folder anywhere on your machine (example: `C:\work\github-summarizer`).
2. Open PowerShell and go to that folder:
   ```powershell
   cd C:\work\github-summarizer
   ```
3. Create a virtual environment:
   ```powershell
   python -m venv .venv
   ```
4. Activate it:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
5. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
6. Start the server:
   ```powershell
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

Test endpoint from PowerShell (`curl.exe`, not `curl` alias):

```powershell
curl.exe --% -X POST http://localhost:8000/summarize -H "Content-Type: application/json" --data-raw "{\"github_url\":\"https://github.com/psf/requests\"}"
```

### 2) Command Prompt (cmd, Windows)
1. Open Command Prompt and go to the project folder:
   ```bat
   cd C:\work\github-summarizer
   ```
2. Create a virtual environment:
   ```bat
   python -m venv .venv
   ```
3. Activate it:
   ```bat
   .venv\Scripts\activate.bat
   ```
4. Install dependencies:
   ```bat
   pip install -r requirements.txt
   ```
5. Start the server:
   ```bat
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

Test endpoint from cmd:

```bat
curl -X POST "http://localhost:8000/summarize" -H "Content-Type: application/json" -d "{\"github_url\":\"https://github.com/psf/requests\"}"
```

### 3) Linux/macOS Terminal (bash/zsh)
1. Open a terminal and go to the project folder:
   ```bash
   cd /path/to/github-summarizer
   ```
2. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   ```
3. Activate it:
   ```bash
   source .venv/bin/activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Start the server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

Test endpoint from Linux/macOS terminal:

```bash
curl -X POST "http://localhost:8000/summarize" -H "Content-Type: application/json" -d '{"github_url":"https://github.com/psf/requests"}'
```

The API is available at `http://localhost:8000`.

## Current Phase Behavior
This is Phase 1 skeleton behavior:

```json
{"status":"error","message":"Not implemented"}
```

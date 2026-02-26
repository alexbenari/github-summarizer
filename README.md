# github-summarizer

## Prerequisites
- Python 3.10+
- `NEBIUS_API_KEY` environment variable set

## Setup and Run

Extract the project folder into a local directory. E.g. C:\work\github-summarizer

### 1) Command Prompt (cmd, Windows)
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
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
5. Start the server:
   ```bat
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

Test endpoint from cmd:

```bat
curl -X POST "http://localhost:8000/summarize" -H "Content-Type: application/json" -d "{\"github_url\":\"https://github.com/psf/requests\"}"
```

### 2) Linux/macOS Terminal (bash/zsh)
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
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
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

## LLM Choice
This submission uses `Qwen/Qwen3-Coder-480B-A35B-Instruct` (configured in `config/runtime.json`). 
It was selected for strong large-repo code understanding and very large context support, which are the two highest-impact factors for repository summarization quality in this project, and given response time was not posed as a hard limitation.

## LLM Context management
- non-informative files and folders are ignored (e.g. binaries, images, .git folder, node_modules etc). Full list is in config/non-informative files.json
- Max allowed repo size portion of prompt is pre-calculated based on model context size (config -> runtime.json -> max_repo_data_ratio_in_prompt, bytes_per_token_estimate)
- File extraction from repo is prioritized by type . It is also capped by total and individual file size and file count to cap response time (config -> runtime.json -> github_gate section).
- Extracted repo files are then processed to fit into the model's context window limit. Truncation business logic is sensitive to file type in order to guarantee maximun representation of all types of informative files (docs, code, tests, build files)
- In case call fails because of context size overflow, a single retry is performed after further truncation of the repo files based on the actual token counts rturned by the failed call.
- For more details see readme-supplement-repo-extraction-logic.md

## Validation
Endpoint was validated on a variety of repo types
- base/happy path
  - 
- non-code
  - https://github.com/artnitolog/awesome-arxiv
  - https://github.com/agentskills/agentskills
- Sparse docs
  - https://github.com/Neko01t/sonus
  - https://github.com/AFAF9988/CIRCLECI-GWP
- Huge
  - https://github.com/torvalds/linux
  - https://github.com/apache/hadoop
  - https://github.com/FFmpeg/FFmpeg
- noisy
  - https://github.com/opencv/opencv
- monorepo
  - https://github.com/microsoft/vscode

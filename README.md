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
- non-informative files and folders are ignored (e.g. binaries, images, .git folder, node_modules etc). Full list is in config/non-informative-files.json
- Max allowed repo size portion of prompt is pre-calculated based on model context size (config -> runtime.json -> max_repo_data_ratio_in_prompt, bytes_per_token_estimate)
- File extraction from repo is prioritized by type . It is also capped by total and individual file size and file count to cap response time (config -> runtime.json -> github_gate section).
- Extracted repo files are then processed to fit into the model's context window limit. Truncation business logic is file category-aware (metadata/tree/readme/docs/build/tests/code) to preserve representation of each high-signal content type under budget constraints.
- In case call fails because of context size overflow, a single retry is performed after further truncation of the repo files based on the actual token counts returned by the failed call.
- For more details, see [`readme-supplement-repo-extraction-logic.md`](readme-supplement-repo-extraction-logic.md).

## Validation
Endpoint was validated on a variety of repo types
- happy path
  - https://github.com/psf/requests
  - https://github.com/alexbenari/github-summarizer [this codebase]
- Huge
  - https://github.com/torvalds/linux
  - https://github.com/apache/hadoop
  - https://github.com/FFmpeg/FFmpeg
- Non-code
  - https://github.com/artnitolog/awesome-arxiv
  - https://github.com/agentskills/agentskills
- Sparse (lack README and have very sparse documentation/code-only content)
  - https://github.com/Neko01t/sonus
  - https://github.com/AFAF9988/CIRCLECI-GWP
- noisy (many non-informative files)
  - https://github.com/opencv/opencv
- monorepo 
  - https://github.com/microsoft/vscode


curl -X POST "http://localhost:8000/summarize" -H "Content-Type: application/json" -d "{\"github_url\":\"https://github.com/alexbenari/github-summarizer\"}"

{
   "summary": "The github-summarizer project is a Python-based API service that generates human-readable summaries of public GitHub repositories. It extracts repository metadata, language statistics, directory structure, README, documentation, build configurations, tests, and code snippets, then processes this data to fit within an LLM's context window before generating a structured summary using a large language model. The service handles large repositories through intelligent truncation strategies and includes robust error handling and observability features.",
   
   "technologies":["Python","FastAPI","ghapi","httpx","pytest","Nebius AI API","Qwen LLM"],
   
   "structure":"The project follows a modular Python package structure with an app/ directory containing the main application logic. Entry point is in app/main.py which orchestrates the summarization workflow. Key modules include app/github_gate/ for GitHub API interactions, app/repo_processor/ for markdown processing and budget management, and app/llm_gate/ for LLM interactions. Tests are organized in tests/ with smoke tests in tests/smoke/. Configuration files are in config/, documentation in docs/, and implementation process notes in impl-process/. Additionally, there are CLI tools for each major component."
}

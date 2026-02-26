## Test cases for github repo summarizer

- Normal case: reuests repo: https://github.com/psf/requests
- Huge repo - one that challenges context limit
- monorepo
- Noise case: many non-informative files
- Sparse docs case: README weak, code dominates.
- non code repo 

## Pass/Fail Thresholds
- JSON valid
- quality of summary
- No hallucinations
- No severe regressions on large-context cases.

## the test repos
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
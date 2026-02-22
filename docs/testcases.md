## Test cases for github repo summarizer

- Normal case: reuests repo: https://github.com/psf/requests
- Sparse docs case: README weak, code dominates.
- Huge repo - one that challenges context limit
- monorepo
- Noise case: many non-informative files
- non code repo 

## Pass/Fail Thresholds
- JSON valid
- quality of summary
- No hallucinations
- No severe regressions on large-context cases.


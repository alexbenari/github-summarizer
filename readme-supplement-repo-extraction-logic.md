## Repo truncation business logic
  - Overall repo-data budget: 65% of model context (via max_repo_data_ratio_in_prompt=0.65). This allows for estimation errors and leaves room for the rest of the prompt.
  - Base fields: repository_metadata, language_stats, directory_tree, readme + contents of external documentation page if exists. These are truncated only as a last resort.
  - Remaining budget after base fields:
      - documentation: 40%
      - build_and_package_data: 20%
      - tests: 20%
      - code: 20%

  If one optional category is smaller than its share, its unused bytes are redistributed proportionally to the others by weight.
  If base fields overflow, truncation order is: directory_tree -> readme -> language_stats -> repository_metadata.

  Number of tokens is estimated as tokens as: bytes / bytes_per_token.
  - Initial default is 4 bytes/token (config -> runtime.json -> bytes_per_token_estimate)



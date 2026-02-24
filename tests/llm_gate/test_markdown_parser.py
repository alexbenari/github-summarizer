from app.llm_gate.errors import LlmDigestParseError
from app.llm_gate.markdown_parser import parse_repo_digest_markdown


def test_parse_repo_digest_markdown_raises_when_no_known_sections() -> None:
    try:
        parse_repo_digest_markdown("this is not a valid digest")
    except LlmDigestParseError:
        return
    raise AssertionError("Expected LlmDigestParseError for malformed markdown input.")


def test_parse_repo_digest_markdown_ignores_heading_inside_fenced_block() -> None:
    markdown = """# Repository Metadata
owner/repo

# README
## File: README.md
- Source: n/a
- UTF8 Bytes: 42
- Estimated Tokens: 11
```text
# This heading must stay in README content
Some content
```

# Code
## File: src/main.py
- Source: n/a
- UTF8 Bytes: 13
- Estimated Tokens: 4
```text
print("hi")
```
"""

    digest = parse_repo_digest_markdown(markdown)
    assert "# This heading must stay in README content" in digest.readme_text
    assert "print(\"hi\")" in digest.code_snippets


def test_parse_repo_digest_markdown_maps_not_found_and_not_requested_to_empty() -> None:
    markdown = """# Repository Metadata
Not found

# Language Stats
Not requested

# Directory Tree
Not found
"""

    digest = parse_repo_digest_markdown(markdown)
    assert digest.repository_metadata == ""
    assert digest.language_stats == ""
    assert digest.tree_summary == ""
    assert digest.readme_text == ""
    assert digest.documentation_text == ""
    assert digest.build_package_text == ""
    assert digest.test_snippets == ""
    assert digest.code_snippets == ""


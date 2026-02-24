from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import re


def test_github_gate_cli_live_smoke(tmp_path: Path) -> None:
    output_path = tmp_path / "requests-cli-output.md"
    command = [
        sys.executable,
        "-m",
        "app.github_gate.cli",
        "--github-url",
        "https://github.com/psf/requests",
        "--entities",
        "metadata,languages,tree,readme,documentation,build_package,tests,code",
        "--output",
        str(output_path),
    ]

    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    failure_details = f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    assert result.returncode == 0, f"CLI exited with non-zero status.{failure_details}"
    assert output_path.exists(), f"Output markdown file was not created.{failure_details}"
    content = output_path.read_text(encoding="utf-8")
    assert content.strip(), f"Output markdown file is empty.{failure_details}"

    sections = [
        "# Repository Metadata",
        "# Language Stats",
        "# Directory Tree",
        "# README",
        "# Documentation",
        "# Build and Package Data",
        "# Tests",
        "# Code",
        "# Extraction Stats",
        "# Warnings",
    ]

    positions: dict[str, int] = {}
    line_positions = {match.group(0): match.start() for match in re.finditer(r"^# .+$", content, flags=re.MULTILINE)}
    for section in sections:
        pos = line_positions.get(section, -1)
        assert pos != -1, f"Missing required section: {section}.{failure_details}"
        positions[section] = pos

    for idx in range(1, len(sections)):
        prev = sections[idx - 1]
        curr = sections[idx]
        assert positions[curr] > positions[prev], (
            f"Section order is invalid. '{curr}' appears before '{prev}'.{failure_details}"
        )

    for idx, section in enumerate(sections[:8]):
        start = positions[section] + len(section)
        end = positions[sections[idx + 1]] if idx + 1 < len(sections) else len(content)
        body = content[start:end].strip()
        assert body, f"Section body is empty: {section}.{failure_details}"
        assert body != "Not requested", f"Section unexpectedly marked Not requested: {section}.{failure_details}"
        assert body != "Not found", f"Section unexpectedly marked Not found: {section}.{failure_details}"

    stats_start = positions["# Extraction Stats"] + len("# Extraction Stats")
    stats_end = positions["# Warnings"]
    stats_body = content[stats_start:stats_end]
    assert "total_utf8_bytes:" in stats_body, f"Missing total_utf8_bytes in Extraction Stats.{failure_details}"
    assert (
        "total_estimated_tokens:" in stats_body
    ), f"Missing total_estimated_tokens in Extraction Stats.{failure_details}"

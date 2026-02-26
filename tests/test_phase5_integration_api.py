from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.github_gate.errors import InvalidGithubUrlError
from app.github_gate.models import DocumentationData, FileContent, GithubGateLimits, ReadmeData, RepoMetadata, RepoRef, TreeEntry
from app.llm_gate.models import SummaryResult


def test_summarize_api_success_calls_expected_flow(monkeypatch) -> None:
    import app.main as main_module

    call_order: list[str] = []

    class FakeGithubGate:
        def __init__(self) -> None:
            self.limits = GithubGateLimits()
            self.warnings: list[str] = []

        def parse_repo_url(self, github_url: str) -> RepoRef:
            call_order.append("parse_repo_url")
            return RepoRef(owner="psf", repo="requests")

        def verify_repo_access(self, repo: RepoRef) -> None:
            call_order.append("verify_repo_access")

        def get_repo_metadata(self, repo: RepoRef) -> RepoMetadata:
            call_order.append("get_repo_metadata")
            return RepoMetadata(
                owner="psf",
                repo="requests",
                default_branch="main",
                description="desc",
                topics=["http"],
                homepage="https://requests.readthedocs.io",
            )

        def get_tree(self, repo: RepoRef) -> list[TreeEntry]:
            call_order.append("get_tree")
            return [
                TreeEntry(path="README.md", type="blob", size=10, api_url="a", download_url="d"),
            ]

        def get_languages(self, repo: RepoRef) -> dict[str, int]:
            call_order.append("get_languages")
            return {"Python": 10}

        def get_readme(self, repo: RepoRef) -> ReadmeData:
            call_order.append("get_readme")
            return ReadmeData(source_url="u", content_text="readme", byte_size=6)

        def get_documentation(self, tree, metadata, limits):  # noqa: ANN001
            call_order.append("get_documentation")
            file_data = FileContent(path="docs/a.md", source_url="u", content_text="doc", byte_size=3)
            return DocumentationData(source_url="u", content_text="doc", files=[file_data], total_bytes=3)

        def get_build_and_package_data(self, tree, limits):  # noqa: ANN001
            call_order.append("get_build_and_package_data")
            return [FileContent(path="pyproject.toml", source_url="u", content_text="x", byte_size=1)]

        def get_tests(self, tree, limits):  # noqa: ANN001
            call_order.append("get_tests")
            return [FileContent(path="tests/test_a.py", source_url="u", content_text="x", byte_size=1)]

        def get_code(self, tree, limits):  # noqa: ANN001
            call_order.append("get_code")
            return [FileContent(path="src/a.py", source_url="u", content_text="x", byte_size=1)]

    class FakeLlmGate:
        def __init__(self) -> None:
            self.config = type("Cfg", (), {"model_id": "fake-model"})()

        def summarize(self, markdown_text: str) -> SummaryResult:
            call_order.append("llm_summarize")
            assert markdown_text == "PROCESSED_MARKDOWN"
            return SummaryResult(summary="s", technologies=["t"], structure="st")

    @dataclass
    class FakeProcessed:
        output_total_utf8_bytes: int = 123
        max_repo_data_size_for_prompt_bytes: int = 456

    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setattr(main_module.ConfigValidator, "validate_startup", lambda self: None)
    monkeypatch.setattr(main_module, "GithubGate", FakeGithubGate)
    monkeypatch.setattr(main_module, "LlmGate", FakeLlmGate)
    monkeypatch.setattr(main_module.RequestDebugLog, "write", lambda self: None)

    def fake_render_full_extraction_markdown(*, repo, results, warnings):  # noqa: ANN001
        call_order.append("render_full_extraction_markdown")
        return "FULL_MARKDOWN"

    def fake_process_markdown(markdown_text: str) -> FakeProcessed:
        call_order.append("process_markdown")
        assert markdown_text == "FULL_MARKDOWN"
        return FakeProcessed()

    def fake_render_processed_markdown(processed: FakeProcessed) -> str:
        call_order.append("render_processed_markdown")
        return "PROCESSED_MARKDOWN"

    monkeypatch.setattr(main_module, "render_full_extraction_markdown", fake_render_full_extraction_markdown)
    monkeypatch.setattr(main_module, "process_markdown", fake_process_markdown)
    monkeypatch.setattr(main_module, "render_processed_markdown", fake_render_processed_markdown)

    with TestClient(main_module.app) as client:
        response = client.post("/summarize", json={"github_url": "https://github.com/psf/requests"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"summary", "technologies", "structure"}
    assert payload == {"summary": "s", "technologies": ["t"], "structure": "st"}
    assert call_order == [
        "parse_repo_url",
        "verify_repo_access",
        "get_repo_metadata",
        "get_tree",
        "get_languages",
        "get_readme",
        "get_documentation",
        "get_build_and_package_data",
        "get_tests",
        "get_code",
        "render_full_extraction_markdown",
        "process_markdown",
        "render_processed_markdown",
        "llm_summarize",
    ]


def test_invalid_github_url_maps_to_400(monkeypatch) -> None:
    import app.main as main_module

    class FakeGithubGate:
        def __init__(self) -> None:
            self.limits = GithubGateLimits()
            self.warnings: list[str] = []

        def parse_repo_url(self, github_url: str) -> RepoRef:
            raise InvalidGithubUrlError("Invalid GitHub URL.")

    class FakeLlmGate:
        def __init__(self) -> None:
            self.config = type("Cfg", (), {"model_id": "unused"})()

    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setattr(main_module.ConfigValidator, "validate_startup", lambda self: None)
    monkeypatch.setattr(main_module, "GithubGate", FakeGithubGate)
    monkeypatch.setattr(main_module, "LlmGate", FakeLlmGate)
    monkeypatch.setattr(main_module.RequestDebugLog, "write", lambda self: None)

    with TestClient(main_module.app) as client:
        response = client.post("/summarize", json={"github_url": "not-a-github-url"})

    assert response.status_code == 400
    assert response.json() == {"status": "error", "message": "Invalid GitHub URL."}

def test_summarize_empty_github_url_returns_not_implemented(
    live_server: str, post_json
) -> None:
    status_code, response_json = post_json(
        url=f"{live_server}/summarize",
        payload={"github_url": ""},
    )

    assert status_code == 501
    assert isinstance(response_json, dict)
    assert set(response_json.keys()) == {"status", "message"}
    assert response_json == {"status": "error", "message": "Not implemented"}

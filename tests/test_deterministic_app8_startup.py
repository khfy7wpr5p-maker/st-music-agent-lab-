from st_music_agent.deterministic_app8_web_app import _DETERMINISTIC_APP8_HTML


def test_deterministic_app8_html_builds_with_validation_pr_gate() -> None:
    assert "Doğrulama PR aç — insan işlemi" in _DETERMINISTIC_APP8_HTML
    assert "validationPrReady" in _DETERMINISTIC_APP8_HTML
    assert "review_ready_for_pr" in _DETERMINISTIC_APP8_HTML

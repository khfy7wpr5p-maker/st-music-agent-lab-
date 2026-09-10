from st_music_agent.output import OutputPolicy, OutputSanitizer
from st_music_agent.sandbox import SandboxResult


def test_text_sanitizer_redacts_tokens_secrets_and_ansi() -> None:
    sanitizer = OutputSanitizer(sensitive_values=("private-value",))
    text = (
        "\x1b[31merror\x1b[0m "
        "Bearer abcdefghijklmnop "
        "api_key=private-value "
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )

    sanitized = sanitizer.sanitize_text(text)

    assert "\x1b" not in sanitized
    assert "private-value" not in sanitized
    assert "abcdefghijklmnop" not in sanitized
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in sanitized
    assert sanitized.count("[REDACTED]") >= 3


def test_recursive_sanitizer_redacts_sensitive_keys() -> None:
    sanitizer = OutputSanitizer()

    sanitized = sanitizer.sanitize_value(
        {
            "status": "ok",
            "token": "do-not-show",
            "nested": {"password": "hidden", "message": "safe"},
            "items": [{"secret": "hidden-too"}],
        }
    )

    assert sanitized == {
        "status": "ok",
        "token": "[REDACTED]",
        "nested": {"password": "[REDACTED]", "message": "safe"},
        "items": [{"secret": "[REDACTED]"}],
    }


def test_text_is_truncated_to_policy_limit() -> None:
    policy = OutputPolicy(max_chars_per_stream=128, truncation_marker="...[CUT]")
    sanitizer = OutputSanitizer(policy=policy)

    sanitized = sanitizer.sanitize_text("x" * 1000)

    assert len(sanitized) == 128
    assert sanitized.endswith("...[CUT]")


def test_sandbox_result_is_sanitized_before_model_exposure() -> None:
    sanitizer = OutputSanitizer(sensitive_values=("super-secret",))

    result = sanitizer.sanitize_result(
        SandboxResult(
            returncode=1,
            stdout="token=super-secret",
            stderr="Bearer abcdefghijklmnop",
        )
    )

    assert result.returncode == 1
    assert "super-secret" not in result.stdout
    assert "abcdefghijklmnop" not in result.stderr

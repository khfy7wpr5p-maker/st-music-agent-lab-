from st_music_agent.music_factory import build_default_music_domain_toolset


def test_default_music_domain_factory_binds_expected_repositories() -> None:
    toolset = build_default_music_domain_toolset(token_env="ST_GITHUB_TOKEN")

    assert (
        toolset.score_restore.client.config.repository
        == "khfy7wpr5p-maker/st-score-restore-engine"
    )
    assert (
        toolset.musicxml_tab.client.config.repository
        == "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine"
    )
    assert (
        toolset.score_editor.client.config.repository
        == "khfy7wpr5p-maker/st-score-editor-core"
    )
    assert (
        toolset.score_following.client.config.repository
        == "khfy7wpr5p-maker/st-real-time-score-following-lab"
    )
    assert toolset.score_restore.client.config.token_env == "ST_GITHUB_TOKEN"
    assert toolset.musicxml_tab.client.config.token_env == "ST_GITHUB_TOKEN"
    assert toolset.score_editor.client.config.token_env == "ST_GITHUB_TOKEN"
    assert toolset.score_following.client.config.token_env == "ST_GITHUB_TOKEN"

"""Тести розбору конфігурації.

`_env_file=None` — щоб тести не залежали від реального backend/.env,
який у розробника заповнений, а в CI відсутній.
"""

from app.config import Settings, env_file_for


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_default_env_file_is_production():
    assert env_file_for("") == ".env"


def test_app_env_selects_separate_env_file():
    """APP_ENV=test має вести на окремий конфіг — це вся ізоляція
    тестового інстансу від робочого бота."""
    assert env_file_for("test") == ".env.test"


def test_env_file_read_from_environment(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    assert env_file_for() == ".env"

    monkeypatch.setenv("APP_ENV", "test")
    assert env_file_for() == ".env.test"

    # Пробіли з .env або з оболонки не мають створювати файл ".env. "
    monkeypatch.setenv("APP_ENV", "  ")
    assert env_file_for() == ".env"


def test_env_label_reports_instance():
    assert _settings().env_label == "prod"
    assert _settings(app_env="test").env_label == "test"


def test_blank_values_from_env_example_do_not_crash():
    """`.env.example` постачається з порожніми значеннями.

    Копіювання його в `.env` не має валити застосунок: pydantic інакше
    намагається розібрати "" як int/bool і кидає ValidationError.
    """
    settings = _settings(telegram_group_chat_id="", run_bot="")

    assert settings.telegram_group_chat_id is None
    assert settings.run_bot is True


def test_group_chat_id_parses_negative_id():
    """ID груп у Telegram від'ємні."""
    settings = _settings(telegram_group_chat_id="-1001234567890")

    assert settings.telegram_group_chat_id == -1001234567890


def test_admin_ids_split_and_trimmed():
    settings = _settings(admin_telegram_ids=" 111 , 222 ,")

    assert settings.admin_ids == {111, 222}
    assert settings.is_admin(111)
    assert not settings.is_admin(999)


def test_blank_admin_ids_means_nobody_is_admin():
    settings = _settings(admin_telegram_ids="")

    assert settings.admin_ids == set()
    assert not settings.is_admin(111)


def test_cors_origins_split_and_trimmed():
    settings = _settings(cors_origins="http://a.test, http://b.test ,")

    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]

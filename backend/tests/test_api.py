import pytest

from app import repository
from app.models import ApplicationStatus
from tests.conftest import TEST_ADMIN_TOKEN


async def _make(session, **overrides):
    payload = {
        "telegram_user_id": 42,
        "telegram_username": "tester",
        "full_name": "Іван Петренко",
        "contact": "+380000000000",
        "category": "Скарга",
        "description": "Опис заявки для тесту",
    }
    payload.update(overrides)
    return await repository.create_application(session, **payload)


async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_returns_created_application(client, session):
    await _make(session)

    response = await client.get("/api/applications")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["full_name"] == "Іван Петренко"
    assert body["items"][0]["status"] == "published"


async def test_public_schema_hides_contact(client, session):
    """Контакт — персональні дані, у відкритий API він потрапляти не має."""
    await _make(session)

    body = (await client.get("/api/applications")).json()

    item = body["items"][0]
    assert "contact" not in item
    assert "telegram_user_id" not in item


async def test_admin_endpoint_exposes_contact(client, session):
    await _make(session)

    response = await client.get(
        "/api/admin/applications", headers={"X-Admin-Token": TEST_ADMIN_TOKEN}
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["contact"] == "+380000000000"


async def test_admin_endpoint_rejects_bad_token(client, session):
    await _make(session)

    assert (await client.get("/api/admin/applications")).status_code == 403
    bad = await client.get(
        "/api/admin/applications", headers={"X-Admin-Token": "wrong"}
    )
    assert bad.status_code == 403


async def test_status_filter_and_pagination(client, session):
    for i in range(3):
        await _make(session, description=f"Заявка номер {i}")
    await _make(session, status=ApplicationStatus.pending, description="У черзі")

    published = (await client.get("/api/applications?status=published")).json()
    assert published["total"] == 3

    page = (await client.get("/api/applications?limit=2&offset=0")).json()
    assert page["total"] == 4
    assert len(page["items"]) == 2
    assert page["limit"] == 2


async def test_get_single_application(client, session):
    application = await _make(session)

    response = await client.get(f"/api/applications/{application.id}")

    assert response.status_code == 200
    assert response.json()["id"] == application.id


async def test_get_missing_application_returns_404(client):
    assert (await client.get("/api/applications/999")).status_code == 404


async def test_delete_requires_token(client, session):
    application = await _make(session)

    response = await client.delete(f"/api/applications/{application.id}")

    assert response.status_code == 403
    assert (await client.get("/api/applications")).json()["total"] == 1


async def test_delete_hides_application_and_retracts_group_message(
    client, session, publisher
):
    application = await _make(session)
    await repository.set_group_message(
        session, application, chat_id=-100999, message_id=17
    )

    response = await client.delete(
        f"/api/applications/{application.id}",
        headers={"X-Admin-Token": TEST_ADMIN_TOKEN},
    )

    assert response.status_code == 204
    assert (await client.get("/api/applications")).json()["total"] == 0
    # Запис лишається в БД (soft delete), але зникає з публічної вибірки.
    assert publisher.retracted == [(-100999, 17)]


async def test_deleted_application_visible_to_admin_on_demand(client, session):
    application = await _make(session)
    await client.delete(
        f"/api/applications/{application.id}",
        headers={"X-Admin-Token": TEST_ADMIN_TOKEN},
    )

    response = await client.get(
        "/api/admin/applications?include_deleted=true",
        headers={"X-Admin-Token": TEST_ADMIN_TOKEN},
    )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "deleted"
    assert body["items"][0]["deleted_at"] is not None


@pytest.mark.parametrize("limit", [0, 101])
async def test_limit_is_bounded(client, limit):
    assert (await client.get(f"/api/applications?limit={limit}")).status_code == 422

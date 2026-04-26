import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.db.session import Base, get_db

# Use an in-memory database for tests (no real Postgres needed)
TEST_DB = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB, connect_args={"check_same_thread": False})
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client):
    await client.post("/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "secret123"
    })
    resp = await client.post("/auth/login", data={
        "username": "testuser",
        "password": "secret123"
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register(client):
    resp = await client.post("/auth/register", json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "pass123"
    })
    assert resp.status_code == 201
    assert resp.json()["username"] == "alice"


@pytest.mark.asyncio
async def test_duplicate_register(client):
    data = {"username": "bob", "email": "bob@example.com", "password": "pass"}
    await client.post("/auth/register", json=data)
    resp = await client.post("/auth/register", json=data)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/auth/register", json={
        "username": "carol", "email": "carol@example.com", "password": "mypass"
    })
    resp = await client.post("/auth/login", data={
        "username": "carol", "password": "mypass"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/auth/register", json={
        "username": "dave", "email": "dave@example.com", "password": "correct"
    })
    resp = await client.post("/auth/login", data={"username": "dave", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_channel(client, auth_headers):
    resp = await client.post("/channels/", json={"name": "general"}, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["name"] == "general"


@pytest.mark.asyncio
async def test_list_channels(client, auth_headers):
    await client.post("/channels/", json={"name": "general"}, headers=auth_headers)
    await client.post("/channels/", json={"name": "random"}, headers=auth_headers)
    resp = await client.get("/channels/", headers=auth_headers)
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_send_message(client, auth_headers):
    ch = await client.post("/channels/", json={"name": "dev"}, headers=auth_headers)
    ch_id = ch.json()["id"]
    resp = await client.post("/messages/", json={
        "content": "Hello team!",
        "channel_id": ch_id
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["content"] == "Hello team!"


@pytest.mark.asyncio
async def test_threaded_reply(client, auth_headers):
    ch = await client.post("/channels/", json={"name": "eng"}, headers=auth_headers)
    ch_id = ch.json()["id"]

    root = await client.post("/messages/", json={
        "content": "Anyone seen the bug?",
        "channel_id": ch_id
    }, headers=auth_headers)
    root_id = root.json()["id"]

    reply = await client.post("/messages/", json={
        "content": "Fixed in PR #42",
        "channel_id": ch_id,
        "reply_to_id": root_id
    }, headers=auth_headers)

    assert reply.json()["reply_to_id"] == root_id

    thread = await client.get(f"/messages/thread/{root_id}", headers=auth_headers)
    assert thread.json()["replies"][0]["content"] == "Fixed in PR #42"
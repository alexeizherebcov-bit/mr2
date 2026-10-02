"""Тесты для API кулинарной книги."""

from typing import AsyncGenerator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import main
from main import Base, get_session

# Отдельная тестовая БД (в памяти)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Создаёт тестовый клиент с чистой БД."""
    engine = create_async_engine(TEST_DATABASE_URL)
    test_session = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_session() as session:
            yield session

    main.app.dependency_overrides[get_session] = override_get_session

    with TestClient(main.app) as test_client:
        # Создаём таблицы
        import asyncio

        async def setup() -> None:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(setup())
        yield test_client

    main.app.dependency_overrides.clear()


def test_create_recipe(client: TestClient) -> None:
    """POST /recipes — создаёт рецепт и возвращает 201."""
    payload = {
        "title": "Борщ",
        "cooking_time": 90,
        "ingredients": ["свёкла", "капуста"],
        "description": "Варим...",
    }
    response = client.post("/recipes", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Борщ"
    assert data["views"] == 0
    assert data["ingredients"] == ["свёкла", "капуста"]


def test_create_recipe_validation(client: TestClient) -> None:
    """POST /recipes с пустым title — 422."""
    payload = {
        "title": "",
        "cooking_time": 90,
        "ingredients": ["а"],
        "description": "d",
    }
    response = client.post("/recipes", json=payload)
    assert response.status_code == 422


def test_get_recipes_empty(client: TestClient) -> None:
    """GET /recipes на пустой БД — пустой список."""
    response = client.get("/recipes")
    assert response.status_code == 200
    assert response.json() == []


def test_get_recipe_and_increment_views(client: TestClient) -> None:
    """GET /recipes/{id} — возвращает рецепт и инкрементит views."""
    client.post(
        "/recipes",
        json={
            "title": "Борщ",
            "cooking_time": 90,
            "ingredients": ["свёкла"],
            "description": "...",
        },
    )

    response = client.get("/recipes/1")
    assert response.status_code == 200
    assert response.json()["views"] == 1

    response = client.get("/recipes/1")
    assert response.json()["views"] == 2


def test_get_recipe_not_found(client: TestClient) -> None:
    """GET /recipes/999 — 404."""
    response = client.get("/recipes/999")
    assert response.status_code == 404


def test_sorting_by_popularity(client: TestClient) -> None:
    """Список сортируется по views desc, cooking_time asc."""
    # Создаём два рецепта с разным временем
    client.post(
        "/recipes",
        json={
            "title": "A",
            "cooking_time": 60,
            "ingredients": ["x"],
            "description": "d",
        },
    )
    client.post(
        "/recipes",
        json={
            "title": "B",
            "cooking_time": 90,
            "ingredients": ["y"],
            "description": "d",
        },
    )

    # Смотрим B дважды — он популярнее
    client.get("/recipes/2")
    client.get("/recipes/2")

    response = client.get("/recipes")
    data = response.json()
    assert data[0]["id"] == 2  # B — первый
    assert data[1]["id"] == 1  # A — второй

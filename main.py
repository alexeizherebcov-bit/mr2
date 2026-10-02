"""API кулинарной книги на FastAPI + асинхронной SQLAlchemy."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ForeignKey, Integer, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DATABASE_URL = "sqlite+aiosqlite:///./recipes.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс для ORM-моделей."""


# ─── ORM-модели ────────────────────────────────────────────────────────────


class Recipe(Base):
    """Рецепт блюда."""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cooking_time: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    ingredients: Mapped[list["Ingredient"]] = relationship(
        "Ingredient",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Ingredient(Base):
    """Ингредиент рецепта."""

    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )

    recipe: Mapped["Recipe"] = relationship("Recipe", back_populates="ingredients")


# ─── Pydantic-схемы ───────────────────────────────────────────────────────


class RecipeListItem(BaseModel):
    """Краткая информация о рецепте (для списка)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str = Field(..., description="Название рецепта")
    views: int = Field(..., description="Количество просмотров")
    cooking_time: int = Field(..., description="Время готовки (минуты)")


class RecipeDetail(BaseModel):
    """Детальная информация о рецепте."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str = Field(..., description="Название рецепта")
    cooking_time: int = Field(..., description="Время готовки (минуты)")
    ingredients: list[str] = Field(..., description="Список ингредиентов")
    description: str = Field(..., description="Текстовое описание")
    views: int = Field(..., description="Количество просмотров")


class RecipeCreate(BaseModel):
    """Схема для создания нового рецепта."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Название рецепта",
        examples=["Борщ"],
    )
    cooking_time: int = Field(
        ...,
        gt=0,
        description="Время готовки в минутах",
        examples=[90],
    )
    ingredients: list[str] = Field(
        ...,
        min_length=1,
        description="Список ингредиентов",
        examples=[["свёкла", "капуста", "мясо"]],
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Текстовое описание процесса",
        examples=["Варим бульон, добавляем овощи..."],
    )


# ─── Зависимость для получения сессии ─────────────────────────────────────


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Отдаёт асинхронную сессию SQLAlchemy.

    Yields:
        AsyncSession: сессия для работы с БД.
    """
    async with async_session() as session:
        yield session


# ─── Lifespan (создание таблиц) ───────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Создаёт таблицы при запуске приложения.

    Args:
        app: FastAPI-приложение.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Кулинарная книга API",
    description=(
        "API для сервиса рецептов. Позволяет получать список рецептов, "
        "детальную информацию и создавать новые рецепты."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Эндпоинты ────────────────────────────────────────────────────────────


@app.get(
    "/recipes",
    response_model=list[RecipeListItem],
    summary="Список всех рецептов",
    description=(
        "Возвращает список рецептов, отсортированный по популярности "
        "(количество просмотров, по убыванию). При равенстве просмотров — "
        "по времени готовки (по возрастанию)."
    ),
    tags=["recipes"],
)
async def get_recipes(
    session: AsyncSession = Depends(get_session),
) -> list[Recipe]:
    """Возвращает список всех рецептов.

    Args:
        session: сессия БД.

    Returns:
        list[Recipe]: список рецептов.
    """
    stmt = select(Recipe).order_by(Recipe.views.desc(), Recipe.cooking_time.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@app.get(
    "/recipes/{recipe_id}",
    response_model=RecipeDetail,
    summary="Детальная информация о рецепте",
    description=(
        "Возвращает полную информацию о рецепте и увеличивает счётчик "
        "просмотров на 1."
    ),
    responses={404: {"description": "Рецепт не найден"}},
    tags=["recipes"],
)
async def get_recipe(
    recipe_id: int = Path(..., ge=1, description="ID рецепта"),
    session: AsyncSession = Depends(get_session),
) -> RecipeDetail:
    """Возвращает детально рецепт и инкрементит просмотры.

    Args:
        recipe_id: ID рецепта.
        session: сессия БД.

    Returns:
        RecipeDetail: детальная информация.

    Raises:
        HTTPException: если рецепт не найден.
    """
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Рецепт с id={recipe_id} не найден",
        )

    recipe.views += 1
    await session.commit()
    await session.refresh(recipe)

    return RecipeDetail(
        id=recipe.id,
        title=recipe.title,
        cooking_time=recipe.cooking_time,
        ingredients=[i.name for i in recipe.ingredients],
        description=recipe.description,
        views=recipe.views,
    )


@app.post(
    "/recipes",
    response_model=RecipeDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый рецепт",
    description="Принимает данные нового рецепта и сохраняет его в БД.",
    tags=["recipes"],
)
async def create_recipe(
    payload: RecipeCreate,
    session: AsyncSession = Depends(get_session),
) -> RecipeDetail:
    """Создаёт новый рецепт.

    Args:
        payload: данные нового рецепта.
        session: сессия БД.

    Returns:
        RecipeDetail: созданный рецепт.
    """
    recipe = Recipe(
        title=payload.title,
        cooking_time=payload.cooking_time,
        description=payload.description,
        views=0,
    )
    recipe.ingredients = [Ingredient(name=n) for n in payload.ingredients]

    session.add(recipe)
    await session.commit()
    await session.refresh(recipe)

    return RecipeDetail(
        id=recipe.id,
        title=recipe.title,
        cooking_time=recipe.cooking_time,
        ingredients=[i.name for i in recipe.ingredients],
        description=recipe.description,
        views=recipe.views,
    )

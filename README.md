# Module 30. FastAPI + линтеры + CI

Практическая работа: код FastAPI-сервиса (кулинарная книга) из предыдущего модуля, перенесённый в отдельный публичный репозиторий, с настроенным CI.

## Стек

- **FastAPI** — веб-фреймворк.
- **SQLAlchemy 2.0 (async)** + **aiosqlite** — асинхронная работа с БД.
- **Pydantic 2.x** — валидация схем.
- **Uvicorn** — ASGI-сервер.
- **pytest** — тесты.
- **flake8, black, isort, mypy** — линтеры.

## API

| Метод | URL | Описание |
|---|---|---|
| GET | `/recipes` | Список рецептов (сортировка по популярности) |
| GET | `/recipes/{id}` | Детали рецепта (с инкрементом просмотров) |
| POST | `/recipes` | Создать новый рецепт |

## Запуск

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
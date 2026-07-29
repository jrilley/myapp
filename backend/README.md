# Backend: Telegram-бот + API заявок

Приймає заявки через Telegram-бота, зберігає їх у БД, публікує в Telegram-групу
і віддає на сайт через REST API.

```
Користувач → бот (анкета) → SQLite → ├─ повідомлення в Telegram-групу
                                     └─ GET /api/applications → React-сторінка /applications
```

## Чому один процес

`aiogram` (polling) і FastAPI живуть в одному процесі та одному event loop:
SQLite має один writer, і два окремі процеси регулярно ловили б
`database is locked`. Плюс це один юніт деплою й одна фабрика сесій.
`RUN_BOT=false` піднімає лише API — так працюють тести й CI.

## Запуск

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # заповніть TELEGRAM_BOT_TOKEN та інші значення
alembic upgrade head      # створити/оновити схему
uvicorn app.main:app --reload --port 8000
```

Фронтенд (в іншому терміналі, з кореня репозиторію):

```bash
npm install
npm start                 # http://localhost:3000/applications
```

У dev запити йдуть через `"proxy": "http://localhost:8000"` у `package.json`,
тому CORS не потрібен. Для продакшн-збірки задайте `REACT_APP_API_URL`.

## Змінні оточення

Усі описані в `.env.example`. Найважливіше:

| Змінна | Призначення |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен від [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_GROUP_CHAT_ID` | ID групи для публікації (від'ємне число) |
| `ADMIN_TELEGRAM_IDS` | Telegram-id адміністраторів через кому |
| `ADMIN_API_TOKEN` | секрет для заголовка `X-Admin-Token` |
| `DATABASE_URL` | за замовчуванням SQLite |
| `RUN_BOT` | `false` — лише API, без polling |

> **Безпека.** `backend/.env` у git не потрапляє. Токен бота ніколи не має
> потрапляти у фронтенд і **ніколи** не повинен мати префікса `REACT_APP_` —
> CRA вшиває такі змінні у публічний бандл у відкритому вигляді.

## Команди бота

| Команда | Хто | Дія |
|---|---|---|
| `/start`, `/help` | усі | довідка; `/start` скидає незавершену анкету |
| `/new` | усі | почати анкету |
| `/cancel` | усі | перервати заповнення |
| `/my` | усі | свої заявки |
| `/delete <id>` | власник або адмін | видалити заявку |

Анкета: ПІБ → контакт → категорія (кнопки) → опис → підтвердження.
При невалідному вводі бот лишається на тому ж кроці, вже введені відповіді
не губляться.

## API

| Метод | Шлях | Доступ |
|---|---|---|
| `GET` | `/api/health` | публічно |
| `GET` | `/api/applications?status=&limit=&offset=` | публічно |
| `GET` | `/api/applications/{id}` | публічно |
| `GET` | `/api/admin/applications?include_deleted=` | `X-Admin-Token` |
| `DELETE` | `/api/applications/{id}` | `X-Admin-Token` |

Документація OpenAPI — на `/docs`.

**Приватність.** Публічні відповіді не містять `contact` і `telegram_user_id`:
анкета містить особистий контакт людини, і віддавати його у відкритий API
означало б віддати телефони в пошукові індекси. Повні дані повертає лише
`/api/admin/applications`. Якщо контакти навмисно мають бути публічними —
замініть `ApplicationPublic` на `ApplicationAdmin` у `app/api/applications.py`.

**`X-Admin-Token` — це спільний секрет, а не повноцінна авторизація**: немає
ролей, ротації й аудиту. Достатньо, щоб сторонній не видалив заявку; коли
з'являться справжні акаунти адміністраторів, це місце треба замінити.

## Видалення

Видалення **м'яке**: проставляються `deleted_at` і `status='deleted'`, запис
лишається в БД, але зникає з публічних вибірок. Заявки — це персональні дані
й історія звернень, тож безповоротне стирання однією командою в чаті надто
легко зробити помилково.

Повідомлення в групі прибирається best-effort: Telegram дозволяє боту
видаляти повідомлення лише близько 48 годин, тому при невдачі текст
замінюється на «Заявку видалено». Збій у Telegram не скасовує видалення в БД.

## Модерація (наперед)

Модерації зараз немає — заявка одразу `published`. Поле `status`
(`pending`/`published`/`rejected`/`deleted`) вже є в схемі й в API, тож
увімкнути модерацію можна **без міграції**: достатньо передавати
`status=ApplicationStatus.pending` у `repository.create_application`
(виклик — у `app/bot/handlers/form.py`) і додати адмінські кнопки схвалення.

## Тести

```bash
cd backend && ./.venv/bin/pytest
```

Мережі не торкаються: БД — SQLite in-memory, публікація в Telegram підмінена
`FakePublisher`, FSM-хендлери викликаються напряму з фейковими
`Message`/`CallbackQuery` і реальним `FSMContext` на `MemoryStorage`.

## Перехід на PostgreSQL

1. `pip install asyncpg`
2. `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db`
3. `alembic upgrade head`

Шар доступу до БД (`app/repository.py`) не містить SQLite-специфіки, тож
змін у коді не потрібно.

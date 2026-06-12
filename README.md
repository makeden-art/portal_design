# portal_design

**Ядро портала управления** — хаб утилит, страница сервисов, Watchtower, подключаемые модули.

Репозиторий: [github.com/makeden-art/portal_design](https://github.com/makeden-art/portal_design)

## Архитектура

| Репозиторий | Роль |
|-------------|------|
| **portal_design** (этот) | Ядро: `/`, `/services`, API обновлений, UI-тема |
| [lisp_Nikolay](https://github.com/makeden-art/lisp_Nikolay) | **Модуль** — поперечники, нормоконтроль, ЭЦП, PDF |
| [masha-print](https://github.com/makeden-art/masha-print) | **Сервис** — печать и анализ PDF |
| `road-pdf-platform` | Docker Compose всей платформы |

```
portal_design/          ← ядро (этот репозиторий)
  portal/               — FastAPI: app, modules, services_hub
  static/               — theme.css
  main.py               — uvicorn entrypoint
  Dockerfile            — сборка вместе с модулями

lisp_Nikolay/           ← модуль-плагин
  portal_utilities/     — register(app), маршруты утилит
  vol_multi_dxf.py      — расчёт поперечников
  pipeline/             — PDF-конвейер
```

## Подключение модулей

Переменная `PORTAL_PLUGINS` — список Python-пакетов с функцией `register(app)`:

```yaml
environment:
  - PORTAL_PLUGINS=portal_utilities   # lisp_Nikolay
```

Модуль регистрирует карточки на главной и свои маршруты через `portal.modules.register_plugin()`.

## Локальная разработка

```bash
cd /opt/road-pdf-platform
export PYTHONPATH=portal_design:lisp_Nikolay
export PORTAL_PLUGINS=portal_utilities
uvicorn main:app --app-dir portal_design --reload --port 8000
```

## Сборка и деплой

```bash
cd /opt/road-pdf-platform
docker compose -f docker-compose.platform.yml build portal
docker compose -f docker-compose.platform.yml up -d portal
```

Образ: `makeden/geo_calc_app:latest` (имя сохранено для Watchtower).

## Структура

```
portal_design/
  docs/           — архитектура
  ui/             — макеты, theme.css (источник)
  static/         — theme.css для /static/
  integrations/   — API-контракты
  portal/         — Python-пакет ядра
```

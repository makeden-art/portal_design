# portal_design

Дизайн и UI-контракт **портала управления** (хаб утилит).

Связанные репозитории:

| Репозиторий | Роль |
|-------------|------|
| [lisp_Nikolay](https://github.com/makeden-art/lisp_Nikolay) | Бэкенд + встроенные страницы портала |
| [masha-print](https://github.com/makeden-art/masha-print) | Микросервис PDF/печати |
| `road-pdf-platform` / `docker-compose.platform.yml` | Сборка всей платформы в контейнерах |

## Структура

```
portal_design/
  docs/           — архитектура, макеты, гайдлайн
  ui/             — общая тема, компоненты, шаблоны
  integrations/   — схемы n8n, API-контракты
```

## Использование в портале

Скопировать или смонтировать `ui/theme.css` в `lisp_Nikolay/static/` (когда появится каталог static) или подключать в HTML-страницах через `/static/theme.css`.

## Деплой платформы

См. родительский проект: `docker compose -f docker-compose.platform.yml up -d --build`

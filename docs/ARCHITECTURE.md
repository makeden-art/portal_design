# Архитектура платформы

## Слои

```mermaid
flowchart TB
  user[Пользователь] --> portal[Портал portal_design :8080]
  portal --> hub[Главная /]
  portal --> services[/services]
  portal --> plugins[PORTAL_PLUGINS]
  plugins --> lisp[lisp_Nikolay модуль]
  lisp --> calc[/calc]
  lisp --> norm[/norm]
  lisp --> verify[/verify]
  lisp --> pdf[/pdf]
  portal --> masha[masha-print :8000]
  portal --> n8n[n8n :5678]
  watchtower[Watchtower] --> portal
  watchtower --> masha
```

## Принцип разделения

1. **Портал** (`portal_design`) — отдельная сущность: хаб, сервисы, обновления, тема UI.
2. **Модули** — подключаются через `register(app)` и `register_plugin()`.  
   `lisp_Nikolay` — один из таких модулей (не ядро).
3. **Сервисы** — отдельные контейнеры: masha-print, n8n, OpenProject.

## API модуля (контракт плагина)

```python
# lisp_Nikolay/portal_utilities/__init__.py
def register(app: FastAPI) -> None:
    from portal.modules import register_plugin
    register_plugin(plugin_id="lisp_Nikolay", modules=..., cards=..., ...)
    app.include_router(router)
```

## Страницы

| Путь | Владелец |
|------|----------|
| `/` | portal_design |
| `/services` | portal_design |
| `/calc`, `/norm`, `/verify`, `/pdf` | lisp_Nikolay (модуль) |

## Автообновление

- Портал: `VERSION` в [portal_design](https://github.com/makeden-art/portal_design)
- Модуль утилит: образ `makeden/geo_calc_app:latest` (портал + lisp_Nikolay)
- masha-print: отдельный образ `makeden/masha-print:latest`

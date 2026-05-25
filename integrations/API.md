# API-контракты платформы

Базовый URL портала: `http://<host>:8080`

## Портал

- `GET /api/services` — статусы микросервисов
- `POST /api/services/update/{id}` — Watchtower
- `GET /api/pipeline/sla` — SLA конвейера PDF
- `POST /api/jobs/pdf` — новая задача PDF

## masha-print

- `GET /api/license/status`
- `POST /api/analyze-pdf`

## n8n

- Webhook вход: настраивается в n8n
- Исходящий: `N8N_WEBHOOK_OUT` в портале

# Telegram Task History Pagination

The paired Telegram task-history endpoint supports bounded keyset pagination:

```http
GET /integrations/telegram/tasks?limit=20
Authorization: Bearer <paired-client-access-token>
```

The access token must include the `tasks:read` scope. The optional `limit` is between 1 and 50 (default: 20).

A response contains the current page and pagination metadata:

```json
{
  "tasks": [],
  "count": 20,
  "has_more": true,
  "next_cursor": "opaque-cursor"
}
```

When `has_more` is true, pass `next_cursor` unchanged on the next request:

```http
GET /integrations/telegram/tasks?limit=20&cursor=opaque-cursor
```

Treat the cursor as opaque. It is a position marker, not an access token; every request is independently authenticated and filtered to the exact paired Telegram client. A malformed cursor returns HTTP 422. The ordering is stable by descending `created_at` and task UUID, so records sharing a timestamp are not skipped between pages.

`count` is the number of tasks in the current page, not a total count of all historical tasks. When there are no more results, `has_more` is false and `next_cursor` is null.

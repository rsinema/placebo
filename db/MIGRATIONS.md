# Database Migrations

Schema is managed by [`golang-migrate/migrate`](https://github.com/golang-migrate/migrate). Migration files live in `db/migrations/` as paired `up`/`down` SQL.

A `migrate` service in `docker-compose.yml` runs `migrate up` once on startup against the `db` service; the bots and API depend on it completing successfully, so any pending migrations apply before app code boots.

## File naming

```
db/migrations/
  NNNNNN_short_name.up.sql
  NNNNNN_short_name.down.sql
```

`NNNNNN` is a zero-padded sequence (`000001`, `000002`, …). Each forward change must ship with a matching `down.sql` that reverses it.

## Adding a migration

1. Pick the next number (one higher than the largest `NNNNNN` in `db/migrations/`).
2. Create both files: `NNNNNN_<name>.up.sql` and `NNNNNN_<name>.down.sql`.
3. Write the forward change in `up.sql`. Prefer idempotent statements (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN IF NOT EXISTS`) so a partial failure leaves the DB recoverable.
4. Write the reverse in `down.sql` (drop in reverse-dependency order).
5. Apply with `docker compose up migrate` (or just `docker compose up --build`, which also runs it).

There is no separate canonical `init.sql` — replaying the migrations from scratch is the canonical schema.

## Applying / rolling back manually

```bash
# Apply all pending migrations
docker compose up migrate

# Roll back the last migration
docker compose run --rm migrate \
  -path=/migrations \
  -database "postgres://$POSTGRES_USER:$POSTGRES_PASSWORD@db:5432/$POSTGRES_DB?sslmode=disable" \
  down 1

# Show current version
docker compose run --rm migrate \
  -path=/migrations \
  -database "postgres://$POSTGRES_USER:$POSTGRES_PASSWORD@db:5432/$POSTGRES_DB?sslmode=disable" \
  version
```

## First-time switchover from the old `init.sql` workflow

The bundled migrations are idempotent (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, exception-guarded `CREATE TYPE`), so an existing DB provisioned by the old `init.sql` can just run them:

```bash
docker compose up migrate
```

The migrate service will create the `schema_migrations` table, replay both migrations as no-ops against the existing schema, and record versions 1 and 2 as applied. Subsequent migrations (`000003_*` and beyond) will run normally.

If you'd rather skip replaying the existing migrations entirely, tell `migrate` to record the current version without running anything:

```bash
docker compose run --rm migrate \
  -path=/migrations \
  -database "postgres://$POSTGRES_USER:$POSTGRES_PASSWORD@db:5432/$POSTGRES_DB?sslmode=disable" \
  force 2
```

## Resetting from scratch (destroys data)

```bash
docker compose down -v   # -v removes the pgdata volume
docker compose up --build
```

The migrate service will then run every migration in order against the empty database.

## Migration log

| #      | File                              | Description                                |
| ------ | --------------------------------- | ------------------------------------------ |
| 000001 | `000001_initial_schema.up.sql`    | Metrics, check-ins, experiments, settings  |
| 000002 | `000002_gym.up.sql`               | Add `exercises` and `exercise_sets` tables |

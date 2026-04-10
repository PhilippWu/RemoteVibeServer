# fullstack-baseline — Starter App Template

A production-ready fullstack application that is automatically bootstrapped
inside every new Coder workspace when `STARTER_TEMPLATE=fullstack-baseline` is
configured.

It is based on **[tiangolo/full-stack-fastapi-template](https://github.com/tiangolo/full-stack-fastapi-template)**
— the official FastAPI project template maintained by the FastAPI author.

---

## What you get

| Layer       | Technology                                    |
|-------------|-----------------------------------------------|
| Backend API | FastAPI (Python) + SQLModel ORM               |
| Database    | PostgreSQL 16                                 |
| Migrations  | Alembic                                       |
| Frontend    | React + Vite + TypeScript + Chakra UI         |
| Auth        | JWT bearer tokens (login / refresh)           |
| RBAC        | Superuser + regular-user roles                |
| CRUD        | Items resource (scaffold for your own models) |
| Dev stack   | Docker Compose                                |

---

## Ports (inside the workspace)

| Service          | URL                               |
|------------------|-----------------------------------|
| Frontend         | http://localhost:5173             |
| Backend API      | http://localhost:8000             |
| Interactive docs | http://localhost:8000/docs        |
| Adminer (DB UI)  | http://localhost:8080             |

---

## Default credentials

| Field    | Value                  |
|----------|------------------------|
| Email    | `admin@example.com`    |
| Password | `changeme123`          |

Change the password immediately after first login.

---

## How it works

When a workspace starts with `STARTER_TEMPLATE=fullstack-baseline`, the
`startup_script` in `coder/main.tf`:

1. Clones `tiangolo/full-stack-fastapi-template` into `~/fullstack-baseline`
2. Patches `.env` (project name, random `SECRET_KEY`, default superuser)
3. Runs `docker compose up -d`
4. Creates `~/fullstack-baseline/.bootstrapped` to make subsequent starts
   idempotent

The stack is started on every workspace launch (via `docker compose up -d`),
and stopped automatically when the workspace is stopped.

---

## Re-running the bootstrap

If the bootstrap was interrupted or you want a clean slate:

```bash
rm ~/fullstack-baseline/.bootstrapped
# restart the workspace, or run the startup script manually
```

## Customising

Fork the template or edit files directly in `~/fullstack-baseline`.  The
`.bootstrapped` marker prevents re-cloning, so local changes persist across
workspace restarts.

For a clean re-clone:

```bash
rm -rf ~/fullstack-baseline
# restart the workspace
```

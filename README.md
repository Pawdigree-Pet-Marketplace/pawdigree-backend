# Pawdigree Backend

Django REST API for Pawdigree, a pet marketplace in Uganda.

## Run the backend locally

These steps give you a backend on `http://localhost:8000` that the frontends
can call while the deployed backend is unavailable.

### 1. Get the code and install

```bash
git clone https://github.com/Pawdigree-Pet-Marketplace/pawdigree-backend.git
cd pawdigree-backend
git checkout dev
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The backend is developed on Python 3.14.

### 2. Create the database

The backend uses PostgreSQL. By default it connects as the `postgres` user to a
database called `pawdigree` on `localhost:5432`. On Ubuntu:

```bash
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'choose_a_password';"
sudo -u postgres createdb pawdigree
```

On other systems, install PostgreSQL your usual way and create the same
database.

### 3. Create your `.env`

```bash
cp .env.example .env
```

Then edit `.env`:

- `DEBUG`: set it to `True`. With `DEBUG` off, the backend redirects every
  `http` request to `https` and uses secure-only cookies, so the frontend
  cannot reach it on `http://localhost:8000`.
- `SECRET_KEY`: any long random string. To generate one:
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `DB_PASSWORD`: the password you chose in step 2.
- `DATABASE_URL`: delete this line (or comment it out), so the default local
  database is used.
- `FRONTEND_URL`: `http://localhost:5173`
- `ADMIN_FRONTEND_URL`: only needed if the admin portal runs somewhere other
  than `http://localhost:5173`. Set it to that address, with `http://` and no
  trailing slash. Several addresses can be separated with commas.

`.env` holds secrets. Never commit it or paste it into a chat.

### 4. Set up the database and start the server

```bash
python manage.py migrate
python manage.py createcachetable
python manage.py runserver
```

Check it works: open `http://localhost:8000/api/health/`. You should get a
200 response. The full list of endpoints is in Swagger at
`http://localhost:8000/api/docs/`.

The customer services listing contract is in
[docs/services-listing-api.md](docs/services-listing-api.md).

### 5. Point your frontend at it

In your frontend's `.env`, set the API URL to `http://localhost:8000/api`
(keep the `/api` at the end). The backend allows requests from
`http://localhost:5173`, the default Vite port. A frontend or the admin
portal on any other address also needs `FRONTEND_URL` or
`ADMIN_FRONTEND_URL` set in the backend's `.env` (see the variables above).

### 6. Create an admin account to log in with

```bash
python manage.py create_system_admin
```

It asks for an email and password. Log in with `POST /api/auth/login/admin/`.
The system admin creates the other admin accounts with
`POST /api/admin/administrators/`, sending its access token. Only `email` and
`password` are required. The full request and response are in
[docs/admin-management-api.md](docs/admin-management-api.md).

### 7. Create categories

A fresh database has no categories. Logged in as an admin, create them with
`POST /api/categories/`. Each category must have a `kind`: `merchandise`,
`services` or `pets`. To change the kind of an existing category, use
`PATCH /api/categories/<id>/`.

Products accept only active `merchandise` categories, and services accept only
active `services` categories. Pet businesses can request only active `pets`
categories. The frontend reads categories without logging in from
`GET /api/categories/public/?kind=merchandise` (or `services`, `pets`); a kind
filter returns only that kind.

### Emails

When `EMAIL_BACKEND` is not set in `.env`, emails are printed in the terminal
that runs `runserver` instead of being sent. For example, a password reset
link shows up there.

## Run the tests

```bash
pytest
```

## Notes

- Never commit `.env` or share its contents.
- Work on a feature branch off `dev` and open pull requests into `dev`.

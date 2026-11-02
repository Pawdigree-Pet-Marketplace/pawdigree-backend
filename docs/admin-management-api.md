# Administrator management API

For the frontend team. All paths are relative to the API base URL
(for example `https://pawdigree-bckd.onrender.com`). IDs, emails and dates in
the examples are illustrative; field names and shapes are the real ones.

## 1. Who can do what

| Role | Can use the endpoints below? |
|---|---|
| `SYSTEM_ADMIN` | Yes, all of them |
| `ADMIN`, `VENDOR`, `CUSTOMER` | No, `403` |
| Not logged in | No, `401` |

- The check is on the **`SYSTEM_ADMIN` role**. A Django superuser without that
  role also gets `403`.
- Only SYSTEM_ADMINs manage ADMINs. These endpoints only ever see accounts with
  role `ADMIN`. A SYSTEM_ADMIN, vendor or customer id returns `404`, so
  SYSTEM_ADMIN accounts are neither visible nor editable here.
- Roles are set by the server. Any `role`, `is_staff`, `is_superuser` or
  `is_active` sent in a request body is ignored.
- SYSTEM_ADMIN accounts cannot be created through the API. The first one is
  created on the server with a management command (see the handover notes).

## 2. Logging in

`POST /api/auth/login/admin/`  (no token needed)

```json
{ "email": "systemadmin@example.com", "password": "YourPassword123!" }
```

Success `200`:

```json
{
  "access": "<access token>",
  "refresh": "<refresh token>",
  "role": "SYSTEM_ADMIN"
}
```

`role` is `SYSTEM_ADMIN` or `ADMIN`. Use it to decide which screens to show.
Only `SYSTEM_ADMIN` sees the administrator management screens.

Wrong password, a non-admin account and a deactivated account all return the
same `400`, so the message never reveals which one it was:

```json
{ "non_field_errors": ["Invalid email or password."] }
```

Missing fields return `400` such as `{ "email": ["This field is required."] }`.

Login is limited to 10 attempts per minute (shared with the other login
endpoints). Past that you get `429` with `{ "detail": "..." }`.

## 3. Sending the token

Send the **access** token on every request:

```
Authorization: Bearer <access>
```

- The access token lasts **15 minutes**.
- Without a token, or with an expired or invalid one: `401`.
- If a SYSTEM_ADMIN deactivates an admin, that admin's refresh tokens are revoked
  immediately and their existing access token stops working too (`401`).

### Refreshing

`POST /api/auth/token/refresh/`

```json
{ "refresh": "<refresh token>" }
```

Success `200` returns a new pair. **Rotation is on**: the old refresh token is
blacklisted, so store the new `refresh` every time.

```json
{ "access": "<new access token>", "refresh": "<new refresh token>" }
```

A refresh token lasts 7 days, and a session ends 30 days after the original login
however often it was refreshed. After that, refresh returns `401` and the user
must log in again.

Suggested flow: on a `401`, try one refresh. If the refresh also returns `401`,
send the user to the login page.

### Logging out

`POST /api/auth/logout/` with a Bearer access token and
`{ "refresh": "<refresh token>" }` returns `200`
`{ "detail": "Successfully logged out." }`. An invalid or expired refresh token
returns `400` `{ "non_field_errors": ["Invalid or expired refresh token."] }`.

## 4. Endpoints

All require `Authorization: Bearer <access>` and the `SYSTEM_ADMIN` role.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/administrators/` | List administrators (paginated) |
| POST | `/api/admin/administrators/` | Create an administrator |
| GET | `/api/admin/administrators/{id}/` | Retrieve one |
| PATCH | `/api/admin/administrators/{id}/` | Update name and phone |
| POST | `/api/admin/administrators/{id}/activate/` | Activate |
| POST | `/api/admin/administrators/{id}/deactivate/` | Deactivate |

`POST /api/auth/register/admin/` does the same as creating an administrator and
is kept for compatibility. New code should use the `/api/admin/` path.
`PUT` and `DELETE` are not supported (`405`). Administrators are deactivated,
never deleted.

### The administrator object

```json
{
  "id": 7,
  "username": "jane",
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@example.com",
  "phone": "+256700123456",
  "role": "ADMIN",
  "is_active": true,
  "date_joined": "2026-11-01T10:15:30.123456Z"
}
```

Passwords and password hashes are never returned. Dates are UTC.

### List

`GET /api/admin/administrators/?page=1&page_size=20`

- `page` starts at 1. `page_size` defaults to 20 and is capped at 50.
- Results are ordered by `id`.

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 7,
      "username": "jane",
      "first_name": "Jane",
      "last_name": "Doe",
      "email": "jane@example.com",
      "phone": "+256700123456",
      "role": "ADMIN",
      "is_active": true,
      "date_joined": "2026-11-01T10:15:30.123456Z"
    }
  ]
}
```

`next` and `previous` are full URLs or `null`. A page past the end returns `404`.

### Create

`POST /api/admin/administrators/`

| Field | Required | Notes |
|---|---|---|
| `email` | Yes | Stored lowercase. Must not already exist, ignoring case |
| `password` | Yes | At least 8 characters, must pass the password rules. Never returned |
| `username` | No | If left out, one is made from the part of the email before `@` |
| `first_name`, `last_name` | No | Up to 150 characters |
| `phone` | No | International format, for example `+256700123456`. Without a `+`, the number is read as Ugandan. Returned in `+256...` form |

```json
{
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@example.com",
  "phone": "0700123456",
  "password": "StrongPass123!"
}
```

Success `201` returns the fields below. There is no `is_active` or
`date_joined` in the create response; fetch the object if you need them.
The new account is active and can log in right away.

```json
{
  "id": 7,
  "username": "jane",
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@example.com",
  "phone": "+256700123456",
  "role": "ADMIN"
}
```

Validation errors return `400`, with each field name mapped to a list of messages:

```json
{
  "email": ["user with this email already exists."],
  "password": ["This password is too common."],
  "phone": ["Enter a valid phone number including the country code, e.g. +256700123456."]
}
```

### Retrieve

`GET /api/admin/administrators/{id}/` returns the administrator object (`200`).

### Update

`PATCH /api/admin/administrators/{id}/` changes only `first_name`, `last_name`
and `phone`. Any other field in the body is ignored.

```json
{ "first_name": "Janet" }
```

Returns `200` with the full administrator object. An invalid phone returns `400`
as shown above.

### Activate and deactivate

`POST /api/admin/administrators/{id}/activate/` and
`POST /api/admin/administrators/{id}/deactivate/` take **no body** and return
`200` with the full administrator object, with `is_active` updated.

- Deactivating also signs the administrator out everywhere (refresh tokens are
  revoked).
- Repeating the same call is harmless and returns `200`.

## 5. Error responses

| Status | When | Body |
|---|---|---|
| 400 | Validation error | Field errors as above, or `{ "non_field_errors": [...] }` |
| 401 | No token, or an invalid or expired token | `{ "detail": "..." }` |
| 403 | Logged in but not `SYSTEM_ADMIN` | `{ "detail": "..." }` |
| 404 | Unknown id, or an id that is not an ADMIN | `{ "detail": "..." }` |
| 405 | `PUT` or `DELETE` | `{ "detail": "..." }` |
| 429 | Too many login attempts | `{ "detail": "..." }` |

Show your own friendly text based on the status code. The wording of `detail`
can change.

## 6. Good to know

- **Swagger** (`/api/docs/`) shows the admin login response with only `email`.
  The real response is `access`, `refresh` and `role`, as in section 2.
- **Passwords:** there is no change-password endpoint. A new administrator
  receives their password from the SYSTEM_ADMIN, and can change it afterwards
  through the normal password reset by email.
- **Audit trail:** creating, activating and deactivating administrators is
  recorded on the server. There is no API to read it yet.

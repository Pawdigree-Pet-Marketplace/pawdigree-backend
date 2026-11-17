# Administrator user management API

All routes below are relative to the API base URL. They require a valid
`Authorization: Bearer <access-token>` header and a user whose role is exactly
`SYSTEM_ADMIN`. A superuser without that role is not authorized. Anonymous users
receive `401`; other authenticated roles receive `403`.

## List registered users

`GET /api/admin/users/`

Lists CUSTOMER, VENDOR and regular ADMIN accounts. SYSTEM_ADMIN accounts and
all superusers are excluded. The response never includes passwords, tokens,
staff flags or other authentication fields.

Supported query parameters:

| Parameter | Behavior |
|---|---|
| `search` | Case-insensitive search across username, first name, last name and email |
| `role` | `CUSTOMER`, `VENDOR` or `ADMIN` |
| `status` | `active`, `deactivated` or `suspended` |
| `page` | Page number, starting at 1 |
| `page_size` | Defaults to 20; maximum is 50 |

The `summary` counts cover the complete eligible user population, regardless
of search, role/status filters or the current page.

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "summary": {
    "total": 12,
    "active": 9,
    "deactivated": 2,
    "suspended": 1
  },
  "results": [
    {
      "id": 24,
      "first_name": "Casey",
      "last_name": "Example",
      "email": "casey@example.com",
      "role": "CUSTOMER",
      "status": "active",
      "date_joined": "2026-11-01T10:15:30Z"
    }
  ]
}
```

Each result contains only `id`, `first_name`, `last_name`, `email`, `role`,
`status` and `date_joined`. `next` and `previous` are full URLs or `null`. An
invalid role or status filter returns `400`; a page beyond the available range
returns `404`.

## Account status actions

Only CUSTOMER and VENDOR accounts can be managed by these endpoints. Regular
ADMIN, SYSTEM_ADMIN, superuser and nonexistent target IDs are treated as
unavailable and return `404`. A SYSTEM_ADMIN cannot change their own account;
that request returns `400`.

| Method and path | Effect |
|---|---|
| `POST /api/admin/users/{user_id}/activate/` | Sets status to `active` and `is_active` to `true` |
| `POST /api/admin/users/{user_id}/deactivate/` | Sets status to `deactivated`, `is_active` to `false`, and revokes outstanding refresh tokens |
| `POST /api/admin/users/{user_id}/suspend/` | Sets status to `suspended`, `is_active` to `false`, revokes outstanding refresh tokens, and audits the reason |

All actions return `200` with the updated safe user object:

```json
{
  "id": 24,
  "first_name": "Casey",
  "last_name": "Example",
  "email": "casey@example.com",
  "role": "CUSTOMER",
  "status": "suspended",
  "date_joined": "2026-11-01T10:15:30Z"
}
```

Activation supports accounts previously deactivated or suspended. The service
keeps the historical suspension event intact and writes a separate activation
event. Repeating an action when the account is already in the requested state
is idempotent and does not create a duplicate audit event.

Suspension requires a JSON body containing a non-empty reason. Whitespace is
trimmed before validation and storage:

```json
{ "reason": "Repeated policy violations" }
```

Missing or whitespace-only reasons return `400`. The reason is stored in the
suspension audit event, not on the User record, so it remains available after
reactivation. A repeated suspension does not overwrite the original audit
reason.

The lifecycle updates and audit records run transactionally. The service locks
the target user row while checking and changing its status. Vendor approval
(`approved`) is separate and is not affected by these account actions.

## Authentication and token behavior

Deactivation and suspension revoke outstanding refresh tokens and set
`is_active` to `false`. Login, refresh and authentication of existing access
tokens reject an inactive account. Access tokens are not individually
blacklisted, however. If an account is reactivated before an earlier access
token expires, that old token may become usable again until its 15-minute
expiration. This feature does not add per-access-token revocation.

## Errors

| Status | Meaning |
|---|---|
| `400` | Missing/blank suspension reason or attempt to change the acting SYSTEM_ADMIN's own account |
| `401` | Missing, invalid or expired authentication |
| `403` | Authenticated role is not SYSTEM_ADMIN |
| `404` | Target does not exist or is a protected account type |

Response detail wording may change; clients should use the HTTP status and
field-level validation errors rather than matching message text.

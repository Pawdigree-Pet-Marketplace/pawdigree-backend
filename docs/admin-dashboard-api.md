# Administrator Dashboard API

## Overview

The administrator dashboard API provides read-only aggregate metrics for the
Pawdigree platform. It supports dashboard overview cards, charts, and tables.
This document covers the backend API only; it does not describe or implement a
frontend.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/admin/dashboard/summary/` | High-level counts for overview cards. |
| `GET` | `/api/admin/dashboard/statistics/` | Detailed role, status, listing, and type breakdowns. |

Both endpoints are read-only. They do not accept a request body or query
parameters.

## Authentication and authorization

Authenticate with the backend's JWT access token using this header:

```http
Authorization: Bearer <access_token>
```

Both endpoints require an authenticated user and the `IsAdmin` permission.
Users with the `ADMIN` or `SYSTEM_ADMIN` role are allowed. Authenticated Django
superusers are also allowed regardless of their assigned role. Ordinary
customer and vendor accounts without superuser privileges are denied access.

Unauthenticated requests receive HTTP `401 Unauthorized`. An authenticated user
without permission, including an ordinary customer or vendor account, receives
HTTP `403 Forbidden`. The body uses DRF's standard JSON `detail` error format;
exact message text may depend on the configured authentication and exception
handling.

## Summary response

The successful response is a JSON object. Every value is an integer count.

| Field | Meaning and counting rule |
|---|---|
| `users` | All rows in the custom `User` table, across all roles and account statuses. |
| `customers` | Users whose role is `CUSTOMER`. |
| `vendors` | User accounts whose role is `VENDOR`. This counts vendor accounts, not businesses. |
| `businesses` | All business records, regardless of verification or active state. |
| `listings` | Combined number of Pet, Product, and Service records, regardless of approval or active state. |
| `bookings` | All booking records, across all booking statuses. |
| `orders` | Parent customer checkout `Order` records. A parent order is counted once regardless of how many `VendorOrder` records it contains. |
| `reports` | All report records, across the statuses currently supported by the Report model. |

Illustrative example only; these are not live platform counts:

```json
{
  "users": 120,
  "customers": 90,
  "vendors": 25,
  "businesses": 30,
  "listings": 200,
  "bookings": 42,
  "orders": 58,
  "reports": 13
}
```

## Statistics response

The statistics response contains the following structure. All leaves are
integer counts. Choice-based maps include every current model choice, including
choices with a count of zero.

```json
{
  "users": {
    "total": 120,
    "by_role": {
      "CUSTOMER": 90,
      "VENDOR": 25,
      "ADMIN": 4,
      "SYSTEM_ADMIN": 1
    },
    "by_status": {
      "active": 111,
      "deactivated": 5,
      "suspended": 4
    }
  },
  "vendors": {
    "total": 25,
    "by_status": {
      "active": 23,
      "deactivated": 1,
      "suspended": 1
    }
  },
  "businesses": {
    "total": 30,
    "by_verification_status": {
      "draft": 2,
      "pending": 4,
      "changes_requested": 1,
      "approved": 20,
      "suspended": 1,
      "rejected": 2
    },
    "by_active_state": {
      "active": 25,
      "inactive": 5
    }
  },
  "listings": {
    "total": 200,
    "by_type": {
      "pets": {
        "total": 40,
        "approval": {"approved": 30, "pending": 5, "rejected": 3},
        "active": 35,
        "inactive": 5
      },
      "products": {
        "total": 100,
        "approval": {"approved": 80, "pending": 10, "rejected": 5},
        "active": 90,
        "inactive": 10
      },
      "services": {
        "total": 60,
        "approval": {"approved": 50, "pending": 4, "rejected": 3},
        "active": 55,
        "inactive": 5
      }
    }
  },
  "bookings": {
    "total": 42,
    "by_status": {
      "pending": 10,
      "accepted": 12,
      "declined": 5,
      "completed": 8,
      "cancelled": 7
    }
  },
  "orders": {
    "total": 58,
    "by_status": {
      "PENDING_PAYMENT": 6,
      "PAID": 44,
      "CANCELLED": 5,
      "EXPIRED": 3
    }
  },
  "reports": {
    "total": 13,
    "by_status": {"PENDING": 13},
    "by_reason": {
      "INAPPROPRIATE_CONTENT": 2,
      "MISLEADING_INFORMATION": 1,
      "SUSPECTED_FRAUD": 3,
      "OFFENSIVE_CONTENT": 2,
      "SUSPICIOUS_ACTIVITY": 3,
      "OTHER": 2
    }
  }
}
```

The example counts are illustrative. Each response is generated from current
database records and model choices.

### Statistics fields

| Object / field | Contents |
|---|---|
| `users.total` | All user records. |
| `users.by_role` | Counts for `CUSTOMER`, `VENDOR`, `ADMIN`, and `SYSTEM_ADMIN`. |
| `users.by_status` | Counts for account statuses `active`, `deactivated`, and `suspended`, across all roles. |
| `vendors.total` | Number of vendor user accounts. |
| `vendors.by_status` | The same account statuses, restricted to vendor accounts. |
| `businesses.total` | All business records. |
| `businesses.by_verification_status` | Counts for `draft`, `pending`, `changes_requested`, `approved`, `suspended`, and `rejected`. |
| `businesses.by_active_state` | `active` and `inactive` business counts from `is_active`. |
| `listings.total` | Sum of the Pet, Product, and Service totals. |
| `listings.by_type` | Separate `pets`, `products`, and `services` objects. Each has `total`, an `approval` object, and `active` / `inactive` counts. |
| `bookings.total` | All booking records. |
| `bookings.by_status` | Counts for `pending`, `accepted`, `declined`, `completed`, and `cancelled`. |
| `orders.total` | Parent `Order` records. |
| `orders.by_status` | Counts for `PENDING_PAYMENT`, `PAID`, `CANCELLED`, and `EXPIRED`. |
| `reports.total` | All report records. |
| `reports.by_status` | Counts for the current Report status choices; currently only `PENDING`. |
| `reports.by_reason` | Counts for `INAPPROPRIATE_CONTENT`, `MISLEADING_INFORMATION`, `SUSPECTED_FRAUD`, `OFFENSIVE_CONTENT`, `SUSPICIOUS_ACTIVITY`, and `OTHER`. |

## Metric definitions and business rules

### Users, vendors, and businesses

`users` includes all user rows. Role and account-status breakdowns are derived
from the `User` model. `vendors` counts users with the `VENDOR` role; it is not
a business count. A vendor may own multiple businesses. Business verification
and activity are counted separately from vendor account status.

### Listings

The combined listing total is the sum of all Pet, Product, and Service rows.
Each type's `total`, approval counts, and active-state counts are separate
dimensions. Approval buckets are defined as follows:

- `approved`: `approved=True`.
- `pending`: `approved=False`, `is_active=True`, and an empty
  `rejection_reason`. This matches each listing model's `pending_review()`
  queryset.
- `rejected`: `approved=False` and a non-empty `rejection_reason`, matching
  the existing rejection action behavior.

Active and inactive counts use `is_active=True` and `is_active=False`
respectively. These dimensions do not necessarily partition the approval
counts: for example, an inactive, unapproved listing with no rejection reason
is not counted as pending. Counts include listings regardless of public
visibility, availability, or business approval.

### Bookings and orders

Booking buckets come from `Booking.Status`: `pending`, `accepted`, `declined`,
`completed`, and `cancelled`.

Orders count parent customer checkout `Order` rows. `VendorOrder` records track
each business's portion of a checkout and are not counted as separate customer
orders. Order buckets come from `Order.Status`: `PENDING_PAYMENT`, `PAID`,
`CANCELLED`, and `EXPIRED`.

### Reports

Report status and reason buckets come directly from the Report model. Its
currently supported status is only `PENDING`; the API does not report
moderation statuses that are not implemented. Reasons are the six keys shown
in the response example.

## Frontend integration guidance

- Call the summary endpoint for overview cards.
- Call the statistics endpoint for charts and tables.
- Treat all counts as numeric values. A zero is a valid count, not a missing
  value.
- The response includes zero-count buckets for model choice values. Render
  returned keys and labels according to the frontend's display mapping; do not
  assume extra status or reason values beyond those returned by the backend.
- Load summary and statistics independently if the UI can display one while
  the other is still loading. Show a loading state while each request is
  pending and an error state if it fails.
- On `401`, follow the existing authentication refresh or sign-in flow. On
  `403`, show an access-denied state; retrying without changing the user's
  access will not grant permission.

## OpenAPI / Swagger

In a running backend, Swagger UI is available at `/api/docs/`. The generated
OpenAPI schema is available at `/api/schema/`. The project also serves Swagger
UI at the root path (`/`).

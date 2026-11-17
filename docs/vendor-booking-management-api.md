# Vendor booking management API

For the Pawdigree vendor frontend. Paths are relative to the API base URL.
Both endpoints require JWT authentication and a user with the `VENDOR` role.

## List my bookings

`GET /api/bookings/vendor/`

Returns all bookings for services whose business belongs to the authenticated
vendor. Bookings are ordered newest-created first, with higher `booking_id`
first when creation timestamps match. The listing includes every booking
status and is not paginated. A vendor cannot see another vendor's bookings.

Each result contains:

| Field | Description |
|---|---|
| `booking_id` | Booking identifier |
| `customer_id` | Customer account identifier |
| `customer_name` | Customer's full name, falling back to username |
| `service_name` | Booked service name |
| `start_at`, `end_at` | Booking start and end timestamps |
| `status` | `pending`, `accepted`, `declined`, `completed`, or `cancelled` |
| `notes` | Customer's booking notes |
| `decision_reason` | Reason recorded for the booking decision, if any |
| `created_at` | Booking creation timestamp |

Example response:

```json
[
  {
    "booking_id": 42,
    "customer_id": 7,
    "customer_name": "Jamie Customer",
    "service_name": "Dog grooming",
    "start_at": "2026-11-21T10:00:00Z",
    "end_at": "2026-11-21T11:00:00Z",
    "status": "pending",
    "notes": "Please call when you arrive.",
    "decision_reason": "",
    "created_at": "2026-11-16T10:00:00Z"
  }
]
```

Unauthenticated requests receive `401`; authenticated non-vendors receive
`403`.

## Update a booking status

`PATCH /api/bookings/vendor/<booking_id>/status/`

The booking must belong to a service business owned by the authenticated
vendor. A booking outside that scope returns `404`.

Allowed transitions:

| Current status | New status | Rule |
|---|---|---|
| `pending` | `accepted` | No reason required |
| `pending` | `declined` | A non-empty `decision_reason` is required; surrounding whitespace is trimmed |
| `accepted` | `completed` | Allowed when the current time is at or after `end_at` |

Declined, completed, and cancelled bookings are terminal for this endpoint.
Vendors cannot cancel bookings here. All other transitions return `400`.

Accept a booking:

```json
{
  "status": "accepted"
}
```

Decline a booking:

```json
{
  "status": "declined",
  "decision_reason": "The provider is unavailable at that time."
}
```

Complete an ended booking:

```json
{
  "status": "completed"
}
```

The `200` response uses the same booking fields as the list endpoint and
contains the updated status and decision reason. Invalid or unsupported
statuses, missing or blank decline reasons, disallowed transitions, and
attempts to complete before `end_at` return `400`. Unauthenticated requests
receive `401`; authenticated non-vendors receive `403`.

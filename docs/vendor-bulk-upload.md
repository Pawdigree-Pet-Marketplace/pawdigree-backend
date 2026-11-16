# Vendor bulk upload (CSV)

Vendors can create many listings at once from a CSV file instead of one at
a time. Pets, merchandise and services each have their own endpoint and
template.

| Listing | Upload (POST, vendor only) | Template (GET, public) |
| --- | --- | --- |
| Pets | `/api/pets/bulk-upload/` | `/api/pets/bulk-upload/template/` |
| Merchandise | `/api/products/bulk-upload/` | `/api/products/bulk-upload/template/` |
| Services | `/api/services/bulk-upload/` | `/api/services/bulk-upload/template/` |

## How it works

- Send the file as multipart form data in a field called `file`.
- The file must be a `.csv` saved as UTF-8 (Excel's "CSV UTF-8" is fine),
  under 5MB, with at most 200 rows.
- Row 1 is the header, so data starts at row 2 (matches the spreadsheet).
  Column names are case-insensitive. Blank cells are ignored and completely
  empty rows are skipped.
- Every row is validated with the same serializer as single create, so the
  rules are identical.
- Valid rows are created. Invalid rows are not, and are reported.
- Pets: `listing_type`, `gender` and `size` are case-insensitive. `age` is
  in months.
- A created listing is not public yet. It becomes visible to customers
  only after an admin approves it (see Business rules).
- The whole request runs in one database transaction.

## Response

Success is always HTTP 200, even if some rows failed:

    {
      "created": 2,
      "failed": [
        {"row": 3, "errors": {"price": ["A valid number is required."]}}
      ]
    }

A problem with the whole file is HTTP 400 with an error under `file`
(no file, wrong type, too big, not UTF-8, missing required column, no
rows, more than 200 rows).

## Columns

| Listing | Required | Optional |
| --- | --- | --- |
| Pets | `listing_type`, `name`, `species`, `age`, `gender`, `size` | `business_id`, `breed`, `description`, `price` (empty for adoption) |
| Merchandise | `category_id`, `name`, `price` | `business_id`, `description`, `stock_quantity` |
| Services | `category_id`, `name`, `service_type`, `description`, `price`, `duration` | `business_id`, `availability_status` |

`category_id` values come from `GET /api/categories/`. Merchandise requires an
active merchandise category; services require an active services category.

## Business rules (agreed with the team)

- A vendor registers, submits documents and is verified by an admin. Only
  a verified (approved, active) business can upload listings, one at a
  time or in bulk.
- An uploaded listing is not public. It becomes visible to customers only
  after an admin approves the listing.
- Merchandise needs a Pet Merchandise business and services need a Pet
  Services business.
- `business_id` can be left blank if the vendor has exactly one approved,
  active business of the right type. With two or more, it is required.
- A vendor can only use their own businesses.
- Services: a category the business has not used before is requested as
  pending, and the service stays hidden until the category is approved.

## Current status

- Pets: the verified-business and Pet Sale and Adoption checks are
  enforced (single and bulk). Admin approval of each listing is built.
- Services: the verified-business check is enforced (single and bulk)
  and admin approval of each listing is built. New and bulk-uploaded
  services start unapproved and are hidden until an admin approves
  them (the category must also be approved for the business). A
  vendor editing a service's name, type, description, category or
  image sends it back to review; changing price, duration or
  availability does not.
- Merchandise: the verified-business check is enforced and admin
  approval of each listing is built. New and bulk-uploaded products
  start unapproved and are hidden until an admin approves them. A
  vendor editing a product's name, description, category or images
  sends it back to review; changing price or stock does not.

Pets, merchandise and services now all need admin approval of each
listing before it is public.

## Not included yet

- `.xlsx` files and image upload (to decide with the team).
- Rate limiting on the upload endpoints.

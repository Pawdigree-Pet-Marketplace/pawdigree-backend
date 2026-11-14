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
| Pets | `listing_type`, `name`, `species`, `age`, `gender`, `size` | see the template |
| Merchandise | `category_id`, `name`, `price` | `business_id`, `description`, `stock_quantity` |
| Services | `category_id`, `name`, `service_type`, `description`, `price`, `duration` | `business_id`, `availability_status` |

`category_id` values come from `GET /api/categories/`. Merchandise accepts
merchandise or general categories; services accept services or general
categories.

## Business rules

- Merchandise and services: only approved, active businesses can add
  listings. Merchandise needs a Pet Merchandise business and services need
  a Pet Services business. (Pets do not enforce this yet.)
- `business_id` can be left blank if the vendor has exactly one approved,
  active business of the right type. With two or more, it is required.
- A vendor can only use their own businesses.
- Services: a category the business has not used before is requested as
  pending. Those services exist but stay hidden from customers until the
  category is approved.
- The same business rule now also applies to single `POST /api/services/`
  (approved, active, Pet Services business only).

## Not included yet

- `.xlsx` files and image upload (to decide with the team).
- Rate limiting on the upload endpoints.

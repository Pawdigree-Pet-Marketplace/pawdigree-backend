# Services listing API

For the Pawdigree customer and vendor frontends. Paths are relative to the API
base URL.

## Browse services

`GET /api/services/public/` is open to anonymous and authenticated customers.
It returns active services for active, approved businesses. A service's
category must be active, have kind `services` or `general`, and be approved
for its business. A pending or rejected business-category association is not
customer-visible.

The listing uses the service's `availability_status`. A service does not need
weekly availability slots to appear. The response does not expose vendor or
service-management fields.

### Query parameters

All filters can be combined.

| Parameter | Behavior |
|---|---|
| `search` | Case-insensitive match in service name or description |
| `category` | Active service/general category ID |
| `city_district` | Case-insensitive match in the business city or district |
| `min_price` | Minimum service price, including the boundary |
| `max_price` | Maximum service price, including the boundary |
| `page` | Page number, starting at 1 |
| `page_size` | Results per page; defaults to 12 and is capped at 50 |

Example:

`GET /api/services/public/?search=wash&category=4&city_district=kampala&min_price=10000&max_price=50000&page=1&page_size=12`

Malformed, unknown, inactive or wrong-kind category IDs, negative or malformed
prices, and a `min_price` greater than `max_price` return `400` with a
field-specific error.

### Response

The list uses the standard page-number response envelope:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "service_id": 12,
      "name": "Dog grooming",
      "service_type": "Grooming",
      "description": "Bath and trim",
      "price": "30000.00",
      "duration": 60,
      "availability_status": "available",
      "category_name": "Grooming",
      "business_name": "Happy Paws",
      "city_district": "Kampala",
      "image": "https://res.cloudinary.com/example/image/upload/services/grooming.png"
    }
  ]
}
```

`image` is the service image URL when one is set; otherwise it is the business
logo URL. It is `null` when neither exists, in which case the frontend should
show its default placeholder. URLs are absolute and come from the configured
Django default storage (Cloudinary when configured).

## Vendor service images

The existing vendor management routes remain in place:

| Method | Path | Purpose |
|---|---|---|
| `GET`, `POST` | `/api/services/` | List or create the authenticated vendor's services |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/services/{service_id}/` | View, edit, or deactivate one of the vendor's services |

Send service create and update requests as `multipart/form-data` when uploading
an image. Use the single `image` field. The same field is returned in the
vendor service response as a URL. To clear an existing image without replacing
it, send a JSON `PATCH` with `{"image": null}`. Otherwise, omit `image` when
the client has not selected a replacement.

Images must be JPEG, PNG, or WebP and no larger than 5 MB. The server validates
the file extension and image contents. Vendor ownership checks and existing
service activation behavior are unchanged.

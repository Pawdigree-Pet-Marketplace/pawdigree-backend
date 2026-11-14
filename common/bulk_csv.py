import csv
import io

from django.http import HttpResponse
from rest_framework import serializers

BULK_MAX_ROWS = 200
BULK_MAX_FILE_BYTES = 5 * 1024 * 1024


def read_bulk_csv(upload, columns, required_columns):
    """Validate an uploaded CSV and return [(row_number, data), ...].

    Whole-file problems raise a ValidationError on "file". Row 1 is the
    header, so data starts at row 2 (matches the spreadsheet). Blank cells
    are dropped and completely empty rows are skipped.
    """
    if upload is None:
        raise serializers.ValidationError({"file": "No file was uploaded."})
    if not upload.name.lower().endswith(".csv"):
        raise serializers.ValidationError({"file": "Please upload a .csv file."})
    if upload.size > BULK_MAX_FILE_BYTES:
        raise serializers.ValidationError({"file": "File must be under 5MB."})

    try:
        text = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise serializers.ValidationError(
            {"file": "File must be saved as UTF-8 CSV."}
        ) from None

    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [
        (name or "").strip().lower() for name in (reader.fieldnames or [])
    ]

    missing = [c for c in required_columns if c not in reader.fieldnames]
    if missing:
        raise serializers.ValidationError(
            {"file": f"Missing columns: {', '.join(missing)}."}
        )

    rows = list(reader)
    if not rows:
        raise serializers.ValidationError({"file": "The file has no rows."})
    if len(rows) > BULK_MAX_ROWS:
        raise serializers.ValidationError(
            {"file": f"At most {BULK_MAX_ROWS} rows per upload."}
        )

    parsed = []
    for row_number, row in enumerate(rows, start=2):
        data = {
            key: (value or "").strip()
            for key, value in row.items()
            if key in columns
        }
        data = {key: value for key, value in data.items() if value}
        if data:
            parsed.append((row_number, data))

    return parsed


def csv_template_response(columns, example_rows, filename):
    """Return a downloadable CSV with the header and example rows."""
    lines = [",".join(columns), *example_rows]
    response = HttpResponse("\n".join(lines) + "\n", content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

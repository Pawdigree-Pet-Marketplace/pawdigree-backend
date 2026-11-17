import os

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_image_upload(file):
    """Validate uploaded images by extension, size, and image content."""
    if file is None:
        return

    name = getattr(file, "name", "") or ""
    extension = os.path.splitext(name)[1].lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            "Unsupported file type. Please upload a JPEG, PNG, or WebP image."
        )

    if getattr(file, "size", 0) > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError("Image size must be 5 MB or smaller.")

    try:
        file.seek(0)
        image = Image.open(file)
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("Uploaded file is not a valid image.")
    finally:
        try:
            file.seek(0)
        except (AttributeError, OSError, ValueError):
            pass


MAX_DESCRIPTION_WORDS = 300
MAX_DESCRIPTION_CHARACTERS = 3000


def validate_description_length(value):
    """Limit listing descriptions to 300 words (and 3,000 characters).

    The character ceiling stops one enormous "word" getting past the
    word count. Empty values are left to the field's own required rule.
    """
    if not value:
        return

    words = len(value.split())
    if words > MAX_DESCRIPTION_WORDS:
        raise ValidationError(
            f"Description must be {MAX_DESCRIPTION_WORDS} words or fewer "
            f"(you wrote {words})."
        )

    if len(value) > MAX_DESCRIPTION_CHARACTERS:
        raise ValidationError(
            f"Description must be {MAX_DESCRIPTION_CHARACTERS:,} "
            "characters or fewer."
        )

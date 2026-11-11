from email.mime.image import MIMEImage
from pathlib import Path


EMAIL_IMAGE_ASSETS = {
    "pawdigree-header-wave": "header-wave-with-logo.png",
    "pawdigree-pawprints": "pawprints.png",
    "pawdigree-coral-underline": "coral-underline.png",
    "pawdigree-footer-paw": "footer-paw.png",
}
EMAIL_IMAGE_CIDS = tuple(EMAIL_IMAGE_ASSETS)


def attach_inline_email_images(message, content_ids):
    """Attach the requested shared PNG assets as related inline images."""
    message.mixed_subtype = "related"

    for content_id in content_ids:
        asset_name = EMAIL_IMAGE_ASSETS[content_id]
        asset_path = Path(__file__).parent / "email_assets" / asset_name
        image = MIMEImage(asset_path.read_bytes(), _subtype="png")
        image.add_header("Content-ID", f"<{content_id}>")
        image.add_header("Content-Disposition", "inline", filename=asset_name)
        message.attach(image)

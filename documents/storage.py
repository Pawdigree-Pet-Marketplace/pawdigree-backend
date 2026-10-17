from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateDocumentStorage(FileSystemStorage):
    """Store verification documents outside public media storage."""

    def __init__(self, *args, **kwargs):
        kwargs["location"] = settings.BASE_DIR / "private_documents"
        kwargs["base_url"] = None
        super().__init__(*args, **kwargs)

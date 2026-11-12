import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.emails import send_verification_email, send_welcome_email

User = get_user_model()

ASSETS_URL = "https://assets.test/email"
HEADER_URL = f"{ASSETS_URL}/header-wave-with-logo.png"
EXPECTED_IMAGES = {
    HEADER_URL,
    f"{ASSETS_URL}/pawprints.png",
    f"{ASSETS_URL}/coral-underline.png",
    f"{ASSETS_URL}/footer-paw.png",
}


@pytest.fixture(autouse=True)
def email_assets_url(settings):
    settings.EMAIL_ASSETS_URL = ASSETS_URL


def assert_remote_email_images(message):
    html_content = message.alternatives[0][0]
    header_image = re.search(
        rf'<img\b[^>]*\bsrc="{re.escape(HEADER_URL)}"[^>]*>',
        html_content,
        re.DOTALL,
    )
    assert header_image
    header_cells = list(
        re.finditer(r"<td\b[^>]*>", html_content[:header_image.start()])
    )
    assert header_cells
    header_cell_attributes = header_cells[-1].group()
    assert 'bgcolor="#216C68"' in header_cell_attributes
    assert re.search(
        r"background-color:\s*#216C68\b",
        header_cell_attributes,
    )

    assert 'alt="Pawdigree"' in header_image.group()
    assert 'width="600"' in header_image.group()
    assert 'height="143"' in header_image.group()
    assert "display: block" in header_image.group()
    assert "width: 100%" in header_image.group()
    assert "max-width: 600px" in header_image.group()
    assert "background-image: url(" not in html_content

    # Brevo rejects inline attachments, so nothing may be attached or cid:.
    assert "cid:" not in html_content
    assert message.attachments == []
    assert message.message().get_content_type() == "multipart/alternative"
    assert (
        set(re.findall(r'src="(https://assets\.test/[^"]+)"', html_content))
        == EXPECTED_IMAGES
    )


@pytest.mark.django_db
def test_welcome_email_uses_remote_images_and_keeps_plain_text(mailoutbox):
    user = User.objects.create_user(
        username="welcomeuser",
        email="welcome@example.com",
        password="SecurePass123!",
        role=User.Role.CUSTOMER,
    )

    assert send_welcome_email(user) is True

    message = mailoutbox[0]
    assert message.to == [user.email]
    assert "Welcome to the Pawdigree pet marketplace." in message.body
    assert_remote_email_images(message)


def test_verification_email_uses_remote_images_and_keeps_plain_text(mailoutbox):
    user = User(username="verifyuser", email="verify@example.com")

    assert send_verification_email(user, "123456", 10) is True

    message = mailoutbox[0]
    assert message.to == [user.email]
    assert "Hi verifyuser," in message.body
    assert "123456" in message.body
    assert "10 minutes" in message.body
    assert_remote_email_images(message)
    html_content = message.alternatives[0][0]
    assert (
        'background-color: #F3F0EA; border: 1px solid #FB8665; '
        'border-radius: 16px;'
    ) in html_content


@pytest.mark.django_db
def test_password_reset_email_uses_remote_images_and_keeps_reset_link(
    mailoutbox,
):
    user = User.objects.create_user(
        username="resetuser",
        email="reset@example.com",
        password="SecurePass123!",
        role=User.Role.CUSTOMER,
    )

    response = APIClient().post(
        reverse("password-reset-request"),
        {"email": user.email},
        format="json",
    )

    assert response.status_code == 200
    message = mailoutbox[0]
    assert message.to == [user.email]
    assert "/reset-password/?uid=" in message.body
    assert_remote_email_images(message)
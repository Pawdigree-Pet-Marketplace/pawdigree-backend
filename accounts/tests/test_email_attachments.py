import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.email_images import EMAIL_IMAGE_ASSETS
from accounts.emails import send_verification_email, send_welcome_email

User = get_user_model()

EXPECTED_CIDS = set(EMAIL_IMAGE_ASSETS)


def assert_inline_email_images(message):
    html_content = message.alternatives[0][0]
    header_image = re.search(
        r'<img\b[^>]*\bsrc="cid:pawdigree-header-wave"[^>]*>',
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
    assert 'background="cid:pawdigree-header-wave"' not in html_content
    assert "background-image: url(" not in html_content
    referenced_cids = set(
        re.findall(r"cid:([A-Za-z0-9-]+)", html_content)
    )
    attached_cids = {
        attachment["Content-ID"].strip("<>")
        for attachment in message.attachments
    }

    assert referenced_cids == EXPECTED_CIDS
    assert attached_cids == EXPECTED_CIDS
    assert all(
        attachment.get_content_type() == "image/png"
        for attachment in message.attachments
    )
    assert message.mixed_subtype == "related"
    mime_message = message.message()
    assert mime_message.get_content_type() == "multipart/related"
    assert {
        part["Content-ID"].strip("<>")
        for part in mime_message.walk()
        if part.get("Content-ID")
    } == EXPECTED_CIDS


@pytest.mark.django_db
def test_welcome_email_embeds_decorations_and_keeps_plain_text(mailoutbox):
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
    assert_inline_email_images(message)


def test_verification_email_embeds_decorations_and_keeps_plain_text(mailoutbox):
    user = User(username="verifyuser", email="verify@example.com")

    assert send_verification_email(user, "123456", 10) is True

    message = mailoutbox[0]
    assert message.to == [user.email]
    assert "Hi verifyuser," in message.body
    assert "123456" in message.body
    assert "10 minutes" in message.body
    assert_inline_email_images(message)
    html_content = message.alternatives[0][0]
    assert (
        'background-color: #F3F0EA; border: 1px solid #FB8665; '
        'border-radius: 16px;'
    ) in html_content


@pytest.mark.django_db
def test_password_reset_email_embeds_decorations_and_keeps_reset_link(
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
    assert_inline_email_images(message)

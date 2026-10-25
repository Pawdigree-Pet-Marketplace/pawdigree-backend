import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from html import unescape

from accounts.models import User


def test_password_reset_html_template_renders():
    """Test that the HTML password-reset email template renders correctly."""
    context = {
        'user': {
            'first_name': 'Test',
            'email': 'test@example.com',
        },
        'reset_url': 'http://localhost:5173/reset-password/?uid=1&token=test-token',
    }

    html_content = render_to_string(
        'accounts/emails/password_reset.html',
        context,
    )

    assert 'Pawdigree' in html_content
    assert context['reset_url']  in unescape(html_content)


def test_password_reset_text_template_renders():
    """Test that the plain-text password-reset email template renders correctly."""
    context = {
        'user': {
            'first_name': 'Test',
            'email': 'test@example.com',
        },
        'reset_url': 'http://localhost:5173/reset-password/?uid=1&token=test-token',
    }

    text_content = render_to_string(
        'accounts/emails/password_reset.txt',
        context,
    )

    assert context['reset_url'] in text_content


@pytest.mark.django_db
def test_password_reset_request_sends_html_email(mailoutbox, settings):
    """Test that requesting a password reset sends an email with HTML content."""
    # Arrange: create a user who can request a password reset.
    user = User.objects.create_user(
        username='resettestuser',
        email='resettest@example.com',
        password='SecurePass123',
        role=User.Role.CUSTOMER,
    )

    settings.FRONTEND_URL = 'http://localhost:5173'
    client = APIClient()

    # Act: request a password reset.
    response = client.post(
        reverse('password-reset-request'),
        {'email': user.email},
        format='json',
    )

    # Assert: the API responds successfully.
    assert response.status_code == status.HTTP_200_OK

    # Assert: one email was sent to the user.
    assert len(mailoutbox) == 1

    email = mailoutbox[0]

    assert email.subject == 'Reset your Pawdigree password'
    assert email.to == [user.email]

    # Check the plain-text version.
    assert '/reset-password/?uid=' in email.body

    # Check the HTML version was attached.
    assert len(email.alternatives) == 1

    html_content, content_type = email.alternatives[0]

    assert content_type == 'text/html'
    assert 'Pawdigree' in html_content
    assert '/reset-password/?uid=' in html_content
    assert 'src="cid:pawdigree-logo"' in html_content
    assert len(email.attachments) == 1
    logo = email.attachments[0]
    assert logo.get_content_type() == 'image/svg+xml'
    assert logo['Content-ID'] == '<pawdigree-logo>'
    assert logo['Content-Disposition'].startswith('inline')

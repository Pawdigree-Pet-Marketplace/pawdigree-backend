import pytest

from accounts.models import User


@pytest.mark.django_db
def test_new_users_are_not_verified_by_default():
    user = User.objects.create_user(
        username="fresh",
        email="fresh@example.com",
        password="SecurePass123",
    )

    assert user.is_email_verified is False

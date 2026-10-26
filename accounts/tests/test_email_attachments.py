from accounts.emails import send_verification_email
from accounts.models import User


def test_verification_email_has_no_attachments(mailoutbox):
    user = User(email='a@example.com')

    assert send_verification_email(user, '123456', 10) is True

    message = mailoutbox[0]
    assert message.attachments == []
    assert 'cid:' not in message.alternatives[0][0]
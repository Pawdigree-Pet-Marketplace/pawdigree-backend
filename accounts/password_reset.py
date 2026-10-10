from django.contrib.auth.tokens import PasswordResetTokenGenerator

class PasswordResetTokenGeneratorService:
    """
    Generates and validates password-reset tokens using Django's
    built-in token generator.
    """

    def __init__(self):
        self.generator = PasswordResetTokenGenerator()

    def generate_token(self, user):
        return self.generator.make_token(user)

    def validate_token(self, user, token):
        return self.generator.check_token(user, token)
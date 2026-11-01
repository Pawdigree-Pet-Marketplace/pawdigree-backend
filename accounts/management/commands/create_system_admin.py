import os
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from accounts.models import AdminAuditLog
from accounts.serializers import unique_username
from accounts.services import record_admin_action

User = get_user_model()


class Command(BaseCommand):
    help = 'Create the first SYSTEM_ADMIN account. Safe to run more than once.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--noinput',
            '--no-input',
            action='store_false',
            dest='interactive',
            help=(
                'Do not prompt. Read SYSTEM_ADMIN_EMAIL and '
                'SYSTEM_ADMIN_PASSWORD from the environment instead.'
            ),
        )

    def handle(self, *args, **options):
        # Checked first so a repeat run never prompts and never changes anything.
        existing = User.objects.filter(
            role=User.Role.SYSTEM_ADMIN,
            is_active=True,
        ).first()
        if existing:
            self.stdout.write(self.style.WARNING(
                f'A SYSTEM_ADMIN already exists ({existing.email}). '
                'Nothing was changed.'
            ))
            return

        if options['interactive']:
            email, password = self._prompt()
        else:
            email, password = self._from_environment()

        email = self._clean_email(email)
        self._check_password(password)

        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(
                'An account with this email already exists. '
                'Its role and password were not changed.'
            )

        with transaction.atomic():
            user = User.objects.create_user(
                username=unique_username(email),
                email=email,
                password=password,  # hashed by create_user
                role=User.Role.SYSTEM_ADMIN,
                is_active=True,
                is_staff=False,
                is_superuser=False,
                is_email_verified=True,
            )
            record_admin_action(
                actor=None,
                target=user,
                action=AdminAuditLog.Action.SYSTEM_ADMIN_CREATED,
            )

        self.stdout.write(self.style.SUCCESS(
            f'SYSTEM_ADMIN created: {user.email}'
        ))

    def _prompt(self):
        email = input('Email: ')
        password = getpass('Password: ')
        confirm = getpass('Password (again): ')
        if password != confirm:
            raise CommandError('Passwords do not match.')
        return email, password

    def _from_environment(self):
        email = os.environ.get('SYSTEM_ADMIN_EMAIL')
        password = os.environ.get('SYSTEM_ADMIN_PASSWORD')
        if not email or not password:
            raise CommandError(
                '--noinput needs SYSTEM_ADMIN_EMAIL and '
                'SYSTEM_ADMIN_PASSWORD to be set.'
            )
        return email, password

    def _clean_email(self, email):
        email = (email or '').strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError('Enter a valid email address.')
        return email

    def _check_password(self, password):
        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError(' '.join(error.messages))

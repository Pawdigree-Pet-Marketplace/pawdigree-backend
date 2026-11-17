from django.db import migrations, models


def backfill_user_status(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(is_active=True).update(status='active')
    User.objects.filter(is_active=False).update(status='deactivated')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_alter_user_managers_alter_user_email_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Active'),
                    ('deactivated', 'Deactivated'),
                    ('suspended', 'Suspended'),
                ],
                default='active',
                max_length=20,
            ),
        ),
        migrations.RunPython(
            backfill_user_status,
            migrations.RunPython.noop,
        ),
    ]

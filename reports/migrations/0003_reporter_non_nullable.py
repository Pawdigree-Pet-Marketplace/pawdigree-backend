import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def assert_no_null_reporters(apps, schema_editor):
    Report = apps.get_model("reports", "Report")
    null_count = Report.objects.filter(reporter_id__isnull=True).count()
    if null_count:
        raise Exception(
            f"Cannot enforce reporter non-nullability: {null_count} Report record(s) "
            "have reporter_id IS NULL. Review and resolve these records (reassign or "
            "remove them) before applying this migration."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0002_report_moderation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            assert_no_null_reporters,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="report",
            name="reporter",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reports_submitted",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

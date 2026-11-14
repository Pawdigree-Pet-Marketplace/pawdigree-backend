from django.db import migrations


def approve_existing_services(apps, schema_editor):
    Service = apps.get_model("services", "Service")
    Service.objects.filter(approved=False, rejection_reason="").update(approved=True)


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0006_service_approval_fields"),
    ]

    operations = [
        migrations.RunPython(approve_existing_services, migrations.RunPython.noop),
    ]

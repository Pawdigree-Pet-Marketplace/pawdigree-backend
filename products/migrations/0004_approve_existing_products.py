from django.db import migrations


def approve_existing_products(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Product.objects.filter(approved=False, rejection_reason="").update(approved=True)


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0003_product_approval_fields"),
    ]

    operations = [
        migrations.RunPython(approve_existing_products, migrations.RunPython.noop),
    ]

from django.db import migrations, models

ORDER_FORWARD = {"PENDING": "PENDING_PAYMENT", "COMPLETED": "PAID"}
VENDOR_ORDER_FORWARD = {"PENDING": "PENDING_PAYMENT", "COMPLETED": "DELIVERED"}

ORDER_BACKWARD = {
    "PENDING_PAYMENT": "PENDING",
    "PAID": "COMPLETED",
    "EXPIRED": "CANCELLED",
}
VENDOR_ORDER_BACKWARD = {
    "PENDING_PAYMENT": "PENDING",
    "PAID": "PENDING",
    "PROCESSING": "PENDING",
    "SHIPPED": "PENDING",
    "DELIVERED": "COMPLETED",
    "EXPIRED": "CANCELLED",
}


def _remap(apps, model_name, mapping):
    model = apps.get_model("orders", model_name)
    for old, new in mapping.items():
        model.objects.filter(status=old).update(status=new)


def forwards(apps, schema_editor):
    _remap(apps, "Order", ORDER_FORWARD)
    _remap(apps, "VendorOrder", VENDOR_ORDER_FORWARD)


def backwards(apps, schema_editor):
    _remap(apps, "Order", ORDER_BACKWARD)
    _remap(apps, "VendorOrder", VENDOR_ORDER_BACKWARD)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_orderitem_order_item_quantity_gte_1'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='expires_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_name',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_phone',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_address',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_city_district',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='order',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('PENDING_PAYMENT', 'Pending payment'), ('PAID', 'Paid'), ('CANCELLED', 'Cancelled'), ('EXPIRED', 'Expired')], default='PENDING_PAYMENT', max_length=20),
        ),
        migrations.AlterField(
            model_name='vendororder',
            name='status',
            field=models.CharField(choices=[('PENDING_PAYMENT', 'Pending payment'), ('PAID', 'Paid'), ('PROCESSING', 'Processing'), ('SHIPPED', 'Shipped'), ('DELIVERED', 'Delivered'), ('CANCELLED', 'Cancelled'), ('EXPIRED', 'Expired')], default='PENDING_PAYMENT', max_length=20),
        ),
        migrations.RunPython(forwards, backwards),
    ]

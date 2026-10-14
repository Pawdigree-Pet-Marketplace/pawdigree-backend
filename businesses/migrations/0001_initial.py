import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models

state_operations = [
    migrations.CreateModel(
        name='Business',
        fields=[
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('name', models.CharField(max_length=150)),
            ('description', models.TextField()),
            ('contact', models.CharField(max_length=30)),
            ('email', models.EmailField(max_length=254)),
            ('address', models.CharField(max_length=255)),
            ('city_district', models.CharField(max_length=100)),
            ('business_hours', models.JSONField(blank=True, default=dict)),
            ('verification_status', models.CharField(choices=[('draft', 'Draft'), ('pending', 'Pending'), ('changes_requested', 'Changes requested'), ('approved', 'Approved'), ('suspended', 'Suspended'), ('rejected', 'Rejected')], default='draft', max_length=20)),
            ('decision_reason', models.TextField(blank=True)),
            ('reviewed_at', models.DateTimeField(blank=True, null=True)),
            ('is_active', models.BooleanField(default=True)),
            ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owned_businesses', to=settings.AUTH_USER_MODEL)),
        ],
        options={
            'db_table': 'marketplace_business',
            'ordering': ('-created_at',),
        },
    ),
    migrations.CreateModel(
        name='BusinessCategory',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('approval_status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
            ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='business_categories', to='businesses.business')),
            ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='business_categories', to='categories.category')),
        ],
        options={
            'db_table': 'marketplace_businesscategory',
        },
    ),
    migrations.AddField(
        model_name='business',
        name='categories',
        field=models.ManyToManyField(related_name='businesses', through='businesses.BusinessCategory', to='categories.category'),
    ),
    migrations.CreateModel(
        name='BusinessImage',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('image', models.ImageField(upload_to='business_images/%Y/%m/')),
            ('alt_text', models.CharField(blank=True, max_length=150)),
            ('display_order', models.PositiveIntegerField(default=0)),
            ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='businesses.business')),
        ],
        options={
            'db_table': 'marketplace_businessimage',
            'ordering': ('display_order', 'created_at'),
        },
    ),
    migrations.AddConstraint(
        model_name='businesscategory',
        constraint=models.UniqueConstraint(fields=('business', 'category'), name='unique_business_category'),
    ),
    migrations.AddIndex(
        model_name='business',
        index=models.Index(fields=['verification_status'], name='marketplace_verific_763555_idx'),
    ),
    migrations.AddConstraint(
        model_name='business',
        constraint=models.UniqueConstraint(fields=('vendor', 'name'), name='unique_vendor_business_name'),
    ),
]


class Migration(migrations.Migration):
    """Adopt the existing marketplace_business* tables. No SQL runs."""

    initial = True

    dependencies = [
        ('categories', '0001_initial'),
        ('marketplace', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
        ),
    ]
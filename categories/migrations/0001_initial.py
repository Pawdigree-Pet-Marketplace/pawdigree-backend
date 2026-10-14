from django.db import migrations, models

state_operations = [
    migrations.CreateModel(
        name='Category',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('name', models.CharField(max_length=100, unique=True)),
            ('slug', models.SlugField(blank=True, max_length=120, unique=True)),
            ('description', models.TextField(blank=True)),
            ('is_active', models.BooleanField(default=True)),
        ],
        options={
            'db_table': 'marketplace_category',
            'ordering': ('name',),
        },
    ),
]


class Migration(migrations.Migration):
    """Adopt the existing marketplace_category table. No SQL runs."""

    initial = True

    dependencies = [
        ('marketplace', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
        ),
    ]
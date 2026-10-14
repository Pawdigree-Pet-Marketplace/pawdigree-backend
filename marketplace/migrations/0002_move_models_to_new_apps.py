from django.db import migrations


class Migration(migrations.Migration):
    """Release the models from marketplace state. No SQL runs.

    The tables now belong to categories and businesses.
    """

    dependencies = [
        ('marketplace', '0001_initial'),
        ('categories', '0001_initial'),
        ('businesses', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='business', name='categories'),
                migrations.DeleteModel(name='BusinessImage'),
                migrations.DeleteModel(name='BusinessCategory'),
                migrations.DeleteModel(name='Business'),
                migrations.DeleteModel(name='Category'),
            ],
        ),
    ]
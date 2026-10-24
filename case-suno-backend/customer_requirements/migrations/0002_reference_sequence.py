
from django.db import migrations


def create_reference_sequence(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        raise RuntimeError(
            "CASE SUNO reference IDs require PostgreSQL."
        )

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            CREATE SEQUENCE IF NOT EXISTS
            customer_requirements_reference_seq
            START WITH 1
        """)

        cursor.execute("""
            SELECT setval(
                'customer_requirements_reference_seq',
                COALESCE(
                    (
                        SELECT MAX(
                            substring(reference_id FROM '([0-9]+)$')::bigint
                        )
                        FROM customer_requirements_requirement
                    ),
                    0
                ) + 1,
                false
            )
        """)


class Migration(migrations.Migration):
    dependencies = [
        ("customer_requirements", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_reference_sequence,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

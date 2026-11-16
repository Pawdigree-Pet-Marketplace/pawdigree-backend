from django.db import migrations, models


SUPPORTED_KINDS = ("pets", "merchandise", "services")
BUSINESS_TYPE_TO_KIND = {
    "PET_SALE_ADOPTION": "pets",
    "PRODUCT_SELLER": "merchandise",
    "SERVICE_PROVIDER": "services",
}


def reclassify_general_categories(apps, schema_editor):
    """Reclassify GENERAL categories only when references prove one kind.

    No rows are updated until every GENERAL category has one unambiguous
    mapping. Unreferenced or conflicting categories stop the migration with
    IDs and names so an operator can resolve them explicitly first.
    """
    alias = schema_editor.connection.alias
    Category = apps.get_model("categories", "Category")
    BusinessCategory = apps.get_model("businesses", "BusinessCategory")
    Product = apps.get_model("products", "Product")
    Service = apps.get_model("services", "Service")

    unsupported = list(
        Category.objects.using(alias)
        .exclude(kind__in=(*SUPPORTED_KINDS, "general"))
        .values_list("id", "name", "kind")
    )
    if unsupported:
        details = "; ".join(
            f"id={pk} name={name!r} kind={kind!r}"
            for pk, name, kind in unsupported
        )
        raise RuntimeError(
            "Cannot remove GENERAL category kind while unsupported category "
            f"values exist: {details}. Resolve them explicitly first."
        )

    plans = []
    unresolved = []
    categories = Category.objects.using(alias).filter(kind="general").order_by("id")
    for category in categories.iterator():
        candidates = set()
        reasons = []

        business_links = (
            BusinessCategory.objects.using(alias)
            .filter(category_id=category.pk)
            .select_related("business")
        )
        for link in business_links.iterator():
            business_type = link.business.business_type
            kind = BUSINESS_TYPE_TO_KIND.get(business_type)
            if kind is None:
                reasons.append(
                    f"business {link.business_id} has unsupported or missing "
                    f"business_type {business_type!r}"
                )
            else:
                candidates.add(kind)

        if Product.objects.using(alias).filter(category_id=category.pk).exists():
            candidates.add("merchandise")
        if Service.objects.using(alias).filter(category_id=category.pk).exists():
            candidates.add("services")

        if len(candidates) != 1 or reasons:
            if not candidates and not reasons:
                reasons.append("the category is unreferenced")
            elif len(candidates) > 1:
                reasons.append(
                    "references imply conflicting kinds: "
                    + ", ".join(sorted(candidates))
                )
            unresolved.append(
                f"id={category.pk} name={category.name!r}: "
                + "; ".join(reasons)
            )
        else:
            plans.append((category.pk, next(iter(candidates))))

    if unresolved:
        raise RuntimeError(
            "Cannot safely remove GENERAL category kind. No categories were "
            "changed. Explicitly map these categories before retrying: "
            + " | ".join(unresolved)
        )

    for category_id, kind in plans:
        Category.objects.using(alias).filter(pk=category_id).update(kind=kind)


class Migration(migrations.Migration):
    dependencies = [
        ("categories", "0002_category_kind"),
        ("businesses", "0008_alter_business_business_type"),
        ("products", "0004_approve_existing_products"),
        ("services", "0007_approve_existing_services"),
    ]

    operations = [
        migrations.RunPython(
            reclassify_general_categories,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="category",
            name="kind",
            field=models.CharField(
                choices=[
                    ("pets", "Pets"),
                    ("merchandise", "Merchandise"),
                    ("services", "Services"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    kind__in=("pets", "merchandise", "services")
                ),
                name="category_kind_is_supported",
            ),
        ),
    ]

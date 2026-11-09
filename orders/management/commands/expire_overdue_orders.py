from django.core.management.base import BaseCommand

from orders.services import expire_overdue_orders


class Command(BaseCommand):
    help = (
        "Expire unpaid orders whose payment window has run out "
        "and give their stock back."
    )

    def handle(self, *args, **options):
        expired = expire_overdue_orders()
        self.stdout.write(self.style.SUCCESS(f"Expired {expired} overdue order(s)."))

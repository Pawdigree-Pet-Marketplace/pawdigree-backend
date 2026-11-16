from django.core.management.base import BaseCommand, CommandError

from payments.gateways import GatewayError
from payments.gateways.pesapal import PesapalGateway


class Command(BaseCommand):
    help = "Register the webhook URL with Pesapal and print the IPN id."

    def add_arguments(self, parser):
        parser.add_argument("url")

    def handle(self, *args, **options):
        try:
            ipn_id = PesapalGateway().register_ipn(options["url"])
        except GatewayError as exc:
            raise CommandError(str(exc)) from exc

        if not ipn_id:
            raise CommandError("Pesapal did not return an IPN id.")

        self.stdout.write(f"IPN id: {ipn_id}")
        self.stdout.write("Put this value in PESAPAL_IPN_ID and restart the server.")
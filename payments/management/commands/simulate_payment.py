import json

from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

from payments.gateways.sandbox import SandboxGateway
from payments.models import Payment


class Command(BaseCommand):
    help = "Send a signed fake webhook to the sandbox, as the gateway would."

    def add_arguments(self, parser):
        parser.add_argument("reference")
        parser.add_argument("--fail", action="store_true")

    def handle(self, *args, **options):
        payment = Payment.objects.filter(gateway_reference=options["reference"]).first()
        if payment is None:
            raise CommandError("No payment with that reference.")

        failed = options["fail"]
        body = json.dumps(
            {
                "reference": payment.gateway_reference,
                "transaction_id": payment.gateway_transaction_id,
                "status": "failed" if failed else "success",
                "amount": str(payment.amount),
                "currency": payment.currency,
                "reason": "Insufficient funds" if failed else "",
            }
        )
        response = Client(SERVER_NAME="localhost").post(
            reverse("payment-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE=SandboxGateway.sign(body.encode()),
        )
        self.stdout.write(f"Webhook answered with status {response.status_code}")
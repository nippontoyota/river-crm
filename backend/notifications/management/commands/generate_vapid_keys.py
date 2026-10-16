from base64 import urlsafe_b64encode

from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand
from py_vapid import Vapid


def encode(value):
    return urlsafe_b64encode(value).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Generate a Web Push VAPID key pair without saving it to the database."

    def handle(self, *args, **options):
        vapid = Vapid()
        vapid.generate_keys()
        private_key = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
        public_key = vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        self.stdout.write(f"WEB_PUSH_VAPID_PUBLIC_KEY={encode(public_key)}")
        self.stdout.write(f"WEB_PUSH_VAPID_PRIVATE_KEY={encode(private_key)}")
        self.stdout.write("WEB_PUSH_VAPID_SUBJECT=mailto:replace-with-admin-email@example.com")

from django.core.management.base import BaseCommand

from apps.core.catalog_loader import CatalogBootstrapService


class Command(BaseCommand):
    help = "Load the real DealSphere CSV datasets into Django models."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reload even if products already exist.",
        )

    def handle(self, *args, **options):
        summary = CatalogBootstrapService.ensure_loaded(force=options["force"])
        self.stdout.write(self.style.SUCCESS(f"Catalog load complete: {summary}"))

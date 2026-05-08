from django.core.management.base import BaseCommand

from academy.services import seed_database


class Command(BaseCommand):
    help = "Seed the SkillForge database with starter catalog and platform data."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Reapply seed defaults where appropriate.")

    def handle(self, *args, **options):
        seed_database(force=options["force"])
        self.stdout.write(self.style.SUCCESS("SkillForge seed data loaded."))

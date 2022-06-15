import os
import shutil
from django.core.management.base import BaseCommand, CommandError
from registration.models import User
from django.conf import settings


class Command(BaseCommand):
    help = 'Generate zip file with on board data file of the given sme email'

    def add_arguments(self, parser):
        parser.add_argument('sme_email', nargs='+', type=str)

    def handle(self, *args, **options):
        # Creating zip file
        user_email = options["sme_email"][0]
        try:
            user_object = User.objects.get(email=user_email)
        except User.DoesNotExist:
            raise CommandError(f"User object does not exists for the given email id: {user_email}")

        if user_object.user_role != settings.SME['number_value']:
            raise CommandError(f"Given email id: {user_email} is not of a sme user")
        zip_file_path = f"{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/" \
                        f"{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/{settings.ON_BOARDING_DATA_ZIP_FILE_NAME}"
        if os.path.exists(f"{zip_file_path}.zip"):
            raise CommandError(f"Zip file already exists for the given user: {user_email}")
        file_path = f'{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/' \
                    f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
        onboard_path = f"{settings.MEDIA_ROOT}/{file_path}"
        shutil.make_archive(zip_file_path, 'zip', onboard_path)
        self.stdout.write(self.style.SUCCESS('Successfully generated zip file for user: "%s"' % user_email))

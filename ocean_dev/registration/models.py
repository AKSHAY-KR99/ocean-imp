import uuid
from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.conf import settings
from utils.model_utility import user_detail_base_path, user_created_send_email, user_detail_id_base_path, xero_file_path \
    , profile_image_path
from transaction_app.models import ContractModel

# user on board choices data
ON_BOARD_USER_CREATED = 1
ON_BOARD_PASSWORD_SET = 2
ON_BOARD_IN_PROGRESS = 3
ON_BOARD_USER_REVIEWED = 4
ON_BOARD_COMPLETED = 5
ON_BOARD_REJECTED = 6
ON_BOARD_STATUS_CHOICES = ((ON_BOARD_USER_CREATED, "USER_CREATED"), (ON_BOARD_PASSWORD_SET, "PASSWORD_SET"),
                           (ON_BOARD_USER_REVIEWED, "USER_REVIEWED"), (ON_BOARD_IN_PROGRESS, "IN_PROGRESS"),
                           (ON_BOARD_COMPLETED, "COMPLETED"), (ON_BOARD_REJECTED, "REJECTED"))

# login otp choices data
OTP_SENT_STRING = 1
OTP_VERIFIED_STRING = 2
LOGIN_OTP_STATUS_CHOICES = ((OTP_SENT_STRING, "OTP_SENT"), (OTP_VERIFIED_STRING, "OTP_VERIFIED"))


class UserDetailModel(models.Model):
    """
    Model class for UserDetailModel Table (entering the user - SME/Supplier details). Supplier will be having the fields
     from company_name to contact_email
    """
    user_detail_path = models.CharField(max_length=200, help_text="Base path for instance files", default='')
    company_name = models.CharField(max_length=200, blank=True, null=True)
    company_registered_address = models.TextField(blank=True, null=True)
    company_physical_address = models.TextField(max_length=200, blank=True, null=True)
    company_registration_id = models.CharField(max_length=200, blank=True, null=True)
    company_website = models.CharField(max_length=200, blank=True, null=True)
    company_telephone_number = models.CharField(max_length=200, blank=True, null=True)
    contact_person = models.CharField(max_length=100, blank=False, null=True)
    contact_person_designation = models.CharField(max_length=100, blank=False, null=True)
    contact_mobile_phone = models.CharField(max_length=200, blank=True, null=True)
    contact_email = models.EmailField(max_length=200, blank=True, null=True)
    additional_info = models.JSONField(null=True)
    no_full_time_employees = models.IntegerField(default=0, help_text="Number of full time employees", blank=True)
    last_fy_annual_revenue = models.DecimalField(max_digits=20, decimal_places=3,
                                                 help_text="Last FY years Annual Revenue", blank=True, null=True)
    total_debt_amounts = models.DecimalField(max_digits=20, decimal_places=3, blank=True, null=True,
                                             help_text="Total Amount of Debt on the Books")
    inventory_on_hand = models.DecimalField(max_digits=20, decimal_places=3, default=0, blank=True, null=True,
                                            help_text="Inventory on Hand (COGS approx)")
    current_balance_sheet = models.FileField(upload_to=user_detail_base_path, blank=True, null=True,
                                             help_text="Current balance sheet")
    last_year_account_statement = models.FileField(upload_to=user_detail_base_path, blank=True,
                                                   help_text="Last year account statement")
    last_year_profit_loss = models.FileField(upload_to=user_detail_base_path, blank=True, null=True,
                                             help_text="Last 12 months profit/loss")
    # Optional data
    last_years_annual_reports = models.FileField(upload_to=user_detail_base_path, blank=True,
                                                 help_text="Last years annual reports")
    ytd_management_accounts = models.FileField(upload_to=user_detail_base_path, blank=True,
                                               help_text="YTD management accounts")
    last_bank_statements = models.FileField(upload_to=user_detail_base_path, blank=True, null=True,
                                            help_text="Last 3 months Bank statements")
    directors_address_proof = models.FileField(upload_to=user_detail_base_path, blank=True,
                                               help_text="Directors Proof of address within 3 months")
    share_holding_corporate_structure = models.FileField(upload_to=user_detail_base_path, blank=True,
                                                         help_text="Shareholding / Corporate Structure")
    cap_table = models.FileField(upload_to=user_detail_base_path, blank=True, help_text="Cap table")
    # Sample - previous trade cycle
    trade_cycle_po = models.FileField(upload_to=user_detail_base_path, blank=True, help_text="PO")
    trade_cycle_invoice = models.FileField(upload_to=user_detail_base_path, blank=True, help_text="Invoice")
    trade_cycle_bl = models.FileField(upload_to=user_detail_base_path, blank=True, help_text="BL")
    trade_cycle_awb = models.FileField(upload_to=user_detail_base_path, blank=True, help_text="AWB")
    trade_cycle_packing_list = models.FileField(upload_to=user_detail_base_path, blank=True, help_text="Packing list")
    trade_cycle_sgs_report = models.FileField(upload_to=user_detail_base_path, blank=True, help_text="SGS report")
    date_created = models.DateField(null=True)
    date_modified = models.DateField(null=True)

    # Removed data
    # last_fy_gp = models.DecimalField(max_digits=20, decimal_places=3, default=0,
    #                                  help_text="Last FY years GP", blank=True)
    # last_fy_np = models.DecimalField(max_digits=20, decimal_places=3, default=0,
    #                                  help_text="Last FY years NP", blank=True)
    # last_bank_statements_desc = models.TextField(blank=True)
    # directors_address_proof_desc = models.TextField(blank=True)
    # share_holding_corporate_structure_desc = models.TextField(blank=True)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        date_value = timezone.now().date()
        if not self.id:
            self.date_created = date_value
        self.date_modified = date_value
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.company_name)


class UserContactDetails(models.Model):
    """
    MOdel class for user additional contact details
    """
    user_details = models.ForeignKey(UserDetailModel, on_delete=models.CASCADE, related_name="detail_id_contact")
    contact_person = models.CharField(max_length=100, blank=False, null=True)
    contact_person_designation = models.CharField(max_length=100, blank=False, null=True)
    contact_mobile_phone = models.CharField(max_length=200, blank=False, null=True)
    contact_email = models.EmailField(max_length=200, blank=False, null=True)

    def __str__(self):
        return self.contact_person


class UserDetailFilesModel(models.Model):
    """
    Model class for saving the directors id copy pe files from the UserDetailModel Table
    """
    detail = models.ForeignKey(UserDetailModel, on_delete=models.CASCADE, related_name="detail_id_files")
    detail_file_key = models.CharField(max_length=50, help_text="id type eg: Passport, Driving licence etc")
    detail_id_file = models.FileField(upload_to=user_detail_id_base_path)

    def __str__(self):
        return str(self.detail_id_file.url)


class CustomUserManager(BaseUserManager):
    """
    Class for customizing the User Model objects manager class
    """

    def create_superuser(self, email, password, **other_fields):

        other_fields.setdefault('is_staff', True)
        other_fields.setdefault('is_superuser', True)
        other_fields.setdefault('is_active', True)
        other_fields.setdefault('user_role', settings.ADMIN_ROLE_VALUE)

        return self.create_user(email, password, **other_fields)

    def create_user(self, email, password=None, **other_fields):

        if not email:
            raise ValueError('You must provide an email address')

        email = self.normalize_email(email)
        user = self.model(email=email, **other_fields)
        if password:
            user.set_password(password)
        user.save()
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """
    Model class for User Table
    """
    email = models.EmailField(unique=True, blank=False)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=50, blank=True, unique=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    on_board_status = models.PositiveSmallIntegerField(choices=ON_BOARD_STATUS_CHOICES, blank=True, null=True)
    is_user_onboard = models.BooleanField(default=False)
    slug_value = models.SlugField(blank=True, null=True, unique=True)
    user_role = models.PositiveSmallIntegerField(choices=settings.ROLE_CHOICES, blank=True, null=True)
    credit_limit = models.DecimalField(max_digits=20, decimal_places=3, default=0)
    currency_value = models.CharField(max_length=5, default="USD")
    on_boarding_details = models.ForeignKey(UserDetailModel, on_delete=models.SET_NULL, blank=True, null=True,
                                            related_name="company_details")
    approved_by = models.CharField(max_length=30, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    master_contract = models.OneToOneField(ContractModel, on_delete=models.SET_NULL, null=True,
                                           related_name="sme_master_contract")
    is_reset_password = models.BooleanField(default=False, blank=True, null=True)
    profile_image = models.ImageField(null=True, blank=True, upload_to=profile_image_path)
    date_created = models.DateField(auto_now_add=True)
    is_mail_send = models.BooleanField(default=False)
    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ['-id']

    def _get_unique_slug(self):
        slug = slugify(get_random_string(length=32))
        unique_slug = slug
        num = 1
        while User.objects.filter(slug_value=unique_slug).exists():
            unique_slug = '{}-{}'.format(slug, num)
            num += 1
        return unique_slug

    def save(self, *args, **kwargs):
        # Checking if model instance is created (new entry)
        if not self.slug_value:
            self.slug_value = self._get_unique_slug()
            # Check for user if created as superuser directly
            if self.is_superuser:
                self.on_board_status = ON_BOARD_COMPLETED
                self.is_user_onboard = True
            else:
                self.on_board_status = ON_BOARD_USER_CREATED
            # Checking if the user is an admin
            if self.user_role == settings.ADMIN_ROLE_VALUE:
                self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class LoginTrackerModel(models.Model):
    """
    Model class for Login Tracker Table (saves data regarding the user login sessions and otp status and value)
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_session_details")
    otp_value = models.IntegerField(default=777777)
    otp_status = models.PositiveSmallIntegerField(choices=LOGIN_OTP_STATUS_CHOICES, blank=True, null=True)
    otp_created_date = models.DateTimeField(default=timezone.now)
    session_id = models.UUIDField(default=uuid.uuid4, editable=False)

    def __str__(self):
        return str(self.otp_created_date)


class XeroAuthTokenModel(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_xero_tokens")
    access_token = models.CharField(max_length=5000)
    refresh_token = models.CharField(max_length=5000)
    date_created = models.DateField(null=True)
    date_modified = models.DateField(null=True)

    def save(self, *args, **kwargs):
        # """ On save, update timestamps """
        date_value = timezone.now().date()
        if not self.id:
            self.date_created = date_value
        self.date_modified = date_value
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.user)


class OnBoardEmailData(models.Model):
    email = models.EmailField(unique=True, blank=False)
    is_deleted = models.BooleanField(default=False)
    date_created = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.email


class SMEOnBoardReviewEmailData(models.Model):
    user_detail = models.ForeignKey(UserDetailModel, on_delete=models.CASCADE, related_name='sme_review_sending_mails')
    email = models.EmailField(blank=False, null=False)
    date_created = models.DateField(auto_now_add=True)

    def __str__(self):
        return str(self.user_detail)


def send_email_user_created_signal(instance, **kwargs):
    """
    Initiating sending mails when new user is created
    """
    if instance.on_board_status == ON_BOARD_USER_CREATED and instance.is_deleted is False and not instance.is_mail_send:

        user_created_send_email(subject=settings.USER_CREATED, model_instance=instance, recipient_email=instance.email)
        instance.is_mail_send = True
        instance.save()


post_save.connect(send_email_user_created_signal, sender=User)

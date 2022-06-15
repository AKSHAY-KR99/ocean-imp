from django.core.exceptions import ValidationError
from django.conf import settings


def validate_password(password):
    special_characters = "~\!@#=+<>$%^&*()_?{}:;'[]/`.,|- "
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        raise ValidationError(
            "This password must contain at least %(min_length)d characters.",
            code='password_too_short',
            params={'min_length': settings.MIN_PASSWORD_LENGTH},
        )
    if not any(char.isdigit() for char in password):
        raise ValidationError('Password must contain at least %(min_length)d digit.' %
                              {'min_length': settings.MIN_SPECIAL_CHARACTERS_LENGTH})
    if not any(char.isalpha() for char in password):
        raise ValidationError('Password must contain at least %(min_length)d letter.' %
                              {'min_length': settings.MIN_SPECIAL_CHARACTERS_LENGTH})
    if not any(char in special_characters for char in password):
        raise ValidationError('Password must contain at least %(min_length)d special character.' %
                              {'min_length': settings.MIN_SPECIAL_CHARACTERS_LENGTH})
    if not any(char.isupper() for char in password):
        raise ValidationError('Password must contain at least %(min_length)d uppercase letter.' %
                              {'min_length': settings.MIN_SPECIAL_CHARACTERS_LENGTH})

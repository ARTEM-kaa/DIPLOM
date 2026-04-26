from django.apps import AppConfig


class ConfigConfig(AppConfig):
    """Core project configuration app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "config"


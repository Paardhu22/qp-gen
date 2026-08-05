from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        # Registering the SQLite tuning hook here (rather than in settings)
        # keeps it out of the settings import cycle and guarantees it runs
        # exactly once per process. No-op on Postgres.
        from apps.common import db_pragmas

        db_pragmas.register()

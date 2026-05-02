from django.contrib import admin

from .models import ScheduleTemplate


@admin.register(ScheduleTemplate)
class ScheduleTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_default", "created_at", "updated_at")
    list_filter = ("is_default",)
    search_fields = ("name",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "rules":
            kwargs["help_text"] = (
                "Weekday mapping: key is weekday number (0=Mon ... 6=Sun), "
                "value is a list of duty_type_id. "
                'Example: {"0": [1, 2], "2": [3], "6": []}.'
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

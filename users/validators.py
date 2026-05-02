"""Shared validation helpers for user-facing fields (DRF serializers)."""

from __future__ import annotations

import re

from django.utils import timezone
from rest_framework import serializers

RU_PHONE_PATTERN = re.compile(r"^\+7\(\d{3}\)\d{3}-\d{2}-\d{2}$")


def validate_phone_number_field(value):
    """Russian mobile format +7(999)123-45-67. Empty / null allowed."""
    if value is None:
        return value
    s = str(value).strip()
    if not s:
        return ""
    if not RU_PHONE_PATTERN.match(s):
        raise serializers.ValidationError(
            "Phone must match format +7(999)123-45-67 (digits only in place of 9 and 1–67)."
        )
    return s


def validate_email_simple_field(value):
    """Minimal email shape: @ present and a dot after @."""
    if value is None:
        return value
    s = str(value).strip()
    if not s:
        return ""
    at = s.find("@")
    if at == -1:
        raise serializers.ValidationError('Email must contain "@".')
    if "." not in s[at + 1 :]:
        raise serializers.ValidationError(
            'Email must contain a dot (.) after "@".'
        )
    return s


def validate_date_not_before_today(value, *, label: str):
    """Reject calendar dates strictly before today (local timezone)."""
    if value is None:
        return value
    today = timezone.localdate()
    if value < today:
        raise serializers.ValidationError(f"{label} cannot be in the past.")
    return value

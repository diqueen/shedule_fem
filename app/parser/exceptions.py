"""Parser-specific exceptions."""
from __future__ import annotations


class ScheduleError(Exception):
    """Base class for all schedule source errors."""


class ScheduleSourceError(ScheduleError):
    """Network / HTTP problem while talking to the schedule website."""


class ScheduleStructureError(ScheduleError):
    """The website responded but its structure does not match expectations."""


class ScheduleNotFoundError(ScheduleError):
    """Requested group/month is not present on the website."""

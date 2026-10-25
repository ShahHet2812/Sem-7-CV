from enum import StrEnum


class VideoStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def active(cls) -> tuple[str, ...]:
        return (cls.QUEUED.value, cls.PROCESSING.value)


class ZoneType(StrEnum):
    GENERAL = "general"
    ENTRY = "entry"
    EXIT = "exit"
    RESTRICTED = "restricted"


class EventType(StrEnum):
    ZONE_ENTRY = "zone_entry"
    ZONE_EXIT = "zone_exit"
    RESTRICTED_ENTRY = "restricted_entry"
    OCCUPANCY_EXCEEDED = "occupancy_exceeded"
    PROCESSING_FAILURE = "processing_failure"

    @classmethod
    def zone_types(cls) -> tuple[str, ...]:
        return (
            cls.ZONE_ENTRY.value,
            cls.ZONE_EXIT.value,
            cls.RESTRICTED_ENTRY.value,
            cls.OCCUPANCY_EXCEEDED.value,
        )

    @classmethod
    def entry_types(cls) -> tuple[str, ...]:
        return (cls.ZONE_ENTRY.value, cls.RESTRICTED_ENTRY.value)


EVENT_SEVERITY: dict[str, str] = {
    EventType.ZONE_ENTRY: "info",
    EventType.ZONE_EXIT: "info",
    EventType.RESTRICTED_ENTRY: "critical",
    EventType.OCCUPANCY_EXCEEDED: "warning",
    EventType.PROCESSING_FAILURE: "critical",
}


class EventStatus(StrEnum):
    NEW = "new"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"

from __future__ import annotations


class ProjectCoreError(Exception):
    code = "project_core_error"

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(ProjectCoreError):
    code = "validation_error"


class NotFoundError(ProjectCoreError):
    code = "not_found"


class ConflictError(ProjectCoreError):
    code = "conflict"


class RevisionConflict(ConflictError):
    code = "revision_conflict"

    def __init__(self, expected_revision: int, current_revision: int) -> None:
        super().__init__(
            "Project revision does not match",
            expected_revision=expected_revision,
            current_revision=current_revision,
        )


class ArchivedProjectError(ConflictError):
    code = "project_archived"


class DatabaseIntegrityError(ProjectCoreError):
    code = "database_integrity_error"

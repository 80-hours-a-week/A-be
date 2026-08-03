"""User PDF → DocModel coordination (U1-owned capability, frozen PR0 contract).

U1 Ingestion owns the DocModel capability; this package is its backend-side seam.
Consumers (U11 evidence/sessions, U12 novelty) depend on the
``UserDocModelCoordinatorPort`` protocol in ``docsuri_shared.ports`` and receive the
concrete coordinator by injection (wiring). Import path is stable:
``backend.modules.user_docmodel`` re-exports the full public surface.
"""

from .coordinator import (
    EVIDENCE_PDF_DEGRADED_NOTICE,
    NOVELTY_PDF_DEGRADED_REASON,
    USER_DOCMODEL_MAX_BYTES,
    USER_DOCMODEL_MODULES,
    USER_DOCMODEL_PDF_CONTENT_TYPE,
    USER_DOCMODEL_VERSION,
    UserDocModelCoordinator,
    UserDocModelRef,
    build_default_user_docmodel_coordinator,
    object_key_for_upload,
    ref_from_attachment,
    user_docmodel_ref,
)

__all__ = [
    "EVIDENCE_PDF_DEGRADED_NOTICE",
    "NOVELTY_PDF_DEGRADED_REASON",
    "USER_DOCMODEL_MAX_BYTES",
    "USER_DOCMODEL_MODULES",
    "USER_DOCMODEL_PDF_CONTENT_TYPE",
    "USER_DOCMODEL_VERSION",
    "UserDocModelCoordinator",
    "UserDocModelRef",
    "build_default_user_docmodel_coordinator",
    "object_key_for_upload",
    "ref_from_attachment",
    "user_docmodel_ref",
]

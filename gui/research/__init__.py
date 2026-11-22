"""Research storage foundations for the desktop application."""

from .evidence import EvidenceStore
from .index import SearchIndex
from .journal import Journal
from .locks import LockError
from .locks import OperationLock
from .notes import NoteStore
from .paths import ResearchPathError
from .paths import default_app_data
from .paths import research_root
from .sources import SourceStore

__all__ = [
    "EvidenceStore",
    "Journal",
    "LockError",
    "NoteStore",
    "OperationLock",
    "ResearchPathError",
    "SearchIndex",
    "SourceStore",
    "default_app_data",
    "research_root",
]

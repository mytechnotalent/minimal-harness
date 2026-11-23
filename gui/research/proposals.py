"""Pending agent note proposals awaiting one user Save action."""

import time
from pathlib import Path

from .atomic import read_json
from .atomic import write_json_atomic
from .ids import new_id
from .ids import require_id

PROPOSAL_PREFIX = "pr"


class ProposalStore:
    """Store pending note proposals for one session."""

    def __init__(self, session_folder):
        """Prepare the proposal folder for a session.

        Parameters
        ----------
        session_folder : pathlib.Path or str
            Primary session folder.

        Returns
        -------
        None
            The proposal directory exists.
        """
        self.session_folder = Path(session_folder)
        self.root = self.session_folder / "research" / "proposals"
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, scope, origin, title, body_md, note_id=None):
        """Create a pending create or revision proposal.

        Parameters
        ----------
        scope : dict
            Session and thread scope.
        origin : dict
            Immutable origin snapshot.
        title : str
            Proposed title.
        body_md : str
            Proposed markdown body.
        note_id : str or None
            Existing note identifier for a revision proposal.

        Returns
        -------
        dict
            Pending proposal record.
        """
        record = _proposal(scope, origin, title, body_md, note_id)
        write_json_atomic(self._path(record["id"]), record)
        return record

    def list(self, status="pending"):
        """List proposals filtered by status.

        Parameters
        ----------
        status : str or None
            Status filter, or ``None`` for all.

        Returns
        -------
        list
            Proposal records, newest first.
        """
        records = [read_json(path) for path in self.root.glob("pr_*.json")]
        records = [item for item in records if _matches(item, status)]
        return sorted(
            records, key=lambda item: item.get("created", 0), reverse=True
        )

    def get(self, proposal_id):
        """Load one proposal.

        Parameters
        ----------
        proposal_id : str
            Proposal identifier.

        Returns
        -------
        dict
            Proposal record.
        """
        require_id(proposal_id, PROPOSAL_PREFIX)
        return read_json(self._path(proposal_id))

    def remove(self, proposal_id):
        """Delete one proposal after save or discard.

        Parameters
        ----------
        proposal_id : str
            Proposal identifier.

        Returns
        -------
        None
            The proposal file is removed.
        """
        require_id(proposal_id, PROPOSAL_PREFIX)
        self._path(proposal_id).unlink(missing_ok=True)

    def _path(self, proposal_id):
        """Return the file path for a proposal.

        Parameters
        ----------
        proposal_id : str
            Proposal identifier.

        Returns
        -------
        pathlib.Path
            Proposal JSON path.
        """
        return self.root / f"{proposal_id}.json"


def _proposal(scope, origin, title, body_md, note_id):
    """Build a pending proposal record.

    Parameters
    ----------
    scope : dict
        Session and thread scope.
    origin : dict
        Immutable origin snapshot.
    title : str
        Proposed title.
    body_md : str
        Proposed markdown body.
    note_id : str or None
        Existing note identifier.

    Returns
    -------
    dict
        Proposal record.
    """
    record = _proposal_ids(scope, origin, note_id)
    record.update(_proposal_text(title, body_md))
    return record


def _proposal_ids(scope, origin, note_id):
    """Build proposal identity and scope fields.

    Parameters
    ----------
    scope : dict
        Session and thread scope.
    origin : dict
        Immutable origin snapshot.
    note_id : str or None
        Existing note identifier.

    Returns
    -------
    dict
        Identity fields.
    """
    record = {"id": new_id(PROPOSAL_PREFIX), "note_id": note_id}
    record["kind"] = "revision" if note_id else "create"
    record.update({"scope": dict(scope), "origin": dict(origin)})
    record.update({"status": "pending", "created": time.time()})
    return record


def _proposal_text(title, body_md):
    """Build proposal text fields.

    Parameters
    ----------
    title : str
        Proposed title.
    body_md : str
        Proposed markdown body.

    Returns
    -------
    dict
        Text fields.
    """
    return {"title": title, "body_md": body_md}


def _matches(record, status):
    """Return whether a proposal matches a status filter.

    Parameters
    ----------
    record : dict
        Proposal record.
    status : str or None
        Status filter.

    Returns
    -------
    bool
        ``True`` when the proposal matches.
    """
    return status is None or record.get("status") == status

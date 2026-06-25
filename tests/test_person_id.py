"""Tests for stable biometric person_id assignment (ADR 0005).

The HTTP routes that emit/return person_id (admin approve, liveness webhook,
GET /identity) build their payloads from these two service helpers, so the
identity-key contract is covered here at the unit level. Route-level integration
needs Postgres (the models use JSONB) and lives in the integration suite.
"""

import uuid

import pytest

from app.services import face_service, person_service


# ── face_service.match_or_mint_person_id (pure clustering) ───────────────────

def test_mint_new_person_id_when_no_existing_people():
    pid, matched = face_service.match_or_mint_person_id([1.0, 0.0, 0.0], [])
    assert matched is False
    # A freshly minted key is a valid uuid4 string.
    assert uuid.UUID(pid).version == 4


def test_reuses_person_id_on_biometric_match():
    existing = [("person-A", [1.0, 0.0, 0.0])]
    pid, matched = face_service.match_or_mint_person_id([1.0, 0.0, 0.0], existing)
    assert matched is True
    assert pid == "person-A"


def test_mints_new_person_id_when_no_match():
    existing = [("person-A", [0.0, 1.0, 0.0])]  # orthogonal → distance 1.0
    pid, matched = face_service.match_or_mint_person_id([1.0, 0.0, 0.0], existing)
    assert matched is False
    assert pid != "person-A"


def test_picks_closest_person_among_several():
    existing = [
        ("person-A", [0.0, 1.0, 0.0]),   # far
        ("person-B", [0.99, 0.01, 0.0]),  # closest
        ("person-C", [0.0, 0.0, 1.0]),   # far
    ]
    pid, matched = face_service.match_or_mint_person_id([1.0, 0.0, 0.0], existing)
    assert matched is True
    assert pid == "person-B"


# ── person_service async helpers (fake session, no real DB) ──────────────────

class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    """Minimal stand-in for AsyncSession returning a canned result."""

    def __init__(self, result: _FakeResult):
        self._result = result

    async def execute(self, _stmt, _params=None):
        return self._result


class _Verification:
    def __init__(self, embedding, id="verif-1", user_id="user-1"):
        self.face_embedding = embedding
        self.id = id
        self.user_id = user_id


@pytest.mark.asyncio
async def test_assign_person_id_fails_closed_without_face():
    """No embedding extracted → no person_id (downstream must fail closed)."""
    db = _FakeSession(_FakeResult())
    v = _Verification(embedding=None)
    assert await person_service.assign_person_id(db, v) is None


@pytest.mark.asyncio
async def test_assign_person_id_reuses_users_own_key():
    """A user's own prior approved person_id wins before any clustering."""
    db = _FakeSession(_FakeResult(rows=[("person-A", [1.0, 0.0, 0.0])], scalar="person-OWN"))
    v = _Verification(embedding=[1.0, 0.0, 0.0])
    assert await person_service.assign_person_id(db, v) == "person-OWN"


@pytest.mark.asyncio
async def test_assign_person_id_reuses_existing_cluster():
    # scalar=None → user has no prior key of their own, so cluster matching runs.
    db = _FakeSession(_FakeResult(rows=[("person-A", [1.0, 0.0, 0.0])]))
    v = _Verification(embedding=[1.0, 0.0, 0.0])
    assert await person_service.assign_person_id(db, v) == "person-A"


@pytest.mark.asyncio
async def test_assign_person_id_mints_when_no_cluster():
    db = _FakeSession(_FakeResult(rows=[]))
    v = _Verification(embedding=[1.0, 0.0, 0.0])
    pid = await person_service.assign_person_id(db, v)
    assert pid is not None
    assert uuid.UUID(pid).version == 4


@pytest.mark.asyncio
async def test_resolve_person_id_returns_stored_key():
    db = _FakeSession(_FakeResult(scalar="person-Z"))
    assert await person_service.resolve_person_id(db, "user-1") == "person-Z"


@pytest.mark.asyncio
async def test_resolve_person_id_none_when_unknown():
    db = _FakeSession(_FakeResult(scalar=None))
    assert await person_service.resolve_person_id(db, "user-1") is None

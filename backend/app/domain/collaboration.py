"""Framework-neutral collaboration roles, resource types, and helpers."""

from __future__ import annotations

from enum import StrEnum


class CollaboratorRole(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    OWNER = "owner"


class InviteResourceType(StrEnum):
    PROJECT = "project"
    RESEARCH = "research"


ROLE_RANK: dict[CollaboratorRole, int] = {
    CollaboratorRole.VIEWER: 1,
    CollaboratorRole.EDITOR: 2,
    CollaboratorRole.OWNER: 3,
}


def role_satisfies(role: CollaboratorRole | None, minimum: CollaboratorRole) -> bool:
    if role is None:
        return False
    return ROLE_RANK[role] >= ROLE_RANK[minimum]


def higher_role(
    first: CollaboratorRole | None, second: CollaboratorRole | None
) -> CollaboratorRole | None:
    if first is None:
        return second
    if second is None:
        return first
    return first if ROLE_RANK[first] >= ROLE_RANK[second] else second

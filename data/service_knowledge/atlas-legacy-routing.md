# Atlas historical blue-green routing

Fictional archived procedure. Status: SUPERSEDED. Revision: routing-v1.
Superseded by routing-v3 on 2026-10-01. Historical applicability only.

The former blue-green release process deliberately changed the public Service
release selector after the entire replacement fleet passed validation. This was
an atomic fleet switch, not the present rolling-update workflow. Applying that
selector rule during a rolling update can reduce the eligible endpoint pool.

Do not use this archived procedure as current authorization to pin a release.
Retrieve the current Atlas API routing contract before recommending a change.
This document remains searchable to explain historical deployment records and
to test whether retrieval consumers notice status and applicability. A high lexical
match does not override the explicit superseded status.

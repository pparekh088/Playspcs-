"""Tests for audit trail read/write/diff/prune."""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playspec.audit import create_audit, save_audit, load_audit, list_audits, prune_audits
from playspec.schemas.audit_entry import AuditEntry, AuditResults, RunMode


@pytest.fixture
def audit_dir(tmp_path):
    d = tmp_path / "audits"
    d.mkdir()
    return d


class TestAuditCRUD:
    def test_save_and_load(self, audit_dir):
        entry = AuditEntry(
            run_id="ps-20260101-120000-abcd",
            mode=RunMode.REGRESSION,
            profile="pr-ci",
            suite="smoke",
            results=AuditResults(passed=10, failed=2, skipped=1),
            duration_seconds=45.3,
        )
        save_audit(entry, audit_dir)
        loaded = load_audit("ps-20260101-120000-abcd", audit_dir)
        assert loaded is not None
        assert loaded.run_id == "ps-20260101-120000-abcd"
        assert loaded.results.passed == 10
        assert loaded.results.failed == 2

    def test_load_missing(self, audit_dir):
        assert load_audit("nonexistent", audit_dir) is None

    def test_list_audits(self, audit_dir):
        for i in range(3):
            entry = AuditEntry(
                run_id=f"ps-20260101-12000{i}-abcd",
                mode=RunMode.REGRESSION,
            )
            save_audit(entry, audit_dir)
        entries = list_audits(audit_dir)
        assert len(entries) == 3

    def test_prune(self, audit_dir):
        old_entry = AuditEntry(
            run_id="ps-20240101-120000-old1",
            mode=RunMode.REGRESSION,
            timestamp=datetime.now(timezone.utc) - timedelta(days=100),
        )
        new_entry = AuditEntry(
            run_id="ps-20260315-120000-new1",
            mode=RunMode.REGRESSION,
            timestamp=datetime.now(timezone.utc),
        )
        save_audit(old_entry, audit_dir)
        save_audit(new_entry, audit_dir)

        deleted = prune_audits(90, audit_dir)
        assert deleted == 1
        remaining = list_audits(audit_dir)
        assert len(remaining) == 1
        assert remaining[0].run_id == "ps-20260315-120000-new1"

"""Tests for run ID generation."""

import re

from playspec.run_id import generate_run_id


class TestRunId:
    def test_format(self):
        rid = generate_run_id()
        assert rid.startswith("ps-")
        assert re.match(r"ps-\d{8}-\d{6}-[0-9a-f]{8}", rid)

    def test_uniqueness(self):
        ids = {generate_run_id() for _ in range(100)}
        assert len(ids) == 100

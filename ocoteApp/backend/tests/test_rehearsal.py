from unittest.mock import MagicMock, patch

import pytest

from tools.f1_local import controlled_upgrade, verify_existing_upgrade


def test_backup_failure_blocks_alembic(tmp_path):
    with (
        patch("tools.f1_local.snapshot", return_value={"tables": []}),
        patch("tools.f1_local.backup_and_restore", side_effect=RuntimeError("backup failed")),
        patch("tools.f1_local.alembic_upgrade") as upgrade,
        pytest.raises(RuntimeError, match="backup failed"),
    ):
        controlled_upgrade(MagicMock(), tmp_path, "unused")
    upgrade.assert_not_called()


def test_existing_backup_failure_blocks_noop_upgrade(tmp_path):
    admin = MagicMock()
    admin.execute.return_value.fetchall.return_value = [("20261124_0001",)]
    with (
        patch(
            "tools.f1_local.snapshot",
            return_value={
                "tables": ["alembic_version", "release_history"],
            },
        ),
        patch("tools.f1_local.backup_and_restore", side_effect=RuntimeError("backup failed")),
        patch("tools.f1_local.alembic_upgrade") as upgrade,
        pytest.raises(RuntimeError, match="backup failed"),
    ):
        verify_existing_upgrade(admin, tmp_path, "unused")
    upgrade.assert_not_called()


def test_existing_verification_detects_history_mutation(tmp_path):
    admin = MagicMock()
    admin.execute.return_value.fetchall.return_value = [("20261124_0001",)]
    baseline = {"tables": ["alembic_version", "release_history"], "rows": ["original"]}
    changed = baseline | {"rows": ["changed"]}
    with (
        patch("tools.f1_local.snapshot", side_effect=[baseline, changed]),
        patch("tools.f1_local.backup_and_restore"),
        patch("tools.f1_local.alembic_upgrade") as upgrade,
        pytest.raises(RuntimeError, match="historical release"),
    ):
        verify_existing_upgrade(admin, tmp_path, "unused")
    upgrade.assert_called_once()

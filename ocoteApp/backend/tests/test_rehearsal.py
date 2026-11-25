from unittest.mock import MagicMock, patch

import pytest

from tools.f1_local import controlled_upgrade


def test_backup_failure_blocks_alembic(tmp_path):
    with (
        patch("tools.f1_local.snapshot", return_value={"tables": []}),
        patch("tools.f1_local.backup_and_restore", side_effect=RuntimeError("backup failed")),
        patch("tools.f1_local.alembic_upgrade") as upgrade,
        pytest.raises(RuntimeError, match="backup failed"),
    ):
        controlled_upgrade(MagicMock(), tmp_path, "unused")
    upgrade.assert_not_called()

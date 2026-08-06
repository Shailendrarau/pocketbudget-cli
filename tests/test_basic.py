import subprocess
import sys


def test_entry_point_prints_startup_message_and_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pocketbudget"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Hello PocketBudget" in result.stdout
    assert result.stderr == ""

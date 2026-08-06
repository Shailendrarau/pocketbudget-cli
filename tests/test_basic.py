import subprocess
import sys


def test_entry_point_without_a_command_prints_usage_and_exits_non_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pocketbudget"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr

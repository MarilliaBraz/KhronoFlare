import pandas as pd
import pytest

from firms_harmonize.cli import _save_parquet_atomic, main


@pytest.mark.parametrize("cmd", ["risk-panel", "risk-drivers", "risk-train", "risk-explain", "risk-climatology"])
@pytest.mark.parametrize("opt", [["--res", "1.0"], ["--min-conf", "high"]])
def test_risk_commands_reject_options_they_would_ignore(cmd, opt):
    with pytest.raises(SystemExit) as e:
        main([cmd, *opt])
    assert e.value.code == 2                                  # erro de argumento do argparse


def test_save_parquet_atomic_writes_and_leaves_no_temporary(tmp_path):
    dest = tmp_path / "panel.parquet"
    _save_parquet_atomic(pd.DataFrame({"a": [1, 2]}), dest)
    assert pd.read_parquet(dest)["a"].tolist() == [1, 2]
    assert [p.name for p in tmp_path.iterdir()] == ["panel.parquet"]

from pathlib import Path

import pytest

from src.extract import metrika_offline
from src.pipeline import analyze
from src.simulate import campaign

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scenarios.yaml"


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("raw")
    campaign.run(CONFIG, out)
    metrika_offline.run(out / "visit_plan.csv", out / "metrika_visits.csv")
    return out


@pytest.fixture(scope="session")
def cfg() -> dict:
    return campaign.load_config(CONFIG)


@pytest.fixture(scope="session")
def truth(raw_dir) -> dict:
    import json

    return json.loads((raw_dir / "ground_truth.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def res(raw_dir, cfg, truth):
    return analyze(raw_dir, cfg, truth)


def missing_date(cfg: dict) -> str:
    """Дата, которую симулятор выкидывает из выгрузки Верификатора."""
    a = next(a for a in cfg["anomalies"] if a["type"] == "missing_date")
    return str(a["date"])

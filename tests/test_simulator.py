import pandas as pd

from src.simulate import campaign
from tests.conftest import CONFIG


def test_same_seed_same_files(raw_dir, tmp_path):
    campaign.run(CONFIG, tmp_path)
    for name in ["dsp_clicks.csv", "verifier_export.csv", "visit_plan.csv", "ground_truth.json"]:
        assert (raw_dir / name).read_bytes() == (tmp_path / name).read_bytes(), name


def test_verifier_total_row_matches_body(raw_dir):
    df = pd.read_csv(raw_dir / "verifier_export.csv", sep=";")
    total = df[df["Дата"] == "Итого"].iloc[0]
    body = df[df["Дата"] != "Итого"]
    for col in ["Кликов всего с учётом IVT", "GIVT", "SIVT", "Чистые клики"]:
        assert int(total[col]) == int(body[col].sum())


def test_ivt_parts_add_up(raw_dir):
    df = pd.read_csv(raw_dir / "verifier_export.csv", sep=";")
    body = df[df["Дата"] != "Итого"]
    assert (body["GIVT"] + body["SIVT"] + body["Чистые клики"] == body["Кликов всего с учётом IVT"]).all()


def test_verifier_never_exceeds_dsp(raw_dir):
    daily = campaign.simulate_daily(campaign.load_config(CONFIG))
    assert (daily["verifier_total"] <= daily["dsp_clicks"]).all()
    assert (daily["visits"] <= daily["clean_clicks"]).all()


def test_damage_is_present(raw_dir, truth):
    dsp = pd.read_csv(raw_dir / "dsp_clicks.csv")
    dup = next(a for a in truth["anomalies"] if a["type"] == "duplicates")
    assert dsp.duplicated().sum() == dup["rows"]

    verifier = pd.read_csv(raw_dir / "verifier_export.csv", sep=";")
    assert "08.09.2026" not in set(verifier["Дата"])

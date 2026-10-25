"""Пайплайн находит ровно то, что вшито в scenarios.yaml."""

import pandas as pd


def _anomaly(truth, kind):
    return [a for a in truth["anomalies"] if a["type"] == kind]


def test_reach_drop_found_exactly(res, truth):
    for a in _anomaly(truth, "reach_drop"):
        found = res.windows[(res.windows["kind"] == "reach") & (res.windows["slice"] == a["ssp"])]
        assert len(found) == 1
        assert found.iloc[0]["start"] == pd.Timestamp(a["start"])
        assert found.iloc[0]["end"] == pd.Timestamp(a["end"])


def test_givt_spike_found_exactly(res, truth):
    givt = res.windows[res.windows["kind"] == "givt"]
    expected = _anomaly(truth, "high_givt")
    assert len(givt) == len(expected)
    for a in expected:
        found = givt[givt["slice"] == a["placement"]]
        assert found.iloc[0]["start"] == pd.Timestamp(a["start"])
        assert found.iloc[0]["end"] == pd.Timestamp(a["end"])


def test_every_reach_window_is_explained(res, truth):
    """Провал доходимости — либо вшитый reach_drop, либо следствие роста GIVT на площадке этой SSP."""
    ssp_of = res.mart.drop_duplicates("placement").set_index("placement")["ssp"]
    givt = res.windows[res.windows["kind"] == "givt"]
    drops = {a["ssp"] for a in _anomaly(truth, "reach_drop")}
    for w in res.windows[res.windows["kind"] == "reach"].itertuples():
        overlaps_givt = (
            (givt["slice"].map(ssp_of) == w.slice) & (givt["start"] <= w.end) & (givt["end"] >= w.start)
        ).any()
        assert w.slice in drops or overlaps_givt, f"необъяснённый провал: {w.slice} {w.start:%d.%m}–{w.end:%d.%m}"


def test_goal_spike_found(res, truth):
    for a in _anomaly(truth, "goal_spike"):
        hit = res.goals_over[(res.goals_over["placement"] == a["placement"]) & (res.goals_over["goal"] == a["goal"])]
        assert len(hit) == 1
        assert hit.iloc[0]["date"] == pd.Timestamp(a["date"])


def test_no_false_goal_alerts(res, truth):
    assert len(res.goals_over) == len(_anomaly(truth, "goal_spike"))

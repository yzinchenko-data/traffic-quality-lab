import pytest

from src.clean.loaders import normalize_utm


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ssp_a", "ssp_a"),
        ("SSP_A", "ssp_a"),
        ("ssp_a ", "ssp_a"),
        ("ssp-a", "ssp_a"),
        ("ssp_a?ref=feed", "ssp_a"),
        ("  Ssp-A?x=1 ", "ssp_a"),
    ],
)
def test_normalize_utm(raw, expected):
    assert normalize_utm(raw) == expected


def test_cleaning_report(res):
    report = res.cleaning.to_frame().set_index("issue")
    assert report.loc["полные дубли строк", "rows"] == 6
    assert report.loc["пропущенные даты", "detail"] == "2026-09-08"
    assert report.loc["UTM-метки в разном написании", "rows"] > 0
    # Сверка с «Итого» прошла: строк о расхождении нет
    assert not report.index.str.startswith("расхождение").any()


def test_mart_has_only_known_ssps(res, cfg):
    assert set(res.mart["ssp"]) == set(cfg["ssps"])
    assert not res.mart.duplicated(["date", "ssp", "placement"]).any()

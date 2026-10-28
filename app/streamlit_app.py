"""Интерактивное демо: двигаешь порог robust z и силу вшитых аномалий, смотришь, что найдёт пайплайн.

Запуск:
  pip install -r requirements.txt streamlit
  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analysis import timeseries  # noqa: E402
from src.extract import metrika_offline  # noqa: E402
from src.pipeline import analyze  # noqa: E402
from src.simulate import campaign  # noqa: E402

st.set_page_config(page_title="Traffic Quality Lab", layout="wide")


@st.cache_data(show_spinner="Симулирую кампанию…")
def simulate(cfg_yaml: str):
    cfg = yaml.safe_load(cfg_yaml)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "scenarios.yaml").write_text(cfg_yaml, encoding="utf-8")
        campaign.run(tmp / "scenarios.yaml", tmp)
        metrika_offline.run(tmp / "visit_plan.csv", tmp / "metrika_visits.csv")
        truth = json.loads((tmp / "ground_truth.json").read_text(encoding="utf-8"))
        res = analyze(tmp, cfg, truth)
    return res.daily_ssp, res.daily_placement, res.summary


base = campaign.load_config(ROOT / "scenarios.yaml")
anomaly = {a["id"]: a for a in base["anomalies"]}

st.title("Traffic Quality Lab")
st.caption("Синтетическая кампания DSP → Верификатор → Метрика. Все данные сгенерированы.")

with st.sidebar:
    st.header("Сценарий")
    reach_factor = st.slider("Провал доходимости ssp_b, доля от нормы", 0.1, 1.0, float(anomaly["reach_drop_ssp_b"]["factor"]), 0.05)
    givt_rate = st.slider("GIVT на mobile_feed в аномальные дни", 0.02, 0.5, float(anomaly["high_givt_mobile_feed"]["givt_rate"]), 0.01)
    seed = st.number_input("seed", value=int(base["seed"]), step=1)
    st.header("Детектор")
    threshold = st.slider("Порог robust z", 1.5, 6.0, timeseries.Z_THRESHOLD, 0.25)

cfg = copy.deepcopy(base)
cfg["seed"] = int(seed)
for a in cfg["anomalies"]:
    if a["id"] == "reach_drop_ssp_b":
        a["factor"] = reach_factor
    if a["id"] == "high_givt_mobile_feed":
        a["givt_rate"] = givt_rate

daily_ssp, daily_placement, summary = simulate(yaml.safe_dump(cfg, allow_unicode=True))
reach = timeseries.detect(daily_ssp, "ssp", "reach_verifier", "low", threshold)
givt = timeseries.detect(daily_placement, "placement", "givt_share", "high", threshold)
win = pd.concat(
    [
        timeseries.windows(reach, "ssp").rename(columns={"ssp": "slice"}).assign(kind="доходимость"),
        timeseries.windows(givt, "placement").rename(columns={"placement": "slice"}).assign(kind="GIVT"),
    ],
    ignore_index=True,
)

c1, c2, c3 = st.columns(3)
c1.metric("Периодов с аномалиями", len(win))
c2.metric("Дней с флагом доходимости", int(reach["flag"].sum()))
c3.metric("Дней с флагом GIVT", int(givt["flag"].sum()))

st.subheader("Доходимость от Верификатора по SSP")
st.line_chart(reach.pivot(index="date", columns="ssp", values="reach_verifier"))
st.subheader("Доля GIVT по площадкам")
st.line_chart(givt.pivot(index="date", columns="placement", values="givt_share"))

st.subheader("Найденные периоды")
st.dataframe(win[["kind", "slice", "start", "end", "days"]], hide_index=True, use_container_width=True)
st.subheader("Сводка за период")
st.dataframe(summary, hide_index=True, use_container_width=True)

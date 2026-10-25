"""Бот-посетитель: проигрывает visit_plan.csv на настоящем сайте через Playwright.

Каждый визит открывает сайт с UTM-метками из плана и ведёт себя по профилю:
  bounce  — открыл и ушёл
  browse  — прокрутил главную, открыл карточку товара
  cart    — положил товар в корзину (цель add_to_cart)
  lead    — оформил заявку (цель form_submit)
Если в плане целей больше, чем визитов (вшитая аномалия), лишние form_submit
отправляются повторно в тех же визитах — так выглядит двойное срабатывание тега.

Запуск (масштаб 5% от плана, одна дата):
  python -m src.simulate.visitor --site https://<user>.github.io/traffic-quality-lab/ --date 2026-09-12 --scale 0.05
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import pandas as pd

if TYPE_CHECKING:
    from playwright.sync_api import Page

UTM_COLS = ["utm_source", "utm_medium", "utm_campaign", "utm_content"]


@dataclass
class Visit:
    utm: dict
    profile: str
    extra_forms: int = 0


def plan_visits(plan: pd.DataFrame, scale: float, rng: random.Random) -> list[Visit]:
    visits: list[Visit] = []
    for row in plan.itertuples(index=False):
        n = round(row.visits * scale)
        if n == 0:
            continue
        leads = min(round(row.form_submit * scale), n)
        carts = min(round(row.add_to_cart * scale), n - leads)
        extra = max(round(row.form_submit * scale) - n, 0)
        rest = n - leads - carts
        bounces = round(rest * 0.25)
        profiles = ["lead"] * leads + ["cart"] * carts + ["bounce"] * bounces + ["browse"] * (rest - bounces)
        utm = {c: getattr(row, c) for c in UTM_COLS}
        for i, p in enumerate(profiles):
            visits.append(Visit(utm, p, extra_forms=extra if (p == "lead" and i == 0) else 0))
    rng.shuffle(visits)
    return visits


def _pause(rng: random.Random, low: float = 0.6, high: float = 2.0) -> None:
    time.sleep(rng.uniform(low, high))


def play(page: Page, site: str, visit: Visit, rng: random.Random) -> None:
    page.goto(f"{site.rstrip('/')}/index.html?{urlencode(visit.utm)}", wait_until="load")
    _pause(rng, 1.5, 3.5)  # Метрике нужно время, чтобы засчитать визит
    if visit.profile == "bounce":
        return

    page.mouse.wheel(0, rng.randint(900, 2200))
    _pause(rng)
    page.locator("[data-catalog] .card-title").nth(rng.randint(0, 5)).click()
    _pause(rng)

    if visit.profile in ("cart", "lead"):
        page.locator("[data-add]").first.click()
        _pause(rng)

    if visit.profile == "lead":
        page.goto(f"{site.rstrip('/')}/contact.html", wait_until="load")
        for _ in range(1 + visit.extra_forms):
            page.fill("#name", "Тестовый посетитель")
            page.fill("#contact", "bot@example.test")
            page.click("[data-lead-form] button")
            _pause(rng, 0.3, 0.8)
    _pause(rng, 1.0, 2.5)


def run(site: str, plan_path: str, date: str, scale: float, seed: int, headless: bool) -> int:
    plan = pd.read_csv(plan_path)
    plan = plan[plan["date"] == date]
    rng = random.Random(f"{seed}-{date}")
    visits = plan_visits(plan, scale, rng)
    from playwright.sync_api import sync_playwright  # тяжёлая зависимость нужна только здесь

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        for i, visit in enumerate(visits, 1):
            # Новый контекст = новый посетитель: чистые cookies и localStorage
            ctx = browser.new_context(locale="ru-RU", viewport={"width": rng.choice([390, 1280, 1440]), "height": 860})
            page = ctx.new_page()
            try:
                play(page, site, visit, rng)
            except Exception as exc:  # один упавший визит не должен ронять весь прогон
                print(f"[{i}/{len(visits)}] {visit.profile}: {exc}")
            finally:
                ctx.close()
        browser.close()
    return len(visits)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", required=True)
    parser.add_argument("--plan", default="data/raw/visit_plan.csv")
    parser.add_argument("--date", required=True, help="дата из плана, YYYY-MM-DD")
    parser.add_argument("--scale", type=float, default=0.05, help="доля визитов плана, которую проигрываем")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    n = run(args.site, args.plan, args.date, args.scale, args.seed, headless=not args.headed)
    print(f"Сыграно визитов: {n}")


if __name__ == "__main__":
    main()

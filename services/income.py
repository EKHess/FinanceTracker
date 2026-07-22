from database import get_connection

PERIODS_PER_YEAR = {
    "day": 365,
    "week": 52,
    "month": 12,
    "year": 1,
}

CANADA_PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "ON": "Ontario",
    "PE": "Prince Edward Island", "QC": "Quebec", "SK": "Saskatchewan",
}

DEFAULT_TAX_RULESETS = {
    ("Canada", "Federal", "FED", 2026): [(0, 58523, 14), (58523, 117045, 20.5), (117045, 181440, 26), (181440, 258482, 29), (258482, None, 33)],
    ("Canada", "Alberta", "AB", 2026): [(0, 61200, 8), (61200, 154259, 10), (154259, 185111, 12), (185111, 246813, 13), (246813, 370220, 14), (370220, None, 15)],
    ("Canada", "British Columbia", "BC", 2026): [(0, 50363, 5.6), (50363, 100728, 7.7), (100728, 115648, 10.5), (115648, 140430, 12.29), (140430, 190405, 14.7), (190405, 265545, 16.8), (265545, None, 20.5)],
    ("Canada", "Manitoba", "MB", 2026): [(0, 47564, 10.8), (47564, 101200, 12.75), (101200, None, 17.4)],
    ("Canada", "New Brunswick", "NB", 2026): [(0, 52333, 9.4), (52333, 104666, 14), (104666, 193861, 16), (193861, None, 19.5)],
    ("Canada", "Newfoundland and Labrador", "NL", 2026): [(0, 44678, 8.7), (44678, 89354, 14.5), (89354, 159528, 15.8), (159528, 223340, 17.8), (223340, 285319, 19.8), (285319, 570638, 20.8), (570638, 1141275, 21.3), (1141275, None, 21.8)],
    ("Canada", "Nova Scotia", "NS", 2026): [(0, 30995, 8.79), (30995, 61991, 14.95), (61991, 97417, 16.67), (97417, 157124, 17.5), (157124, None, 21)],
    ("Canada", "Ontario", "ON", 2026): [(0, 53891, 5.05), (53891, 107785, 9.15), (107785, 150000, 11.16), (150000, 220000, 12.16), (220000, None, 13.16)],
    ("Canada", "Prince Edward Island", "PE", 2026): [(0, 33928, 9.5), (33928, 65820, 13.47), (65820, 106890, 16.6), (106890, 142520, 17.62), (142520, 200000, 19), (200000, None, 20)],
    ("Canada", "Quebec", "QC", 2026): [(0, 54345, 14), (54345, 108680, 19), (108680, 132245, 24), (132245, None, 25.75)],
    ("Canada", "Saskatchewan", "SK", 2026): [(0, 54532, 10.5), (54532, 155805, 12.5), (155805, None, 14.5)],
}


def seed_default_tax_rules():
    conn = get_connection()
    for (country, region_name, region_code, year), brackets in DEFAULT_TAX_RULESETS.items():
        exists = conn.execute(
            "SELECT 1 FROM tax_rulesets WHERE country=? AND region_code=? AND tax_year=?",
            (country, region_code, year),
        ).fetchone()
        if exists:
            continue
        cursor = conn.execute(
            "INSERT INTO tax_rulesets(country, region_name, region_code, tax_year, source_url) VALUES(?,?,?,?,?)",
            (country, region_name, region_code, year, "https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/current-year.html"),
        )
        ruleset_id = cursor.lastrowid
        for lower, upper, rate in brackets:
            conn.execute(
                "INSERT INTO tax_brackets(ruleset_id, lower_bound, upper_bound, rate) VALUES(?,?,?,?)",
                (ruleset_id, lower, upper, rate),
            )
    conn.commit()
    conn.close()


def calculate_tax(income, brackets):
    total = 0.0
    for bracket in brackets:
        lower = float(bracket["lower_bound"])
        upper = bracket["upper_bound"]
        upper = float(upper) if upper is not None else None
        if income <= lower:
            continue
        taxable = (min(income, upper) if upper is not None else income) - lower
        total += taxable * (float(bracket["rate"]) / 100)
    return round(total, 2)


def get_tax_rulesets():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM tax_rulesets ORDER BY country, tax_year DESC, region_name").fetchall()
    rulesets = []
    for row in rows:
        brackets = conn.execute("SELECT * FROM tax_brackets WHERE ruleset_id=? ORDER BY lower_bound", (row["id"],)).fetchall()
        item = dict(row)
        item["brackets"] = [dict(bracket) for bracket in brackets]
        rulesets.append(item)
    conn.close()
    return rulesets


def get_income_profile(month_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM months WHERE id=?", (month_id,)).fetchone()
    conn.close()
    return dict(row)


def save_income_profile(month_id, payload):
    mode = payload.get("mode", "simple")
    duration = max(float(payload.get("period_duration") or 1), 0.01)
    unit = payload.get("period_unit") or "month"
    if unit not in PERIODS_PER_YEAR:
        unit = "month"
    conn = get_connection()
    if mode == "gross_tax":
        gross = max(float(payload.get("gross_annual_income") or 0), 0)
        country = payload.get("country") or "Canada"
        region = payload.get("region_code") or "ON"
        year = int(payload.get("tax_year") or 2026)
        fed = _rules(conn, country, "FED", year)
        prov = [] if region == "FED" else _rules(conn, country, region, year)
        tax = calculate_tax(gross, fed) + calculate_tax(gross, prov)
        period_income = round((gross - tax) / (PERIODS_PER_YEAR[unit] / duration), 2)
        tax_rate = round((tax / gross) * 100, 2) if gross else 0
    else:
        amount = max(float(payload.get("take_home_income") or payload.get("income") or 0), 0)
        tax_rate = max(float(payload.get("manual_tax_rate") or 0), 0)
        period_income = round(amount * (1 - tax_rate / 100), 2)
        gross = None; country = None; region = None; year = None
    conn.execute(
        """
        UPDATE months SET income=?, income_mode=?, income_period_duration=?, income_period_unit=?,
            manual_tax_rate=?, gross_annual_income=?, tax_country=?, tax_region_code=?, tax_year=?
        WHERE id=?
        """,
        (period_income, mode, duration, unit, tax_rate, gross, country, region, year, month_id),
    )
    conn.commit(); conn.close()
    return get_income_profile(month_id)


def _rules(conn, country, region_code, year):
    ruleset = conn.execute("SELECT id FROM tax_rulesets WHERE country=? AND region_code=? AND tax_year=?", (country, region_code, year)).fetchone()
    if not ruleset:
        return []
    return conn.execute("SELECT lower_bound, upper_bound, rate FROM tax_brackets WHERE ruleset_id=? ORDER BY lower_bound", (ruleset["id"],)).fetchall()

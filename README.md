# FinanceTracker

FinanceTracker is a local Flask application for planning income and spending using the four-category framework popularized by Ramit Sethi:

- Fixed Costs
- Investments
- Savings
- Guilt Free Spending

The dashboard compares all four categories against the same take-home income amount, shows the remaining surplus, tracks recurring expenses, and can save completed periods as scorecards.

## Income profiles

Select the pencil icon on the **Income** card to open the income editor. FinanceTracker supports two ways to define income.

### Option 1: Simple take-home income

Use this option when you already know the amount deposited into your account, or when a grant, scholarship, or other source is not taxable.

Enter:

1. The income amount for one pay period.
2. An optional manual tax rate (defaults to `0%`).
3. The pay-period duration and unit, such as every `1 month` or every `2 weeks`.

The calculated amount is updated live while you type.

**Example — non-taxable monthly scholarship**

| Field | Value |
| --- | ---: |
| Take-home income before manual tax | $2,000 |
| Manual tax rate | 0% |
| Pay period | Every 1 month |
| Income shown on the dashboard | **$2,000 every 1 month** |

**Example — manually estimated biweekly tax**

| Field | Value |
| --- | ---: |
| Income before manual tax | $2,000 |
| Manual tax rate | 15% |
| Pay period | Every 2 weeks |
| Income shown on the dashboard | **$1,700 every 2 weeks** |

### Option 2: Gross annual income with tax rulesets

Use this option to estimate take-home pay from annual gross income. Choose a country, province/region, tax year, and pay period, then enter annual gross income. FinanceTracker:

1. Finds the federal ruleset for the selected country and year.
2. Applies the selected provincial/regional ruleset, when applicable.
3. Deducts each ruleset's enabled basic personal amount from gross income.
4. Applies that ruleset's marginal brackets to its remaining taxable income.
5. Subtracts federal and regional tax from gross income.
6. Converts annual take-home income to the selected pay period.

The live invoice-style breakdown shows annual gross income, each basic personal amount, federal and regional taxable income, tax owed to each jurisdiction, annual take-home pay, and take-home pay for the selected period.

**Illustrative monthly example**

Assume a hypothetical ruleset with a 10% federal rate, a 5% regional rate, a $15,000 federal basic personal amount, and a $10,000 regional basic personal amount:

| Calculation | Amount |
| --- | ---: |
| Annual gross income | $60,000.00 |
| Federal basic personal amount | −$15,000.00 |
| Federal taxable income | $45,000.00 |
| Federal tax (10%) | $4,500.00 |
| Regional basic personal amount | −$10,000.00 |
| Regional taxable income | $50,000.00 |
| Regional tax (5%) | $2,500.00 |
| Annual take-home pay | **$53,000.00** |
| Take-home every 1 month | **$4,416.67** |

This example is intentionally simplified. Actual results use every marginal bracket and basic personal amount configured in the selected rulesets.

## Tax ruleset management

Expand **View/edit tax rulesets** in the income editor to manage the tax data used by gross-income calculations.

### Browse and edit rulesets

Select a country, province/region, and tax year to display the matching federal ruleset first and the selected regional ruleset beneath it. For each ruleset, you can:

- Enable or disable its basic personal amount.
- Set the annual basic personal amount deducted before tax is calculated.
- Edit each bracket's **From**, **Up to**, and **Tax rate %** values.
- Add or remove brackets.
- Save or delete the ruleset.

An empty **Up to** value represents a bracket with no upper limit.

### Add a ruleset

Select **Add ruleset** and choose either:

- **Federal**, which applies at the country level; or
- **Provincial/regional**, which applies alongside the country's federal ruleset.

Provide a name, country, province/region when applicable, tax year, optional basic personal amount, and at least one tax bracket. If the same country, region, and tax year already exist, the form displays a live warning; saving will overwrite that ruleset. After saving, the ruleset browser and gross-income dropdowns refresh automatically.

Canada's federal and ten provincial rulesets are seeded for 2026. Rulesets are stored in the local database and can be updated as rates and brackets change or extended with additional countries and regions.

> [!IMPORTANT]
> FinanceTracker provides a configurable estimate, not tax advice. The calculation currently models configured income-tax brackets and basic personal amounts only; it does not automatically include payroll deductions, surtaxes, benefit clawbacks, additional credits, or other jurisdiction-specific rules. Verify rulesets against official sources before relying on an estimate.

## Other features

- Create, edit, and delete expenses in each spending category.
- Mark expenses as recurring.
- View spending totals, surplus, savings rate, investment rate, and a spending-mix chart.
- Save a period as a scorecard while carrying recurring expenses forward.
- Export scorecards as CSV.
- Export or import the local SQLite database.

## Run locally

Requires Python 3 and `pip`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py
```

Open <http://127.0.0.1:5000> in a browser. Application data is stored locally in `data/finance.db`.

## Tests

```bash
python3 -m pytest -q
```

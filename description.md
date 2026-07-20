Absolutely. Here's the summary I'd send to another developer. It explains both the application's current functionality and the architectural direction we've intentionally taken.

---

# Finance Tracker (Current Project Summary)

## Overview

I'm building a personal finance tracking web application for monthly budgeting and financial planning. The application is designed to run entirely locally using Flask and SQLite, with no external services required.

The overall goal is to create a polished, desktop-like budgeting application that allows me to manage monthly finances, carry recurring expenses forward, generate historical monthly scorecards, and visualize spending.

Although it's currently a local application, the architecture is being designed so that it could easily evolve into a larger application in the future.

---

# Technology Stack

### Backend

* Python 3
* Flask
* SQLite
* Standard `sqlite3` library
* REST-style JSON API

### Frontend

* HTML5
* Bootstrap 5
* Bootstrap Icons
* Vanilla JavaScript (ES6)
* Fetch API (AJAX)
* Chart.js (being added next)

No frontend frameworks (React/Vue/etc.) by design.

---

# Project Structure

```text
FinanceTracker/

│
├── app.py
├── database.py
├── config.py
│
├── services/
│   ├── finance.py        (planned)
│   ├── expenses.py
│   └── months.py
│
├── templates/
│   └── dashboard.html
│
├── static/
│   ├── css/
│   └── js/
│
└── data/
    └── finance.db
```

The project is being organized around a simple service layer rather than placing business logic directly inside Flask routes.

---

# Current Database

Currently two tables exist.

## months

```sql
id
label
month
year
income
finalized
created_at
```

`label` is planned to become the unique identifier for each month (e.g. `2026-07`).

---

## expenses

```sql
id
month_id
description
amount
category
recurring
```

Each expense belongs to one month and has a recurring flag used for future month generation.

---

# Current Features

## Dashboard

Currently supports:

* Current month detection
* Automatic month creation
* Monthly income
* Total spending
* Surplus calculation
* Green surplus
* Red deficit

The dashboard updates live without page refreshes.

---

## Category Cards

Four interactive cards:

* Fixed Costs
* Savings
* Investments
* Guilt Free Spending

Each card displays:

* Category total
* Expense count

Clicking a card opens a modal showing expenses for that category.

---

## Expense Manager

Each category modal currently contains:

* Category total
* Expense list
* Add Expense
* Delete Expense
* Recurring indicator

The UI is being transitioned toward inline editing instead of nested dialogs.

---

## Live Updates

The dashboard is API-driven.

Operations such as:

* updating income
* adding expenses
* deleting expenses

update immediately without refreshing the page.

---

# Current API

Examples include:

```
GET /api/dashboard      (planned)

GET /api/summary

GET /api/categories

GET /api/expenses

POST /api/income

POST /api/expenses

DELETE /api/expenses/<id>
```

The architecture is moving toward a single dashboard endpoint that returns everything needed to render the dashboard in one request.

---

# Architectural Direction

We're intentionally keeping the application layered.

```
Browser

↓

Dashboard

↓

Flask API

↓

Service Layer

↓

SQLite
```

Business logic is gradually being centralized into service modules instead of Flask routes.

---

# Planned Configuration Layer

We're introducing a centralized category configuration.

Instead of storing:

```
Fixed Costs
```

the database will store:

```
fixed
```

A shared configuration maps IDs to:

* display label
* color
* Bootstrap icon

Example:

```python
CATEGORY_CONFIG = {
    "fixed": {
        "label": "Fixed Costs",
        "color": "#0d6efd",
        "icon": "house-fill"
    },
    ...
}
```

This will become the single source of truth for:

* dashboard cards
* pie chart
* scorecards
* reports
* exports

---

# Planned Finance Service

Financial calculations are being consolidated into a dedicated service.

Example responsibilities:

```python
dashboard_summary()

category_totals()

surplus()

recurring_total()

largest_expense()

savings_rate()

investment_rate()
```

The UI should never calculate financial data itself.

---

# Frontend Direction

JavaScript is being split into modules.

```
dashboard.js

expenses.js

charts.js

api.js

utils.js
```

The goal is to keep responsibilities separated as the application grows.

---

# User Experience Philosophy

The application is intentionally being designed to feel like a desktop application rather than a traditional website.

Examples:

* no page refreshes
* inline editing
* Bootstrap modals
* live updates
* responsive dashboard
* interactive cards
* immediate feedback

---

# Version 1.0 Roadmap

## Sprint 1

Dashboard Foundation

* category IDs
* centralized config
* finance service
* Chart.js pie chart
* dashboard API

---

## Sprint 2

Monthly Workflow

* recurring expense engine
* expected monthly commitments
* create new month wizard

---

## Sprint 3

Scorecards

* finalize month
* immutable monthly snapshots
* historical timeline
* monthly notes

---

## Sprint 4

Polish

* CSV export
* PDF export
* responsive improvements
* animations
* cleanup

---

# Long-Term Goal

The objective isn't simply to build a CRUD budgeting app.

The goal is to build a cleanly architected, locally hosted personal finance application with a desktop-like user experience, strong separation of concerns, and maintainable code that can grow over time without requiring major refactoring.

One guiding principle we've adopted throughout development is to **invest in architecture early enough to simplify future work, but avoid overengineering**. Every refactor we've planned directly supports upcoming features in the roadmap, allowing us to keep the application cohesive while staying focused on delivering a polished v1.0.


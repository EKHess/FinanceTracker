const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
let selectedCategory = "";
let categoryChart;
let dashboardState = { categories: [], expenses: [], summary: {} };

async function api(path, options = {}) {
    const response = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
    return data;
}

async function loadDashboard() {
    dashboardState = await api("/api/dashboard");
    renderSummary(dashboardState.summary);
    renderCategories(dashboardState.categories);
    renderChart(dashboardState.categories);
}

function renderSummary(summary) {
    document.getElementById("income").textContent = money.format(summary.income);
    document.getElementById("spending").textContent = money.format(summary.spending);
    document.getElementById("recurringTotal").textContent = money.format(summary.recurring_total);
    document.getElementById("savingsRate").textContent = `${summary.savings_rate.toFixed(1)}%`;
    document.getElementById("investmentRate").textContent = `${summary.investment_rate.toFixed(1)}%`;

    const surplus = document.getElementById("surplus");
    surplus.textContent = money.format(summary.surplus);
    surplus.classList.toggle("text-success", summary.surplus >= 0);
    surplus.classList.toggle("text-danger", summary.surplus < 0);
}

function renderCategories(categories) {
    categories.forEach((category) => {
        document.getElementById(`${category.id}-total`).textContent = money.format(category.total);
        document.getElementById(`${category.id}-count`).textContent = category.count;
        document.getElementById(`${category.id}-caption`).textContent = `${category.count} expense${category.count === 1 ? "" : "s"}`;
    });
}

function renderChart(categories) {
    const ctx = document.getElementById("categoryChart");
    const data = categories.map((category) => category.total);
    const labels = categories.map((category) => category.label);
    const colors = categories.map((category) => category.color);

    if (categoryChart) {
        categoryChart.data.labels = labels;
        categoryChart.data.datasets[0].data = data;
        categoryChart.update();
        return;
    }

    categoryChart = new Chart(ctx, {
        type: "doughnut",
        data: { labels, datasets: [{ data, backgroundColor: colors }] },
        options: { plugins: { legend: { position: "bottom" } }, cutout: "60%" },
    });
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
}

async function editIncome() {
    const value = prompt("Monthly Income", dashboardState.summary.income || 0);
    if (value === null) return;
    await api("/api/income", { method: "POST", body: JSON.stringify({ income: parseFloat(value) || 0 }) });
    await loadDashboard();
}

async function showCategory(categoryId) {
    selectedCategory = categoryId;
    const category = window.CATEGORY_CONFIG[categoryId];
    document.getElementById("categoryTitle").textContent = category.label;
    await refreshCategory();
    new bootstrap.Modal(document.getElementById("categoryModal")).show();
}

function toggleExpenseForm(expense = null) {
    document.getElementById("expenseForm").style.display = "block";
    document.getElementById("expenseId").value = expense?.id || "";
    document.getElementById("expenseDescription").value = expense?.description || "";
    document.getElementById("expenseAmount").value = expense?.amount || "";
    document.getElementById("expenseRecurring").checked = Boolean(expense?.recurring);
}

async function saveExpense() {
    const expenseId = document.getElementById("expenseId").value;
    const payload = {
        description: document.getElementById("expenseDescription").value,
        amount: parseFloat(document.getElementById("expenseAmount").value) || 0,
        category: selectedCategory,
        recurring: document.getElementById("expenseRecurring").checked,
    };
    const path = expenseId ? `/api/expenses/${expenseId}` : "/api/expenses";
    await api(path, { method: expenseId ? "PUT" : "POST", body: JSON.stringify(payload) });
    document.getElementById("expenseForm").style.display = "none";
    await refreshCategory();
}

async function refreshCategory() {
    const expenses = await api(`/api/expenses?category=${encodeURIComponent(selectedCategory)}`);
    const table = document.getElementById("expenseTable");
    table.innerHTML = "";
    let total = 0;

    expenses.forEach((expense) => {
        total += expense.amount;
        const row = document.createElement("tr");
        row.innerHTML = `<td>${expense.description}</td><td>${money.format(expense.amount)}</td><td>${expense.recurring ? "✓" : ""}</td><td class="text-end"><button class="btn btn-sm btn-outline-primary me-1">Edit</button><button class="btn btn-sm btn-outline-danger">Delete</button></td>`;
        row.querySelector(".btn-outline-primary").addEventListener("click", () => toggleExpenseForm(expense));
        row.querySelector(".btn-outline-danger").addEventListener("click", () => deleteExpense(expense.id));
        table.appendChild(row);
    });

    document.getElementById("categoryTotal").textContent = money.format(total);
    await loadDashboard();
}

async function deleteExpense(id) {
    if (!confirm("Delete this expense?")) return;
    await api(`/api/expenses/${id}`, { method: "DELETE" });
    await refreshCategory();
}

loadDashboard();

function openSaveScorecardModal() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const lastDay = new Date(year, today.getMonth() + 1, 0).getDate();
    document.getElementById("scorecardName").value = `${today.toLocaleString("default", { month: "long" })} ${year}`;
    document.getElementById("scorecardStartDate").value = `${year}-${month}-01`;
    document.getElementById("scorecardEndDate").value = `${year}-${month}-${String(lastDay).padStart(2, "0")}`;
    document.getElementById("scorecardSaveError").classList.add("d-none");
    new bootstrap.Modal(document.getElementById("saveScorecardModal")).show();
}

async function saveScorecard() {
    const error = document.getElementById("scorecardSaveError");
    error.classList.add("d-none");
    const payload = {
        name: document.getElementById("scorecardName").value,
        start_date: document.getElementById("scorecardStartDate").value,
        end_date: document.getElementById("scorecardEndDate").value,
    };

    try {
        await api("/api/scorecards", { method: "POST", body: JSON.stringify(payload) });
        bootstrap.Modal.getInstance(document.getElementById("saveScorecardModal")).hide();
        await loadDashboard();
    } catch (err) {
        error.textContent = err.message;
        error.classList.remove("d-none");
    }
}

async function showScorecards() {
    const modal = new bootstrap.Modal(document.getElementById("scorecardsModal"));
    modal.show();
    await refreshScorecardList();
}

function renderScorecardList(scorecards) {
    const list = document.getElementById("scorecardList");
    list.innerHTML = "";
    if (!scorecards.length) {
        list.innerHTML = '<div class="text-muted">No scorecards saved yet.</div>';
        return;
    }
    scorecards.forEach((scorecard) => {
        const button = document.createElement("button");
        button.className = "list-group-item list-group-item-action";
        button.innerHTML = `<div class="fw-bold">${escapeHtml(scorecard.name)}</div><small>${scorecard.start_date} – ${scorecard.end_date}</small><div>${money.format(scorecard.total_spending)}</div>`;
        button.addEventListener("click", () => loadScorecardDetails(scorecard.id));
        list.appendChild(button);
    });
}

async function loadScorecardDetails(id) {
    const scorecard = await api(`/api/scorecards/${id}`);
    renderScorecardDetails(scorecard);
}


let activeScorecardId = null;
let editingScorecardExpenseId = null;

function categoryOptions(selectedCategory = "") {
    return Object.entries(window.CATEGORY_CONFIG).map(([id, category]) => `<option value="${id}" ${id === selectedCategory ? "selected" : ""}>${category.label}</option>`).join("");
}

function showScorecardExpenseForm(expense = null) {
    editingScorecardExpenseId = expense?.id || null;
    const form = document.getElementById("scorecardExpenseForm");
    form.classList.remove("d-none");
    document.getElementById("scorecardExpenseFormTitle").textContent = expense ? "Edit saved charge" : "Add saved charge";
    document.getElementById("scorecardExpenseDescription").value = expense?.description || "";
    document.getElementById("scorecardExpenseAmount").value = expense?.amount || "";
    document.getElementById("scorecardExpenseCategory").value = expense?.category || "fixed";
    document.getElementById("scorecardExpenseRecurring").checked = Boolean(expense?.recurring);
}

function hideScorecardExpenseForm() {
    editingScorecardExpenseId = null;
    document.getElementById("scorecardExpenseForm").classList.add("d-none");
}

async function saveScorecardExpense() {
    const payload = {
        description: document.getElementById("scorecardExpenseDescription").value,
        amount: parseFloat(document.getElementById("scorecardExpenseAmount").value) || 0,
        category: document.getElementById("scorecardExpenseCategory").value,
        recurring: document.getElementById("scorecardExpenseRecurring").checked,
    };
    const path = editingScorecardExpenseId ? `/api/scorecards/${activeScorecardId}/expenses/${editingScorecardExpenseId}` : `/api/scorecards/${activeScorecardId}/expenses`;
    const method = editingScorecardExpenseId ? "PUT" : "POST";
    const scorecard = await api(path, { method, body: JSON.stringify(payload) });
    renderScorecardDetails(scorecard);
    await refreshScorecardList();
}

async function deleteScorecardExpense(expenseId) {
    if (!confirm("Delete this saved charge?")) return;
    const scorecard = await api(`/api/scorecards/${activeScorecardId}/expenses/${expenseId}`, { method: "DELETE" });
    renderScorecardDetails(scorecard);
    await refreshScorecardList();
}

async function deleteActiveScorecard() {
    if (!activeScorecardId) return;
    if (!confirm("Delete this scorecard? This action cannot be undone.")) return;
    await api(`/api/scorecards/${activeScorecardId}`, { method: "DELETE" });
    activeScorecardId = null;
    document.getElementById("scorecardDetails").className = "scorecard-details text-muted";
    document.getElementById("scorecardDetails").textContent = "Select a scorecard to view totals and detailed charges.";
    await refreshScorecardList();
}

async function refreshScorecardList() {
    const scorecards = await api("/api/scorecards");
    renderScorecardList(scorecards);
}

function renderScorecardDetails(scorecard) {
    activeScorecardId = scorecard.id;
    editingScorecardExpenseId = null;
    const details = document.getElementById("scorecardDetails");
    details.classList.remove("text-muted");
    details.innerHTML = `
        <div class="d-flex flex-wrap justify-content-between align-items-start gap-2 mb-3">
            <div>
                <h4>${escapeHtml(scorecard.name)}</h4>
                <div class="text-muted">${scorecard.start_date} – ${scorecard.end_date}</div>
            </div>
            <div class="text-end">
                <h4>${money.format(scorecard.total_spending)}</h4>
                <a class="btn btn-sm btn-outline-primary me-1" href="/api/scorecards/${scorecard.id}/export.csv"><i class="bi bi-filetype-csv me-1"></i>Export to CSV</a><button class="btn btn-sm btn-outline-danger" onclick="deleteActiveScorecard()"><i class="bi bi-trash me-1"></i>Delete Scorecard</button>
            </div>
        </div>
        <div class="card mb-3 scorecard-editor-card">
            <div class="card-body">
                <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
                    <h5 class="mb-0">Saved charges</h5>
                    <button class="btn btn-sm btn-success" onclick="showScorecardExpenseForm()">+ Add Charge</button>
                </div>
                <div id="scorecardExpenseForm" class="scorecard-expense-form mt-3 d-none">
                    <div class="fw-bold" id="scorecardExpenseFormTitle">Add saved charge</div>
                    <div class="row g-3 align-items-end">
                        <div class="col-12 col-lg-5">
                            <label for="scorecardExpenseDescription" class="form-label">Description</label>
                            <input id="scorecardExpenseDescription" class="form-control" placeholder="Description">
                        </div>
                        <div class="col-12 col-sm-6 col-lg-3">
                            <label for="scorecardExpenseAmount" class="form-label">Amount</label>
                            <input id="scorecardExpenseAmount" class="form-control" type="number" step="0.01" min="0" placeholder="Amount">
                        </div>
                        <div class="col-12 col-sm-6 col-lg-4">
                            <label for="scorecardExpenseCategory" class="form-label">Category</label>
                            <select id="scorecardExpenseCategory" class="form-select">${categoryOptions()}</select>
                        </div>
                        <div class="col-12 d-flex flex-wrap justify-content-between align-items-center gap-3">
                            <div class="form-check mb-0">
                                <input id="scorecardExpenseRecurring" class="form-check-input" type="checkbox">
                                <label class="form-check-label" for="scorecardExpenseRecurring">Recurring charge</label>
                            </div>
                            <div class="d-flex flex-wrap gap-2 scorecard-form-actions">
                                <button class="btn btn-primary" onclick="saveScorecardExpense()">Save</button>
                                <button class="btn btn-outline-secondary" onclick="hideScorecardExpenseForm()">Cancel</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;

    scorecard.categories.forEach((category) => {
        const section = document.createElement("div");
        section.className = "card category-summary mb-3";
        section.style.setProperty("--category-color", category.color);
        const rows = category.expenses.length ? category.expenses.map((expense) => `<div class="expense-row border-top py-2"><span>${escapeHtml(expense.description)}</span><span>${expense.recurring ? "Recurring" : "One-time"}</span><strong>${money.format(expense.amount)}</strong><span class="text-end"><button class="btn btn-sm btn-outline-primary me-1">Edit</button><button class="btn btn-sm btn-outline-danger">Delete</button></span></div>`).join("") : '<div class="text-muted border-top py-2">No charges in this category.</div>';
        section.innerHTML = `<div class="card-body"><div class="d-flex justify-content-between"><h5>${category.label}</h5><strong>${money.format(category.total)}</strong></div><div class="small text-muted mb-2">${category.count} charge${category.count === 1 ? "" : "s"}</div>${rows}</div>`;
        section.querySelectorAll(".btn-outline-primary").forEach((button, index) => button.addEventListener("click", () => showScorecardExpenseForm(category.expenses[index])));
        section.querySelectorAll(".btn-outline-danger").forEach((button, index) => button.addEventListener("click", () => deleteScorecardExpense(category.expenses[index].id)));
        details.appendChild(section);
    });
}


function exportDatabase() {
    window.location.href = "/api/database/export";
}

function openImportDatabaseModal() {
    document.getElementById("databaseImportFile").value = "";
    document.getElementById("databaseImportError").classList.add("d-none");
    new bootstrap.Modal(document.getElementById("importDatabaseModal")).show();
}

async function importDatabase() {
    const fileInput = document.getElementById("databaseImportFile");
    const error = document.getElementById("databaseImportError");
    error.classList.add("d-none");

    if (!fileInput.files.length) {
        error.textContent = "Choose a database file to import.";
        error.classList.remove("d-none");
        return;
    }

    if (!confirm("Import this database? This replaces the current app database.")) return;

    const formData = new FormData();
    formData.append("database", fileInput.files[0]);
    const response = await fetch("/api/database/import", { method: "POST", body: formData });
    const data = await response.json();

    if (!response.ok) {
        error.textContent = data.error || `Request failed: ${response.status}`;
        error.classList.remove("d-none");
        return;
    }

    bootstrap.Modal.getInstance(document.getElementById("importDatabaseModal")).hide();
    await loadDashboard();
}

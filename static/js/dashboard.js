const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
let selectedCategory = "";
let categoryChart;
let dashboardState = { categories: [], expenses: [], summary: {} };

async function api(path, options = {}) {
    const response = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    return response.json();
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

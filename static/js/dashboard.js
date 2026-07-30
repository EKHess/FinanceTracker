const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
let selectedCategory = "";
let categoryChart;
let dashboardState = { categories: [], expenses: [], summary: {} };
let currentWorkspaceState = null;
let workspaceTimeline = [];
let workspaceIndex = 0;
let incomeEditorLoaded = false;
let visibleExpenseLimit = 5;
let visibleRecurringExpenseLimit = 5;
let workspaceSchedule = null;
let financialReports = [];
const CATEGORY_ORDER_KEY = "finance-tracker-category-order";

function getCategoryOrder() {
    const fallback = Object.keys(window.CATEGORY_CONFIG);
    try {
        const stored = JSON.parse(localStorage.getItem(CATEGORY_ORDER_KEY));
        if (!Array.isArray(stored)) return fallback;
        return [...stored.filter((id) => fallback.includes(id)), ...fallback.filter((id) => !stored.includes(id))];
    } catch {
        return fallback;
    }
}

function orderCategories(categories) {
    const positions = new Map(getCategoryOrder().map((id, index) => [id, index]));
    return [...categories].sort((a, b) => (positions.get(a.id) ?? positions.size) - (positions.get(b.id) ?? positions.size));
}

function applyCategoryOrder() {
    const order = getCategoryOrder();
    const moveChildren = (container, selector) => {
        if (!container) return;
        const children = new Map([...container.querySelectorAll(selector)].map((element) => [element.dataset.categoryId, element]));
        order.forEach((id) => { if (children.has(id)) container.appendChild(children.get(id)); });
    };
    moveChildren(document.querySelector(".categories-table"), ".categories-table-row");
    moveChildren(document.getElementById("categoryCards"), ".category-row");
}

function saveCategoryOrder() {
    const rows = [...document.querySelectorAll(".categories-table-row")];
    localStorage.setItem(CATEGORY_ORDER_KEY, JSON.stringify(rows.map((row) => row.dataset.categoryId)));
    applyCategoryOrder();
    if (dashboardState.categories?.length) {
        dashboardState.categories = orderCategories(dashboardState.categories);
        renderCategoryLegend(dashboardState.categories, Number(dashboardState.summary.income) || 0);
        renderChart(dashboardState.categories);
    }
}

function initializeCategoryReordering() {
    const table = document.querySelector(".categories-table");
    if (!table) return;
    let draggedRow = null;
    table.querySelectorAll(".category-order").forEach((handle) => {
        handle.addEventListener("dragstart", (event) => {
            draggedRow = handle.closest(".categories-table-row");
            draggedRow.classList.add("is-dragging");
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", draggedRow.dataset.categoryId);
        });
        handle.addEventListener("dragend", () => {
            draggedRow?.classList.remove("is-dragging");
            table.querySelectorAll(".drag-over").forEach((row) => row.classList.remove("drag-over"));
            draggedRow = null;
        });
    });
    table.addEventListener("dragover", (event) => {
        if (!draggedRow) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        const target = event.target.closest(".categories-table-row");
        table.querySelectorAll(".drag-over").forEach((row) => row.classList.toggle("drag-over", row === target && row !== draggedRow));
        if (!target || target === draggedRow) return;
        const afterTarget = event.clientY > target.getBoundingClientRect().top + target.offsetHeight / 2;
        table.insertBefore(draggedRow, afterTarget ? target.nextSibling : target);
    });
    table.addEventListener("drop", (event) => {
        if (!draggedRow) return;
        event.preventDefault();
        saveCategoryOrder();
    });
    applyCategoryOrder();
}

function openCategoryEditor(categoryId) {
    const category = window.CATEGORY_CONFIG[categoryId];
    document.getElementById("categoryEditorId").value = categoryId;
    document.getElementById("categoryEditorLabel").value = category.label;
    document.getElementById("categoryEditorColorPicker").value = category.color;
    document.getElementById("categoryEditorColorText").value = category.color.slice(1).toUpperCase();
    document.getElementById("categoryEditorError").classList.add("d-none");
    new bootstrap.Modal(document.getElementById("categoryEditorModal")).show();
}

function syncCategoryColorFromPicker() {
    document.getElementById("categoryEditorColorText").value = document.getElementById("categoryEditorColorPicker").value.slice(1).toUpperCase();
}

function syncCategoryColorFromText() {
    const value = document.getElementById("categoryEditorColorText").value.trim();
    if (/^[0-9a-f]{6}$/i.test(value)) document.getElementById("categoryEditorColorPicker").value = `#${value}`;
}

function refreshCategoryAppearance(category) {
    window.CATEGORY_CONFIG[category.id] = { ...window.CATEGORY_CONFIG[category.id], label: category.label, color: category.color };
    const managementRow = document.querySelector(`.categories-table-row[data-category-id="${category.id}"]`);
    managementRow.querySelector("strong").textContent = category.label;
    managementRow.querySelector(".category-color i").style.background = category.color;
    managementRow.querySelector(".category-color").lastChild.textContent = category.color;
    managementRow.querySelector(".category-actions button").setAttribute("aria-label", `Edit ${category.label}`);
    managementRow.querySelector(".category-order").setAttribute("aria-label", `Drag to reorder ${category.label}`);
    const budgetRow = document.querySelector(`#categoryCards [data-category-id="${category.id}"]`);
    budgetRow.querySelector("strong").textContent = category.label;
    const icon = budgetRow.querySelector(".category-icon");
    icon.style.color = category.color;
    icon.style.background = `${category.color}18`;
    document.querySelectorAll(`option[value="${category.id}"]`).forEach((option) => { option.textContent = category.label; });
}

async function saveCategoryEdit(event) {
    event.preventDefault();
    const categoryId = document.getElementById("categoryEditorId").value;
    const error = document.getElementById("categoryEditorError");
    error.classList.add("d-none");
    try {
        const category = await api(`/api/categories/${categoryId}`, { method: "PUT", body: JSON.stringify({
            label: document.getElementById("categoryEditorLabel").value,
            color: `#${document.getElementById("categoryEditorColorText").value}`,
        }) });
        refreshCategoryAppearance(category);
        await loadDashboard();
        bootstrap.Modal.getInstance(document.getElementById("categoryEditorModal")).hide();
    } catch (err) {
        error.textContent = err.message;
        error.classList.remove("d-none");
    }
}

async function deleteCategory(categoryId) {
    const category = window.CATEGORY_CONFIG[categoryId];
    const current = currentWorkspaceState?.categories?.find((item) => item.id === categoryId);
    const returned = Number(current?.total) || 0;
    const confirmed = window.confirm(
        `Delete “${category.label}”?\n\nThis cannot be undone. All expenses tied to this category in the current workspace, including recurring expenses, will be deleted. ${money.format(returned)} will return to this workspace's unspent income/surplus as if it was never spent.\n\nPast saved financial reports will not be changed.`
    );
    if (!confirmed) return;
    try {
        await api(`/api/categories/${categoryId}`, { method: "DELETE" });
        document.querySelector(`.categories-table-row[data-category-id="${categoryId}"]`)?.remove();
        document.querySelector(`#categoryCards [data-category-id="${categoryId}"]`)?.remove();
        document.querySelectorAll(`option[value="${categoryId}"]`).forEach((option) => option.remove());
        delete window.CATEGORY_CONFIG[categoryId];
        localStorage.setItem(CATEGORY_ORDER_KEY, JSON.stringify(getCategoryOrder().filter((id) => id !== categoryId)));
        await loadDashboard();
        renderExpenseManager();
        renderRecurringExpensesPage();
    } catch (error) {
        window.alert(error.message);
    }
}

function setDarkMode(enabled) {
    const theme = enabled ? "dark" : "light";
    document.documentElement.dataset.bsTheme = theme;
    localStorage.setItem("finance-tracker-theme", theme);
    const toggle = document.getElementById("darkModeToggle");
    if (toggle) toggle.checked = enabled;
    if (categoryChart) categoryChart.draw();
}

function initializeTheme() {
    setDarkMode(document.documentElement.dataset.bsTheme === "dark");
}

function navigateTo(page) {
    document.querySelectorAll(".app-page").forEach((section) => section.classList.toggle("active", section.id === `page-${page}`));
    document.querySelectorAll(".app-nav [data-page]").forEach((button) => button.classList.toggle("active", button.dataset.page === page));
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (page === "income" || page === "settings") initializeIncomeEditor();
    if (page === "settings") loadWorkspaceSchedule();
    if (page === "recurring") renderRecurringExpensesPage();
    if (page === "reports") refreshScorecardList();
    if (page === "net-worth") loadNetWorth();
    if (page === "tfsa-calculator") initializeTfsaCalculator(true);
    if (page === "retirement-calculator") updateRetirementCalculator();
}

function retirementInputNumber(id) {
    const value = document.getElementById(id)?.value.replace?.(/,/g, "") ?? document.getElementById(id)?.value;
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function updateRetirementCalculator() {
    const retirementAge = retirementInputNumber("retirementAge");
    const lifeExpectancy = retirementInputNumber("retirementLifeExpectancy");
    const annualSpending = retirementInputNumber("retirementAnnualSpending");
    const includeInflation = document.getElementById("retirementIncludeInflation")?.checked ?? false;
    const inflationPercent = includeInflation ? retirementInputNumber("retirementInflationRate") : 0;
    const inflationRate = inflationPercent / 100;
    const years = Math.max(lifeExpectancy - retirementAge, 0);
    const requiredSavings = inflationRate === 0
        ? annualSpending * years
        : annualSpending * (((1 + inflationRate) ** years - 1) / inflationRate);

    document.getElementById("retirementYears").textContent = String(years);
    document.getElementById("retirementSpendingSummary").textContent = money.format(annualSpending);
    document.getElementById("retirementInflationSummary").textContent = `${inflationPercent.toFixed(2)}%`;
    document.getElementById("retirementTodayTotal").textContent = money.format(annualSpending * years);
    document.getElementById("retirementRequiredSavings").textContent = money.format(requiredSavings);
    document.getElementById("retirementInflationRate").disabled = !includeInflation;
}

function initializeRetirementCalculator() {
    const inputs = ["retirementAge", "retirementLifeExpectancy", "retirementAnnualSpending", "retirementIncludeInflation", "retirementInflationRate"];
    inputs.forEach((id) => document.getElementById(id)?.addEventListener("input", updateRetirementCalculator));
    document.getElementById("retirementIncludeInflation")?.addEventListener("change", updateRetirementCalculator);
    updateRetirementCalculator();
}

const tfsaPeriodsPerYear = { annually: 1, quarterly: 4, monthly: 12, biweekly: 26, weekly: 52 };
let tfsaCalculatorInitialized = false;

function tfsaInputNumber(id) {
    const value = Number(document.getElementById(id)?.value);
    return Number.isFinite(value) && value >= 0 ? value : 0;
}

function calculateTfsaGrowth(startingContribution, contributionAmount, periodsPerYear, annualReturnRate, years) {
    const periodicRate = annualReturnRate / periodsPerYear;
    const totalPeriods = years * periodsPerYear;
    const growthFactor = (1 + periodicRate) ** totalPeriods;
    const startingFutureValue = startingContribution * growthFactor;
    const contributionFutureValue = periodicRate === 0
        ? contributionAmount * totalPeriods
        : contributionAmount * ((growthFactor - 1) / periodicRate);
    const yearlyBalances = [];
    let balance = startingContribution;
    for (let period = 1; period <= totalPeriods; period += 1) {
        balance = balance * (1 + periodicRate);
        balance = balance + contributionAmount;
        if (period % periodsPerYear === 0) yearlyBalances.push(balance);
    }
    return { total: startingFutureValue + contributionFutureValue, yearlyBalances };
}

function tfsaIncrementalTax(income, interest, country, regionCode, taxYear) {
    const taxForIncome = (amount) => {
        const federal = calculateRulesetTax(amount, findRuleset(country, "FED", taxYear)).taxOwed;
        const regional = regionCode === "FED" ? 0 : calculateRulesetTax(amount, findRuleset(country, regionCode, taxYear)).taxOwed;
        return federal + regional;
    };
    return Math.max(taxForIncome(income + Math.max(interest, 0)) - taxForIncome(income), 0);
}

function renderTfsaTaxSelectors(preferredCountry = "Canada", preferredRegion = "AB", preferredYear = 2026) {
    const countrySelect = document.getElementById("tfsaCountry");
    const regionSelect = document.getElementById("tfsaProvince");
    const yearSelect = document.getElementById("tfsaTaxYear");
    if (!countrySelect) return;
    const countries = [...new Set(taxRulesets.map((ruleset) => ruleset.country))].sort();
    countrySelect.innerHTML = countries.map((country) => `<option value="${escapeHtml(country)}">${escapeHtml(country)}</option>`).join("");
    countrySelect.value = countries.includes(preferredCountry) ? preferredCountry : countries[0] || "";
    const syncYears = (requestedYear = yearSelect.value || preferredYear) => {
        const years = [...new Set(taxRulesets.filter((ruleset) => ruleset.country === countrySelect.value && ["FED", regionSelect.value].includes(ruleset.region_code)).map((ruleset) => Number(ruleset.tax_year)))].sort((a, b) => b - a);
        yearSelect.innerHTML = years.map((year) => `<option value="${year}">${year}</option>`).join("");
        yearSelect.value = years.includes(Number(requestedYear)) ? String(requestedYear) : String(years[0] || "");
        updateTfsaCalculator();
    };
    const syncRegions = (requestedRegion = regionSelect.value || preferredRegion) => {
        const regionalRules = taxRulesets.filter((ruleset) => ruleset.country === countrySelect.value && ruleset.region_code !== "FED");
        const uniqueRegions = [...new Map(regionalRules.map((ruleset) => [ruleset.region_code, ruleset])).values()];
        regionSelect.innerHTML = `<option value="FED">Federal only</option>${uniqueRegions.map((ruleset) => `<option value="${escapeHtml(ruleset.region_code)}">${escapeHtml(ruleset.region_name)}</option>`).join("")}`;
        regionSelect.value = ["FED", ...uniqueRegions.map((ruleset) => ruleset.region_code)].includes(requestedRegion) ? requestedRegion : "FED";
        syncYears(preferredYear);
    };
    countrySelect.onchange = () => syncRegions("FED");
    regionSelect.onchange = () => syncYears();
    yearSelect.onchange = updateTfsaCalculator;
    syncRegions(preferredRegion);
}

function updateTfsaCalculator() {
    const periodsPerYear = Number(document.getElementById("tfsaFrequency")?.value) || tfsaPeriodsPerYear.monthly;
    const years = Math.max(Math.floor(tfsaInputNumber("tfsaYears")), 1);
    const startingContribution = tfsaInputNumber("tfsaStartingContribution");
    const contributionAmount = tfsaInputNumber("tfsaOngoingContribution");
    const result = calculateTfsaGrowth(startingContribution, contributionAmount, periodsPerYear, tfsaInputNumber("tfsaReturnRate"), years);
    const income = tfsaInputNumber("tfsaAnnualIncome");
    const country = document.getElementById("tfsaCountry")?.value || "";
    const regionCode = document.getElementById("tfsaProvince")?.value || "FED";
    const taxYear = Number(document.getElementById("tfsaTaxYear")?.value);
    const taxableBalances = result.yearlyBalances.map((grossBalance, index) => {
        const contributedPrincipal = startingContribution + contributionAmount * periodsPerYear * (index + 1);
        return grossBalance - tfsaIncrementalTax(income, grossBalance - contributedPrincipal, country, regionCode, taxYear);
    });
    const taxableTotal = taxableBalances.at(-1) ?? startingContribution;
    document.getElementById("tfsaResultYears").textContent = String(years);
    document.getElementById("tfsaFutureValue").textContent = money.format(result.total);
    document.getElementById("tfsaTaxSavings").textContent = money.format(Math.max(result.total - taxableTotal, 0));
    renderTfsaChart(result.yearlyBalances, taxableBalances);
}

function renderTfsaChart(tfsaBalances, taxableBalances) {
    const bars = document.getElementById("tfsaBars");
    const yAxis = document.getElementById("tfsaYAxis");
    const maximum = Math.max(...tfsaBalances, ...taxableBalances, 1);
    const compactMoney = (value) => value >= 1000000 ? `$${(value / 1000000).toFixed(1)}M` : value >= 1000 ? `$${(value / 1000).toFixed(1)}K` : money.format(value);
    yAxis.innerHTML = [maximum, maximum * .75, maximum * .5, maximum * .25, 0].map((value) => `<span>${compactMoney(value)}</span>`).join("");
    bars.style.gridTemplateColumns = `repeat(${tfsaBalances.length},minmax(42px,1fr))`;
    bars.innerHTML = tfsaBalances.map((value, index) => `<div class="tfsa-year"><div class="tfsa-bar-pair"><i class="tax-free" style="height:${value / maximum * 100}%" title="TFSA: ${money.format(value)}"></i><i class="taxable" style="height:${taxableBalances[index] / maximum * 100}%" title="Taxable: ${money.format(taxableBalances[index])}"></i></div><span>${index + 1} ${index === 0 ? "yr" : "yrs"}</span></div>`).join("");
}

async function initializeTfsaCalculator(refreshRulesets = false) {
    if (!tfsaCalculatorInitialized) {
        ["tfsaAnnualIncome", "tfsaStartingContribution", "tfsaOngoingContribution", "tfsaFrequency", "tfsaReturnRate", "tfsaYears"].forEach((id) => document.getElementById(id)?.addEventListener("input", updateTfsaCalculator));
        tfsaCalculatorInitialized = true;
    }
    if (refreshRulesets || !taxRulesets.length) taxRulesets = await api("/api/tax-rulesets");
    const country = document.getElementById("tfsaCountry")?.value || "Canada";
    const region = document.getElementById("tfsaProvince")?.value || "AB";
    const year = Number(document.getElementById("tfsaTaxYear")?.value) || 2026;
    renderTfsaTaxSelectors(country, region, year);
}

let netWorthState = { assets: [], liabilities: [] };
let netWorthHistory = [];
let netWorthChart;

async function loadNetWorth() {
    [netWorthState, netWorthHistory] = await Promise.all([api("/api/net-worth"), api("/api/scorecards")]);
    document.getElementById("netWorthTotal").textContent = money.format(netWorthState.net_worth);
    document.getElementById("netWorthTotal").classList.toggle("negative", netWorthState.net_worth < 0);
    document.getElementById("netWorthAssets").textContent = money.format(netWorthState.total_assets);
    document.getElementById("netWorthLiabilities").textContent = money.format(netWorthState.total_liabilities);
    document.getElementById("assetTotal").textContent = money.format(netWorthState.total_assets);
    document.getElementById("liabilityTotal").textContent = money.format(netWorthState.total_liabilities);
    renderNetWorthItems("asset", netWorthState.assets);
    renderNetWorthItems("liability", netWorthState.liabilities);
    renderNetWorthHistory();
    renderLiabilityAutocomplete(netWorthState.liabilities);
}

function renderLiabilityAutocomplete(liabilities) {
    const list = document.getElementById("liabilityNames");
    if (!list) return;
    list.replaceChildren(...liabilities.filter((liability) => liability.amount > 0).map((liability) => {
        const option = document.createElement("option");
        option.value = liability.name;
        option.label = `${liability.name} · ${money.format(liability.amount)} remaining`;
        return option;
    }));
}

async function loadLiabilityAutocomplete() {
    renderLiabilityAutocomplete((await api("/api/net-worth")).liabilities);
}

function showExpenseSubmissionError(error, inlineAlert = null) {
    if (error.message.includes("exceeds the current value")) {
        window.alert(error.message);
        return;
    }
    if (inlineAlert) {
        inlineAlert.textContent = error.message;
        inlineAlert.classList.remove("d-none");
    } else {
        window.alert(error.message);
    }
}

function netWorthRangeStart(range) {
    if (range === "all") return null;
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    start.setMonth(start.getMonth() - ({ "6m": 6, "1y": 12, "3y": 36 }[range] || 12));
    return start;
}

function renderNetWorthHistory() {
    const canvas = document.getElementById("netWorthChart");
    if (!canvas) return;
    const start = netWorthRangeStart(document.getElementById("netWorthRange").value);
    const points = netWorthHistory.filter((report) => report.net_worth !== null && (!start || new Date(`${report.end_date}T00:00:00`) >= start))
        .sort((a, b) => a.end_date.localeCompare(b.end_date));
    document.getElementById("netWorthChartEmpty").classList.toggle("d-none", points.length > 0);
    canvas.classList.toggle("d-none", points.length === 0);
    if (netWorthChart) netWorthChart.destroy();
    if (!points.length) return;
    netWorthChart = new Chart(canvas, { type: "line", data: { labels: points.map((point) => formatWorkspacePeriodDate(point.end_date)), datasets: [{
        label: "Net Worth", data: points.map((point) => point.net_worth), borderColor: "#15975d", backgroundColor: "rgba(21,151,93,.12)",
        pointBackgroundColor: "#15975d", pointBorderColor: "#fff", pointBorderWidth: 2, pointRadius: 4, pointHoverRadius: 6, borderWidth: 3, fill: true, tension: .3,
    }] }, options: { responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: "index" }, plugins: { legend: { display: false },
        tooltip: { callbacks: { label: (context) => `Net Worth: ${money.format(context.parsed.y)}` } } }, scales: {
        x: { grid: { display: false }, ticks: { color: "#718096", maxRotation: 0, autoSkip: true } },
        y: { grid: { color: "rgba(113,128,150,.14)" }, ticks: { color: "#718096", callback: (value) => money.format(value) } },
    } } });
}

function renderNetWorthItems(type, items) {
    const container = document.getElementById(`${type}Items`);
    container.replaceChildren();
    if (!items.length) {
        const empty = document.createElement("p");
        empty.className = "worth-empty";
        empty.textContent = `No ${type === "asset" ? "assets" : "liabilities"} added yet.`;
        container.appendChild(empty);
        return;
    }
    items.forEach((item) => {
        const section = document.createElement("div");
        section.className = type === "liability" ? "liability-section" : "worth-section";
        const row = document.createElement("div");
        row.className = "worth-row";
        let history;
        if (type === "liability") {
            const historyId = `liability-payments-${item.id}`;
            row.classList.add("liability-toggle");
            row.tabIndex = 0;
            row.setAttribute("role", "button");
            row.setAttribute("aria-expanded", "false");
            row.setAttribute("aria-controls", historyId);
            history = renderLiabilityPayments(item, historyId);
            const toggle = () => {
                const expanded = row.getAttribute("aria-expanded") === "true";
                row.setAttribute("aria-expanded", String(!expanded));
                history.hidden = expanded;
            };
            row.addEventListener("click", toggle);
            row.addEventListener("keydown", (event) => {
                if (event.target === row && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    toggle();
                }
            });
        }
        const icon = document.createElement("span");
        icon.className = `worth-row-icon ${type}`;
        icon.innerHTML = `<i class="bi bi-${type === "asset" ? "bank" : "credit-card"}"></i>`;
        const copy = document.createElement("div");
        const name = document.createElement("strong");
        name.textContent = item.name;
        const category = document.createElement("small");
        category.textContent = item.category || (type === "asset" ? "Asset" : "Liability");
        if (type === "liability") {
            const count = item.payment_history?.length || 0;
            category.textContent += ` · ${count} ${count === 1 ? "payment" : "payments"}`;
        }
        copy.append(name, category);
        const amount = document.createElement("b");
        amount.textContent = money.format(item.amount);
        const actions = document.createElement("div");
        actions.className = "worth-actions";
        actions.innerHTML = '<button type="button" aria-label="Edit item"><i class="bi bi-pencil"></i></button><button type="button" aria-label="Delete item"><i class="bi bi-trash"></i></button>';
        actions.children[0].onclick = (event) => { event.stopPropagation(); openNetWorthModal(type, item); };
        actions.children[1].onclick = (event) => { event.stopPropagation(); deleteNetWorthItem(item.id); };
        row.append(icon, copy, amount, actions);
        section.appendChild(row);
        if (history) section.appendChild(history);
        container.appendChild(section);
    });
}

function renderLiabilityPayments(item, historyId) {
    const history = document.createElement("div");
    history.id = historyId;
    history.className = "liability-payments";
    history.hidden = true;
    const payments = item.payment_history || [];
    if (!payments.length) {
        const empty = document.createElement("p");
        empty.className = "liability-payments-empty";
        empty.textContent = "No payments recorded yet.";
        history.appendChild(empty);
        return history;
    }
    const heading = document.createElement("div");
    heading.className = "liability-payment-head";
    heading.innerHTML = "<span>Payment date</span><span>Amount</span>";
    history.appendChild(heading);
    payments.forEach((payment) => {
        const row = document.createElement("div");
        row.className = "liability-payment-row";
        const paymentDate = document.createElement("time");
        paymentDate.dateTime = payment.date;
        paymentDate.textContent = formatWorkspacePeriodDate(payment.date);
        const amount = document.createElement("strong");
        amount.textContent = money.format(payment.amount);
        row.append(paymentDate, amount);
        history.appendChild(row);
    });
    return history;
}

function openNetWorthModal(type, item = null) {
    document.getElementById("netWorthItemId").value = item?.id || "";
    document.getElementById("netWorthItemType").value = type;
    document.getElementById("netWorthName").value = item?.name || "";
    document.getElementById("netWorthCategory").value = item?.category || "";
    document.getElementById("netWorthAmount").value = item?.amount ?? "";
    document.getElementById("netWorthModalTitle").textContent = `${item ? "Edit" : "Add"} ${type === "asset" ? "Asset" : "Liability"}`;
    document.getElementById("netWorthError").classList.add("d-none");
    bootstrap.Modal.getOrCreateInstance(document.getElementById("netWorthModal")).show();
}

async function saveNetWorthItem(event) {
    event.preventDefault();
    const id = document.getElementById("netWorthItemId").value;
    const payload = { item_type: document.getElementById("netWorthItemType").value, name: document.getElementById("netWorthName").value,
        category: document.getElementById("netWorthCategory").value, amount: Number(document.getElementById("netWorthAmount").value) };
    try {
        await api(id ? `/api/net-worth/${id}` : "/api/net-worth", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        bootstrap.Modal.getInstance(document.getElementById("netWorthModal")).hide();
        await loadNetWorth();
    } catch (error) {
        const alert = document.getElementById("netWorthError");
        alert.textContent = error.message;
        alert.classList.remove("d-none");
    }
}

async function deleteNetWorthItem(id) {
    if (!confirm("Delete this item?")) return;
    await api(`/api/net-worth/${id}`, { method: "DELETE" });
    await loadNetWorth();
}

function openWorkspaceSettings() {
    navigateTo("settings");
    document.getElementById("generalSettings").classList.add("show");
    document.getElementById("workspaceScheduleForm").scrollIntoView({ behavior: "smooth", block: "center" });
}


function formatWorkspacePeriodDate(value) {
    if (!value) return "";
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString([], { dateStyle: "medium" });
}

function workspacePeriodCaption(period) {
    if (!period?.start || !period?.end) return "Current workspace period: unavailable";
    return `Current workspace period: ${formatWorkspacePeriodDate(period.start)} – ${formatWorkspacePeriodDate(period.end)}`;
}

function setWorkspacePeriodCaption(text) {
    const caption = document.getElementById("workspacePeriodCaption");
    if (caption) caption.textContent = text;
}

function renderWorkspaceSchedule(schedule) {
    workspaceSchedule = schedule;
    const nextRun = new Date(schedule.next_run);
    document.getElementById("workspaceSaveDay").textContent = nextRun.toLocaleDateString([], { dateStyle: "long" });
    document.getElementById("workspaceSaveTime").textContent = nextRun.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    document.getElementById(schedule.mode === "monthly" ? "workspaceModeMonthly" : "workspaceModeInterval").checked = true;
    syncWorkspaceScheduleMode();
    document.getElementById("workspaceMonthlyDay").value = schedule.monthly_day;
    document.getElementById("workspaceIntervalValue").value = schedule.interval_value;
    document.getElementById("workspaceIntervalUnit").value = schedule.interval_unit;
    const [hours, minutes] = schedule.time_of_day.split(":");
    document.getElementById("workspaceTimeHours").value = hours;
    document.getElementById("workspaceTimeMinutes").value = minutes;
}

function syncWorkspaceScheduleMode() {
    const monthly = document.getElementById("workspaceModeMonthly").checked;
    document.getElementById("workspaceMonthlyFields").classList.toggle("d-none", !monthly);
    document.getElementById("workspaceIntervalFields").classList.toggle("d-none", monthly);
}

async function loadWorkspaceSchedule() {
    renderWorkspaceSchedule(await api("/api/workspace-schedule"));
}

async function saveWorkspaceSchedule(event) {
    event.preventDefault();
    const status = document.getElementById("workspaceScheduleStatus");
    try {
        const schedule = await api("/api/workspace-schedule", { method: "PUT", body: JSON.stringify({
            mode: document.querySelector('[name="workspaceScheduleMode"]:checked')?.value,
            monthly_day: Number(document.getElementById("workspaceMonthlyDay").value),
            interval_value: Number(document.getElementById("workspaceIntervalValue").value),
            interval_unit: document.getElementById("workspaceIntervalUnit").value,
            time_of_day: `${document.getElementById("workspaceTimeHours").value}:${document.getElementById("workspaceTimeMinutes").value}`,
        }) });
        renderWorkspaceSchedule(schedule);
        await loadDashboard();
        await initializeWorkspaceNavigation(true);
        status.textContent = "Saved.";
        status.className = "small ms-2 text-success";
    } catch (error) {
        status.textContent = error.message;
        status.className = "small ms-2 text-danger";
    }
}

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
    dashboardState.categories = orderCategories(dashboardState.categories);
    currentWorkspaceState = dashboardState;
    renderSummary(dashboardState.summary);
    renderCategories(dashboardState.categories);
    renderChart(dashboardState.categories);
    renderGlobalBalance(dashboardState.global_balance);
}

function renderGlobalBalance(state) {
    if (!state) return;
    const deficit = state.balance < 0;
    const amount = document.getElementById("globalBalanceAmount");
    amount.textContent = money.format(Math.abs(state.balance));
    amount.classList.toggle("text-danger", deficit);
    amount.classList.toggle("text-success", !deficit);
    document.getElementById("globalBalancePanel").classList.toggle("is-deficit", deficit);
    document.getElementById("globalBalancePanel").classList.toggle("is-surplus", !deficit);
    document.getElementById("globalDeficitAction").classList.toggle("d-none", !deficit);
    document.getElementById("globalSurplusAction").classList.toggle("d-none", deficit);
    document.getElementById("globalBalanceCaption").textContent = deficit
        ? "Global deficit · current income will help bring this back to zero"
        : "Available surplus carried from past financial reports";
    document.getElementById("globalPledgeAmount").value = state.pledge || "";
    document.getElementById("globalPledgeButtonLabel").textContent = state.pledge ? "Update pledge" : "Make pledge";
    document.getElementById("globalPledgeHint").textContent = state.pledge
        ? `${money.format(state.pledge)} is pledged this period. Updating it will revise the highlighted Savings expense.`
        : "Earmark unallocated income as Savings. You can revise this pledge at any time.";
}

async function saveGlobalPledge(event) {
    event.preventDefault();
    await submitGlobalAction("/api/global-balance/pledge", { amount: parseFloat(document.getElementById("globalPledgeAmount").value) });
}

async function drawGlobalSurplus(event) {
    event.preventDefault();
    await submitGlobalAction("/api/global-balance/draw", {
        description: document.getElementById("globalDrawDescription").value.trim(),
        category: document.getElementById("globalDrawCategory").value,
        amount: parseFloat(document.getElementById("globalDrawAmount").value),
    });
}

async function submitGlobalAction(path, payload) {
    const error = document.getElementById("globalBalanceError");
    error.classList.add("d-none");
    try {
        await api(path, { method: "POST", body: JSON.stringify(payload) });
        await loadDashboard();
        await loadLiabilityAutocomplete();
        document.getElementById("globalDrawDescription").value = "";
        document.getElementById("globalDrawCategory").value = "";
        document.getElementById("globalDrawAmount").value = "";
    } catch (err) {
        showExpenseSubmissionError(err, error);
    }
}

function scorecardDashboard(scorecard) {
    const hasIncomeSnapshot = Boolean(scorecard.income_snapshot_present);
    const currentMonth = currentWorkspaceState?.month || {};
    const income = hasIncomeSnapshot ? Number(scorecard.income) || 0 : Number(currentWorkspaceState?.summary?.income) || 0;
    const spending = Number(scorecard.total_spending) || 0;
    const category = (id) => scorecard.categories.find((item) => item.id === id)?.total || 0;
    const rate = (amount) => income > 0 ? (Number(amount) / income) * 100 : 0;
    return {
        month: {
            income_period_duration: hasIncomeSnapshot ? scorecard.income_period_duration || 1 : currentMonth.income_period_duration || 1,
            income_period_unit: hasIncomeSnapshot ? scorecard.income_period_unit || "month" : currentMonth.income_period_unit || "month",
        },
        summary: {
            income, spending, surplus: income - spending,
            recurring_total: scorecard.expenses.filter((expense) => expense.recurring).reduce((sum, expense) => sum + Number(expense.amount), 0),
            savings_rate: rate(category("savings")), investment_rate: rate(category("investments")),
        },
        categories: scorecard.categories,
        expenses: scorecard.expenses,
    };
}

async function initializeWorkspaceNavigation(forceCurrent = false) {
    const scorecards = await api("/api/scorecards");
    workspaceTimeline = [...scorecards].reverse().map((scorecard) => ({ id: scorecard.id, label: scorecard.name }));
    workspaceTimeline.push({ id: null, label: "Current" });
    if (forceCurrent || workspaceIndex >= workspaceTimeline.length) workspaceIndex = workspaceTimeline.length - 1;
    await displayWorkspace(workspaceIndex);
}

async function navigateWorkspace(direction) {
    const nextIndex = Math.min(Math.max(workspaceIndex + direction, 0), workspaceTimeline.length - 1);
    if (nextIndex === workspaceIndex) return;
    await displayWorkspace(nextIndex);
}

async function displayWorkspace(index) {
    workspaceIndex = index;
    const selection = workspaceTimeline[index];
    const historical = selection.id !== null;
    if (historical) {
        const scorecard = await api(`/api/scorecards/${selection.id}`);
        dashboardState = scorecardDashboard(scorecard);
        renderSummary(dashboardState.summary);
        renderCategories(dashboardState.categories);
        renderChart(dashboardState.categories);
        document.getElementById("budgetViewCaption").textContent = `${scorecard.start_date} – ${scorecard.end_date} saved scorecard.`;
        setWorkspacePeriodCaption(`Saved report period: ${formatWorkspacePeriodDate(scorecard.start_date)} – ${formatWorkspacePeriodDate(scorecard.end_date)}`);
    } else {
        dashboardState = currentWorkspaceState || await api("/api/dashboard");
        currentWorkspaceState = dashboardState;
        renderSummary(dashboardState.summary);
        renderCategories(dashboardState.categories);
        renderChart(dashboardState.categories);
        document.getElementById("budgetViewCaption").textContent = "Your active, unsaved workspace.";
        setWorkspacePeriodCaption(workspacePeriodCaption(dashboardState.workspace_period));
    }
    document.getElementById("workspaceLabel").textContent = selection.label;
    document.getElementById("previousWorkspace").disabled = index === 0;
    document.getElementById("nextWorkspace").disabled = index === workspaceTimeline.length - 1;
    document.getElementById("addExpenseButton").disabled = historical;
    document.getElementById("viewRecurringButton").disabled = historical;
    document.querySelectorAll("#categoryCards .category-row").forEach((button) => button.disabled = historical);
}

async function initializeDashboard() {
    await loadWorkspaceSchedule();
    await loadDashboard();
    await loadLiabilityAutocomplete();
    await initializeWorkspaceNavigation(true);
}

function renderSummary(summary) {
    document.getElementById("income").textContent = money.format(summary.income);
    if (dashboardState.month) {
        const duration = dashboardState.month.income_period_duration || 1;
        const unit = dashboardState.month.income_period_unit || "month";
        document.getElementById("incomePeriod").textContent = `every ${formatDuration(duration, unit)}`;
    }
    document.getElementById("spending").textContent = money.format(summary.spending);
    document.getElementById("recurringTotal").textContent = money.format(summary.recurring_total);

    const surplus = document.getElementById("surplus");
    surplus.textContent = money.format(summary.surplus);
    surplus.classList.toggle("text-success", summary.surplus >= 0);
    surplus.classList.toggle("text-danger", summary.surplus < 0);
    const income = Number(summary.income) || 0;
    const spending = Number(summary.spending) || 0;
    const usedPercent = income > 0 ? (spending / income) * 100 : 0;
    const surplusPercent = income > 0 ? (summary.surplus / income) * 100 : 0;
    document.getElementById("surplusCaption").textContent = `${surplusPercent.toFixed(1)}% of income`;
    document.getElementById("incomeUsedPercent").textContent = `${usedPercent.toFixed(1)}%`;
    document.getElementById("incomeUsedCaption").textContent = income > 0 ? "of income spent" : "add income to begin";
    const usageBar = document.getElementById("incomeUsedBar");
    usageBar.style.width = `${Math.min(Math.max(usedPercent, 0), 100)}%`;
    usageBar.classList.toggle("over-budget", usedPercent > 100);
}

function renderCategories(categories) {
    const income = Number(dashboardState.summary.income) || 0;
    categories.forEach((category) => {
        const percentage = income > 0 ? (Number(category.total) / income) * 100 : 0;
        document.getElementById(`${category.id}-total`).textContent = money.format(category.total);
        document.getElementById(`${category.id}-count`).textContent = category.count;
        document.getElementById(`${category.id}-caption`).textContent = `${category.count} expense${category.count === 1 ? "" : "s"}`;
        document.getElementById(`${category.id}-percent`).textContent = `${percentage.toFixed(1)}%`;
    });
    renderCategoryLegend(categories, income);
}

function renderCategoryLegend(categories, income) {
    document.getElementById("categoryLegend").innerHTML = categories.map((category) => {
        const percentage = income > 0 ? (Number(category.total) / income) * 100 : 0;
        return `<div><span class="legend-dot" style="background:${category.color}"></span><span>${escapeHtml(category.label)}</span><strong>${money.format(category.total)} <small>(${percentage.toFixed(1)}%)</small></strong></div>`;
    }).join("");
}

function renderChart(categories) {
    const ctx = document.getElementById("categoryChart");
    const data = categories.map((category) => category.total);
    const labels = categories.map((category) => category.label);
    const colors = categories.map((category) => category.color);

    if (categoryChart) {
        categoryChart.data.labels = labels;
        categoryChart.data.datasets[0].data = data;
        categoryChart.data.datasets[0].backgroundColor = colors;
        categoryChart.update();
        return;
    }

    const centerLabel = {
        id: "centerLabel",
        afterDraw(chart) {
            const { ctx: context, chartArea } = chart;
            if (!chartArea) return;
            const total = chart.data.datasets[0].data.reduce((sum, value) => sum + Number(value || 0), 0);
            context.save();
            context.textAlign = "center";
            context.textBaseline = "middle";
            context.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim();
            context.font = "700 18px Inter, sans-serif";
            context.fillText(money.format(total), (chartArea.left + chartArea.right) / 2, (chartArea.top + chartArea.bottom) / 2 - 6);
            context.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--muted").trim();
            context.font = "12px Inter, sans-serif";
            context.fillText("Total Expenses", (chartArea.left + chartArea.right) / 2, (chartArea.top + chartArea.bottom) / 2 + 14);
            context.restore();
        },
    };
    categoryChart = new Chart(ctx, {
        type: "doughnut",
        data: { labels, datasets: [{ data, backgroundColor: colors }] },
        plugins: [centerLabel],
        options: { responsive: true, maintainAspectRatio: true, aspectRatio: 1, plugins: { legend: { display: false } }, cutout: "62%" },
    });
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
}

let taxRulesets = [];

const provinces = { AB: "Alberta", BC: "British Columbia", MB: "Manitoba", NB: "New Brunswick", NL: "Newfoundland and Labrador", NS: "Nova Scotia", ON: "Ontario", PE: "Prince Edward Island", QC: "Quebec", SK: "Saskatchewan" };

function formatDuration(duration, unit) {
    const rounded = Number(duration) % 1 === 0 ? Number(duration).toFixed(0) : Number(duration).toString();
    return `${rounded} ${unit}${Number(duration) === 1 ? "" : "s"}`;
}

function selectedIncomeMode() {
    return document.querySelector('input[name="incomeMode"]:checked').value;
}

async function initializeIncomeEditor() {
    if (incomeEditorLoaded) return;
    incomeEditorLoaded = true;
    document.querySelectorAll('input[name="incomeMode"]').forEach((input) => input.addEventListener("change", syncIncomeMode));
    ["takeHomeIncome", "manualTaxRate", "grossAnnualIncome", "incomePeriodDuration", "incomePeriodUnit"].forEach((id) => document.getElementById(id).addEventListener("input", updateIncomePreview));
    const profile = await api("/api/income");
    document.getElementById(profile.income_mode === "gross_tax" ? "incomeModeGross" : "incomeModeSimple").checked = true;
    document.getElementById("takeHomeIncome").value = profile.income || 0;
    document.getElementById("manualTaxRate").value = profile.manual_tax_rate || 0;
    document.getElementById("incomePeriodDuration").value = profile.income_period_duration || 1;
    document.getElementById("incomePeriodUnit").value = profile.income_period_unit || "month";
    document.getElementById("grossAnnualIncome").value = profile.gross_annual_income || "";
    taxRulesets = await api("/api/tax-rulesets");
    renderIncomeTaxSelectors(profile.tax_country || "Canada", profile.tax_region_code || "ON", profile.tax_year || 2026);
    renderTaxRulesetSelectors();
    syncIncomeMode();
}

function openIncomeModal() { navigateTo("income"); }

function renderIncomeTaxSelectors(preferredCountry, preferredRegion, preferredYear) {
    const countrySelect = document.getElementById("taxCountry");
    const regionSelect = document.getElementById("taxProvince");
    const yearSelect = document.getElementById("taxYear");
    const countries = [...new Set(taxRulesets.map((ruleset) => ruleset.country))].sort();
    countrySelect.innerHTML = countries.map((country) => `<option value="${escapeHtml(country)}">${escapeHtml(country)}</option>`).join("");
    countrySelect.value = countries.includes(preferredCountry) ? preferredCountry : countries[0] || "";

    const syncRegions = (requestedRegion = regionSelect.value || preferredRegion) => {
        const regionalRules = taxRulesets.filter((ruleset) => ruleset.country === countrySelect.value && ruleset.region_code !== "FED");
        const uniqueRegions = [...new Map(regionalRules.map((ruleset) => [ruleset.region_code, ruleset])).values()];
        regionSelect.innerHTML = `<option value="FED">Federal only</option>${uniqueRegions.map((ruleset) => `<option value="${escapeHtml(ruleset.region_code)}">${escapeHtml(ruleset.region_name)}</option>`).join("")}`;
        regionSelect.value = ["FED", ...uniqueRegions.map((ruleset) => ruleset.region_code)].includes(requestedRegion) ? requestedRegion : "FED";
        syncYears(preferredYear);
    };
    const syncYears = (requestedYear = yearSelect.value || preferredYear) => {
        const years = [...new Set(taxRulesets.filter((ruleset) => ruleset.country === countrySelect.value && ["FED", regionSelect.value].includes(ruleset.region_code)).map((ruleset) => Number(ruleset.tax_year)))].sort((a, b) => b - a);
        yearSelect.innerHTML = years.map((year) => `<option value="${year}">${year}</option>`).join("");
        yearSelect.value = years.includes(Number(requestedYear)) ? String(requestedYear) : String(years[0] || "");
        updateIncomePreview();
    };
    countrySelect.onchange = () => syncRegions("FED");
    regionSelect.onchange = () => syncYears();
    yearSelect.onchange = updateIncomePreview;
    syncRegions(preferredRegion);
}

function syncIncomeMode() {
    document.getElementById("simpleIncomeFields").classList.toggle("d-none", selectedIncomeMode() !== "simple");
    document.getElementById("grossIncomeFields").classList.toggle("d-none", selectedIncomeMode() !== "gross_tax");
    document.getElementById("grossTaxBreakdown").classList.toggle("d-none", selectedIncomeMode() !== "gross_tax");
    updateIncomePreview();
}

function updateIncomePreview() {
    let preview = 0;
    if (selectedIncomeMode() === "simple") {
        const amount = parseFloat(document.getElementById("takeHomeIncome").value) || 0;
        const rate = parseFloat(document.getElementById("manualTaxRate").value) || 0;
        preview = amount * (1 - rate / 100);
    } else {
        const gross = parseFloat(document.getElementById("grossAnnualIncome").value) || 0;
        const duration = parseFloat(document.getElementById("incomePeriodDuration").value) || 1;
        const unit = document.getElementById("incomePeriodUnit").value;
        const year = parseInt(document.getElementById("taxYear").value, 10) || 2026;
        const regionCode = document.getElementById("taxProvince").value;
        const country = document.getElementById("taxCountry").value;
        const federal = findRuleset(country, "FED", year);
        const provincial = regionCode === "FED" ? null : findRuleset(country, regionCode, year);
        const federalTax = calculateRulesetTax(gross, federal);
        const regionalTax = calculateRulesetTax(gross, provincial);
        const tax = federalTax.taxOwed + regionalTax.taxOwed;
        preview = (gross - tax) / (({ day: 365, week: 52, month: 12, year: 1 }[unit] || 12) / duration);
        renderGrossTaxBreakdown(gross, federalTax, regionalTax, provincial, gross - tax, preview, duration, unit);
    }
    document.getElementById("incomePreview").textContent = money.format(preview);
}

function calculateRulesetTax(income, ruleset) {
    const configuredAmount = ruleset?.basic_personal_credit_enabled ? (parseFloat(ruleset.basic_personal_credit_amount) || 0) : 0;
    const personalAmount = Math.min(income, configuredAmount);
    const taxableIncome = Math.max(income - personalAmount, 0);
    return { personalAmount, taxableIncome, taxOwed: calculateTax(taxableIncome, ruleset?.brackets || []) };
}

function renderGrossTaxBreakdown(gross, federal, regional, regionalRuleset, annualTakeHome, periodTakeHome, duration, unit) {
    const personalAmountRow = (label, amount) => amount > 0 ? `<div class="d-flex justify-content-between text-success"><span>${label} basic personal amount</span><span>−${money.format(amount)}</span></div>` : "";
    const taxRows = (label, values) => `<div class="mt-2 small text-muted fw-semibold">${label}</div>${personalAmountRow(label, values.personalAmount)}<div class="d-flex justify-content-between"><span>${label} taxable income</span><span>${money.format(values.taxableIncome)}</span></div><div class="d-flex justify-content-between fw-semibold"><span>${label} tax owed</span><span>${money.format(values.taxOwed)}</span></div>`;
    document.getElementById("grossTaxBreakdown").innerHTML = `
        <div class="tax-invoice border rounded p-3 mt-2">
            <div class="d-flex justify-content-between fw-semibold mb-2"><span>Annual gross income</span><span>${money.format(gross)}</span></div>
            ${taxRows("Federal", federal)}
            ${regionalRuleset ? taxRows(escapeHtml(regionalRuleset.region_name), regional) : ""}
            <hr class="my-2">
            <div class="d-flex justify-content-between"><span>Annual take-home pay</span><strong>${money.format(annualTakeHome)}</strong></div>
            <div class="d-flex justify-content-between fs-5 mt-2"><strong>Take-home every ${formatDuration(duration, unit)}</strong><strong>${money.format(periodTakeHome)}</strong></div>
        </div>`;
}

function findRuleset(country, regionCode, taxYear) {
    return taxRulesets.find((ruleset) => ruleset.country === country && ruleset.region_code === regionCode && Number(ruleset.tax_year) === Number(taxYear));
}

function calculateTax(income, brackets) {
    return brackets.reduce((total, bracket) => {
        const lower = parseFloat(bracket.lower_bound) || 0;
        const upper = bracket.upper_bound === null || bracket.upper_bound === "" ? null : parseFloat(bracket.upper_bound);
        if (income <= lower) return total;
        const taxable = (upper === null ? income : Math.min(income, upper)) - lower;
        return total + taxable * ((parseFloat(bracket.rate) || 0) / 100);
    }, 0);
}

async function saveIncomeProfile() {
    const payload = {
        mode: selectedIncomeMode(),
        take_home_income: parseFloat(document.getElementById("takeHomeIncome").value) || 0,
        manual_tax_rate: parseFloat(document.getElementById("manualTaxRate").value) || 0,
        country: document.getElementById("taxCountry").value,
        region_code: document.getElementById("taxProvince").value,
        tax_year: parseInt(document.getElementById("taxYear").value, 10) || 2026,
        gross_annual_income: parseFloat(document.getElementById("grossAnnualIncome").value) || 0,
        period_duration: parseFloat(document.getElementById("incomePeriodDuration").value) || 1,
        period_unit: document.getElementById("incomePeriodUnit").value,
    };
    try {
        await api("/api/income", { method: "POST", body: JSON.stringify(payload) });
        await loadDashboard();
        navigateTo("budget");
    } catch (err) {
        document.getElementById("incomeError").textContent = err.message;
        document.getElementById("incomeError").classList.remove("d-none");
    }
}

function renderTaxRulesetSelectors() {
    const countrySelect = document.getElementById("rulesetCountry");
    const regionSelect = document.getElementById("rulesetRegion");
    const yearSelect = document.getElementById("rulesetYear");
    if (!countrySelect || !regionSelect || !yearSelect) return;

    const countries = [...new Set(taxRulesets.map((ruleset) => ruleset.country))];
    countrySelect.innerHTML = countries.map((country) => `<option value="${escapeHtml(country)}">${escapeHtml(country)}</option>`).join("");
    countrySelect.value = countrySelect.value || "Canada";

    const syncRegions = () => {
        const selectedCountry = countrySelect.value;
        const regions = taxRulesets.filter((ruleset) => ruleset.country === selectedCountry && ruleset.region_code !== "FED");
        regionSelect.innerHTML = regions.map((ruleset) => `<option value="${escapeHtml(ruleset.region_code)}">${escapeHtml(ruleset.region_name)}</option>`).join("");
        if (!regionSelect.value) regionSelect.value = document.getElementById("taxProvince").value || "ON";
        syncYears();
    };

    const syncYears = () => {
        const selectedCountry = countrySelect.value;
        const selectedRegion = regionSelect.value;
        const years = [...new Set(taxRulesets.filter((ruleset) => ruleset.country === selectedCountry && [selectedRegion, "FED"].includes(ruleset.region_code)).map((ruleset) => ruleset.tax_year))].sort((a, b) => b - a);
        yearSelect.innerHTML = years.map((year) => `<option value="${year}">${year}</option>`).join("");
        if (!yearSelect.value) yearSelect.value = document.getElementById("taxYear").value || years[0] || 2026;
        renderTaxRulesetDetail();
    };

    countrySelect.onchange = syncRegions;
    regionSelect.onchange = syncYears;
    yearSelect.onchange = renderTaxRulesetDetail;
    syncRegions();
}

function renderTaxRulesetDetail() {
    const country = document.getElementById("rulesetCountry").value;
    const regionCode = document.getElementById("rulesetRegion").value;
    const year = parseInt(document.getElementById("rulesetYear").value, 10);
    const rulesets = [findRuleset(country, "FED", year), findRuleset(country, regionCode, year)].filter(Boolean);
    const detail = document.getElementById("taxRulesDetail");
    detail.innerHTML = rulesets.map((ruleset) => `
        <div class="border rounded p-3 mb-3" data-ruleset-id="${ruleset.id}">
            <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
                <strong>${escapeHtml(ruleset.region_name)} (${ruleset.region_code}) ${ruleset.tax_year}</strong>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteTaxRuleset(${ruleset.id})">Delete ruleset</button>
            </div>
            <div class="border rounded p-2 mb-3">
                <div class="form-check form-switch"><input id="ruleset-credit-enabled-${ruleset.id}" class="form-check-input" type="checkbox" ${ruleset.basic_personal_credit_enabled ? "checked" : ""} onchange="syncDisplayedCredit(${ruleset.id})"><label class="form-check-label" for="ruleset-credit-enabled-${ruleset.id}">Apply basic personal amount</label></div>
                <div id="ruleset-credit-group-${ruleset.id}" class="mt-2 ${ruleset.basic_personal_credit_enabled ? "" : "d-none"}"><label class="form-label small" for="ruleset-credit-amount-${ruleset.id}">Annual basic personal amount</label><div class="input-group input-group-sm"><span class="input-group-text">$</span><input id="ruleset-credit-amount-${ruleset.id}" class="form-control" type="number" min="0" step="0.01" value="${ruleset.basic_personal_credit_amount || 0}"></div><div class="form-text">Deducted from gross income before this ruleset's tax brackets are applied.</div></div>
            </div>
            <div class="table-responsive"><table class="table table-sm align-middle mb-2"><thead><tr><th>From</th><th>Up to</th><th>Tax rate %</th><th></th></tr></thead><tbody id="ruleset-${ruleset.id}">
                ${ruleset.brackets.map((bracket) => taxBracketRow(ruleset.id, bracket)).join("")}
            </tbody></table></div>
            <div class="d-flex gap-2"><button class="btn btn-sm btn-outline-secondary" onclick="addTaxBracketRow(${ruleset.id})">Add bracket</button><button class="btn btn-sm btn-outline-primary" onclick="saveDisplayedTaxRuleset(${ruleset.id})">Save ${escapeHtml(ruleset.region_name)}</button></div>
        </div>`).join("");
}

function syncDisplayedCredit(id) {
    document.getElementById(`ruleset-credit-group-${id}`).classList.toggle("d-none", !document.getElementById(`ruleset-credit-enabled-${id}`).checked);
}

function taxBracketRow(rulesetId, bracket = { lower_bound: 0, upper_bound: "", rate: 0 }) {
    return `<tr><td><input class="form-control form-control-sm bracket-from" type="number" min="0" step="0.01" value="${bracket.lower_bound ?? 0}"></td><td><input class="form-control form-control-sm bracket-up-to" type="number" min="0" step="0.01" placeholder="No limit" value="${bracket.upper_bound ?? ""}"></td><td><input class="form-control form-control-sm bracket-rate" type="number" min="0" step="0.01" value="${bracket.rate ?? 0}"></td><td class="text-end"><button class="btn btn-sm btn-outline-danger" onclick="this.closest('tr').remove()">Remove</button></td></tr>`;
}

function addTaxBracketRow(rulesetId) {
    document.getElementById(`ruleset-${rulesetId}`).insertAdjacentHTML("beforeend", taxBracketRow(rulesetId));
}

function parseDisplayedBrackets(id) {
    return [...document.querySelectorAll(`#ruleset-${id} tr`)].map((row) => ({
        lower_bound: parseFloat(row.querySelector(".bracket-from").value) || 0,
        upper_bound: row.querySelector(".bracket-up-to").value === "" ? null : parseFloat(row.querySelector(".bracket-up-to").value),
        rate: parseFloat(row.querySelector(".bracket-rate").value) || 0,
    }));
}

async function saveDisplayedTaxRuleset(id) {
    const ruleset = taxRulesets.find((item) => item.id === id);
    ruleset.basic_personal_credit_enabled = document.getElementById(`ruleset-credit-enabled-${id}`).checked;
    ruleset.basic_personal_credit_amount = parseFloat(document.getElementById(`ruleset-credit-amount-${id}`).value) || 0;
    const selectedIncomeRules = [document.getElementById("taxCountry").value, document.getElementById("taxProvince").value, document.getElementById("taxYear").value];
    await api(`/api/tax-rulesets/${id}`, { method: "PUT", body: JSON.stringify({ ...ruleset, brackets: parseDisplayedBrackets(id) }) });
    taxRulesets = await api("/api/tax-rulesets");
    await initializeTfsaCalculator();
    renderIncomeTaxSelectors(...selectedIncomeRules);
    renderTaxRulesetSelectors();
    updateIncomePreview();
}

async function deleteTaxRuleset(id) {
    if (!confirm("Delete this tax ruleset?")) return;
    const selectedIncomeRules = [document.getElementById("taxCountry").value, document.getElementById("taxProvince").value, document.getElementById("taxYear").value];
    await api(`/api/tax-rulesets/${id}`, { method: "DELETE" });
    taxRulesets = await api("/api/tax-rulesets");
    await initializeTfsaCalculator();
    renderIncomeTaxSelectors(...selectedIncomeRules);
    renderTaxRulesetSelectors();
    updateIncomePreview();
}

function showNewTaxRulesetForm() {
    document.getElementById("taxRulesBrowser").classList.add("d-none");
    document.getElementById("newTaxRulesetForm").classList.remove("d-none");
    document.getElementById("newRulesetRegion").innerHTML = Object.entries(provinces)
        .map(([code, name]) => `<option value="${code}">${escapeHtml(name)}</option>`).join("");
    document.getElementById("newRulesetType").value = "federal";
    document.getElementById("newRulesetName").value = "Federal";
    document.getElementById("newRulesetCountry").value = document.getElementById("rulesetCountry").value || "Canada";
    document.getElementById("newRulesetRegion").value = document.getElementById("rulesetRegion").value || "ON";
    document.getElementById("newRulesetYear").value = document.getElementById("rulesetYear").value || new Date().getFullYear();
    document.getElementById("ruleset-new").innerHTML = taxBracketRow("new");
    document.getElementById("newRulesetCreditEnabled").checked = false;
    document.getElementById("newRulesetCreditAmount").value = 0;
    document.getElementById("newRulesetCreditEnabled").onchange = syncNewRulesetCredit;
    ["newRulesetType", "newRulesetCountry", "newRulesetRegion", "newRulesetYear"].forEach((id) => {
        document.getElementById(id).oninput = syncNewTaxRulesetForm;
    });
    syncNewTaxRulesetForm();
}

function syncNewRulesetCredit() {
    document.getElementById("newRulesetCreditAmountGroup").classList.toggle("d-none", !document.getElementById("newRulesetCreditEnabled").checked);
}

function cancelNewTaxRuleset() {
    document.getElementById("newTaxRulesetForm").classList.add("d-none");
    document.getElementById("taxRulesBrowser").classList.remove("d-none");
}

function newRulesetIdentity() {
    const federal = document.getElementById("newRulesetType").value === "federal";
    return {
        country: document.getElementById("newRulesetCountry").value.trim(),
        regionCode: federal ? "FED" : document.getElementById("newRulesetRegion").value,
        taxYear: parseInt(document.getElementById("newRulesetYear").value, 10),
    };
}

function syncNewTaxRulesetForm() {
    const federal = document.getElementById("newRulesetType").value === "federal";
    document.getElementById("newRulesetRegionGroup").classList.toggle("d-none", federal);
    const identity = newRulesetIdentity();
    const existing = findRuleset(identity.country, identity.regionCode, identity.taxYear);
    const warning = document.getElementById("newRulesetWarning");
    warning.classList.toggle("d-none", !existing);
    warning.textContent = existing
        ? `A ${federal ? "federal" : "provincial/regional"} ruleset already exists for ${identity.country}, ${existing.region_name}, ${identity.taxYear}. Saving will overwrite the current ruleset.`
        : "";
}

async function saveNewTaxRuleset() {
    const identity = newRulesetIdentity();
    const name = document.getElementById("newRulesetName").value.trim();
    const error = document.getElementById("newRulesetError");
    error.classList.add("d-none");
    if (!name || !identity.country || !identity.taxYear) {
        error.textContent = "Enter a ruleset name, country, and valid tax year.";
        error.classList.remove("d-none");
        return;
    }
    const payload = {
        country: identity.country,
        region_name: name,
        region_code: identity.regionCode,
        tax_year: identity.taxYear,
        basic_personal_credit_enabled: document.getElementById("newRulesetCreditEnabled").checked,
        basic_personal_credit_amount: parseFloat(document.getElementById("newRulesetCreditAmount").value) || 0,
        brackets: parseDisplayedBrackets("new"),
    };
    try {
        await api("/api/tax-rulesets", { method: "POST", body: JSON.stringify(payload) });
        taxRulesets = await api("/api/tax-rulesets");
        await initializeTfsaCalculator();
        renderIncomeTaxSelectors(identity.country, identity.regionCode, identity.taxYear);
        cancelNewTaxRuleset();
        renderTaxRulesetSelectors();
        document.getElementById("rulesetCountry").value = identity.country;
        document.getElementById("rulesetCountry").dispatchEvent(new Event("change"));
        if (identity.regionCode !== "FED") document.getElementById("rulesetRegion").value = identity.regionCode;
        document.getElementById("rulesetRegion").dispatchEvent(new Event("change"));
        document.getElementById("rulesetYear").value = String(identity.taxYear);
        renderTaxRulesetDetail();
        updateIncomePreview();
    } catch (err) {
        error.textContent = err.message;
        error.classList.remove("d-none");
    }
}

async function showCategory(categoryId) {
    selectedCategory = categoryId;
    const category = window.CATEGORY_CONFIG[categoryId];
    document.getElementById("categoryTitle").textContent = category.label;
    await refreshCategory();
    new bootstrap.Modal(document.getElementById("categoryModal")).show();
}

function openAddExpenseModal() {
    resetQuickExpenseForm();
    document.getElementById("expenseSearch").value = "";
    document.getElementById("expenseSort").value = "date";
    visibleExpenseLimit = 5;
    renderExpenseManager();
    new bootstrap.Modal(document.getElementById("addExpenseModal")).show();
}

function localToday() {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
}

function resetQuickExpenseForm() {
    document.getElementById("quickExpenseForm").reset();
    document.getElementById("quickExpenseId").value = "";
    document.getElementById("quickExpenseDate").value = localToday();
    document.getElementById("quickExpenseRecurrenceInterval").value = 1;
    document.getElementById("quickExpenseRecurrenceUnit").value = "month";
    syncRecurrenceFields("quickExpense");
    document.getElementById("quickExpenseSubmit").querySelector("span").textContent = "Add Expense";
    document.getElementById("quickExpenseError").classList.add("d-none");
}

async function submitQuickExpense(event) {
    event.preventDefault();
    const form = document.getElementById("quickExpenseForm");
    if (!form.reportValidity()) return;
    const id = document.getElementById("quickExpenseId").value;
    const payload = {
        description: document.getElementById("quickExpenseDescription").value.trim(),
        category: document.getElementById("quickExpenseCategory").value,
        amount: parseFloat(document.getElementById("quickExpenseAmount").value),
        expense_date: document.getElementById("quickExpenseDate").value,
        recurring: document.getElementById("quickExpenseRecurring").checked,
        recurrence_interval: parseInt(document.getElementById("quickExpenseRecurrenceInterval").value, 10) || 1,
        recurrence_unit: document.getElementById("quickExpenseRecurrenceUnit").value,
    };
    try {
        await api(id ? `/api/expenses/${id}` : "/api/expenses", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        await loadDashboard();
        await loadLiabilityAutocomplete();
        resetQuickExpenseForm();
        renderExpenseManager();
        renderRecurringExpensesPage();
        document.getElementById("quickExpenseDescription").focus();
    } catch (err) {
        const error = document.getElementById("quickExpenseError");
        showExpenseSubmissionError(err, error);
    }
}

function handleExpenseSearch() {
    visibleExpenseLimit = 5;
    renderExpenseManager();
}

function sortedManagerExpenses() {
    const prefix = document.getElementById("expenseSearch").value.trim().toLocaleLowerCase();
    const sort = document.getElementById("expenseSort").value;
    const expenses = dashboardState.expenses.filter((expense) => expense.description.toLocaleLowerCase().startsWith(prefix));
    const byDescription = (a, b) => a.description.localeCompare(b.description, undefined, { sensitivity: "base" });
    if (sort === "description") expenses.sort(byDescription);
    else if (sort === "category") expenses.sort((a, b) => (window.CATEGORY_CONFIG[a.category]?.label || a.category).localeCompare(window.CATEGORY_CONFIG[b.category]?.label || b.category) || byDescription(a, b));
    else if (sort === "amount") expenses.sort((a, b) => Number(b.amount) - Number(a.amount) || byDescription(a, b));
    else expenses.sort((a, b) => (b.expense_date || "").localeCompare(a.expense_date || "") || byDescription(a, b));
    return expenses;
}

function formatExpenseDate(value) {
    if (!value) return "—";
    const [year, month, day] = value.split("-").map(Number);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(year, month - 1, day));
}

function expenseDescription(expense) {
    const marker = expense.global_type === "draw"
        ? '<i class="bi bi-globe2 global-surplus-marker" aria-label="Allocated from global surplus" title="Allocated from global surplus"></i>'
        : "";
    return `${escapeHtml(expense.description)}${marker}`;
}

function renderGlobalSurplusCaption(element, expenses) {
    const hasGlobalDraw = expenses.some((expense) => expense.global_type === "draw");
    element.innerHTML = hasGlobalDraw
        ? '<i class="bi bi-globe2 global-surplus-marker"></i> Expenses marked with the globe icon came from global surplus, not income in this workspace period.'
        : "";
    element.classList.toggle("d-none", !hasGlobalDraw);
}

function syncRecurrenceFields(prefix) {
    const recurring = document.getElementById(`${prefix}Recurring`).checked;
    document.getElementById(`${prefix}RecurrenceFields`).classList.toggle("d-none", !recurring);
}

function recurrenceLabel(expense) {
    if (!expense.recurring) return "—";
    const interval = Number(expense.recurrence_interval) || 1;
    const unit = expense.recurrence_unit || "month";
    return `Every ${interval} ${unit}${interval === 1 ? "" : "s"}`;
}

function openRecurringExpensesModal() {
    navigateTo("recurring");
}

function resetRecurringExpenseForm() {
    document.getElementById("recurringExpenseForm").reset();
    document.getElementById("recurringExpenseDate").value = localToday();
    document.getElementById("recurringExpenseRecurring").checked = true;
    document.getElementById("recurringExpenseRecurrenceInterval").value = 1;
    document.getElementById("recurringExpenseRecurrenceUnit").value = "month";
    document.getElementById("recurringExpenseError").classList.add("d-none");
}

async function submitRecurringExpense(event) {
    event.preventDefault();
    const form = document.getElementById("recurringExpenseForm");
    if (!form.reportValidity()) return;
    const payload = {
        description: document.getElementById("recurringExpenseDescription").value.trim(),
        category: document.getElementById("recurringExpenseCategory").value,
        amount: parseFloat(document.getElementById("recurringExpenseAmount").value),
        expense_date: document.getElementById("recurringExpenseDate").value,
        recurring: true,
        recurrence_interval: parseInt(document.getElementById("recurringExpenseRecurrenceInterval").value, 10) || 1,
        recurrence_unit: document.getElementById("recurringExpenseRecurrenceUnit").value,
    };
    try {
        await api("/api/expenses", { method: "POST", body: JSON.stringify(payload) });
        await loadDashboard();
        await loadLiabilityAutocomplete();
        resetRecurringExpenseForm();
        renderRecurringExpensesPage();
        document.getElementById("recurringExpenseDescription").focus();
    } catch (err) {
        showExpenseSubmissionError(err, document.getElementById("recurringExpenseError"));
    }
}

function handleRecurringExpenseSearch() {
    visibleRecurringExpenseLimit = 5;
    renderRecurringExpensesPage();
}

function sortedRecurringExpenses() {
    const prefix = document.getElementById("recurringExpenseSearch").value.trim().toLocaleLowerCase();
    const sort = document.getElementById("recurringExpenseSort").value;
    const expenses = (currentWorkspaceState?.recurring_expenses || currentWorkspaceState?.expenses || []).filter((expense) => expense.recurring && expense.description.toLocaleLowerCase().startsWith(prefix));
    const byDescription = (a, b) => a.description.localeCompare(b.description, undefined, { sensitivity: "base" });
    if (sort === "description") expenses.sort(byDescription);
    else if (sort === "category") expenses.sort((a, b) => (window.CATEGORY_CONFIG[a.category]?.label || a.category).localeCompare(window.CATEGORY_CONFIG[b.category]?.label || b.category) || byDescription(a, b));
    else if (sort === "amount") expenses.sort((a, b) => Number(b.amount) - Number(a.amount) || byDescription(a, b));
    else expenses.sort((a, b) => (b.expense_date || "").localeCompare(a.expense_date || "") || byDescription(a, b));
    return expenses;
}

function renderRecurringExpensesPage() {
    const expenses = sortedRecurringExpenses();
    const visible = expenses.slice(0, visibleRecurringExpenseLimit);
    document.getElementById("recurringExpenseRows").innerHTML = visible.length ? visible.map((expense) => {
        const category = window.CATEGORY_CONFIG[expense.category] || { label: expense.category, color: "#718096" };
        return `<div class="expense-manager-row"><span>${formatExpenseDate(expense.expense_date)}</span><strong>${escapeHtml(expense.description)}</strong><span class="expense-category-label"><i style="background:${category.color}"></i>${escapeHtml(category.label)}</span><span>${money.format(expense.amount)}</span><span class="recurrence-label">${recurrenceLabel(expense)}</span><span class="expense-row-actions"><button aria-label="Edit recurring expense" onclick="editRecurringExpense(${expense.id})"><i class="bi bi-pencil"></i></button><button aria-label="Delete recurring expense" onclick="deleteManagedExpense(${expense.id})"><i class="bi bi-trash"></i></button></span></div>`;
    }).join("") : '<div class="expense-manager-empty">No matching recurring expenses.</div>';
    const remaining = expenses.length - visible.length;
    const more = document.getElementById("showMoreRecurringExpenses");
    more.classList.toggle("d-none", remaining <= 0);
    more.textContent = remaining > 0 ? `Show more (${remaining})⌄` : "";
}

function showMoreRecurringExpenses() {
    visibleRecurringExpenseLimit = Number.MAX_SAFE_INTEGER;
    renderRecurringExpensesPage();
}

function editRecurringExpense(id) {
    openAddExpenseModal();
    editManagedExpense(id);
}

function renderExpenseManager() {
    const expenses = sortedManagerExpenses();
    const visible = expenses.slice(0, visibleExpenseLimit);
    document.getElementById("expenseManagerRows").innerHTML = visible.length ? visible.map((expense) => {
        const category = window.CATEGORY_CONFIG[expense.category] || { label: expense.category, color: "#718096" };
        const globalClass = expense.global_type ? ` global-expense ${expense.global_type}` : "";
        const badge = expense.global_type === "pledge" ? '<span class="global-expense-badge"><i class="bi bi-shield-check"></i> Deficit pledge</span>' : "";
        return `<div class="expense-manager-row${globalClass}"><span>${formatExpenseDate(expense.expense_date)}</span><strong>${expenseDescription(expense)}${badge}</strong><span class="expense-category-label"><i style="background:${category.color}"></i>${escapeHtml(category.label)}</span><span>${money.format(expense.amount)}</span><span class="recurrence-label">${recurrenceLabel(expense)}</span><span class="expense-row-actions"><button aria-label="Edit expense" onclick="editManagedExpense(${expense.id})"><i class="bi bi-pencil"></i></button><button aria-label="Delete expense" onclick="deleteManagedExpense(${expense.id})"><i class="bi bi-trash"></i></button></span></div>`;
    }).join("") : '<div class="expense-manager-empty">No matching expenses.</div>';
    renderGlobalSurplusCaption(document.getElementById("expenseManagerGlobalCaption"), expenses);
    const remaining = expenses.length - visible.length;
    const more = document.getElementById("showMoreExpenses");
    more.classList.toggle("d-none", remaining <= 0);
    more.textContent = remaining > 0 ? `Show more (${remaining})⌄` : "";
}

function showMoreExpenses() {
    visibleExpenseLimit = Number.MAX_SAFE_INTEGER;
    renderExpenseManager();
}

function editManagedExpense(id) {
    const expense = dashboardState.expenses.find((item) => item.id === id)
        || currentWorkspaceState?.recurring_expenses?.find((item) => item.id === id);
    if (!expense) return;
    document.getElementById("quickExpenseId").value = expense.id;
    document.getElementById("quickExpenseDescription").value = expense.description;
    document.getElementById("quickExpenseCategory").value = expense.category;
    document.getElementById("quickExpenseAmount").value = expense.amount;
    document.getElementById("quickExpenseDate").value = expense.expense_date || localToday();
    document.getElementById("quickExpenseRecurring").checked = Boolean(expense.recurring);
    document.getElementById("quickExpenseRecurrenceInterval").value = expense.recurrence_interval || 1;
    document.getElementById("quickExpenseRecurrenceUnit").value = expense.recurrence_unit || "month";
    syncRecurrenceFields("quickExpense");
    document.getElementById("quickExpenseSubmit").querySelector("span").textContent = "Update Expense";
    document.getElementById("quickExpenseDescription").focus();
}

async function deleteManagedExpense(id) {
    if (!confirm("Delete this expense?")) return;
    await api(`/api/expenses/${id}`, { method: "DELETE" });
    await loadDashboard();
    await loadLiabilityAutocomplete();
    renderExpenseManager();
    renderRecurringExpensesPage();
}

function toggleExpenseForm(expense = null) {
    document.getElementById("expenseForm").style.display = "block";
    document.getElementById("expenseId").value = expense?.id || "";
    document.getElementById("expenseDescription").value = expense?.description || "";
    document.getElementById("expenseAmount").value = expense?.amount || "";
    document.getElementById("expenseDate").value = expense?.expense_date || localToday();
    document.getElementById("expenseRecurring").checked = Boolean(expense?.recurring);
    document.getElementById("expenseRecurrenceInterval").value = expense?.recurrence_interval || 1;
    document.getElementById("expenseRecurrenceUnit").value = expense?.recurrence_unit || "month";
    syncRecurrenceFields("expense");
}

async function saveExpense() {
    const expenseId = document.getElementById("expenseId").value;
    const payload = {
        description: document.getElementById("expenseDescription").value,
        amount: parseFloat(document.getElementById("expenseAmount").value) || 0,
        expense_date: document.getElementById("expenseDate").value,
        category: selectedCategory,
        recurring: document.getElementById("expenseRecurring").checked,
        recurrence_interval: parseInt(document.getElementById("expenseRecurrenceInterval").value, 10) || 1,
        recurrence_unit: document.getElementById("expenseRecurrenceUnit").value,
    };
    const path = expenseId ? `/api/expenses/${expenseId}` : "/api/expenses";
    try {
        await api(path, { method: expenseId ? "PUT" : "POST", body: JSON.stringify(payload) });
        document.getElementById("expenseForm").style.display = "none";
        await refreshCategory();
        await loadLiabilityAutocomplete();
    } catch (error) {
        showExpenseSubmissionError(error);
    }
}

async function refreshCategory() {
    const expenses = await api(`/api/expenses?category=${encodeURIComponent(selectedCategory)}`);
    const table = document.getElementById("expenseTable");
    table.innerHTML = "";
    let total = 0;

    expenses.forEach((expense) => {
        total += expense.amount;
        const row = document.createElement("tr");
        row.innerHTML = `<td>${formatExpenseDate(expense.expense_date)}</td><td>${expenseDescription(expense)}</td><td>${money.format(expense.amount)}</td><td>${recurrenceLabel(expense)}</td><td class="text-end"><button class="btn btn-sm btn-outline-primary me-1">Edit</button><button class="btn btn-sm btn-outline-danger">Delete</button></td>`;
        row.querySelector(".btn-outline-primary").addEventListener("click", () => toggleExpenseForm(expense));
        row.querySelector(".btn-outline-danger").addEventListener("click", () => deleteExpense(expense.id));
        table.appendChild(row);
    });

    document.getElementById("categoryTotal").textContent = money.format(total);
    renderGlobalSurplusCaption(document.getElementById("categoryGlobalCaption"), expenses);
    await loadDashboard();
}

async function deleteExpense(id) {
    if (!confirm("Delete this expense?")) return;
    await api(`/api/expenses/${id}`, { method: "DELETE" });
    await refreshCategory();
    await loadLiabilityAutocomplete();
}

initializeTheme();
initializeCategoryReordering();
initializeRetirementCalculator();
resetRecurringExpenseForm();
initializeDashboard();
setInterval(async () => {
    const previousRun = workspaceSchedule?.next_run;
    try {
        await loadWorkspaceSchedule();
        if (previousRun && previousRun !== workspaceSchedule.next_run) {
            await loadDashboard();
            await initializeWorkspaceNavigation(true);
        }
    } catch (error) {
        console.warn("Unable to check the workspace schedule", error);
    }
}, 60000);

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
        await initializeWorkspaceNavigation(true);
    } catch (err) {
        error.textContent = err.message;
        error.classList.remove("d-none");
    }
}

async function showScorecards() {
    navigateTo("reports");
}

function renderScorecardList(scorecards) {
    const body = document.getElementById("financialReportsTable");
    if (!body) return;
    body.innerHTML = scorecards.length ? scorecards.map((report) => {
        const surplus = Number(report.surplus);
        return `<tr><td>${formatWorkspacePeriodDate(report.start_date)}</td><td>${formatWorkspacePeriodDate(report.end_date)}</td><td>${money.format(report.income)}</td><td>${money.format(report.total_spending)}</td><td class="report-balance ${surplus < 0 ? "deficit" : "surplus"}">${money.format(surplus)}</td><td class="report-balance ${(report.net_worth || 0) < 0 ? "deficit" : "surplus"}">${report.net_worth === null ? "—" : money.format(report.net_worth)}</td><td><div class="report-actions"><button type="button" onclick="openFinancialReport(${report.id})" aria-label="View ${escapeHtml(report.name)}" title="View report"><i class="bi bi-eye"></i></button><a href="/api/scorecards/${report.id}/export.csv" aria-label="Download ${escapeHtml(report.name)} as CSV" title="Download CSV"><i class="bi bi-download"></i></a><button class="danger" type="button" onclick="deleteScorecard(${report.id})" aria-label="Delete ${escapeHtml(report.name)}" title="Delete report"><i class="bi bi-trash"></i></button></div></td></tr>`;
    }).join("") : '<tr><td colspan="7" class="reports-empty">No financial reports match this date range.</td></tr>';
    const summary = document.getElementById("reportFilterSummary");
    if (summary) summary.textContent = `${scorecards.length} of ${financialReports.length} report${financialReports.length === 1 ? "" : "s"}`;
}

function filterFinancialReports() {
    const start = document.getElementById("reportStartFilter").value;
    const end = document.getElementById("reportEndFilter").value;
    renderScorecardList(financialReports.filter((report) => (!start || report.start_date >= start) && (!end || report.end_date <= end)));
}

function clearReportFilters() {
    document.getElementById("reportStartFilter").value = "";
    document.getElementById("reportEndFilter").value = "";
    filterFinancialReports();
}

async function openFinancialReport(id) {
    const details = document.getElementById("scorecardDetails");
    details.className = "scorecard-details text-muted";
    details.textContent = "Loading financial report…";
    new bootstrap.Modal(document.getElementById("scorecardsModal")).show();
    await loadScorecardDetails(id);
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
    document.getElementById("scorecardExpenseRecurrenceInterval").value = expense?.recurrence_interval || 1;
    document.getElementById("scorecardExpenseRecurrenceUnit").value = expense?.recurrence_unit || "month";
    syncRecurrenceFields("scorecardExpense");
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
        recurrence_interval: parseInt(document.getElementById("scorecardExpenseRecurrenceInterval").value, 10) || 1,
        recurrence_unit: document.getElementById("scorecardExpenseRecurrenceUnit").value,
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
    await deleteScorecard(activeScorecardId);
}

async function deleteScorecard(scorecardId) {
    if (!confirm("Delete this scorecard? This action cannot be undone.")) return;
    await api(`/api/scorecards/${scorecardId}`, { method: "DELETE" });
    if (activeScorecardId === scorecardId) {
        activeScorecardId = null;
        document.getElementById("scorecardDetails").className = "scorecard-details text-muted";
        document.getElementById("scorecardDetails").textContent = "Select a scorecard to view totals and detailed charges.";
        bootstrap.Modal.getInstance(document.getElementById("scorecardsModal"))?.hide();
    }
    await refreshScorecardList();
    await loadDashboard();
    await initializeWorkspaceNavigation(true);
}

async function deleteAllScorecards() {
    if (!financialReports.length) return;
    if (!confirm("Delete all reports? This action cannot be undone.")) return;
    await api("/api/scorecards", { method: "DELETE" });
    activeScorecardId = null;
    document.getElementById("scorecardDetails").className = "scorecard-details text-muted";
    document.getElementById("scorecardDetails").textContent = "Select a scorecard to view totals and detailed charges.";
    bootstrap.Modal.getInstance(document.getElementById("scorecardsModal"))?.hide();
    await refreshScorecardList();
    await loadDashboard();
    await initializeWorkspaceNavigation(true);
}

async function refreshScorecardList() {
    const year = new Date().getFullYear();
    const [reports, yearToDate, globalBalance] = await Promise.all([
        api("/api/scorecards"),
        api(`/api/scorecards/year-to-date?year=${year}`),
        api("/api/global-balance"),
    ]);
    financialReports = reports;
    filterFinancialReports();
    renderYearToDate(yearToDate, globalBalance);
}

function renderYearToDate(summary, globalBalance) {
    document.getElementById("yearToDateYear").textContent = summary.year;
    document.getElementById("ytdIncome").textContent = money.format(summary.total_income);
    document.getElementById("ytdSpending").textContent = money.format(summary.total_spending);
    const balance = document.getElementById("ytdGlobalBalance");
    balance.textContent = money.format(globalBalance.balance);
    balance.classList.toggle("negative", globalBalance.balance < 0);
    balance.classList.toggle("positive", globalBalance.balance >= 0);
    document.getElementById("ytdSavedInvested").textContent = `${summary.percent_saved_invested.toFixed(1)}%`;
}

function renderScorecardDetails(scorecard) {
    activeScorecardId = scorecard.id;
    editingScorecardExpenseId = null;
    const details = document.getElementById("scorecardDetails");
    details.classList.remove("text-muted");
    const largestExpense = scorecard.summary.largest_expense;
    const largestCategory = scorecard.summary.largest_category;
    const categoryTotals = scorecard.categories.map((category) => `<div class="report-category-total" style="--category-color:${category.color}"><span>${escapeHtml(category.label)}</span><strong>${money.format(category.total)}</strong></div>`).join("");
    details.innerHTML = `
        <div class="d-flex flex-wrap justify-content-between align-items-start gap-2 mb-3">
            <div>
                <h4>${escapeHtml(scorecard.name)}</h4>
                <div class="text-muted">${scorecard.start_date} – ${scorecard.end_date}</div>
            </div>
            <div class="report-detail-actions">
                <a class="report-icon-button" href="/api/scorecards/${scorecard.id}/export.csv" aria-label="Download report as CSV" title="Download CSV"><i class="bi bi-download"></i></a><button class="report-icon-button danger" onclick="deleteActiveScorecard()" aria-label="Delete report" title="Delete report"><i class="bi bi-trash"></i></button>
            </div>
        </div>
        <section class="report-summary" aria-label="Financial report summary">
            <div class="report-summary-primary"><article><span>Total spending</span><strong>${money.format(scorecard.total_spending)}</strong></article><article><span>Surplus / Deficit</span><strong class="${scorecard.surplus < 0 ? "negative" : "positive"}">${money.format(scorecard.surplus)}</strong></article><article><span>Global Surplus / Deficit</span><strong class="${scorecard.global_balance < 0 ? "negative" : "positive"}">${money.format(scorecard.global_balance)}</strong><small>At time of save</small></article><article><span>Net Worth</span><strong class="${(scorecard.net_worth || 0) < 0 ? "negative" : "positive"}">${scorecard.net_worth === null ? "Not captured" : money.format(scorecard.net_worth)}</strong><small>At time of save</small></article></div>
            <div class="report-category-totals"><div class="summary-section-label">Spending by category</div>${categoryTotals}</div>
            <div class="report-summary-insights"><article><i class="bi bi-arrow-up-right-circle"></i><div><span>Largest expense</span><strong>${largestExpense ? `${expenseDescription(largestExpense)} · ${money.format(largestExpense.amount)}` : "No expenses"}</strong><small>${largestExpense ? escapeHtml(largestExpense.category_label) : ""}</small></div></article><article><i class="bi bi-pie-chart"></i><div><span>Largest category</span><strong>${largestCategory ? escapeHtml(largestCategory.label) : "No expenses"}</strong><small>${largestCategory ? money.format(largestCategory.total) : ""}</small></div></article><article><i class="bi bi-receipt"></i><div><span>Total expenses</span><strong>${scorecard.summary.expense_count}</strong><small>Saved charges</small></div></article><article><i class="bi bi-arrow-repeat"></i><div><span>Recurring expenses</span><strong>${scorecard.summary.recurring_count}</strong><small>${scorecard.summary.recurring_percent.toFixed(1)}% of spending</small></div></article></div>
        </section>
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
                                <input id="scorecardExpenseRecurring" class="form-check-input" type="checkbox" onchange="syncRecurrenceFields('scorecardExpense')">
                                <label class="form-check-label" for="scorecardExpenseRecurring">Recurring charge</label>
                            </div>
                            <div class="d-flex flex-wrap gap-2 scorecard-form-actions">
                                <button class="btn btn-primary" onclick="saveScorecardExpense()">Save</button>
                                <button class="btn btn-outline-secondary" onclick="hideScorecardExpenseForm()">Cancel</button>
                            </div>
                        </div>
                        <div id="scorecardExpenseRecurrenceFields" class="col-12 recurrence-fields d-none"><span>Every</span><input id="scorecardExpenseRecurrenceInterval" class="form-control" type="number" min="1" step="1" value="1"><select id="scorecardExpenseRecurrenceUnit" class="form-select"><option value="day">day(s)</option><option value="week">week(s)</option><option value="month" selected>month(s)</option><option value="year">year(s)</option></select></div>
                    </div>
                </div>
            </div>
        </div>`;


    scorecard.categories.forEach((category) => {
        const section = document.createElement("div");
        section.className = "card category-summary report-category-collapse mb-3";
        section.style.setProperty("--category-color", category.color);
        const collapseId = `report-category-${scorecard.id}-${category.id}`;
        const rows = category.expenses.length ? category.expenses.map((expense) => `<div class="expense-row border-top py-2"><span>${expenseDescription(expense)}</span><span>${expense.recurring ? recurrenceLabel(expense) : "One-time"}</span><strong>${money.format(expense.amount)}</strong><span class="text-end"><button class="btn btn-sm btn-outline-primary me-1">Edit</button><button class="btn btn-sm btn-outline-danger">Delete</button></span></div>`).join("") : '<div class="text-muted border-top py-2">No charges in this category.</div>';
        const globalCaption = category.expenses.some((expense) => expense.global_type === "draw") ? `<p class="global-surplus-caption"><i class="bi bi-globe2 global-surplus-marker"></i> Expenses marked with the globe icon came from global surplus, not income in this workspace period.</p>` : "";
        section.innerHTML = `<button class="report-category-toggle" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="false"><span class="category-icon" style="color:${category.color};background:${category.color}18"><i class="bi bi-${category.icon}"></i></span><span><strong>${category.label}</strong><small>${category.count} charge${category.count === 1 ? "" : "s"}</small></span><b>${money.format(category.total)}</b><i class="bi bi-chevron-down category-chevron"></i></button><div class="collapse" id="${collapseId}"><div class="report-category-body">${rows}${globalCaption}</div></div>`;
        section.querySelectorAll(".btn-outline-primary").forEach((button, index) => button.addEventListener("click", () => showScorecardExpenseForm(category.expenses[index])));
        section.querySelectorAll(".btn-outline-danger").forEach((button, index) => button.addEventListener("click", () => deleteScorecardExpense(category.expenses[index].id)));
        details.appendChild(section);
    });
}


function exportDatabase() {
    window.location.href = "/api/database/export";
}

function openImportDatabaseModal() {
    navigateTo("import");
    document.getElementById("databaseImportFile").value = "";
    document.getElementById("databaseImportError").classList.add("d-none");
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

    await loadDashboard();
    navigateTo("budget");
}

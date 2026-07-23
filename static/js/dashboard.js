const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
let selectedCategory = "";
let categoryChart;
let dashboardState = { categories: [], expenses: [], summary: {} };
let incomeEditorLoaded = false;
let visibleExpenseLimit = 5;

function navigateTo(page) {
    document.querySelectorAll(".app-page").forEach((section) => section.classList.toggle("active", section.id === `page-${page}`));
    document.querySelectorAll(".app-nav [data-page]").forEach((button) => button.classList.toggle("active", button.dataset.page === page));
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (page === "income" || page === "settings") initializeIncomeEditor();
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
    renderSummary(dashboardState.summary);
    renderCategories(dashboardState.categories);
    renderChart(dashboardState.categories);
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
    document.getElementById("savingsRate").textContent = `${summary.savings_rate.toFixed(1)}%`;
    document.getElementById("investmentRate").textContent = `${summary.investment_rate.toFixed(1)}%`;

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
            context.fillStyle = "#10223b";
            context.font = "700 17px Inter, sans-serif";
            context.fillText(money.format(total), (chartArea.left + chartArea.right) / 2, (chartArea.top + chartArea.bottom) / 2 - 6);
            context.fillStyle = "#718096";
            context.font = "10px Inter, sans-serif";
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
    renderIncomeTaxSelectors(...selectedIncomeRules);
    renderTaxRulesetSelectors();
    updateIncomePreview();
}

async function deleteTaxRuleset(id) {
    if (!confirm("Delete this tax ruleset?")) return;
    const selectedIncomeRules = [document.getElementById("taxCountry").value, document.getElementById("taxProvince").value, document.getElementById("taxYear").value];
    await api(`/api/tax-rulesets/${id}`, { method: "DELETE" });
    taxRulesets = await api("/api/tax-rulesets");
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
    };
    try {
        await api(id ? `/api/expenses/${id}` : "/api/expenses", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        await loadDashboard();
        resetQuickExpenseForm();
        renderExpenseManager();
        document.getElementById("quickExpenseDescription").focus();
    } catch (err) {
        const error = document.getElementById("quickExpenseError");
        error.textContent = err.message;
        error.classList.remove("d-none");
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

function renderExpenseManager() {
    const expenses = sortedManagerExpenses();
    const visible = expenses.slice(0, visibleExpenseLimit);
    document.getElementById("expenseManagerRows").innerHTML = visible.length ? visible.map((expense) => {
        const category = window.CATEGORY_CONFIG[expense.category] || { label: expense.category, color: "#718096" };
        return `<div class="expense-manager-row"><span>${formatExpenseDate(expense.expense_date)}</span><strong>${escapeHtml(expense.description)}</strong><span class="expense-category-label"><i style="background:${category.color}"></i>${escapeHtml(category.label)}</span><span>${money.format(expense.amount)}</span><span>${expense.recurring ? '<i class="bi bi-check-square-fill recurring-check"></i>' : "—"}</span><span class="expense-row-actions"><button aria-label="Edit expense" onclick="editManagedExpense(${expense.id})"><i class="bi bi-pencil"></i></button><button aria-label="Delete expense" onclick="deleteManagedExpense(${expense.id})"><i class="bi bi-trash"></i></button></span></div>`;
    }).join("") : '<div class="expense-manager-empty">No matching expenses.</div>';
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
    const expense = dashboardState.expenses.find((item) => item.id === id);
    if (!expense) return;
    document.getElementById("quickExpenseId").value = expense.id;
    document.getElementById("quickExpenseDescription").value = expense.description;
    document.getElementById("quickExpenseCategory").value = expense.category;
    document.getElementById("quickExpenseAmount").value = expense.amount;
    document.getElementById("quickExpenseDate").value = expense.expense_date || localToday();
    document.getElementById("quickExpenseRecurring").checked = Boolean(expense.recurring);
    document.getElementById("quickExpenseSubmit").querySelector("span").textContent = "Update Expense";
    document.getElementById("quickExpenseDescription").focus();
}

async function deleteManagedExpense(id) {
    if (!confirm("Delete this expense?")) return;
    await api(`/api/expenses/${id}`, { method: "DELETE" });
    await loadDashboard();
    renderExpenseManager();
}

function toggleExpenseForm(expense = null) {
    document.getElementById("expenseForm").style.display = "block";
    document.getElementById("expenseId").value = expense?.id || "";
    document.getElementById("expenseDescription").value = expense?.description || "";
    document.getElementById("expenseAmount").value = expense?.amount || "";
    document.getElementById("expenseDate").value = expense?.expense_date || localToday();
    document.getElementById("expenseRecurring").checked = Boolean(expense?.recurring);
}

async function saveExpense() {
    const expenseId = document.getElementById("expenseId").value;
    const payload = {
        description: document.getElementById("expenseDescription").value,
        amount: parseFloat(document.getElementById("expenseAmount").value) || 0,
        expense_date: document.getElementById("expenseDate").value,
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
        row.innerHTML = `<td>${formatExpenseDate(expense.expense_date)}</td><td>${escapeHtml(expense.description)}</td><td>${money.format(expense.amount)}</td><td>${expense.recurring ? "✓" : ""}</td><td class="text-end"><button class="btn btn-sm btn-outline-primary me-1">Edit</button><button class="btn btn-sm btn-outline-danger">Delete</button></td>`;
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

function openSaveScorecardFromReports() {
    const reportsElement = document.getElementById("scorecardsModal");
    reportsElement.addEventListener("hidden.bs.modal", openSaveScorecardModal, { once: true });
    bootstrap.Modal.getInstance(reportsElement).hide();
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

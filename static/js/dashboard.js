async function loadDashboard() {

    const response = await fetch("/api/summary");

    const data = await response.json();

    document.getElementById("income").innerHTML =
        "$" + data.income.toFixed(2);

    document.getElementById("spending").innerHTML =
        "$" + data.spending.toFixed(2);

    const surplus = document.getElementById("surplus");

    surplus.innerHTML =
        "$" + data.surplus.toFixed(2);

    surplus.classList.remove("text-success");
    surplus.classList.remove("text-danger");

    if (data.surplus >= 0)
        surplus.classList.add("text-success");
    else
        surplus.classList.add("text-danger");
}

async function editIncome() {

    const value = prompt("Monthly Income");

    if (value === null)
        return;

    await fetch("/api/income", {

        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({
            income: parseFloat(value)
        })

    });

    loadDashboard();
}

async function loadCategories() {

    const response =
        await fetch("/api/categories");

    const data =
        await response.json();

    document.getElementById("fixed-total")
        .innerHTML =
        "$" + data["Fixed Costs"].total.toFixed(2);

    document.getElementById("fixed-count")
        .innerHTML =
        data["Fixed Costs"].count + " expenses";

    document.getElementById("savings-total")
        .innerHTML =
        "$" + data["Savings"].total.toFixed(2);

    document.getElementById("savings-count")
        .innerHTML =
        data["Savings"].count + " expenses";

    document.getElementById("investments-total")
        .innerHTML =
        "$" + data["Investments"].total.toFixed(2);

    document.getElementById("investments-count")
        .innerHTML =
        data["Investments"].count + " expenses";

    document.getElementById("guilt-total")
        .innerHTML =
        "$" + data["Guilt Free Spending"].total.toFixed(2);

    document.getElementById("guilt-count")
        .innerHTML =
        data["Guilt Free Spending"].count + " expenses";
}

function showCategory(category){

    document
        .getElementById("categoryTitle")
        .innerHTML = category;

    document
        .getElementById("categoryExpenses")
        .innerHTML =
        "<p>Expenses will appear here.</p>";

    const modal =
        new bootstrap.Modal(
            document.getElementById("categoryModal")
        );

    modal.show();
}

loadDashboard();
loadCategories();
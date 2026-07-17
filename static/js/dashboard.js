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

loadDashboard();
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

let selectedCategory = "";

async function showCategory(category){

    selectedCategory = category;

    document.getElementById(
        "categoryTitle"
    ).innerHTML = category;

    await refreshCategory();

    new bootstrap.Modal(
        document.getElementById(
            "categoryModal"
        )
    ).show();
}

function toggleExpenseForm(){

    const form =
        document.getElementById("expenseForm");

    form.style.display =
        form.style.display === "none"
            ? "block"
            : "none";
}

async function saveExpense(){

    const description =
        document.getElementById(
            "expenseDescription"
        ).value;

    const amount =
        parseFloat(
            document.getElementById(
                "expenseAmount"
            ).value
        );

    const recurring =
        document.getElementById(
            "expenseRecurring"
        ).checked;

    await fetch("/api/expenses",{

        method:"POST",

        headers:{
            "Content-Type":"application/json"
        },

        body:JSON.stringify({

            description,

            amount,

            category:selectedCategory,

            recurring

        })

    });

    document.getElementById(
        "expenseDescription"
    ).value="";

    document.getElementById(
        "expenseAmount"
    ).value="";

    document.getElementById(
        "expenseRecurring"
    ).checked=false;

    await refreshCategory();
}

async function refreshCategory(){

    const response =
        await fetch(
            "/api/expenses?category="+
            encodeURIComponent(selectedCategory)
        );

    const expenses =
        await response.json();

    let total = 0;

    const table =
        document.getElementById(
            "expenseTable"
        );

    table.innerHTML="";

    expenses.forEach(expense=>{

        total += expense.amount;

        table.innerHTML += `

        <tr>

            <td>${expense.description}</td>

            <td>$${expense.amount.toFixed(2)}</td>

            <td>${expense.recurring?"✓":""}</td>

            <td>

                <button
                    class="btn btn-sm btn-outline-primary"
                    onclick="editExpense(${expense.id})">

                    ✏

                </button>

                <button
                    class="btn btn-sm btn-outline-danger"
                    onclick="deleteExpense(${expense.id})">

                    🗑

                </button>

            </td>

        </tr>

        `;

    });

    document.getElementById(
        "categoryTotal"
    ).innerHTML =
        "$"+total.toFixed(2);

    await loadDashboard();

    await loadCategories();
}

loadDashboard();
loadCategories();
# Ideas for New Features

- [ ] Update README with all the app's current features, plus setup instructions.
- [x] More robust monthly income editor.
    - Move "Edit Income" button inside the Income modal, and clicking it should bring up a pop-up that allows users ti input the following:
    - Select income tax option. Keep the default option of 0% income tax (what we currently have). Add the option to specify country and region. For now, just Canada and the 10 provinces. Use your expected annual gross income and the selected province to calculate monthly take-home pay. THIS becomes the "Income" number shown on the dashboard, from which we derive the amounts for each of the four categories
- [ ] Fix conscious spending plan below the pie chart. Compare the percentages of Income with what is actually spent. 
    - Green up arrows if Savings or Investments are higher than 10%, red down arrows if below 10%
    - Green down arrow if Fixed Costs or is below 60% of Income, red up arrow if it's above 60% of Income
    -  Green down arrow if Guilty Free Spending is below 20% of Income, red up arrow if it's above 20%
- [ ] Rich Dad, Poor Dad asset and liability card. 
    - For any stocks, bonds or funds in the Assets column, add suport to pull real financial data, updating the value of this asset as often as a "free" plan for the financial API allows. 

## Income Tax
Income tax feature for Canada uses federal and provincial rates [provided by the Canadian Federal Government](https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/current-year.html).

## Basic Personal Amount
Found [information on basic personal amounts](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/deductions-credits-expenses/line-30000-basic-personal-amount.html) for the Government of Canada and each provincial government here. 



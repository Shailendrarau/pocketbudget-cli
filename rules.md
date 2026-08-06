# Application Domain Rules

This document is the source of truth for your TDD loop. Fill in each section **before** you write any code — every rule you write here becomes at least one test.

There are no wrong answers, but there are inconsistent ones. Once you decide a rule, your code has to match it.

---

## 1. Currency Symbol

*What currency does your application use, and how is money formatted when it's displayed?*

> _Your answer:_

$55

## 2. Standard Categories

*Which expense categories are allowed? Limit yourself to 3–5. What happens if someone uses a category that isn't on your list?*

> _Your answer:_
Allowed categories:
Food 
Transport
Entertainment
 If a user enters a category that is not on this list, the application rejects the expense and displays an error:
Shopping
Sports

## 3. Overspending Behaviour (Total Balance)

*What happens when an expense is larger than the total balance? Does your app allow the balance to go negative, or does it block the transaction? If it blocks, what does the caller get back?*

> _Your answer:_

Th application 

## 4. Budget Limits (Category Budgets)

*What happens when an expense exceeds a category's budget limit, but the balance could still cover it? Is it blocked, or is it recorded with a warning?*

> _Your answer:_
 The expense is recorded even if it exceeds the category budget.
 The application displays a Budget limit exceeded warning.
 The category's total expense is updated as normal.

## TDD Blueprint

Now turn each rule above into the test you will write **before** the implementation exists. Name the behaviour you'd assert.

- [ ] Rule 1 (Currency) →
- [ ] Rule 2 (Categories) →
- [ ] Rule 3 (Overspending) →
- [ ] Rule 4 (Budget Limits) →

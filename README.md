# PocketBudget

PocketBudget is a simple command-line Python application that allows users to keep track of their own expenses. It enables users to manage their balance, track their expenses, and check their transaction history. The application is designed with simplicity, readability, and maintainability in mind, making it ideal for those new to Python and object-oriented programming.

## Installation & Setup

Prerequisites:
Python 3.10 or later
Git (optional, for cloning the repository)


The save file is created automatically at `data/budget.json` the first time you run a command. Set the `POCKETBUDGET_DATA_FILE` environment variable to use a different location.

## Usage

Run the application from the project directory:

python main.py

The application allows you to:

View your current balance.
Add income to your budget.
Record expenses.
View transaction history.

## Running the Tests

If the project uses pytest, run:

pytest


## Design Decisions

Object-Oriented Design

The application follows an object-oriented approach by encapsulating budget-related data and behaviour into classes. This improves code organisation and makes future enhancements easier.

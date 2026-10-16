# Library Management System

A full-stack college mini project: **Flask + MySQL + Jinja2 + Bootstrap 5**.
Supports two roles (Admin/Librarian and Student) with book, student, issue/return,
fine and transaction management.

## Features

- Login with hashed passwords (Werkzeug `scrypt`), role-based access, logout
- Admin dashboard: total books, available books, issued books, total students,
  overdue books, recent transactions
- Book management: add, view, edit, delete, search, filter by title/author/category/availability
- Student management: add (creates login account), view, edit, delete, search
- Issue book: picks student, book, issue date, due date; decrements available copies;
  refuses when no copy is free; uses row locking to prevent race conditions
- Return book: increments available copies, stores return date, sets status to Returned,
  calculates fine at Rs. 5 per late day
- Transactions: full history with search and filters (status, overdue, date range)
- Student dashboard: browse/search available books, see books currently issued with due dates,
  see transaction history and applicable fines. Students cannot reach admin pages (403).

## Project structure

```
LibraryManagementSystem/
├── app.py
├── database.sql
├── requirements.txt
├── README.md
├── .env.example
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── error.html
│   ├── admin/
│   └── student/
└── static/
    ├── css/style.css
    └── js/main.js
```

## Setup

### 1. Prerequisites
- Python 3.10+
- MySQL 8.0+ (CHECK constraints need 8.0.16 or later)

### 2. Create the database

```bash
mysql -u root -p < database.sql
```

This creates `library_db`, all four tables, and the sample data.

### 3. Install Python packages

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set `DB_PASSWORD` to your MySQL password and `SECRET_KEY` to a long random string.

### 5. Run

```bash
python app.py
```

Open http://localhost:5000

## Sample accounts

| Role    | Username | Password   |
|---------|----------|------------|
| Admin   | `admin`  | `admin123` |
| Student | `STU001` | `student123` |

Student logins use the **Student ID** as the username. When an admin adds a new student
they set an initial password, and can reset it later from the edit page.

## Business rules

| Rule | Behaviour |
|------|-----------|
| Loan period | 14 days by default (pre-filled in the issue form, editable) |
| Issuing | Blocked if `available_quantity` is 0 |
| Available copies | Decremented on issue, incremented on return |
| Late fine | Rs. 5 × number of days returned after the due date |
| Deleting a book | Blocked while any copy is currently issued |
| Deleting a student | Blocked while the student has books issued; removes their login and history |
| Reducing book quantity | Cannot go below the number of copies currently issued |

## Database tables

- **users**: login accounts (`role` = admin/student), linked to `students` by `student_id`
- **students**: profile data (code, name, email, phone, branch, year)
- **books**: catalogue with `quantity` and `available_quantity`
- **transactions**: one row per issue, with issue/due/return dates, status and fine

Primary keys, foreign keys with cascade rules, unique constraints on ISBN, student code
and email, and CHECK constraints for year, quantity and dates are all defined in `database.sql`.

## Security notes

- Passwords are stored only as salted hashes.
- Every admin route is wrapped in `@login_required("admin")`; student routes in
  `@login_required("student")`. Wrong-role access returns HTTP 403.
- All SQL uses parameterised queries.
- Sessions are signed with `SECRET_KEY`.

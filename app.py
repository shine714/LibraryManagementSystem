import os
from datetime import date, timedelta
from functools import wraps

import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, abort)
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

FINE_PER_DAY = 5  # Rs. per late day
LOAN_DAYS = 14

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "library_db"),
}

pool = pooling.MySQLConnectionPool(pool_name="lib_pool", pool_size=5, **DB_CONFIG)


# ---------------------------------------------------------------- helpers
def get_db():
    return pool.get_connection()


def query(sql, params=None, one=False, commit=False):
    """Run a query. Returns rows (dicts) for SELECT, lastrowid for INSERT."""
    conn = get_db()
    cur = None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        if commit:
            conn.commit()
            return cur.lastrowid
        rows = cur.fetchone() if one else cur.fetchall()
        return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        if cur is not None:
            cur.close()
        conn.close()


def run_in_tx(fn):
    """Call fn(cursor) inside one transaction; commit on success, roll back on error."""
    conn = get_db()
    cur = conn.cursor()
    try:
        result = fn(cur)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def fine_for(due_date, return_date):
    if return_date and return_date > due_date:
        return (return_date - due_date).days * FINE_PER_DAY
    return 0


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                           message="You do not have permission to view this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           message="The page you requested was not found."), 404


@app.context_processor
def inject_globals():
    return {"current_role": session.get("role"),
            "current_name": session.get("name"),
            "today": date.today()}


# ---------------------------------------------------------------- auth
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("admin_dashboard" if session["role"] == "admin"
                            else "student_dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = query("SELECT * FROM users WHERE username = %s", (username,), one=True)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["user_id"]
            session["role"] = user["role"]
            session["name"] = user["full_name"]
            session["student_id"] = user["student_id"]
            flash(f"Welcome, {user['full_name']}!", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------- admin dashboard
@app.route("/admin/dashboard")
@login_required("admin")
def admin_dashboard():
    stats = query("""
        SELECT
          (SELECT COALESCE(SUM(quantity),0) FROM books)            AS total_books,
          (SELECT COALESCE(SUM(available_quantity),0) FROM books)  AS available_books,
          (SELECT COUNT(*) FROM transactions WHERE status='Issued') AS issued_books,
          (SELECT COUNT(*) FROM students)                          AS total_students,
          (SELECT COUNT(*) FROM transactions
             WHERE status='Issued' AND due_date < CURDATE())       AS overdue_books
    """, one=True)
    recent = query("""
        SELECT t.transaction_id, s.name AS student_name, b.title AS book_title,
               t.issue_date, t.due_date, t.return_date, t.status, t.fine
        FROM transactions t
        JOIN students s ON s.student_id = t.student_id
        JOIN books b    ON b.book_id    = t.book_id
        ORDER BY t.transaction_id DESC LIMIT 8
    """)
    return render_template("admin/dashboard.html", stats=stats, recent=recent)


# ---------------------------------------------------------------- books
@app.route("/admin/books")
@login_required("admin")
def admin_books():
    q = request.args.get("q", "").strip()
    title = request.args.get("title", "").strip()
    author = request.args.get("author", "").strip()
    category = request.args.get("category", "").strip()
    availability = request.args.get("availability", "").strip()

    sql = "SELECT * FROM books WHERE 1=1"
    params = []
    if q:
        sql += " AND (title LIKE %s OR author LIKE %s OR isbn LIKE %s OR category LIKE %s)"
        params += [f"%{q}%"] * 4
    if title:
        sql += " AND title LIKE %s"; params.append(f"%{title}%")
    if author:
        sql += " AND author LIKE %s"; params.append(f"%{author}%")
    if category:
        sql += " AND category = %s"; params.append(category)
    if availability == "available":
        sql += " AND available_quantity > 0"
    elif availability == "unavailable":
        sql += " AND available_quantity = 0"
    sql += " ORDER BY book_id"

    books = query(sql, params)
    categories = query("SELECT DISTINCT category FROM books ORDER BY category")
    return render_template("admin/books.html", books=books, categories=categories,
                           filters=dict(q=q, title=title, author=author,
                                        category=category, availability=availability))


def _book_form_values(form):
    return {
        "title": form.get("title", "").strip(),
        "author": form.get("author", "").strip(),
        "category": form.get("category", "").strip(),
        "isbn": form.get("isbn", "").strip(),
        "quantity": form.get("quantity", "0").strip(),
    }


def _validate_book(v):
    if not v["title"] or not v["author"] or not v["category"] or not v["isbn"]:
        return "Title, author, category and ISBN are required."
    if not v["quantity"].isdigit() or int(v["quantity"]) < 1:
        return "Quantity must be a whole number of at least 1."
    return None


@app.route("/admin/books/add", methods=["GET", "POST"])
@login_required("admin")
def admin_book_add():
    if request.method == "POST":
        v = _book_form_values(request.form)
        err = _validate_book(v)
        if err:
            flash(err, "danger")
            return render_template("admin/book_form.html", book=v, mode="add")
        try:
            qty = int(v["quantity"])
            query("""INSERT INTO books (title, author, category, isbn, quantity, available_quantity)
                     VALUES (%s,%s,%s,%s,%s,%s)""",
                  (v["title"], v["author"], v["category"], v["isbn"], qty, qty), commit=True)
            flash("Book added successfully.", "success")
            return redirect(url_for("admin_books"))
        except mysql.connector.IntegrityError:
            flash("A book with this ISBN already exists.", "danger")
            return render_template("admin/book_form.html", book=v, mode="add")
    return render_template("admin/book_form.html", book={}, mode="add")


@app.route("/admin/books/<int:book_id>/edit", methods=["GET", "POST"])
@login_required("admin")
def admin_book_edit(book_id):
    book = query("SELECT * FROM books WHERE book_id=%s", (book_id,), one=True)
    if not book:
        abort(404)
    if request.method == "POST":
        v = _book_form_values(request.form)
        err = _validate_book(v)
        if err:
            flash(err, "danger")
            return render_template("admin/book_form.html", book={**book, **v},
                                   mode="edit")
        new_qty = int(v["quantity"])
        issued = book["quantity"] - book["available_quantity"]
        if new_qty < issued:
            flash(f"Quantity cannot be less than the {issued} copies currently issued.", "danger")
            return render_template("admin/book_form.html", book={**book, **v},
                                   mode="edit")
        new_available = new_qty - issued
        try:
            query("""UPDATE books SET title=%s, author=%s, category=%s, isbn=%s,
                       quantity=%s, available_quantity=%s WHERE book_id=%s""",
                  (v["title"], v["author"], v["category"], v["isbn"],
                   new_qty, new_available, book_id), commit=True)
            flash("Book updated successfully.", "success")
            return redirect(url_for("admin_books"))
        except mysql.connector.IntegrityError:
            flash("Another book already uses this ISBN.", "danger")
            return render_template("admin/book_form.html", book={**book, **v},
                                   mode="edit")
    return render_template("admin/book_form.html", book=book, mode="edit")


@app.route("/admin/books/<int:book_id>/delete", methods=["POST"])
@login_required("admin")
def admin_book_delete(book_id):
    book = query("SELECT * FROM books WHERE book_id=%s", (book_id,), one=True)
    if not book:
        abort(404)
    active = query("SELECT COUNT(*) AS c FROM transactions WHERE book_id=%s AND status='Issued'",
                   (book_id,), one=True)
    if active["c"] > 0:
        flash("Cannot delete a book that is currently issued.", "danger")
        return redirect(url_for("admin_books"))
    query("DELETE FROM books WHERE book_id=%s", (book_id,), commit=True)
    flash("Book deleted.", "success")
    return redirect(url_for("admin_books"))


# ---------------------------------------------------------------- students
@app.route("/admin/students")
@login_required("admin")
def admin_students():
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM students"
    params = []
    if q:
        sql += " WHERE student_code LIKE %s OR name LIKE %s OR email LIKE %s OR branch LIKE %s"
        params = [f"%{q}%"] * 4
    sql += " ORDER BY student_id"
    students = query(sql, params)
    return render_template("admin/students.html", students=students, q=q)


def _student_form_values(form):
    return {
        "student_code": form.get("student_code", "").strip(),
        "name": form.get("name", "").strip(),
        "email": form.get("email", "").strip(),
        "phone": form.get("phone", "").strip(),
        "branch": form.get("branch", "").strip(),
        "year": form.get("year", "").strip(),
    }


def _validate_student(v, password=None):
    if not all([v["student_code"], v["name"], v["email"], v["branch"], v["year"]]):
        return "Student ID, name, email, branch and year are required."
    if "@" not in v["email"]:
        return "Please enter a valid email address."
    if not v["year"].isdigit() or not (1 <= int(v["year"]) <= 6):
        return "Year must be a number between 1 and 6."
    if password is not None and len(password) < 6:
        return "Password must be at least 6 characters."
    return None


@app.route("/admin/students/add", methods=["GET", "POST"])
@login_required("admin")
def admin_student_add():
    if request.method == "POST":
        v = _student_form_values(request.form)
        password = request.form.get("password", "")
        err = _validate_student(v, password)
        if err:
            flash(err, "danger")
            return render_template("admin/student_form.html", student=v, mode="add")
        def _create(cur):
            cur.execute("""INSERT INTO students (student_code, name, email, phone, branch, year)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (v["student_code"], v["name"], v["email"], v["phone"],
                         v["branch"], int(v["year"])))
            new_id = cur.lastrowid
            cur.execute("""INSERT INTO users (username, password_hash, role, full_name, student_id)
                           VALUES (%s,%s,'student',%s,%s)""",
                        (v["student_code"], generate_password_hash(password),
                         v["name"], new_id))
        try:
            run_in_tx(_create)
            flash("Student added. Login username is the Student ID.", "success")
            return redirect(url_for("admin_students"))
        except mysql.connector.IntegrityError:
            flash("Student ID or email already exists.", "danger")
            return render_template("admin/student_form.html", student=v, mode="add")
    return render_template("admin/student_form.html", student={}, mode="add")


@app.route("/admin/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required("admin")
def admin_student_edit(student_id):
    student = query("SELECT * FROM students WHERE student_id=%s", (student_id,), one=True)
    if not student:
        abort(404)
    if request.method == "POST":
        v = _student_form_values(request.form)
        new_password = request.form.get("password", "")
        err = _validate_student(v, new_password or None) if new_password else _validate_student(v)
        if err:
            flash(err, "danger")
            return render_template("admin/student_form.html", student={**student, **v},
                                   mode="edit")
        try:
            def _update(cur):
                cur.execute("""UPDATE students SET student_code=%s, name=%s, email=%s,
                               phone=%s, branch=%s, year=%s WHERE student_id=%s""",
                            (v["student_code"], v["name"], v["email"], v["phone"],
                             v["branch"], int(v["year"]), student_id))
                cur.execute("UPDATE users SET username=%s, full_name=%s WHERE student_id=%s",
                            (v["student_code"], v["name"], student_id))
                if new_password:
                    cur.execute("UPDATE users SET password_hash=%s WHERE student_id=%s",
                                (generate_password_hash(new_password), student_id))
            run_in_tx(_update)
            flash("Student updated.", "success")
            return redirect(url_for("admin_students"))
        except mysql.connector.IntegrityError:
            flash("Student ID or email already used by another student.", "danger")
            return render_template("admin/student_form.html", student={**student, **v},
                                   mode="edit")
    return render_template("admin/student_form.html", student=student, mode="edit")


@app.route("/admin/students/<int:student_id>/delete", methods=["POST"])
@login_required("admin")
def admin_student_delete(student_id):
    student = query("SELECT * FROM students WHERE student_id=%s", (student_id,), one=True)
    if not student:
        abort(404)
    active = query("SELECT COUNT(*) AS c FROM transactions WHERE student_id=%s AND status='Issued'",
                   (student_id,), one=True)
    if active["c"] > 0:
        flash("Cannot delete a student who has books currently issued.", "danger")
        return redirect(url_for("admin_students"))
    # users row is removed by ON DELETE CASCADE; transactions cascade too
    query("DELETE FROM students WHERE student_id=%s", (student_id,), commit=True)
    flash("Student deleted.", "success")
    return redirect(url_for("admin_students"))


# ---------------------------------------------------------------- issue / return
@app.route("/admin/issue", methods=["GET", "POST"])
@login_required("admin")
def admin_issue():
    if request.method == "POST":
        try:
            student_id = int(request.form.get("student_id", "0"))
            book_id = int(request.form.get("book_id", "0"))
            issue_date = date.fromisoformat(request.form.get("issue_date", ""))
            due_date = date.fromisoformat(request.form.get("due_date", ""))
        except ValueError:
            flash("Please select a student, a book and valid dates.", "danger")
            return redirect(url_for("admin_issue"))
        if due_date < issue_date:
            flash("Due date cannot be before the issue date.", "danger")
            return redirect(url_for("admin_issue"))

        conn = get_db()
        cur = conn.cursor()
        try:
            # lock the book row so two admins cannot take the last copy
            cur.execute("SELECT available_quantity FROM books WHERE book_id=%s FOR UPDATE",
                        (book_id,))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                flash("Book not found.", "danger")
                return redirect(url_for("admin_issue"))
            if row[0] < 1:
                conn.rollback()
                flash("No copies of this book are available right now.", "danger")
                return redirect(url_for("admin_issue"))
            cur.execute("SELECT student_id FROM students WHERE student_id=%s", (student_id,))
            if not cur.fetchone():
                conn.rollback()
                flash("Student not found.", "danger")
                return redirect(url_for("admin_issue"))
            cur.execute("""UPDATE books SET available_quantity = available_quantity - 1
                           WHERE book_id=%s""", (book_id,))
            cur.execute("""INSERT INTO transactions
                           (student_id, book_id, issue_date, due_date, status, fine)
                           VALUES (%s,%s,%s,%s,'Issued',0)""",
                        (student_id, book_id, issue_date, due_date))
            conn.commit()
            flash("Book issued successfully.", "success")
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("admin_transactions"))

    students = query("SELECT student_id, student_code, name FROM students ORDER BY name")
    books = query("SELECT book_id, title, author, available_quantity FROM books "
                  "WHERE available_quantity > 0 ORDER BY title")
    default_issue = date.today()
    default_due = default_issue + timedelta(days=LOAN_DAYS)
    return render_template("admin/issue.html", students=students, books=books,
                           default_issue=default_issue.isoformat(),
                           default_due=default_due.isoformat())


@app.route("/admin/return/<int:txn_id>", methods=["POST"])
@login_required("admin")
def admin_return(txn_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM transactions WHERE transaction_id=%s FOR UPDATE", (txn_id,))
        txn = cur.fetchone()
        if not txn:
            conn.rollback()
            abort(404)
        if txn["status"] != "Issued":
            conn.rollback()
            flash("This book has already been returned.", "warning")
            return redirect(url_for("admin_transactions"))
        return_date = date.today()
        fine = fine_for(txn["due_date"], return_date)
        cur.execute("""UPDATE transactions SET return_date=%s, status='Returned', fine=%s
                       WHERE transaction_id=%s""", (return_date, fine, txn_id))
        cur.execute("""UPDATE books SET available_quantity = available_quantity + 1
                       WHERE book_id=%s""", (txn["book_id"],))
        conn.commit()
        if fine:
            flash(f"Book returned. Late fine: ₹{fine}.", "warning")
        else:
            flash("Book returned on time. No fine.", "success")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_transactions"))


# ---------------------------------------------------------------- transactions
@app.route("/admin/transactions")
@login_required("admin")
def admin_transactions():
    return _transactions_view(admin=True)


@app.route("/student/transactions")
@login_required("student")
def student_transactions():
    return _transactions_view(admin=False)


def _transactions_view(admin):
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    sql = """
        SELECT t.transaction_id, t.student_id, s.name AS student_name, s.student_code,
               b.title AS book_title, t.issue_date, t.due_date, t.return_date,
               t.status, t.fine,
               CASE WHEN t.status='Issued' AND t.due_date < CURDATE() THEN 1 ELSE 0 END AS is_overdue
        FROM transactions t
        JOIN students s ON s.student_id = t.student_id
        JOIN books b    ON b.book_id    = t.book_id
        WHERE 1=1
    """
    params = []
    if not admin:
        sql += " AND t.student_id = %s"
        params.append(session["student_id"])
    if status in ("Issued", "Returned"):
        sql += " AND t.status = %s"; params.append(status)
    if status == "Overdue":
        sql += " AND t.status='Issued' AND t.due_date < CURDATE()"
    if q and admin:
        sql += " AND (s.name LIKE %s OR s.student_code LIKE %s OR b.title LIKE %s)"
        params += [f"%{q}%"] * 3
    if q and not admin:
        sql += " AND b.title LIKE %s"; params.append(f"%{q}%")
    if date_from:
        sql += " AND t.issue_date >= %s"; params.append(date_from)
    if date_to:
        sql += " AND t.issue_date <= %s"; params.append(date_to)
    sql += " ORDER BY t.transaction_id DESC"

    rows = query(sql, params)
    template = "admin/transactions.html" if admin else "student/transactions.html"
    return render_template(template, rows=rows,
                           filters=dict(status=status, q=q, date_from=date_from, date_to=date_to))


# ---------------------------------------------------------------- student area
@app.route("/student/dashboard")
@login_required("student")
def student_dashboard():
    sid = session["student_id"]
    student = query("SELECT * FROM students WHERE student_id=%s", (sid,), one=True)
    current = query("""
        SELECT t.transaction_id, b.title AS book_title, b.author, t.issue_date, t.due_date,
               CASE WHEN t.due_date < CURDATE() THEN 1 ELSE 0 END AS is_overdue
        FROM transactions t JOIN books b ON b.book_id = t.book_id
        WHERE t.student_id=%s AND t.status='Issued'
        ORDER BY t.due_date
    """, (sid,))
    fines = query("SELECT COALESCE(SUM(fine),0) AS total FROM transactions WHERE student_id=%s",
                  (sid,), one=True)
    pending_fine = 0
    for c in current:
        if c["is_overdue"]:
            pending_fine += (date.today() - c["due_date"]).days * FINE_PER_DAY
    return render_template("student/dashboard.html", student=student, current=current,
                           total_fines=fines["total"] + pending_fine,
                           paid_fines=fines["total"], pending_fine=pending_fine)


@app.route("/student/books")
@login_required("student")
def student_books():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    sql = "SELECT * FROM books WHERE 1=1"
    params = []
    if q:
        sql += " AND (title LIKE %s OR author LIKE %s OR category LIKE %s)"
        params += [f"%{q}%"] * 3
    if category:
        sql += " AND category=%s"; params.append(category)
    sql += " ORDER BY title"
    books = query(sql, params)
    categories = query("SELECT DISTINCT category FROM books ORDER BY category")
    return render_template("student/books.html", books=books, categories=categories,
                           filters=dict(q=q, category=category))


# ---------------------------------------------------------------- run
if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", port=int(os.getenv("PORT", "5000")))

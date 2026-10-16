-- ============================================================
--  Library Management System - MySQL schema + sample data
--  Run:  mysql -u root -p < database.sql
-- ============================================================

DROP DATABASE IF EXISTS library_db;
CREATE DATABASE library_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE library_db;

-- ------------------------------------------------------------
-- students : student profile records
-- ------------------------------------------------------------
CREATE TABLE students (
    student_id   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    student_code VARCHAR(20)  NOT NULL UNIQUE,
    name         VARCHAR(100) NOT NULL,
    email        VARCHAR(120) NOT NULL UNIQUE,
    phone        VARCHAR(15)  NULL,
    branch       VARCHAR(60)  NOT NULL,
    year         TINYINT UNSIGNED NOT NULL,
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_students_year CHECK (year BETWEEN 1 AND 6)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- users : login accounts (admin / librarian and students)
-- ------------------------------------------------------------
CREATE TABLE users (
    user_id       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(30)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('admin','student') NOT NULL,
    full_name     VARCHAR(100) NOT NULL,
    student_id    INT UNSIGNED NULL UNIQUE,
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_users_student FOREIGN KEY (student_id)
        REFERENCES students(student_id) ON DELETE CASCADE,
    CONSTRAINT chk_student_role CHECK (
        (role = 'student' AND student_id IS NOT NULL) OR
        (role = 'admin'   AND student_id IS NULL))
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- books : catalogue, with quantity tracking
-- ------------------------------------------------------------
CREATE TABLE books (
    book_id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title              VARCHAR(200) NOT NULL,
    author             VARCHAR(120) NOT NULL,
    category           VARCHAR(60)  NOT NULL,
    isbn               VARCHAR(20)  NOT NULL UNIQUE,
    quantity           INT UNSIGNED NOT NULL DEFAULT 1,
    available_quantity INT UNSIGNED NOT NULL DEFAULT 1,
    created_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_book_qty CHECK (quantity >= 1),
    CONSTRAINT chk_book_avail CHECK (available_quantity <= quantity)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- transactions : every issue / return
-- ------------------------------------------------------------
CREATE TABLE transactions (
    transaction_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    student_id     INT UNSIGNED NOT NULL,
    book_id        INT UNSIGNED NOT NULL,
    issue_date     DATE NOT NULL,
    due_date       DATE NOT NULL,
    return_date    DATE NULL,
    status         ENUM('Issued','Returned') NOT NULL DEFAULT 'Issued',
    fine           DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    CONSTRAINT fk_txn_student FOREIGN KEY (student_id)
        REFERENCES students(student_id) ON DELETE CASCADE,
    CONSTRAINT fk_txn_book FOREIGN KEY (book_id)
        REFERENCES books(book_id) ON DELETE CASCADE,
    CONSTRAINT chk_txn_dates CHECK (due_date >= issue_date),
    CONSTRAINT chk_txn_fine CHECK (fine >= 0),
    CONSTRAINT chk_txn_return CHECK (
        (status = 'Issued'   AND return_date IS NULL) OR
        (status = 'Returned' AND return_date IS NOT NULL))
) ENGINE=InnoDB;

CREATE INDEX idx_txn_student ON transactions(student_id);
CREATE INDEX idx_txn_book    ON transactions(book_id);
CREATE INDEX idx_txn_status  ON transactions(status);

-- ============================================================
--  SAMPLE DATA
-- ============================================================

-- Accounts
-- admin   / admin123     (Librarian)
-- STU001  / student123   (Aarav Sharma)
INSERT INTO users (username, password_hash, role, full_name, student_id) VALUES
('admin',
 'scrypt:32768:8:1$MwunEFIAF2fgcQJN$5c020c8b84ba87f61a0679f9fb7ce065256532ae51ee5c4939d5eb640021c027bf3d4dda11e1ae2db0aec366384792ca38e1fe4d685e0147fb3d6b456c35d4c6',
 'admin', 'Head Librarian', NULL);

-- 5 students
INSERT INTO students (student_code, name, email, phone, branch, year) VALUES
('STU001', 'Aarav Sharma',    'aarav.sharma@college.edu',  '9876500001', 'Computer Science', 2),
('STU002', 'Priya Verma',     'priya.verma@college.edu',   '9876500002', 'Computer Science', 3),
('STU003', 'Rohan Singh',     'rohan.singh@college.edu',   '9876500003', 'Electronics',      1),
('STU004', 'Sneha Gupta',     'sneha.gupta@college.edu',   '9876500004', 'Information Tech', 4),
('STU005', 'Mohammad Imran',  'imran.m@college.edu',       '9876500005', 'Mechanical',       2);

-- Student login account (for STU001)
INSERT INTO users (username, password_hash, role, full_name, student_id) VALUES
('STU001',
 'scrypt:32768:8:1$Wl68XwGpHcBCWu52$920fc35f8ce13bb7b35c70b990e69aa08f0026c2084d947fd30ffe19855adf0bb4b6b5223d78bc508f8c45acfda2f5b3c8e0ac8b113f84b3689a38dfc3b9340e',
 'student', 'Aarav Sharma', 1);

-- 10 books  (quantity / available_quantity)
INSERT INTO books (title, author, category, isbn, quantity, available_quantity) VALUES
('Clean Code',                        'Robert C. Martin',   'Software Engineering', '9780132350884', 3, 2),
('Introduction to Algorithms',        'Thomas H. Cormen',   'Algorithms',           '9780262033848', 2, 1),
('Database System Concepts',          'Abraham Silberschatz','Databases',           '9780078022159', 2, 2),
('Computer Networks',                 'Andrew S. Tanenbaum','Networking',           '9780132126953', 2, 2),
('Operating System Concepts',         'Abraham Silberschatz','Operating Systems',   '9781118063330', 3, 3),
('Python Crash Course',               'Eric Matthes',       'Programming',          '9781593276034', 2, 1),
('The Pragmatic Programmer',          'Andrew Hunt',        'Software Engineering', '9780135957059', 2, 2),
('Digital Logic and Computer Design', 'M. Morris Mano',     'Computer Architecture','9780132774758', 2, 2),
('Wings of Fire',                     'A. P. J. Abdul Kalam','Biography',           '9788173711466', 3, 3),
('The God of Small Things',           'Arundhati Roy',      'Fiction',              '9780006550686', 2, 2);

-- Transactions
-- T1: Aarav   - Python Crash Course   issued 20 days ago, due 6 days ago  -> OVERDUE (still out)
-- T2: Priya   - Clean Code            issued 5 days ago,  due in 9 days   -> Issued
-- T3: Rohan   - Intro to Algorithms   issued 30 days ago, returned 10 days ago, 6 days late -> Returned, fine Rs.30
-- T4: Sneha   - Intro to Algorithms   issued 3 days ago,  due in 11 days  -> Issued
-- T5: Sneha   - Wings of Fire         issued 10 days ago, returned 1 day ago, 2 days late -> Returned, fine Rs.10
INSERT INTO transactions (student_id, book_id, issue_date, due_date, return_date, status, fine) VALUES
(1, 6, DATE_SUB(CURDATE(), INTERVAL 20 DAY), DATE_SUB(CURDATE(), INTERVAL 6 DAY),  NULL,                                   'Issued',   0.00),
(2, 1, DATE_SUB(CURDATE(), INTERVAL 5 DAY),  DATE_ADD(CURDATE(), INTERVAL 9 DAY),  NULL,                                   'Issued',   0.00),
(3, 2, DATE_SUB(CURDATE(), INTERVAL 30 DAY), DATE_SUB(CURDATE(), INTERVAL 16 DAY), DATE_SUB(CURDATE(), INTERVAL 10 DAY),  'Returned', 30.00),
(4, 2, DATE_SUB(CURDATE(), INTERVAL 3 DAY),  DATE_ADD(CURDATE(), INTERVAL 11 DAY), NULL,                                   'Issued',   0.00),
(4, 9, DATE_SUB(CURDATE(), INTERVAL 10 DAY), DATE_SUB(CURDATE(), INTERVAL 3 DAY),  DATE_SUB(CURDATE(), INTERVAL 1 DAY),   'Returned', 10.00);

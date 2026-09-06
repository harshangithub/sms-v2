import os
import csv
import sqlite3
from collections import defaultdict
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox


DB_FILE = "sms.db"
SUBJECT_FIELDS = [
    ("physics", "Physics"),
    ("chemistry", "Chemistry"),
    ("maths", "Maths"),
    ("english", "English"),
    ("computer_science", "Computer Science"),
]


class DatabaseManager:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._initialize_database()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _create_students_table(self, cursor, table_name="students"):
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roll_no TEXT UNIQUE NOT NULL,
                student_name TEXT NOT NULL,
                class_name TEXT NOT NULL,
                section TEXT NOT NULL,
                physics_marks REAL NOT NULL,
                chemistry_marks REAL NOT NULL,
                maths_marks REAL NOT NULL,
                english_marks REAL NOT NULL,
                computer_science_marks REAL NOT NULL,
                total_marks REAL NOT NULL,
                average_marks REAL NOT NULL,
                overall_rank INTEGER DEFAULT 0
            )
            """
        )

    def _initialize_database(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS admin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    password TEXT NOT NULL
                )
                """
            )

            students_table = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='students'"
            ).fetchone()
            if not students_table:
                self._create_students_table(cursor)
            else:
                self._migrate_students_table(cursor)

            admin_count = cursor.execute("SELECT COUNT(*) FROM admin").fetchone()[0]
            if admin_count == 0:
                cursor.execute("INSERT INTO admin (password) VALUES (?)", ("admin",))
            conn.commit()

    def _migrate_students_table(self, cursor):
        cols_info = cursor.execute("PRAGMA table_info(students)").fetchall()
        existing_cols = [col[1] for col in cols_info]
        target_cols = {
            "id",
            "roll_no",
            "student_name",
            "class_name",
            "section",
            "physics_marks",
            "chemistry_marks",
            "maths_marks",
            "english_marks",
            "computer_science_marks",
            "total_marks",
            "average_marks",
            "overall_rank",
        }
        legacy_cols = {"phone", "science_marks", "social_marks", "computer_marks"}

        if set(existing_cols) == target_cols:
            return

        if target_cols.issubset(set(existing_cols)) and not legacy_cols.intersection(existing_cols):
            return

        self._create_students_table(cursor, "students_new")

        def col_expr(primary, fallback=None, default="0"):
            if primary in existing_cols:
                return f"COALESCE({primary}, 0)"
            if fallback and fallback in existing_cols:
                return f"COALESCE({fallback}, 0)"
            return default

        physics_expr = col_expr("physics_marks", fallback="science_marks")
        chemistry_expr = col_expr("chemistry_marks", fallback="social_marks")
        maths_expr = col_expr("maths_marks")
        english_expr = col_expr("english_marks")
        computer_science_expr = col_expr("computer_science_marks", fallback="computer_marks")

        total_expr = (
            "COALESCE(total_marks, 0)"
            if "total_marks" in existing_cols
            else f"(({physics_expr}) + ({chemistry_expr}) + ({maths_expr}) + ({english_expr}) + ({computer_science_expr}))"
        )
        average_expr = (
            "COALESCE(average_marks, 0)"
            if "average_marks" in existing_cols
            else f"(({total_expr}) / 5.0)"
        )
        rank_expr = "COALESCE(overall_rank, 0)" if "overall_rank" in existing_cols else "0"

        cursor.execute(
            f"""
            INSERT INTO students_new (
                id, roll_no, student_name, class_name, section,
                physics_marks, chemistry_marks, maths_marks, english_marks,
                computer_science_marks, total_marks, average_marks, overall_rank
            )
            SELECT
                id,
                COALESCE(roll_no, ''),
                COALESCE(student_name, ''),
                COALESCE(class_name, ''),
                COALESCE(section, ''),
                {physics_expr},
                {chemistry_expr},
                {maths_expr},
                {english_expr},
                {computer_science_expr},
                {total_expr},
                {average_expr},
                {rank_expr}
            FROM students
            """
        )
        cursor.execute("DROP TABLE students")
        cursor.execute("ALTER TABLE students_new RENAME TO students")

    def verify_admin_password(self, password):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password FROM admin ORDER BY id LIMIT 1"
            ).fetchone()
            return bool(row and row[0] == password)

    def update_admin_password(self, new_password):
        with self._connect() as conn:
            conn.execute(
                "UPDATE admin SET password = ? WHERE id = (SELECT id FROM admin ORDER BY id LIMIT 1)",
                (new_password,),
            )
            conn.commit()

    def _calculate_totals(self, student):
        total = sum(float(student[f"{subject}_marks"]) for subject, _ in SUBJECT_FIELDS)
        average = round(total / len(SUBJECT_FIELDS), 2)
        return round(total, 2), average

    def add_student(self, student):
        student["total_marks"], student["average_marks"] = self._calculate_totals(student)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO students (
                        roll_no, student_name, class_name, section,
                        physics_marks, chemistry_marks, maths_marks, english_marks,
                        computer_science_marks, total_marks, average_marks
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        student["roll_no"],
                        student["student_name"],
                        student["class_name"],
                        student["section"],
                        student["physics_marks"],
                        student["chemistry_marks"],
                        student["maths_marks"],
                        student["english_marks"],
                        student["computer_science_marks"],
                        student["total_marks"],
                        student["average_marks"],
                    ),
                )
                conn.commit()
            self.recalculate_rankings()
            return True, "Student added successfully."
        except sqlite3.IntegrityError:
            return False, "Roll number already exists."

    def add_students_bulk(self, students):
        if not students:
            return 0

        prepared = []
        for student in students:
            total_marks, average_marks = self._calculate_totals(student)
            prepared.append(
                (
                    student["roll_no"],
                    student["student_name"],
                    student["class_name"],
                    student["section"],
                    student["physics_marks"],
                    student["chemistry_marks"],
                    student["maths_marks"],
                    student["english_marks"],
                    student["computer_science_marks"],
                    total_marks,
                    average_marks,
                )
            )

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO students (
                    roll_no, student_name, class_name, section,
                    physics_marks, chemistry_marks, maths_marks, english_marks,
                    computer_science_marks, total_marks, average_marks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                prepared,
            )
            conn.commit()

        self.recalculate_rankings()
        return len(prepared)

    def find_existing_roll_numbers(self, roll_numbers):
        unique_rolls = sorted({roll.strip() for roll in roll_numbers if roll and roll.strip()})
        if not unique_rolls:
            return set()

        placeholders = ", ".join("?" for _ in unique_rolls)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT roll_no FROM students WHERE roll_no IN ({placeholders})",
                unique_rolls,
            ).fetchall()
        return {row[0] for row in rows}

    def update_student(self, student_id, student):
        student["total_marks"], student["average_marks"] = self._calculate_totals(student)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE students
                    SET roll_no=?, student_name=?, class_name=?, section=?,
                        physics_marks=?, chemistry_marks=?, maths_marks=?, english_marks=?,
                        computer_science_marks=?, total_marks=?, average_marks=?
                    WHERE id=?
                    """,
                    (
                        student["roll_no"],
                        student["student_name"],
                        student["class_name"],
                        student["section"],
                        student["physics_marks"],
                        student["chemistry_marks"],
                        student["maths_marks"],
                        student["english_marks"],
                        student["computer_science_marks"],
                        student["total_marks"],
                        student["average_marks"],
                        student_id,
                    ),
                )
                conn.commit()
            self.recalculate_rankings()
            return True, "Student updated successfully."
        except sqlite3.IntegrityError:
            return False, "Roll number already exists."

    def delete_student(self, student_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM students WHERE id=?", (student_id,))
            conn.commit()
        self.recalculate_rankings()

    def get_all_students(self):
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, roll_no, student_name, class_name, section,
                       physics_marks, chemistry_marks, maths_marks, english_marks,
                       computer_science_marks, total_marks, average_marks, overall_rank
                FROM students
                ORDER BY overall_rank ASC, student_name ASC
                """
            )
            return cursor.fetchall()

    def search_students(self, field, value):
        field_map = {
            "Roll Number": "roll_no",
            "Name": "student_name",
            "Class": "class_name",
            "Section": "section",
        }
        column = field_map.get(field)
        if not column:
            return []
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT id, roll_no, student_name, class_name, section,
                       physics_marks, chemistry_marks, maths_marks, english_marks,
                       computer_science_marks, total_marks, average_marks, overall_rank
                FROM students
                WHERE {column} LIKE ?
                ORDER BY overall_rank ASC, student_name ASC
                """,
                (f"%{value.strip()}%",),
            )
            return cursor.fetchall()

    def get_student_by_id(self, student_id):
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, roll_no, student_name, class_name, section,
                       physics_marks, chemistry_marks, maths_marks, english_marks,
                       computer_science_marks, total_marks, average_marks, overall_rank
                FROM students
                WHERE id=?
                """,
                (student_id,),
            )
            return cursor.fetchone()

    def recalculate_rankings(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, average_marks FROM students ORDER BY average_marks DESC, student_name ASC"
            ).fetchall()
            previous_avg = None
            current_rank = 0
            for index, (student_id, avg) in enumerate(rows, start=1):
                if previous_avg is None or float(avg) < float(previous_avg):
                    current_rank = index
                    previous_avg = avg
                conn.execute(
                    "UPDATE students SET overall_rank=? WHERE id=?",
                    (current_rank, student_id),
                )
            conn.commit()

    def get_statistics(self):
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
            school_avg = conn.execute(
                "SELECT COALESCE(ROUND(AVG(average_marks), 2), 0) FROM students"
            ).fetchone()[0]
            topper = conn.execute(
                """
                SELECT student_name, class_name, average_marks
                FROM students
                ORDER BY average_marks DESC, student_name ASC
                LIMIT 1
                """
            ).fetchone()
            if topper:
                topper_text = f"{topper[0]} (Class {topper[1]}) - {topper[2]}"
            else:
                topper_text = "N/A"
            return {
                "total_students": total,
                "school_average": school_avg,
                "topper": topper_text,
            }

    def export_students_to_csv(self, file_path):
        headers = [
            "Roll No",
            "Name",
            "Class",
            "Section",
            "Physics",
            "Chemistry",
            "Maths",
            "English",
            "Computer Science",
            "Total Marks",
            "Average",
            "Rank",
        ]
        rows = self.get_all_students()
        with open(file_path, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row[1:])


class LoginWindow:
    def __init__(self, root, db_manager):
        self.root = root
        self.db = db_manager
        self.dashboard = None
        self.root.title("Student Management System")
        self.root.geometry("460x300")
        self.root.minsize(430, 280)
        self.root.configure(bg="#f4f6f9")
        self._setup_style()
        self._build_ui()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Card.TFrame", background="white")
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), background="white")
        style.configure("SubTitle.TLabel", font=("Segoe UI", 10), background="white")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))

    def _build_ui(self):
        container = ttk.Frame(self.root, style="Card.TFrame", padding=24)
        container.pack(expand=True, fill="both", padx=24, pady=24)

        ttk.Label(container, text="Student Management System", style="Title.TLabel").pack(
            pady=(0, 8)
        )
        ttk.Label(
            container,
            text="Enter admin password or continue as student",
            style="SubTitle.TLabel",
        ).pack(pady=(0, 16))

        ttk.Label(container, text="Admin Password:").pack(anchor="w")
        self.password_var = tk.StringVar()
        entry = ttk.Entry(container, textvariable=self.password_var, show="*")
        entry.pack(fill="x", pady=(4, 16))
        entry.focus_set()
        entry.bind("<Return>", lambda _event: self.admin_login())

        ttk.Button(
            container, text="Login as Admin", style="Primary.TButton", command=self.admin_login
        ).pack(fill="x", pady=(0, 8))
        ttk.Button(container, text="Login as Student", command=self.student_login).pack(fill="x")

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status, anchor="w", relief="sunken").pack(
            side="bottom", fill="x"
        )

    def admin_login(self):
        password = self.password_var.get().strip()
        if not password:
            messagebox.showerror("Login Failed", "Please enter admin password.")
            return
        if self.db.verify_admin_password(password):
            self.status.set("Admin login successful")
            self._open_dashboard(AdminDashboard)
        else:
            self.status.set("Invalid admin password")
            messagebox.showerror("Login Failed", "Invalid admin password.")

    def student_login(self):
        self.status.set("Student login successful")
        self._open_dashboard(StudentDashboard)

    def _open_dashboard(self, dashboard_cls):
        if self.dashboard and self.dashboard.winfo_exists():
            self._focus_window(self.dashboard)
            return
        self.root.withdraw()
        self.dashboard = dashboard_cls(self.root, self.db, on_logout=self.logout)
        self._focus_window(self.dashboard)

    def _focus_window(self, window):
        if not window or not window.winfo_exists():
            return
        window.lift()
        try:
            window.focus_force()
        except tk.TclError:
            pass

    def logout(self):
        if self.dashboard and self.dashboard.winfo_exists():
            self.dashboard.destroy()
        self.dashboard = None
        self.password_var.set("")
        self.root.deiconify()
        self._focus_window(self.root)
        self.status.set("Ready")


class BaseDashboard(tk.Toplevel):
    def __init__(self, master, db_manager, title, can_manage=False, on_logout=None):
        super().__init__(master)
        self.db = db_manager
        self.can_manage = can_manage
        self.on_logout = on_logout
        self.title(title)
        self.geometry("1200x700")
        self.minsize(980, 580)
        self.configure(bg="#eef1f5")
        self.protocol("WM_DELETE_WINDOW", self.logout)
        self.status_var = tk.StringVar(value="Ready")
        self.search_field = tk.StringVar(value="Name")
        self.search_text = tk.StringVar()
        self.sort_states = {}
        self._build_ui()
        self.refresh_table()
        self._bind_shortcuts()

    def _build_ui(self):
        main = ttk.Frame(self, padding=14)
        main.pack(expand=True, fill="both")

        stats_frame = ttk.LabelFrame(main, text="Dashboard Statistics", padding=10)
        stats_frame.pack(fill="x", pady=(0, 10))

        self.total_label = ttk.Label(stats_frame, text="Total Students: 0")
        self.total_label.grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.topper_label = ttk.Label(stats_frame, text="Class Topper: N/A")
        self.topper_label.grid(row=0, column=1, padx=6, pady=4, sticky="w")
        self.avg_label = ttk.Label(stats_frame, text="Average School Score: 0")
        self.avg_label.grid(row=0, column=2, padx=6, pady=4, sticky="w")

        controls = ttk.Frame(main)
        controls.pack(fill="x", pady=(0, 10))

        ttk.Label(controls, text="Search By:").pack(side="left", padx=(0, 6))
        ttk.Combobox(
            controls,
            textvariable=self.search_field,
            values=["Roll Number", "Name", "Class", "Section"],
            width=14,
            state="readonly",
        ).pack(side="left", padx=(0, 8))

        search_entry = ttk.Entry(controls, textvariable=self.search_text, width=28)
        search_entry.pack(side="left", padx=(0, 8))
        search_entry.bind("<Return>", lambda _event: self.search_students())

        ttk.Button(controls, text="Search", command=self.search_students).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(controls, text="Show All", command=self.refresh_table).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="View Report Card", command=self.view_report_card).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(controls, text="Export CSV", command=self.export_csv).pack(side="left", padx=(0, 6))

        if self.can_manage:
            ttk.Button(controls, text="Add Student", command=self.add_student).pack(
                side="right", padx=(6, 0)
            )
            ttk.Button(controls, text="Add Multiple Students", command=self.add_multiple_students).pack(
                side="right", padx=(6, 0)
            )
            ttk.Button(controls, text="Edit Student", command=self.edit_student).pack(
                side="right", padx=(6, 0)
            )
            ttk.Button(controls, text="Delete Student", command=self.delete_student).pack(
                side="right", padx=(6, 0)
            )

        table_frame = ttk.Frame(main)
        table_frame.pack(expand=True, fill="both")

        columns = ["id", "roll", "name", "class", "section", "total", "average", "rank"]
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headers = {
            "id": "ID",
            "roll": "Roll No",
            "name": "Name",
            "class": "Class",
            "section": "Section",
            "total": "Total",
            "average": "Average",
            "rank": "Rank",
        }
        widths = {
            "id": 60,
            "roll": 120,
            "name": 220,
            "class": 100,
            "section": 100,
            "total": 100,
            "average": 100,
            "rank": 80,
        }
        for col in columns:
            self.tree.heading(col, text=headers[col], command=lambda c=col: self.sort_tree(c))
            self.tree.column(col, width=widths[col], anchor="center")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        bottom = ttk.Frame(main)
        bottom.pack(fill="x", pady=(10, 0))
        if self.can_manage:
            ttk.Button(bottom, text="Change Password", command=self.change_password).pack(
                side="left", padx=(0, 8)
            )
        ttk.Button(bottom, text="Refresh Rankings", command=self.recalculate_rankings).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(bottom, text="Logout", command=self.logout).pack(side="right")

        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w").pack(
            side="bottom", fill="x"
        )

    def _bind_shortcuts(self):
        self.bind("<Control-f>", lambda _event: self.focus_search())
        self.bind("<Control-r>", lambda _event: self.refresh_table())
        if self.can_manage:
            self.bind("<Control-n>", lambda _event: self.add_student())
            self.bind("<Control-e>", lambda _event: self.edit_student())
            self.bind("<Delete>", lambda _event: self.delete_student())

    def focus_search(self):
        for child in self.winfo_children():
            for inner in child.winfo_children():
                if isinstance(inner, ttk.Entry):
                    inner.focus_set()
                    return

    def _close(self):
        self.logout()

    def logout(self):
        if callable(self.on_logout):
            self.on_logout()
            return
        self.destroy()

    def refresh_table(self):
        students = self.db.get_all_students()
        self._populate(students)
        self._update_stats()
        self.status_var.set(f"Loaded {len(students)} student(s)")

    def search_students(self):
        value = self.search_text.get().strip()
        if not value:
            self.refresh_table()
            return
        students = self.db.search_students(self.search_field.get(), value)
        self._populate(students)
        self.status_var.set(f"Found {len(students)} result(s)")

    def _populate(self, rows):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    f"{float(row[10]):.2f}",
                    f"{float(row[11]):.2f}",
                    row[12],
                ),
            )

    def _update_stats(self):
        stats = self.db.get_statistics()
        self.total_label.configure(text=f"Total Students: {stats['total_students']}")
        self.topper_label.configure(text=f"Class Topper: {stats['topper']}")
        self.avg_label.configure(text=f"Average School Score: {stats['school_average']}")

    def get_selected_student_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selection Required", "Please select a student first.")
            return None
        return int(self.tree.item(selected[0], "values")[0])

    def add_student(self):
        StudentForm(self, self.db, on_save=self.refresh_table)

    def add_multiple_students(self):
        messagebox.showinfo("Access Denied", "This action is only available for admin.")

    def edit_student(self):
        student_id = self.get_selected_student_id()
        if student_id is None:
            return
        student_data = self.db.get_student_by_id(student_id)
        if not student_data:
            messagebox.showerror("Error", "Selected student no longer exists.")
            self.refresh_table()
            return
        StudentForm(self, self.db, student_data=student_data, on_save=self.refresh_table)

    def delete_student(self):
        student_id = self.get_selected_student_id()
        if student_id is None:
            return
        confirm = messagebox.askyesno("Confirm Delete", "Delete selected student?")
        if not confirm:
            return
        self.db.delete_student(student_id)
        self.refresh_table()
        messagebox.showinfo("Deleted", "Student deleted successfully.")

    def recalculate_rankings(self):
        self.db.recalculate_rankings()
        self.refresh_table()
        messagebox.showinfo("Ranking Updated", "Rankings recalculated successfully.")

    def view_report_card(self):
        student_id = self.get_selected_student_id()
        if student_id is None:
            return
        student = self.db.get_student_by_id(student_id)
        if not student:
            messagebox.showerror("Error", "Selected student no longer exists.")
            self.refresh_table()
            return
        ReportCardWindow(self, student)

    def export_csv(self):
        file_name = f"students_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = os.path.join(os.getcwd(), file_name)
        self.db.export_students_to_csv(file_path)
        messagebox.showinfo("Export Complete", f"Data exported to:\n{file_path}")
        self.status_var.set("Student data exported to CSV")

    def change_password(self):
        messagebox.showinfo("Access Denied", "This action is only available for admin.")

    def sort_tree(self, col):
        reverse = self.sort_states.get(col, False)
        data = [(self.tree.set(item, col), item) for item in self.tree.get_children("")]

        def _convert(value):
            try:
                return float(value)
            except (ValueError, TypeError):
                return str(value).lower()

        data.sort(key=lambda x: _convert(x[0]), reverse=reverse)
        for index, (_val, item) in enumerate(data):
            self.tree.move(item, "", index)
        self.sort_states[col] = not reverse


class AdminDashboard(BaseDashboard):
    def __init__(self, master, db_manager, on_logout=None):
        super().__init__(
            master, db_manager, "Admin Dashboard", can_manage=True, on_logout=on_logout
        )
        self.status_var.set("Admin dashboard ready")

    def add_multiple_students(self):
        MultipleStudentsWindow(self, self.db, on_save=self.refresh_table)

    def change_password(self):
        ChangePasswordWindow(self, self.db)


class StudentDashboard(BaseDashboard):
    def __init__(self, master, db_manager, on_logout=None):
        super().__init__(
            master, db_manager, "Student Dashboard", can_manage=False, on_logout=on_logout
        )
        self.status_var.set("Student dashboard ready")


class ManagedChildWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.parent = master
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.close_window)

    def close_window(self):
        self.destroy()
        if self.parent and self.parent.winfo_exists():
            self.parent.lift()
            try:
                self.parent.focus_force()
            except tk.TclError:
                pass


class StudentForm(ManagedChildWindow):
    def __init__(self, master, db_manager, student_data=None, on_save=None):
        super().__init__(master)
        self.db = db_manager
        self.student_data = student_data
        self.on_save = on_save
        self.title("Edit Student" if student_data else "Add Student")
        self.geometry("520x590")
        self.minsize(500, 560)
        self.resizable(True, True)
        self.vars = {}
        self._build_ui()
        if self.student_data:
            self._populate_form()

    def _build_ui(self):
        container = ttk.Frame(self, padding=16)
        container.pack(expand=True, fill="both")

        fields = [
            ("roll_no", "Roll No"),
            ("student_name", "Name"),
            ("class_name", "Class"),
            ("section", "Section"),
            ("physics_marks", "Physics Marks"),
            ("chemistry_marks", "Chemistry Marks"),
            ("maths_marks", "Maths Marks"),
            ("english_marks", "English Marks"),
            ("computer_science_marks", "Computer Science Marks"),
        ]

        for index, (key, label) in enumerate(fields):
            ttk.Label(container, text=label + ":").grid(row=index, column=0, sticky="w", pady=6)
            var = tk.StringVar()
            self.vars[key] = var
            entry = ttk.Entry(container, textvariable=var)
            entry.grid(row=index, column=1, sticky="ew", pady=6)

        container.columnconfigure(1, weight=1)

        button_frame = ttk.Frame(container)
        button_frame.grid(row=len(fields), column=0, columnspan=2, pady=18, sticky="e")
        ttk.Button(button_frame, text="Save", command=self.save).pack(side="left", padx=(0, 8))
        ttk.Button(button_frame, text="Cancel", command=self.close_window).pack(side="left")

    def _populate_form(self):
        self.vars["roll_no"].set(self.student_data[1])
        self.vars["student_name"].set(self.student_data[2])
        self.vars["class_name"].set(self.student_data[3])
        self.vars["section"].set(self.student_data[4])
        self.vars["physics_marks"].set(self.student_data[5])
        self.vars["chemistry_marks"].set(self.student_data[6])
        self.vars["maths_marks"].set(self.student_data[7])
        self.vars["english_marks"].set(self.student_data[8])
        self.vars["computer_science_marks"].set(self.student_data[9])

    def _validate(self):
        required_fields = ["roll_no", "student_name", "class_name", "section"]
        for field in required_fields:
            if not self.vars[field].get().strip():
                return False, "Please fill all required fields."

        marks = {}
        for subject, _ in SUBJECT_FIELDS:
            key = f"{subject}_marks"
            value = self.vars[key].get().strip()
            if value == "":
                return False, "Please provide marks for all subjects."
            try:
                mark = float(value)
            except ValueError:
                return False, "Marks must be numeric values."
            if mark < 0 or mark > 100:
                return False, "Marks must be between 0 and 100."
            marks[key] = mark

        student = {
            "roll_no": self.vars["roll_no"].get().strip(),
            "student_name": self.vars["student_name"].get().strip(),
            "class_name": self.vars["class_name"].get().strip(),
            "section": self.vars["section"].get().strip(),
        }
        student.update(marks)
        return True, student

    def save(self):
        valid, payload = self._validate()
        if not valid:
            messagebox.showerror("Validation Error", payload)
            return
        if self.student_data:
            success, msg = self.db.update_student(self.student_data[0], payload)
        else:
            success, msg = self.db.add_student(payload)
        if success:
            if self.on_save:
                self.on_save()
            messagebox.showinfo("Success", msg)
            self.close_window()
        else:
            messagebox.showerror("Error", msg)


class MultipleStudentsWindow(ManagedChildWindow):
    def __init__(self, master, db_manager, on_save=None):
        super().__init__(master)
        self.db = db_manager
        self.on_save = on_save
        self.title("Add Multiple Students")
        self.geometry("1260x700")
        self.minsize(1100, 620)
        self.input_vars = {}
        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self, padding=12)
        main.pack(expand=True, fill="both")

        entry_frame = ttk.LabelFrame(main, text="Add Row", padding=10)
        entry_frame.pack(fill="x", pady=(0, 10))

        fields = [
            ("roll_no", "Roll No"),
            ("student_name", "Student Name"),
            ("class_name", "Class"),
            ("section", "Section"),
            ("physics_marks", "Physics Marks"),
            ("chemistry_marks", "Chemistry Marks"),
            ("maths_marks", "Maths Marks"),
            ("english_marks", "English Marks"),
            ("computer_science_marks", "Computer Science Marks"),
        ]

        for index, (key, label) in enumerate(fields):
            row = 0 if index < 5 else 1
            col = (index % 5) * 2
            ttk.Label(entry_frame, text=f"{label}:").grid(row=row, column=col, sticky="w", padx=4, pady=4)
            var = tk.StringVar()
            self.input_vars[key] = var
            ttk.Entry(entry_frame, textvariable=var, width=18).grid(
                row=row, column=col + 1, sticky="ew", padx=4, pady=4
            )

        for col in range(10):
            entry_frame.columnconfigure(col, weight=1)

        ttk.Button(entry_frame, text="Add Row", command=self.add_row).grid(
            row=2, column=9, sticky="e", padx=4, pady=(8, 0)
        )

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(0, 8))
        ttk.Button(buttons, text="Remove Selected Row", command=self.remove_selected_row).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(buttons, text="Clear All", command=self.clear_all_rows).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Save All Students", command=self.save_all_students).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(buttons, text="Close", command=self.close_window).pack(side="right")

        table_frame = ttk.Frame(main)
        table_frame.pack(expand=True, fill="both")

        self.columns = [
            "roll_no",
            "student_name",
            "class_name",
            "section",
            "physics_marks",
            "chemistry_marks",
            "maths_marks",
            "english_marks",
            "computer_science_marks",
        ]
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings", selectmode="extended")

        headers = {
            "roll_no": "Roll No",
            "student_name": "Student Name",
            "class_name": "Class",
            "section": "Section",
            "physics_marks": "Physics",
            "chemistry_marks": "Chemistry",
            "maths_marks": "Maths",
            "english_marks": "English",
            "computer_science_marks": "Computer Science",
        }
        widths = {
            "roll_no": 120,
            "student_name": 220,
            "class_name": 90,
            "section": 90,
            "physics_marks": 100,
            "chemistry_marks": 100,
            "maths_marks": 100,
            "english_marks": 100,
            "computer_science_marks": 140,
        }

        for col in self.columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=widths[col], anchor="center")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

    def _validate_student(self, student):
        required_fields = ["roll_no", "student_name", "class_name", "section"]
        for field in required_fields:
            if not student[field].strip():
                return "Required fields are missing."

        for subject, _ in SUBJECT_FIELDS:
            key = f"{subject}_marks"
            value = student[key]
            try:
                mark = float(value)
            except ValueError:
                return "Marks must be numeric values."
            if mark < 0 or mark > 100:
                return "Marks must be between 0 and 100."
            student[key] = mark
        return None

    def add_row(self):
        student = {key: var.get().strip() for key, var in self.input_vars.items()}
        error = self._validate_student(student)
        if error:
            messagebox.showerror("Validation Error", error)
            return

        self.tree.insert(
            "",
            "end",
            values=(
                student["roll_no"],
                student["student_name"],
                student["class_name"],
                student["section"],
                f"{student['physics_marks']:.2f}",
                f"{student['chemistry_marks']:.2f}",
                f"{student['maths_marks']:.2f}",
                f"{student['english_marks']:.2f}",
                f"{student['computer_science_marks']:.2f}",
            ),
        )

        for key, var in self.input_vars.items():
            if key in {"class_name", "section"}:
                continue
            var.set("")

    def remove_selected_row(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selection Required", "Please select at least one row.")
            return
        for item in selected:
            self.tree.delete(item)

    def clear_all_rows(self):
        if not self.tree.get_children():
            return
        if not messagebox.askyesno("Confirm", "Clear all pending rows?"):
            return
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _extract_rows(self):
        extracted = []
        errors = {}
        for index, item in enumerate(self.tree.get_children(), start=1):
            values = self.tree.item(item, "values")
            student = {
                "roll_no": str(values[0]).strip(),
                "student_name": str(values[1]).strip(),
                "class_name": str(values[2]).strip(),
                "section": str(values[3]).strip(),
                "physics_marks": str(values[4]).strip(),
                "chemistry_marks": str(values[5]).strip(),
                "maths_marks": str(values[6]).strip(),
                "english_marks": str(values[7]).strip(),
                "computer_science_marks": str(values[8]).strip(),
            }
            error = self._validate_student(student)
            if error:
                errors[item] = f"Row {index}: {error}"
            extracted.append((index, item, student))
        return extracted, errors

    def save_all_students(self):
        if not self.tree.get_children():
            messagebox.showwarning("No Data", "Please add at least one row before saving.")
            return

        rows, row_errors = self._extract_rows()

        roll_to_items = defaultdict(list)
        for row_number, item, student in rows:
            roll_to_items[student["roll_no"]].append((row_number, item))

        for roll, entries in roll_to_items.items():
            if len(entries) > 1:
                for row_number, item in entries:
                    row_errors[item] = f"Row {row_number}: Duplicate roll number '{roll}' in current batch."

        existing_rolls = self.db.find_existing_roll_numbers([student["roll_no"] for _, _, student in rows])
        for row_number, item, student in rows:
            if item in row_errors:
                continue
            if student["roll_no"] in existing_rolls:
                row_errors[item] = (
                    f"Row {row_number}: Roll number '{student['roll_no']}' already exists in database."
                )

        valid_students = [student for _, item, student in rows if item not in row_errors]
        added_count = 0
        if valid_students:
            try:
                added_count = self.db.add_students_bulk(valid_students)
            except sqlite3.IntegrityError:
                messagebox.showerror(
                    "Insert Error",
                    "Bulk insert failed due to duplicate roll numbers. Please review and try again.",
                )
                return

        for _, item, _student in rows:
            if item not in row_errors:
                self.tree.delete(item)

        if self.on_save:
            self.on_save()

        if row_errors:
            ordered_errors = [row_errors[item] for item in self.tree.get_children() if item in row_errors]
            remaining_errors = [msg for item, msg in row_errors.items() if item not in self.tree.get_children()]
            error_text = "\n".join(ordered_errors + remaining_errors)
            messagebox.showwarning(
                "Save Completed with Issues",
                f"Successfully added {added_count} student(s).\n\nIssues:\n{error_text}",
            )
        else:
            messagebox.showinfo("Success", f"Successfully added {added_count} student(s).")


class ReportCardWindow(ManagedChildWindow):
    def __init__(self, master, student):
        super().__init__(master)
        self.student = student
        self.title("Report Card")
        self.geometry("540x560")
        self.minsize(500, 520)
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=16)
        frame.pack(expand=True, fill="both")

        ttk.Label(frame, text="Student Report Card", font=("Segoe UI", 14, "bold")).pack(pady=(0, 10))
        details = (
            f"Roll Number: {self.student[1]}\n"
            f"Name: {self.student[2]}\n"
            f"Class: {self.student[3]}\n"
            f"Section: {self.student[4]}\n"
        )
        ttk.Label(frame, text=details, justify="left").pack(anchor="w", pady=(0, 10))

        marks_frame = ttk.LabelFrame(frame, text="Subject Marks", padding=10)
        marks_frame.pack(fill="x", pady=(0, 10))

        subject_labels = [label for _, label in SUBJECT_FIELDS]
        values = self.student[5:10]
        for index, (label, value) in enumerate(zip(subject_labels, values)):
            ttk.Label(marks_frame, text=f"{label}: {value}").grid(
                row=index, column=0, sticky="w", pady=2
            )

        total_marks = float(self.student[10])
        summary = (
            f"Total Marks: {total_marks:.2f}/500\n"
            f"Average Marks: {float(self.student[11]):.2f}\n"
            f"Overall Rank: {self.student[12]}"
        )
        ttk.Label(frame, text=summary, justify="left").pack(anchor="w", pady=(0, 12))

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x")
        ttk.Button(button_frame, text="Print Report Card", command=self.print_report).pack(
            side="left"
        )
        ttk.Button(button_frame, text="Close", command=self.close_window).pack(side="right")

    def print_report(self):
        file_name = f"report_card_{self.student[1]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path = os.path.join(os.getcwd(), file_name)
        subject_labels = [label for _, label in SUBJECT_FIELDS]
        values = self.student[5:10]
        total_marks = float(self.student[10])

        lines = [
            "=" * 46,
            "           STUDENT REPORT CARD",
            "=" * 46,
            f"Generated On: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}",
            "",
            f"Roll Number : {self.student[1]}",
            f"Name        : {self.student[2]}",
            f"Class       : {self.student[3]}",
            f"Section     : {self.student[4]}",
            "",
            "Subject Marks",
            "-" * 46,
        ]
        for label, value in zip(subject_labels, values):
            lines.append(f"{label:<20}: {value}")
        lines.extend(
            [
                "-" * 46,
                f"Total Marks         : {total_marks:.2f}/500",
                f"Average Marks       : {float(self.student[11]):.2f}",
                f"Overall Rank        : {self.student[12]}",
                "=" * 46,
            ]
        )

        with open(file_path, "w", encoding="utf-8") as report_file:
            report_file.write("\n".join(lines))

        messagebox.showinfo("Printed", f"Report card saved to:\n{file_path}")


class ChangePasswordWindow(ManagedChildWindow):
    def __init__(self, master, db_manager):
        super().__init__(master)
        self.db = db_manager
        self.title("Change Password")
        self.geometry("420x260")
        self.minsize(380, 240)
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=18)
        frame.pack(expand=True, fill="both")

        self.current = tk.StringVar()
        self.new_pass = tk.StringVar()
        self.confirm = tk.StringVar()

        ttk.Label(frame, text="Current Password:").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.current, show="*").grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="New Password:").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.new_pass, show="*").grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="Confirm Password:").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.confirm, show="*").grid(row=2, column=1, sticky="ew", pady=6)

        frame.columnconfigure(1, weight=1)

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=12)
        ttk.Button(buttons, text="Update", command=self.update_password).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Close", command=self.close_window).pack(side="left")

    def update_password(self):
        current = self.current.get().strip()
        new_pass = self.new_pass.get().strip()
        confirm = self.confirm.get().strip()

        if not self.db.verify_admin_password(current):
            messagebox.showerror("Error", "Current password is incorrect.")
            return
        if not new_pass:
            messagebox.showerror("Error", "New password cannot be empty.")
            return
        if new_pass != confirm:
            messagebox.showerror("Error", "Passwords do not match.")
            return

        self.db.update_admin_password(new_pass)
        messagebox.showinfo("Success", "Password updated successfully.")
        self.close_window()


def main():
    root = tk.Tk()
    db_manager = DatabaseManager()
    LoginWindow(root, db_manager)
    root.mainloop()


if __name__ == "__main__":
    main()

import os
import csv
import sqlite3
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox


DB_FILE = "sms.db"
SUBJECTS = ["english", "maths", "science", "social", "computer"]


class DatabaseManager:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._initialize_database()

    def _connect(self):
        return sqlite3.connect(self.db_path)

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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    roll_no TEXT UNIQUE NOT NULL,
                    student_name TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    section TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    english_marks REAL NOT NULL,
                    maths_marks REAL NOT NULL,
                    science_marks REAL NOT NULL,
                    social_marks REAL NOT NULL,
                    computer_marks REAL NOT NULL,
                    average_marks REAL NOT NULL,
                    overall_rank INTEGER DEFAULT 0
                )
                """
            )
            admin_count = cursor.execute("SELECT COUNT(*) FROM admin").fetchone()[0]
            if admin_count == 0:
                cursor.execute("INSERT INTO admin (password) VALUES (?)", ("admin",))
            conn.commit()

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

    def _calculate_average(self, student):
        total = sum(float(student[f"{subject}_marks"]) for subject in SUBJECTS)
        return round(total / len(SUBJECTS), 2)

    def add_student(self, student):
        student["average_marks"] = self._calculate_average(student)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO students (
                        roll_no, student_name, class_name, section, phone,
                        english_marks, maths_marks, science_marks, social_marks,
                        computer_marks, average_marks
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        student["roll_no"],
                        student["student_name"],
                        student["class_name"],
                        student["section"],
                        student["phone"],
                        student["english_marks"],
                        student["maths_marks"],
                        student["science_marks"],
                        student["social_marks"],
                        student["computer_marks"],
                        student["average_marks"],
                    ),
                )
                conn.commit()
            self.recalculate_rankings()
            return True, "Student added successfully."
        except sqlite3.IntegrityError:
            return False, "Roll number already exists."

    def update_student(self, student_id, student):
        student["average_marks"] = self._calculate_average(student)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE students
                    SET roll_no=?, student_name=?, class_name=?, section=?, phone=?,
                        english_marks=?, maths_marks=?, science_marks=?, social_marks=?,
                        computer_marks=?, average_marks=?
                    WHERE id=?
                    """,
                    (
                        student["roll_no"],
                        student["student_name"],
                        student["class_name"],
                        student["section"],
                        student["phone"],
                        student["english_marks"],
                        student["maths_marks"],
                        student["science_marks"],
                        student["social_marks"],
                        student["computer_marks"],
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
                SELECT id, roll_no, student_name, class_name, section, phone,
                       english_marks, maths_marks, science_marks, social_marks,
                       computer_marks, average_marks, overall_rank
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
                SELECT id, roll_no, student_name, class_name, section, phone,
                       english_marks, maths_marks, science_marks, social_marks,
                       computer_marks, average_marks, overall_rank
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
                SELECT id, roll_no, student_name, class_name, section, phone,
                       english_marks, maths_marks, science_marks, social_marks,
                       computer_marks, average_marks, overall_rank
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
            "Phone",
            "English",
            "Maths",
            "Science",
            "Social",
            "Computer",
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
            AdminDashboard(self.root, self.db)
        else:
            self.status.set("Invalid admin password")
            messagebox.showerror("Login Failed", "Invalid admin password.")

    def student_login(self):
        self.status.set("Student login successful")
        StudentDashboard(self.root, self.db)


class BaseDashboard(tk.Toplevel):
    def __init__(self, master, db_manager, title, can_manage=False):
        super().__init__(master)
        self.db = db_manager
        self.can_manage = can_manage
        self.title(title)
        self.geometry("1200x700")
        self.minsize(980, 580)
        self.configure(bg="#eef1f5")
        self.protocol("WM_DELETE_WINDOW", self._close)
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
            ttk.Button(controls, text="Edit Student", command=self.edit_student).pack(
                side="right", padx=(6, 0)
            )
            ttk.Button(controls, text="Delete Student", command=self.delete_student).pack(
                side="right", padx=(6, 0)
            )

        table_frame = ttk.Frame(main)
        table_frame.pack(expand=True, fill="both")

        columns = ["id", "roll", "name", "class", "section", "phone", "average", "rank"]
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headers = {
            "id": "ID",
            "roll": "Roll No",
            "name": "Name",
            "class": "Class",
            "section": "Section",
            "phone": "Phone",
            "average": "Average",
            "rank": "Rank",
        }
        widths = {
            "id": 60,
            "roll": 120,
            "name": 220,
            "class": 100,
            "section": 100,
            "phone": 140,
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
        ttk.Button(bottom, text="Close", command=self._close).pack(side="right")

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
                    row[5],
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
    def __init__(self, master, db_manager):
        super().__init__(master, db_manager, "Admin Dashboard", can_manage=True)
        self.status_var.set("Admin dashboard ready")

    def change_password(self):
        ChangePasswordWindow(self, self.db)


class StudentDashboard(BaseDashboard):
    def __init__(self, master, db_manager):
        super().__init__(master, db_manager, "Student Dashboard", can_manage=False)
        self.status_var.set("Student dashboard ready")


class StudentForm(tk.Toplevel):
    def __init__(self, master, db_manager, student_data=None, on_save=None):
        super().__init__(master)
        self.db = db_manager
        self.student_data = student_data
        self.on_save = on_save
        self.title("Edit Student" if student_data else "Add Student")
        self.geometry("520x620")
        self.minsize(500, 600)
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
            ("phone", "Phone Number"),
            ("english_marks", "English Marks"),
            ("maths_marks", "Maths Marks"),
            ("science_marks", "Science Marks"),
            ("social_marks", "Social Marks"),
            ("computer_marks", "Computer Marks"),
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
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="left")

    def _populate_form(self):
        self.vars["roll_no"].set(self.student_data[1])
        self.vars["student_name"].set(self.student_data[2])
        self.vars["class_name"].set(self.student_data[3])
        self.vars["section"].set(self.student_data[4])
        self.vars["phone"].set(self.student_data[5])
        self.vars["english_marks"].set(self.student_data[6])
        self.vars["maths_marks"].set(self.student_data[7])
        self.vars["science_marks"].set(self.student_data[8])
        self.vars["social_marks"].set(self.student_data[9])
        self.vars["computer_marks"].set(self.student_data[10])

    def _validate(self):
        required_fields = ["roll_no", "student_name", "class_name", "section", "phone"]
        for field in required_fields:
            if not self.vars[field].get().strip():
                return False, "Please fill all required fields."

        phone = self.vars["phone"].get().strip()
        if not phone.isdigit() or len(phone) < 7 or len(phone) > 15:
            return False, "Phone number must be 7 to 15 digits."

        marks = {}
        for subject in SUBJECTS:
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
            "phone": phone,
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
            self.destroy()
        else:
            messagebox.showerror("Error", msg)


class ReportCardWindow(tk.Toplevel):
    def __init__(self, master, student):
        super().__init__(master)
        self.student = student
        self.title("Report Card")
        self.geometry("540x540")
        self.minsize(500, 500)
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
        subject_labels = ["English", "Maths", "Science", "Social", "Computer"]
        values = self.student[6:11]
        for index, (label, value) in enumerate(zip(subject_labels, values)):
            ttk.Label(marks_frame, text=f"{label}: {value}").grid(
                row=index, column=0, sticky="w", pady=2
            )

        total_marks = sum(float(v) for v in values)
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
        ttk.Button(button_frame, text="Close", command=self.destroy).pack(side="right")

    def print_report(self):
        file_name = f"report_card_{self.student[1]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path = os.path.join(os.getcwd(), file_name)
        subject_labels = ["English", "Maths", "Science", "Social", "Computer"]
        values = self.student[6:11]
        total_marks = sum(float(v) for v in values)

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


class ChangePasswordWindow(tk.Toplevel):
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
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left")

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
        self.destroy()


def main():
    root = tk.Tk()
    db_manager = DatabaseManager()
    LoginWindow(root, db_manager)
    root.mainloop()


if __name__ == "__main__":
    main()

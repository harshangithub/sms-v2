# sms-v2

## Student Management System (Single File)

Run:

```bash
python student_management_system.py
```

This project currently ships as a complete single-file desktop app using Tkinter + SQLite3.

## Suggested Modular Split (next step)

- `database.py` → `DatabaseManager`
- `login.py` → `LoginWindow`
- `dashboards.py` → `AdminDashboard`, `StudentDashboard`
- `student_form.py` → `StudentForm`
- `report_card.py` → `ReportCardWindow`
- `change_password.py` → `ChangePasswordWindow`
- `main.py` → application bootstrap

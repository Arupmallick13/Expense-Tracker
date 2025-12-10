"""
Expense Tracker - Tkinter GUI
Single-file Python application demonstrating:
- User registration & login (SQLite)
- Add / Edit / Delete expenses
- Categories management (simple preset + add)
- Monthly summary and charts (Matplotlib embedded)
- Export CSV
- Budget alert

Run: python expense_tracker_tkinter.py
Dependencies: matplotlib, pandas (for CSV export, optional)
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import sqlite3
import hashlib
from datetime import datetime
import os
import csv
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

DB_PATH = 'expenses.db'

# ------------------------- Database Manager -------------------------
class DB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        cur = self.conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                budget REAL DEFAULT 0
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER,
                UNIQUE(name, user_id)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL
            )
        ''')
        self.conn.commit()
        # ensure some default categories
        defaults = ['Food','Transport','Shopping','Bills','Entertainment','Other']
        cur = self.conn.cursor()
        for cat in defaults:
            try:
                cur.execute('INSERT INTO categories (name, user_id) VALUES (?, NULL)', (cat,))
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()

    def add_user(self, username, password):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        cur = self.conn.cursor()
        try:
            cur.execute('INSERT INTO users (username, password_hash) VALUES (?,?)', (username, pw_hash))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def authenticate(self, username, password):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM users WHERE username = ? AND password_hash = ?', (username, pw_hash))
        row = cur.fetchone()
        return row

    def set_budget(self, user_id, amount):
        cur = self.conn.cursor()
        cur.execute('UPDATE users SET budget = ? WHERE id = ?', (amount, user_id))
        self.conn.commit()

    def get_budget(self, user_id):
        cur = self.conn.cursor()
        cur.execute('SELECT budget FROM users WHERE id=?', (user_id,))
        row = cur.fetchone()
        return row['budget'] if row else 0

    def add_category(self, name, user_id=None):
        cur = self.conn.cursor()
        try:
            cur.execute('INSERT INTO categories (name, user_id) VALUES (?,?)', (name, user_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_categories(self, user_id=None):
        cur = self.conn.cursor()
        # global categories (user_id NULL) + user categories
        if user_id is None:
            cur.execute('SELECT name FROM categories WHERE user_id IS NULL ORDER BY name')
        else:
            cur.execute('SELECT name FROM categories WHERE user_id IS NULL OR user_id = ? ORDER BY name', (user_id,))
        return [r['name'] for r in cur.fetchall()]

    def add_expense(self, user_id, amount, category, description, date):
        cur = self.conn.cursor()
        cur.execute('INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?,?,?,?,?)',
                    (user_id, amount, category, description, date))
        self.conn.commit()

    def update_expense(self, exp_id, amount, category, description, date):
        cur = self.conn.cursor()
        cur.execute('UPDATE expenses SET amount=?, category=?, description=?, date=? WHERE id=?',
                    (amount, category, description, date, exp_id))
        self.conn.commit()

    def delete_expense(self, exp_id):
        cur = self.conn.cursor()
        cur.execute('DELETE FROM expenses WHERE id=?', (exp_id,))
        self.conn.commit()

    def get_expenses(self, user_id):
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM expenses WHERE user_id=? ORDER BY date DESC', (user_id,))
        return cur.fetchall()

    def get_monthly_total(self, user_id, year, month):
        start = f"{year:04d}-{month:02d}-01"
        if month == 12:
            end = f"{year+1:04d}-01-01"
        else:
            end = f"{year:04d}-{month+1:02d}-01"
        cur = self.conn.cursor()
        cur.execute('SELECT SUM(amount) as total FROM expenses WHERE user_id=? AND date>=? AND date<?', (user_id, start, end))
        row = cur.fetchone()
        return row['total'] if row and row['total'] is not None else 0

    def get_category_summary(self, user_id, year, month):
        start = f"{year:04d}-{month:02d}-01"
        if month == 12:
            end = f"{year+1:04d}-01-01"
        else:
            end = f"{year:04d}-{month+1:02d}-01"
        cur = self.conn.cursor()
        cur.execute('SELECT category, SUM(amount) as total FROM expenses WHERE user_id=? AND date>=? AND date<? GROUP BY category', (user_id, start, end))
        return cur.fetchall()

# ------------------------- GUI -------------------------
class LoginWindow:
    def __init__(self, master, db: DB):
        self.master = master
        self.db = db
        self.master.title('Expense Tracker - Login')
        self.master.geometry('350x220')
        self.frame = ttk.Frame(master, padding=10)
        self.frame.pack(fill='both', expand=True)
        ttk.Label(self.frame, text='Username:').grid(row=0, column=0, sticky='w')
        self.username = ttk.Entry(self.frame)
        self.username.grid(row=0, column=1)
        ttk.Label(self.frame, text='Password:').grid(row=1, column=0, sticky='w')
        self.password = ttk.Entry(self.frame, show='*')
        self.password.grid(row=1, column=1)
        self.message = ttk.Label(self.frame, text='')
        self.message.grid(row=2, column=0, columnspan=2)
        ttk.Button(self.frame, text='Login', command=self.login).grid(row=3, column=0, pady=10)
        ttk.Button(self.frame, text='Register', command=self.register).grid(row=3, column=1)

    def login(self):
        u = self.username.get().strip()
        p = self.password.get().strip()
        if not u or not p:
            self.message.config(text='Enter username & password')
            return
        user = self.db.authenticate(u, p)
        if user:
            self.master.destroy()
            root = tk.Tk()
            app = MainApp(root, self.db, user['id'], user['username'])
            root.mainloop()
        else:
            self.message.config(text='Invalid credentials')

    def register(self):
        u = self.username.get().strip()
        p = self.password.get().strip()
        if not u or not p:
            self.message.config(text='Enter username & password')
            return
        ok = self.db.add_user(u, p)
        if ok:
            messagebox.showinfo('Success', 'User registered. Please login.')
        else:
            messagebox.showerror('Error', 'Username already exists')


class MainApp:
    def __init__(self, master, db: DB, user_id, username):
        self.master = master
        self.db = db
        self.user_id = user_id
        self.username = username
        master.title(f'Expense Tracker - {username}')
        master.geometry('900x600')
        self._build_ui()
        self.refresh_expenses()
        self.draw_summary()

    def _build_ui(self):
        self.paned = ttk.Panedwindow(self.master, orient='horizontal')
        self.paned.pack(fill='both', expand=True)
        # Left frame: controls & form
        left = ttk.Frame(self.paned, width=320, padding=10)
        right = ttk.Frame(self.paned, padding=10)
        self.paned.add(left, weight=0)
        self.paned.add(right, weight=1)

        # Form
        ttk.Label(left, text='Add / Edit Expense', font=('TkDefaultFont', 12, 'bold')).pack(anchor='w')
        form = ttk.Frame(left)
        form.pack(fill='x', pady=5)
        ttk.Label(form, text='Amount:').grid(row=0, column=0, sticky='w')
        self.amount_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.amount_var).grid(row=0, column=1)
        ttk.Label(form, text='Category:').grid(row=1, column=0, sticky='w')
        self.category_var = tk.StringVar()
        self.category_cb = ttk.Combobox(form, textvariable=self.category_var, values=self.db.get_categories(self.user_id))
        self.category_cb.grid(row=1, column=1)
        ttk.Label(form, text='Date (YYYY-MM-DD):').grid(row=2, column=0, sticky='w')
        self.date_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        ttk.Entry(form, textvariable=self.date_var).grid(row=2, column=1)
        ttk.Label(form, text='Description:').grid(row=3, column=0, sticky='w')
        self.desc_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.desc_var).grid(row=3, column=1)
        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill='x', pady=6)
        ttk.Button(btn_frame, text='Add Expense', command=self.add_expense).pack(side='left')
        ttk.Button(btn_frame, text='Update Selected', command=self.update_selected).pack(side='left')
        ttk.Button(btn_frame, text='Delete Selected', command=self.delete_selected).pack(side='left')

        ttk.Separator(left).pack(fill='x', pady=6)
        ttk.Button(left, text='Add Category', command=self.add_category).pack(fill='x')
        ttk.Button(left, text='Set Budget', command=self.set_budget).pack(fill='x', pady=3)
        ttk.Button(left, text='Export CSV', command=self.export_csv).pack(fill='x')

        # Right: Treeview of expenses and charts
        ttk.Label(right, text='Expenses', font=('TkDefaultFont', 12, 'bold')).pack(anchor='w')
        self.tree = ttk.Treeview(right, columns=('id','date','category','amount','description'), show='headings', selectmode='browse')
        self.tree.heading('id', text='ID')
        self.tree.column('id', width=40)
        self.tree.heading('date', text='Date')
        self.tree.heading('category', text='Category')
        self.tree.heading('amount', text='Amount')
        self.tree.heading('description', text='Description')
        self.tree.pack(fill='x')
        self.tree.bind('<<TreeviewSelect>>', self.on_select)

        # Summary & Charts
        self.summary_frame = ttk.LabelFrame(right, text='Monthly Summary')
        self.summary_frame.pack(fill='both', expand=True, pady=8)
        top_controls = ttk.Frame(self.summary_frame)
        top_controls.pack(fill='x')
        ttk.Label(top_controls, text='Year:').pack(side='left')
        self.year_var = tk.IntVar(value=datetime.now().year)
        ttk.Spinbox(top_controls, from_=2000, to=2100, textvariable=self.year_var, width=6, command=self.draw_summary).pack(side='left')
        ttk.Label(top_controls, text='Month:').pack(side='left')
        self.month_var = tk.IntVar(value=datetime.now().month)
        ttk.Spinbox(top_controls, from_=1, to=12, textvariable=self.month_var, width=4, command=self.draw_summary).pack(side='left')
        ttk.Button(top_controls, text='Refresh', command=self.draw_summary).pack(side='left', padx=6)

        # matplotlib figure placeholder
        self.fig = Figure(figsize=(5,3))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.summary_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0],'values')
        # id, date, category, amount, description
        self.amount_var.set(vals[3])
        self.category_var.set(vals[2])
        self.date_var.set(vals[1])
        self.desc_var.set(vals[4])

    def add_category(self):
        name = simpledialog.askstring('Category', 'New category name:')
        if not name:
            return
        ok = self.db.add_category(name.strip(), self.user_id)
        if ok:
            messagebox.showinfo('Success', 'Category added')
            self.category_cb['values'] = self.db.get_categories(self.user_id)
        else:
            messagebox.showwarning('Exists', 'Category already exists')

    def set_budget(self):
        val = simpledialog.askfloat('Budget', 'Monthly budget amount:', minvalue=0)
        if val is None:
            return
        self.db.set_budget(self.user_id, val)
        messagebox.showinfo('Saved', f'Budget set to {val}')
        self.draw_summary()

    def add_expense(self):
        try:
            amt = float(self.amount_var.get())
        except Exception:
            messagebox.showerror('Error', 'Enter valid amount')
            return
        cat = self.category_var.get().strip() or 'Other'
        date = self.date_var.get().strip()
        # validate date simple
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except Exception:
            messagebox.showerror('Error', 'Date must be YYYY-MM-DD')
            return
        desc = self.desc_var.get().strip()
        self.db.add_expense(self.user_id, amt, cat, desc, date)
        self.clear_form()
        self.refresh_expenses()
        self.draw_summary()
        # budget alert
        year = self.year_var.get()
        month = self.month_var.get()
        total = self.db.get_monthly_total(self.user_id, year, month)
        budget = self.db.get_budget(self.user_id)
        if budget > 0 and total > budget:
            messagebox.showwarning('Budget Exceeded', f'You have exceeded your budget of {budget:.2f} for {year}-{month:02d}. Total: {total:.2f}')

    def update_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select an expense to update')
            return
        exp_id = int(self.tree.item(sel[0],'values')[0])
        try:
            amt = float(self.amount_var.get())
        except Exception:
            messagebox.showerror('Error', 'Enter valid amount')
            return
        cat = self.category_var.get().strip() or 'Other'
        date = self.date_var.get().strip()
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except Exception:
            messagebox.showerror('Error', 'Date must be YYYY-MM-DD')
            return
        desc = self.desc_var.get().strip()
        self.db.update_expense(exp_id, amt, cat, desc, date)
        self.refresh_expenses()
        self.draw_summary()

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select an expense to delete')
            return
        exp_id = int(self.tree.item(sel[0],'values')[0])
        if messagebox.askyesno('Confirm', 'Delete selected expense?'):
            self.db.delete_expense(exp_id)
            self.refresh_expenses()
            self.draw_summary()

    def clear_form(self):
        self.amount_var.set('')
        self.category_var.set('')
        self.desc_var.set('')
        self.date_var.set(datetime.now().strftime('%Y-%m-%d'))

    def refresh_expenses(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        rows = self.db.get_expenses(self.user_id)
        for r in rows:
            self.tree.insert('', 'end', values=(r['id'], r['date'], r['category'], f"{r['amount']:.2f}", r['description'] or ''))

    def draw_summary(self):
        year = int(self.year_var.get())
        month = int(self.month_var.get())
        # category summary
        rows = self.db.get_category_summary(self.user_id, year, month)
        cats = [r['category'] for r in rows]
        vals = [r['total'] for r in rows]
        self.ax.clear()
        if vals:
            # pie chart
            self.ax.pie(vals, labels=cats, autopct='%1.1f%%')
            self.ax.set_title(f'Spending by Category — {year}-{month:02d}')
        else:
            self.ax.text(0.5,0.5,'No data for this month', ha='center')
        self.canvas.draw()
        # monthly total and budget
        total = self.db.get_monthly_total(self.user_id, year, month)
        budget = self.db.get_budget(self.user_id)
        # show as small label
        if hasattr(self, 'budget_label'):
            self.budget_label.destroy()
        self.budget_label = ttk.Label(self.summary_frame, text=f'Total: {total:.2f}   Budget: {budget:.2f}')
        self.budget_label.pack()

    def export_csv(self):
        rows = self.db.get_expenses(self.user_id)
        if not rows:
            messagebox.showinfo('No data', 'No expenses to export')
            return
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV','*.csv')])
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id','date','category','amount','description'])
            for r in rows:
                writer.writerow([r['id'], r['date'], r['category'], f"{r['amount']:.2f}", r['description'] or ''])
        # also show option to open in pandas and preview
        if messagebox.askyesno('Exported', 'Exported CSV. Open preview?'):
            try:
                df = pd.read_csv(path)
                top = tk.Toplevel(self.master)
                top.title('CSV Preview')
                txt = tk.Text(top, wrap='none')
                txt.pack(fill='both', expand=True)
                txt.insert('end', df.head(50).to_string())
            except Exception as e:
                messagebox.showerror('Error', str(e))


if __name__ == '__main__':
    db = DB()
    root = tk.Tk()
    LoginWindow(root, db)
    root.mainloop()

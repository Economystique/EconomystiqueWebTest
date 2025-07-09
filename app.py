import os, sys
import sqlite3
import json
import bcrypt
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory, send_file
from functools import wraps
from collections import defaultdict
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
import random
import torch
#from transformers import pipeline, GPTNeoForCausalLM, GPT2Tokenizer
import smtplib
from email.message import EmailMessage
#import webview 
#import threading
from dateutil.relativedelta import relativedelta
import calendar
import io
from collections import defaultdict
from statsmodels.tsa.holtwinters import ExponentialSmoothing

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = os.path.join('static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Month-to-Month Mapping
month_table_map = {
    'January': 'jan', 'February': 'feb', 'March': 'mar', 'April': 'apr',
    'May': 'may', 'June': 'jun', 'July': 'jul', 'August': 'aug',
    'September': 'sep', 'October': 'oct', 'November': 'nov', 'December': 'dec'
}

# Helper Functions
def get_db_connection():
    conn = sqlite3.connect(os.path.join('db', 'users_db.db'))
    conn.row_factory = sqlite3.Row
    return conn

def get_available_years():  
    db_path = os.path.join('db/salesdb', 'sales_yearly.db')
    years = []

    if not os.path.exists(db_path):
        return years

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sales_y2%'")
        tables = cursor.fetchall()
        for table in tables:
            name = table[0]
            if name.startswith("sales_y") and len(name) == 11:
                year = name[-4:]
                if year.isdigit():
                    years.append(year)
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    return sorted(years, reverse=True)

def get_month_total_from_db(year, month):
    db_path = os.path.join('db/salesdb/monthly', f'sales_m{year}.db')
    table_name = month_table_map.get(month)

    if not os.path.exists(db_path) or not table_name:
        return 0

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT SUM(sales_total) FROM {table_name}")
        result = cursor.fetchone()
        return result[0] if result and result[0] else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()

def get_year_totals_from_db(year):
    db_path = os.path.join('db/salesdb/monthly', f'sales_m{year}.db')
    if not os.path.exists(db_path):
        return [0] * 12

    totals = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for table_name in month_table_map.values():
            try:
                cursor.execute(f"SELECT SUM(sales_total) FROM {table_name}")
                result = cursor.fetchone()
                totals.append(result[0] if result and result[0] else 0)
            except sqlite3.Error:
                totals.append(0)
        return totals
    finally:
        conn.close()

# Login required decorator
def login_required(f): 
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_identifier = request.form['username']
        password = request.form['password'].encode('utf-8')
        
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT user_name, pw_hash FROM user_data WHERE user_name = ? OR email = ?", (login_identifier, login_identifier))
        result = cursor.fetchone()

        if result and bcrypt.checkpw(password, result['pw_hash'].encode('utf-8')):
            session['username'] = result['user_name']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')

        conn.close()    
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password'].encode('utf-8')
        confirm_password = request.form['confirm_password'].encode('utf-8')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('signup'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM user_data WHERE user_name = ? OR email = ?", (username, email))
        if cursor.fetchone():
            flash('Username or email already exists.', 'error')
            conn.close()
            return redirect(url_for('signup'))
        
        pw_hash = bcrypt.hashpw(password, bcrypt.gensalt())
        cursor.execute("INSERT INTO user_data (user_name, email, pw_hash, owner_name) VALUES (?, ?, ?, ?)",
                      (username, email, pw_hash.decode('utf-8'), username))
        conn.commit()
        conn.close()
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Dummy data for expired products
    near_expiry = [
        {'name': 'Milk', 'quantity': 45, 'expiry_date': '2024-03-15'},
        {'name': 'Yogurt', 'quantity': 30, 'expiry_date': '2024-03-16'},
        {'name': 'Bread', 'quantity': 25, 'expiry_date': '2024-03-14'},
        {'name': 'Fresh Juice', 'quantity': 20, 'expiry_date': '2024-03-15'},
        {'name': 'Cheese', 'quantity': 15, 'expiry_date': '2024-03-13'}
    ]

    #Dummy data for critical items
    critical_items = [
        {
            'name': 'Milk',
            'quantity': 45,
            
        },
        {
            'name': 'Milk',
            'quantity': 45,
            
        },
        {
            'name': 'Milk',
            'quantity': 45,
            
        },
        {
            'name': 'Milk',
            'quantity': 45,
            
        },{
            'name': 'Milk',
            'quantity': 45,
            
        }
    ]
    
    daily_sales = []
    labels = []

    for i in range(9, -1, -1):
        date_check = date.today() - timedelta(days=i)
        year = date_check.year
        month = date_check.strftime('%b').lower()
        day = date_check.day
        table_name = f"d0{day}" if day < 10 else f"d{day}"

        try:
            db_path = os.path.join(f'db/salesdb/daily/sales_d{year}', f'{month}_{year}.db')
            with sqlite3.connect(db_path) as dconn:
                dcursor = dconn.cursor()
                dcursor.execute(f"SELECT SUM(quantity_sold * price) FROM {table_name}")
                total = dcursor.fetchone()[0] or 0
        except Exception:
            total = 0

        labels.append(date_check.strftime('%b %d'))
        daily_sales.append(total)

    return render_template('dashboard.html',
                        labels=labels,
                        quantities=daily_sales,
                        near_expiry=near_expiry,
                        critical_items=critical_items)

@app.route('/api/top_least/<period>')
@login_required
def get_top_least_products(period):
    from collections import defaultdict

    # Get today's date
    today = date.today()
    thisYear = today.year
    thisMonth = today.month
    thisDay = today.day
    months = ("jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec")

    def compute_percentages(rows):
        result = []
        total = sum(row[2] * row[3] for row in rows)
        for row in rows:
            product_total = row[2] * row[3]
            percent = (product_total / total * 100) if total > 0 else 0
            result.append({
                'name': row[1],
                'percentage': percent,
                'sales_total': product_total
            })
        return result

    product_data = []

    try:
        if period == "daily":
            # Load from daily table
            db_name = f"{months[thisMonth-1]}_{thisYear}.db"
            db_path = os.path.join(f'db/salesdb/daily/sales_d{thisYear}', db_name)
            table = f'd0{thisDay}' if thisDay < 10 else f'd{thisDay}'

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT inv_id, inv_desc, quantity_sold, price FROM {table}")
                product_data = cursor.fetchall()

        elif period == "monthly":
            db_name = f"{months[thisMonth-1]}_{thisYear}.db"
            db_path = os.path.join(f'db/salesdb/daily/sales_d{thisYear}', db_name)
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                for day in range(1, thisDay + 1):
                    table = f'd0{day}' if day < 10 else f'd{day}'
                    try:
                        cursor.execute(f"SELECT inv_id, inv_desc, quantity_sold, price FROM {table}")
                        product_data.extend(cursor.fetchall())
                    except sqlite3.OperationalError:
                        continue

        elif period == "yearly":
            db_path = os.path.join('db/salesdb', 'sales_yearly.db')
            table = f'sales_y{thisYear}'

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT inv_id, inv_desc, quantity_sold, price FROM {table}")
                product_data = cursor.fetchall()

        else:
            return jsonify({'error': 'Invalid period'}), 400

        # Aggregate data by product
        summary = defaultdict(lambda: [None, 0, 0])  # inv_desc, qty, price

        for inv_id, inv_desc, qty, price in product_data:
            summary[inv_id][0] = inv_desc
            summary[inv_id][1] += qty
            summary[inv_id][2] = price

        rows = [(inv_id, data[0], data[1], data[2]) for inv_id, data in summary.items()]
        ranked = compute_percentages(rows)

        ranked_sorted = sorted(ranked, key=lambda x: x['percentage'], reverse=True)

        return jsonify({
            'best_sellers': [{'name': p['name'], 'rank': i + 1} for i, p in enumerate(ranked_sorted[:3])],
            'least_products': [{'name': p['name'], 'rank': i + 1} for i, p in enumerate(ranked_sorted[-3:][::-1])]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/products')
@login_required
def products():
    conn = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
    cursor = conn.cursor()
    
    # From Static
    cursor.execute("""
        SELECT inv_id, inv_desc, cat, sub_cat, unit, rop
        FROM inv_static
    """
    )
    invStatic = cursor.fetchall()
    
    # From Dynamic    
    cursor.execute("""
        SELECT inv_id, quantity FROM inv_dynamic
    """)
    invDynamic = cursor.fetchall()
    conn.close()
    
     # Sum quantities from inv_dynamic by inv_id
    quantity_map = defaultdict(float)
    for inv_id, quantity in invDynamic:
        quantity_map[inv_id] += quantity
    
    # Combine data
    merged_data = []
    for inv_id, inv_desc, cat, sub_cat, unit, rop in invStatic:
        total_qty = quantity_map.get(inv_id, 0)
        merged_data.append({
            "inv_id": inv_id,
            "inv_desc": inv_desc,
            "cat": cat,
            "sub_cat": sub_cat,
            "quantity": total_qty,
            "rop": rop,
            "unit": unit
        })
    
    # Extract categories
    categories = sorted(set(product['cat'] for product in merged_data))
    return render_template('products.html', products=merged_data, categories=categories)

#for manage button in inventory/products
@app.route('/manage')
def manage():
    conn = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
    cursor = conn.cursor()
    cursor.execute("SELECT inv_id, inv_desc, unit FROM inv_static")
    products = cursor.fetchall()
    
    # Get the next inventory ID
    cursor.execute("SELECT MAX(CAST(SUBSTR(inv_id, 5) AS INTEGER)) FROM inv_static")
    max_id = cursor.fetchone()[0]
    next_id = 1 if max_id is None else max_id + 1
    next_inv_id = f"INVa{next_id:05d}"
    
    conn.close()
    # products will be a list of tuples (inv_id, inv_desc, unit)
    return render_template('manage.html', products=products, next_inv_id=next_inv_id)

@app.route('/sales')
@login_required
def sales():
    conn = sqlite3.connect(os.path.join('db/salesdb', 'sales_now.db'))
    cursor = conn.cursor()

    # Daily Table
    cursor.execute("""
        SELECT inv_id, inv_desc, quantity_sold, price, sales_total
        FROM sales_today
    """)
    rows = cursor.fetchall()
    conn.close()

    sales_data = [
        {
            'inv_id': row[0],
            'inv_desc': row[1],
            'quantity_sold': row[2],
            'price': row[3],
            'sales_total': row[4],
        } for row in rows
    ]
    
    # Line Graph Data
    daily_sales = []
    labels = []

    for i in range(9, -1, -1):
        date_check = date.today() - timedelta(days=i)
        year = date_check.year
        month = date_check.strftime('%b').lower()
        day = date_check.day
        table_name = f"d0{day}" if day < 10 else f"d{day}"

        try:
            db_path = os.path.join(f'db/salesdb/daily/sales_d{year}', f'{month}_{year}.db')
            with sqlite3.connect(db_path) as dconn:
                dcursor = dconn.cursor()
                dcursor.execute(f"SELECT SUM(quantity_sold * price) FROM {table_name}")
                total = dcursor.fetchone()[0] or 0
        except Exception:
            total = 0

        labels.append(date_check.strftime('%b %d'))
        daily_sales.append(total)

    return render_template('sales.html', sales_data=sales_data, labels=labels, quantities=daily_sales)

@app.route('/api/sales/<period>')
@login_required
def get_sales_data(period):
    table_map = {
        'daily': 'sales_today',
        'monthly': 'sales_this_month',
        'yearly': 'sales_this_year'
    }

    months = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    
    dateTodayFull = date.today()
    thisYear = dateTodayFull.year
    thisMonth = dateTodayFull.month
    thisDay = dateTodayFull.day
    
    month_index = thisMonth - 1
    month_str = months[month_index]
    
    table_name = table_map.get(period)
    if not table_name:
        return jsonify({'error': 'Invalid period'}), 400
    
    # Daily
    if period == "daily":
        # Parse date
        date_param = request.args.get('date')
        try:
            if date_param:
                base_date = datetime.strptime(date_param, "%Y-%m-%d").date()
            else:
                base_date = date.today()
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400

        daily_sales = []
        labels = []

        for i in range(9, -1, -1):
            date_check = base_date - timedelta(days=i)
            year = date_check.year
            month = date_check.strftime('%b').lower()
            day = date_check.day
            table_name = f"d0{day}" if day < 10 else f"d{day}"

            try:
                db_path = os.path.join(f'db/salesdb/daily/sales_d{year}', f'{month}_{year}.db')
                with sqlite3.connect(db_path) as dconn:
                    dcursor = dconn.cursor()
                    dcursor.execute(f"SELECT SUM(quantity_sold * price) FROM {table_name}")
                    total = dcursor.fetchone()[0] or 0
            except Exception:
                total = 0

            labels.append(date_check.strftime('%b %d'))
            daily_sales.append(total)

        target_year = base_date.year
        target_month = base_date.strftime('%b').lower()
        target_day = base_date.day
        table_name = f"d0{target_day}" if target_day < 10 else f"d{target_day}"
        try:
            db_path = os.path.join(f'db/salesdb/daily/sales_d{target_year}', f'{target_month}_{target_year}.db')
            with sqlite3.connect(db_path) as tconn:
                tcursor = tconn.cursor()
                tcursor.execute(f"""
                    SELECT inv_id, inv_desc, quantity_sold, price, (quantity_sold * price) AS sales_total
                    FROM {table_name}
                """)
                rows = tcursor.fetchall()
        except Exception:
            rows = []

        result = [
            {
                'inv_id': row[0],
                'inv_desc': row[1],
                'quantity_sold': row[2],
                'price': row[3],
                'sales_total': row[4],
            } for row in rows
        ]

        return jsonify({
            'labels': labels,
            'quantities': daily_sales,
            'table': result
        })
        
    # Yearly
    elif period == 'yearly':
        # Get year
        selected_year = request.args.get('date', str(date.today().year))
        try:
            selected_year = int(selected_year)
        except ValueError:
            return jsonify({'error': 'Invalid year'}), 400

        db_path = os.path.join('db/salesdb', 'sales_yearly.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all available year tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sales_y%'")
        tables = [row[0] for row in cursor.fetchall()]

        available_years = sorted([int(name.replace('sales_y', '')) for name in tables])

        start_year = selected_year - 9
        years_to_check = [y for y in range(start_year, selected_year + 1) if y in available_years]

        yearly_sales = []
        labels = []

        for y in years_to_check:
            table = f"sales_y{y}"
            try:
                cursor.execute(f"SELECT SUM(quantity_sold * price) FROM {table}")
                total = cursor.fetchone()[0] or 0
            except Exception:
                total = 0

            yearly_sales.append(total)
            labels.append(str(y))

        result = []
        table_name = f"sales_y{selected_year}"
        if table_name in tables:
            cursor.execute(f"""
                SELECT inv_id, inv_desc, quantity_sold, price, sales_total
                FROM {table_name}
            """)
            rows = cursor.fetchall()
            result = [
                {
                    'inv_id': row[0],
                    'inv_desc': row[1],
                    'quantity_sold': row[2],
                    'price': row[3],
                    'sales_total': row[4],
                } for row in rows
            ]

        conn.close()

        return jsonify({
            'labels': labels,
            'quantities': yearly_sales,
            'table': result,
            'available_years': available_years
        })
    # Monthly
    elif period == 'monthly':
        # Get date param or default to current date
        date_param = request.args.get('date')
        if date_param:
            try:
                target_date = datetime.strptime(date_param, "%Y-%m")
                target_year = target_date.year
                target_month = target_date.month
            except ValueError:
                return jsonify({'error': 'Invalid date format'}), 400
        else:
            target_date = date.today()
            target_year = target_date.year
            target_month = target_date.month
        dConn = sqlite3.connect(os.path.join(f'db/salesdb/daily/sales_d{thisYear}', f'{month_str}_{thisYear}.db')) 
        dCursor = dConn.cursor()
        conn = sqlite3.connect(os.path.join('db/salesdb', 'sales_now.db'))
        cursor = conn.cursor()

        # Clear old data
        cursor.execute("DELETE FROM sales_this_month")
        sales_aggregate = {}

        # Summate all entries in the current month
        for x in range(1, thisDay + 1):
            table_name = f"d0{x}" if x < 10 else f"d{x}"
            dCursor.execute(f"""
                SELECT inv_id, inv_desc, SUM(quantity_sold), price
                FROM {table_name}
                GROUP BY inv_id
            """)
            temp_rows = dCursor.fetchall()
            
            for inv_id, inv_desc, qty_sold, price in temp_rows:
                if inv_id not in sales_aggregate:
                    sales_aggregate[inv_id] = [inv_desc, qty_sold, price]
                else:
                    sales_aggregate[inv_id][1] += qty_sold
        dConn.close()
        data_to_insert = [
            (inv_id, desc, qty, price)
            for inv_id, (desc, qty, price) in sales_aggregate.items()
        ]

        cursor.executemany("""
            INSERT INTO sales_this_month (inv_id, inv_desc, quantity_sold, price)
            VALUES (?, ?, ?, ?)
        """, data_to_insert)
        
        # Commit Changes to database
        conn.commit()
        
        # Get Monthly
        cursor.execute("""
            SELECT inv_id, inv_desc, quantity_sold, price, sales_total
            FROM sales_this_month
        """)
        rows = cursor.fetchall()

        conn.close()

        result = [
            {
                'inv_id': row[0],
                'inv_desc': row[1],
                'quantity_sold': row[2],
                'price': row[3],
                'sales_total': row[4],
            } for row in rows
        ]
        # Generate sales totals for the last 10 months
        monthly_sales = []
        month_labels = []
        sales_aggregate = defaultdict(lambda: [None, 0, 0])  # inv_desc, qty, price

        for i in range(9, -1, -1):
            date_check = date(target_year, target_month, 1) - relativedelta(months=i)
            y = date_check.year
            m = date_check.month
            m_str = date_check.strftime('%b').lower()
            db_path = os.path.join(f'db/salesdb/daily/sales_d{y}', f'{m_str}_{y}.db')
            label = f"{m_str.capitalize()} {y}"
            total = 0

            if os.path.exists(db_path):
                try:
                    with sqlite3.connect(db_path) as dConn:
                        dCursor = dConn.cursor()
                        days_in_month = calendar.monthrange(y, m)[1]
                        for day in range(1, days_in_month + 1):
                            table_name = f'd0{day}' if day < 10 else f'd{day}'
                            try:
                                dCursor.execute(f"SELECT inv_id, inv_desc, quantity_sold, price FROM {table_name}")
                                for inv_id, inv_desc, qty, price in dCursor.fetchall():
                                    sales_aggregate[inv_id][0] = inv_desc
                                    sales_aggregate[inv_id][1] += qty
                                    sales_aggregate[inv_id][2] = price
                                    total += qty * price
                            except sqlite3.OperationalError:
                                continue
                except Exception as e:
                    print(f"Error reading {db_path}: {e}")

            monthly_sales.append(total)
            month_labels.append(label)

        # prepare table result
        result = [
            {
                'inv_id': inv_id,
                'inv_desc': data[0],
                'quantity_sold': data[1],
                'price': data[2],
                'sales_total': data[1] * data[2]
            } for inv_id, data in sales_aggregate.items()
        ]

        return jsonify({
            'labels': month_labels,
            'quantities': monthly_sales,
            'table': result
        })

@app.route('/sales_forecast', methods=['GET'])
@login_required
def sales_forecast():
    product_id = request.args.get('product', type=int)

    # Load product list
    conn = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
    cur = conn.cursor()
    cur.execute("SELECT inv_id, inv_desc FROM inv_static")
    products = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    conn.close()

    selected = next((p for p in products if p['id'] == product_id), None)

    # If no product selected or invalid, return empty chart (for page load)
    if not product_id or not selected:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'labels': [],
                'actual_data': [],
                'forecast_data_full_line': []
            })
        return render_template('sales_forecast.html',
                               products=products,
                               selected_product_id=None,
                               labels=[],
                               actual_data=[],
                               forecast_data_full_line=[],
                               sales_trend_message=None)

    # Build time series from past 181 days including today
    today = datetime.today().date()
    dates = [today - timedelta(days=i) for i in range(180, -1, -1)]
    sales = []

    for d in dates:
        db_year = f"sales_d{d.year}"
        db_month = f"{d.strftime('%b').lower()}_{d.year}.db"
        db_path = os.path.join('db', 'salesdb', 'daily', db_year, db_month)
        table = f"d{d.day:02d}"
        total = 0
        if os.path.exists(db_path):
            try:
                with sqlite3.connect(db_path) as c:
                    cur = c.cursor()
                    cur.execute(f"SELECT SUM(sales_total) FROM {table} WHERE inv_id = ?", (product_id,))
                    res = cur.fetchone()
                    total = res[0] if res and res[0] else 0
            except sqlite3.Error:
                total = 0
        sales.append(total)

    # Build pandas Series
    ts = pd.Series(sales, index=pd.to_datetime(dates))

    # Holt-Winters forecast
    model = ExponentialSmoothing(ts, trend='add', seasonal=None)
    fit = model.fit(optimized=True)
    forecast = fit.forecast(6)  # Next 6 days

    # Build 13-day window: 6 past days + today + 6 future days
    past_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    actual_window_series = ts[ts.index.date >= past_7_days[0]]

    full_window = pd.concat([actual_window_series, forecast])
    labels = [d.strftime('%b %d').lower() for d in full_window.index.date]
    actual_data = actual_window_series.tolist()
    forecast_data_full_line = actual_data + forecast.tolist()

    # Return JSON for AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'labels': labels,
            'actual_data': actual_data,
            'forecast_data_full_line': forecast_data_full_line
        })

    # Return full HTML for normal request
    return render_template("sales_forecast.html",
                           products=products,
                           selected_product_id=product_id,
                           labels=labels,
                           actual_data=actual_data,
                           forecast_data_full_line=forecast_data_full_line,
                           sales_trend_message=None)

@app.route('/performance_comparison')
@login_required
def performance_comparison():
    months = list(month_table_map.keys())
    years = get_available_years()
    return render_template('performance_comparison.html', months=months, years=years)

@app.route('/get_performance_data')
@login_required
def get_performance_data():
    month = request.args.get('month')
    year = request.args.get('year')
    total = get_month_total_from_db(year, month)
    return jsonify({
        'labels': ['Total Sales'],
        'values': [total]
    })

@app.route('/get_year_performance_data')
@login_required
def get_year_performance_data():
    year = request.args.get('year')
    monthly_totals = get_year_totals_from_db(year)
    return jsonify({'monthly_totals': monthly_totals})

@app.route('/wastage')
@login_required
def wastage():
    # --- Fetch confirmed wastage records ---
    conn = sqlite3.connect(os.path.join('db', 'wastage_db.db'))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT waste_id, batch_id, inv_id, inv_desc, quantity, unit, waste_date, remark FROM wastages
    """)
    rows = cursor.fetchall()

    wastage_record = [
        {
            'waste_id': row[0],
            'batch_id': row[1],
            'inv_id': row[2],
            'inv_desc': row[3],
            'quantity': row[4],
            'unit': row[5],
            'waste_date': row[6],
            'remark': row[7]
        } for row in rows
    ]

    # --- Fetch unconfirmed wastage (cart) records ---
    cursor.execute("""
        SELECT waste_id, inv_id, inv_desc, batch_id, exp_date, quantity, unit, remark, waste_date
        FROM wastage_cart
    """)
    cart_rows = cursor.fetchall()
    conn.close()

    wastage_cart = [
        {
            'waste_id': row[0],
            'inv_id': row[1],
            'inv_desc': row[2],
            'batch_id': row[3],
            'exp_date': row[4],
            'quantity': row[5],
            'unit': row[6],
            'remark': row[7],
            'waste_date': row[8]
        } for row in cart_rows
    ]

    # --- Fetch inventory list from inv_static ---
    inv_conn = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
    inv_cursor = inv_conn.cursor()
    inv_cursor.execute("SELECT inv_id, inv_desc, unit FROM inv_static ORDER BY inv_id")
    inv_rows = inv_cursor.fetchall()
    inv_conn.close()

    inv_data = [
        {'inv_id': row[0], 'inv_desc': row[1], 'unit': row[2]} for row in inv_rows
    ]

    return render_template(
        'wastage.html',
        wastage_data=wastage_record,
        inv_data=inv_data,
        wastage_cart=wastage_cart
    )

#modal for declaring wastage
@app.route('/declare_wastage', methods=['POST'])
def declare_wastage():
    inv_id   = request.form['inv_id']
    quantity = float(request.form['quantity'])
    dec_date = request.form['dec_date']
    remark   = request.form.get('remark', '')

    # add DB + inventory shit logic here u got dis kim lessgow!
    # Olrayt leszgo!
    flash('Wastage recorded successfully!', 'success')
    return redirect(url_for('wastage'))

@app.route('/get_batches/<inv_id>')
@login_required
def get_batches(inv_id):
    conn = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT batch_id, exp_date, quantity, unit FROM inv_dynamic
        WHERE inv_id = ?
        ORDER BY exp_date ASC
    """, (inv_id,))
    rows = cursor.fetchall()
    conn.close()

    # Format results as list of dicts
    batch_data = [{'batch_id': row[0], 'exp_date': row[1], 'quantity': row[2], 'unit': row[3]} for row in rows]
    return jsonify(batch_data)

@app.route('/insert_wastage_cart', methods=['POST'])
@login_required
def insert_wastage_cart():
    data = request.get_json()
    inv_id     = data.get('inv_id')
    batch_id   = data.get('batch_id')
    quantity   = data.get('quantity')
    waste_date = data.get('dec_date')
    remark     = data.get('remark', '')

    try:
        # --- Validate available quantity in inv_dynamic ---
        conn_check = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
        cursor_check = conn_check.cursor()
        cursor_check.execute("""
            SELECT quantity FROM inv_dynamic
            WHERE inv_id = ? AND batch_id = ?
        """, (inv_id, batch_id))
        check_row = cursor_check.fetchone()
        conn_check.close()

        if not check_row:
            return jsonify({'success': False, 'error': 'Inventory batch not found'}), 400

        available_qty = check_row[0]
        if quantity > available_qty:
            return jsonify({
                'success': False,
                'error': f'Declared quantity ({quantity}) exceeds available ({available_qty}).'
            }), 400

        # --- Fetch inv_desc and unit ---
        conn_inv = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
        cursor_inv = conn_inv.cursor()
        cursor_inv.execute("SELECT inv_desc, unit FROM inv_static WHERE inv_id = ?", (inv_id,))
        inv_row = cursor_inv.fetchone()
        conn_inv.close()

        if not inv_row:
            return jsonify({'success': False, 'error': 'Inventory not found'}), 400

        inv_desc, unit = inv_row

        # --- Fetch exp_date ---
        conn_batch = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
        cursor_batch = conn_batch.cursor()
        cursor_batch.execute("SELECT exp_date FROM inv_dynamic WHERE batch_id = ?", (batch_id,))
        batch_row = cursor_batch.fetchone()
        conn_batch.close()

        if not batch_row:
            return jsonify({'success': False, 'error': 'Batch not found'}), 400

        exp_date = batch_row[0]

        # --- Generate waste_id ---
        conn_waste = sqlite3.connect(os.path.join('db', 'wastage_db.db'))
        cursor_waste = conn_waste.cursor()

        cursor_waste.execute("SELECT waste_id FROM wastages WHERE waste_id LIKE 'Wa_____' ORDER BY waste_id DESC LIMIT 1")
        last_id_main = cursor_waste.fetchone()

        cursor_waste.execute("SELECT waste_id FROM wastage_cart WHERE waste_id LIKE 'Wa_____' ORDER BY waste_id DESC LIMIT 1")
        last_id_cart = cursor_waste.fetchone()

        def extract_num(wid):
            return int(wid[2:]) if wid else 0

        next_num = max(extract_num(last_id_main[0]) if last_id_main else 0,
                       extract_num(last_id_cart[0]) if last_id_cart else 0) + 1
        new_waste_id = f"Wa{next_num:05d}"

        # --- Insert into wastage_cart ---
        cursor_waste.execute("""
            INSERT INTO wastage_cart (
                waste_id, inv_id, inv_desc, batch_id, exp_date,
                quantity, unit, remark, waste_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_waste_id, inv_id, inv_desc, batch_id, exp_date,
            quantity, unit, remark, waste_date
        ))

        conn_waste.commit()
        conn_waste.close()

        return jsonify({
            'success': True,
            'entry': {
                'waste_id': new_waste_id,
                'inv_id': inv_id,
                'inv_desc': inv_desc,
                'batch_id': batch_id,
                'exp_date': exp_date,
                'quantity': quantity,
                'unit': unit,
                'remark': remark,
                'waste_date': waste_date
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/clear_wastage_cart', methods=['POST'])
@login_required
def clear_wastage_cart():
    try:
        conn = sqlite3.connect(os.path.join('db', 'wastage_db.db'))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM wastage_cart")
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/confirm_wastage', methods=['POST'])
@login_required
def confirm_wastage():
    try:
        conn_waste = sqlite3.connect(os.path.join('db', 'wastage_db.db'))
        cursor_waste = conn_waste.cursor()

        # Fetch all records from wastage_cart
        cursor_waste.execute("SELECT * FROM wastage_cart")
        rows = cursor_waste.fetchall()

        if not rows:
            return jsonify({'success': False, 'error': 'No items to confirm'}), 400

        # Open inventory DB for deduction
        conn_inv = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
        cursor_inv = conn_inv.cursor()

        for row in rows:
            # Unpack fields from wastage_cart
            waste_id, inv_id, inv_desc, batch_id, exp_date, quantity, unit, remark, waste_date = row

            # Insert into wastages table
            cursor_waste.execute("""
                INSERT INTO wastages (
                    waste_id, inv_id, inv_desc, batch_id, exp_date,
                    quantity, unit, remark, waste_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)

            # Subtract from inv_dynamic
            cursor_inv.execute("""
                UPDATE inv_dynamic
                SET quantity = quantity - ?
                WHERE inv_id = ? AND batch_id = ?
            """, (quantity, inv_id, batch_id))

        # Clear the cart
        cursor_waste.execute("DELETE FROM wastage_cart")

        # Commit both databases
        conn_waste.commit()
        conn_inv.commit()

        # Close connections
        conn_waste.close()
        conn_inv.close()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/pos')
@login_required
def pos():
    conn = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query all static inventory
    cursor.execute("""
        SELECT inv_id, inv_desc, price, image
        FROM inv_static
    """)
    static_data = cursor.fetchall()

    # Query dynamic inventory to compute stock per inv_id
    cursor.execute("""
        SELECT inv_id, SUM(quantity) as stock
        FROM inv_dynamic
        GROUP BY inv_id
    """)
    dynamic_data = cursor.fetchall()
    conn.close()

    # Map dynamic data for quick lookup
    stock_map = {row['inv_id']: row['stock'] for row in dynamic_data}

    # Merge static and dynamic data
    products = []
    for row in static_data:
        inv_id = row['inv_id']
        products.append({
            "id": inv_id,
            "name": row['inv_desc'],
            "price": row['price'],
            "stock": stock_map.get(inv_id, 0),
            "image": row['image']
        })

    return render_template('pos.html', products=products)

# Flask route to add/update item in pos_cart
@app.route('/add_to_pos_cart', methods=['POST'])
def add_to_pos_cart():
    data = request.get_json()
    inv_id = data.get('inv_id')
    inv_desc = data.get('inv_desc')
    price = data.get('price')

    conn = sqlite3.connect(os.path.join('db', 'restock_db.db'))
    cursor = conn.cursor()

    # Check if item already exists
    cursor.execute("SELECT quantity FROM pos_cart WHERE inv_id = ?", (inv_id,))
    result = cursor.fetchone()

    if result:
        # Increment quantity
        cursor.execute("""
            UPDATE pos_cart
            SET quantity = quantity + 1
            WHERE inv_id = ?
        """, (inv_id,))
    else:
        # Insert new product with quantity = 1
        cursor.execute("""
            INSERT INTO pos_cart (inv_id, inv_desc, quantity, price)
            VALUES (?, ?, 1, ?)
        """, (inv_id, inv_desc, price))

    conn.commit()
    conn.close()
    print("🛒 Product clicked:", inv_id, file=sys.stderr)
    
    return jsonify({'status': 'success'})

@app.route('/get_pos_cart', methods=['GET'])
def get_pos_cart():
    conn = sqlite3.connect(os.path.join('db', 'restock_db.db'))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT inv_id, inv_desc, quantity, price, quantity * price AS total
        FROM pos_cart
    """)
    cart_items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(cart_items)

@app.route('/clear_pos_cart', methods=['POST'])
def clear_pos_cart():
    conn = sqlite3.connect(os.path.join('db', 'restock_db.db'))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pos_cart")
    conn.commit()
    conn.close()
    return jsonify({'status': 'cleared'})

@app.route('/remove_from_pos_cart', methods=['POST'])
def remove_from_pos_cart():
    data = request.get_json()
    inv_id = data.get('inv_id')

    conn = sqlite3.connect(os.path.join('db', 'restock_db.db'))
    cursor = conn.cursor()

    # Reduce quantity or delete if it reaches 0
    cursor.execute("SELECT quantity FROM pos_cart WHERE inv_id = ?", (inv_id,))
    result = cursor.fetchone()

    if result:
        if result[0] > 1:
            cursor.execute("""
                UPDATE pos_cart
                SET quantity = quantity - 1
                WHERE inv_id = ?
            """, (inv_id,))
        else:
            cursor.execute("DELETE FROM pos_cart WHERE inv_id = ?", (inv_id,))

        conn.commit()

    conn.close()
    return jsonify({'status': 'success'})

@app.route('/finalize_checkout', methods=['POST'])
def finalize_checkout():
    # Step 1: Fetch cart items
    cart_conn = sqlite3.connect(os.path.join('db', 'restock_db.db'))
    cart_conn.row_factory = sqlite3.Row
    cart_cursor = cart_conn.cursor()
    cart_cursor.execute("""
        SELECT inv_id, inv_desc, quantity, price FROM pos_cart
    """)
    cart_items = cart_cursor.fetchall()
    cart_conn.close()

    if not cart_items:
        return jsonify({'status': 'error', 'message': 'Cart is empty'}), 400

    # Step 2: Subtract inventory (from inv_dynamic) — same logic as before
    inventory_path = os.path.join('db', 'inventory_db.db')
    inv_conn = sqlite3.connect(inventory_path)
    inv_cursor = inv_conn.cursor()

    for item in cart_items:
        inv_id = item['inv_id']
        qty_needed = item['quantity']

        # Select inventory batches sorted by earliest expiration date
        inv_cursor.execute("""
            SELECT actual_id, quantity FROM inv_dynamic
            WHERE inv_id = ?
            ORDER BY DATE(exp_date) ASC
        """, (inv_id,))
        batches = inv_cursor.fetchall()

        for batch in batches:
            if qty_needed <= 0:
                break

            actual_id, available = batch
            to_subtract = min(qty_needed, available)

            # Subtract from the batch
            new_qty = available - to_subtract
            inv_cursor.execute("""
                UPDATE inv_dynamic
                SET quantity = ?
                WHERE actual_id = ?
            """, (new_qty, actual_id))

            qty_needed -= to_subtract

    inv_conn.commit()
    inv_conn.close()

    # Step 3: Prepare sales logging path
    now = datetime.now()
    day_str = f"d{now.day:02d}"
    month_str = now.strftime("%b").lower()  # e.g., 'jul'
    year_str = str(now.year)
    db_dir = os.path.join("db", "salesdb", "daily", f"sales_d{year_str}")
    db_path = os.path.join(db_dir, f"{month_str}_{year_str}.db")

    if not os.path.exists(db_path):
        return jsonify({'status': 'error', 'message': 'Sales database not found'}), 500

    # Step 4: Record the sale in the correct dXX table
    sales_conn = sqlite3.connect(db_path)
    sales_cursor = sales_conn.cursor()

    for item in cart_items:
        inv_id = item['inv_id']
        inv_desc = item['inv_desc']
        quantity = item['quantity']
        price = item['price']

        # Check if item already exists in today's sales table
        sales_cursor.execute(f"""
            SELECT quantity_sold FROM {day_str}
            WHERE inv_id = ?
        """, (inv_id,))
        existing = sales_cursor.fetchone()

        if existing:
            # Update quantity
            sales_cursor.execute(f"""
                UPDATE {day_str}
                SET quantity_sold = quantity_sold + ?
                WHERE inv_id = ?
            """, (quantity, inv_id))
        else:
            # Insert new record
            sales_cursor.execute(f"""
                INSERT INTO {day_str} (inv_id, inv_desc, quantity_sold, price)
                VALUES (?, ?, ?, ?)
            """, (inv_id, inv_desc, quantity, price))

    sales_conn.commit()
    sales_conn.close()

    # Step 5: Clear cart
    clear_conn = sqlite3.connect(os.path.join('db', 'restock_db.db'))
    clear_cursor = clear_conn.cursor()
    clear_cursor.execute("DELETE FROM pos_cart")
    clear_conn.commit()
    clear_conn.close()

    return jsonify({'status': 'success', 'message': 'Checkout finalized'})

@app.route('/account')
@login_required
def account():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM user_data WHERE user_name = ?", (session['username'],))
    user_data = cursor.fetchone()
    
    conn.close()
    
    return render_template('account.html', user_data=user_data)

# API endpoints for AJAX calls
@app.route('/api/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        return jsonify({'error': 'Product not found'}), 404
    
    if product['stock'] < quantity:
        conn.close()
        return jsonify({'error': 'Insufficient stock'}), 400
    
    cart_item = {
        'id': product['id'],
        'name': product['name'],
        'price': product['price'],
        'quantity': quantity,
        'total': product['price'] * quantity
    }
    
    conn.close()
    return jsonify(cart_item)

@app.route('/api/checkout', methods=['POST'])
@login_required
def checkout():
    data = request.get_json()
    cart_items = data.get('cart_items', [])
    
    if not cart_items:
        return jsonify({'error': 'Cart is empty'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        for item in cart_items:
            # Update product stock
            cursor.execute("""
                UPDATE products
                SET stock = stock - ?
                WHERE id = ?
            """, (item['quantity'], item['id']))
            
            # Record sale
            cursor.execute("""
                INSERT INTO sales (product_id, quantity, total_amount, date)
                VALUES (?, ?, ?, datetime('now'))
            """, (item['id'], item['quantity'], item['total']))
        
        conn.commit()
        conn.close()
        return jsonify({'message': 'Checkout successful'})
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_personal_profile', methods=['POST'])
@login_required
def update_personal_profile():
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        owner_name = data.get('owner_name', '').strip()
        contact = data.get('contact', '').strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update the user's personal profile information
        cursor.execute("""
            UPDATE user_data 
            SET title = ?, owner_name = ?, contact = ?
            WHERE user_name = ?
        """, (title, owner_name, contact, session['username']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Personal profile updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/update_business_profile', methods=['POST'])
@login_required
def update_business_profile():
    try:
        data = request.get_json()
        biz_name = data.get('biz_name', '').strip()
        industry = data.get('industry', '').strip()
        biz_type = data.get('biz_type', '').strip()
        address = data.get('address', '').strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update the user's business profile information
        cursor.execute("""
            UPDATE user_data 
            SET biz_name = ?, industry = ?, biz_type = ?, address = ?
            WHERE user_name = ?
        """, (biz_name, industry, biz_type, address, session['username']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Business profile updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def send_recovery_email(to_email, username):
    # Configure your SMTP server settings here
    SMTP_SERVER = 'smtp.example.com'  # e.g., 'smtp.gmail.com'
    SMTP_PORT = 587
    SMTP_USER = 'your_email@example.com'
    SMTP_PASSWORD = 'your_email_password'

    msg = EmailMessage()
    msg['Subject'] = 'Account Recovery - Economystique'
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg.set_content(f"Hello {username},\n\nYou requested a password reset for your Economystique account. If this was you, please follow the instructions provided by the administrator to reset your password.\n\nIf you did not request this, you can ignore this email.\n\nBest regards,\nEconomystique Team")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending recovery email: {e}")
        return False

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    email = request.form.get('recovery_email')
    if not email:
        flash('Please enter your email address.', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_name FROM user_data WHERE email = ?", (email,))
    result = cursor.fetchone()
    if result:
        username = result['user_name']
        if send_recovery_email(email, username):
            flash('A recovery email has been sent to your address.', 'success')
        else:
            flash('Failed to send recovery email. Please try again later.', 'error')
    else:
        flash('No account found with that email address.', 'error')
    conn.close()
    return redirect(url_for('login'))

@app.route('/api/change_username', methods=['POST'])
@login_required
def api_change_username():
    try:
        data = request.get_json()
        current_username = data.get('current_username')
        new_username = data.get('new_username', '').strip()
        password = data.get('password', '').encode('utf-8')
        
        # Validate inputs
        if not new_username:
            return jsonify({'success': False, 'error': 'Please enter a new username.'})
        
        if len(new_username) < 3:
            return jsonify({'success': False, 'error': 'Username must be at least 3 characters long.'})
        
        if new_username == current_username:
            return jsonify({'success': False, 'error': 'New username must be different from current username.'})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify current user and password
        cursor.execute("SELECT pw_hash FROM user_data WHERE user_name = ?", (current_username,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid current username.'})
        
        if not bcrypt.checkpw(password, result['pw_hash'].encode('utf-8')):
            conn.close()
            return jsonify({'success': False, 'error': 'Incorrect password.'})
        
        # Check if new username already exists
        cursor.execute("SELECT user_name FROM user_data WHERE user_name = ?", (new_username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Username already exists. Please choose a different username.'})
        
        # Update username
        cursor.execute("UPDATE user_data SET user_name = ? WHERE user_name = ?", (new_username, current_username))
        conn.commit()
        
        # Update session
        session['username'] = new_username
        
        conn.close()
        return jsonify({'success': True, 'message': 'Username changed successfully!'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

#def on_loaded():
#     webview.windows[0].gui.window.showMaximized()

# def start_server():
#    app.run(port=5000)

@app.route('/api/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        file_bytes = file.read()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE user_data SET avatar_blob = ? WHERE user_name = ?", (file_bytes, session['username']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'avatar_url': url_for('avatar_image', username=session['username'])})
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/upload_biz_logo', methods=['POST'])
@login_required
def upload_biz_logo():
    if 'biz_logo' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['biz_logo']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        file_bytes = file.read()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE user_data SET biz_logo_blob = ? WHERE user_name = ?", (file_bytes, session['username']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'logo_url': url_for('biz_logo_image', username=session['username'])})
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/avatar_image/<username>')
def avatar_image(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT avatar_blob FROM user_data WHERE user_name = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row and row['avatar_blob']:
        return send_file(io.BytesIO(row['avatar_blob']), mimetype='image/png')
    else:
        return send_file(os.path.join('static', 'img', 'catholder.jpg'), mimetype='image/jpeg')

@app.route('/biz_logo_image/<username>')
def biz_logo_image(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT biz_logo_blob FROM user_data WHERE user_name = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row and row['biz_logo_blob']:
        return send_file(io.BytesIO(row['biz_logo_blob']), mimetype='image/png')
    else:
        return send_file(os.path.join('static', 'img', 'dashboardIcon.png'), mimetype='image/png')

@app.route('/api/restock_cart/add', methods=['POST'])
def add_to_restock_cart():
    data = request.get_json()
    inv_id = data.get('inv_id')
    inv_desc = data.get('inv_desc')
    quantity = data.get('quantity')
    cost = data.get('cost')
    exp_date = data.get('exp_date')
    session_id = session.get('username', 'guest')

    if not all([inv_id, inv_desc, quantity, cost, exp_date]):
        return jsonify({'error': 'Missing data'}), 400

    db_path = os.path.join('db', 'restock_db.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restock_cart (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            inv_id TEXT,
            inv_desc TEXT,
            quantity INTEGER,
            cost REAL,
            exp_date TEXT
        )
    """)
    # Get next id
    cursor.execute("SELECT MAX(id) FROM restock_cart")
    max_id = cursor.fetchone()[0]
    next_id = 1 if max_id is None else int(max_id) + 1
    cursor.execute("""
        INSERT INTO restock_cart (id, session_id, inv_id, inv_desc, quantity, cost, exp_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (next_id, session_id, inv_id, inv_desc, quantity, cost, exp_date))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/restock_cart', methods=['GET'])
def get_restock_cart():
    session_id = session.get('username', 'guest')
    db_path = os.path.join('db', 'restock_db.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restock_cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            inv_id TEXT,
            inv_desc TEXT,
            quantity INTEGER,
            cost REAL,
            exp_date TEXT
        )
    """)
    cursor.execute("SELECT inv_id, inv_desc, quantity, cost, exp_date FROM restock_cart WHERE session_id = ?", (session_id,))
    items = cursor.fetchall()
    conn.close()
    cart = [
        {
            'inv_id': row[0],
            'inv_desc': row[1],
            'quantity': row[2],
            'cost': row[3],
            'exp_date': row[4]
        } for row in items
    ]
    return jsonify(cart)

@app.route('/api/restock_cart/confirm', methods=['POST'])
def confirm_restock_cart():
    import sqlite3
    import os
    from datetime import datetime
    session_id = session.get('username', 'guest')
    db_path = os.path.join('db', 'restock_db.db')
    inv_db_path = os.path.join('db', 'inventory_db.db')
    batches_db_path = os.path.join('db', 'batches_db.db')

    # 1. Get all items from restock_cart for this session
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT inv_id, inv_desc, quantity, cost, exp_date FROM restock_cart WHERE session_id = ?", (session_id,))
    items = cursor.fetchall()

    # 2. Get unit for each item from inv_static and prepare for batch table
    inv_conn = sqlite3.connect(inv_db_path)
    inv_cursor = inv_conn.cursor()
    batch_items = []
    rec_date = datetime.now().strftime('%Y-%m-%d')
    for row in items:
        inv_id, inv_desc, quantity, cost, exp_date = row
        inv_cursor.execute("SELECT unit FROM inv_static WHERE inv_id = ?", (inv_id,))
        unit_row = inv_cursor.fetchone()
        unit = unit_row[0] if unit_row else ''
        batch_items.append((inv_id, inv_desc, quantity, unit, exp_date, rec_date, cost))

    # 3. Create new batch table in batches_db.db
    batches_conn = sqlite3.connect(batches_db_path)
    batches_cursor = batches_conn.cursor()
    # Find next batch table name
    batches_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Ba%'")
    batch_tables = [row[0] for row in batches_cursor.fetchall()]
    if batch_tables:
        last_num = max(int(name[2:]) for name in batch_tables if name[2:].isdigit())
        next_batch = f"Ba{last_num+1:05d}"
    else:
        next_batch = "Ba00001"
    # Create the new batch table
    batches_cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {next_batch} (
            inv_id TEXT,
            inv_desc TEXT,
            quantity INTEGER,
            unit TEXT,
            exp_date TEXT,
            rec_date TEXT,
            cost REAL
        )
    """)
    # Insert items into the new batch table
    batches_cursor.executemany(f"INSERT INTO {next_batch} (inv_id, inv_desc, quantity, unit, exp_date, rec_date, cost) VALUES (?, ?, ?, ?, ?, ?, ?)", batch_items)
    batches_conn.commit()
    batches_conn.close()

    # 4. Insert into inv_dynamic as before
    inv_cursor.execute("""
        CREATE TABLE IF NOT EXISTS inv_dynamic (
            actual_id TEXT PRIMARY KEY,
            batch_id TEXT,
            inv_id TEXT,
            quantity INTEGER,
            unit TEXT,
            exp_date DATE,
            rec_date DATE,
            cost REAL
        )
    """)
    # Get current max actual_id
    inv_cursor.execute("SELECT MAX(CAST(SUBSTR(actual_id, 5) AS INTEGER)) FROM inv_dynamic WHERE actual_id LIKE 'ITa%'")
    max_actual_id = inv_cursor.fetchone()[0]
    next_actual_id_num = 1 if max_actual_id is None else max_actual_id + 1
    for row in items:
        inv_id, inv_desc, quantity, cost, exp_date = row
        batch_id = next_batch
        rec_date = datetime.now().strftime('%Y-%m-%d')
        inv_cursor.execute("SELECT unit FROM inv_static WHERE inv_id = ?", (inv_id,))
        unit_row = inv_cursor.fetchone()
        unit = unit_row[0] if unit_row else ''
        actual_id = f'ITa{next_actual_id_num:05d}'
        next_actual_id_num += 1
        inv_cursor.execute("""
            INSERT INTO inv_dynamic (actual_id, batch_id, inv_id, quantity, unit, exp_date, rec_date, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (actual_id, batch_id, inv_id, quantity, unit, exp_date, rec_date, cost))
    inv_conn.commit()
    inv_conn.close()

    # 5. Clear restock_cart
    cursor.execute("DELETE FROM restock_cart WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/get_categories', methods=['GET'])
def get_categories():
    try:
        conn = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
        cursor = conn.cursor()
        
        # Get unique categories
        cursor.execute("SELECT DISTINCT cat FROM inv_static WHERE cat IS NOT NULL AND cat != '' ORDER BY cat")
        categories = [row[0] for row in cursor.fetchall()]
        
        # Get unique subcategories
        cursor.execute("SELECT DISTINCT sub_cat FROM inv_static WHERE sub_cat IS NOT NULL AND sub_cat != '' ORDER BY sub_cat")
        subcategories = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'categories': categories,
            'subcategories': subcategories
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/add_new_product', methods=['POST'])
def add_new_product():
    try:
        data = request.get_json()
        
        # Extract form data
        inv_desc = data.get('inv_desc', '').strip()
        barcode = data.get('barcode', '').strip()
        category = data.get('category', '').strip()
        subcategory = data.get('subcategory', '').strip()
        unit = data.get('unit', '').strip()
        reorder_point = data.get('reorder_point', 0)
        price = data.get('price', 0.0)
        cost = data.get('cost', 0.0)
        
        # Validate required fields
        if not inv_desc:
            return jsonify({'success': False, 'message': 'Inventory description is required'})
        
        if not unit:
            return jsonify({'success': False, 'message': 'Unit is required'})
        
        conn = sqlite3.connect(os.path.join('db', 'inventory_db.db'))
        cursor = conn.cursor()
        
        # Get the next inventory ID
        cursor.execute("SELECT MAX(CAST(SUBSTR(inv_id, 5) AS INTEGER)) FROM inv_static")
        max_id = cursor.fetchone()[0]
        next_id = 1 if max_id is None else max_id + 1
        inv_id = f"INVa{next_id:05d}"
        
        # Check if barcode already exists (if provided)
        if barcode:
            cursor.execute("SELECT inv_id FROM inv_static WHERE barcode = ?", (barcode,))
            if cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'message': 'Barcode already exists'})
        
        # Get image data
        image_data = data.get('image')
        
        # Insert new product into inv_static
        cursor.execute("""
            INSERT INTO inv_static (inv_id, inv_desc, cat, sub_cat, unit, rop, barcode, price, cost, image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (inv_id, inv_desc, category, subcategory, unit, reorder_point, barcode, price, cost, image_data))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': 'Product added successfully',
            'inv_id': inv_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/restock_cart/clear', methods=['POST'])
def clear_restock_cart():
    session_id = session.get('username', 'guest')
    db_path = os.path.join('db', 'restock_db.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM restock_cart WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# if __name__ == '__main__':
#     # Start Flask server in a separate thread
#     threading.Thread(target=start_server, daemon=True).start()
#     
#     # Create and show the window
#     webview.create_window('Economystique', 
#                          'http://127.0.0.1:5000',
#                          maximized=True,
#                          resizable=True,
#                          min_size=(640, 360))
#     webview.start(on_loaded, gui='qt')

if __name__ == '__main__':
    app.run(debug=True)
    
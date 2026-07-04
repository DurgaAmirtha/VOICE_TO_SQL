import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from config import Config
from utils.common import logger

def seed_demo_database(db_path: Path):
    """Generates a realistic SQLite database with sample business records."""
    logger.info(f"Seeding demo database at: {db_path}")
    
    # Connect and clean up if database already exists
    if db_path.exists():
        db_path.unlink()
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Enable Foreign Keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 2. Create Tables
    # Customers
    cursor.execute("""
    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        city TEXT NOT NULL,
        country TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    
    # Employees
    cursor.execute("""
    CREATE TABLE employees (
        employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        role TEXT NOT NULL,
        department TEXT NOT NULL,
        manager_id INTEGER,
        FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
    );
    """)
    
    # Products
    cursor.execute("""
    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL,
        cost REAL NOT NULL,
        stock_quantity INTEGER NOT NULL
    );
    """)
    
    # Orders
    cursor.execute("""
    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        employee_id INTEGER,
        order_date TEXT NOT NULL,
        total_amount REAL NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
    );
    """)
    
    # Sales (Line items)
    cursor.execute("""
    CREATE TABLE sales (
        sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        discount REAL NOT NULL, -- percentage value, e.g. 0.05
        total_revenue REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );
    """)
    
    # 3. Seed Data
    # 3.1. Employees
    employees = [
        # (first_name, last_name, role, department, manager_id)
        ("Sarah", "Connor", "VP Sales", "Sales & Marketing", None), # 1
        ("John", "Doe", "Sales Manager", "Sales", 1), # 2
        ("Alice", "Smith", "Sales Agent", "Sales", 2), # 3
        ("Bob", "Johnson", "Sales Agent", "Sales", 2), # 4
        ("Charlie", "Brown", "Support Lead", "Customer Service", 1), # 5
        ("David", "Miller", "Support Agent", "Customer Service", 5), # 6
        ("Emma", "Davis", "Marketing Manager", "Marketing", 1), # 7
        ("Frank", "Garcia", "Marketing Analyst", "Marketing", 7), # 8
        ("Grace", "Wilson", "Sales Agent", "Sales", 2), # 9
        ("Henry", "Taylor", "Sales Agent", "Sales", 2) # 10
    ]
    
    for emp in employees:
        cursor.execute("""
        INSERT INTO employees (first_name, last_name, role, department, manager_id)
        VALUES (?, ?, ?, ?, ?);
        """, emp)
        
    # 3.2. Customers
    cities = [
        ("New York", "USA"), ("San Francisco", "USA"), ("Chicago", "USA"),
        ("London", "UK"), ("Manchester", "UK"), ("Paris", "France"),
        ("Berlin", "Germany"), ("Munich", "Germany"), ("Toronto", "Canada"),
        ("Sydney", "Australia"), ("Tokyo", "Japan"), ("Mumbai", "India")
    ]
    
    first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "William", "Elizabeth",
                   "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                  "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
    
    customer_ids = []
    start_date = datetime(2024, 1, 1)
    
    # Generate 30 customers
    random.seed(42)
    for i in range(1, 31):
        fn = random.choice(first_names)
        ln = random.choice(last_names)
        email = f"{fn.lower()}.{ln.lower()}{i}@example-business.com"
        city, country = random.choice(cities)
        created_at = (start_date + timedelta(days=random.randint(0, 500))).strftime("%Y-%m-%d")
        
        cursor.execute("""
        INSERT INTO customers (first_name, last_name, email, city, country, created_at)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (fn, ln, email, city, country, created_at))
        customer_ids.append(i)
        
    # 3.3. Products
    products_catalog = [
        # (name, category, price, cost, stock_quantity)
        ("Enterprise Server S1", "Electronics", 2499.99, 1500.00, 25),
        ("Developer Laptop L2", "Electronics", 1299.99, 800.00, 50),
        ("Standard Office Desk", "Furniture", 299.99, 120.00, 80),
        ("Ergonomic Mesh Chair", "Furniture", 199.99, 85.00, 120),
        ("Wireless Noise-Canceling Headset", "Electronics", 149.99, 60.00, 200),
        ("Mechanical Keyboard K1", "Electronics", 89.99, 35.00, 150),
        ("Business Polo Shirt", "Apparel", 39.99, 12.00, 300),
        ("Leather Document Portfolio", "Apparel", 79.99, 30.00, 100),
        ("4K UltraWide Monitor M1", "Electronics", 449.99, 260.00, 45),
        ("Smart Conference Webcam", "Electronics", 189.99, 90.00, 70),
        ("Executive Wooden Bookshelf", "Furniture", 349.99, 160.00, 30),
        ("Adjustable Footrest", "Furniture", 49.99, 18.00, 110),
        ("Structured Blazer", "Apparel", 129.99, 50.00, 85),
        ("Comfort-Fit Chinos", "Apparel", 59.99, 22.00, 140),
        ("USB-C Docking Station Multi", "Electronics", 119.99, 55.00, 95)
    ]
    
    for prod in products_catalog:
        cursor.execute("""
        INSERT INTO products (product_name, category, price, cost, stock_quantity)
        VALUES (?, ?, ?, ?, ?);
        """, prod)
        
    # 3.4. Orders and Sales
    # Let's generate 60 orders
    sales_rep_ids = [3, 4, 9, 10] # Sales agents
    order_dates = []
    
    base_order_date = datetime(2024, 6, 1)
    
    for order_id in range(1, 61):
        customer_id = random.choice(customer_ids)
        employee_id = random.choice(sales_rep_ids)
        order_date = (base_order_date + timedelta(days=random.randint(0, 380))).strftime("%Y-%m-%d")
        
        # Order amount is calculated dynamically based on sales lines
        # We will insert the order with total = 0 first, insert lines, then update order total
        cursor.execute("""
        INSERT INTO orders (customer_id, employee_id, order_date, total_amount)
        VALUES (?, ?, ?, 0.0);
        """, (customer_id, employee_id, order_date))
        
        # Insert 1 to 4 sales items per order
        num_items = random.randint(1, 4)
        selected_products = random.sample(range(1, 16), num_items)
        order_total = 0.0
        
        for prod_id in selected_products:
            # Query price
            cursor.execute("SELECT price FROM products WHERE product_id = ?;", (prod_id,))
            price = cursor.fetchone()[0]
            
            qty = random.randint(1, 5)
            # 10% chance of a discount (either 5%, 10%, or 15%)
            discount = random.choice([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.10, 0.15])
            
            line_total = qty * price * (1.0 - discount)
            line_total = round(line_total, 2)
            order_total += line_total
            
            cursor.execute("""
            INSERT INTO sales (order_id, product_id, quantity, unit_price, discount, total_revenue)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (order_id, prod_id, qty, price, discount, line_total))
            
        # Update the order total
        order_total = round(order_total, 2)
        cursor.execute("UPDATE orders SET total_amount = ? WHERE order_id = ?;", (order_total, order_id))
        
    conn.commit()
    conn.close()
    logger.info("Demo database seeded successfully.")

if __name__ == "__main__":
    seed_demo_database(Config.DEMO_DB_PATH)
    # Verification print
    conn = sqlite3.connect(Config.DEMO_DB_PATH)
    cursor = conn.cursor()
    print("DEMO DATABASE TABLES AND RECORD COUNTS:")
    for table in ["customers", "employees", "products", "orders", "sales"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        print(f"Table '{table}': {cursor.fetchone()[0]} rows")
    conn.close()

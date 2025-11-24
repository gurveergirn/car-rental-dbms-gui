from flask import Flask, render_template, request, redirect, url_for, session
import oracledb

#  DB Connection
DB_USER = "gsgirn"
DB_PASSWORD = "02078027"
DB_DSN = "oracle12c.cs.torontomu.ca/orcl12c"

app = Flask(__name__)
app.secret_key = "cps510_secret_key"

def get_conn():
    return oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)

def login_required(fn):
    def wrapper(*args, **kwargs):
        if "logged_in" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


# Drop, create, population of tables

DROP_TABLES_PLSQL = """
BEGIN
  FOR t IN (SELECT table_name FROM user_tables
            WHERE table_name IN ('PAYMENT','RENTAL','INVENTORY',
                                 'VEHICLE','ADMIN','CUSTOMER')) LOOP
    EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS';
  END LOOP;
END;
"""

CREATE_TABLES_SQL = """
CREATE TABLE Customer (
    Customer_ID           NUMBER        PRIMARY KEY,
    Email                 VARCHAR2(255) NOT NULL,
    Full_Name             VARCHAR2(120) NOT NULL,
    Phone_Number          VARCHAR2(40),
    Customer_Address      VARCHAR2(300),
    Drivers_LicenseNumber VARCHAR2(40)  NOT NULL,
    Customer_Password     VARCHAR2(200) NOT NULL,
    CONSTRAINT uq_customer_email UNIQUE (Email),
    CONSTRAINT uq_customer_dl    UNIQUE (Drivers_LicenseNumber)
);

CREATE TABLE Admin (
    Admin_ID       NUMBER        PRIMARY KEY,
    Admin_Role     VARCHAR2(40)  NOT NULL,
    Admin_Email    VARCHAR2(255) NOT NULL,
    Admin_Password VARCHAR2(200) NOT NULL,
    CONSTRAINT uq_admin_email UNIQUE (Admin_Email)
);

CREATE TABLE Vehicle (
    Vehicle_ID    NUMBER        PRIMARY KEY,
    License_Plate VARCHAR2(20)  NOT NULL,
    Vehicle_Make  VARCHAR2(40)  NOT NULL,
    Vehicle_Model VARCHAR2(60)  NOT NULL,
    Vehicle_Year  NUMBER(4)     NOT NULL,
    Vehicle_VIN   VARCHAR2(32)  NOT NULL,
    CONSTRAINT uq_vehicle_vin   UNIQUE (Vehicle_VIN),
    CONSTRAINT uq_vehicle_plate UNIQUE (License_Plate)
);

CREATE TABLE Inventory (
    Inventory_ID    NUMBER        PRIMARY KEY,
    Vehicle_ID      NUMBER        NOT NULL,
    Admin_ID        NUMBER        NOT NULL,
    Availability    VARCHAR2(20)  DEFAULT 'AVAILABLE' NOT NULL,
    Daily_Rate      NUMBER(10,2)  NOT NULL,
    Current_Mileage NUMBER(10)    DEFAULT 0 NOT NULL,
    Mileage_Policy  VARCHAR2(80),
    CONSTRAINT fk_inv_vehicle FOREIGN KEY (Vehicle_ID)
        REFERENCES Vehicle(Vehicle_ID),
    CONSTRAINT fk_inv_admin   FOREIGN KEY (Admin_ID)
        REFERENCES Admin(Admin_ID),
    CONSTRAINT uq_inv_vehicle UNIQUE (Vehicle_ID)
);

CREATE TABLE Rental (
    Rental_ID       NUMBER        PRIMARY KEY,
    Customer_ID     NUMBER        NOT NULL,
    Vehicle_ID      NUMBER        NOT NULL,
    Rental_Duration NUMBER,
    Pickup_Date     DATE          NOT NULL,
    Return_Date     DATE,
    Rental_Rate     NUMBER(10,2)  NOT NULL,
    CONSTRAINT fk_rental_customer FOREIGN KEY (Customer_ID)
        REFERENCES Customer(Customer_ID),
    CONSTRAINT fk_rental_vehicle  FOREIGN KEY (Vehicle_ID)
        REFERENCES Vehicle(Vehicle_ID)
);

CREATE TABLE Payment (
    Payment_ID     NUMBER        PRIMARY KEY,
    Customer_ID    NUMBER        NOT NULL,
    Rental_ID      NUMBER        NOT NULL,
    Payment_Amount NUMBER(10,2)  NOT NULL,
    Status         VARCHAR2(20)  DEFAULT 'PENDING' NOT NULL,
    CONSTRAINT fk_pay_customer FOREIGN KEY (Customer_ID)
        REFERENCES Customer(Customer_ID),
    CONSTRAINT fk_pay_rental   FOREIGN KEY (Rental_ID)
        REFERENCES Rental(Rental_ID),
    CONSTRAINT uq_pay_rental   UNIQUE (Rental_ID)
);
"""

POPULATE_SQL = """
INSERT INTO Customer VALUES
(1, 'aliyah@example.com', 'Aliyah Diaz', '555-1111',
 'Toronto, ON', 'DL-A1', 'pw1');
INSERT INTO Customer VALUES
(2, 'akash@example.com', 'Akash Seeraalan', '555-2222',
 'Scarborough, ON', 'DL-A2', 'pw2');
INSERT INTO Customer VALUES
(3, 'gurveer@example.com', 'Gurveer Girn', '555-3333',
 'Brampton, ON', 'DL-G3', 'pw3');

INSERT INTO Admin VALUES (10, 'Manager', 'admin1@rental.ca', 'adminpw1');
INSERT INTO Admin VALUES (11, 'Clerk',   'admin2@rental.ca', 'adminpw2');

INSERT INTO Vehicle VALUES (100, 'ABC123', 'Toyota', 'Corolla', 2020, 'VIN-T-001');
INSERT INTO Vehicle VALUES (101, 'XYZ789', 'Honda',  'Civic',   2022, 'VIN-H-002');
INSERT INTO Vehicle VALUES (102, 'JKL456', 'Tesla',  'Model 3', 2023, 'VIN-E-003');

INSERT INTO Inventory VALUES (1000, 100, 10, 'AVAILABLE',   40.00, 12000, '100km/day');
INSERT INTO Inventory VALUES (1001, 101, 10, 'AVAILABLE',   50.00, 10000, '100km/day');
INSERT INTO Inventory VALUES (1002, 102, 10, 'MAINTENANCE', 90.00,  8000, 'Unlimited');

INSERT INTO Rental VALUES
(5000, 2, 101, 7, DATE '2025-09-25', NULL,              55.00);
INSERT INTO Rental VALUES
(5001, 1, 100, 3, DATE '2025-09-20', DATE '2025-09-23', 45.00);

INSERT INTO Payment VALUES (9000, 1, 5001,  90.00, 'PAID');
INSERT INTO Payment VALUES (9001, 2, 5000, 420.00, 'PAID');

COMMIT;
"""


# Queries
QUERIES = {
    "1": ("Rentals > 5 Days",
          """
          SELECT c.Full_Name AS CUSTOMER_NAME,
                 v.Vehicle_Make,
                 v.Vehicle_Model,
                 r.Rental_Duration
          FROM Rental r
          JOIN Customer c ON c.Customer_ID = r.Customer_ID
          JOIN Vehicle  v ON v.Vehicle_ID  = r.Vehicle_ID
          WHERE r.Rental_Duration > 5
          ORDER BY r.Rental_Duration DESC
          """),

    "2": ("Rental Count per Customer",
          """
          SELECT c.Full_Name AS CUSTOMER_NAME,
                 COUNT(r.Rental_ID) AS RENTAL_COUNT
          FROM Customer c
          LEFT JOIN Rental r ON r.Customer_ID = c.Customer_ID
          GROUP BY c.Full_Name
          ORDER BY RENTAL_COUNT DESC
          """),

    "3": ("Earnings per Customer",
          """
          SELECT c.Full_Name AS CUSTOMER_NAME,
                 NVL(SUM(p.Payment_Amount),0) AS TOTAL_EARNINGS
          FROM Customer c
          LEFT JOIN Rental r ON r.Customer_ID = c.Customer_ID
          LEFT JOIN Payment p ON p.Rental_ID   = r.Rental_ID
          GROUP BY c.Full_Name
          HAVING NVL(SUM(p.Payment_Amount),0) > 0
          ORDER BY TOTAL_EARNINGS DESC
          """),

    "4": ("Available Vehicles",
          """
          SELECT v.Vehicle_Make,
                 v.Vehicle_Model,
                 v.Vehicle_Year,
                 i.Daily_Rate,
                 i.Current_Mileage
          FROM Vehicle v
          JOIN Inventory i ON i.Vehicle_ID = v.Vehicle_ID
          WHERE i.Availability = 'AVAILABLE'
          ORDER BY v.Vehicle_Make, v.Vehicle_Model
          """),

    "5": ("Rental Cost Statistics",
          """
          SELECT MIN(rental_rate) AS MIN_RATE,
                 MAX(rental_rate) AS MAX_RATE,
                 ROUND(AVG(rental_rate), 2) AS AVG_RATE
          FROM Rental
          """),

        "6": ("Customer Rental & Payment Summary",
          """
          SELECT c.Customer_ID,
                 c.Full_Name AS CUSTOMER_NAME,
                 COUNT(DISTINCT r.Rental_ID) AS NUM_RENTALS,
                 NVL(SUM(p.Payment_Amount), 0) AS TOTAL_PAID,
                 MIN(r.Pickup_Date) AS FIRST_RENTAL_DATE,
                 MAX(r.Pickup_Date) AS LAST_RENTAL_DATE
          FROM Customer c
          LEFT JOIN Rental r
            ON r.Customer_ID = c.Customer_ID
          LEFT JOIN Payment p
            ON p.Rental_ID = r.Rental_ID
          GROUP BY c.Customer_ID, c.Full_Name
          ORDER BY TOTAL_PAID DESC, NUM_RENTALS DESC, c.Customer_ID
          """),

}


# helpers

def get_current_tables():
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT table_name
                FROM user_tables
                ORDER BY table_name
            """)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return cols, rows, None
    except Exception as e:
        return None, None, str(e)


def refresh_index(message=None):
    """Helper to reload index WITH displayed tables + contents."""
    table_cols, table_rows, table_error = get_current_tables()
    table_data = get_all_table_data()
    return render_template(
        "index.html",
        message=message,
        table_cols=table_cols,
        table_rows=table_rows,
        table_error=table_error,
        table_data=table_data,
    )


def get_all_table_data():
    """
    Return a dict:
      {
        'CUSTOMER': {'cols': [...], 'rows': [...]},
        'RENTAL':   {'cols': [...], 'rows': [...]},
        ...
      }
    Only includes tables that actually exist.
    """
    tables = ["ADMIN", "CUSTOMER", "INVENTORY", "PAYMENT", "RENTAL", "VEHICLE"]
    data = {}
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            for t in tables:
                try:
                    cur.execute(f"SELECT * FROM {t}")
                    rows = cur.fetchall()
                    cols = [d[0] for d in cur.description]
                    data[t] = {"cols": cols, "rows": rows}
                except Exception:
                    continue
    except Exception:
        return {}
    return data



def run_ddl_script(sql_script):
    with get_conn() as conn:
        cur = conn.cursor()
        for stmt in sql_script.split(";"):
            s = stmt.strip()
            if s:
                cur.execute(s)
        conn.commit()


# routes for each page

@app.route("/")
@login_required
def index():
    return refresh_index()

#login page
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("username")
        pw = request.form.get("password")

        if user == "cps510" and pw == "1234":
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            error = "Invalid username or password."

    return render_template("login.html", error=error)

# logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/drop", methods=["POST"])
@login_required
def drop_tables():
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(DROP_TABLES_PLSQL)
            conn.commit()
        return refresh_index("Tables dropped.")
    except Exception as e:
        return refresh_index(str(e))


@app.route("/create", methods=["POST"])
@login_required
def create_tables():
    try:
        run_ddl_script(CREATE_TABLES_SQL)
        return refresh_index("Tables created.")
    except Exception as e:
        return refresh_index(str(e))


@app.route("/populate", methods=["POST"])
@login_required
def populate_tables():
    try:
        run_ddl_script(POPULATE_SQL)
        return refresh_index("Tables populated with sample data.")
    except Exception as e:
        return refresh_index(str(e))


@app.route("/queries", methods=["GET", "POST"])
@login_required
def queries():
    cols = rows = title = error = None
    if request.method == "POST":
        qid = request.form.get("query_id")
        if qid in QUERIES:
            title, sql = QUERIES[qid]
            try:
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(sql)
                    rows = cur.fetchall()
                    cols = [d[0] for d in cur.description]
            except Exception as e:
                error = str(e)
        else:
            error = "Invalid query selection."
    return render_template("queries.html",
                           queries=QUERIES,
                           cols=cols,
                           rows=rows,
                           title=title,
                           error=error)


# delete
@app.route("/delete", methods=["GET", "POST"])
@login_required
def delete():
    msg = error = None

    if request.method == "POST":
        cid = request.form.get("customer_id")
        try:
            cid_int = int(cid)

            with get_conn() as conn:
                cur = conn.cursor()

                # delete payments for all rentals for customer
                cur.execute("""
                    DELETE FROM Payment
                    WHERE Rental_ID IN (
                        SELECT Rental_ID
                        FROM Rental
                        WHERE Customer_ID = :cid
                    )
                """, {"cid": cid_int})

                # delete rentals for this customer
                cur.execute("""
                    DELETE FROM Rental
                    WHERE Customer_ID = :cid
                """, {"cid": cid_int})

                # delete the customer
                cur.execute("""
                    DELETE FROM Customer
                    WHERE Customer_ID = :cid
                """, {"cid": cid_int})

                conn.commit()

                if cur.rowcount == 0:
                    msg = f"No customer with ID {cid_int}."
                else:
                    msg = f"Deleted customer {cid_int} and related rentals/payments."

        except Exception as e:
            error = str(e)

    # load current customers for display
    cols = rows = None
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT Customer_ID, Full_Name, Email, Phone_Number
                FROM Customer
                ORDER BY Customer_ID
            """)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
    except Exception as e:
        error = str(e)

    return render_template(
        "delete.html",
        message=msg,
        error=error,
        cols=cols,
        rows=rows
    )



# adding/updating page
@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    msg = error = None
    selected = "CUSTOMER"

    if request.method == "POST":
        selected = request.form.get("table", "CUSTOMER").upper()

        try:
            with get_conn() as conn:
                cur = conn.cursor()

                # customer
                if selected == "CUSTOMER":
                    cid = int(request.form.get("customer_id"))
                    name = request.form.get("full_name")
                    email = request.form.get("email")
                    phone = request.form.get("phone")
                    addr = request.form.get("address")
                    dl   = request.form.get("dl")

                    if not name or not email or not dl:
                        raise ValueError("Full_Name, Email, Drivers_License are required.")

                    cur.execute("""
                        UPDATE Customer
                        SET Full_Name = :name,
                            Email = :email,
                            Phone_Number = :phone,
                            Customer_Address = :addr,
                            Drivers_LicenseNumber = :dl
                        WHERE Customer_ID = :cid
                    """, dict(name=name, email=email, phone=phone,
                              addr=addr, dl=dl, cid=cid))

                    if cur.rowcount == 0:
                        cur.execute("""
                            INSERT INTO Customer
                            (Customer_ID, Email, Full_Name, Phone_Number,
                             Customer_Address, Drivers_LicenseNumber, Customer_Password)
                            VALUES (:cid, :email, :name, :phone, :addr, :dl, 'defaultpw')
                        """, dict(cid=cid, email=email, name=name,
                                  phone=phone, addr=addr, dl=dl))

                    msg = f"Customer {cid} saved."

                # vehicle
                elif selected == "VEHICLE":
                    vid = int(request.form.get("vehicle_id"))
                    plate = request.form.get("license_plate")
                    make = request.form.get("vehicle_make")
                    model = request.form.get("vehicle_model")
                    year = int(request.form.get("vehicle_year"))
                    vin = request.form.get("vehicle_vin")

                    if not plate or not make or not model or not vin:
                        raise ValueError("All Vehicle fields except year are required.")

                    cur.execute("""
                        UPDATE Vehicle
                        SET License_Plate = :plate,
                            Vehicle_Make  = :make,
                            Vehicle_Model = :model,
                            Vehicle_Year  = :year,
                            Vehicle_VIN   = :vin
                        WHERE Vehicle_ID = :vid
                    """, dict(plate=plate, make=make, model=model,
                              year=year, vin=vin, vid=vid))

                    if cur.rowcount == 0:
                        cur.execute("""
                            INSERT INTO Vehicle
                            (Vehicle_ID, License_Plate, Vehicle_Make,
                             Vehicle_Model, Vehicle_Year, Vehicle_VIN)
                            VALUES (:vid, :plate, :make, :model, :year, :vin)
                        """, dict(vid=vid, plate=plate, make=make, model=model,
                                  year=year, vin=vin))

                    msg = f"Vehicle {vid} saved."

                # rental
                elif selected == "RENTAL":
                    rid = int(request.form.get("rental_id"))
                    cid = int(request.form.get("customer_id"))
                    vid = int(request.form.get("vehicle_id"))
                    dur_raw = request.form.get("rental_duration")
                    dur = int(dur_raw) if dur_raw else None
                    pickup = request.form.get("pickup_date")
                    return_date = request.form.get("return_date") or None
                    rate = float(request.form.get("rental_rate"))

                    if not pickup:
                        raise ValueError("Pickup_Date is required (YYYY-MM-DD).")

                    params = dict(rid=rid, cid=cid, vid=vid,
                                  dur=dur, pdate=pickup,
                                  rdate=return_date, rate=rate)

                    # update
                    cur.execute("""
                        UPDATE Rental
                        SET Customer_ID     = :cid,
                            Vehicle_ID      = :vid,
                            Rental_Duration = :dur,
                            Pickup_Date     = TO_DATE(:pdate, 'YYYY-MM-DD'),
                            Return_Date     = TO_DATE(:rdate, 'YYYY-MM-DD'),
                            Rental_Rate     = :rate
                        WHERE Rental_ID = :rid
                    """, params)

                    if cur.rowcount == 0:
                        cur.execute("""
                            INSERT INTO Rental
                            (Rental_ID, Customer_ID, Vehicle_ID, Rental_Duration,
                             Pickup_Date, Return_Date, Rental_Rate)
                            VALUES (:rid, :cid, :vid, :dur,
                                    TO_DATE(:pdate, 'YYYY-MM-DD'),
                                    TO_DATE(:rdate, 'YYYY-MM-DD'),
                                    :rate)
                        """, params)

                    msg = f"Rental {rid} saved."

                # payment
                elif selected == "PAYMENT":
                    pid = int(request.form.get("payment_id"))
                    cid = int(request.form.get("customer_id"))
                    rid = int(request.form.get("rental_id"))
                    amount = float(request.form.get("payment_amount"))
                    status = request.form.get("status") or "PENDING"

                    params = dict(pid=pid, cid=cid, rid=rid,
                                  amount=amount, status=status)

                    cur.execute("""
                        UPDATE Payment
                        SET Customer_ID    = :cid,
                            Rental_ID      = :rid,
                            Payment_Amount = :amount,
                            Status         = :status
                        WHERE Payment_ID = :pid
                    """, params)

                    if cur.rowcount == 0:
                        cur.execute("""
                            INSERT INTO Payment
                            (Payment_ID, Customer_ID, Rental_ID,
                             Payment_Amount, Status)
                            VALUES (:pid, :cid, :rid, :amount, :status)
                        """, params)

                    msg = f"Payment {pid} saved."

                else:
                    raise ValueError("Unknown table selection.")

                conn.commit()

        except Exception as e:
            error = str(e)

    # Load current rows for the selected table to show under the form
    cols = rows = None
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            if selected in ("ADMIN", "CUSTOMER", "INVENTORY", "PAYMENT", "RENTAL", "VEHICLE"):
                cur.execute(f"SELECT * FROM {selected}")
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
    except Exception as e:
        if not error:
            error = str(e)

    table_data = get_all_table_data()

    return render_template("add.html",
                           message=msg,
                           error=error,
                           cols=cols,
                           rows=rows,
                           selected_table=selected,
                           table_data=table_data)
    



if __name__ == "__main__":
    app.run(debug=True)

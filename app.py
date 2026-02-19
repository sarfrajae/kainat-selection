import os
import sqlite3
from datetime import datetime
from urllib.parse import quote

from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "kainat-selection-secret-key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "boutique.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_filename TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            size TEXT NOT NULL,
            price REAL NOT NULL,
            is_new_arrival INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/")
def dashboard():
    conn = get_db_connection()
    total_products = conn.execute("SELECT COUNT(*) as count FROM products").fetchone()["count"]
    new_arrivals = conn.execute(
        "SELECT COUNT(*) as count FROM products WHERE is_new_arrival = 1"
    ).fetchone()["count"]
    recent_items = conn.execute(
        "SELECT * FROM products ORDER BY datetime(created_at) DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return render_template(
        "dashboard.html",
        total_products=total_products,
        new_arrivals=new_arrivals,
        recent_items=recent_items,
    )


@app.route("/add-product", methods=["GET", "POST"])
def add_product():
    categories = ["Kurti", "Gown", "Saree", "Dress", "Top"]
    sizes = ["Free", "S", "M", "L", "XL"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        size = request.form.get("size", "")
        price = request.form.get("price", "").strip()
        is_new_arrival = 1 if request.form.get("is_new_arrival") == "on" else 0
        image = request.files.get("image")

        if not name or not category or not size or not price or not image:
            flash("Please fill all fields and upload an image.")
            return render_template("add_product.html", categories=categories, sizes=sizes)

        if category not in categories or size not in sizes:
            flash("Invalid category or size selected.")
            return render_template("add_product.html", categories=categories, sizes=sizes)

        try:
            price_value = float(price)
        except ValueError:
            flash("Price must be a number.")
            return render_template("add_product.html", categories=categories, sizes=sizes)

        if image.filename == "" or not allowed_file(image.filename):
            flash("Please upload a valid image file (png, jpg, jpeg, gif, webp).")
            return render_template("add_product.html", categories=categories, sizes=sizes)

        original_name = secure_filename(image.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        image_filename = f"{timestamp}_{original_name}"
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
        image.save(image_path)

        conn = get_db_connection()
        conn.execute(
            """
            INSERT INTO products (image_filename, name, category, size, price, is_new_arrival, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                image_filename,
                name,
                category,
                size,
                price_value,
                is_new_arrival,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        flash("Product saved successfully.")
        return redirect(url_for("product_list"))

    return render_template("add_product.html", categories=categories, sizes=sizes)


@app.route("/product-list")
def product_list():
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products ORDER BY datetime(created_at) DESC").fetchall()
    conn.close()
    return render_template("product_list.html", products=products)


@app.route("/shop")
def shop():
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products ORDER BY datetime(created_at) DESC").fetchall()
    conn.close()

    shop_products = []
    for product in products:
        product_data = dict(product)
        message = f"Hello Kainat Selection, I want to order {product_data['name']}"
        product_data["whatsapp_link"] = f"https://wa.me/919898617889?text={quote(message)}"
        shop_products.append(product_data)

    return render_template("shop.html", products=shop_products)


@app.route("/delete-product/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    conn = get_db_connection()
    product = conn.execute("SELECT image_filename FROM products WHERE id = ?", (product_id,)).fetchone()
    if product:
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], product["image_filename"])
        if os.path.exists(image_path):
            os.remove(image_path)
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        flash("Product deleted.")
    conn.close()
    return redirect(url_for("product_list"))


init_db()

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
# redeploy trigger

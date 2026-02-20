```python
import os
from datetime import datetime
from urllib.parse import quote
from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# ---------------- APP ----------------
app = Flask(__name__)
app.secret_key = "kainat-selection-secret-key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# ---------------- DATABASE (RENDER POSTGRES FIX) ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found. Add Postgres in Render")

# Force psycopg3
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://")
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------- MODEL ----------------
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    size = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)
    is_new_arrival = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Auto create table
with app.app_context():
    db.create_all()

# ---------------- HELPERS ----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---------------- DASHBOARD ----------------
@app.route("/")
def dashboard():
    total_products = Product.query.count()
    new_arrivals = Product.query.filter_by(is_new_arrival=True).count()
    recent_items = Product.query.order_by(Product.created_at.desc()).limit(5).all()

    return render_template(
        "dashboard.html",
        total_products=total_products,
        new_arrivals=new_arrivals,
        recent_items=recent_items,
    )

# ---------------- ADD PRODUCT ----------------
@app.route("/add-product", methods=["GET", "POST"])
def add_product():
    categories = ["Kurti", "Gown", "Saree", "Dress", "Top"]
    sizes = ["Free", "S", "M", "L", "XL"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        size = request.form.get("size", "")
        price = request.form.get("price", "").strip()
        is_new_arrival = True if request.form.get("is_new_arrival") == "on" else False
        image = request.files.get("image")

        if not name or not category or not size or not price or not image:
            flash("Fill all fields")
            return render_template("add_product.html", categories=categories, sizes=sizes)

        if not allowed_file(image.filename):
            flash("Invalid image format")
            return render_template("add_product.html", categories=categories, sizes=sizes)

        filename = secure_filename(image.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        image_filename = f"{timestamp}_{filename}"
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))

        product = Product(
            image_filename=image_filename,
            name=name,
            category=category,
            size=size,
            price=float(price),
            is_new_arrival=is_new_arrival,
        )

        db.session.add(product)
        db.session.commit()

        flash("Product added")
        return redirect(url_for("product_list"))

    return render_template("add_product.html", categories=categories, sizes=sizes)

# ---------------- PRODUCT LIST ----------------
@app.route("/product-list")
def product_list():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("product_list.html", products=products)

# ---------------- SHOP ----------------
@app.route("/shop")
def shop():
    products = Product.query.order_by(Product.created_at.desc()).all()
    shop_products = []

    for p in products:
        message = f"Hello Kainat Selection, I want to order {p.name}"
        shop_products.append({
            **p.__dict__,
            "whatsapp_link": f"https://wa.me/919898617889?text={quote(message)}"
        })

    return render_template("shop.html", products=shop_products)

# ---------------- DELETE ----------------
@app.route("/delete-product/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    product = Product.query.get(product_id)

    if product:
        path = os.path.join(app.config["UPLOAD_FOLDER"], product.image_filename)
        if os.path.exists(path):
            os.remove(path)

        db.session.delete(product)
        db.session.commit()
        flash("Deleted")

    return redirect(url_for("product_list"))

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
```

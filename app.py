import os
from datetime import datetime
from urllib.parse import quote
from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "kainat-selection-secret-key"

# ================= DATABASE =================
DATABASE_URL = os.getenv("DATABASE_URL")

# Render postgres fix
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ================= FILE UPLOAD =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ================= MODEL =================
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    size = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)
    is_new_arrival = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# create tables
with app.app_context():
    db.create_all()

# ================= HELPERS =================
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ================= DASHBOARD =================
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

# ================= ADD PRODUCT =================
@app.route("/add-product", methods=["GET", "POST"])
def add_product():
    categories = ["Kurti", "Gown", "Saree", "Dress", "Top"]
    sizes = ["Free", "S", "M", "L", "XL"]

    if request.method == "POST":
        name = request.form.get("name")
        category = request.form.get("category")
        size = request.form.get("size")
        price = request.form.get("price")
        is_new_arrival = True if request.form.get("is_new_arrival") == "on" else False
        image = request.files.get("image")

        if not all([name, category, size, price, image]):
            flash("Fill all fields")
            return redirect(request.url)

        if not allowed_file(image.filename):
            flash("Invalid image format")
            return redirect(request.url)

        filename = secure_filename(image.filename)
        unique_name = f"{datetime.now().timestamp()}_{filename}"
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))

        product = Product(
            image_filename=unique_name,
            name=name,
            category=category,
            size=size,
            price=float(price),
            is_new_arrival=is_new_arrival
        )

        db.session.add(product)
        db.session.commit()

        flash("Product added successfully")
        return redirect("/product-list")

    return render_template("add_product.html", categories=categories, sizes=sizes)

# ================= PRODUCT LIST =================
@app.route("/product-list")
def product_list():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("product_list.html", products=products)

# ================= SHOP =================
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

# ================= DELETE =================
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

    return redirect("/product-list")

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
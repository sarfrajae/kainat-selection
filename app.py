import os
from datetime import datetime
from urllib.parse import quote

from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.utils import secure_filename

# ---------------- APP ----------------
app = Flask(__name__)
app.secret_key = "kainat-selection-secret-key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# ---------------- DATABASE ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found. Add Postgres in Render")

DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://")
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ---------------- MODELS ----------------
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(200), nullable=True)  # legacy compatibility
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    size = db.Column(db.String(20), nullable=True)  # legacy compatibility
    price = db.Column(db.Float, nullable=True)  # legacy compatibility
    original_price = db.Column(db.Float, nullable=True)
    selling_price = db.Column(db.Float, nullable=True)
    is_new_arrival = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    images = db.relationship(
        "ProductImage",
        backref="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductImage.sort_order.asc()",
    )
    sizes = db.relationship(
        "ProductSize",
        backref="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductSize.label.asc()",
    )
    orders = db.relationship("Order", backref="product", lazy="select")

    @property
    def effective_original_price(self):
        return self.original_price if self.original_price is not None else (self.price or 0.0)

    @property
    def effective_selling_price(self):
        if self.selling_price is not None:
            return self.selling_price
        if self.price is not None:
            return self.price
        return 0.0

    @property
    def discount_percentage(self):
        original = self.effective_original_price
        selling = self.effective_selling_price
        if original > 0 and selling < original:
            return round(((original - selling) / original) * 100)
        return 0

    @property
    def primary_image_filename(self):
        if self.images:
            return self.images[0].filename
        return self.image_filename

    @property
    def total_stock(self):
        if not self.sizes:
            return 0
        return sum(size.stock for size in self.sizes)


class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    filename = db.Column(db.String(200), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class ProductSize(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    label = db.Column(db.String(20), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.CheckConstraint("stock >= 0", name="ck_product_size_stock_non_negative"),)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    product_size_id = db.Column(db.Integer, db.ForeignKey("product_size.id"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    product_size = db.relationship("ProductSize")


# ---------------- HELPERS ----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_file(file_storage):
    filename = secure_filename(file_storage.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    saved_name = f"{timestamp}_{filename}"
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], saved_name))
    return saved_name


def parse_sizes_from_form():
    labels = request.form.getlist("size_label[]")
    stocks = request.form.getlist("size_stock[]")

    cleaned_sizes = []
    seen = set()

    for idx, raw_label in enumerate(labels):
        label = (raw_label or "").strip()
        raw_stock = (stocks[idx] if idx < len(stocks) else "").strip()

        if not label:
            continue

        if label.lower() in seen:
            continue

        if not raw_stock.isdigit():
            return None, "Stock must be a non-negative number for each size"

        stock = int(raw_stock)
        seen.add(label.lower())
        cleaned_sizes.append({"label": label, "stock": stock})

    if not cleaned_sizes:
        return None, "Add at least one size with stock"

    return cleaned_sizes, None


def ensure_product_columns(engine):
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if "product" not in existing_tables:
        return

    columns = {col["name"] for col in inspector.get_columns("product")}

    with engine.begin() as connection:
        if "original_price" not in columns:
            connection.execute(text("ALTER TABLE product ADD COLUMN original_price FLOAT"))

        if "selling_price" not in columns:
            connection.execute(text("ALTER TABLE product ADD COLUMN selling_price FLOAT"))


def backfill_product_data():
    products = Product.query.all()

    for product in products:
        if product.original_price is None and product.price is not None:
            product.original_price = product.price

        if product.selling_price is None and product.price is not None:
            product.selling_price = product.price

        if not product.images and product.image_filename:
            product.images.append(ProductImage(filename=product.image_filename, sort_order=0))

        if not product.sizes:
            fallback_size = (product.size or "Free").strip() or "Free"
            product.sizes.append(ProductSize(label=fallback_size, stock=10))

    db.session.commit()


def init_db():
    db.create_all()
    ensure_product_columns(db.engine)
    db.create_all()
    backfill_product_data()


with app.app_context():
    init_db()


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

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        original_price_raw = request.form.get("original_price", "").strip()
        selling_price_raw = request.form.get("selling_price", "").strip()
        is_new_arrival = request.form.get("is_new_arrival") == "on"
        images = request.files.getlist("images")

        if not name or not category or not original_price_raw or not selling_price_raw:
            flash("Fill all required fields")
            return render_template("add_product.html", categories=categories)

        try:
            original_price = float(original_price_raw)
            selling_price = float(selling_price_raw)
        except ValueError:
            flash("Enter valid prices")
            return render_template("add_product.html", categories=categories)

        if original_price <= 0 or selling_price <= 0:
            flash("Prices must be greater than zero")
            return render_template("add_product.html", categories=categories)

        if selling_price > original_price:
            flash("Selling price cannot be greater than original price")
            return render_template("add_product.html", categories=categories)

        valid_images = [img for img in images if img and img.filename]
        if not valid_images:
            flash("Upload at least one product image")
            return render_template("add_product.html", categories=categories)

        for image in valid_images:
            if not allowed_file(image.filename):
                flash("Invalid image format")
                return render_template("add_product.html", categories=categories)

        parsed_sizes, size_error = parse_sizes_from_form()
        if size_error:
            flash(size_error)
            return render_template("add_product.html", categories=categories)

        saved_filenames = [save_uploaded_file(image) for image in valid_images]

        product = Product(
            image_filename=saved_filenames[0],
            name=name,
            category=category,
            size=parsed_sizes[0]["label"],
            price=selling_price,
            original_price=original_price,
            selling_price=selling_price,
            is_new_arrival=is_new_arrival,
        )

        db.session.add(product)
        db.session.flush()

        for index, filename in enumerate(saved_filenames):
            db.session.add(ProductImage(product_id=product.id, filename=filename, sort_order=index))

        for size in parsed_sizes:
            db.session.add(ProductSize(product_id=product.id, label=size["label"], stock=size["stock"]))

        db.session.commit()

        flash("Product added")
        return redirect(url_for("product_list"))

    return render_template("add_product.html", categories=categories)


# ---------------- PRODUCT LIST ----------------
@app.route("/product-list")
def product_list():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("product_list.html", products=products)


# ---------------- SHOP ----------------
@app.route("/shop")
def shop():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("shop.html", products=products)


# ---------------- PRODUCT DETAIL ----------------
@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("product_detail.html", product=product)


# ---------------- ORDER ----------------
@app.route("/product/<int:product_id>/order", methods=["POST"])
def place_order(product_id):
    product = Product.query.get_or_404(product_id)

    size_id_raw = request.form.get("size_id", "").strip()
    quantity_raw = request.form.get("quantity", "1").strip()

    if not size_id_raw.isdigit():
        flash("Please select a size")
        return redirect(url_for("product_detail", product_id=product.id))

    if not quantity_raw.isdigit() or int(quantity_raw) <= 0:
        flash("Invalid quantity")
        return redirect(url_for("product_detail", product_id=product.id))

    size = (
        ProductSize.query.filter_by(id=int(size_id_raw), product_id=product.id)
        .with_for_update()
        .first()
    )
    quantity = int(quantity_raw)

    if not size:
        flash("Invalid size selected")
        return redirect(url_for("product_detail", product_id=product.id))

    if size.stock < quantity:
        flash(f"Only {size.stock} item(s) left for size {size.label}")
        return redirect(url_for("product_detail", product_id=product.id))

    size.stock -= quantity

    order = Order(product_id=product.id, product_size_id=size.id, quantity=quantity)
    db.session.add(order)
    db.session.commit()

    message = (
        f"Hello Kainat Selection, I want to order {product.name} "
        f"(Size: {size.label}, Qty: {quantity}, Order ID: {order.id})"
    )
    whatsapp_link = f"https://wa.me/919898617889?text={quote(message)}"

    return redirect(whatsapp_link)


# ---------------- DELETE ----------------
@app.route("/delete-product/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    product = Product.query.get(product_id)

    if product:
        image_files = {img.filename for img in product.images}
        if product.image_filename:
            image_files.add(product.image_filename)

        for filename in image_files:
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
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

from flask import Flask, render_template, g, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app

app = Flask(__name__)
app.secret_key = '78c5441cebb102803b543b56af14707ac27e4d97'
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:rirmakkirill890@localhost:5432/Bakery"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True

db = SQLAlchemy(app)

connections = {
    1: 'postgresql://admin:admin@localhost:5432/Bakery',
    4: 'postgresql://baker_user:baker@localhost:5432/Bakery',
    3: 'postgresql://analyst_user:analyst@localhost:5432/Bakery',
    2: 'postgresql://visitor_user:visitor@localhost:5432/Bakery'
}


class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.user_uris = {}

    def create_session(self, user_id, db_uri):
        engine = create_engine(db_uri)
        Session = sessionmaker(bind=engine)
        self.sessions[user_id] = Session()
        self.user_uris[user_id] = db_uri

    def get_session(self, user_id):
        if user_id not in self.sessions:
            return None
        return self.sessions[user_id]

    def close_session(self, user_id):
        session = self.sessions.pop(user_id, None)
        if session:
            session.close()
            session.bind.dispose()
            del self.user_uris[user_id]

    def close_all_sessions(self):
        for user_id in list(self.sessions.keys()):
            self.close_session(user_id)


session_manager = SessionManager()


def get_db_engine(user_role):
    connection = connections.get(user_role)
    if connection:
        engine = create_engine(connection)
        g.db_engine = engine
        return engine
    else:
        raise ValueError("Invalid user role")


def check_db_connection():
    engine = get_db_engine(session['userrole'])
    with engine.connect() as connection:
        try:
            connection.execute(text('SELECT 1'))
            print('Підключення до бази даних успішне')
        except Exception as e:
            print(f'Помилка підключення до бази даних: {str(e)}')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Перевірка наявності користувача з таким же ім'ям чи email
        existing_user = User.query.filter_by(username=username).first()
        existing_email = User.query.filter_by(email=email).first()
        if existing_user or existing_email:
            flash('Користувач з таким іменем або email вже існує', 'error')
            return render_template('fail_reg.html')
            # return redirect(url_for('register'))

        # Генерація хеша пароля
        hashed_password = generate_password_hash(password)

        # Створення нового користувача з хешованим паролем
        new_user = User(username=username, email=email, encoded_password=hashed_password)

        try:
            db.session.add(new_user)
            db.session.commit()

            session['userrole'] = new_user.user_role
            session['userid'] = new_user.user_id
            db_connection = connections.get(new_user.user_role)
            session_manager.create_session(new_user.user_id, db_connection)
            check_db_connection()
            g.user_id = new_user.user_id
            flash('Реєстрація пройшла успішно', 'success')
            return render_template('success.html')
            #return redirect(url_for('index'))
        except IntegrityError:
            db.session.rollback()
            flash('Помилка при реєстрації користувача', 'error')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.encoded_password, password):
            session['userrole'] = user.user_role
            session['userid'] = user.user_id
            g.user_id = user.user_id
            db_connection = connections.get(user.user_role)
            session_manager.create_session(user.user_id, db_connection)
            check_db_connection()
            flash('Авторизація пройшла успішно', 'success')
            return render_template('success.html')
            #return redirect(url_for('index', userrole=user.user_role))
        else:
            flash('Помилка при реєстрації користувача', 'error')
            return render_template('fail_login.html')
            # return redirect(url_for('login'))

    return render_template('login.html')


# Модель користувача
class User(db.Model):
    __tablename__ = 'user'
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    encoded_password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    user_role = db.Column(db.Integer, db.ForeignKey('user_role.role_id'), nullable=False)
    balance = db.Column(db.Numeric(8, 2), nullable=False)


# Модель ролей користувачів
class UserRole(db.Model):
    __tablename__ = 'user_role'
    role_id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(64), nullable=False)


# Модель товару
class Product(db.Model):
    __tablename__ = 'product'
    product_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.String(4096))
    price = db.Column(db.Numeric(8, 2), nullable=False)
    recipe_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)


# Модель рецепту
class Recipe(db.Model):
    __tablename__ = 'recipe'
    recipe_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(4096), nullable=False)


# Модель замовлення
class Order(db.Model):
    __tablename__ = 'order'
    order_id = db.Column(db.Integer, primary_key=True)
    order_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    price = db.Column(db.Numeric(8, 2), nullable=False)
    status = db.Column(db.Boolean, nullable=False)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    products = db.relationship('Product', secondary='product_to_order')


# Модель відгуків на замовлення
class OrderReview(db.Model):
    __tablename__ = 'order_review'
    review_order_id = db.Column(db.Integer, primary_key=True)
    review_text = db.Column(db.String(4096))
    rating = db.Column(db.Integer, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.order_id'), nullable=False)


# Модель відгуків на продукти
class ProductReview(db.Model):
    __tablename__ = 'product_review'
    review_id = db.Column(db.Integer, primary_key=True)
    review_text = db.Column(db.String(4096))
    rating = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.product_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)


# Зв'язувальна таблиця між продуктами і замовленнями
class ProductToOrder(db.Model):
    __tablename__ = 'product_to_order'
    product_id = db.Column(db.Integer, db.ForeignKey('product.product_id'), primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.order_id'), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)


def get_db_session():
    if 'db_session' not in g:
        db_uri = connections.get(session.get('userrole'))
        if db_uri:
            engine = create_engine(db_uri, poolclass=NullPool)
            Session = sessionmaker(bind=engine)
            g.db_session = Session()
    return g.db_session


@app.teardown_appcontext
def teardown_db_session(exception=None):
    # engine = getattr(g, 'db_engine', None)
    # if engine is not None:
    #     engine.dispose()
    user_id = g.get('user_id')
    if user_id is not None:
        session_manager.close_session(user_id)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/products', methods=['GET'])
def get_products():
    products = Product.query.all()
    return render_template('products.html', products=products)


@app.route('/orders', methods=['GET'])
def get_orders():
    orders = Order.query.all()
    return render_template('orders.html', orders=orders)


# Функція для аутентифікації користувача
# def authenticate(username, password):
#     user = User.query.filter_by(username=username).first()
#     if user and check_password_hash(user.encoded_password, password):
#         session['user_id'] = user.user_id
#         session['role'] = user.user_role
#         return True
#     return False
#
# # Функція для перевірки ролі користувача
# def is_admin_or_analyst():
#     role = session.get('role')
#     if role == 'administrator' or role == 'financial_analyst':
#         return True
#     return False


@app.route('/logout')
def logout():
    # Видаляємо всі дані сесії користувача
    session_manager.close_session(session['userid'])
    session.clear()
    g.db_session.close()

    # Викликаємо teardown функцію для закриття підключення до бази даних
    #teardown_db_session()
    flash('Ви вийшли з облікового запису', 'success')
    return render_template('logout.html')
    # return redirect(url_for('login'))


if __name__ == '__main__':
    app.run()

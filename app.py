from flask import Flask, render_template, g, redirect, url_for, flash, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError
from hashlib import sha256
from sqlalchemy.exc import OperationalError
from decimal import Decimal
from threading import Thread
import sys
import os
from datetime import datetime, date, timedelta

app = Flask(__name__)
app.secret_key = '78c5441cebb102803b543b56af14707ac27e4d97'
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://default_user:5994471abb01112afcc18159f6cc74b4f511b99806da59b3caf5a9c173cacfc5@localhost:5432/Bakery"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True

db = SQLAlchemy(app)


class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.user_uris = {}

    def __del__(self):
        self.close_all_sessions()

    def create_session(self, user_id, db_uri):
        engine = create_engine(db_uri)
        session_factory = sessionmaker(bind=engine)
        Session = scoped_session(session_factory)
        self.sessions[user_id] = Session
        self.user_uris[user_id] = db_uri

    def get_session(self, user_id):

        if user_id not in self.sessions:
            self.create_session(user_id, self.user_uris[user_id])
            session1 = self.sessions[user_id]
            return session1
        return self.sessions[user_id]

    def execute_query(self, user_id, query, params=None):
        session_find = self.get_session(user_id)
        if session_find:
            try:
                with session_find.connection() as connect:
                    query = text(query)
                    if params:
                        result = connect.execute(query, params)
                    else:
                        result = connect.execute(query)  # session_find.execute(query)
                    connect.commit()  # session_find.commit()
                    # session_find.close()
                    return result.fetchall() if result.returns_rows else None
            except OperationalError as e:
                print(f"Error executing query: {e}")
                return None
        else:
            print("Session not found.")
            return None

    def close_session(self, user_id):
        session1: scoped_session = self.sessions.pop(user_id, None)

        if session1:
            session1.close()
            session1.bind.dispose()

            del self.user_uris[user_id]

            # try:
            #     session1.commit()  # Завершаем транзакцию
            # except Exception as e:
            #     session1.rollback()  # Откатываем транзакцию в случае ошибки
            #     print(f"Error during session commit: {e}")
            # else:
            # session1.rollback()

    def close_all_sessions(self):
        user_ids = list(self.sessions.keys())  # list(self.sessions.keys())
        for user_id in user_ids:
            self.close_session(user_id)


session_manager = SessionManager()


def hash_password(password):
    return sha256(password.encode()).hexdigest()


# def get_db_engine(username, hashed_password):
#     connection = f"postgresql://{username}:{hashed_password}@localhost:5432/Bakery"
#     if connection:
#         engine = create_engine(connection)
#         g.db_engine = engine
#         return engine
#     else:
#         raise ValueError("Invalid user role")


def check_db_connection(user_id):
    db_session = session_manager.get_session(user_id)
    with db_session.connection() as connection:
        try:
            connection.execute(text('SELECT 1'))
            print('Підключення до бази даних успішне')
        except Exception as e:
            print(f'Помилка підключення до бази даних: {str(e)}')


# def check_db_connection(username, password):
#     #session_user = session_manager.get_session()
#     global engine
#     engine = getattr(g, 'db_engine', None)
#     if engine is None:
#         engine = get_db_engine(username, password)
#     with engine.connect() as connection:
#         try:
#             connection.execute(text('SELECT 1'))
#             print('Підключення до бази даних успішне')
#         except Exception as e:
#             print(f'Помилка підключення до бази даних: {str(e)}')


def execute_sql_script(sql_script):
    try:
        db.session.execute(text(sql_script))
        db.session.commit()
        print("SQL script executed successfully!")
    except IntegrityError as e:
        db.session.rollback()
        print(f"Error executing SQL script: {e}")


def create_user_and_grant_role(username, password, role='visitor'):
    create_user_script = """
    CREATE USER {username} WITH PASSWORD '{password}';
    GRANT {role} TO {username};
    """
    sql_script = create_user_script.format(username=username, password=password, role=role)
    execute_sql_script(sql_script)


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
        hashed_password = hash_password(password)

        # Створення нового користувача з хешованим паролем
        new_user = User(username=username, email=email)

        try:
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Помилка при реєстрації користувача: email не корректний', 'error')
            return render_template('fail_reg.html')
        else:
            create_user_and_grant_role(username=username, password=hashed_password)
            session['userrole'] = new_user.user_role
            session['userid'] = new_user.user_id

            db_connection = f"postgresql://{username}:{hashed_password}@localhost:5432/Bakery"
            session_manager.create_session(new_user.user_id, db_connection)
            check_db_connection(new_user.user_id)

            g.user_id = new_user.user_id
            flash('Реєстрація пройшла успішно', 'success')
            return render_template('success.html')
            # return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        hashed_password = hash_password(password)

        try:

            db_connection = f"postgresql://{username}:{hashed_password}@localhost:5432/Bakery"

            # print(session_manager.get_session(user.user_id))
            session['userrole'] = user.user_role
            session['userid'] = user.user_id

            session_manager.create_session(user.user_id, db_connection)
            check_db_connection(user.user_id)
            g.user_id = user.user_id
            flash('Авторизація пройшла успішно', 'success')
            return render_template('success.html')
        except:
            flash('Помилка при ідентифікації користувача', 'error')
            return render_template('fail_login.html')
        # return redirect(url_for('login'))

    return render_template('login.html')


# Модель користувача
class User(db.Model):
    __tablename__ = 'user'
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    # encoded_password = db.Column(db.String(255), nullable=False)
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
    recipe_id = db.Column(db.Integer)
    quantity = db.Column(db.Integer, nullable=False)


# Модель рецепту
class Recipe(db.Model):
    __tablename__ = 'recipe'
    recipe_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(4096), default='поки не доступно')
    product_id = db.Column(db.Integer, db.ForeignKey('product.product_id'))


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


#
# def get_db_session():
#     if 'db_session' not in g:
#         db_uri = connections.get(session.get('userrole'))
#         if db_uri:
#             engine = create_engine(db_uri, poolclass=NullPool)
#             Session = sessionmaker(bind=engine)
#             g.db_session = Session()
#     return g.db_session

# @app.teardown_appcontext
# def teardown_db_session(exception=None):
#     # engine = getattr(g, 'db_engine', None)
#     # if engine is not None:
#     #     engine.dispose()
#     user_id = g.get('user_id')
#     if user_id is not None:
#         session_manager.close_session(user_id)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/profile')
def profile():
    user_id = session.get('userid')
    user = User.query.filter_by(user_id=user_id).first()
    if user:
        return render_template('profile.html', user=user)
    else:
        return 'Користувача не знайдено', 404


@app.route('/add_money', methods=['GET', 'POST'])
def add_money():
    if request.method == 'POST':
        amount = request.form.get('amount')
        try:
            amount = Decimal(amount)
        except:
            flash('Будь ласка, введіть числове значення', 'error')
            return render_template('error_page.html', path='add_money')
        else:

            # Получаем текущего пользователя
            user_id = session.get('userid')

            user = User.query.filter_by(user_id=user_id).first()

            user.balance += amount
            session['balance'] = user.balance
            db.session.commit()
            return jsonify({'balance': float(user.balance)}), 200
        # Возвращаем пользователя на страницу с продуктами с обновленным балансом
        # return redirect(url_for('get_products'))

    return render_template('add_money.html')


@app.route('/products', methods=['GET'])
def get_products():
    if 'userid' in session:
        user_id = session['userid']
        user_role = session['userrole']
        user_session = session_manager.get_session(user_id)
        # query = text(f"SELECT * FROM product")

        products = user_session.query(Product).all()

        # products = session_manager.execute_query(user_id, query)  #user_session.query(Product).all()
        if products:
            user_session.commit()
            #user_session.close()
            # обработка результатов запроса
            return render_template('products.html', products=products)
        else:
            flash('Помилка при отриманні даних про продукти', 'error')
            return redirect(url_for('index'))  # render_template('error.html')
    else:
        flash('Спочатку увійдіть в систему', 'error')
        return render_template('login.html')


@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    # Проверяем, что пользователь авторизован и имеет роль пекаря

    user_id = session['userid']
    user_role = session['userrole']
    user_session = session_manager.get_session(user_id)
    if request.method == 'POST':
        # Получаем данные из формы
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])  # Преобразуем цену в числовой формат
        quantity = int(request.form['quantity'])  # Преобразуем количество в целочисленный формат

        existing_product = user_session.query(Product).filter_by(name=name).first()
        if existing_product:
            flash('Такий продукт вже існує', 'error')
            return render_template('error_page.html', path='add_product')

        if quantity <= 0 or price < 0:
            flash("Кількість продукту або/чи вартість продукту не може бути від'ємною", 'error')
            return render_template('error_page.html', path='add_product')

        try:
            # new_recipe = Recipe(name=name)
            # user_session.add(new_recipe)
            # user_session.commit()

            new_product = Product(name=name, description=description, price=price, quantity=quantity)
            user_session.add(new_product)
            user_session.commit()
            """Trigger works"""

            new_recipe = user_session.query(Recipe).filter_by(product_id=new_product.product_id).first()
            new_product.recipe_id = new_recipe.recipe_id
            user_session.commit()
            # new_recipe.product_id = new_product.product_id
            # user_session.commit()

            flash('Продукт успішно додано', 'success')
            return redirect(url_for('get_products'))
        except:
            flash('У вас немає прав для додавання продуктів', 'error')
            return render_template('error_page.html', path='get_products') #redirect(url_for('index'))
    else:
        # Если метод запроса GET, просто показываем форму для добавления продукта
        user_session.close()
        return render_template('add_product.html')




@app.route('/update_product/<int:product_id>', methods=['GET', 'POST'])
def update_product(product_id):
    # Проверяем, что пользователь авторизован и имеет роль пекаря
    #if 'userid' in session and session.get('userrole') == 4:
    user_id = session['userid']
    user_role = session['userrole']
    user_session = session_manager.get_session(user_id)
    # Получаем продукт для обновления
    product = user_session.query(Product).filter_by(product_id=product_id).first()

    if product:
        if request.method == 'POST':
            # Получаем данные из формы
            name = request.form['name']
            description = request.form['description']
            price = float(request.form['price'])
            quantity = int(request.form['quantity'])
            query = f"""
                UPDATE product
                SET name = '{name}', description = '{description}', price = {price}, quantity = {quantity}
                WHERE product_id = {product_id}
                """

            # Обновляем данные продукта
            try:
                session_manager.execute_query(user_id, query)
                flash('Продукт успішно редаговано', 'success')
                return redirect(url_for('get_products'))
            except:
                #user_session.rollback()
                flash('Немає прав доступа для редагування продукта', 'error')
                return render_template('error_page.html', path='get_products')#redirect(url_for('index'))
        else:
            user_session.commit() #user_session.close()
            return render_template('update_product.html', product=product)
    else:
        flash('Продукт не знайдено', 'error')
        return redirect(url_for('index'))




@app.route('/delete_product/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    #if 'userid' in session: #and session.get('userrole') == 4:
    user_id = session['userid']
    user_session = session_manager.get_session(user_id)
    if request.method == 'DELETE':
        product = user_session.query(Product).filter_by(product_id=product_id).first()

        # recipe = user_session.query(Recipe).filter_by(name=product.name).first()
        if product:
            try:
                user_session.delete(product)
                user_session.commit()

                # user_session.delete(recipe)
                # user_session.commit()
            except:
                user_session.rollback()
                return jsonify({'message': 'Немає прав для видалення'})
                #flash('Ви не маєте дозволу для видалення продукта', 'error')
                #return render_template('error_page.html', path='get_products')
            else:
                #flash('Продукт успішно видалено', 'success')
                return jsonify({'message': 'Продукт успішно видалено'}), 200
        else:
            flash('Продукт не знайдено', 'error')
    # else:
    #     flash('Ви не маєте дозволу для видалення продукта', 'error')
    #     return render_template('error_page.html', path='get_products')


@app.route('/orders', methods=['GET'])
def get_orders():
    user_id = session.get('userid')
    user_role = session.get('userrole')
    # if user_id and user_role == 2:
    products = {}
    user_session = session_manager.get_session(user_id)

    try:
        orders = user_session.query(Order).filter_by(user_id=user_id).all()

        for order in orders:
            for product_id_in_order in user_session.query(ProductToOrder).filter_by(order_id=order.order_id).all():
                product = user_session.query(Product).filter_by(product_id=product_id_in_order.product_id).first()
                products.setdefault(order.order_id, []).append({product.name: product_id_in_order.quantity})
                #products.setdefault(order.order_id, []).append(product)

        # user_session.commit()
        user_session.close()
        return render_template('orders.html', orders=orders, products=products)

    except:
        flash("Ви не маєте права переглядати замовлення")
        return render_template('error_page.html', path='index')



@app.route('/create_order', methods=['GET', 'POST'])
def create_order():
    user_id = session.get('userid')
    user_session = session_manager.get_session(user_id)
    if request.method == 'POST':
        selected_products = {}
        total_price = 0
        products = []

        for product in user_session.query(Product).all():
            quantity = int(request.form.get(f'product_{product.product_id}', 0))
            if quantity > 0:
                selected_products[product] = quantity
                total_price += product.price * quantity
                try:
                    product.quantity -= quantity
                    user_session.commit()
                except IntegrityError:
                    user_session.rollback()  # Откатываем транзакцию
                    flash('Недопустима кількість продуктів', 'error')
                    return render_template('error_page.html', path='create_order')  # create_order'))
                products.append(product)

        # Создаем новый заказ
        order = Order(user_id=user_id, order_date=date.today(), price=total_price, status=False)
        user_session.add(order)
        user_session.commit()

        for product, quantity in selected_products.items():
            order_product = ProductToOrder(product_id=product.product_id, order_id=order.order_id, quantity=quantity)
            user_session.add(order_product)
            user_session.commit()

        user_session.close()
        return redirect(url_for('get_orders', products=products))  # Перенаправление на страницу просмотра заказов
    else:
        products = user_session.query(Product).all()
        return render_template('create_order.html', products=products)


@app.route('/edit_order/<int:order_id>', methods=['GET', 'POST'])
def edit_order(order_id):
    user_id = session.get('userid')
    user_session = session_manager.get_session(user_id)
    order = user_session.query(Order).filter_by(order_id=order_id, user_id=user_id).first()
    if not order:
        flash('Замовлення не знайдено або ви не маєте прав доступу до цього замовлення', 'error')
        return redirect(url_for('get_orders'))

    if request.method == 'POST':
        updated_products = {}
        total_price = 0
        products = []

        for product in user_session.query(Product).all():
            quantity = int(request.form.get(f'product_{product.product_id}', 0))
            if quantity > 0:
                updated_products[product] = quantity
                total_price += product.price * quantity
                products.append(product)
                # product.quantity -= quantity

        for product, quantity in updated_products.items():
            product_in_order = user_session.query(ProductToOrder).filter_by(product_id=product.product_id,
                                                                            order_id=order.order_id).first()
            if not product_in_order:
                order_product = ProductToOrder(product_id=product.product_id, order_id=order.order_id,
                                               quantity=quantity)
                product.quantity -= quantity
                user_session.add(order_product)
                user_session.commit()

        # Обновляем общую цену заказа
        order.price = total_price
        user_session.commit()
        # user_session.close()

        flash('Замовлення успішно оновлено', 'success')
        return redirect(url_for('get_orders'))

    else:
        products = user_session.query(Product).all()
        products_to_order = user_session.query(ProductToOrder).filter_by(order_id=order.order_id).all()
        user_session.close()
        return render_template('edit_order.html', order=order, products=products,
                               products_to_order=products_to_order)  #


@app.route('/delete_order/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    user_id = session.get('userid')
    user_session = session_manager.get_session(user_id)

    # Проверяем, существует ли заказ с указанным ID и принадлежит ли он текущему пользователю
    order = user_session.query(Order).filter_by(order_id=order_id, user_id=user_id).first()
    products_to_order = user_session.query(ProductToOrder).filter_by(order_id=order.order_id).all()
    for product_to_order in products_to_order:
        product = user_session.query(Product).filter_by(product_id=product_to_order.product_id).first()
        product.quantity += product_to_order.quantity


    if not order:
        return jsonify({'error': 'Замовлення не знайдене або авторизація не виконана'})

    # Удаляем заказ из базы данных
    try:
        current_user = User.query.filter_by(user_id=user_id).first()
        current_user.balance += order.price
        db.session.commit()

        user_session.delete(order)
        user_session.commit()
        return jsonify({'message': 'Замовлення успішно видалено'}), 200
    except:
        user_session.rollback()
        return jsonify({'error': 'Немає прав для видалення замовлення'})


@app.route('/confirm_order/<int:order_id>', methods=['POST'])
def confirm_order(order_id):
    user_id = session.get('userid')
    user_session = session_manager.get_session(user_id)

    order = user_session.query(Order).filter_by(order_id=order_id, user_id=user_id).first()
    current_user = User.query.filter_by(user_id=user_id).first()
    if not order:
        return jsonify({'error': 'Замовлення не знайдене або авторизація не виконана'})
    try:
    # if current_user.balance >= order.price:
        current_user.balance -= order.price
        db.session.commit()
    # else:

    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': 'На жаль, не вистачає коштів на здійснення замовлення'})
    #     return jsonify({'error': 'Помилка при відніманні коштів з балансу користувача'})


    # Устанавливаем статус заказа как подтвержденный
    order.status = True

    # Устанавливаем start_date как текущее время
    order.start_date = datetime.now()

    # Вычисляем end_date по формуле: текущее время + количество продуктов в заказе * некоторое количество минут или часов
    order_products = user_session.query(ProductToOrder).filter_by(order_id=order.order_id).all()  # len(order.products_to_order)
    num_products = sum([product.quantity for product in order_products])
    end_date = datetime.now() + timedelta(minutes=num_products * 7)  # Например, по 7 минут на продукт
    order.end_date = end_date
    user_session.commit()
    db.session.commit()

    return jsonify({'message': 'Замовлення успішно підтверджено'})


@app.route('/order_reviews', methods=['GET'])
def get_order_reviews():
    user_id = session.get('userid')
    userrole = session.get('userrole', None)
    user_session = session_manager.get_session(user_id)

    if user_id and userrole == 2:

        orders_user = user_session.query(Order).filter_by(user_id=user_id).all()
        order_ids = [order.order_id for order in orders_user]
        order_reviews = user_session.query(OrderReview).filter(OrderReview.order_id.in_(order_ids)).all()


    elif user_id and userrole in (1, 3):
        order_reviews = user_session.query(OrderReview).all()


    user_session.close()
    return render_template('order_reviews.html', order_reviews=order_reviews)


@app.route('/add_order_review/<int:order_id>', methods=['GET', 'POST'])
def add_order_review(order_id):
    if 'userid' not in session:
        flash('Спочатку увійдіть в систему', 'error')
        return render_template('error_page.html', path='login')

    user_id = session['userid']
    userrole = session['userrole']
    user_session = session_manager.get_session(user_id)
    if request.method == 'POST':
        # order_id = request.form['order_id']
        review_text = request.form['review_text']
        rating = request.form['rating']

        # Проверяем, что все поля заполнены
        if not review_text or not rating:
            flash('Заповніть всі поля, будь ласка', 'error')
            return render_template('error_page.html', path='get_orders')

        order_review = user_session.query(OrderReview).filter_by(order_id=order_id).first()
        if order_review:
            flash('Відгук до такого замовлення вже існує', 'error')
            return render_template('error_page.html', path='get_orders')

        # Добавляем отзыв в базу данных
        try:
            new_review = OrderReview(order_id=order_id, review_text=review_text, rating=rating)
            user_session.add(new_review)
            user_session.commit()
            #flash('Відгук успішно додано', 'success')
            return redirect(url_for('get_order_reviews'))
        except Exception as e:
            flash('Помилка при створенні відгука: ', 'error')
            user_session.rollback()
            return render_template('error_page.html', path='get_orders')
    else:
        return render_template('add_order_review.html', order_id=order_id)



@app.route('/edit_order_review/<int:review_order_id>', methods=['GET', 'POST'])
def edit_order_review(review_order_id):
    # Проверяем, что пользователь авторизован и имеет роль пекаря
    #if 'userid' in session and session.get('userrole') == 4:
    user_id = session['userid']
    user_role = session['userrole']
    user_session = session_manager.get_session(user_id)
    # Получаем продукт для обновления
    order_review = user_session.query(OrderReview).filter_by(review_order_id=review_order_id).first()
    order = user_session.query(Order).filter_by(order_id=order_review.order_id).first()

    if order_review:
        if request.method == 'POST':
            # Получаем данные из формы
            review_text = request.form['review_text']
            rating = request.form['rating']
            order_id = order.order_id
            query = f"""
                UPDATE order_review
                SET review_text = '{review_text}', rating = {rating}, order_id = {order_id}
                WHERE review_order_id = {review_order_id}
                """

            # Обновляем данные продукта
            try:
                session_manager.execute_query(user_id, query)
                flash('Замовлення успішно редаговано', 'success')
                return redirect(url_for('get_order_reviews'))
            except:
                #user_session.rollback()
                flash('Немає прав доступа для редагування замовлення', 'error')
                return render_template('error_page.html', path='get_order_reviews')  #redirect(url_for('index'))
        else:
            user_session.commit() #user_session.close()
            return render_template('edit_order_review.html', order_id=order.order_id, order_review=order_review)
    else:
        flash('Замовлення не знайдено', 'error')
        return redirect(url_for('index'))


@app.route('/delete_order_review/<int:review_order_id>', methods=['DELETE'])
def delete_order_review(review_order_id):
    #if 'userid' in session: #and session.get('userrole') == 4:
    user_id = session['userid']
    user_session = session_manager.get_session(user_id)
    if request.method == 'DELETE':
        order_review = user_session.query(OrderReview).filter_by(review_order_id=review_order_id).first()
        if order_review:
            try:
                user_session.delete(order_review)
                user_session.commit()
            except:
                user_session.rollback()
                return jsonify({'message': 'Немає прав для видалення'})
                #flash('Ви не маєте дозволу для видалення продукта', 'error')
                #return render_template('error_page.html', path='get_products')
            else:
                #flash('Продукт успішно видалено', 'success')
                return jsonify({'message': 'Відгук замовлення успішно видалено'}), 200
        else:
            flash('Продукт не знайдено', 'error')



@app.route('/product_reviews', methods=['GET'])
def get_product_reviews():
    user_id = session.get('userid')
    userrole = session.get('userrole', None)
    user_session = session_manager.get_session(user_id)

    if user_id and userrole == 2:
        product_reviews = user_session.query(ProductReview).filter_by(user_id=user_id).all()
        products = [user_session.query(Product).filter_by(product_id=product_review.product_id).first() for product_review in product_reviews]


    elif user_id and userrole in (1, 3):
        product_reviews = user_session.query(ProductReview).all()
        products = [user_session.query(Product).filter_by(product_id=product_review.product_id).first() for product_review in product_reviews]

    user_session.close()
    return render_template('product_reviews.html', product_reviews=product_reviews, products=products)


@app.route('/add_product_review/<int:product_id>', methods=['GET', 'POST'])
def add_product_review(product_id):
    if 'userid' not in session:
        flash('Спочатку увійдіть в систему', 'error')
        return render_template('error_page.html', path='login')

    user_id = session['userid']
    userrole = session['userrole']
    user_session = session_manager.get_session(user_id)
    if request.method == 'POST':
        review_text = request.form['review_text']
        rating = request.form['rating']

        # Проверяем, что все поля заполнены
        if not review_text or not rating:
            flash('Заповніть всі поля, будь ласка', 'error')
            return render_template('error_page.html', path='get_products')

        product_review = user_session.query(ProductReview).filter_by(product_id=product_id, user_id=user_id).first()
        if product_review:
            flash('Відгук до такого замовлення вже існує', 'error')
            return render_template('error_page.html', path='get_products')

        # Добавляем отзыв в базу данных
        try:
            new_review = ProductReview(review_text=review_text, rating=rating, product_id=product_id, user_id=user_id)
            user_session.add(new_review)
            user_session.commit()
            #flash('Відгук успішно додано', 'success')
            return redirect(url_for('get_product_reviews'))
        except Exception as e:
            flash('Помилка при створенні відгука: ' + str(e), 'error')
            user_session.rollback()
            return render_template('error_page.html', path='get_products')
    else:
        product = user_session.query(Product).filter_by(product_id=product_id).first()
        return render_template('add_product_review.html', product_id=product_id, product=product)


@app.route('/edit_product_review/<int:review_id>', methods=['GET', 'POST'])
def edit_product_review(review_id):
    # Проверяем, что пользователь авторизован и имеет роль пекаря
    #if 'userid' in session and session.get('userrole') == 4:
    user_id = session['userid']
    user_role = session['userrole']
    user_session = session_manager.get_session(user_id)
    # Получаем продукт для обновления
    product_review = user_session.query(ProductReview).filter_by(review_id=review_id).first()

    if product_review:
        if request.method == 'POST':
            # Получаем данные из формы
            review_text = request.form['review_text']
            rating = request.form['rating']
            query = f"""
                UPDATE product_review
                SET review_text = '{review_text}', rating = {rating}
                WHERE review_id = {review_id}
                """

            # Обновляем данные продукта
            try:
                session_manager.execute_query(user_id, query)
                flash('Замовлення успішно редаговано', 'success')
                return redirect(url_for('get_product_reviews'))
            except:
                #user_session.rollback()
                flash('Немає прав доступа для редагування замовлення', 'error')
                return render_template('error_page.html', path='get_product_reviews')  #redirect(url_for('index'))
        else:
            user_session.commit() #user_session.close()
            return render_template('edit_product_review.html', product_review=product_review)
    else:
        flash('Замовлення не знайдено', 'error')
        return redirect(url_for('index'))


@app.route('/delete_product_review/<int:review_id>', methods=['DELETE'])
def delete_product_review(review_id):
    #if 'userid' in session: #and session.get('userrole') == 4:
    user_id = session['userid']
    user_session = session_manager.get_session(user_id)
    if request.method == 'DELETE':
        product_review = user_session.query(ProductReview).filter_by(review_id=review_id).first()
        if product_review:
            try:
                user_session.delete(product_review)
                user_session.commit()
            except:
                user_session.rollback()
                return jsonify({'message': 'Немає прав для видалення'})
            else:
                #flash('Продукт успішно видалено', 'success')
                return jsonify({'message': 'Відгук продукта успішно видалено'}), 200
        else:
            flash('Продукт не знайдено', 'error')


@app.route('/recipies', methods=['GET'])
def get_recipies():
    if 'userid' in session:
        user_id = session['userid']
        user_role = session['userrole']
        user_session = session_manager.get_session(user_id)
        # query = text(f"SELECT * FROM product")

        recipies = user_session.query(Recipe).all()

        # products = session_manager.execute_query(user_id, query)  #user_session.query(Product).all()
        if recipies:
            user_session.commit()
            #user_session.close()
            # обработка результатов запроса
            return render_template('recipies.html', recipies=recipies)
        else:
            flash('Помилка при отриманні даних про продукти', 'error')
            return redirect(url_for('index'))  # render_template('error.html')
    else:
        flash('Спочатку увійдіть в систему', 'error')
        return render_template('login.html')



@app.route('/edit_recipe/<int:recipe_id>', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    # Проверяем, что пользователь авторизован и имеет роль пекаря
    #if 'userid' in session and session.get('userrole') == 4:
    user_id = session['userid']
    user_role = session['userrole']
    user_session = session_manager.get_session(user_id)
    # Получаем продукт для обновления
    recipe = user_session.query(Recipe).filter_by(recipe_id=recipe_id).first()

    if recipe:
        if request.method == 'POST':
            # Получаем данные из формы
            name = request.form['name']
            description = request.form['description']
            query = f"""
                UPDATE recipe
                SET name = '{name}', description = '{description}'
                WHERE recipe_id = {recipe_id}
                """

            # Обновляем данные продукта
            try:
                session_manager.execute_query(user_id, query)
                flash('Рецепт оновлено', 'success')
                return redirect(url_for('get_recipies'))
            except:
                #user_session.rollback()
                flash('Немає прав доступа для редагування рецепта', 'error')
                return render_template('error_page.html', path='get_recipies')  #redirect(url_for('index'))
        else:
            user_session.commit() #user_session.close()
            return render_template('edit_recipe.html', recipe=recipe)
    else:
        flash('Рецепт не знайдено', 'error')
        return redirect(url_for('index'))


@app.route('/delete_recipe/<int:recipe_id>', methods=['DELETE'])
def delete_recipe(recipe_id):
    #if 'userid' in session: #and session.get('userrole') == 4:
    user_id = session['userid']
    user_session = session_manager.get_session(user_id)
    if request.method == 'DELETE':
        recipe = user_session.query(Recipe).filter_by(recipe_id=recipe_id).first()
        if recipe:
            try:
                user_session.delete(recipe)
                user_session.commit()
            except Exception as e:
                user_session.rollback()
                return jsonify({'message': f'Немає прав для видалення {str(e)}'})
            else:
                #flash('Продукт успішно видалено', 'success')
                return jsonify({'message': 'Відгук рецепта успішно видалено'}), 200
        else:
            flash('Продукт не знайдено', 'error')


@app.route('/orders_with_details')
def orders_with_details():
    user_id = session.get('userid')
    user_session = session_manager.get_session(user_id)

    if not user_id:
        flash('Вам потрібно війти в систему.', 'error')
        return redirect(url_for('login'))

    query = f"""
        SELECT 
            o.order_id,
            o.order_date,
            o.user_id,
            o.product_id,
            o.product_name,
            o.product_price,
            o.quantity,
            o.total_price
        FROM orders_with_details o
        WHERE o.user_id = {user_id}
    """

    orders_with_details = session_manager.execute_query(user_id, query)

    return render_template('orders_with_details.html', orders_with_details=orders_with_details)


@app.route('/logout')
def logout():
    # Видаляємо всі дані сесії користувача
    session_manager.close_session(session['userid'])
    # teardown_db_session()
    session_manager.close_all_sessions()
    session.clear()

    flash('Ви вийшли з облікового запису', 'success')
    return render_template('logout.html')




if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user, login_user, logout_user, LoginManager
from main_db import Session, Users, Menu, Orders
import secrets
import uuid, os, datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = '#cv)3v7w$*s3fk;5c!@y0?:?№3"9)#'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    with Session() as session:
        return session.query(Users).filter_by(id=user_id).first()


@app.after_request
def apply_csp(response):
    nonce = secrets.token_urlsafe(16)
    csp = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self'; "
        f"frame-ancestors 'none'; "
        f"base-uri 'self'; "
        f"form-action 'self'"
    )
    response.headers["Content-Security-Policy"] = csp
    response.set_cookie('nonce', nonce)
    return response


@app.route('/')
@app.route('/home')
def home():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)

    return render_template('index.html')


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        if request.form.get("csrf_token") != session["csrf_token"]:
            return "Request Blocked!", 403

        nickname = request.form['nickname']
        password = request.form['password']

        with Session() as cursor:
            user = cursor.query(Users).filter_by(nickname=nickname).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('home'))

            flash('Wrong password or name!', 'danger')

    return render_template('login.html', csrf_token=session["csrf_token"])


@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if request.form.get("csrf_token") != session["csrf_token"]:
            return "Request Blocked!", 403

        nickname = request.form['nickname']
        email = request.form['email']
        password = request.form['password']

        with Session() as cursor:
            if cursor.query(Users).filter((Users.email==email) | (Users.nickname==nickname)).first():
                flash('Користувач з таким email або нікнеймом вже існує!', 'danger')
                return render_template('register.html', csrf_token=session["csrf_token"])

            new_user = Users(nickname=nickname, email=email)
            new_user.set_password(password)
            cursor.add(new_user)
            cursor.commit()
            cursor.refresh(new_user)
            login_user(new_user)
            return redirect(url_for('home'))

    return render_template('register.html', csrf_token=session["csrf_token"])


@app.route("/add_position", methods=['GET', 'POST'])
@login_required
def add_position():
    if current_user.nickname != 'Admin':
        return redirect(url_for('home'))

    if request.method == "POST":
        if request.form.get("csrf_token") != session["csrf_token"]:
            return "Запит заблоковано!", 403

        name = request.form['name']
        file = request.files.get('img')
        ingredients = request.form['ingredients']
        description = request.form['description']
        price = request.form['price']
        weight = request.form['weight']

        if not file or not file.filename:
            return 'Файл не вибрано або завантаження не вдалося'

        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        output_path = os.path.join('static/menu', unique_filename)

        with open(output_path, 'wb') as f:
            f.write(file.read())

        with Session() as cursor:
            new_position = Menu(name=name, ingredients=ingredients, description=description,
                                price=price, weight=weight, file_name=unique_filename)
            cursor.add(new_position)
            cursor.commit()

        flash('Позицію додано успішно!')

    return render_template('add_position.html', csrf_token=session["csrf_token"])

@app.route('/menu')
def menu():
    with Session() as session:
        all_positions = session.query(Menu).filter_by(active = True).all()
    return render_template('menu.html',all_positions = all_positions)

@app.route('/position/<name>', methods = ['GET','POST'])
def position(name):
    if request.method == 'POST':

        if request.form.get("csrf_token") != session["csrf_token"]:
            return "Запит заблоковано!", 403

        position_name = request.form.get('name')
        position_num = request.form.get('num')
        if 'basket' not in session:
            basket = {}
            basket[position_name] = position_num
            session['basket'] = basket
        else:
            basket = session.get('basket')
            basket[position_name] = position_num
            session['basket'] = basket
        flash('Позицію додано у кошик!')
    with Session() as cursor:
        us_position = cursor.query(Menu).filter_by(active = True, name = name).first()
    return render_template('position.html', csrf_token=session["csrf_token"] ,position = us_position)

@app.route('/create_order', methods=['GET','POST'])
def create_order():
    basket = session.get('basket')
    if len(basket) > 10:
        return render_template("over_ten_basket.html")
           
    if request.method == 'POST':

        if request.form.get("csrf_token") != session["csrf_token"]:
            return "Запит заблоковано!", 403

        if not current_user:
            flash("Для оформлення замовлення необхідно бути зареєстрованим")
        else:
            if not basket:
                flash("Ваш кошик порожній")
            else:
                with Session() as cursor:
                    new_order = Orders(order_list = basket,order_time = datetime.date(1,3,4), user_id=current_user.id)
                    cursor.add(new_order)
                    cursor.commit()
                    session.pop('basket')
                    cursor.refresh(new_order)
                    return redirect(f"/my_order/{new_order.id}")

    return render_template('create_order.html', csrf_token=session["csrf_token"], basket=basket)

@app.route('/change_order', methods=['GET','POST'])
def change_order():
    basket = session.get('basket')
    if request.method == 'POST':
        if request.form.get("csrf_token") != session["csrf_token"]:
            return "Запит заблоковано!", 403

        if not current_user:
            flash("To change your order you have to be logged in")
        else:
            if not basket:
                flash("Ваш кошик порожній")
            else:
                name = request.form.get("name")
                new_amount = request.form.get("num")

                if new_amount == 0:
                    app.logger.info(f"new_amount = 0, deleting {name}")
                    basket.pop(name)
                    session['basket'] = basket
                    return render_template('change_order.html', csrf_token=session["csrf_token"], basket=basket)
                    

                app.logger.info(f"changing {name}'s value to {new_amount}")
                basket[name] = new_amount
                session['basket'] = basket
                app.logger.info(f"change is succesful, returning changeorder.html")
                
                return render_template('change_order.html', csrf_token=session["csrf_token"], basket=basket)
    
    return render_template('change_order.html', csrf_token=session["csrf_token"], basket=basket)



        



@app.route('/delete_basket')
def delete_basket():
    basket = session.get("basket")
    app.logger.info(f"deleteing the basket: {basket}, length: {len(basket)}")
    session.pop("basket")
    app.logger.info(f"basket was deleted, returning to \"/create_order\"")
    return app.redirect("/create_order")

app.run(debug=True)


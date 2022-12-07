import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "GET":
        """Show portfolio of stocks"""
        # individual stock info that the user owns
        stocks = db.execute("SELECT * FROM home_track WHERE ID = ? ORDER BY TOTAL DESC", session["user_id"])

        # available cash on hand that the user has
        available = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        available = available[0]["cash"]

        overall = available

        for stock in stocks:
            price = lookup(stock["Symbol"])["price"]
            total = stock["Shares"] * price
            stock.update({"Price": price, "TOTAL": total})
            overall += total

        return render_template("index.html", stocks=stocks, available=available, overall=overall, usd=usd)
    else:
        if not request.form.get("add"):
            return apology("must add money", 400)
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = cash[0]["cash"]
        add = request.form.get("add")
        new_amt = float(cash) + float(add)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_amt, session["user_id"])

        return redirect("/")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock
    Collect symbol and amount of shares that user wants. Use lookup to get the price of symbol. Multiply amount of shares with the price of the stock. Check if total buy amount is within user's
    total cash amount. Add a new table to finance.db that keeps track of symbol name, symbol, amount of shares, and how much the shares are worth. This table will be used for
    the homepage. Use total price to subtract from user's available CASH amount, but the value of the shares will be updated continuously. """
    if request.method == "POST":
        # checks if the requires fields are empty or not
        if not request.form.get("symbol"):
            return apology("must provide a stock symbol", 400)
        else:
            symbol_buy = request.form.get("symbol")

        if not request.form.get("shares"):
            return apology("missing shares", 400)
        elif request.form.get("shares") == ValueError or request.form.get("shares") == TypeError:
            return apology("invalid input", 400)
        else:
            shares = request.form.get("shares")

        if float(shares) % 1 != 0:
            return apology("cannot byt fractional shares", 400)
        elif int(shares) <= 0:
            return apology("invalid amount of shares", 400)

        # checks if the given symbol is a valid symbol by calling lookup helper funct
        info = lookup(symbol_buy.upper())
        if not info:
            return apology("invalid symbol", 400)
        else:
            # once these are passed, create some variables to make things easier. These will be used to update user's available cash and also to insert the buy request info into home_track table
            symb = info["symbol"]
            name = info["name"]
            indiv_price = info["price"]
            total_price = info["price"] * float(shares)
            available_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
            available_cash = available_cash[0]["cash"]

        # checks if user has enough available cash to even buy the stocks.
        if total_price > float(available_cash):
            return apology("buy amount exceeds current available cash amount", 403)
        else:
            # when we buy stocks, we are either adding to our existing owned shares of that stock, or creating a new entry of owned stock shares
            check = db.execute("SELECT * FROM home_track WHERE ID = ? AND Symbol = ?", session["user_id"], symb)

            # if user doesn't already own shares of the given symbol, create a new entry into home_track
            if len(check) == 0:
                db.execute("INSERT INTO home_track VALUES (?, ?, ?, ?, ?, ?)", session["user_id"], symb, name, shares, indiv_price, total_price)

            # add bought shares to existing shares
            else:
                new_total = float(check[0]["TOTAL"]) + total_price
                new_shares = check[0]["Shares"] + int(shares)
                db.execute("UPDATE home_track SET Shares = ?, Price = ?, TOTAL = ? WHERE ID = ? AND Symbol = ?", new_shares, indiv_price, new_total, session["user_id"], symb)

            #update user's available cash in users table
            available_cash -= float(total_price)
            db.execute("UPDATE users SET cash = ? WHERE id = ?", available_cash, session["user_id"])

            # inserts transaction into history table
            db.execute("INSERT INTO history (ID, symbol, shares, price, action) VALUES (?, ?, ?, ?, ?)", session["user_id"], symb, shares, indiv_price, "BUY")

        flash(f"Successfully bought {shares} shares of {symb}")
        return redirect("/")

    # method == GET, just loads the buy page when clicking buy lol
    else:
        return render_template("/buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM history WHERE ID = ?", session["user_id"])
    return render_template("/history.html", history=history, usd=usd)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        symbol = request.form.get("symbol")
        quoteprice = lookup(symbol.upper())
        if not quoteprice:
            return apology("invalid symbol", 400)
        else:
            return render_template("quoteprice.html", quoteprice=quoteprice, usd=usd)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # checks if username, password, confirm password field are filled and if confirm password matches password
        if not request.form.get("username"):
            return apology("must provide username", 400)
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("confirmation password must match the password", 400)

        # once the above is passed, we have to put the username and password into the database. we are storing the password hash and not the actual password
        check = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(check) != 0:
            return apology("username has been taken", 400)
        elif len(check) == 0:
            passw = request.form.get("password")
            unique_hash = generate_password_hash(passw, method='pbkdf2:sha256', salt_length=8)
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"), unique_hash)

        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # symbol input is the only thing to check for
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)
        elif not request.form.get("shares"):
            return apology("must sell shares", 403)

        # request.form.get for the amount of shares and compare to the amount of owned shares
        symbol = request.form.get("symbol")
        info = lookup(symbol.upper())
        amt_owned = db.execute("SELECT Shares FROM home_track WHERE ID = ? AND Symbol = ?", session["user_id"], info["symbol"])
        amt_owned = amt_owned[0]["Shares"]
        sell_amt = request.form.get("shares")
        indiv_price = info["price"]
        total_price = indiv_price * float(sell_amt)
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = cash[0]["cash"]

        # checks if user is selling an amount of shares that they actually own
        if int(sell_amt) > int(amt_owned):
            return apology("sell amount exceeds owned amount", 400)
        elif int(sell_amt) == int(amt_owned):
            # delete row in table in home_track
            db.execute("DELETE FROM home_track WHERE ID = ? AND Symbol = ?", session["user_id"], info["symbol"])
        elif int(sell_amt) < int(amt_owned):
            # if sell amount is less or equal to shared amount:
            # update home_track to reflect the sell action
            # subtract amount of shares, update TOTAL
            new_amt = int(amt_owned) - int(sell_amt) # end amount of shares that user owns for that symbol
            total_before = db.execute("SELECT TOTAL FROM home_track WHERE ID = ? AND Symbol = ?", session["user_id"], info["symbol"])
            total_before = total_before[0]["TOTAL"]
            new_total = float(total_before) - total_price # end value worth for the amount of shares that the user owns for that symbol
            db.execute("UPDATE home_track SET TOTAL = ?, Shares = ?, Price = ? WHERE ID = ? AND Symbol = ?", new_total, new_amt, indiv_price, session["user_id"], info["symbol"])

        # add money to cash after selling
        new_cash = cash + total_price
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, session["user_id"])

        # insert sell info into history
        db.execute("INSERT INTO history (ID, symbol, shares, price, action) VALUES (?, ?, ?, ?, ?)", session["user_id"], info["symbol"], sell_amt, indiv_price, "SELL")

        flash(f"Successfully sold {sell_amt} shares of {symbol.upper()}")
        return redirect("/")
    else:
        # passes the owned stocks to the sell page
        symb = db.execute("SELECT Symbol FROM home_track WHERE ID = ?", session["user_id"])
        return render_template("sell.html", symb=symb)

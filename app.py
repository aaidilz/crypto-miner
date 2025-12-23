from flask import Flask, render_template, request, redirect, url_for, flash
from game_state import GameState
from miners import AVAILABLE_MINERS

# Minimal Flask application that exposes the CLI mechanics via web pages.
# Comments below explain the mapping between routes and the old CLI commands.

app = Flask(__name__)
app.secret_key = "dev-key-for-flask-session"

# Load or create game state once at startup. For simplicity we keep it in memory.
game = GameState.load()


@app.route("/")
def dashboard():
    """Dashboard page shows the main game stats.

    This maps to the old CLI 'status' or main screen.
    """
    return render_template(
        "dashboard.html",
        money=round(game.money, 2),
        crypto=round(game.crypto, 6),
        price=round(game.price, 2),
        difficulty=round(game.difficulty, 3),
        hashrate=round(game.recalc_hashrate(), 2),
        miners_owned=game.miners_owned,
    )


@app.route("/mine", methods=["POST"])
def mine():
    """Perform one mining tick. This maps to the CLI 'mine' command.

    After performing a tick we save and redirect back to dashboard.
    """
    game.mining_tick()
    game.save()
    flash("Mined for one tick.")
    return redirect(url_for("dashboard"))


@app.route("/shop")
def shop():
    """Show available miners and ownership.

    This replaces the CLI shop listing.
    """
    return render_template("shop.html", miners=AVAILABLE_MINERS, owned=game.miners_owned)


@app.route("/buy", methods=["POST"])
def buy():
    """Buy a miner from the shop.

    Expects form field `miner_key`. On success saves automatically.
    """
    key = request.form.get("miner_key")
    if not key:
        flash("No miner selected.")
        return redirect(url_for("shop"))
    success = game.buy_miner(key)
    if success:
        game.save()
        flash("Purchased miner.")
    else:
        flash("Not enough money or invalid miner.")
    return redirect(url_for("shop"))


@app.route("/upgrades")
def upgrades():
    """Show upgrade options. Simple single upgrade here."""
    return render_template("upgrades.html")


@app.route("/buy_upgrade", methods=["POST"])
def buy_upgrade():
    """Purchase a simple upgrade by id (form field `upgrade_id`)."""
    uid = request.form.get("upgrade_id")
    if not uid:
        flash("No upgrade selected.")
        return redirect(url_for("upgrades"))
    if game.buy_upgrade(uid):
        game.save()
        flash("Upgrade purchased.")
    else:
        flash("Can't buy upgrade. Check funds or id.")
    return redirect(url_for("upgrades"))


@app.route("/sell", methods=["POST"])
def sell():
    """Sell crypto for money. Expects `amount` form field."""
    try:
        amt = float(request.form.get("amount", "0"))
    except ValueError:
        amt = 0.0
    if game.sell_crypto(amt):
        game.save()
        flash(f"Sold {amt} crypto.")
    else:
        flash("Invalid sell amount.")
    return redirect(url_for("dashboard"))


@app.route("/save", methods=["POST"])
def save():
    """Endpoint to force a save from the UI."""
    game.save()
    flash("Game saved.")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    # Run app locally: `python app.py` and open http://127.0.0.1:5000
    app.run(debug=True)

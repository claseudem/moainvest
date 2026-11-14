"""Reglas anti-ruido de las alertas (lógica pura)."""
from app.alertas import rules
from app.alertas.rules import Settings
from app.core.market_data import Quote
from app.core.watchlists import Symbol, Watchlist

TECH = Watchlist(slug="tech", name="Tech", icon="", symbols=(Symbol("DELL", "Dell"), Symbol("SONY", "Sony")))
GAMES = Watchlist(slug="games", name="Games", icon="", symbols=(Symbol("SONY", "Sony"), Symbol("RBLX", "Roblox")))
LISTS = (TECH, GAMES)


def q(ticker, pct, prev=100.0):
    price = None if pct is None else prev * (1 + pct / 100)
    return Quote(symbol=ticker, name=ticker, price=price, previous_close=prev, change=None, change_percent=pct, currency="USD")


def tickers(triggers):
    return [t.ticker for t in triggers]


def test_only_moves_beyond_the_threshold_trigger():
    quotes = {"DELL": q("DELL", -9.2), "SONY": q("SONY", 4.9), "RBLX": q("RBLX", 5.0)}
    triggers = rules.evaluate(LISTS, Settings(threshold=5), quotes, set())
    assert tickers(triggers) == ["DELL", "RBLX"]  # del más brusco al más suave
    dell = triggers[0]
    assert dell.direction == "down" and dell.level == 1 and dell.name == "DELL"


def test_threshold_is_user_configurable():
    quotes = {"SONY": q("SONY", 3.4)}
    assert tickers(rules.evaluate(LISTS, Settings(threshold=3), quotes, set())) == ["SONY"]
    assert rules.evaluate(LISTS, Settings(threshold=5), quotes, set()) == []


def test_same_move_is_not_notified_twice_in_a_session():
    quotes = {"DELL": q("DELL", -6)}
    first = rules.evaluate(LISTS, Settings(), quotes, set())
    again = rules.evaluate(LISTS, Settings(), quotes, {t.key for t in first})
    assert again == []


def test_escalation_to_double_threshold_notifies_once_more():
    sent = {t.key for t in rules.evaluate(LISTS, Settings(), {"DELL": q("DELL", -6)}, set())}
    worse = rules.evaluate(LISTS, Settings(), {"DELL": q("DELL", -11)}, sent)
    assert [(t.ticker, t.level) for t in worse] == [("DELL", 2)]


def test_jumping_straight_to_level_three_sends_a_single_alert_capped_at_three():
    triggers = rules.evaluate(LISTS, Settings(threshold=3), {"DELL": q("DELL", -40)}, set())
    assert [(t.ticker, t.level) for t in triggers] == [("DELL", 3)]


def test_reversal_in_the_other_direction_is_a_new_alert():
    sent = {t.key for t in rules.evaluate(LISTS, Settings(), {"DELL": q("DELL", -6)}, set())}
    assert tickers(rules.evaluate(LISTS, Settings(), {"DELL": q("DELL", 6)}, sent)) == ["DELL"]


def test_new_session_resets_the_dedup():
    sent = {t.key for t in rules.evaluate(LISTS, Settings(), {"DELL": q("DELL", -6, prev=100)}, set())}
    assert tickers(rules.evaluate(LISTS, Settings(), {"DELL": q("DELL", -6, prev=94)}, sent)) == ["DELL"]


def test_muted_watchlists_are_skipped_but_shared_tickers_still_alert():
    quotes = {"DELL": q("DELL", -9), "SONY": q("SONY", -7), "RBLX": q("RBLX", 8)}
    triggers = rules.evaluate(LISTS, Settings(muted_watchlists=frozenset({"tech"})), quotes, set())
    # DELL solo está en "tech" (silenciada); SONY sigue vigilada por "games".
    assert sorted(tickers(triggers)) == ["RBLX", "SONY"]
    sony = next(t for t in triggers if t.ticker == "SONY")
    assert sony.watchlists == ("games",)


def test_quotes_without_data_are_ignored():
    quotes = {"DELL": q("DELL", None), "SONY": Quote("SONY", "SONY", 1.0, None, None, 9.0)}
    assert rules.evaluate(LISTS, Settings(), quotes, set()) == []


def test_names_come_from_the_watchlists_when_given():
    triggers = rules.evaluate(LISTS, Settings(), {"DELL": q("DELL", -9)}, set(), names={"DELL": "Dell"})
    assert triggers[0].name == "Dell"

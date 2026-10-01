#!/usr/bin/env python3
"""Pure mechanical-portfolio planning helpers. No network or persistent writes."""
import argparse
import calendar
import json
import math
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
DEFAULT_EXCLUSIONS = ()
FIELDS = ("MktCap_USD", "ADTV_90D_USD", "PSR", "RevenueGrowth_YoY_Q_%")
WEIGHTS = (35, 35, 15, 15)
BASIS = "regular_close_as_traded"
PROVIDERS = ("Yahoo", "Alpaca Paper Trading", "TradingView", "미확인")


class InputError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise InputError(code)


def number(value):
    require(not isinstance(value, bool), "number_required")
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise InputError("number_required") from None
    require(math.isfinite(value), "finite_number_required")
    return value


def positive(value):
    value = number(value)
    require(value > 0, "positive_number_required")
    return value


def iso_date(value):
    require(isinstance(value, str), "date_required")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise InputError("invalid_date") from None
    require(value == parsed.isoformat(), "canonical_date_required")
    return parsed


def timestamp(value):
    require(isinstance(value, str), "timestamp_required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InputError("invalid_timestamp") from None
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            "timezone_required")
    return parsed


def ticker(value):
    require(isinstance(value, str) and bool(value.strip()), "ticker_required")
    value = value.strip().upper()
    require(not any(c.isspace() for c in value) and "|" not in value,
            "invalid_ticker")
    return value


def exclusions(payload):
    values = payload.get("exclusions", DEFAULT_EXCLUSIONS)
    require(isinstance(values, (list, tuple, dict)), "invalid_exclusions")
    return {ticker(v) for v in values}


def resolve_exclusions(payload):
    require(payload.get("lookup_complete") is True, "incomplete_exclusion_lookup")
    observed = timestamp(payload.get("as_of"))
    raw_rows = payload.get("rows")
    require(isinstance(raw_rows, list), "exclusion_rows_required")
    issues, warnings, periods, selected = [], [], [], set()
    mappings = defaultdict(set)
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, dict):
            issues.append({"row": index, "reason": "invalid_exclusion_row"})
            continue
        state = raw.get("state")
        if state == "대기":
            continue
        try:
            require(state in ("제외", "해제"), "invalid_exclusion_state")
            symbol = ticker(raw.get("ticker"))
            security = ticker(raw.get("security_id"))
            require(":" in security and security.split(":", 1)[1] == symbol,
                    "exclusion_security_mapping_required")
            started = timestamp(raw.get("starts_at") or raw.get("created_at"))
            ended = timestamp(raw["ends_at"]) if raw.get("ends_at") is not None else None
            require(state != "해제" or ended is not None, "release_date_required")
            require(ended is None or ended >= started, "invalid_exclusion_period")
        except InputError as error:
            issues.append({"row": index, "page_id": raw.get("page_id"), "reason": str(error)})
            continue
        mappings[symbol].add(security)
        active = started <= observed and (ended is None or observed < ended)
        if active:
            selected.add(symbol)
        periods.append({"ticker": symbol, "security_id": security,
                        "page_id": raw.get("page_id"), "state": state,
                        "starts_at": started.isoformat(),
                        "ends_at": ended.isoformat() if ended else None,
                        "key": f"{security}|{started.astimezone(timezone.utc).isoformat()}",
                        "effective": active, "reason": raw.get("reason")})
    for symbol, identities in mappings.items():
        if len(identities) > 1:
            issues.append({"ticker": symbol, "reason": "conflicting_exclusion_identity"})
    active_counts = Counter(p["security_id"] for p in periods if p["effective"])
    for security, count in active_counts.items():
        if count > 1:
            warnings.append({"security_id": security, "reason": "overlapping_active_exclusions",
                             "count": count})
    complete = not issues
    return {"status": "resolved" if complete else "data_pending",
            "effective_complete": complete,
            "exclusions": sorted(selected) if complete else None,
            "resolved_exclusions": sorted(selected), "periods": periods,
            "issues": issues, "warnings": warnings, "writes_executed": False}


def rank(payload):
    require(payload.get("source_complete") is True, "incomplete_universe")
    require(payload.get("universe_verified") is True, "unverified_universe")
    raw = payload.get("rows")
    require(isinstance(raw, list) and bool(raw), "rows_required")
    seen, rows, gaps = set(), [], []
    for raw_row in raw:
        symbol = ticker(raw_row.get("Ticker"))
        require(symbol not in seen, "duplicate_ticker")
        seen.add(symbol)
        row = dict(raw_row, Ticker=symbol, ComponentRanks={})
        bad = []
        for field in FIELDS:
            try:
                row[field] = positive(row.get(field))
            except InputError:
                bad.append(field)
        if bad:
            gaps.append({"Ticker": symbol, "fields": bad})
        else:
            rows.append(row)
    require(bool(rows), "no_valid_rows")
    for idx, field in enumerate(FIELDS):
        values = sorted((r[field] for r in rows), reverse=field != "PSR")
        ranks = {}
        for pos, value in enumerate(values, 1):
            ranks.setdefault(value, pos)
        for row in rows:
            row["ComponentRanks"] = row.get("ComponentRanks", {})
            row["ComponentRanks"][field] = ranks[row[field]]
    for row in rows:
        row["ScoreNumerator"] = sum(w * row["ComponentRanks"][f]
                                    for w, f in zip(WEIGHTS, FIELDS))
        row["CombinedRank"] = row["ScoreNumerator"] / 100
    rows.sort(key=lambda r: (r["ScoreNumerator"], -r["MktCap_USD"], r["Ticker"]))
    excluded, eligible_rank = exclusions(payload), 0
    for pos, row in enumerate(rows, 1):
        row["FinalRank"] = pos
        row["ManualExcluded"] = row["Ticker"] in excluded
        row["EligibleRank"] = None
        if not row["ManualExcluded"]:
            eligible_rank += 1
            row["EligibleRank"] = eligible_rank
    return {"ranked": rows, "input_count": len(raw), "valid_count": len(rows),
            "data_gaps": gaps, "ranking_complete": not gaps}


def decision_plan(payload):
    target, buffer = payload.get("target_size", 15), payload.get("buffer_rank", 20)
    require(type(target) is int and type(buffer) is int and 0 < target <= buffer,
            "invalid_portfolio_size")
    holdings = [ticker(v) for v in payload.get("holdings", [])]
    require(len(set(holdings)) == len(holdings), "duplicate_holding")
    require(len(holdings) <= target, "overfull_holdings_require_explicit_policy")
    if payload.get("ranking_complete") is not True:
        return {"status": "data_pending", "composition_trades": [],
                "pending": holdings, "weight_mode": "deferred"}
    rows = payload.get("ranked", [])
    lookup, ranks = {}, set()
    for row in rows:
        symbol = ticker(row.get("Ticker"))
        pos = row.get("FinalRank")
        require(type(pos) is int and pos > 0, "invalid_rank")
        require(symbol not in lookup and pos not in ranks, "duplicate_rank_or_ticker")
        lookup[symbol], _ = row, ranks.add(pos)
    excluded = exclusions(payload)
    exits = {ticker(v) for v in payload.get("verified_universe_exits", [])}
    keep, pending, trades = [], [], []
    for symbol in holdings:
        row = lookup.get(symbol)
        reason = None
        if symbol in excluded:
            reason = "manual_exclusion"
        elif symbol in exits:
            reason = "verified_universe_exit"
        elif row is None:
            pending.append(symbol)
            keep.append(symbol)
        elif row["FinalRank"] > buffer:
            reason = "rank_buffer_exit"
        else:
            keep.append(symbol)
        if reason:
            trades.append({"side": "SELL", "Ticker": symbol, "reason": reason})
    next_holdings = list(keep)
    if not pending:
        for row in sorted(rows, key=lambda r: r["FinalRank"]):
            if len(next_holdings) >= target:
                break
            symbol = ticker(row["Ticker"])
            if symbol in holdings or symbol in excluded or row.get("ManualExcluded"):
                continue
            next_holdings.append(symbol)
            trades.append({"side": "BUY", "Ticker": symbol, "reason": "fill_vacancy"})
    monthly = payload.get("monthly_due") is True
    complete = not pending and len(next_holdings) == target
    mode = ("equal_weight_initial" if not holdings and not pending
            else "deferred" if not complete else "equal_weight_monthly" if monthly
            else "replace_with_sale_proceeds" if trades else "no_trade")
    weights = {v: 1 / target for v in next_holdings} if mode.startswith("equal_weight") else None
    return {"status": "data_pending" if pending else "candidate_shortage" if not complete else "planned",
            "composition_trades": trades, "pending": pending, "next_holdings": next_holdings,
            "unfilled_slots": target - len(next_holdings), "weight_mode": mode,
            "target_weights": weights,
            "target_cash_weight": 1 - sum(weights.values()) if weights is not None else None,
            "fills_confirmed": False}


def next_session(payload):
    require(payload.get("calendar_complete") is True, "incomplete_calendar")
    start, end = iso_date(payload.get("calendar_start")), iso_date(payload.get("calendar_end"))
    require(start <= end, "invalid_calendar_range")
    sessions, dates = [], set()
    for raw in payload.get("sessions", []):
        day = iso_date(raw.get("session_date"))
        opened, closed = timestamp(raw.get("open_at")), timestamp(raw.get("close_at"))
        require(day not in dates and start <= day <= end, "invalid_session_date")
        require(opened < closed and opened.astimezone(NY).date() == day
                and closed.astimezone(NY).date() == day, "invalid_session_times")
        dates.add(day)
        sessions.append((day, opened, closed))
    sessions.sort()
    kind = payload.get("kind", "replacement")
    if kind == "monthly":
        month = payload.get("month")
        require(isinstance(month, str) and len(month) == 7, "month_required")
        first = iso_date(month + "-01")
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        require(start <= first and end >= last, "month_calendar_coverage_required")
        choices = [s for s in sessions if first <= s[0] <= last]
    else:
        require(kind in ("replacement", "initial"), "invalid_event_kind")
        observed = timestamp(payload.get("observed_at"))
        require(start <= observed.astimezone(NY).date() <= end,
                "observation_outside_calendar")
        choices = [s for s in sessions if s[1] > observed]
    if not choices:
        return {"status": "calendar_gap", "session_date": None, "fills_confirmed": False}
    day, opened, closed = choices[0]
    return {"status": "pending_first_valid_regular_minute_bar", "session_date": day.isoformat(),
            "earliest_open_kst": opened.astimezone(KST).isoformat(),
            "session_close_kst": closed.astimezone(KST).isoformat(), "fills_confirmed": False}


def validate_close(payload):
    reasons = []
    requested = iso_date(payload.get("requested_session_date"))
    requested_symbol = ticker(payload.get("requested_security_id"))
    row = payload.get("candidate", {})
    if ticker(row.get("security_id")) != requested_symbol:
        reasons.append("wrong_security")
    day = iso_date(row.get("session_date"))
    close_at, observed = timestamp(row.get("session_close_at")), timestamp(row.get("observed_at"))
    require(close_at.astimezone(NY).date() == requested, "close_calendar_date_mismatch")
    if day != requested:
        reasons.append("wrong_session_date")
    try:
        positive(row.get("value"))
    except InputError:
        reasons.append("invalid_price")
    if row.get("session") != "regular" or row.get("interval") != "1d":
        reasons.append("not_regular_daily_bar")
    if row.get("field") not in ("Close", "dailyBar.c", "prevDailyBar.c", "OHLCV.c", "c"):
        reasons.append("not_close_field")
    if row.get("currency") != "USD":
        reasons.append("wrong_currency")
    if row.get("price_basis") != BASIS:
        reasons.append("incompatible_price_basis")
    if row.get("provider") not in PROVIDERS[:-1]:
        reasons.append("unknown_provider")
    if row.get("finalized") is not True:
        reasons.append("unconfirmed_final_bar")
    delay = row.get("delay_seconds")
    if delay is None:
        reasons.append("unknown_delay")
    else:
        delay = number(delay)
        require(delay >= 0, "invalid_delay")
        if observed < close_at + timedelta(seconds=delay):
            reasons.append("session_or_delay_not_complete")
    limited = row.get("provider") == "Alpaca Paper Trading" and row.get("feed") == "iex"
    if row.get("feed_scope") in ("single_venue", "unknown"):
        limited = True
    status = "미확인" if reasons else "추정" if limited else "확정"
    return {"status": status, "eligible_confirmed_close": status == "확정",
            "reasons": reasons + (["limited_venue_coverage"] if limited else [])}


def close_record(raw):
    row = dict(raw)
    symbol = ticker(row.get("security_id"))
    require(":" in symbol, "security_id_required")
    day = iso_date(row.get("session_date")).isoformat()
    require(row.get("currency") == "USD" and row.get("price_basis") == BASIS,
            "invalid_close_contract")
    require(row.get("status") in ("확정", "추정", "미확인"), "invalid_close_status")
    require(row.get("provider") in PROVIDERS, "invalid_close_provider")
    if row["status"] == "미확인":
        require(row.get("value") is None, "unconfirmed_close_must_be_null")
    else:
        row["value"] = positive(row.get("value"))
    key = f"{symbol}|{day}|{BASIS}|USD"
    require("key" not in row or row["key"] == key, "close_key_mismatch")
    row.update(security_id=symbol, session_date=day, key=key)
    return row


def close_plan(payload):
    require(payload.get("lookup_complete") is True, "incomplete_key_lookup")
    desired = [close_record(v) for v in payload.get("records", [])]
    require(len({v["key"] for v in desired}) == len(desired), "duplicate_input_close")
    existing = defaultdict(list)
    for raw in payload.get("existing", []):
        row = close_record(raw)
        require(isinstance(row.get("page_id"), str) and bool(row["page_id"]),
                "existing_page_id_required")
        existing[row["key"]].append(row)
    approved = set(payload.get("verified_correction_keys", []))
    levels = {"미확인": 0, "추정": 1, "확정": 2}
    actions = []
    for row in desired:
        matches = existing[row["key"]]
        action = {"key": row["key"], "record": row}
        if len(matches) > 1:
            action.update(action="conflict", reason="duplicate_remote_key")
        elif not matches:
            action.update(action="create")
        else:
            old = matches[0]
            action["page_id"] = old["page_id"]
            old_level, new_level = levels[old["status"]], levels[row["status"]]
            equal = (old.get("value") is None and row.get("value") is None or
                     old.get("value") is not None and row.get("value") is not None and
                     math.isclose(old["value"], row["value"], rel_tol=1e-7, abs_tol=0.00005))
            if new_level < old_level:
                action.update(action="skip", reason="preserve_higher_quality")
            elif new_level > old_level:
                action.update(action="update", reason="quality_upgrade")
            elif equal:
                better = PROVIDERS.index(row["provider"]) < PROVIDERS.index(old["provider"])
                action.update(action="update" if better else "skip",
                              reason="primary_source_upgrade" if better else "same_close")
            elif row["key"] in approved and row.get("correction_note"):
                action.update(action="update", reason="verified_correction",
                              previous_record=old)
            else:
                action.update(action="conflict", reason="price_conflict")
        actions.append(action)
    return {"actions": actions, "counts": dict(Counter(v["action"] for v in actions)),
            "writes_executed": False}


def continuous_ledger(payload):
    """Replay source composition cues without a cash-equivalent pause."""
    require(payload.get("transition_actions_verified") is True,
            "transition_corporate_actions_unverified")
    require(payload.get("pause_split_events") == [], "split_replay_requires_explicit_policy")
    model_id = payload.get("model_id")
    require(isinstance(model_id, str) and bool(model_id), "model_id_required")
    paused = iso_date(payload.get("pause_date")).isoformat()
    changed = iso_date(payload.get("transition_date")).isoformat()
    require(paused < changed, "invalid_hold_period")
    target = payload.get("target_size", 15)
    require(type(target) is int and target > 0, "invalid_portfolio_size")
    raw = payload.get("source_events")
    require(isinstance(raw, list) and bool(raw), "source_events_required")
    source = [dict(r) for r in raw if r.get("event_type") in ("cash", "trade")]
    require(bool(source), "no_source_transactions")
    dates = [iso_date(r.get("date")).isoformat() for r in source]
    require(dates == sorted(dates), "source_dates_not_ordered")
    ids = [r.get("event_id") for r in source]
    require(all(isinstance(v, str) and bool(v) for v in ids) and len(set(ids)) == len(ids),
            "invalid_source_event_ids")
    require(all(r.get("currency") == "USD" for r in source), "source_currency_mismatch")
    require(all(r.get("side") in ("BUY", "SELL") for r in source if r["event_type"] == "trade"),
            "invalid_trade_side")
    events, holdings, cash, before_source = [], defaultdict(float), 0.0, defaultdict(float)
    rebalance_dates = {iso_date(v).isoformat() for v in payload.get("rebalance_dates", [])}
    groups = defaultdict(list)
    for r in source:
        if r["date"] >= paused:
            groups[r["date"]].append(r)

    def apply(row):
        nonlocal cash
        if row["event_type"] == "cash":
            cash += number(row["amount"])
        else:
            symbol, quantity, price = ticker(row["symbol"]), positive(row["quantity"]), positive(row["price"])
            require(row["side"] in ("BUY", "SELL"), "invalid_trade_side")
            sign = 1 if row["side"] == "BUY" else -1
            holdings[symbol] += sign * quantity
            require(holdings[symbol] >= -1e-9, "model_oversell")
            if abs(holdings[symbol]) < 1e-10:
                holdings.pop(symbol, None)
            cash -= sign * quantity * price + number(row.get("fee", 0))
        require(cash >= -1e-8, "model_negative_cash")
        if abs(cash) < 1e-9:
            cash = 0.0

    def emit(day, symbol, side, quantity, price, refs, mode):
        if quantity <= 1e-10:
            return
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'{model_id}|{day}|{symbol}|{side}'))
        row = {"schema_version": 1, "event_id": event_id, "date": day,
               "event_type": "trade", "symbol": symbol, "side": side,
               "quantity": quantity, "price": price, "fee": 0.0, "currency": "USD",
               "model_id": model_id, "source_event_ids": refs, "model_mode": mode,
               "price_basis": "regular_session_open",
               "effective_at": payload.get("event_times", {}).get(day),
               "memo": f'{mode}; continuous holdings, source composition retained'}
        apply(row)
        events.append(row)

    # Source files can list same-day equal-weight purchases before the
    # corresponding sales. Replay funding first without inventing fill times.
    prefix = [row for row in source if row["date"] < paused]
    prefix.sort(key=lambda row: (row["date"],
                0 if row["event_type"] == "cash" and number(row["amount"]) > 0 else
                1 if row["event_type"] == "trade" and row["side"] == "SELL" else 2))
    for row in prefix:
        if row["event_type"] == "trade":
            sign = 1 if row["side"] == "BUY" else -1
            before_source[ticker(row["symbol"])] += sign * positive(row["quantity"])
        imported = dict(row, model_id=model_id, source_event_ids=[row["event_id"]],
                        model_mode="source_import", price_basis="source_recorded_price")
        apply(imported)
        events.append(imported)
    require(len(holdings) == target, "pre_pause_holdings_count_mismatch")
    pause_holdings = dict(holdings)
    require("BOXX" not in holdings, "pre_pause_cash_equivalent_conflict")
    skipped, group_audit, transition_nav = [], [], None
    for day, rows in sorted(groups.items()):
        previous_source = {s: q for s, q in before_source.items() if q > 1e-10}
        for r in rows:
            require(number(r.get("fee", 0)) == 0, "nonzero_source_fee_requires_cost_policy")
            require(r["event_type"] == "trade", "post_pause_cash_flow_requires_policy")
            symbol = ticker(r["symbol"])
            sign = 1 if r["side"] == "BUY" else -1
            before_source[symbol] += sign * positive(r["quantity"])
            require(before_source[symbol] >= -1e-9, "source_oversell")
        source_after = {s: q for s, q in before_source.items() if q > 1e-10}
        if day < changed:
            require(day == paused and set(source_after) == {"BOXX"},
                    "intervening_trade_requires_explicit_hold_policy")
            skipped.extend(r["event_id"] for r in rows)
            continue
        require(len(source_after) == target and "BOXX" not in source_after,
                "post_transition_composition_mismatch")
        refs = [r["event_id"] for r in rows]
        prices = {}
        if day == changed:
            prices = {ticker(s): positive(v) for s, v in payload.get("transition_prices", {}).items()}
            require(set(holdings) | set(source_after) <= set(prices), "transition_price_missing")
            skipped.extend(r["event_id"] for r in rows if ticker(r["symbol"]) == "BOXX")
        else:
            for r in rows:
                symbol, price = ticker(r["symbol"]), positive(r["price"])
                require(symbol not in prices or math.isclose(prices[symbol], price, rel_tol=1e-8),
                        "multiple_intraday_prices_require_ordered_groups")
                prices[symbol] = price
        start_count = len(events)
        if day == changed or day in rebalance_dates:
            require(set(holdings) | set(source_after) <= set(prices), "rebalance_price_missing")
            nav = cash + sum(q * prices[s] for s, q in holdings.items())
            require(nav > 0, "invalid_model_nav")
            if day == changed:
                transition_nav = nav
            desired = {s: nav / target / prices[s] for s in source_after}
            deltas = {s: desired.get(s, 0) - holdings.get(s, 0)
                      for s in set(holdings) | set(desired)}
            mode = "hold_transition_equal_weight" if day == changed else "source_dated_equal_weight"
            for s in sorted(deltas):
                if deltas[s] < 0:
                    emit(day, s, "SELL", -deltas[s], prices[s], refs, mode)
            for s in sorted(deltas):
                if deltas[s] > 0:
                    emit(day, s, "BUY", deltas[s], prices[s], refs, mode)
        else:
            removed = set(previous_source) - set(source_after)
            added = set(source_after) - set(previous_source)
            require(bool(removed) and bool(added), "unclassified_source_trade_group")
            require({ticker(r["symbol"]) for r in rows} == removed | added,
                    "swap_contains_retained_weight_changes")
            for s in sorted(removed):
                require(s in holdings and s in prices, "swap_source_missing")
                emit(day, s, "SELL", holdings[s], prices[s], refs, "source_dated_swap")
            budget = cash
            weights = {s: sum(positive(r["quantity"]) * positive(r["price"])
                              for r in rows if r["side"] == "BUY" and ticker(r["symbol"]) == s)
                       for s in added}
            weight_sum = sum(weights.values())
            require(weight_sum > 0, "swap_buy_missing")
            for s in sorted(added):
                emit(day, s, "BUY", budget * weights[s] / weight_sum / prices[s], prices[s],
                     refs, "source_dated_swap")
        require(set(holdings) == set(source_after), "model_composition_diverged")
        group_audit.append({"date": day, "mode": mode if day == changed or day in rebalance_dates else "source_dated_swap",
                            "source_event_count": len(rows), "model_event_count": len(events) - start_count,
                            "holdings_count": len(holdings), "cash": cash})
    require(transition_nav is not None, "transition_group_missing")
    require(len({r["event_id"] for r in events}) == len(events), "duplicate_model_event")
    return {"model_id": model_id, "events": events, "event_count": len(events),
            "hold_period": {"start": paused, "end": changed, "holdings": pause_holdings},
            "transition_nav": transition_nav, "holdings": dict(holdings), "cash": cash,
            "suppressed_source_event_ids": skipped, "groups": group_audit,
            "writes_executed": False}


COMMANDS = {"resolve-exclusions": resolve_exclusions,
            "rank": rank, "decision-plan": decision_plan, "next-session": next_session,
            "validate-close": validate_close, "close-plan": close_plan,
            "continuous-ledger": continuous_ledger}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        require(isinstance(payload, dict), "object_required")
        output = {"ok": True, **COMMANDS[args.command](payload)}
        print(json.dumps(output, ensure_ascii=False, allow_nan=False))
        return 0
    except (InputError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
        error = sys.exc_info()[1]
        code = str(error) if isinstance(error, InputError) else "invalid_input_shape"
        print(json.dumps({"ok": False, "error": code}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

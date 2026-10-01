import json
import subprocess
import sys
import unittest
from pathlib import Path

from mechanical import (BASIS, InputError, close_plan, decision_plan,
                        continuous_ledger, next_session, rank, resolve_exclusions, validate_close)


class MechanicalTests(unittest.TestCase):
    def continuous_input(self, with_later=False):
        events = []
        def trade(day, symbol, side, quantity, price):
            events.append({"event_id": str(len(events)), "date": day, "event_type": "trade",
                           "symbol": symbol, "side": side, "quantity": quantity, "price": price,
                           "fee": 0, "currency": "USD"})
        events.append({"event_id": "cash", "date": "2026-01-02", "event_type": "cash",
                       "amount": 100, "currency": "USD"})
        trade("2026-01-02", "A", "BUY", 5, 10)
        trade("2026-01-02", "B", "BUY", 5, 10)
        trade("2026-04-01", "A", "SELL", 5, 10)
        trade("2026-04-01", "B", "SELL", 5, 10)
        trade("2026-04-01", "BOXX", "BUY", 1, 100)
        trade("2026-05-20", "BOXX", "SELL", 1, 100)
        trade("2026-05-20", "B", "BUY", 5, 10)
        trade("2026-05-20", "C", "BUY", 5, 10)
        if with_later:
            trade("2026-06-01", "B", "SELL", 1.25, 20)
            trade("2026-06-01", "C", "BUY", 2.5, 10)
            trade("2026-08-05", "B", "SELL", 3.75, 20)
            trade("2026-08-05", "D", "BUY", 7.5, 10)
        return {"model_id": "test-continuous", "source_events": events,
                "pause_date": "2026-04-01", "transition_date": "2026-05-20", "target_size": 2,
                "transition_prices": {"A": 20, "B": 10, "C": 10},
                "transition_actions_verified": True, "pause_split_events": [],
                "rebalance_dates": ["2026-06-01"]}

    def test_continuous_preserves_spring_hold_and_does_not_reset_capital(self):
        result = continuous_ledger(self.continuous_input())
        self.assertEqual(result["hold_period"]["holdings"], {"A": 5, "B": 5})
        self.assertEqual(result["transition_nav"], 150)
        self.assertEqual(result["holdings"], {"B": 7.5, "C": 7.5})
        self.assertFalse(any(e.get("symbol") == "BOXX" for e in result["events"]))
        self.assertFalse(any(e["date"] == "2026-04-01" for e in result["events"]))
        self.assertEqual([e["amount"] for e in result["events"] if e["event_type"] == "cash"], [100])
        self.assertEqual(result["cash"], 0)

    def test_continuous_monthly_reweight_and_swap_use_model_capital(self):
        result = continuous_ledger(self.continuous_input(with_later=True))
        self.assertEqual(result["holdings"], {"C": 11.25, "D": 11.25})
        swap = [e for e in result["events"] if e["date"] == "2026-08-05"]
        self.assertEqual(len(swap), 2)
        self.assertEqual(swap[0]["quantity"] * swap[0]["price"], 112.5)
        self.assertEqual(swap[1]["quantity"] * swap[1]["price"], 112.5)
        self.assertFalse(any(e["symbol"] == "C" for e in swap))

    def test_continuous_deterministic_ids_and_no_mutations(self):
        payload = self.continuous_input()
        before = json.dumps(payload, sort_keys=True)
        first, second = continuous_ledger(payload), continuous_ledger(payload)
        self.assertEqual(first["events"], second["events"])
        self.assertEqual(json.dumps(payload, sort_keys=True), before)
        self.assertFalse(first["writes_executed"])

    def test_continuous_same_day_source_purchases_are_funded_by_sales(self):
        payload = self.continuous_input()
        payload["source_events"][3:3] = [
            {"event_id": "weight-buy", "date": "2026-02-02", "event_type": "trade",
             "symbol": "A", "side": "BUY", "quantity": 1, "price": 10, "currency": "USD"},
            {"event_id": "weight-sell", "date": "2026-02-02", "event_type": "trade",
             "symbol": "B", "side": "SELL", "quantity": 1, "price": 10, "currency": "USD"}]
        for event in payload["source_events"]:
            if event["date"] == "2026-04-01" and event.get("side") == "SELL":
                event["quantity"] = 6 if event["symbol"] == "A" else 4
        result = continuous_ledger(payload)
        day = [r for r in result["events"] if r["date"] == "2026-02-02"]
        self.assertEqual([r["side"] for r in day], ["SELL", "BUY"])
        self.assertEqual(result["hold_period"]["holdings"], {"A": 6, "B": 4})
        self.assertEqual(result["transition_nav"], 160)

    def test_continuous_missing_prices_and_unverified_splits_stop(self):
        for patch in [{"transition_prices": {"B": 10, "C": 10}},
                      {"transition_actions_verified": False}, {"pause_split_events": [{"symbol": "A", "ratio": 2}]}]:
            with self.assertRaises(InputError):
                continuous_ledger({**self.continuous_input(), **patch})

    def test_continuous_intervening_trades_and_duplicate_source_ids_stop(self):
        payload = self.continuous_input()
        payload["source_events"].insert(6, {"event_id": "unexpected", "date": "2026-04-15",
                    "event_type": "trade", "symbol": "BOXX", "side": "BUY", "quantity": .1,
                    "price": 100, "currency": "USD"})
        with self.assertRaises(InputError):
            continuous_ledger(payload)
        payload = self.continuous_input()
        payload["source_events"][1]["event_id"] = "cash"
        with self.assertRaises(InputError):
            continuous_ledger(payload)

    def exclusion(self, **patch):
        return {"ticker": "AAA", "security_id": "NASDAQ:AAA", "state": "제외",
                "starts_at": "2026-09-30T00:00:00+09:00", "ends_at": None,
                "created_at": "2026-09-29T12:00:00Z", **patch}

    def resolve(self, rows, as_of="2026-10-01T00:00:00+09:00"):
        return resolve_exclusions({"lookup_complete": True, "as_of": as_of, "rows": rows})

    def test_notions_empty_list_disables_legacy_constants(self):
        resolved = self.resolve([])
        self.assertEqual(resolved["exclusions"], [])
        ranked = rank({"source_complete": True, "universe_verified": True,
                       "exclusions": resolved["exclusions"], "rows": [self.row("AAA")]})
        self.assertFalse(ranked["ranked"][0]["ManualExcluded"])

    def test_manual_start_inclusive_end_exclusive(self):
        row = self.exclusion(state="해제", ends_at="2026-10-01T00:00:00+09:00")
        self.assertEqual(self.resolve([row], "2026-09-29T23:59:59+09:00")["exclusions"], [])
        self.assertEqual(self.resolve([row], "2026-09-30T00:00:00+09:00")["exclusions"], ["AAA"])
        self.assertEqual(self.resolve([row], "2026-10-01T00:00:00+09:00")["exclusions"], [])

    def test_empty_manual_start_uses_immutable_creation_time(self):
        row = self.exclusion(starts_at=None)
        self.assertEqual(self.resolve([row], "2026-09-29T11:59:59Z")["exclusions"], [])
        resolved = self.resolve([row], "2026-09-29T12:00:00Z")
        self.assertEqual(resolved["exclusions"], ["AAA"])
        self.assertEqual(resolved["periods"][0]["key"], "NASDAQ:AAA|2026-09-29T12:00:00+00:00")

    def test_manual_release_history_and_reentry_are_preserved(self):
        old = self.exclusion(state="해제", ends_at="2026-10-01T00:00:00+09:00")
        new = self.exclusion(starts_at="2026-10-05T00:00:00+09:00")
        self.assertEqual(self.resolve([old, new], "2026-09-30T12:00:00+09:00")["exclusions"], ["AAA"])
        self.assertEqual(self.resolve([old, new], "2026-10-02T12:00:00+09:00")["exclusions"], [])
        self.assertEqual(self.resolve([old, new], "2026-10-05T00:00:00+09:00")["exclusions"], ["AAA"])
        self.assertNotEqual(self.resolve([old, new])["periods"][0]["key"],
                            self.resolve([old, new])["periods"][1]["key"])

    def test_manual_pending_and_duplicate_rows_never_double_exclude(self):
        resolved = self.resolve([self.exclusion(), self.exclusion(), {"state": "대기"}])
        self.assertTrue(resolved["effective_complete"])
        self.assertEqual(resolved["exclusions"], ["AAA"])
        self.assertEqual(resolved["warnings"][0]["reason"], "overlapping_active_exclusions")

    def test_incomplete_manual_read_and_bad_periods_dont_become_empty_list(self):
        with self.assertRaises(InputError):
            resolve_exclusions({"lookup_complete": False, "as_of": "2026-10-01T00:00:00Z", "rows": []})
        for row in [self.exclusion(state="해제"), self.exclusion(ends_at="2026-09-01T00:00:00Z"),
                    self.exclusion(security_id="NASDAQ:BBB"), self.exclusion(starts_at="unknown")]:
            resolved = self.resolve([row])
            self.assertFalse(resolved["effective_complete"])
            self.assertIsNone(resolved["exclusions"])
            self.assertEqual(resolved["status"], "data_pending")

    def test_manual_exclusion_flows_into_ranking_and_replacement(self):
        resolved = self.resolve([self.exclusion()])
        ranked = rank({"source_complete": True, "universe_verified": True,
                       "exclusions": resolved["exclusions"], "rows": [self.row("AAA"), self.row("BBB")]})
        plan = decision_plan({"ranking_complete": ranked["ranking_complete"], "ranked": ranked["ranked"],
                              "exclusions": resolved["exclusions"], "target_size": 1, "holdings": ["AAA"]})
        self.assertEqual(plan["composition_trades"][0]["reason"], "manual_exclusion")
        self.assertEqual(plan["next_holdings"], ["BBB"])

    def row(self, symbol, cap=20e9, adtv=3e8, psr=2, growth=10):
        return dict(Ticker=symbol, MktCap_USD=cap, ADTV_90D_USD=adtv,
                    PSR=psr, **{"RevenueGrowth_YoY_Q_%": growth})

    def test_rank_ties_and_exclusions_leave_raw_rank(self):
        result = rank({"source_complete": True, "universe_verified": True,
                       "exclusions": ["AAA"],
                       "rows": [self.row("BBB"), self.row("AAA"), self.row("CCC", cap=10e9)]})
        a, b, c = result["ranked"]
        self.assertEqual([a["Ticker"], b["Ticker"], c["Ticker"]], ["AAA", "BBB", "CCC"])
        self.assertEqual(c["ComponentRanks"]["MktCap_USD"], 3)
        self.assertEqual(b["FinalRank"], 2)
        self.assertEqual(b["EligibleRank"], 1)
        self.assertIsNone(a["EligibleRank"])

    def test_rank_partial_and_duplicate_inputs_stop(self):
        for kwargs in [{"source_complete": False}, {"universe_verified": False}]:
            with self.assertRaises(InputError):
                rank({"source_complete": True, "universe_verified": True,
                      "rows": [self.row("A")], **kwargs})
        with self.assertRaises(InputError):
            rank({"source_complete": True, "universe_verified": True,
                  "rows": [self.row("a"), self.row("A")]})

    def test_missing_never_becomes_zero_or_verified_rank(self):
        result = rank({"source_complete": True, "universe_verified": True,
                       "rows": [self.row("A"), self.row("B", psr=None)]})
        self.assertFalse(result["ranking_complete"])
        self.assertEqual(result["data_gaps"], [{"Ticker": "B", "fields": ["PSR"]}])

    def test_buffer_twenty_retains_despite_new_top_candidate(self):
        p = decision_plan({"ranking_complete": True, "target_size": 1,
                           "holdings": ["OLD"], "ranked": [
                               {"Ticker": "NEW", "FinalRank": 1},
                               {"Ticker": "OLD", "FinalRank": 20}]})
        self.assertEqual(p["composition_trades"], [])
        self.assertEqual(p["weight_mode"], "no_trade")

    def test_rank_twentyone_replaces_without_monthly_reweight(self):
        p = decision_plan({"ranking_complete": True, "target_size": 1,
                           "holdings": ["OLD"], "ranked": [
                               {"Ticker": "NEW", "FinalRank": 1},
                               {"Ticker": "OLD", "FinalRank": 21}]})
        self.assertEqual([t["side"] for t in p["composition_trades"]], ["SELL", "BUY"])
        self.assertEqual(p["weight_mode"], "replace_with_sale_proceeds")
        self.assertFalse(p["fills_confirmed"])

    def test_missing_holding_does_not_sell_or_duplicate_buy(self):
        p = decision_plan({"ranking_complete": True, "target_size": 1,
                           "holdings": ["OLD"], "ranked": [{"Ticker": "NEW", "FinalRank": 1}]})
        self.assertEqual(p["pending"], ["OLD"])
        self.assertEqual(p["composition_trades"], [])
        p = decision_plan({"ranking_complete": False, "holdings": ["OLD"]})
        self.assertEqual(p["status"], "data_pending")

    def test_verified_exit_and_monthly_are_distinct(self):
        p = decision_plan({"ranking_complete": True, "target_size": 1, "monthly_due": True,
                           "holdings": ["OLD"], "ranked": [{"Ticker": "OLD", "FinalRank": 20}]})
        self.assertEqual(p["composition_trades"], [])
        self.assertEqual(p["target_weights"], {"OLD": 1})
        self.assertEqual(p["weight_mode"], "equal_weight_monthly")
        p = decision_plan({"ranking_complete": True, "target_size": 1,
                           "verified_universe_exits": ["OLD"], "holdings": ["OLD"],
                           "ranked": [{"Ticker": "NEW", "FinalRank": 1}]})
        self.assertEqual(p["composition_trades"][0]["reason"], "verified_universe_exit")

    def test_initial_shortage_reserves_cash(self):
        p = decision_plan({"ranking_complete": True, "target_size": 2,
                           "holdings": [], "ranked": [{"Ticker": "A", "FinalRank": 1}]})
        self.assertEqual(p["status"], "candidate_shortage")
        self.assertEqual(p["target_weights"], {"A": .5})
        self.assertEqual(p["target_cash_weight"], .5)

    def calendar(self):
        return {"calendar_complete": True, "calendar_start": "2026-10-02", "calendar_end": "2026-10-05",
                "sessions": [
                    {"session_date": "2026-10-02", "open_at": "2026-10-02T13:30:00Z", "close_at": "2026-10-02T20:00:00Z"},
                    {"session_date": "2026-10-05", "open_at": "2026-10-05T13:30:00Z", "close_at": "2026-10-05T20:00:00Z"}]}

    def test_premarket_can_use_today_open(self):
        p = next_session({**self.calendar(), "observed_at": "2026-10-02T21:29:00+09:00"})
        self.assertEqual(p["session_date"], "2026-10-02")
        self.assertEqual(p["earliest_open_kst"], "2026-10-02T22:30:00+09:00")

    def test_at_open_and_after_open_wait_next_session(self):
        for t in ["2026-10-02T22:30:00+09:00", "2026-10-03T06:00:00+09:00"]:
            p = next_session({**self.calendar(), "observed_at": t})
            self.assertEqual(p["session_date"], "2026-10-05")

    def test_monthly_weekend_and_dst(self):
        p = next_session({"kind": "monthly", "month": "2026-11", "calendar_complete": True,
                          "calendar_start": "2026-11-01", "calendar_end": "2026-11-30",
                          "sessions": [{"session_date": "2026-11-02", "open_at": "2026-11-02T14:30:00Z",
                                        "close_at": "2026-11-02T21:00:00Z"}]})
        self.assertEqual(p["session_date"], "2026-11-02")
        self.assertEqual(p["earliest_open_kst"], "2026-11-02T23:30:00+09:00")

    def candidate(self):
        return {"security_id": "AMEX:SPY", "session_date": "2026-09-29", "session": "regular", "interval": "1d",
                "value": 764.2, "field": "Close", "currency": "USD", "price_basis": BASIS,
                "provider": "Yahoo", "feed": "yfinance", "delay_seconds": 0, "finalized": True,
                "session_close_at": "2026-09-29T20:00:00Z", "observed_at": "2026-09-30T06:00:00+09:00"}

    def validate(self, candidate):
        return validate_close({"requested_security_id": "AMEX:SPY", "requested_session_date": "2026-09-29", "candidate": candidate})

    def test_completed_close_accepts_correct_day_and_basis(self):
        self.assertTrue(self.validate(self.candidate())["eligible_confirmed_close"])

    def test_stale_symbol_intraday_adjusted_unknown_delay_reject(self):
        for patch in [{"security_id": "NASDAQ:QQQ"}, {"session_date": "2026-09-28"},
                      {"session": "pre"}, {"interval": "1m"}, {"price_basis": "split_adjusted"},
                      {"delay_seconds": None}, {"field": "latestTrade.p"}]:
            self.assertFalse(self.validate({**self.candidate(), **patch})["eligible_confirmed_close"])

    def test_incomplete_bar_delay_and_iex_not_confirmed(self):
        for patch in [{"finalized": False}, {"observed_at": "2026-09-29T19:59:00Z"},
                      {"observed_at": "2026-09-29T20:01:00Z", "delay_seconds": 900}]:
            self.assertEqual(self.validate({**self.candidate(), **patch})["status"], "미확인")
        self.assertEqual(self.validate({**self.candidate(), "provider": "Alpaca Paper Trading", "feed": "iex"})["status"], "추정")

    def record(self, status="확정", value=764.2):
        return {"security_id": "AMEX:SPY", "session_date": "2026-09-29", "currency": "USD",
                "price_basis": BASIS, "status": status, "provider": "Yahoo", "value": value}

    def test_retry_existing_row_is_noop_and_precision_is_tolerated(self):
        p = close_plan({"lookup_complete": True, "records": [self.record(value=764.200012)],
                        "existing": [{**self.record(), "page_id": "remote-id"}]})
        self.assertEqual(p["actions"][0]["action"], "skip")
        self.assertFalse(p["writes_executed"])

    def test_confirmed_close_never_downgrades(self):
        p = close_plan({"lookup_complete": True, "records": [self.record("미확인", None)],
                        "existing": [{**self.record(), "page_id": "remote-id"}]})
        self.assertEqual(p["actions"][0]["reason"], "preserve_higher_quality")

    def test_upgrade_reuses_same_page(self):
        p = close_plan({"lookup_complete": True, "records": [self.record()],
                        "existing": [{**self.record("미확인", None), "page_id": "remote-id"}]})
        self.assertEqual(p["actions"][0]["action"], "update")
        self.assertEqual(p["actions"][0]["page_id"], "remote-id")

    def test_duplicate_remote_and_conflicting_price_do_not_write(self):
        row = {**self.record(), "page_id": "remote-id"}
        for old in [[row, {**row, "page_id": "other"}], [{**row, "value": 800}]]:
            p = close_plan({"lookup_complete": True, "records": [self.record()], "existing": old})
            self.assertEqual(p["actions"][0]["action"], "conflict")

    def test_correction_requires_key_and_preserves_old(self):
        p = close_plan({"lookup_complete": True, "records": [self.record()],
                        "existing": [{**self.record(value=800), "page_id": "remote-id"}]})
        key = p["actions"][0]["key"]
        p = close_plan({"lookup_complete": True, "records": [{**self.record(), "correction_note": "verified source correction"}],
                        "existing": [{**self.record(value=800), "page_id": "remote-id"}], "verified_correction_keys": [key]})
        self.assertEqual(p["actions"][0]["previous_record"]["value"], 800)
        self.assertEqual(p["actions"][0]["action"], "update")

    def test_incomplete_lookup_stops_and_unknown_price_is_not_zero(self):
        with self.assertRaises(InputError):
            close_plan({"lookup_complete": False, "records": [self.record()], "existing": []})
        with self.assertRaises(InputError):
            close_plan({"lookup_complete": True, "records": [self.record("미확인", 0)], "existing": []})

    def test_cli_safe_failure_and_valid_request(self):
        cli = str(Path(__file__).with_name("mechanical.py"))
        result = subprocess.run([sys.executable, cli, "close-plan"], input="{bad", text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout), {"ok": False, "error": "invalid_input_shape"})
        result = subprocess.run([sys.executable, cli, "close-plan"], input=json.dumps({"lookup_complete": True, "records": [self.record()], "existing": []}), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["counts"], {"create": 1})


if __name__ == "__main__":
    unittest.main()

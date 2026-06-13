"""
Tests for shopee_engine.feedback_engine.

Covers:
- CSV import (revenue / click / order)
- prediction logging
- learning report accuracy metrics
- weight retraining
- profit learning (TP/FP/FN)
- recommendations
- adaptive daily picks
- Spearman correlation helper
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Resolve project root so imports work
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_temp_db() -> Path:
    """Return a unique temp path for a DuckDB database (file must NOT exist yet)."""
    f = tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False)
    f.close()
    p = Path(f.name)
    p.unlink()  # DuckDB creates it fresh; pre-existing empty file is rejected
    return p


def _write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _patch_db(db_path: Path):
    """Monkey-patch config to point at a temp DB."""
    from shopee_engine import config as cfg_mod
    cfg_mod.config.db_path  = db_path
    cfg_mod.config.data_dir = db_path.parent


# ---------------------------------------------------------------------------
# 1. Spearman helper
# ---------------------------------------------------------------------------

class TestSpearman(unittest.TestCase):

    def test_perfect_positive(self):
        from shopee_engine.feedback_engine import _spearman
        self.assertAlmostEqual(_spearman([1, 2, 3, 4], [1, 2, 3, 4]), 1.0, places=5)

    def test_perfect_negative(self):
        from shopee_engine.feedback_engine import _spearman
        self.assertAlmostEqual(_spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0, places=5)

    def test_no_correlation(self):
        from shopee_engine.feedback_engine import _spearman
        r = _spearman([1, 2, 3, 4], [3, 1, 4, 2])
        self.assertGreater(r, -1.0)
        self.assertLess(r, 1.0)

    def test_too_short(self):
        from shopee_engine.feedback_engine import _spearman
        self.assertEqual(_spearman([5.0], [5.0]), 0.0)

    def test_with_ties(self):
        from shopee_engine.feedback_engine import _spearman
        r = _spearman([1, 1, 2, 3], [1, 2, 3, 4])
        self.assertGreater(r, 0.5)


# ---------------------------------------------------------------------------
# 2. CSV import
# ---------------------------------------------------------------------------

class TestImportRevenueFeedback(unittest.TestCase):

    def setUp(self):
        self._db = _make_temp_db()
        _patch_db(self._db)

    def tearDown(self):
        try:
            self._db.unlink(missing_ok=True)
        except Exception:
            pass

    def _make_revenue_csv(self, tmp_dir: Path) -> Path:
        p = tmp_dir / "revenue.csv"
        _write_csv([
            {"date": "2026-06-01", "product_name": "Product A", "clicks": "500",
             "orders": "20", "revenue": "10000", "commission": "700"},
            {"date": "2026-06-01", "product_name": "Product B", "clicks": "300",
             "orders": "12", "revenue": "6000",  "commission": "420"},
            {"date": "2026-06-02", "product_name": "Product A", "clicks": "600",
             "orders": "25", "revenue": "12500", "commission": "875"},
        ], p)
        return p

    def test_import_revenue_report_basic(self):
        from shopee_engine.feedback_engine import import_revenue_report, REVENUE_TABLE
        import duckdb
        with tempfile.TemporaryDirectory() as d:
            csv_path = self._make_revenue_csv(Path(d))
            result = import_revenue_report(csv_path)

        self.assertEqual(result["rows_imported"], 3)
        self.assertEqual(result["source"], "revenue")

        con = duckdb.connect(str(self._db))
        rows = con.execute(f"SELECT COUNT(*) FROM {REVENUE_TABLE}").fetchone()[0]
        con.close()
        self.assertEqual(rows, 3)

    def test_import_revenue_report_deduplication(self):
        from shopee_engine.feedback_engine import import_revenue_report, REVENUE_TABLE
        import duckdb
        with tempfile.TemporaryDirectory() as d:
            csv_path = self._make_revenue_csv(Path(d))
            import_revenue_report(csv_path)
            import_revenue_report(csv_path)  # second import same dates

        con = duckdb.connect(str(self._db))
        rows = con.execute(f"SELECT COUNT(*) FROM {REVENUE_TABLE}").fetchone()[0]
        con.close()
        self.assertEqual(rows, 3)  # deduplicated by (source, report_date)

    def test_import_click_report(self):
        from shopee_engine.feedback_engine import import_click_report, REVENUE_TABLE
        import duckdb
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "clicks.csv"
            _write_csv([
                {"date": "2026-06-01", "product_name": "P1", "clicks": "100"},
            ], p)
            result = import_click_report(p)

        self.assertEqual(result["source"], "clicks")
        con = duckdb.connect(str(self._db))
        row = con.execute(f"SELECT source FROM {REVENUE_TABLE} LIMIT 1").fetchone()
        con.close()
        self.assertEqual(row[0], "clicks")

    def test_import_order_report(self):
        from shopee_engine.feedback_engine import import_order_report, REVENUE_TABLE
        import duckdb
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "orders.csv"
            _write_csv([
                {"date": "2026-06-01", "product_name": "P2",
                 "orders": "5", "revenue": "2500", "commission": "175"},
            ], p)
            result = import_order_report(p)

        self.assertEqual(result["source"], "orders")

    def test_import_missing_file_raises(self):
        from shopee_engine.feedback_engine import import_revenue_report
        with self.assertRaises(FileNotFoundError):
            import_revenue_report(Path("/nonexistent/path.csv"))


# ---------------------------------------------------------------------------
# 3. log_predictions
# ---------------------------------------------------------------------------

class TestLogPredictions(unittest.TestCase):

    def setUp(self):
        self._db = _make_temp_db()
        _patch_db(self._db)

        import duckdb
        con = duckdb.connect(str(self._db))
        con.execute("""
            CREATE TABLE products (
                item_name TEXT, item_sold DOUBLE, "like" DOUBLE,
                discount_percentage DOUBLE, shop_rating DOUBLE, item_rating DOUBLE
            )
        """)
        con.execute("""
            INSERT INTO products VALUES
            ('Product Alpha', 5000, 2000, 15.0, 4.8, 4.7),
            ('Product Beta',  3000, 1000, 10.0, 4.5, 4.4),
            ('Product Gamma', 1000,  500,  5.0, 4.2, 4.1)
        """)
        con.close()

    def tearDown(self):
        try:
            self._db.unlink(missing_ok=True)
        except Exception:
            pass

    def test_log_predictions_inserts_rows(self):
        from shopee_engine.feedback_engine import log_predictions, PREDICT_TABLE
        import duckdb
        count = log_predictions(table_name="products", top=3)
        self.assertEqual(count, 3)

        con = duckdb.connect(str(self._db))
        rows = con.execute(f"SELECT COUNT(*) FROM {PREDICT_TABLE}").fetchone()[0]
        con.close()
        self.assertEqual(rows, 3)

    def test_log_predictions_rank_order(self):
        from shopee_engine.feedback_engine import log_predictions, PREDICT_TABLE
        import duckdb
        log_predictions(table_name="products", top=3)
        con = duckdb.connect(str(self._db))
        top1 = con.execute(
            f"SELECT product_name FROM {PREDICT_TABLE} WHERE predicted_rank=1"
        ).fetchone()[0]
        con.close()
        self.assertIn("Alpha", top1)


# ---------------------------------------------------------------------------
# 4. learning_report
# ---------------------------------------------------------------------------

class TestLearningReport(unittest.TestCase):

    def setUp(self):
        self._db = _make_temp_db()
        _patch_db(self._db)

        import duckdb
        from shopee_engine.feedback_engine import PREDICT_TABLE, REVENUE_TABLE, _init_feedback_tables

        con = duckdb.connect(str(self._db))

        con.execute("""
            CREATE TABLE products (
                item_name TEXT, item_sold DOUBLE, "like" DOUBLE,
                discount_percentage DOUBLE, shop_rating DOUBLE, item_rating DOUBLE
            )
        """)
        for i in range(1, 6):
            con.execute(f"INSERT INTO products VALUES ('Prod {i}', {i*1000}, {i*200}, {i*5.0}, {4.0+i*0.1}, {3.9+i*0.1})")

        _init_feedback_tables(con)

        for i in range(1, 6):
            con.execute(f"""
                INSERT INTO {PREDICT_TABLE}
                (id, logged_at, snapshot_date, product_name, predicted_opp_score, predicted_viral_score, predicted_rank)
                VALUES ({i}, '2026-06-13 08:00:00', '2026-06-13', 'Prod {i}', {(6-i)*1000.0}, {(6-i)*800.0}, {i})
            """)

        for i in range(1, 5):
            con.execute(f"""
                INSERT INTO {REVENUE_TABLE}
                (id, imported_at, report_date, product_name, product_id, clicks, orders,
                 revenue, commission, category, shop_name, source)
                VALUES ({i}, '2026-06-13', '2026-06-13', 'Prod {i}', '', {i*100}, {i*10},
                        {i*5000.0}, {i*350.0}, 'Test', 'TestShop', 'revenue')
            """)
        con.close()

    def tearDown(self):
        try:
            self._db.unlink(missing_ok=True)
        except Exception:
            pass

    def test_learning_report_returns_accuracy(self):
        from shopee_engine.feedback_engine import learning_report
        data = learning_report()

        self.assertNotIn("error", data)
        self.assertIn("product_accuracy",     data)
        self.assertIn("opportunity_accuracy", data)
        self.assertIn("viral_accuracy",       data)
        self.assertIsInstance(data["product_accuracy"],     float)
        self.assertGreaterEqual(data["product_accuracy"],   0.0)
        self.assertLessEqual(data["product_accuracy"],    100.0)

    def test_learning_report_no_predictions(self):
        from shopee_engine.feedback_engine import learning_report, PREDICT_TABLE
        import duckdb
        con = duckdb.connect(str(self._db))
        con.execute(f"DELETE FROM {PREDICT_TABLE}")
        con.close()
        data = learning_report()
        self.assertIn("error", data)


# ---------------------------------------------------------------------------
# 5. retrain_rankings
# ---------------------------------------------------------------------------

class TestRetrainRankings(unittest.TestCase):

    def setUp(self):
        self._db = _make_temp_db()
        _patch_db(self._db)

        import duckdb
        from shopee_engine.feedback_engine import REVENUE_TABLE, _init_feedback_tables

        con = duckdb.connect(str(self._db))
        con.execute("""
            CREATE TABLE products (
                item_name TEXT, item_sold DOUBLE, "like" DOUBLE,
                discount_percentage DOUBLE, shop_rating DOUBLE, item_rating DOUBLE
            )
        """)
        for i in range(1, 11):
            con.execute(f"INSERT INTO products VALUES ('Prod {i}', {i*1000}, {i*200}, {i*3.0}, {4.0+i*0.05}, {3.9+i*0.05})")

        _init_feedback_tables(con)
        for i in range(1, 9):
            con.execute(f"""
                INSERT INTO {REVENUE_TABLE}
                (id, imported_at, report_date, product_name, product_id,
                 clicks, orders, revenue, commission, category, shop_name, source)
                VALUES ({i}, '2026-06-13', '2026-06-13', 'Prod {i}', '',
                        {i*80}, {i*8}, {i*4000.0}, {i*280.0}, 'Test', 'Shop', 'revenue')
            """)
        con.close()

    def tearDown(self):
        try:
            self._db.unlink(missing_ok=True)
        except Exception:
            pass

    def test_retrain_returns_updated_weights(self):
        from shopee_engine.feedback_engine import retrain_rankings, DEFAULT_WEIGHTS
        data = retrain_rankings(table_name="products")

        self.assertIn("new_weights", data)
        self.assertIn("old_weights", data)
        self.assertIn("signal_correlations", data)
        self.assertIn("matched_products", data)

        new_w = data["new_weights"]
        self.assertAlmostEqual(sum(new_w.values()), 1.0, places=3)
        for key in DEFAULT_WEIGHTS:
            self.assertIn(key, new_w)
            self.assertGreaterEqual(new_w[key], 0.05)
            self.assertLessEqual(new_w[key], 0.80)

    def test_retrain_persists_to_db(self):
        from shopee_engine.feedback_engine import retrain_rankings, WEIGHT_TABLE
        import duckdb
        retrain_rankings(table_name="products")
        con = duckdb.connect(str(self._db))
        cnt = con.execute(f"SELECT COUNT(*) FROM {WEIGHT_TABLE}").fetchone()[0]
        con.close()
        self.assertEqual(cnt, 1)

    def test_retrain_increments_iteration(self):
        from shopee_engine.feedback_engine import retrain_rankings
        r1 = retrain_rankings(table_name="products")
        r2 = retrain_rankings(table_name="products")
        self.assertEqual(r2["iteration"], r1["iteration"] + 1)


# ---------------------------------------------------------------------------
# 6. profit_learning
# ---------------------------------------------------------------------------

class TestProfitLearning(unittest.TestCase):

    def setUp(self):
        self._db = _make_temp_db()
        _patch_db(self._db)

        import duckdb
        from shopee_engine.feedback_engine import PREDICT_TABLE, REVENUE_TABLE, _init_feedback_tables

        con = duckdb.connect(str(self._db))
        _init_feedback_tables(con)

        for i in range(1, 11):
            con.execute(f"""
                INSERT INTO {PREDICT_TABLE}
                (id, logged_at, snapshot_date, product_name, predicted_opp_score, predicted_viral_score, predicted_rank)
                VALUES ({i}, '2026-06-13', '2026-06-13', 'Prod {i}', {(11-i)*1000.0}, {(11-i)*800.0}, {i})
            """)

        # Products 1-6 have real revenue (good performers)
        for i in range(1, 7):
            con.execute(f"""
                INSERT INTO {REVENUE_TABLE}
                (id, imported_at, report_date, product_name, product_id,
                 clicks, orders, revenue, commission, category, shop_name, source)
                VALUES ({i}, '2026-06-13', '2026-06-13', 'Prod {i}', '',
                        {i*100}, {i*5}, {i*3000.0}, {i*210.0}, 'Cat', 'Shop', 'revenue')
            """)

        # Undiscovered winner — not in prediction_log top-5 but has high revenue
        con.execute(f"""
            INSERT INTO {REVENUE_TABLE}
            (id, imported_at, report_date, product_name, product_id,
             clicks, orders, revenue, commission, category, shop_name, source)
            VALUES (99, '2026-06-13', '2026-06-13', 'Unknown Winner', '',
                    2000, 150, 90000.0, 6300.0, 'Cat', 'Shop', 'revenue')
        """)
        con.close()

    def tearDown(self):
        try:
            self._db.unlink(missing_ok=True)
        except Exception:
            pass

    def test_profit_learning_structure(self):
        from shopee_engine.feedback_engine import profit_learning
        data = profit_learning(top=5)

        self.assertNotIn("error", data)
        self.assertIn("true_positives",  data)
        self.assertIn("false_positives", data)
        self.assertIn("false_negatives", data)
        self.assertIn("precision",       data)
        self.assertIn("recall",          data)
        self.assertIn("f1_score",        data)

    def test_profit_learning_has_false_negatives(self):
        from shopee_engine.feedback_engine import profit_learning
        data = profit_learning(top=5)
        fn_names = [item["product"].lower() for item in data["false_negatives"]]
        self.assertTrue(any("unknown winner" in n for n in fn_names))

    def test_profit_learning_precision_range(self):
        from shopee_engine.feedback_engine import profit_learning
        data = profit_learning(top=5)
        self.assertGreaterEqual(data["precision"], 0.0)
        self.assertLessEqual(data["precision"], 100.0)


# ---------------------------------------------------------------------------
# 7. recommend_next_products
# ---------------------------------------------------------------------------

class TestRecommendNextProducts(unittest.TestCase):

    def setUp(self):
        self._db = _make_temp_db()
        _patch_db(self._db)

        import duckdb
        from shopee_engine.feedback_engine import REVENUE_TABLE, _init_feedback_tables

        con = duckdb.connect(str(self._db))
        con.execute("""
            CREATE TABLE products (
                item_name TEXT, item_sold DOUBLE, "like" DOUBLE,
                discount_percentage DOUBLE, shop_rating DOUBLE, item_rating DOUBLE
            )
        """)
        for i in range(1, 21):
            con.execute(f"INSERT INTO products VALUES ('Prod {i}', {i*500}, {i*100}, {i*2.0}, {4.0+i*0.04}, {3.9+i*0.04})")

        _init_feedback_tables(con)
        # Mark Prod 1-5 as already promoted (in revenue_feedback)
        for i in range(1, 6):
            con.execute(f"""
                INSERT INTO {REVENUE_TABLE}
                (id, imported_at, report_date, product_name, product_id,
                 clicks, orders, revenue, commission, category, shop_name, source)
                VALUES ({i}, '2026-06-13', '2026-06-13', 'Prod {i}', '',
                        100, 5, 2500.0, 175.0, 'Cat', 'Shop', 'revenue')
            """)
        con.close()

    def tearDown(self):
        try:
            self._db.unlink(missing_ok=True)
        except Exception:
            pass

    def test_recommendations_exclude_promoted(self):
        from shopee_engine.feedback_engine import recommend_next_products
        recs = recommend_next_products(top=10, table_name="products")

        promoted = {"prod 1", "prod 2", "prod 3", "prod 4", "prod 5"}
        for r in recs:
            self.assertNotIn(r["name"].lower(), promoted)

    def test_recommendations_count(self):
        from shopee_engine.feedback_engine import recommend_next_products
        recs = recommend_next_products(top=5, table_name="products")
        self.assertLessEqual(len(recs), 5)
        self.assertGreater(len(recs), 0)

    def test_recommendations_have_required_keys(self):
        from shopee_engine.feedback_engine import recommend_next_products
        recs = recommend_next_products(top=3, table_name="products")
        for r in recs:
            self.assertIn("name",           r)
            self.assertIn("adaptive_score", r)
            self.assertIn("sold",           r)
            self.assertIn("price",          r)


# ---------------------------------------------------------------------------
# 8. adaptive_daily_picks
# ---------------------------------------------------------------------------

class TestAdaptiveDailyPicks(unittest.TestCase):

    def setUp(self):
        self._db = _make_temp_db()
        _patch_db(self._db)

        import duckdb
        con = duckdb.connect(str(self._db))
        con.execute("""
            CREATE TABLE products (
                item_name TEXT, item_sold DOUBLE, "like" DOUBLE,
                discount_percentage DOUBLE, shop_rating DOUBLE, item_rating DOUBLE,
                global_category1 TEXT, sale_price DOUBLE
            )
        """)
        for i in range(1, 31):
            cat = "Mobile & Gadget" if i % 3 == 0 else ("Home & Living" if i % 3 == 1 else "Health")
            con.execute(f"INSERT INTO products VALUES ('Prod {i}', {i*400}, {i*100 if i>5 else 50}, {i*3.0}, {4.0+i*0.03}, {3.9+i*0.03}, '{cat}', {i*100.0})")
        con.close()

    def tearDown(self):
        try:
            self._db.unlink(missing_ok=True)
        except Exception:
            pass

    def test_adaptive_picks_returns_buckets(self):
        from shopee_engine.feedback_engine import adaptive_daily_picks
        picks = adaptive_daily_picks(top=3, table_name="products")
        self.assertIsInstance(picks, dict)
        self.assertGreater(len(picks), 0)

    def test_adaptive_picks_uses_default_weights_when_no_training(self):
        from shopee_engine.feedback_engine import adaptive_daily_picks, DEFAULT_WEIGHTS
        picks = adaptive_daily_picks(top=3, table_name="products")
        for bucket, items in picks.items():
            for item in items:
                self.assertIn("adaptive_score", item)
                self.assertGreaterEqual(item["adaptive_score"], 0.0)

    def test_adaptive_picks_respects_top_limit(self):
        from shopee_engine.feedback_engine import adaptive_daily_picks
        picks = adaptive_daily_picks(top=2, table_name="products")
        for bucket, items in picks.items():
            self.assertLessEqual(len(items), 2)


if __name__ == "__main__":
    unittest.main()

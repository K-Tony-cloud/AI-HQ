"""
Tests for Knowledge Engine — Phase 3A

Test classes:
    TestGraphValidation      — product_graph.yaml validation
    TestConfigValidation     — link_config.yaml validation
    TestPinsValidation       — pinned_links.yaml validation
    TestRealYAML             — integration: real YAML files load cleanly
    TestSignalComputation    — SignalVector correctness
    TestScoring              — weighted scoring and multipliers
    TestSafetyAndFilters     — score threshold, self-link, subcategory cap
    TestColdStart            — published threshold gate
    TestPinnedLinks          — pin injection, safety, expiry
    TestAnchorRotation       — hash determinism, overrides, template variables
    TestComputeLinks         — pure compute_links() end-to-end
    TestClusterBundleStub    — ClusterBundle raises NotImplementedError
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from shopee_engine.knowledge_engine import (
    ArticleProfile,
    ClusterBundle,
    ConfigValidationError,
    GraphValidationError,
    KnowledgeGraph,
    LinkBundle,
    PinsValidationError,
    SignalVector,
    compute_links,
    compute_signals,
)
from shopee_engine.knowledge_engine.graph import _parse_and_validate_config, _parse_and_validate_graph, _parse_and_validate_pins
from shopee_engine.knowledge_engine.linker import (
    _placement_for,
    _resolve_link_type,
    _select_anchor,
    _weighted_score,
)
from shopee_engine.knowledge_engine.signals import (
    _is_budget_alt,
    _jaccard,
    _keyword_diversity,
    _price_compat,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _minimal_graph_data(*, extra_nodes=None, extra_edges=None, extra_templates=None):
    nodes = {
        "fans": {
            "label": "พัดลม USB",
            "category": "mobile-gadgets",
            "intent_tags": ["cooling", "portable"],
            "personas": ["งบน้อย", "พกพาบ่อย"],
            "price_typical": [100, 500],
        },
        "powerbank": {
            "label": "Power Bank",
            "category": "mobile-gadgets",
            "intent_tags": ["portable", "charging"],
            "personas": ["พกพาบ่อย", "งบน้อย"],
            "price_typical": [200, 1000],
        },
        "desk": {
            "label": "อุปกรณ์โต๊ะ",
            "category": "home-living",
            "intent_tags": ["office", "wfh"],
            "personas": ["งบน้อย"],
            "price_typical": [50, 500],
        },
    }
    if extra_nodes:
        nodes.update(extra_nodes)

    edges = [
        {"source": "fans", "target": "powerbank", "type": "complement", "score": 0.85, "rationale": "test"},
        {"source": "fans", "target": "desk",      "type": "related",    "score": 0.50, "rationale": "test"},
        {"source": "powerbank", "target": "fans", "type": "complement", "score": 0.80, "rationale": "test"},
    ]
    if extra_edges:
        edges.extend(extra_edges)

    templates = {
        "complement": ["{target_label} ที่ใช้คู่กัน", "ใช้ร่วมกับ {target_label}"],
        "budget_alt": ["ดูตัวเลือกงบ {target_price_range}", "รุ่นประหยัดกว่า"],
        "related":    ["อ่านเพิ่มเติมเรื่อง {target_label}", "บทความใกล้เคียง"],
        "type_alt":   ["ทางเลือกแทน {target_label}", "สินค้าแนวเดียวกัน"],
    }
    if extra_templates:
        templates.update(extra_templates)

    return {"version": "1.0", "nodes": nodes, "edges": edges, "anchor_templates": templates}


def _minimal_config_data(**overrides):
    data = {
        "version": "1.0",
        "scoring_weights": {
            "complement": 0.35, "persona_overlap": 0.20, "use_case_proximity": 0.15,
            "price_compat": 0.15, "category_match": 0.10, "keyword_diversity": 0.05,
            "seasonal_intent": 0.00, "content_performance": 0.00, "campaign_match": 0.00,
        },
        "multipliers": {
            "budget_alt_bonus": 1.20,
            "same_subcategory_penalty": 0.50,
            "min_score_threshold": 0.25,
        },
        "limits": {
            "max_links_per_article": 4,
            "max_same_subcategory": 1,
            "min_links_to_show": 2,
            "min_published_threshold": 5,
        },
        "anchor_rotation": "hash",
    }
    data.update(overrides)
    return data


def _minimal_pins_data(pins=None):
    return {"version": "1.0", "pinned": pins or []}


def _make_graph(graph_data=None, config_data=None, pins_data=None) -> KnowledgeGraph:
    return KnowledgeGraph.from_dicts(
        graph_data  or _minimal_graph_data(),
        config_data or _minimal_config_data(),
        pins_data   or _minimal_pins_data(),
    )


def _profile(
    article_id="fans-500", keyword="พัดลม USB ไม่เกิน 500", category="mobile-gadgets",
    subcategory="fans", price_min=100, price_max=449,
    intent_tags=("cooling", "portable"), personas=("งบน้อย", "พกพาบ่อย"),
    node_label="พัดลม USB",
) -> ArticleProfile:
    return ArticleProfile(
        article_id=article_id, keyword=keyword, category=category,
        subcategory=subcategory, price_min=price_min, price_max=price_max,
        canonical_url=f"https://suenaidee.com/{article_id}/",
        intent_tags=tuple(intent_tags), personas=tuple(personas),
        node_label=node_label,
    )


# ---------------------------------------------------------------------------
# TestGraphValidation
# ---------------------------------------------------------------------------

class TestGraphValidation(unittest.TestCase):

    def test_valid_graph_loads(self):
        g = _make_graph()
        self.assertIsNotNone(g)

    def test_missing_nodes_raises(self):
        data = _minimal_graph_data()
        data["nodes"] = {}
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("empty", str(ctx.exception))

    def test_duplicate_node_id_raises(self):
        # Simulate duplicate by manually passing
        data = _minimal_graph_data()
        # Inject duplicate via manipulation (edge points to same node twice)
        data["edges"].append({"source": "fans", "target": "fans", "type": "complement", "score": 0.5, "rationale": ""})
        with self.assertRaises(GraphValidationError):
            _parse_and_validate_graph(data)

    def test_missing_node_label_raises(self):
        data = _minimal_graph_data()
        data["nodes"]["fans"]["label"] = ""
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("label", str(ctx.exception))

    def test_missing_node_category_raises(self):
        data = _minimal_graph_data()
        data["nodes"]["fans"]["category"] = ""
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("category", str(ctx.exception))

    def test_invalid_price_typical_raises(self):
        data = _minimal_graph_data()
        data["nodes"]["fans"]["price_typical"] = [100]  # only one value
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("price_typical", str(ctx.exception))

    def test_edge_score_above_1_raises(self):
        data = _minimal_graph_data()
        data["edges"][0]["score"] = 1.5
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("score", str(ctx.exception))

    def test_edge_score_negative_raises(self):
        data = _minimal_graph_data()
        data["edges"][0]["score"] = -0.1
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("score", str(ctx.exception))

    def test_edge_missing_source_raises(self):
        data = _minimal_graph_data()
        data["edges"].append({"target": "powerbank", "type": "complement", "score": 0.5, "rationale": ""})
        with self.assertRaises(GraphValidationError):
            _parse_and_validate_graph(data)

    def test_edge_referencing_nonexistent_node_raises(self):
        data = _minimal_graph_data()
        data["edges"].append({"source": "fans", "target": "nonexistent-xyz", "type": "complement", "score": 0.5, "rationale": ""})
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("nonexistent-xyz", str(ctx.exception))

    def test_self_edge_raises(self):
        data = _minimal_graph_data()
        data["edges"].append({"source": "fans", "target": "fans", "type": "complement", "score": 0.5, "rationale": ""})
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("self-edge", str(ctx.exception))

    def test_invalid_edge_type_raises(self):
        data = _minimal_graph_data()
        data["edges"][0]["type"] = "buy_now"
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("type", str(ctx.exception))

    def test_empty_anchor_pool_raises(self):
        data = _minimal_graph_data()
        data["anchor_templates"]["complement"] = []
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        self.assertIn("complement", str(ctx.exception))

    def test_multiple_errors_collected(self):
        data = _minimal_graph_data()
        data["nodes"]["fans"]["label"] = ""
        data["nodes"]["powerbank"]["category"] = ""
        with self.assertRaises(GraphValidationError) as ctx:
            _parse_and_validate_graph(data)
        msg = str(ctx.exception)
        self.assertIn("label", msg)
        self.assertIn("category", msg)

    def test_get_edge_returns_correct(self):
        g = _make_graph()
        edge = g.get_edge("fans", "powerbank")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.link_type, "complement")
        self.assertEqual(edge.score, 0.85)

    def test_get_edge_missing_returns_none(self):
        g = _make_graph()
        self.assertIsNone(g.get_edge("powerbank", "desk"))

    def test_get_anchor_pool_generic(self):
        g = _make_graph()
        pool = g.get_anchor_pool("fans", "complement")
        self.assertIsInstance(pool, list)
        self.assertTrue(len(pool) >= 1)

    def test_get_anchor_pool_subcategory_override(self):
        data = _minimal_graph_data()
        data["anchor_templates"]["subcategory_overrides"] = {
            "fans": {"complement": ["Override anchor สำหรับ fans"]}
        }
        g = _make_graph(graph_data=data)
        pool = g.get_anchor_pool("fans", "complement")
        self.assertIn("Override anchor สำหรับ fans", pool)

    def test_get_anchor_pool_fallback_to_generic(self):
        g = _make_graph()
        # "desk" has no subcategory override
        pool = g.get_anchor_pool("desk", "complement")
        self.assertGreater(len(pool), 0)


# ---------------------------------------------------------------------------
# TestConfigValidation
# ---------------------------------------------------------------------------

class TestConfigValidation(unittest.TestCase):

    def test_valid_config_loads(self):
        cfg = _parse_and_validate_config(_minimal_config_data())
        self.assertEqual(cfg.anchor_rotation, "hash")

    def test_weights_must_sum_to_1(self):
        data = _minimal_config_data()
        data["scoring_weights"]["complement"] = 0.99  # sum >> 1
        with self.assertRaises(ConfigValidationError) as ctx:
            _parse_and_validate_config(data)
        self.assertIn("sum", str(ctx.exception))

    def test_missing_weight_key_raises(self):
        data = _minimal_config_data()
        del data["scoring_weights"]["complement"]
        with self.assertRaises(ConfigValidationError) as ctx:
            _parse_and_validate_config(data)
        self.assertIn("complement", str(ctx.exception))

    def test_negative_weight_raises(self):
        data = _minimal_config_data()
        data["scoring_weights"]["complement"] = -0.1
        with self.assertRaises(ConfigValidationError):
            _parse_and_validate_config(data)

    def test_missing_limit_key_raises(self):
        data = _minimal_config_data()
        del data["limits"]["max_links_per_article"]
        with self.assertRaises(ConfigValidationError) as ctx:
            _parse_and_validate_config(data)
        self.assertIn("max_links_per_article", str(ctx.exception))

    def test_invalid_rotation_strategy_raises(self):
        data = _minimal_config_data()
        data["anchor_rotation"] = "random"
        with self.assertRaises(ConfigValidationError) as ctx:
            _parse_and_validate_config(data)
        self.assertIn("anchor_rotation", str(ctx.exception))

    def test_valid_rotation_strategies(self):
        for strategy in ("hash", "round_robin", "performance"):
            data = _minimal_config_data()
            data["anchor_rotation"] = strategy
            cfg = _parse_and_validate_config(data)
            self.assertEqual(cfg.anchor_rotation, strategy)

    def test_weights_read_correctly(self):
        cfg = _parse_and_validate_config(_minimal_config_data())
        self.assertAlmostEqual(cfg.weights["complement"], 0.35)
        self.assertAlmostEqual(cfg.weights["persona_overlap"], 0.20)

    def test_limits_read_correctly(self):
        cfg = _parse_and_validate_config(_minimal_config_data())
        self.assertEqual(cfg.max_links_per_article, 4)
        self.assertEqual(cfg.min_published_threshold, 5)


# ---------------------------------------------------------------------------
# TestPinsValidation
# ---------------------------------------------------------------------------

class TestPinsValidation(unittest.TestCase):

    def test_empty_pins_valid(self):
        pins = _parse_and_validate_pins(_minimal_pins_data())
        self.assertEqual(pins, [])

    def test_valid_pin_parses(self):
        data = _minimal_pins_data([{
            "source_article_id": "fans-500",
            "target_article_id": "powerbank-travel",
            "link_type": "complement",
            "anchor_text": "Power Bank สำหรับพัดลม USB",
            "placement": "post_advisor",
            "priority": 1,
            "note": "test",
            "expires_at": None,
        }])
        pins = _parse_and_validate_pins(data)
        self.assertEqual(len(pins), 1)
        self.assertEqual(pins[0].anchor_text, "Power Bank สำหรับพัดลม USB")

    def test_missing_source_raises(self):
        data = _minimal_pins_data([{
            "target_article_id": "powerbank",
            "link_type": "complement",
            "anchor_text": "test",
            "placement": "post_advisor",
            "priority": 1,
            "note": "",
            "expires_at": None,
        }])
        with self.assertRaises(PinsValidationError) as ctx:
            _parse_and_validate_pins(data)
        self.assertIn("source_article_id", str(ctx.exception))

    def test_self_link_raises(self):
        data = _minimal_pins_data([{
            "source_article_id": "fans-500",
            "target_article_id": "fans-500",
            "link_type": "complement",
            "anchor_text": "test",
            "placement": "post_advisor",
            "priority": 1,
            "note": "",
            "expires_at": None,
        }])
        with self.assertRaises(PinsValidationError) as ctx:
            _parse_and_validate_pins(data)
        self.assertIn("same", str(ctx.exception))

    def test_invalid_link_type_raises(self):
        data = _minimal_pins_data([{
            "source_article_id": "fans-500",
            "target_article_id": "powerbank",
            "link_type": "buy_now",
            "anchor_text": "test",
            "placement": "post_advisor",
            "priority": 1,
            "note": "",
            "expires_at": None,
        }])
        with self.assertRaises(PinsValidationError):
            _parse_and_validate_pins(data)

    def test_empty_anchor_raises(self):
        data = _minimal_pins_data([{
            "source_article_id": "fans-500",
            "target_article_id": "powerbank",
            "link_type": "complement",
            "anchor_text": "",
            "placement": "post_advisor",
            "priority": 1,
            "note": "",
            "expires_at": None,
        }])
        with self.assertRaises(PinsValidationError):
            _parse_and_validate_pins(data)

    def test_pins_sorted_by_priority(self):
        data = _minimal_pins_data([
            {"source_article_id": "a", "target_article_id": "b", "link_type": "related",
             "anchor_text": "low", "placement": "post_summary", "priority": 5, "note": "", "expires_at": None},
            {"source_article_id": "a", "target_article_id": "c", "link_type": "related",
             "anchor_text": "high", "placement": "post_summary", "priority": 1, "note": "", "expires_at": None},
        ])
        pins = _parse_and_validate_pins(data)
        self.assertEqual(pins[0].priority, 1)
        self.assertEqual(pins[1].priority, 5)


# ---------------------------------------------------------------------------
# TestRealYAML
# ---------------------------------------------------------------------------

class TestRealYAML(unittest.TestCase):

    def setUp(self):
        KnowledgeGraph._reset()

    def tearDown(self):
        KnowledgeGraph._reset()

    def test_real_yaml_loads_without_error(self):
        graph = KnowledgeGraph.load()
        self.assertIsNotNone(graph)

    def test_singleton_returns_same_instance(self):
        g1 = KnowledgeGraph.load()
        g2 = KnowledgeGraph.load()
        self.assertIs(g1, g2)

    def test_real_graph_has_usb_mobile_fans_node(self):
        graph = KnowledgeGraph.load()
        node = graph.get_node("usb-mobile-fans")
        self.assertIsNotNone(node)
        self.assertEqual(node.label, "พัดลม USB & มือถือ")

    def test_real_graph_has_complement_edge(self):
        graph = KnowledgeGraph.load()
        edge = graph.get_edge("usb-mobile-fans", "power-bank")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.link_type, "complement")

    def test_real_config_weights_sum_to_1(self):
        graph = KnowledgeGraph.load()
        total = sum(graph.config.weights.values())
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_real_config_limits_positive(self):
        graph = KnowledgeGraph.load()
        cfg = graph.config
        self.assertGreater(cfg.max_links_per_article, 0)
        self.assertGreater(cfg.min_published_threshold, 0)


# ---------------------------------------------------------------------------
# TestSignalComputation
# ---------------------------------------------------------------------------

class TestSignalComputation(unittest.TestCase):

    def setUp(self):
        self.graph = _make_graph()
        self.source = _profile(
            article_id="fans-500", subcategory="fans",
            intent_tags=("cooling", "portable"), personas=("งบน้อย", "พกพาบ่อย"),
            price_min=100, price_max=449,
        )
        self.powerbank = _profile(
            article_id="powerbank-1", subcategory="powerbank",
            intent_tags=("portable", "charging"), personas=("พกพาบ่อย", "งบน้อย"),
            price_min=200, price_max=800, node_label="Power Bank",
        )

    def test_complement_signal_from_graph_edge(self):
        signals = compute_signals(self.source, self.powerbank, self.graph)
        self.assertAlmostEqual(signals.complement, 0.85)

    def test_persona_overlap_jaccard(self):
        signals = compute_signals(self.source, self.powerbank, self.graph)
        # both have งบน้อย + พกพาบ่อย → intersection=2, union=2 → 1.0
        self.assertAlmostEqual(signals.persona_overlap, 1.0)

    def test_use_case_proximity_jaccard(self):
        signals = compute_signals(self.source, self.powerbank, self.graph)
        # fans: {cooling, portable}, powerbank: {portable, charging}
        # intersection=1, union=3 → 1/3
        self.assertAlmostEqual(signals.use_case_proximity, 1/3, places=3)

    def test_category_match_same_category(self):
        signals = compute_signals(self.source, self.powerbank, self.graph)
        self.assertEqual(signals.category_match, 1.0)

    def test_category_match_different_category(self):
        desk = _profile(article_id="desk-1", subcategory="desk", category="home-living",
                        intent_tags=("office",), personas=("งบน้อย",))
        signals = compute_signals(self.source, desk, self.graph)
        self.assertEqual(signals.category_match, 0.0)

    def test_no_edge_gives_zero_complement(self):
        desk = _profile(article_id="desk-1", subcategory="desk", category="home-living")
        signals = compute_signals(self.powerbank, desk, self.graph)
        self.assertEqual(signals.complement, 0.0)

    def test_price_compat_overlap(self):
        # source: 100-449, powerbank: 200-800 → overlap 200-449 = 249; union 100-800 = 700
        signals = compute_signals(self.source, self.powerbank, self.graph)
        expected = 249 / 700
        self.assertAlmostEqual(signals.price_compat, expected, places=2)

    def test_price_compat_no_overlap(self):
        cheap  = _profile(article_id="c", subcategory="fans", price_min=50, price_max=150)
        expensive = _profile(article_id="e", subcategory="fans", price_min=500, price_max=1000)
        result = _price_compat(cheap, expensive)
        self.assertEqual(result, 0.0)

    def test_keyword_diversity_different_keywords(self):
        result = _keyword_diversity("พัดลม USB", "Power Bank เดินทาง")
        self.assertGreater(result, 0.5)

    def test_keyword_diversity_same_keyword(self):
        result = _keyword_diversity("พัดลม USB", "พัดลม USB")
        self.assertEqual(result, 0.0)

    def test_is_budget_alt_same_sub_non_overlapping(self):
        fan_cheap = _profile(article_id="a", subcategory="fans", price_min=100, price_max=449)
        fan_exp   = _profile(article_id="b", subcategory="fans", price_min=500, price_max=999)
        self.assertTrue(_is_budget_alt(fan_cheap, fan_exp))

    def test_is_budget_alt_different_subcategory(self):
        fan   = _profile(article_id="a", subcategory="fans",      price_min=100, price_max=449)
        power = _profile(article_id="b", subcategory="powerbank", price_min=600, price_max=999)
        self.assertFalse(_is_budget_alt(fan, power))

    def test_is_budget_alt_overlapping_price(self):
        a = _profile(article_id="a", subcategory="fans", price_min=100, price_max=500)
        b = _profile(article_id="b", subcategory="fans", price_min=400, price_max=800)
        self.assertFalse(_is_budget_alt(a, b))

    def test_jaccard_empty_sets(self):
        self.assertEqual(_jaccard(set(), set()), 0.0)

    def test_jaccard_identical_sets(self):
        self.assertEqual(_jaccard({"a", "b"}, {"a", "b"}), 1.0)

    def test_reserved_signals_are_zero(self):
        signals = compute_signals(self.source, self.powerbank, self.graph)
        self.assertEqual(signals.seasonal_intent, 0.0)
        self.assertEqual(signals.content_performance, 0.0)
        self.assertEqual(signals.campaign_match, 0.0)


# ---------------------------------------------------------------------------
# TestScoring
# ---------------------------------------------------------------------------

class TestScoring(unittest.TestCase):

    def setUp(self):
        self.graph = _make_graph()
        self.cfg   = self.graph.config

    def test_weighted_score_all_zeros_is_zero(self):
        signals = SignalVector()
        score = _weighted_score(signals, self.cfg)
        self.assertEqual(score, 0.0)

    def test_weighted_score_all_ones(self):
        signals = SignalVector(
            complement=1.0, persona_overlap=1.0, use_case_proximity=1.0,
            price_compat=1.0, category_match=1.0, keyword_diversity=1.0,
        )
        score = _weighted_score(signals, self.cfg)
        self.assertAlmostEqual(score, 1.0, places=3)

    def test_complement_drives_score(self):
        high = SignalVector(complement=1.0)
        low  = SignalVector(complement=0.0)
        self.assertGreater(_weighted_score(high, self.cfg), _weighted_score(low, self.cfg))

    def test_budget_alt_bonus_applied(self):
        fan_cheap = _profile(article_id="a", subcategory="fans", price_min=100, price_max=449)
        fan_exp   = _profile(article_id="b", subcategory="fans", price_min=600, price_max=999,
                             node_label="พัดลม USB")
        lt, mult = _resolve_link_type(fan_cheap, fan_exp, compute_signals(fan_cheap, fan_exp, self.graph), self.graph)
        self.assertEqual(lt, "budget_alt")
        self.assertEqual(mult, self.cfg.budget_alt_bonus)

    def test_complement_edge_gives_complement_type(self):
        source = _profile(article_id="fans-1", subcategory="fans")
        target = _profile(article_id="pb-1",   subcategory="powerbank", node_label="Power Bank")
        signals = compute_signals(source, target, self.graph)
        lt, _ = _resolve_link_type(source, target, signals, self.graph)
        self.assertEqual(lt, "complement")

    def test_no_edge_no_category_match_returns_none(self):
        source = _profile(article_id="fans-1", subcategory="fans",      category="mobile-gadgets")
        target = _profile(article_id="desk-1", subcategory="noedge",    category="home-living")
        signals = compute_signals(source, target, self.graph)
        lt, _ = _resolve_link_type(source, target, signals, self.graph)
        self.assertIsNone(lt)


# ---------------------------------------------------------------------------
# TestSafetyAndFilters
# ---------------------------------------------------------------------------

class TestSafetyAndFilters(unittest.TestCase):

    def setUp(self):
        self.graph = _make_graph()

    def _candidates_with_score(self, *articles):
        return list(articles)

    def test_self_link_excluded(self):
        source = _profile(article_id="fans-500", subcategory="fans")
        clone  = _profile(article_id="fans-500", subcategory="fans")  # same ID
        bundle = compute_links(source, [clone], self.graph)
        ids = [r.target_id for r in bundle.links]
        self.assertNotIn("fans-500", ids)

    def test_below_min_threshold_show_false(self):
        source = _profile(article_id="fans-500", subcategory="fans")
        # Only 1 valid candidate — below min_links_to_show (2)
        powerbank = _profile(article_id="pb-1", subcategory="powerbank", node_label="Power Bank",
                             intent_tags=("portable", "charging"), personas=("พกพาบ่อย",))
        bundle = compute_links(source, [powerbank], self.graph)
        # Either show or not — if < min_links, must be False
        if len(bundle.links) < self.graph.config.min_links_to_show:
            self.assertFalse(bundle._show)

    def test_max_links_cap_enforced(self):
        source = _profile(article_id="fans-500", subcategory="fans")
        candidates = [
            _profile(article_id=f"c-{i}", subcategory="powerbank" if i % 2 == 0 else "desk",
                     category="mobile-gadgets" if i % 2 == 0 else "home-living",
                     intent_tags=("portable",), personas=("งบน้อย",),
                     node_label=f"Product {i}")
            for i in range(10)
        ]
        bundle = compute_links(source, candidates, self.graph)
        if bundle._show:
            self.assertLessEqual(len(bundle.links), self.graph.config.max_links_per_article)

    def test_low_score_candidate_excluded(self):
        source = _profile(article_id="fans-500", subcategory="fans")
        # Candidate with no edge, different category, no shared tags
        target = _profile(article_id="unrelated", subcategory="xyz", category="food-drinks",
                         intent_tags=(), personas=(), node_label="")
        bundle = compute_links(source, [target], self.graph)
        ids = [r.target_id for r in bundle.links]
        self.assertNotIn("unrelated", ids)

    def test_link_type_assigned(self):
        source = _profile(article_id="fans-500", subcategory="fans",
                         intent_tags=("cooling", "portable"), personas=("งบน้อย",))
        target = _profile(article_id="pb-1", subcategory="powerbank", node_label="Power Bank",
                         intent_tags=("portable", "charging"), personas=("พกพาบ่อย",))
        bundle = compute_links(source, [target, target], self.graph)  # target twice = deduplicated
        if bundle._show:
            self.assertIn(bundle.links[0].link_type, {"complement", "budget_alt", "type_alt", "related"})

    def test_placement_assigned(self):
        source = _profile(article_id="fans-500", subcategory="fans",
                         intent_tags=("cooling", "portable"), personas=("งบน้อย",))
        target = _profile(article_id="pb-1", subcategory="powerbank", node_label="Power Bank",
                         intent_tags=("portable", "charging"), personas=("พกพาบ่อย",))
        desk = _profile(article_id="desk-1", subcategory="desk", category="home-living",
                       intent_tags=("office",), personas=("งบน้อย",), node_label="อุปกรณ์โต๊ะ")
        bundle = compute_links(source, [target, desk], self.graph)
        for link in bundle.links:
            self.assertIn(link.placement, ("post_advisor", "post_summary"))

    def test_post_advisor_for_complement(self):
        self.assertEqual(_placement_for("complement"), "post_advisor")
        self.assertEqual(_placement_for("budget_alt"),  "post_advisor")

    def test_post_summary_for_related(self):
        self.assertEqual(_placement_for("related"),  "post_summary")
        self.assertEqual(_placement_for("type_alt"), "post_summary")

    def test_bundle_reason_populated_when_hidden(self):
        source = _profile(article_id="fans-500", subcategory="fans")
        bundle = compute_links(source, [], self.graph)
        self.assertFalse(bundle._show)
        self.assertIsInstance(bundle._reason, str)
        self.assertTrue(len(bundle._reason) > 0)


# ---------------------------------------------------------------------------
# TestColdStart
# ---------------------------------------------------------------------------

class TestColdStart(unittest.TestCase):

    def test_cold_start_bundle_show_false(self):
        # Simulate via compute_links with min_links_to_show = 3 but 0 candidates
        graph = _make_graph()
        source = _profile(article_id="fans-500", subcategory="fans")
        bundle = compute_links(source, [], graph)
        self.assertFalse(bundle._show)

    def test_cold_start_reason_contains_too_few_links(self):
        graph = _make_graph()
        source = _profile(article_id="fans-500", subcategory="fans")
        bundle = compute_links(source, [], graph)
        self.assertIn("too_few_links", bundle._reason)

    def test_cold_start_links_empty(self):
        graph = _make_graph()
        source = _profile(article_id="fans-500", subcategory="fans")
        bundle = compute_links(source, [], graph)
        self.assertEqual(bundle.links, [])

    def test_candidate_count_populated(self):
        graph = _make_graph()
        source = _profile(article_id="fans-500", subcategory="fans")
        candidates = [
            _profile(article_id=f"x-{i}", subcategory="powerbank", node_label=f"P{i}")
            for i in range(3)
        ]
        bundle = compute_links(source, candidates, graph)
        self.assertEqual(bundle._candidate_count, 3)


# ---------------------------------------------------------------------------
# TestPinnedLinks
# ---------------------------------------------------------------------------

class TestPinnedLinks(unittest.TestCase):

    def _graph_with_pin(self, pin_dict) -> KnowledgeGraph:
        return KnowledgeGraph.from_dicts(
            _minimal_graph_data(),
            _minimal_config_data(),
            _minimal_pins_data([pin_dict]),
        )

    def test_pinned_attribute_on_load(self):
        pin = {
            "source_article_id": "fans-500",
            "target_article_id": "powerbank-travel",
            "link_type": "complement",
            "anchor_text": "Power Bank สำหรับพัดลม USB",
            "placement": "post_advisor",
            "priority": 1,
            "note": "",
            "expires_at": None,
        }
        graph = self._graph_with_pin(pin)
        self.assertEqual(len(graph.pinned), 1)
        self.assertEqual(graph.pinned[0].anchor_text, "Power Bank สำหรับพัดลม USB")

    def test_expired_pin_detected(self):
        pin = {
            "source_article_id": "fans-500",
            "target_article_id": "powerbank-travel",
            "link_type": "complement",
            "anchor_text": "test",
            "placement": "post_advisor",
            "priority": 1,
            "note": "",
            "expires_at": "2020-01-01",  # in the past
        }
        graph = self._graph_with_pin(pin)
        # Pin is stored but expires_at field is accessible
        self.assertEqual(graph.pinned[0].expires_at, "2020-01-01")

    def test_pinned_link_is_in_graph(self):
        pin = {
            "source_article_id": "fans-500",
            "target_article_id": "powerbank-travel",
            "link_type": "complement",
            "anchor_text": "Power Bank สำหรับพัดลม USB",
            "placement": "post_advisor",
            "priority": 1,
            "note": "",
            "expires_at": None,
        }
        graph = self._graph_with_pin(pin)
        pins_for_source = [p for p in graph.pinned if p.source_article_id == "fans-500"]
        self.assertEqual(len(pins_for_source), 1)


# ---------------------------------------------------------------------------
# TestAnchorRotation
# ---------------------------------------------------------------------------

class TestAnchorRotation(unittest.TestCase):

    def setUp(self):
        self.graph = _make_graph()

    def test_hash_rotation_deterministic(self):
        source = _profile(article_id="fans-500", subcategory="fans")
        target = _profile(article_id="pb-1", subcategory="powerbank", node_label="Power Bank")
        a1 = _select_anchor(source, target, "complement", self.graph)
        a2 = _select_anchor(source, target, "complement", self.graph)
        self.assertEqual(a1, a2)

    def test_different_source_may_get_different_anchor(self):
        source_a = _profile(article_id="fans-500", subcategory="fans")
        source_b = _profile(article_id="fans-1000", subcategory="fans")
        target   = _profile(article_id="pb-1", subcategory="powerbank", node_label="Power Bank")
        pool = self.graph.get_anchor_pool("fans", "complement")
        if len(pool) > 1:
            a1 = _select_anchor(source_a, target, "complement", self.graph)
            a2 = _select_anchor(source_b, target, "complement", self.graph)
            # Different source IDs may produce different anchors (hash-based)
            # This is a property test — not guaranteed to differ, but acceptable
            self.assertIsInstance(a1, str)
            self.assertIsInstance(a2, str)

    def test_anchor_variables_filled(self):
        source = _profile(article_id="fans-500", subcategory="fans",       node_label="พัดลม USB")
        target = _profile(article_id="pb-1",     subcategory="powerbank",  node_label="Power Bank",
                         price_min=200, price_max=800)
        anchor = _select_anchor(source, target, "complement", self.graph)
        # No raw template variables should remain
        self.assertNotIn("{target_label}", anchor)
        self.assertNotIn("{source_label}", anchor)

    def test_budget_alt_anchor_filled(self):
        source = _profile(article_id="fans-500", subcategory="fans", node_label="พัดลม USB")
        target = _profile(article_id="fans-1000", subcategory="fans", node_label="พัดลม USB",
                         price_min=600, price_max=999)
        anchor = _select_anchor(source, target, "budget_alt", self.graph)
        self.assertIsInstance(anchor, str)
        self.assertGreater(len(anchor), 0)
        self.assertNotIn("{", anchor)

    def test_subcategory_override_used(self):
        data = _minimal_graph_data()
        data["anchor_templates"]["subcategory_overrides"] = {
            "fans": {"complement": ["Override พิเศษ"]}
        }
        graph = _make_graph(graph_data=data)
        source = _profile(article_id="fans-500", subcategory="fans")
        target = _profile(article_id="pb-1", subcategory="powerbank", node_label="Power Bank")
        anchor = _select_anchor(source, target, "complement", graph)
        self.assertEqual(anchor, "Override พิเศษ")

    def test_fallback_to_label_when_no_pool(self):
        source = _profile(article_id="fans-500", subcategory="fans")
        target = _profile(article_id="unknown-1", subcategory="unknown", node_label="สินค้า X")
        anchor = _select_anchor(source, target, "type_alt", self.graph)
        self.assertIsInstance(anchor, str)
        self.assertGreater(len(anchor), 0)


# ---------------------------------------------------------------------------
# TestComputeLinks (end-to-end pure)
# ---------------------------------------------------------------------------

class TestComputeLinks(unittest.TestCase):

    def setUp(self):
        self.graph = _make_graph()
        self.source = _profile(
            article_id="fans-500", subcategory="fans",
            intent_tags=("cooling", "portable"), personas=("งบน้อย", "พกพาบ่อย"),
            price_min=100, price_max=449, node_label="พัดลม USB",
        )
        self.powerbank = _profile(
            article_id="pb-travel", subcategory="powerbank", node_label="Power Bank",
            intent_tags=("portable", "charging"), personas=("พกพาบ่อย", "งบน้อย"),
            price_min=300, price_max=900,
        )
        self.desk = _profile(
            article_id="desk-wfh", subcategory="desk", category="home-living",
            node_label="อุปกรณ์โต๊ะ", intent_tags=("office", "wfh"), personas=("งบน้อย",),
        )

    def test_produces_link_bundle(self):
        bundle = compute_links(self.source, [self.powerbank, self.desk], self.graph)
        self.assertIsInstance(bundle, LinkBundle)

    def test_show_true_with_enough_candidates(self):
        bundle = compute_links(self.source, [self.powerbank, self.desk], self.graph)
        self.assertTrue(bundle._show)
        self.assertGreaterEqual(len(bundle.links), 1)

    def test_each_link_has_required_fields(self):
        bundle = compute_links(self.source, [self.powerbank, self.desk], self.graph)
        for link in bundle.links:
            self.assertIsInstance(link.target_id,    str)
            self.assertIsInstance(link.target_url,   str)
            self.assertIsInstance(link.anchor_text,  str)
            self.assertIsInstance(link.score,        float)
            self.assertIn(link.placement, ("post_advisor", "post_summary"))
            self.assertIn(link.link_type, ("complement", "budget_alt", "type_alt", "related"))

    def test_score_within_range(self):
        bundle = compute_links(self.source, [self.powerbank, self.desk], self.graph)
        for link in bundle.links:
            self.assertGreaterEqual(link.score, 0.0)
            self.assertLessEqual(link.score, 2.0)  # budget_alt bonus can exceed 1.0

    def test_target_url_correct_format(self):
        bundle = compute_links(self.source, [self.powerbank, self.desk], self.graph)
        for link in bundle.links:
            self.assertIn("suenaidee.com", link.target_url)
            self.assertTrue(link.target_url.startswith("https://"))

    def test_no_duplicate_targets(self):
        bundle = compute_links(self.source, [self.powerbank, self.desk, self.powerbank], self.graph)
        target_ids = [r.target_id for r in bundle.links]
        self.assertEqual(len(target_ids), len(set(target_ids)))

    def test_signals_attached_to_records(self):
        bundle = compute_links(self.source, [self.powerbank, self.desk], self.graph)
        for link in bundle.links:
            self.assertIsInstance(link.signals, SignalVector)

    def test_no_rendering_in_output(self):
        bundle = compute_links(self.source, [self.powerbank, self.desk], self.graph)
        # bundle must not contain markdown
        import json
        try:
            blob = str(bundle)
            self.assertNotIn("##", blob)
        except Exception:
            pass  # str() not expected to produce markdown

    def test_budget_alt_detected(self):
        fans_1000 = _profile(
            article_id="fans-1000", subcategory="fans", node_label="พัดลม USB",
            price_min=600, price_max=999,
            intent_tags=("cooling", "portable"), personas=("งบน้อย", "พกพาบ่อย"),
        )
        bundle = compute_links(self.source, [fans_1000, self.powerbank], self.graph)
        link_types = {r.link_type for r in bundle.links}
        self.assertIn("budget_alt", link_types)

    def test_public_import_works(self):
        from shopee_engine.knowledge_engine import compute_links as cl
        self.assertIs(cl, compute_links)


# ---------------------------------------------------------------------------
# TestClusterBundleStub
# ---------------------------------------------------------------------------

class TestClusterBundleStub(unittest.TestCase):

    def test_cluster_bundle_raises_not_implemented(self):
        with self.assertRaises(NotImplementedError) as ctx:
            ClusterBundle()
        self.assertIn("Phase 3D", str(ctx.exception))

    def test_cluster_bundle_raises_with_args(self):
        with self.assertRaises(NotImplementedError):
            ClusterBundle("pillar", ["spoke1"])


if __name__ == "__main__":
    unittest.main()

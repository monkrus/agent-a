"""Tests for Phase 2 journey checks: search, checkout, navigation, comparison."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import scorers
from browser_agent import _product_name_from_url, _homepage_url


# ---- Helper tests -----------------------------------------------------------

class TestProductNameFromUrl:
    def test_shopify_url(self):
        url = "https://skims.com/products/fits-everybody-t-shirt-bra-onyx"
        assert _product_name_from_url(url) == "fits everybody t shirt bra onyx"

    def test_url_with_trailing_slash(self):
        url = "https://example.com/products/widget/"
        assert _product_name_from_url(url) == "widget"

    def test_url_with_html_extension(self):
        url = "https://example.com/product/cool-gadget.html"
        assert _product_name_from_url(url) == "cool gadget"

    def test_underscored_slug(self):
        url = "https://example.com/products/blue_sneakers"
        assert _product_name_from_url(url) == "blue sneakers"


class TestHomepageUrl:
    def test_product_url(self):
        assert _homepage_url("https://skims.com/products/bra-onyx") == "https://skims.com"

    def test_already_homepage(self):
        assert _homepage_url("https://example.com/") == "https://example.com"

    def test_with_port(self):
        assert _homepage_url("http://localhost:5000/products/x") == "http://localhost:5000"


# ---- BROWSER dispatch table ------------------------------------------------

class TestBrowserDispatch:
    def test_all_browser_checks_registered(self):
        expected = {"add_to_cart_flow", "search_discovery", "checkout_reachable",
                    "homepage_to_product", "compare_products"}
        assert set(scorers.BROWSER.keys()) == expected

    def test_dispatch_unknown_detect(self):
        page = {"url": "https://example.com/products/x"}
        r = scorers.run_browser({"detect": "nonexistent"}, page)
        assert r["verdict"] == "UNKNOWN"

    def test_dispatch_no_url(self):
        page = {"url": ""}
        r = scorers.run_browser({"detect": "search_discovery"}, page)
        assert r["verdict"] == "UNKNOWN"


# ---- YAML integration ------------------------------------------------------

class TestYamlIntegration:
    def test_all_browser_detects_in_yaml(self):
        """Every browser detect in the YAML maps to a BROWSER dispatch entry."""
        import yaml
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        data = yaml.safe_load(yaml_path.read_text())
        browser_checks = [c for c in data["checks"] if c["type"] == "browser"]
        for c in browser_checks:
            assert c["detect"] in scorers.BROWSER, \
                f"Browser check {c['id']} detect={c['detect']} not in BROWSER dispatch"

    def test_browser_check_count(self):
        import yaml
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        data = yaml.safe_load(yaml_path.read_text())
        browser_checks = [c for c in data["checks"] if c["type"] == "browser"]
        assert len(browser_checks) == 5

    def test_check_ids_unique(self):
        import yaml
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        data = yaml.safe_load(yaml_path.read_text())
        ids = [c["id"] for c in data["checks"]]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[i for i in ids if ids.count(i) > 1]}"

    def test_new_checks_have_categories(self):
        import yaml
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        data = yaml.safe_load(yaml_path.read_text())
        new_ids = {"RDY-018", "RDY-019", "RDY-020", "RDY-021"}
        for c in data["checks"]:
            if c["id"] in new_ids:
                assert "category" in c, f"{c['id']} missing category"
                assert "severity_if_fail" in c, f"{c['id']} missing severity"
                assert "detect" in c, f"{c['id']} missing detect"

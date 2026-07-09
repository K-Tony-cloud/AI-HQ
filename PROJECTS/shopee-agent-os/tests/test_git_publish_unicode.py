"""Regression tests: Unicode/Thai filename handling in git_publish_service.

Coverage:
  - _git_staged_files() splits on NUL and filters empty strings
  - Thai Unicode filename passes _verify_staged_allowlist
  - Octal-escaped path (old behaviour) would have failed allowlist
  - Non-article file is still blocked by allowlist
  - .env file is still blocked by allowlist
"""
from __future__ import annotations

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_git_result(stdout: str) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    return m


# ---------------------------------------------------------------------------
# Tests: _git_staged_files
# ---------------------------------------------------------------------------

class TestGitStagedFiles:

    def test_nul_delimited_returns_unicode_paths(self):
        from shopee_engine.git_publish_service import _git_staged_files
        thai_path = "PROJECTS/seo-website/src/content/articles/พัดลมพกพา-review.md"
        nul_output = thai_path + "\0"
        with patch("shopee_engine.git_publish_service._git", return_value=_make_git_result(nul_output)):
            result = _git_staged_files()
        assert result == [thai_path]

    def test_multiple_paths_split_correctly(self):
        from shopee_engine.git_publish_service import _git_staged_files
        paths = [
            "PROJECTS/seo-website/src/content/articles/test1.md",
            "PROJECTS/seo-website/src/content/articles/ไม่เกิน-500-บาท.md",
        ]
        nul_output = "\0".join(paths) + "\0"
        with patch("shopee_engine.git_publish_service._git", return_value=_make_git_result(nul_output)):
            result = _git_staged_files()
        assert result == paths

    def test_empty_output_returns_empty_list(self):
        from shopee_engine.git_publish_service import _git_staged_files
        with patch("shopee_engine.git_publish_service._git", return_value=_make_git_result("")):
            result = _git_staged_files()
        assert result == []

    def test_trailing_nul_not_included(self):
        from shopee_engine.git_publish_service import _git_staged_files
        path = "PROJECTS/seo-website/src/content/articles/a.md"
        with patch("shopee_engine.git_publish_service._git", return_value=_make_git_result(path + "\0")):
            result = _git_staged_files()
        assert result == [path]
        assert "" not in result


# ---------------------------------------------------------------------------
# Tests: _verify_staged_allowlist
# ---------------------------------------------------------------------------

class TestVerifyStagedAllowlist:

    def test_thai_unicode_article_path_passes(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        thai_path = "PROJECTS/seo-website/src/content/articles/ไม่เกิน-500-บาท.md"
        bad = _verify_staged_allowlist([thai_path])
        assert bad == [], f"Expected no violations, got: {bad}"

    def test_ascii_article_path_passes(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        path = "PROJECTS/seo-website/src/content/articles/best-fans-under-500.md"
        bad = _verify_staged_allowlist([path])
        assert bad == []

    def test_octal_escaped_thai_path_would_be_blocked(self):
        """Old behaviour: git returns octal-escaped path starting with '"'.
        The allowlist should (correctly) block it since it doesn't start with the expected prefix."""
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        # Simulate old octal-escaped string as git would return in text mode
        octal_escaped = '"PROJECTS/seo-website/src/content/articles/\\340\\271\\204\\340\\270\\241.md"'
        bad = _verify_staged_allowlist([octal_escaped])
        # This would have been the false positive before the fix — now we confirm
        # the allowlist does reject anything starting with '"' (the old bug scenario)
        assert bad == [octal_escaped], "Octal-escaped path should fail allowlist (it has a leading quote)"

    def test_env_file_is_blocked(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        bad = _verify_staged_allowlist(["PROJECTS/shopee-agent-os/.env"])
        assert bad == ["PROJECTS/shopee-agent-os/.env"]

    def test_non_article_file_is_blocked(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        bad = _verify_staged_allowlist(["PROJECTS/shopee-agent-os/shopee_engine/seo_engine.py"])
        assert len(bad) == 1

    def test_mixed_good_and_bad_returns_only_bad(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        good = "PROJECTS/seo-website/src/content/articles/review.md"
        bad_file = "PROJECTS/shopee-agent-os/.env"
        bad = _verify_staged_allowlist([good, bad_file])
        assert bad == [bad_file]

    def test_empty_list_passes(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        bad = _verify_staged_allowlist([])
        assert bad == []


# ---------------------------------------------------------------------------
# Tests: _git invocation uses correct flags
# ---------------------------------------------------------------------------

class TestGitStagedFilesInvocation:

    def test_uses_core_quotepath_false_and_z_flag(self):
        """_git_staged_files must call _git with core.quotepath=false and -z."""
        from shopee_engine.git_publish_service import _git_staged_files
        with patch("shopee_engine.git_publish_service._git", return_value=_make_git_result("")) as mock_git:
            _git_staged_files()
        call_args = mock_git.call_args[0]
        assert "-c" in call_args
        assert "core.quotepath=false" in call_args
        assert "-z" in call_args
        assert "--name-only" in call_args
        assert "--cached" in call_args


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

"""Safe Git publish service for SEO articles.

All git and npm operations go through here.  Nothing is committed or pushed
until every pre-flight check passes.

Environment variables (set in .env):
    SEO_PUBLISH_ENABLED   — "true" enables real commit+push (default: false → dry-run)
    SEO_GIT_REMOTE        — remote name (default: origin)
    SEO_GIT_BRANCH        — branch to push to (default: main)
    SEO_SITE_PATH         — absolute path to seo-website directory
    SITE_URL              — canonical base URL for the site
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path

from shopee_engine.article_exporter import (
    delete_article_file,
    export_article,
    get_articles_dir,
    get_dist_dir,
    get_site_path,
)
from shopee_engine.seo_engine import (
    SEO_ARTICLES_TABLE,
    _connect,
    _init_seo_tables,
    refresh_article_products,
    update_article_status,
    validate_article_for_publish,
    validate_status_transition,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _seo_env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def is_publish_enabled() -> bool:
    return _seo_env("SEO_PUBLISH_ENABLED", "false").lower() == "true"


def get_git_remote() -> str:
    return _seo_env("SEO_GIT_REMOTE", "origin")


def get_git_branch() -> str:
    return _seo_env("SEO_GIT_BRANCH", "main")


# ---------------------------------------------------------------------------
# Concurrency lock (thread + file level)
# ---------------------------------------------------------------------------

_THREAD_LOCK = threading.Lock()
_LOCK_FILE   = Path(tempfile.gettempdir()) / "seo_publish.lock"


class _PublishLock:
    """Context manager that acquires both a threading lock and a file lock."""

    def __enter__(self) -> "_PublishLock":
        if not _THREAD_LOCK.acquire(blocking=False):
            raise RuntimeError("Another publish operation is in progress (thread lock)")
        try:
            self._fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            _THREAD_LOCK.release()
            raise RuntimeError("Another publish operation is in progress (file lock)")
        return self

    def __exit__(self, *_) -> None:
        try:
            os.close(self._fd)
            _LOCK_FILE.unlink(missing_ok=True)
        finally:
            _THREAD_LOCK.release()


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_root() -> Path:
    """Return the monorepo git root."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a git command; raises RuntimeError on non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd or _git_root()),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed:\n{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def check_git_environment() -> dict:
    """Verify git branch, remote, and working tree before publishing.

    Returns {ok: bool, branch: str, remote: str, errors: list[str], warnings: list[str]}
    """
    errors: list[str]   = []
    warnings: list[str] = []
    expected_branch = get_git_branch()
    expected_remote = get_git_remote()

    # Current branch
    try:
        result  = _git("branch", "--show-current")
        current = result.stdout.strip()
        if current != expected_branch:
            errors.append(
                f"Wrong branch: expected '{expected_branch}', on '{current}'"
            )
    except RuntimeError as e:
        errors.append(f"Cannot determine branch: {e}")
        current = ""

    # Remote exists
    try:
        _git("remote", "get-url", expected_remote)
    except RuntimeError:
        errors.append(f"Remote '{expected_remote}' not found")

    # Pre-existing staged changes (would contaminate our commit)
    try:
        staged_files = _git_staged_files()
        if staged_files:
            errors.append(
                "Staging area is not clean — commit or unstage existing changes first:\n"
                + "\n".join(staged_files)[:500]
            )
    except RuntimeError as e:
        warnings.append(f"Could not check staged changes: {e}")

    return {
        "ok":      len(errors) == 0,
        "branch":  current,
        "remote":  expected_remote,
        "errors":  errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Allowlist for staging
# ---------------------------------------------------------------------------

_ARTICLES_REL = "PROJECTS/seo-website/src/content/articles"


def _git_staged_files() -> list[str]:
    """Return currently staged file paths as proper Unicode strings.

    Uses -z (NUL-delimited output) and core.quotepath=false so that
    non-ASCII filenames (Thai, CJK, etc.) are returned as real UTF-8
    strings rather than octal-escaped sequences like \\340\\271\\204.
    """
    result = _git("-c", "core.quotepath=false", "diff", "--cached", "--name-only", "-z")
    return [f for f in result.stdout.split("\0") if f]


def _verify_staged_allowlist(staged_files: list[str]) -> list[str]:
    """Return list of files that are outside the allowed staging paths.

    Expects paths as proper Unicode strings (not octal-escaped).
    """
    bad = []
    for f in staged_files:
        if not f.startswith(_ARTICLES_REL):
            bad.append(f)
    return bad


# ---------------------------------------------------------------------------
# npm build
# ---------------------------------------------------------------------------

def run_astro_build() -> dict:
    """Run npm run build in seo-website. Returns {success, output, error}."""
    site_path = get_site_path()
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(site_path),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        return {
            "success": False,
            "output":  (result.stdout + result.stderr)[:2000],
            "error":   "npm run build failed",
        }
    return {
        "success": True,
        "output":  result.stdout[-1000:],
        "error":   None,
    }


def verify_article_in_build(article_id: str) -> dict:
    """Check that the article's page was generated in dist/.

    Returns {success, page_path, in_sitemap, error}
    """
    dist = get_dist_dir()
    page = dist / article_id / "index.html"

    if not page.exists():
        return {
            "success":    False,
            "page_path":  str(page),
            "in_sitemap": False,
            "error":      f"Built page not found: {page}",
        }

    # Check sitemap
    in_sitemap = False
    for sm in dist.glob("sitemap*.xml"):
        try:
            if f"/{article_id}/" in sm.read_text(encoding="utf-8"):
                in_sitemap = True
                break
        except OSError:
            pass

    return {
        "success":    True,
        "page_path":  str(page),
        "in_sitemap": in_sitemap,
        "error":      None,
    }


# ---------------------------------------------------------------------------
# DB status updaters
# ---------------------------------------------------------------------------

def _mark_published(article_id: str, commit_hash: str, file_path: str) -> None:
    con = _connect(read_only=False)
    try:
        _init_seo_tables(con)
        con.execute(f"""
            UPDATE {SEO_ARTICLES_TABLE}
            SET status          = 'published',
                published_at    = CURRENT_TIMESTAMP,
                git_commit_hash = ?,
                published_path  = ?,
                updated_at      = CURRENT_TIMESTAMP
            WHERE article_id = ?
        """, [commit_hash, file_path, article_id])
        con.close()
    except Exception:
        con.close()
        raise


def _mark_unpublished(article_id: str) -> None:
    con = _connect(read_only=False)
    try:
        _init_seo_tables(con)
        con.execute(f"""
            UPDATE {SEO_ARTICLES_TABLE}
            SET status = 'reviewed', updated_at = CURRENT_TIMESTAMP
            WHERE article_id = ?
        """, [article_id])
        con.close()
    except Exception:
        con.close()
        raise


# ---------------------------------------------------------------------------
# Safe publish pipeline
# ---------------------------------------------------------------------------

def safe_publish(article_id: str) -> dict:
    """Full publish pipeline for one article.

    Steps: lock → env check → load article → validate → export → build →
           verify → (dry-run exit OR git commit/push) → update DB status.

    SEO_PUBLISH_ENABLED=false: runs all steps up to (and including) build,
    then cleans up the exported file and returns a dry-run summary without
    committing, pushing, or changing the DB status.

    Returns a rich dict suitable for the Discord embed builder.
    """
    published_enabled = is_publish_enabled()

    try:
        lock_ctx = _PublishLock()
        lock_ctx.__enter__()
    except RuntimeError as e:
        return _pub_err(article_id, str(e))

    exported_path: str | None = None

    try:
        # 1. Git environment check
        env = check_git_environment()
        if not env["ok"]:
            return _pub_err(article_id, "Git environment check failed: " + "; ".join(env["errors"]))

        # 2. Load article and verify status
        con = _connect(read_only=True)
        try:
            row = con.execute(
                f"SELECT status FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
            ).fetchone()
            con.close()
        except Exception as exc:
            con.close()
            return _pub_err(article_id, str(exc))

        if not row:
            return _pub_err(article_id, f"Article '{article_id}' not found")

        current_status = row[0]
        trans = validate_status_transition(current_status, "published")
        if not trans["valid"]:
            return _pub_err(article_id, trans["error"])

        # 3. Pre-publish validation
        val = validate_article_for_publish(article_id)
        if not val["valid"]:
            return _pub_err(
                article_id,
                "Pre-publish validation failed: " + "; ".join(val["errors"]),
                warnings=val.get("warnings", []),
            )

        # 4. Export to Markdown
        export_result = export_article(article_id, as_status="published")
        if not export_result["success"]:
            return _pub_err(article_id, "Export failed: " + export_result["error"])

        exported_path = export_result["file_path"]

        # 5. Astro build
        build_result = run_astro_build()
        if not build_result["success"]:
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, "Astro build failed: " + build_result["error"],
                            build_output=build_result["output"])

        # 6. Verify article in built output
        verify = verify_article_in_build(article_id)
        if not verify["success"]:
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, verify["error"])

        # ── DRY-RUN EXIT ─────────────────────────────────────────────────────
        if not published_enabled:
            delete_article_file(article_id)
            exported_path = None
            return {
                "success":    True,
                "dry_run":    True,
                "article_id": article_id,
                "commit_hash": None,
                "pushed":     False,
                "page_url":   None,
                "warnings":   val.get("warnings", []),
                "in_sitemap": verify.get("in_sitemap", False),
                "message":    (
                    "Dry-run: validation ✅, export ✅, build ✅, page ✅ — "
                    "SEO_PUBLISH_ENABLED=false → no commit/push"
                ),
            }

        # 7. Git commit (only the article file)
        rel_path = Path(exported_path).relative_to(_git_root()).as_posix()
        try:
            _git("add", rel_path)
        except RuntimeError as e:
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, f"git add failed: {e}")

        # Verify staged allowlist
        staged_files = _git_staged_files()
        bad_files    = _verify_staged_allowlist(staged_files)
        if bad_files:
            _git("reset", "HEAD", rel_path)
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(
                article_id,
                "Staged allowlist violation — unexpected files staged: " + ", ".join(bad_files),
            )

        commit_msg = f"seo: publish article {article_id}"
        try:
            _git("commit", "-m", commit_msg)
        except RuntimeError as e:
            # Commit failed — unstage and clean up
            try:
                _git("reset", "HEAD", rel_path)
            except RuntimeError:
                pass
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, f"git commit failed: {e}")

        # Capture commit hash
        commit_hash = _git("rev-parse", "HEAD").stdout.strip()

        # 8. Git push
        try:
            _git("push", get_git_remote(), get_git_branch())
        except RuntimeError as e:
            # Push failed — commit exists locally, do NOT delete file or reset
            return {
                "success":     False,
                "dry_run":     False,
                "article_id":  article_id,
                "commit_hash": commit_hash,
                "pushed":      False,
                "page_url":    None,
                "warnings":    val.get("warnings", []),
                "error": (
                    f"git push failed — commit {commit_hash[:8]} exists locally. "
                    f"Run `git push {get_git_remote()} {get_git_branch()}` to retry. "
                    f"DB status remains 'reviewed'. Original error: {e}"
                ),
            }

        # 9. Update DB status after successful push
        from shopee_engine.article_exporter import get_site_url
        try:
            site_url = get_site_url()
            page_url = f"{site_url}/{article_id}/"
        except ValueError:
            page_url = None

        _mark_published(article_id, commit_hash, rel_path)

        return {
            "success":    True,
            "dry_run":    False,
            "article_id": article_id,
            "commit_hash": commit_hash,
            "pushed":     True,
            "page_url":   page_url,
            "warnings":   val.get("warnings", []),
            "in_sitemap": verify.get("in_sitemap", False),
            "message":    f"Published: {page_url or article_id}",
        }

    finally:
        lock_ctx.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Safe republish pipeline (published articles only, preserves published_at)
# ---------------------------------------------------------------------------

def _mark_republished(article_id: str, commit_hash: str, file_path: str) -> None:
    """Update git metadata and updated_at; published_at is intentionally NOT changed."""
    con = _connect(read_only=False)
    try:
        _init_seo_tables(con)
        con.execute(f"""
            UPDATE {SEO_ARTICLES_TABLE}
            SET git_commit_hash = ?,
                published_path  = ?,
                updated_at      = CURRENT_TIMESTAMP
            WHERE article_id = ?
        """, [commit_hash, file_path, article_id])
        con.close()
    except Exception:
        con.close()
        raise


def safe_republish(article_id: str) -> dict:
    """Re-publish a published article after content edits.

    Differences from safe_publish:
    - Requires status == 'published' (not 'reviewed').
    - Preserves original published_at; only updates git_commit_hash and updated_at.
    - Git commit message uses 'republish' prefix.
    """
    published_enabled = is_publish_enabled()

    try:
        lock_ctx = _PublishLock()
        lock_ctx.__enter__()
    except RuntimeError as e:
        return _pub_err(article_id, str(e))

    exported_path: str | None = None

    try:
        # 1. Git environment
        env = check_git_environment()
        if not env["ok"]:
            return _pub_err(article_id, "Git environment check failed: " + "; ".join(env["errors"]))

        # 2. Verify article is published
        con = _connect(read_only=True)
        try:
            row = con.execute(
                f"SELECT status, published_at FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
                [article_id],
            ).fetchone()
            con.close()
        except Exception as exc:
            con.close()
            return _pub_err(article_id, str(exc))

        if not row:
            return _pub_err(article_id, f"Article '{article_id}' not found")

        current_status, original_published_at = row[0], row[1]
        if current_status != "published":
            return _pub_err(
                article_id,
                f"/seo-republish ใช้ได้เฉพาะบทความ status 'published' "
                f"(ปัจจุบัน: '{current_status}'). "
                f"สำหรับบทความ draft/reviewed ให้ใช้ /seo-publish แทน",
            )

        # 3. Pre-publish validation — filter out the status=='reviewed' error since we ARE published
        val = validate_article_for_publish(article_id)
        real_errors = [e for e in val["errors"] if "must be 'reviewed'" not in e]
        if real_errors:
            return _pub_err(article_id,
                            "Pre-publish validation failed: " + "; ".join(real_errors),
                            warnings=val.get("warnings", []))

        # 4. Export — pass original published_at so frontmatter retains it
        pub_ts = str(original_published_at) if original_published_at else None
        export_result = export_article(article_id, as_status="published", published_at=pub_ts)
        if not export_result["success"]:
            return _pub_err(article_id, "Export failed: " + export_result["error"])
        exported_path = export_result["file_path"]

        # 5. Astro build
        build_result = run_astro_build()
        if not build_result["success"]:
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, "Astro build failed: " + build_result["error"])

        # 6. Verify
        verify = verify_article_in_build(article_id)
        if not verify["success"]:
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, verify["error"])

        # ── DRY-RUN EXIT ────────────────────────────────────────────────────
        if not published_enabled:
            delete_article_file(article_id)
            exported_path = None
            return {
                "success":     True,
                "dry_run":     True,
                "republished": True,
                "article_id":  article_id,
                "commit_hash": None,
                "pushed":      False,
                "page_url":    None,
                "warnings":    val.get("warnings", []),
                "in_sitemap":  verify.get("in_sitemap", False),
                "message": (
                    "Dry-run republish: validation ✅, export ✅, build ✅, page ✅ — "
                    "SEO_PUBLISH_ENABLED=false → no commit/push"
                ),
            }

        # 7. Git commit
        rel_path = Path(exported_path).relative_to(_git_root()).as_posix()
        try:
            _git("add", rel_path)
        except RuntimeError as e:
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, f"git add failed: {e}")

        staged_files = _git_staged_files()
        bad_files    = _verify_staged_allowlist(staged_files)
        if bad_files:
            _git("reset", "HEAD", rel_path)
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, "Staged allowlist violation: " + ", ".join(bad_files))

        commit_msg = f"seo: republish article {article_id}"
        try:
            _git("commit", "-m", commit_msg)
        except RuntimeError as e:
            try:
                _git("reset", "HEAD", rel_path)
            except RuntimeError:
                pass
            delete_article_file(article_id)
            exported_path = None
            return _pub_err(article_id, f"git commit failed: {e}")

        commit_hash = _git("rev-parse", "HEAD").stdout.strip()

        # 8. Git push
        try:
            _git("push", get_git_remote(), get_git_branch())
        except RuntimeError as e:
            return {
                "success":     False,
                "dry_run":     False,
                "republished": True,
                "article_id":  article_id,
                "commit_hash": commit_hash,
                "pushed":      False,
                "page_url":    None,
                "warnings":    val.get("warnings", []),
                "error": (
                    f"git push failed — commit {commit_hash[:8]} exists locally. "
                    f"Run `git push` to retry. Original error: {e}"
                ),
            }

        # 9. Update DB — only git_commit_hash + updated_at, NOT published_at
        from shopee_engine.article_exporter import get_site_url
        try:
            site_url = get_site_url()
            page_url = f"{site_url}/{article_id}/"
        except ValueError:
            page_url = None

        _mark_republished(article_id, commit_hash, rel_path)

        return {
            "success":     True,
            "dry_run":     False,
            "republished": True,
            "article_id":  article_id,
            "commit_hash": commit_hash,
            "pushed":      True,
            "page_url":    page_url,
            "warnings":    val.get("warnings", []),
            "in_sitemap":  verify.get("in_sitemap", False),
            "message":     f"Republished: {page_url or article_id}",
        }

    finally:
        lock_ctx.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Safe unpublish pipeline
# ---------------------------------------------------------------------------

def safe_unpublish(article_id: str) -> dict:
    """Remove article from site: published → reviewed, delete file, build, push."""
    published_enabled = is_publish_enabled()

    try:
        lock_ctx = _PublishLock()
        lock_ctx.__enter__()
    except RuntimeError as e:
        return _pub_err(article_id, str(e))

    try:
        # 1. Git environment
        env = check_git_environment()
        if not env["ok"]:
            return _pub_err(article_id, "Git environment check failed: " + "; ".join(env["errors"]))

        # 2. Check article status
        con = _connect(read_only=True)
        try:
            row = con.execute(
                f"SELECT status FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
            ).fetchone()
            con.close()
        except Exception as exc:
            con.close()
            return _pub_err(article_id, str(exc))

        if not row:
            return _pub_err(article_id, f"Article '{article_id}' not found")

        current_status = row[0]
        trans = validate_status_transition(current_status, "reviewed")
        if not trans["valid"]:
            return _pub_err(article_id, f"Cannot unpublish: {trans['error']}")

        # 3. Delete exported file
        file_deleted = delete_article_file(article_id)

        if not file_deleted:
            return _pub_err(article_id, "Article file not found in content directory")

        # 4. Build
        build = run_astro_build()
        if not build["success"]:
            # Re-export to restore file (best-effort)
            export_article(article_id, as_status="published")
            return _pub_err(article_id, "Astro build failed after file removal: " + build["error"])

        # DRY-RUN EXIT
        if not published_enabled:
            # Restore file
            export_article(article_id, as_status="published")
            return {
                "success":    True,
                "dry_run":    True,
                "article_id": article_id,
                "commit_hash": None,
                "pushed":     False,
                "message": "Dry-run: file deletion ✅, build ✅ — SEO_PUBLISH_ENABLED=false → no commit/push",
            }

        # 5. Git commit the deletion
        articles_dir = get_articles_dir()
        file_path    = articles_dir / f"{article_id}.md"
        rel_path     = file_path.relative_to(_git_root()).as_posix()

        try:
            _git("add", rel_path)
        except RuntimeError as e:
            export_article(article_id, as_status="published")
            return _pub_err(article_id, f"git add (deletion) failed: {e}")

        staged_files = _git_staged_files()
        bad_files    = _verify_staged_allowlist(staged_files)
        if bad_files:
            _git("reset", "HEAD", rel_path)
            export_article(article_id, as_status="published")
            return _pub_err(article_id, "Staged allowlist violation: " + ", ".join(bad_files))

        try:
            _git("commit", "-m", f"seo: unpublish article {article_id}")
        except RuntimeError as e:
            try:
                _git("reset", "HEAD", rel_path)
            except RuntimeError:
                pass
            export_article(article_id, as_status="published")
            return _pub_err(article_id, f"git commit failed: {e}")

        commit_hash = _git("rev-parse", "HEAD").stdout.strip()

        try:
            _git("push", get_git_remote(), get_git_branch())
        except RuntimeError as e:
            return {
                "success":     False,
                "dry_run":     False,
                "article_id":  article_id,
                "commit_hash": commit_hash,
                "pushed":      False,
                "error": (
                    f"git push failed — commit {commit_hash[:8]} exists locally. "
                    f"DB status unchanged. Error: {e}"
                ),
            }

        # 6. Update DB status after successful push
        _mark_unpublished(article_id)

        return {
            "success":    True,
            "dry_run":    False,
            "article_id": article_id,
            "commit_hash": commit_hash,
            "pushed":     True,
            "message":    f"Unpublished: {article_id}",
        }

    finally:
        lock_ctx.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pub_err(
    article_id: str,
    error: str,
    warnings: list[str] | None = None,
    build_output: str | None = None,
) -> dict:
    return {
        "success":    False,
        "dry_run":    False,
        "article_id": article_id,
        "commit_hash": None,
        "pushed":     False,
        "page_url":   None,
        "warnings":   warnings or [],
        "build_output": build_output,
        "error":      error,
    }

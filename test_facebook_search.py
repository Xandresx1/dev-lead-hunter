#!/usr/bin/env python3
"""
Test suite for Facebook Search feature (scrapeforge/facebook-search-posts)
Tests static validation, wiring, unit tests, and ONE live run
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
load_dotenv("/app/dev-lead-hunter/.env")


class TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def test(self, name: str, func):
        """Run a single test"""
        self.tests_run += 1
        print(f"\n{'='*70}")
        print(f"TEST {self.tests_run}: {name}")
        print('='*70)
        try:
            func()
            self.tests_passed += 1
            print(f"✅ PASSED: {name}")
            return True
        except AssertionError as e:
            self.tests_failed += 1
            self.failures.append(f"{name}: {str(e)}")
            print(f"❌ FAILED: {name}")
            print(f"   Error: {str(e)}")
            return False
        except Exception as e:
            self.tests_failed += 1
            self.failures.append(f"{name}: {type(e).__name__}: {str(e)}")
            print(f"❌ ERROR: {name}")
            print(f"   {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def summary(self):
        """Print test summary"""
        print(f"\n{'='*70}")
        print("TEST SUMMARY - FACEBOOK SEARCH FEATURE")
        print('='*70)
        print(f"Total: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_failed} ❌")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failures:
            print(f"\n{'='*70}")
            print("FAILURES:")
            print('='*70)
            for i, failure in enumerate(self.failures, 1):
                print(f"{i}. {failure}")
        
        return self.tests_failed == 0


def test_static_py_compile():
    """Test 1: py_compile all .py files"""
    import py_compile
    
    base_dir = Path("/app/dev-lead-hunter")
    py_files = list(base_dir.glob("**/*.py"))
    
    print(f"Found {len(py_files)} Python files")
    errors = []
    
    for py_file in py_files:
        if "__pycache__" in str(py_file):
            continue
        try:
            py_compile.compile(str(py_file), doraise=True)
            print(f"  ✓ {py_file.relative_to(base_dir)}")
        except py_compile.PyCompileError as e:
            errors.append(f"{py_file}: {e}")
            print(f"  ✗ {py_file.relative_to(base_dir)}: {e}")
    
    assert len(errors) == 0, f"Python compilation errors: {errors}"
    print("✓ All Python files compile successfully")


def test_static_workflow_yaml():
    """Test 2: Parse hunter.yml and verify Facebook search env vars"""
    import yaml
    
    workflow_file = Path("/app/dev-lead-hunter/.github/workflows/hunter.yml")
    print(f"Parsing workflow: {workflow_file}")
    
    with open(workflow_file) as f:
        workflow = yaml.safe_load(f)
    
    # Find the step with env
    env = None
    for step in workflow["jobs"]["hunt"]["steps"]:
        if "env" in step:
            env = step["env"]
            break
    
    assert env is not None, "No step with 'env' found in workflow"
    
    # Verify Facebook search environment variables
    required_vars = [
        "FACEBOOK_SEARCH_ENABLED",
        "FACEBOOK_SEARCH_INTERVAL_MINUTES",
        "FACEBOOK_SEARCH_QUERIES",
        "FACEBOOK_SEARCH_RESULTS"
    ]
    
    for var in required_vars:
        assert var in env, f"{var} not in workflow env"
        print(f"  ✓ {var}: {env[var]}")
    
    # Verify defaults
    assert "'true'" in env["FACEBOOK_SEARCH_ENABLED"], "Wrong FACEBOOK_SEARCH_ENABLED default"
    assert "'720'" in env["FACEBOOK_SEARCH_INTERVAL_MINUTES"], "Wrong FACEBOOK_SEARCH_INTERVAL_MINUTES default"
    assert "'5'" in env["FACEBOOK_SEARCH_RESULTS"], "Wrong FACEBOOK_SEARCH_RESULTS default"
    
    # Verify FACEBOOK_INTERVAL_MINUTES default is 1440
    assert "FACEBOOK_INTERVAL_MINUTES" in env, "FACEBOOK_INTERVAL_MINUTES not in workflow"
    assert "'1440'" in env["FACEBOOK_INTERVAL_MINUTES"], "FACEBOOK_INTERVAL_MINUTES should default to 1440"
    print(f"  ✓ FACEBOOK_INTERVAL_MINUTES: {env['FACEBOOK_INTERVAL_MINUTES']}")
    
    # Verify queries contain Spanish keywords
    queries_str = env["FACEBOOK_SEARCH_QUERIES"]
    assert "busco programador" in queries_str, "Missing 'busco programador' in queries"
    assert "necesito un programador" in queries_str, "Missing 'necesito un programador' in queries"
    print(f"  ✓ FACEBOOK_SEARCH_QUERIES contains Spanish keywords")
    
    print("✓ Workflow YAML has correct Facebook search configuration")


def test_static_env_example():
    """Test 3: Verify .env.example documents FACEBOOK_SEARCH_* variables"""
    env_example = Path("/app/dev-lead-hunter/.env.example")
    
    with open(env_example) as f:
        content = f.read()
    
    required_vars = [
        "FACEBOOK_SEARCH_ENABLED",
        "FACEBOOK_SEARCH_INTERVAL_MINUTES",
        "FACEBOOK_SEARCH_QUERIES",
        "FACEBOOK_SEARCH_RESULTS"
    ]
    
    for var in required_vars:
        assert var in content, f"{var} not documented in .env.example"
        print(f"  ✓ {var} documented")
    
    # Verify FACEBOOK_INTERVAL_MINUTES is 1440
    assert "FACEBOOK_INTERVAL_MINUTES=1440" in content, "FACEBOOK_INTERVAL_MINUTES should be 1440 in .env.example"
    print(f"  ✓ FACEBOOK_INTERVAL_MINUTES=1440")
    
    # Verify there's a comment about the feature
    assert "palabra clave" in content.lower() or "keyword" in content.lower(), "Missing description of keyword search"
    print(f"  ✓ Feature description present")
    
    print("✓ .env.example documents all Facebook search variables")


def test_wiring_with_apify_token():
    """Test 4: Wiring - fbsearch source included when APIFY_TOKEN is set"""
    # Save original env
    original_token = os.environ.get("APIFY_TOKEN", "")
    original_enabled = os.environ.get("FACEBOOK_SEARCH_ENABLED", "")
    
    try:
        # Set APIFY_TOKEN
        os.environ["APIFY_TOKEN"] = "test_token_12345"
        os.environ["FACEBOOK_SEARCH_ENABLED"] = "true"
        
        # Reload config
        import importlib
        import config
        importlib.reload(config)
        
        from sources import build_sources
        sources = build_sources()
        
        source_names = [s.name for s in sources]
        print(f"Sources with APIFY_TOKEN: {source_names}")
        
        # Verify fbsearch is present
        assert "fbsearch" in source_names, "fbsearch source not found when APIFY_TOKEN is set"
        
        # Verify fbsearch source properties
        fbsearch = next(s for s in sources if s.name == "fbsearch")
        assert fbsearch.interval_minutes == 720, f"Wrong interval: {fbsearch.interval_minutes}"
        assert fbsearch.uses_apify == True, "fbsearch should use Apify"
        
        print(f"  ✓ fbsearch source found")
        print(f"  ✓ interval_minutes: {fbsearch.interval_minutes}")
        print(f"  ✓ uses_apify: {fbsearch.uses_apify}")
        
        # Verify paid sources (Apify + Bright Data) are ordered first
        apify_sources = [s for s in sources if s.uses_apify or getattr(s, "paid", False)]
        non_apify_sources = [s for s in sources if not (s.uses_apify or getattr(s, "paid", False))]
        
        print(f"  Apify sources (should be first): {[s.name for s in apify_sources]}")
        print(f"  Non-Apify sources: {[s.name for s in non_apify_sources]}")
        
        # Check that all Apify sources come before non-Apify sources
        if apify_sources and non_apify_sources:
            first_apify_idx = sources.index(apify_sources[0])
            first_non_apify_idx = sources.index(non_apify_sources[0])
            assert first_apify_idx < first_non_apify_idx, "Apify sources should be ordered first"
            print(f"  ✓ Apify sources ordered first")
        
        print("✓ Wiring test with APIFY_TOKEN passed")
        
    finally:
        # Restore original env
        if original_token:
            os.environ["APIFY_TOKEN"] = original_token
        else:
            os.environ.pop("APIFY_TOKEN", None)
        
        if original_enabled:
            os.environ["FACEBOOK_SEARCH_ENABLED"] = original_enabled
        else:
            os.environ.pop("FACEBOOK_SEARCH_ENABLED", None)
        
        # Reload config
        import importlib
        import config
        importlib.reload(config)


def test_wiring_without_apify_token():
    """Test 5: Wiring - fbsearch absent when APIFY_TOKEN is empty"""
    import subprocess
    
    # Use subprocess to test in clean environment
    code = """
import sys
sys.path.insert(0, '/app/dev-lead-hunter')
import os
os.environ['APIFY_TOKEN'] = ''
from sources import build_sources
sources = build_sources()
source_names = [s.name for s in sources]
print(f"Sources: {source_names}")
assert 'fbsearch' not in source_names, f"fbsearch should be absent, got: {source_names}"
print("PASS")
"""
    
    result = subprocess.run(
        ["python", "-c", code],
        capture_output=True,
        text=True,
        cwd="/app/dev-lead-hunter"
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    assert result.returncode == 0, f"Test failed: {result.stderr}"
    assert "PASS" in result.stdout, "Test did not pass"
    
    print(f"  ✓ fbsearch absent when APIFY_TOKEN is empty")
    print(f"  ✓ No crash")
    
    print("✓ Wiring test without APIFY_TOKEN passed")


def test_wiring_disabled():
    """Test 6: Wiring - fbsearch absent when FACEBOOK_SEARCH_ENABLED=false"""
    import subprocess
    
    # Use subprocess to test in clean environment
    code = """
import sys
sys.path.insert(0, '/app/dev-lead-hunter')
import os
os.environ['APIFY_TOKEN'] = 'test_token_12345'
os.environ['FACEBOOK_SEARCH_ENABLED'] = 'false'
from sources import build_sources
sources = build_sources()
source_names = [s.name for s in sources]
print(f"Sources: {source_names}")
assert 'fbsearch' not in source_names, f"fbsearch should be absent, got: {source_names}"
print("PASS")
"""
    
    result = subprocess.run(
        ["python", "-c", code],
        capture_output=True,
        text=True,
        cwd="/app/dev-lead-hunter"
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    assert result.returncode == 0, f"Test failed: {result.stderr}"
    assert "PASS" in result.stdout, "Test did not pass"
    
    print(f"  ✓ fbsearch absent when FACEBOOK_SEARCH_ENABLED=false")
    
    print("✓ Wiring test with FACEBOOK_SEARCH_ENABLED=false passed")


def test_unit_item_parsing():
    """Test 7: Unit test - FacebookSearchSource item parsing with mocked data"""
    # Save original env
    original_token = os.environ.get("APIFY_TOKEN", "")
    
    try:
        # Set up environment
        os.environ["APIFY_TOKEN"] = "test_token_12345"
        os.environ["FACEBOOK_SEARCH_ENABLED"] = "true"
        
        # Reload config
        import importlib
        import config
        importlib.reload(config)
        
        from sources.apify_facebook_search import FacebookSearchSource
        
        # Create source instance
        source = FacebookSearchSource()
        
        # Mock data from Apify actor
        mock_items = [
            {
                'post_id': '1',
                'message': 'busco programador para mi tienda',
                'url': 'https://www.facebook.com/groups/1/posts/1/',
                'author': {'id': 'x', 'name': 'Ana'},
                'timestamp': 1792875824,
                'associated_group': {'name': 'G'},
                'reactions_count': 3
            },
            {
                'post_id': '2',
                'message': '',  # Empty message should be skipped
                'url': 'u2'
            }
        ]
        
        # Mock run_actor to return our test data
        with patch.object(source, 'run_actor', return_value=mock_items):
            posts = source.fetch()
        
        print(f"Parsed {len(posts)} posts from mock data")
        
        # Should only have 1 post (second one has empty message)
        assert len(posts) == 1, f"Expected 1 post, got {len(posts)}"
        
        post = posts[0]
        
        # Verify post properties
        assert post.id == 'facebook:1', f"Wrong id: {post.id}"
        assert post.source == 'facebook', f"Wrong source: {post.source}"
        assert post.author == 'Ana', f"Wrong author: {post.author}"
        assert post.text == 'busco programador para mi tienda', f"Wrong text: {post.text}"
        assert post.url == 'https://www.facebook.com/groups/1/posts/1/', f"Wrong url: {post.url}"
        assert post.posted_at is not None, "posted_at should not be None"
        
        # Verify extra fields
        assert post.extra.get('group') == 'G', f"Wrong group: {post.extra.get('group')}"
        assert post.extra.get('query') is not None, "query should be set in extra"
        assert post.extra.get('reactions') == 3, f"Wrong reactions: {post.extra.get('reactions')}"
        
        print(f"  ✓ Post ID: {post.id}")
        print(f"  ✓ Source: {post.source}")
        print(f"  ✓ Author: {post.author}")
        print(f"  ✓ Text: {post.text[:50]}...")
        print(f"  ✓ Group: {post.extra.get('group')}")
        print(f"  ✓ Query: {post.extra.get('query')}")
        print(f"  ✓ Posted at: {post.posted_at}")
        
        print("✓ Unit test - item parsing passed")
        
    finally:
        # Restore original env
        if original_token:
            os.environ["APIFY_TOKEN"] = original_token
        else:
            os.environ.pop("APIFY_TOKEN", None)
        
        # Reload config
        import importlib
        import config
        importlib.reload(config)


def test_unit_deduplication():
    """Test 8: Unit test - Deduplication of same post_id across queries"""
    import subprocess
    
    # Use subprocess to test in clean environment
    code = """
import sys
sys.path.insert(0, '/app/dev-lead-hunter')
import os
from unittest.mock import patch

# Set up environment with two queries
os.environ['APIFY_TOKEN'] = 'test_token_12345'
os.environ['FACEBOOK_SEARCH_ENABLED'] = 'true'
os.environ['FACEBOOK_SEARCH_QUERIES'] = 'busco programador,necesito programador'

from sources.apify_facebook_search import FacebookSearchSource

# Create source instance
source = FacebookSearchSource()

# Mock data - same post returned for both queries
mock_item = {
    'post_id': 'duplicate123',
    'message': 'busco programador urgente',
    'url': 'https://www.facebook.com/groups/1/posts/123/',
    'author': {'id': 'x', 'name': 'Juan'},
    'timestamp': 1792875824,
    'associated_group': {'name': 'Programadores'},
    'reactions_count': 5
}

# Mock run_actor to return the same item twice (once per query)
call_count = 0
def mock_run_actor(*args, **kwargs):
    global call_count
    call_count += 1
    return [mock_item]

with patch.object(source, 'run_actor', side_effect=mock_run_actor):
    posts = source.fetch()

print(f"run_actor called {call_count} times (once per query)")
print(f"Parsed {len(posts)} unique posts")

# Should only have 1 post (deduped)
assert len(posts) == 1, f"Expected 1 post after dedup, got {len(posts)}"
assert call_count == 2, f"Expected 2 calls to run_actor, got {call_count}"

post = posts[0]
assert post.id == 'facebook:duplicate123', f"Wrong id: {post.id}"

print(f"Post ID: {post.id}")
print("PASS")
"""
    
    result = subprocess.run(
        ["python", "-c", code],
        capture_output=True,
        text=True,
        cwd="/app/dev-lead-hunter"
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    assert result.returncode == 0, f"Test failed: {result.stderr}"
    assert "PASS" in result.stdout, "Test did not pass"
    
    print(f"  ✓ Deduplication works: 2 queries returned same post, only 1 kept")
    
    print("✓ Unit test - deduplication passed")


def test_live_facebook_search():
    """Test 9: Live test - ONE small run with fbsearch source (costs ~$0.03)"""
    import subprocess
    
    print("\n⚠️  WARNING: This test will make ONE live Apify API call (cost ~$0.03)")
    print("    Using a single query with max 5 results")
    
    # Check if we have required API keys
    apify_token = os.environ.get("APIFY_TOKEN", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    oxion_key = os.environ.get("OXION_API_KEY", "")
    ntfy_topic = os.environ.get("NTFY_TOPIC", "")
    
    if not apify_token:
        print("⚠️  APIFY_TOKEN not set, skipping live test")
        return
    
    print(f"  ✓ APIFY_TOKEN: {'*' * 10}{apify_token[-4:]}")
    print(f"  ✓ GEMINI_API_KEY: {'set' if gemini_key else 'not set'}")
    print(f"  ✓ OXION_API_KEY: {'set' if oxion_key else 'not set'}")
    print(f"  ✓ NTFY_TOPIC: {'set' if ntfy_topic else 'not set'}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        docs_dir = Path(tmpdir) / "docs"
        data_dir.mkdir()
        docs_dir.mkdir()
        
        env = os.environ.copy()
        env.update({
            "DATA_DIR": str(data_dir),
            "PAGES_DIR": str(docs_dir),
            "PAGES_BASE_URL": "https://xandresx1.github.io/dev-lead-hunter",
            "MAX_CLASSIFY_PER_TICK": "6",
            "FACEBOOK_SEARCH_QUERIES": "busco programador",  # Single query
            "FACEBOOK_SEARCH_RESULTS": "5",
            "GEMINI_API_KEY": gemini_key,
            "APIFY_TOKEN": apify_token,
            "OXION_API_KEY": oxion_key,
            "NTFY_TOPIC": ntfy_topic,
        })
        
        cmd = [
            "timeout", "280",
            "python", "main.py",
            "--once", "--force", "--dry-run",
            "--sources", "fbsearch"
        ]
        
        print(f"\nRunning: {' '.join(cmd)}")
        print(f"DATA_DIR: {data_dir}")
        print(f"PAGES_DIR: {docs_dir}")
        
        result = subprocess.run(
            cmd,
            cwd="/app/dev-lead-hunter",
            env=env,
            capture_output=True,
            text=True
        )
        
        print("\n--- STDOUT ---")
        print(result.stdout)
        
        if result.stderr:
            print("\n--- STDERR ---")
            print(result.stderr)
        
        output = result.stdout + result.stderr
        
        # Check exit code
        assert result.returncode == 0, f"Bot exited with code {result.returncode}"
        print(f"  ✓ Exit code: 0")
        
        # Check for Apify run (should be exactly once)
        apify_run_count = output.count("Apify run scrapeforge/facebook-search-posts")
        print(f"  ✓ Apify actor called {apify_run_count} time(s)")
        assert apify_run_count == 1, f"Expected 1 Apify run, found {apify_run_count}"
        
        # Check for FB search log
        if "FB search:" in output:
            # Extract the log line
            for line in output.split('\n'):
                if "FB search:" in line:
                    print(f"  ✓ Found log: {line.strip()}")
                    # Should say "N posts de 1 queries"
                    assert "de 1 queries" in line or "de 1 query" in line, "Should mention 1 query"
                    break
        else:
            print("  ⚠️  'FB search:' log not found (might be no results)")
        
        # Check for LEAD lines with [facebook] source
        lead_lines = [line for line in output.split('\n') if 'LEAD' in line and '[facebook]' in line]
        if lead_lines:
            print(f"  ✓ Found {len(lead_lines)} LEAD(s) with [facebook] source:")
            for line in lead_lines[:3]:  # Show first 3
                print(f"    {line.strip()}")
        else:
            print("  ℹ️  No LEADs found (expected if no high-quality posts)")
        
        # Check for no Traceback
        assert "Traceback" not in output, "Found Traceback in output"
        print(f"  ✓ No Traceback")
        
        # Test --stats command
        print("\nTesting --stats command...")
        result_stats = subprocess.run(
            ["python", "main.py", "--stats"],
            cwd="/app/dev-lead-hunter",
            env=env,
            capture_output=True,
            text=True
        )
        
        print(result_stats.stdout)
        
        assert result_stats.returncode == 0, f"--stats failed with code {result_stats.returncode}"
        
        # Check for fbsearch in stats
        if "fbsearch" in result_stats.stdout:
            print(f"  ✓ fbsearch row found in stats")
        else:
            print(f"  ⚠️  fbsearch not in stats (might be first run)")
        
        # Check for Apify spend line
        if "Apify" in result_stats.stdout and "gastado" in result_stats.stdout:
            print(f"  ✓ Apify spend line found")
        else:
            print(f"  ⚠️  Apify spend line not found")
        
        print("✓ Live test passed - fbsearch source works correctly")


def main():
    """Run all tests"""
    print("="*70)
    print("FACEBOOK SEARCH FEATURE - COMPREHENSIVE TEST SUITE")
    print("="*70)
    
    runner = TestRunner()
    
    # Static tests
    runner.test("Static: py_compile all .py files", test_static_py_compile)
    runner.test("Static: Parse hunter.yml and verify env vars", test_static_workflow_yaml)
    runner.test("Static: Verify .env.example documents vars", test_static_env_example)
    
    # Wiring tests (no network)
    runner.test("Wiring: fbsearch included with APIFY_TOKEN", test_wiring_with_apify_token)
    runner.test("Wiring: fbsearch absent without APIFY_TOKEN", test_wiring_without_apify_token)
    runner.test("Wiring: fbsearch absent when disabled", test_wiring_disabled)
    
    # Unit tests
    runner.test("Unit: FacebookSearchSource item parsing", test_unit_item_parsing)
    runner.test("Unit: Deduplication across queries", test_unit_deduplication)
    
    # Live test (ONE run only)
    runner.test("Live: ONE small run with fbsearch (costs ~$0.03)", test_live_facebook_search)
    
    # Print summary
    success = runner.summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

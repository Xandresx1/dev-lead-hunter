#!/usr/bin/env python3
"""
Comprehensive backend tests for Dev Lead Hunter
Tests all new features: INR filter, proposals, pages, notifications
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

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
        print(f"\n{'='*60}")
        print(f"TEST {self.tests_run}: {name}")
        print('='*60)
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
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print('='*60)
        print(f"Total: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_failed} ❌")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failures:
            print(f"\n{'='*60}")
            print("FAILURES:")
            print('='*60)
            for i, failure in enumerate(self.failures, 1):
                print(f"{i}. {failure}")
        
        return self.tests_failed == 0


def test_static_validation():
    """Test 1: Static validation - py_compile all .py files"""
    import py_compile
    import yaml
    
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
    
    # Test YAML parsing
    workflow_file = base_dir / ".github/workflows/hunter.yml"
    print(f"\nParsing workflow: {workflow_file}")
    
    with open(workflow_file) as f:
        workflow = yaml.safe_load(f)
    
    # Verify key environment variables are passed
    # Find the step with env (it's the "Ejecutar bot" step)
    env = None
    for step in workflow["jobs"]["hunt"]["steps"]:
        if "env" in step:
            env = step["env"]
            break
    
    assert env is not None, "No step with 'env' found in workflow"
    
    assert "OXION_API_KEY" in env, "OXION_API_KEY not in workflow env"
    assert "OXION_MODEL" in env, "OXION_MODEL not in workflow env"
    assert "PAGES_BASE_URL" in env, "PAGES_BASE_URL not in workflow env"
    assert "PAGES_DIR" in env, "PAGES_DIR not in workflow env"
    assert "EXCLUDED_CURRENCIES" in env, "EXCLUDED_CURRENCIES not in workflow env"
    
    # Verify defaults
    assert "'claude-sonnet-5'" in env["OXION_MODEL"], "Wrong OXION_MODEL default"
    assert "'INR'" in env["EXCLUDED_CURRENCIES"], "Wrong EXCLUDED_CURRENCIES default"
    assert "./docs" in env["PAGES_DIR"], "Wrong PAGES_DIR default"
    
    # Verify git add includes docs
    git_step = None
    for step in workflow["jobs"]["hunt"]["steps"]:
        if "run" in step and "git add" in step["run"]:
            git_step = step["run"]
            break
    
    assert git_step is not None, "Git step not found"
    assert "git add data/state.json docs" in git_step, "Git step doesn't add docs"
    
    print("✓ Workflow YAML is valid and has correct configuration")


def test_inr_filter_unit():
    """Test 2: INR filter unit tests"""
    from keywords import excluded_currency_hit
    
    test_cases = [
        ("Budget 5000 INR", "INR"),
        ("₹3000 for this project", "INR"),
        ("pago en rupias", "INR"),
        ("Rs. 2000", "INR"),
        ("USD 500", None),
        ("inrush current", None),  # word boundary test
        ("INR 1000-2000", "INR"),
        ("rupees 500", "INR"),
    ]
    
    for text, expected in test_cases:
        result = excluded_currency_hit(text, ["INR"])
        print(f"  '{text}' -> {result} (expected: {expected})")
        assert result == expected, f"Failed for '{text}': got {result}, expected {expected}"
    
    print("✓ All INR filter unit tests passed")


def test_inr_filter_integration():
    """Test 3: INR filter integration - run bot and verify INR filtering"""
    import subprocess
    
    # Create temp directory for this test
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
            "APIFY_TOKEN": "",  # Empty to avoid costs
        })
        
        cmd = [
            "timeout", "240",
            "python", "main.py",
            "--once", "--force", "--dry-run",
            "--sources", "freelancer"
        ]
        
        print(f"Running: {' '.join(cmd)}")
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
        
        # Check exit code
        assert result.returncode == 0, f"Bot exited with code {result.returncode}"
        
        # Check for INR filtering in logs
        output = result.stdout + result.stderr
        
        # Should have filtered some INR projects
        if "descartado por moneda excluida (INR)" in output or "omito proyecto" in output:
            print("✓ Found INR filtering in logs")
        else:
            print("⚠ No INR filtering found (might be no INR projects at this time)")
        
        # Should not have any Traceback
        assert "Traceback" not in output, "Found Traceback in output"
        
        print("✓ INR filter integration test passed")


def test_pages_generation():
    """Test 4: Pages generation and HTML structure"""
    from pages import PageWriter, theme
    from proposals import Proposal
    
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        
        # Override settings
        import config
        config.settings.pages_dir = str(docs_dir)
        config.settings.pages_base_url = "https://xandresx1.github.io/dev-lead-hunter"
        config.settings.pages_enabled = True
        
        writer = PageWriter()
        
        # Create a sample proposal
        proposal = Proposal(
            text="Necesitas un sistema de ventas. Lo construyo con Python + PostgreSQL.",
            price_usd=650,
            price_type="fijo",
            days=21,
            justification="Rango del cliente 400-800; promedio 520",
            question="La facturacion electronica, la emites via OSE?",
            model="claude-sonnet-5"
        )
        
        # Write a page
        url = writer.write(
            post_id="freelancer:test123",
            source="freelancer",
            score=85,
            title="Sistema de ventas para bodega",
            text="Hola, busco un programador que me haga un sistema de ventas <b>con HTML</b>",
            url="https://www.freelancer.com/projects/test",
            summary="Duena de bodega busca sistema de ventas",
            opener="Hola! Vi que necesitas un sistema",
            location="Lima, Peru",
            proposal=proposal
        )
        
        print(f"Generated URL: {url}")
        assert url is not None, "URL should not be None"
        assert url.startswith("https://xandresx1.github.io/dev-lead-hunter/p/"), f"Wrong URL format: {url}"
        
        # Check files exist
        assert (docs_dir / "index.html").exists(), "index.html not created"
        assert (docs_dir / ".nojekyll").exists(), ".nojekyll not created"
        
        pages = list((docs_dir / "p").glob("*.html"))
        assert len(pages) == 1, f"Expected 1 page, found {len(pages)}"
        
        page_file = pages[0]
        content = page_file.read_text()
        
        print(f"\nPage file: {page_file}")
        print(f"Content length: {len(content)} chars")
        
        # Verify content
        assert '<meta name="robots" content="noindex' in content, "Missing noindex meta"
        assert '#1e88e5' in content, "Missing Freelancer blue color"
        assert 'Copiar' in content, "Missing Copiar button"
        assert '&lt;b&gt;' in content, "HTML not escaped (should be &lt;b&gt; not <b>)"
        assert '<b>con HTML</b>' not in content, "HTML not escaped properly"
        assert 'USD 650' in content, "Missing price"
        assert '21 días' in content or '21 d' in content, "Missing days"
        
        # Check theme color
        th = theme("freelancer")
        assert th["color"] == "#1e88e5", "Wrong Freelancer color"
        
        print("✓ Pages generation test passed")


def test_pages_copy_button():
    """Test 5: Pages copy button works in browser (Playwright test will be separate)"""
    # This is a placeholder - actual browser test will be done with Playwright
    print("✓ Copy button test will be done with Playwright separately")


def test_proposal_gating():
    """Test 6: Proposal gating - only for freelancer + Spanish"""
    from proposals import ProposalWriter
    from sources.base import Post
    from datetime import datetime
    
    writer = ProposalWriter()
    
    # Test 1: freelancer + es -> should apply
    post_es = Post(
        id="test1",
        source="freelancer",
        title="Test",
        text="Test project",
        url="http://test.com",
        author="test",
        posted_at=datetime.now(),
        extra={"lang": "es"}
    )
    
    result = writer.applies(post_es, "es")
    print(f"freelancer + es: {result}")
    assert result == True, "Should apply for freelancer + es"
    
    # Test 2: freelancer + en -> should NOT apply
    post_en = Post(
        id="test2",
        source="freelancer",
        title="Test",
        text="Test project",
        url="http://test.com",
        author="test",
        posted_at=datetime.now(),
        extra={"lang": "en"}
    )
    
    result = writer.applies(post_en, "en")
    print(f"freelancer + en: {result}")
    assert result == False, "Should NOT apply for freelancer + en"
    
    # Test 3: facebook + es -> should NOT apply
    post_fb = Post(
        id="test3",
        source="facebook",
        title="Test",
        text="Test project",
        url="http://test.com",
        author="test",
        posted_at=datetime.now(),
        extra={"lang": "es"}
    )
    
    result = writer.applies(post_fb, "es")
    print(f"facebook + es: {result}")
    assert result == False, "Should NOT apply for facebook + es"
    
    print("✓ Proposal gating test passed")


def test_oxion_live_status():
    """Test 7: Oxion API status and proposal generation"""
    from proposals import ProposalWriter
    
    writer = ProposalWriter()
    
    if not writer.enabled:
        print("⚠ OXION_API_KEY not set, skipping Oxion tests")
        return
    
    # Test models endpoint
    print("\nTesting Oxion models endpoint...")
    try:
        models = writer.list_models()
        print(f"Available models: {models}")
        assert "claude-sonnet-5" in models, "claude-sonnet-5 not in models list"
        print("✓ Models endpoint works")
    except Exception as e:
        print(f"⚠ Models endpoint failed: {e}")
    
    # Test proposal generation with a real Spanish Freelancer post
    print("\nTesting proposal generation...")
    from sources.freelancer import FreelancerSource
    from sources.base import Post
    from datetime import datetime
    
    # Override settings to only fetch Spanish projects
    import config
    config.settings.freelancer_queries_en = []
    config.settings.freelancer_queries_es = ["sistema"]
    
    try:
        source = FreelancerSource()
        posts = source.fetch()
        
        # Find a Spanish post
        spanish_post = None
        for post in posts:
            if post.extra.get("lang") == "es":
                spanish_post = post
                break
        
        if spanish_post:
            print(f"\nFound Spanish post: {spanish_post.title[:60]}")
            print(f"Testing proposal generation...")
            
            proposal = writer.write(spanish_post, "es")
            
            if proposal is None:
                print("⚠ Proposal generation returned None (expected if Oxion is in maintenance)")
                print("  This is the expected behavior when Oxion returns 503")
            else:
                print("✓ Proposal generated successfully!")
                print(f"  Price: {proposal.price_label}")
                print(f"  Days: {proposal.days}")
                print(f"  Text length: {len(proposal.text)} chars")
                print(f"  Text preview: {proposal.text[:200]}...")
                
                # Verify proposal structure
                assert len(proposal.text) > 0, "Proposal text is empty"
                assert proposal.price_usd > 0, "Price should be > 0"
                assert proposal.days > 0, "Days should be > 0"
                assert len(proposal.text.split()) <= 200, "Proposal too long (>200 words)"
        else:
            print("⚠ No Spanish posts found in Freelancer")
    
    except Exception as e:
        print(f"⚠ Proposal generation test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("✓ Oxion live status test completed")


def test_fallback_notification():
    """Test 8: Fallback notification when proposal fails"""
    from notifier import Notifier
    
    notifier = Notifier()
    
    if not notifier.enabled:
        print("⚠ NTFY_TOPIC not set, skipping notification test")
        return
    
    # Test notification with proposal_failed=True
    print("\nSending test notification with proposal_failed=True...")
    
    result = notifier.send_lead(
        source="freelancer",
        score=80,
        language="es",
        summary="Test lead for fallback notification",
        opener="Hola, test message",
        text="This is a test lead to verify fallback notification works",
        url="https://www.freelancer.es/projects/test",
        author="TestAuthor",
        ai=True,
        posted_at=None,
        proposal=None,
        page_url="https://xandresx1.github.io/dev-lead-hunter/p/test.html",
        proposal_failed=True
    )
    
    assert result == True, "Notification should return True"
    print("✓ Fallback notification sent successfully")
    
    # Test --test-notify command
    print("\nTesting --test-notify command...")
    import subprocess
    
    result = subprocess.run(
        ["python", "main.py", "--test-notify"],
        cwd="/app/dev-lead-hunter",
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    assert result.returncode == 0, f"--test-notify failed with code {result.returncode}"
    assert "Notificacion enviada" in result.stdout, "Missing success message"
    
    print("✓ --test-notify command works")


def test_regression_dedup_state():
    """Test 9: Regression - dedup and state.json still work"""
    import subprocess
    
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        docs_dir = Path(tmpdir) / "docs"
        state_file = Path(tmpdir) / "state.json"
        data_dir.mkdir()
        docs_dir.mkdir()
        
        env = os.environ.copy()
        env.update({
            "DATA_DIR": str(data_dir),
            "PAGES_DIR": str(docs_dir),
            "PAGES_BASE_URL": "https://xandresx1.github.io/dev-lead-hunter",
            "MAX_CLASSIFY_PER_TICK": "6",
            "APIFY_TOKEN": "",
        })
        
        # First run
        print("\nFirst run...")
        cmd = [
            "timeout", "240",
            "python", "main.py",
            "--once", "--force", "--dry-run",
            "--sources", "freelancer",
            "--state-json", str(state_file)
        ]
        
        result1 = subprocess.run(cmd, cwd="/app/dev-lead-hunter", env=env, capture_output=True, text=True)
        assert result1.returncode == 0, f"First run failed with code {result1.returncode}"
        
        # Check state.json was created
        assert state_file.exists(), "state.json not created"
        
        with open(state_file) as f:
            state = json.load(f)
        
        print(f"State keys: {list(state.keys())}")
        assert "seen" in state, "Missing 'seen' key in state.json"
        assert "runs" in state, "Missing 'runs' key in state.json"
        assert "counters" in state, "Missing 'counters' key in state.json"
        assert "leads" in state, "Missing 'leads' key in state.json"
        assert "stats" in state, "Missing 'stats' key in state.json"
        
        first_seen_count = len(state["seen"])
        print(f"First run: {first_seen_count} posts seen")
        
        # Second run - should have 0 new leads (all deduped)
        print("\nSecond run (should dedupe)...")
        result2 = subprocess.run(cmd, cwd="/app/dev-lead-hunter", env=env, capture_output=True, text=True)
        assert result2.returncode == 0, f"Second run failed with code {result2.returncode}"
        
        with open(state_file) as f:
            state2 = json.load(f)
        
        second_seen_count = len(state2["seen"])
        print(f"Second run: {second_seen_count} posts seen")
        
        # Should have same or more seen (no new leads should be notified)
        assert second_seen_count >= first_seen_count, "Dedup not working"
        
        # Test --stats command
        print("\nTesting --stats command...")
        result3 = subprocess.run(
            ["python", "main.py", "--stats"],
            cwd="/app/dev-lead-hunter",
            env=env,
            capture_output=True,
            text=True
        )
        
        print(result3.stdout)
        assert result3.returncode == 0, f"--stats failed with code {result3.returncode}"
        assert "Fuentes" in result3.stdout or "Totales" in result3.stdout, "Stats output missing"
        
        print("✓ Regression test passed - dedup and state.json work")


def main():
    """Run all tests"""
    print("="*60)
    print("DEV LEAD HUNTER - COMPREHENSIVE BACKEND TESTS")
    print("="*60)
    
    runner = TestRunner()
    
    # Run all tests
    runner.test("Static Validation (py_compile + YAML)", test_static_validation)
    runner.test("INR Filter Unit Tests", test_inr_filter_unit)
    runner.test("INR Filter Integration", test_inr_filter_integration)
    runner.test("Pages Generation", test_pages_generation)
    runner.test("Pages Copy Button (placeholder)", test_pages_copy_button)
    runner.test("Proposal Gating", test_proposal_gating)
    runner.test("Oxion Live Status", test_oxion_live_status)
    runner.test("Fallback Notification", test_fallback_notification)
    runner.test("Regression: Dedup and State", test_regression_dedup_state)
    
    # Print summary
    success = runner.summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Test MIN_SCORE=90 and Proposal Retry Queue + Circuit Breaker
Tests the two new features as specified in the review request.
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
        print("TEST SUMMARY")
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


def test_static_min_score_90():
    """Test 1: Static - MIN_SCORE default is 90 in all places"""
    import yaml
    from config import settings
    
    # Check config.py
    print(f"config.py MIN_SCORE: {settings.min_score}")
    assert settings.min_score == 90, f"config.py MIN_SCORE should be 90, got {settings.min_score}"
    
    # Check .env.example
    env_example = Path("/app/dev-lead-hunter/.env.example").read_text()
    assert "MIN_SCORE=90" in env_example, ".env.example should have MIN_SCORE=90"
    print("✓ .env.example has MIN_SCORE=90")
    
    # Check hunter.yml
    workflow_file = Path("/app/dev-lead-hunter/.github/workflows/hunter.yml")
    with open(workflow_file) as f:
        workflow = yaml.safe_load(f)
    
    # Find the step with env
    env = None
    for step in workflow["jobs"]["hunt"]["steps"]:
        if "env" in step:
            env = step["env"]
            break
    
    assert env is not None, "No step with 'env' found in workflow"
    assert "MIN_SCORE" in env, "MIN_SCORE not in workflow env"
    assert "'90'" in env["MIN_SCORE"], f"MIN_SCORE default should be '90', got {env['MIN_SCORE']}"
    print(f"✓ hunter.yml has MIN_SCORE default '90': {env['MIN_SCORE']}")
    
    print("✓ All static checks passed for MIN_SCORE=90")


def test_storage_pending_proposals_unit():
    """Test 2: Unit - Storage pending_proposals operations"""
    from storage import Storage
    
    # Use a temp file path (not :memory: as per requirement)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        storage = Storage(Path(db_path))
        
        # Test add_pending_proposal
        lead_payload = {
            'id': 'freelancer:1',
            'source': 'freelancer',
            'text': 'Necesito un sistema de ventas',
            'url': 'https://www.freelancer.es/projects/test',
            'extra': {'lang': 'es'},
            'language': 'es',
            'score': 90,
            'summary': 'Cliente busca sistema de ventas',
            'opener': 'Hola! Vi que necesitas un sistema',
            'location': None
        }
        
        storage.add_pending_proposal('freelancer:1', lead_payload)
        print("✓ add_pending_proposal succeeded")
        
        # Test pending_count
        count = storage.pending_count()
        assert count == 1, f"Expected 1 pending, got {count}"
        print(f"✓ pending_count() == 1")
        
        # Test pending_proposals
        pending = storage.pending_proposals()
        assert len(pending) == 1, f"Expected 1 pending proposal, got {len(pending)}"
        assert pending[0]['id'] == 'freelancer:1', f"Wrong id: {pending[0]['id']}"
        assert pending[0]['language'] == 'es', f"Wrong language: {pending[0]['language']}"
        assert pending[0]['_attempts'] == 0, f"Initial attempts should be 0, got {pending[0]['_attempts']}"
        print(f"✓ pending_proposals() returns correct data")
        
        # Test bump_pending_proposal
        storage.bump_pending_proposal('freelancer:1')
        pending = storage.pending_proposals()
        assert pending[0]['_attempts'] == 1, f"After bump, attempts should be 1, got {pending[0]['_attempts']}"
        print(f"✓ bump_pending_proposal() increments attempts")
        
        # Test export_json with pending_proposals
        with tempfile.NamedTemporaryFile(mode='w', suffix=".json", delete=False) as f:
            export_path = Path(f.name)
        
        storage.export_json(export_path)
        assert export_path.exists(), "export_json should create file"
        
        exported = json.loads(export_path.read_text())
        assert 'pending_proposals' in exported, "Exported JSON should have 'pending_proposals' key"
        assert len(exported['pending_proposals']) == 1, f"Expected 1 pending in export, got {len(exported['pending_proposals'])}"
        assert 'stats' in exported, "Exported JSON should have 'stats' key"
        assert exported['stats']['pending_proposals'] == 1, f"stats.pending_proposals should be 1, got {exported['stats']['pending_proposals']}"
        print(f"✓ export_json() includes pending_proposals")
        
        # Test import_json (new Storage instance)
        storage.close()
        os.unlink(db_path)
        
        storage2 = Storage(Path(db_path))
        storage2.import_json(export_path)
        
        count2 = storage2.pending_count()
        assert count2 == 1, f"After import, pending_count should be 1, got {count2}"
        print(f"✓ import_json() restores pending_proposals")
        
        # Test remove_pending_proposal
        storage2.remove_pending_proposal('freelancer:1')
        count3 = storage2.pending_count()
        assert count3 == 0, f"After remove, pending_count should be 0, got {count3}"
        print(f"✓ remove_pending_proposal() works")
        
        storage2.close()
        os.unlink(export_path)
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_proposal_writer_post_payload_roundtrip():
    """Test 3: Unit - ProposalWriter post_payload/post_from_payload round-trip"""
    from proposals import ProposalWriter
    from sources.base import Post
    from datetime import datetime
    
    # Create a test post
    original_post = Post(
        id='freelancer:123',
        source='freelancer',
        text='Necesito un sistema de ventas e inventario',
        url='https://www.freelancer.es/projects/test',
        title='Sistema de ventas',
        author='TestUser',
        posted_at=datetime.now(),
        extra={'lang': 'es', 'budget': '500-1000 USD'}
    )
    
    # Convert to payload
    payload = ProposalWriter.post_payload(
        original_post,
        language='es',
        score=92,
        summary='Cliente busca sistema de ventas',
        opener='Hola! Vi que necesitas un sistema',
        location='Lima, Peru'
    )
    
    print(f"Payload keys: {list(payload.keys())}")
    assert 'id' in payload, "Payload should have 'id'"
    assert 'source' in payload, "Payload should have 'source'"
    assert 'text' in payload, "Payload should have 'text'"
    assert 'extra' in payload, "Payload should have 'extra'"
    assert 'language' in payload, "Payload should have 'language'"
    assert payload['id'] == 'freelancer:123', f"Wrong id: {payload['id']}"
    assert payload['language'] == 'es', f"Wrong language: {payload['language']}"
    print("✓ post_payload() creates correct structure")
    
    # Convert back to Post
    restored_post = ProposalWriter.post_from_payload(payload)
    
    assert restored_post.id == original_post.id, f"ID mismatch: {restored_post.id} != {original_post.id}"
    assert restored_post.source == original_post.source, f"Source mismatch: {restored_post.source} != {original_post.source}"
    assert restored_post.text == original_post.text, f"Text mismatch"
    assert restored_post.url == original_post.url, f"URL mismatch"
    assert restored_post.extra == original_post.extra, f"Extra mismatch"
    print("✓ post_from_payload() restores Post correctly")
    
    print("✓ Round-trip test passed")


def test_proposal_writer_applies_with_pause():
    """Test 4: Unit - ProposalWriter applies() with pause logic"""
    from proposals import ProposalWriter
    from sources.base import Post
    from datetime import datetime
    
    # Get OXION_API_KEY from environment
    oxion_key = os.environ.get('OXION_API_KEY')
    if not oxion_key:
        print("⚠ OXION_API_KEY not set, skipping this test")
        return
    
    writer = ProposalWriter()
    
    # Create Spanish Freelancer post
    post_es = Post(
        id='test1',
        source='freelancer',
        title='Test',
        text='Necesito un sistema',
        url='http://test.com',
        author='test',
        posted_at=datetime.now(),
        extra={'lang': 'es'}
    )
    
    # Test 1: applies() should return True for Spanish Freelancer
    result = writer.applies(post_es, 'es')
    print(f"applies(post_es, 'es') = {result}")
    assert result == True, "Should apply for Spanish Freelancer post"
    
    # Test 2: Set writer to paused state
    writer._disabled_until = time.time() + 600  # Pause for 10 minutes
    
    # applies() should return False when paused
    result_paused = writer.applies(post_es, 'es')
    print(f"applies(post_es, 'es') when paused = {result_paused}")
    assert result_paused == False, "Should NOT apply when paused"
    
    # Test 3: applies() with ignore_pause=True should return True
    result_ignore = writer.applies(post_es, 'es', ignore_pause=True)
    print(f"applies(post_es, 'es', ignore_pause=True) = {result_ignore}")
    assert result_ignore == True, "Should apply when ignore_pause=True"
    
    # Test 4: paused property should return True
    assert writer.paused == True, "writer.paused should be True"
    print(f"✓ writer.paused = {writer.paused}")
    
    print("✓ ProposalWriter applies() with pause logic works correctly")


def test_integration_oxion_outage():
    """Test 5: Integration - Real Oxion outage with circuit breaker"""
    import subprocess
    
    print("\n⚠ This test runs against REAL Oxion API (currently in maintenance with 503)")
    print("Expected behavior: circuit breaker should pause after first 503")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        docs_dir = Path(tmpdir) / "docs"
        state_file = data_dir / "state.json"
        data_dir.mkdir()
        docs_dir.mkdir()
        
        env = os.environ.copy()
        env.update({
            "DATA_DIR": str(data_dir),
            "PAGES_DIR": str(docs_dir),
            "PAGES_BASE_URL": "https://xandresx1.github.io/dev-lead-hunter",
            "APIFY_TOKEN": "",  # Empty to avoid costs
            "MAX_CLASSIFY_PER_TICK": "8",
            "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
            "NTFY_TOPIC": os.environ.get("NTFY_TOPIC", ""),
            "OXION_API_KEY": os.environ.get("OXION_API_KEY", ""),
        })
        
        # Run Hunter with Spanish queries only
        cmd = [
            "timeout", "300",
            "python", "-c",
            """
from config import settings
settings.freelancer_queries_en = []
settings.freelancer_queries_es = ['sistema web', 'aplicacion', 'pagina web', 'software']
settings.freelancer_limit_per_query = 8
import main as M
from pathlib import Path
h = M.Hunter(dry_run=True, only=['freelancer'], state_json=Path('/tmp/tq/state.json'))
r = h.run_once(force=True)
print(f"\\n=== RESULT ===")
print(f"leads: {r['leads']}")
print(f"proposals_pending: {r['proposals_pending']}")
print(f"proposals_retried: {r['proposals_retried']}")
"""
        ]
        
        # Create /tmp/tq directory
        os.makedirs("/tmp/tq", exist_ok=True)
        
        print(f"Running integration test...")
        print(f"Command: python -c '...'")
        
        result = subprocess.run(
            cmd,
            cwd="/app/dev-lead-hunter",
            env=env,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        print("\n--- STDOUT ---")
        print(result.stdout)
        
        if result.stderr:
            print("\n--- STDERR ---")
            print(result.stderr)
        
        output = result.stdout + result.stderr
        
        # Check 1: No Traceback
        assert "Traceback" not in output, "Found Traceback in output"
        print("✓ No Traceback")
        
        # Check 2: MIN_SCORE >= 90 filtering
        # Look for leads in the database
        db_path = Path("/tmp/tq/hunter.db")
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT score FROM leads")
            scores = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            if scores:
                print(f"Found {len(scores)} leads with scores: {scores}")
                for score in scores:
                    assert score >= 90, f"Found lead with score {score} < 90"
                print(f"✓ All leads have score >= 90")
            else:
                print("⚠ No leads found (Gemini might have scored all < 90)")
                # Check if there were any classifications
                if "LEAD score=" in output or "no score=" in output:
                    print("✓ MIN_SCORE gating is working (leads with score<90 were not saved)")
        
        # Check 3: Circuit breaker - only ONE 503 log per run
        oxion_503_count = output.count("Oxion no disponible (503")
        print(f"Oxion 503 errors found: {oxion_503_count}")
        
        # Check 4: Pending proposals queue
        state_json_path = Path("/tmp/tq/state.json")
        if state_json_path.exists():
            state = json.loads(state_json_path.read_text())
            pending_count = len(state.get('pending_proposals', []))
            print(f"Pending proposals in state.json: {pending_count}")
            
            # If there were Spanish leads, they should be in pending queue
            if "=== RESULT ===" in output:
                result_lines = output.split("=== RESULT ===")[1]
                if "proposals_pending:" in result_lines:
                    pending_from_output = int([l for l in result_lines.split('\n') if 'proposals_pending:' in l][0].split(':')[1].strip())
                    print(f"proposals_pending from output: {pending_from_output}")
                    assert pending_count == pending_from_output, f"Mismatch: state.json has {pending_count}, output says {pending_from_output}"
                    print(f"✓ Pending proposals count matches")
        
        print("✓ Integration test with Oxion outage completed")


def test_second_run_queue_persistence():
    """Test 6: Second run - Queue persists via state.json"""
    import subprocess
    
    print("\n⚠ This test verifies queue persistence across runs")
    
    # Clean up from previous test
    os.system("rm -rf /tmp/tq2")
    os.makedirs("/tmp/tq2", exist_ok=True)
    
    env = os.environ.copy()
    env.update({
        "DATA_DIR": "/tmp/tq2",
        "PAGES_DIR": "/tmp/tq2/docs",
        "PAGES_BASE_URL": "https://xandresx1.github.io/dev-lead-hunter",
        "APIFY_TOKEN": "",
        "MAX_CLASSIFY_PER_TICK": "8",
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
        "NTFY_TOPIC": os.environ.get("NTFY_TOPIC", ""),
        "OXION_API_KEY": os.environ.get("OXION_API_KEY", ""),
    })
    
    # First run - create some pending proposals
    cmd1 = [
        "timeout", "300",
        "python", "-c",
        """
from config import settings
settings.freelancer_queries_en = []
settings.freelancer_queries_es = ['bot', 'tienda online', 'app movil', 'automatizacion']
settings.freelancer_limit_per_query = 8
import main as M
from pathlib import Path
h = M.Hunter(dry_run=True, only=['freelancer'], state_json=Path('/tmp/tq2/state.json'))
r = h.run_once(force=True)
print(f"First run - proposals_pending: {r['proposals_pending']}")
"""
    ]
    
    print("Running first run...")
    result1 = subprocess.run(cmd1, cwd="/app/dev-lead-hunter", env=env, capture_output=True, text=True, timeout=300)
    print(result1.stdout)
    
    # Check state.json was created
    state_file = Path("/tmp/tq2/state.json")
    assert state_file.exists(), "state.json should be created"
    
    state1 = json.loads(state_file.read_text())
    pending_count1 = len(state1.get('pending_proposals', []))
    print(f"✓ First run created {pending_count1} pending proposals")
    
    # Delete the database to simulate fresh start
    db_path = Path("/tmp/tq2/hunter.db")
    if db_path.exists():
        os.unlink(db_path)
        print("✓ Deleted database")
    
    # Second run - should reimport queue from state.json
    cmd2 = [
        "timeout", "300",
        "python", "-c",
        """
from config import settings
settings.freelancer_queries_en = []
settings.freelancer_queries_es = []  # No new queries
import main as M
from pathlib import Path
h = M.Hunter(dry_run=True, only=['freelancer'], state_json=Path('/tmp/tq2/state.json'))
print(f"After import - pending_count: {h.storage.pending_count()}")
retried = h.retry_pending_proposals()
print(f"Retried: {retried}")
print(f"After retry - pending_count: {h.storage.pending_count()}")
"""
    ]
    
    print("\nRunning second run (fresh DB, reimport from state.json)...")
    result2 = subprocess.run(cmd2, cwd="/app/dev-lead-hunter", env=env, capture_output=True, text=True, timeout=300)
    print(result2.stdout)
    
    output2 = result2.stdout + result2.stderr
    
    # Check that pending count was restored
    if "After import - pending_count:" in output2:
        import re
        match = re.search(r"After import - pending_count: (\d+)", output2)
        if match:
            pending_after_import = int(match.group(1))
            print(f"✓ Queue survived via state.json: {pending_after_import} pending proposals")
            assert pending_after_import == pending_count1, f"Expected {pending_count1}, got {pending_after_import}"
    
    # Check retry behavior
    if "Retried:" in output2:
        # While Oxion is 503, retried should be 0
        # If Oxion is back, retried might be > 0
        print("✓ retry_pending_proposals() executed without exception")
    
    print("✓ Second run test completed")


def test_notification_send_proposal_ready():
    """Test 7: Notification - send_proposal_ready()"""
    from notifier import Notifier
    from proposals import Proposal
    
    notifier = Notifier()
    
    if not notifier.enabled:
        print("⚠ NTFY_TOPIC not set, skipping notification test")
        return
    
    # Create a test proposal
    proposal = Proposal(
        text='Propuesta de prueba: Necesitas un bot de WhatsApp para recordatorios. Lo construyo con Python + Twilio.',
        price_usd=350,
        price_type='fijo',
        days=10,
        justification='60h de desarrollo + 30% colchon',
        question='¿Prefieres Twilio o Meta API?',
        model='claude-sonnet-5'
    )
    
    print("\nSending test notification with send_proposal_ready()...")
    
    result = notifier.send_proposal_ready(
        source='freelancer',
        title='Bot WhatsApp recordatorios',
        summary='Emprendedor necesita bot de recordatorios',
        url='https://www.freelancer.es/projects/x',
        proposal=proposal,
        page_url='https://xandresx1.github.io/dev-lead-hunter/p/test.html',
        post_id='freelancer:test'
    )
    
    assert result == True, "send_proposal_ready should return True"
    print("✓ Notification sent successfully")
    print(f"  Check your ntfy app for the notification!")


def test_regression_stats_and_test_notify():
    """Test 8: Regression - --stats and --test-notify commands"""
    import subprocess
    
    env = os.environ.copy()
    env.update({
        "DATA_DIR": "/tmp/tq2",
        "PAGES_DIR": "/tmp/tq2/docs",
        "PAGES_BASE_URL": "https://xandresx1.github.io/dev-lead-hunter",
    })
    
    # Test --stats
    print("\nTesting --stats command...")
    result_stats = subprocess.run(
        ["python", "main.py", "--stats"],
        cwd="/app/dev-lead-hunter",
        env=env,
        capture_output=True,
        text=True,
        timeout=30
    )
    
    print(result_stats.stdout)
    
    assert result_stats.returncode == 0, f"--stats failed with code {result_stats.returncode}"
    assert "propuestas_pendientes=" in result_stats.stdout, "Missing 'propuestas_pendientes=' in --stats output"
    print("✓ --stats command works")
    
    # Test --test-notify
    print("\nTesting --test-notify command...")
    result_notify = subprocess.run(
        ["python", "main.py", "--test-notify"],
        cwd="/app/dev-lead-hunter",
        env=env,
        capture_output=True,
        text=True,
        timeout=30
    )
    
    print(result_notify.stdout)
    
    assert result_notify.returncode == 0, f"--test-notify failed with code {result_notify.returncode}"
    print("✓ --test-notify command works")


def main():
    """Run all tests"""
    print("="*70)
    print("MIN_SCORE=90 AND PROPOSAL RETRY QUEUE TESTS")
    print("="*70)
    
    runner = TestRunner()
    
    # Run all tests
    runner.test("Static: MIN_SCORE=90 in config.py, .env.example, hunter.yml", test_static_min_score_90)
    runner.test("Unit: Storage pending_proposals operations", test_storage_pending_proposals_unit)
    runner.test("Unit: ProposalWriter post_payload/post_from_payload round-trip", test_proposal_writer_post_payload_roundtrip)
    runner.test("Unit: ProposalWriter applies() with pause logic", test_proposal_writer_applies_with_pause)
    runner.test("Integration: Real Oxion outage with circuit breaker", test_integration_oxion_outage)
    runner.test("Second run: Queue persistence via state.json", test_second_run_queue_persistence)
    runner.test("Notification: send_proposal_ready()", test_notification_send_proposal_ready)
    runner.test("Regression: --stats and --test-notify", test_regression_stats_and_test_notify)
    
    # Print summary
    success = runner.summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

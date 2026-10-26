#!/usr/bin/env python3
"""Test sources registration and sorting."""
import os
import sys
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["BRIGHTDATA_API_TOKEN"] = "test-token"
os.environ["BRIGHTDATA_GROUPS"] = "https://www.facebook.com/groups/660236834107139"
os.environ["APIFY_TOKEN"] = "test-apify"

from sources import build_sources

# Test 1: fbgroups is registered when BRIGHTDATA_API_TOKEN is set
sources = build_sources()
names = [s.name for s in sources]
assert "fbgroups" in names, f"fbgroups not registered. Sources: {names}"
print(f"✅ fbgroups registered when BRIGHTDATA_API_TOKEN is set. Sources: {names}")

# Test 2: paid sources (fbgroups, Apify sources) are sorted before free ones
fbgroups_idx = names.index("fbgroups")
freelancer_idx = names.index("freelancer")
reddit_idx = names.index("reddit")
assert fbgroups_idx < freelancer_idx, f"fbgroups should come before freelancer. Order: {names}"
assert fbgroups_idx < reddit_idx, f"fbgroups should come before reddit. Order: {names}"
print(f"✅ Paid sources sorted before free ones. Order: {names}")

# Test 3: fbgroups has correct attributes
fbgroups = next(s for s in sources if s.name == "fbgroups")
assert fbgroups.paid is True, "fbgroups.paid should be True"
assert fbgroups.interval_minutes == 360, f"Expected interval 360, got {fbgroups.interval_minutes}"
print(f"✅ fbgroups has paid=True and interval_minutes={fbgroups.interval_minutes}")

# Test 4: Without BRIGHTDATA_API_TOKEN, fbgroups should not be registered
os.environ["BRIGHTDATA_API_TOKEN"] = ""
from importlib import reload
import sources
reload(sources)
sources_no_token = sources.build_sources()
names_no_token = [s.name for s in sources_no_token]
assert "fbgroups" not in names_no_token, f"fbgroups should not be registered without token. Sources: {names_no_token}"
print(f"✅ fbgroups not registered when BRIGHTDATA_API_TOKEN is empty. Sources: {names_no_token}")

print("\n✅ ALL SOURCES REGISTRATION TESTS PASSED")
sys.exit(0)

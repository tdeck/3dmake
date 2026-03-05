#!/usr/bin/env python3
"""Checks that the repo is in a clean, tagged state ready for release."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))  # so we can import from the repo root
from version import VERSION
from default_file_hashes import LATEST_TAG_RECORDED

BUNDLED_DIRS = ['deps/linux', 'deps/windows', 'default_config']

errors = []

# Check for uncommitted changes to tracked files
status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
dirty = [line for line in status.stdout.splitlines() if not line.startswith('??')]
if dirty:
    errors.append("Uncommitted changes in tracked files:\n" + "\n".join(f"  {l}" for l in dirty))

# Check that HEAD has a version tag matching version.py
tags = subprocess.run(['git', 'tag', '--points-at', 'HEAD'], capture_output=True, text=True)
version_tags = [t for t in tags.stdout.splitlines() if t.startswith('v')]
if not version_tags:
    errors.append("No version tag (vX.Y...) on current commit")
else:
    tag = version_tags[0]
    expected = f'v{VERSION}'
    if tag != expected:
        errors.append(f"Tag {tag!r} does not match version.py VERSION {expected!r}")

# Check that LATEST_TAG_RECORDED is the tag immediately before this release
all_version_tags = subprocess.run(
    ['git', 'tag', '-l', 'v*', '--sort=version:refname'],
    capture_output=True, text=True,
).stdout.splitlines()
current_tag = f'v{VERSION}'
if current_tag in all_version_tags:
    idx = all_version_tags.index(current_tag)
    if idx == 0:
        errors.append(f"No previous version tag found before {current_tag}")
    else:
        expected_latest = all_version_tags[idx - 1]
        if LATEST_TAG_RECORDED != expected_latest:
            errors.append(f"LATEST_TAG_RECORDED is {LATEST_TAG_RECORDED!r} but expected {expected_latest!r} (the tag before {current_tag})")

# Check for untracked files in bundled directories
for d in BUNDLED_DIRS:
    source_path = REPO_ROOT / d
    if not source_path.is_dir():
        continue
    result = subprocess.run(
        ['git', 'ls-files', '--others', str(source_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    untracked = result.stdout.strip()
    if untracked:
        errors.append(f"Untracked files in bundled directory {d}:\n" + "\n".join(f"  {f}" for f in untracked.splitlines()))

if errors:
    for e in errors:
        print(f"ERROR: {e}")
    sys.exit(1)
else:
    print(f"OK.")
    print("Remember to publish the new version JSON by regenerating the Hugo blog.")

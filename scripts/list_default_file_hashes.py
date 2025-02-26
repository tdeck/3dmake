#! /usr/bin/env python
# This enumerates the files in default_config from past releases, so we can
# determine if the user has manually altered one of their profiles, or if
# they're just using the default (and therefore it's safe to replace it with
# a newer default).
import subprocess
import os
import hashlib

def shell(cmd, raw=False):
    return subprocess.check_output(
        cmd,
        shell=True,
        encoding='utf-8' if not raw else None,
    )


version_tags = shell("git tag -l 'v*'").splitlines()

hashes_by_path: dict[str, set] = {}
os.chdir('default_config')
for tag in version_tags:
    paths = shell(f"git ls-tree --name-only -r '{tag}' .").splitlines()

    for path in paths:
        content = shell(f"git show {tag}:default_config/{path}", raw=True)
        content = content.replace(b"\r", b'') # Strip any Windows line endings
        digest = hashlib.sha256(content, usedforsecurity=False).hexdigest()

        if path not in hashes_by_path:
            hashes_by_path[path] = set()

        hashes_by_path[path].add(digest)

from pprint import pprint
print(f"# Generate by scripts/list_default_file_hashes.py")
print(f"# Latest tag recorded {version_tags[-1]}")
print("BUNDLED_PATH_HASHES = ", end='')
pprint(hashes_by_path, sort_dicts=True)

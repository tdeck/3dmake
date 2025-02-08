#! /bin/bash
# Run this from root 3dmake dir, inside pipenv
python -X importtime 3dm.py version 2>&1 1>/dev/null | sort -k3,3n

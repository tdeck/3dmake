#! /bin/bash
# This helps find configs that aren't relevant so we can remove them and reduce noise in the config files

CONFDIR="$(readlink -f $(dirname "$0")/../default_config)"
grep -r --include '*.ini' 'bed_custom_texture' "$CONFDIR"

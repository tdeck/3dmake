#! /bin/bash
base_profile_name="${1:?need base profile}"
new_profile_name="${2:?need new profile}"
source_3mf="${3:?need_3mf}"

base_ini="default_config/profiles/$base_profile_name.ini"
new_ini="default_config/profiles/$new_profile_name.ini"
# TODO check if files exist

cp "$base_profile" "$new_profile"
python scripts/3mf_settings_extractor.py "$source_3mf"  >> "$new_ini"
python scripts/reformat_config.py "$new_ini"

meld "$base_ini" "$new_ini"

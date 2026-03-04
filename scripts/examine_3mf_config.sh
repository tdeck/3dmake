#! /bin/bash

echo Metadata/slice_info.config
echo ==========================
unzip -p "$1" Metadata/slice_info.config

echo
echo Metadata/project_settings.config
echo ==============================
unzip -p "$1" Metadata/project_settings.config | python -m json.tool

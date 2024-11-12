#! /bin/bash

CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/3dmake"
SCRIPTDIR="$(dirname "$0")"

if [ -d "$CONF_DIR" ]; then
    echo "Global 3dmake config dir exists; overwrite it? (y or n)" 

    read yn

    if [[ "$yn" != "y" ]]; then
        echo 'Exiting.'
        exit 1
    fi
fi

mkdir -p "$CONF_DIR"
cp -rf "$SCRIPTDIR/default_config"/* "$CONF_DIR"
echo "Global configuration and profiles installed in $CONF_DIR"  

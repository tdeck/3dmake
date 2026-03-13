#!/bin/bash
set -e

# Ensure we are in the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# Identify shell config
SHELL_CONFIG="$HOME/.zshrc"
[[ "$SHELL" == *"/bin/bash"* ]] && SHELL_CONFIG="$HOME/.bash_profile"

ask_yes_no() {
    read -p "$1 (y/n): " choice
    case "$choice" in 
      y|Y ) return 0;;
      * ) return 1;;
    esac
}

echo "--- 3DMake macOS Build & Setup ---"

# 1. Check for Apple Silicon & Rosetta 2
if [[ "$(uname -m)" == "arm64" ]]; then
    if ! pkgutil --pkg-info=com.apple.pkg.RosettaDevelSoftware &>/dev/null; then
        echo "Rosetta 2 is recommended for some Intel-based 3D tool dependencies."
        if ask_yes_no "Install Rosetta 2 now?"; then
            softwareupdate --install-rosetta --agree-to-license
        fi
    fi
fi

# 2. Setup Homebrew
if ! command -v brew &> /dev/null; then
    if ask_yes_no "Homebrew not found. Install it now?"; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add to current path immediately for the rest of the script
        [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
        [[ -f /usr/local/bin/brew ]] && eval "$(/usr/local/bin/brew shellenv)"
    else
        echo "Homebrew is required for automated setup. Exiting."
        exit 1
    fi
fi

# 3. Check for OpenSCAD & PrusaSlicer (offer Cask install)
if [[ ! -d "/Applications/OpenSCAD.app" ]]; then
    if ask_yes_no "OpenSCAD.app not found. Install it via Homebrew Cask?"; then
        brew install --cask openscad
    fi
fi

if [[ ! -d "/Applications/PrusaSlicer.app" ]]; then
    if ask_yes_no "PrusaSlicer.app not found. Install it via Homebrew Cask?"; then
        brew install --cask prusaslicer
    fi
fi

# 4. Setup Python 3.13 & Pipenv
if ! command -v python3.13 &> /dev/null || ! command -v pipenv &> /dev/null; then
    if ask_yes_no "Install Python 3.13 and Pipenv via Homebrew?"; then
        brew install python@3.13 pipenv
        if ! grep -q "python@3.13" "$SHELL_CONFIG" 2>/dev/null; then
            echo 'export PATH="/opt/homebrew/opt/python@3.13/bin:$PATH"' >> "$SHELL_CONFIG"
            export PATH="/opt/homebrew/opt/python@3.13/bin:$PATH"
        fi
    fi
fi

# 5. Clean & Build
echo "Cleaning old build artifacts..."
rm -rf build/ dist/

echo "Installing dependencies..."
pipenv --python $(which python3.13) install --dev

echo "Building 3DMake binary..."
pipenv run pyinstaller -y 3dm.spec

# 6. Ad-hoc Code Signing (prevents "Damaged" app warnings on macOS)
if [[ -d "dist/3dmake" ]]; then
    echo "Applying ad-hoc code signature..."
    codesign --force --deep --sign - dist/3dmake/3dm
fi

# 7. Installation logic
BINARY="dist/3dmake/3dm"
if [[ -f "$BINARY" ]]; then
    echo "-----------------------------------"
    echo "Build successful!"
    if ask_yes_no "Install '3dm' to /usr/local/bin (requires sudo)?"; then
        # Clean up old installation
        sudo mkdir -p /usr/local/bin
        sudo mkdir -p /usr/local/lib
        sudo rm -rf /usr/local/lib/3dmake
        
        # Check for conflicting 3dm in PATH
        EXISTING_3DM=$(which 3dm 2>/dev/null || true)
        if [[ -n "$EXISTING_3DM" && "$EXISTING_3DM" != "/usr/local/bin/3dm" ]]; then
            echo "Found another '3dm' at: $EXISTING_3DM"
            if ask_yes_no "Remove conflicting version to ensure the new one is used?"; then
                sudo rm "$EXISTING_3DM"
            fi
        fi

        # Install new version
        sudo cp -R dist/3dmake /usr/local/lib/3dmake
        sudo ln -sf /usr/local/lib/3dmake/3dm /usr/local/bin/3dm
        
        # Ensure /usr/local/bin is in PATH
        NEEDS_SOURCE=0
        if [[ ":$PATH:" != *":/usr/local/bin:"* ]]; then
            echo "WARNING: /usr/local/bin is not in your PATH."
            if ask_yes_no "Add /usr/local/bin to your $SHELL_CONFIG?"; then
                echo 'export PATH="/usr/local/bin:$PATH"' >> "$SHELL_CONFIG"
                NEEDS_SOURCE=1
            fi
        fi

        echo "-----------------------------------"
        echo "SUCCESS: 3DMake is installed!"
        echo "Binary: /usr/local/lib/3dmake/3dm"
        echo "Symlink: /usr/local/bin/3dm"
        
        if [[ $NEEDS_SOURCE -eq 1 ]]; then
            echo ""
            echo "IMPORTANT: To use '3dm' in THIS terminal window, run:"
            echo "    source $SHELL_CONFIG"
        fi
        echo "Otherwise, just open a new terminal tab to start using '3dm'."
    else
        echo "Creating distribution zip..."
        cd dist && zip -r 3dmake_macos.zip 3dmake
        echo "Created: dist/3dmake_macos.zip"
    fi
fi

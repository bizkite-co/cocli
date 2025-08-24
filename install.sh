#!/bin/bash

# install.sh - A simple installer for the Company CLI (cocli)

echo "Installing cocli..."

# --- Configuration ---
# The directory where scripts will be installed (must be in user's PATH)
INSTALL_DIR="$HOME/.local/bin"
# The name of the main executable
EXE_NAME="cocli"
# The root directory of the source code
SOURCE_DIR=$(cd "$(dirname "$0")" && pwd)

# --- Dependency Check ---
echo -n "Checking for dependencies... "
if ! command -v fzf &> /dev/null; then
    echo
    echo "Error: fzf is not installed."
    echo "Please install fzf to continue. (e.g., 'sudo apt install fzf')"
    return 1
fi
echo "OK"

# --- Installation ---
# Ensure the installation directory exists
mkdir -p "$INSTALL_DIR"

# The full path to the source executable
SOURCE_EXE="$SOURCE_DIR/bin/$EXE_NAME"
# The full path where the symlink will be created
DEST_LINK="$INSTALL_DIR/$EXE_NAME"

echo -n "Creating symbolic link... "
# Create a symbolic link from the source to the install directory
# The -f flag ensures we overwrite any old link if it exists
ln -sf "$SOURCE_EXE" "$DEST_LINK"
if [ $? -eq 0 ]; then
    echo "OK"
else
    echo "Failed."
    echo "Could not create symbolic link at $DEST_LINK"
    return 1
fi

# --- Directory Setup ---
DEFAULT_COMPANIES_DIR="$HOME/companies"
if [ ! -d "$DEFAULT_COMPANIES_DIR" ]; then
    echo
    echo "The default companies directory ('$DEFAULT_COMPANIES_DIR') does not exist."
    read -p "Do you want to create it now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mkdir -p "$DEFAULT_COMPANIES_DIR"
        echo "Created '$DEFAULT_COMPANIES_DIR'."
    fi
fi
# --- Configuration File Setup ---
echo -n "Creating default configuration file... "
# Assuming cocli is installed and its modules are accessible
# Copy the template config file
CONFIG_DIR="$HOME/.config/cocli"
mkdir -p "$CONFIG_DIR"
cp "$SOURCE_DIR/cocli/core/cocli_config.template.toml" "$CONFIG_DIR/cocli_config.toml"
if [ $? -eq 0 ]; then
    echo "OK"
else
    echo "Failed."
    echo "Could not create default config file."
    return 1
fi


# --- Final Instructions ---
echo
echo "--------------------------------------------------"
echo "✅ cocli has been successfully installed!"
echo
echo "To use it, make sure '$INSTALL_DIR' is in your PATH."
echo "You can add it to your .bashrc or .zshrc with:"
echo "   export PATH=\"$HOME/.local/bin:\$PATH\""
echo
echo "Run 'cocli help' to get started."
echo "--------------------------------------------------"

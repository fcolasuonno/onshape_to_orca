#!/bin/bash
set -e

APP_NAME="onshape-to-orca"
APP_VERSION="1.0.0"
DEB_DIR="dist/${APP_NAME}_${APP_VERSION}_amd64"

# Ensure you run this from the project root
cd "$(dirname "$0")"

echo "Setting up environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller

echo "Building PyInstaller executable..."
# --windowed removes the console window natively
pyinstaller --name "${APP_NAME}" --windowed --onedir onshape_to_orca.py

echo "Creating Debian package structure..."
mkdir -p "${DEB_DIR}/DEBIAN"
mkdir -p "${DEB_DIR}/opt/${APP_NAME}"
mkdir -p "${DEB_DIR}/usr/bin"
mkdir -p "${DEB_DIR}/usr/share/applications"

echo "Copying application files..."
cp -r "dist/${APP_NAME}/"* "${DEB_DIR}/opt/${APP_NAME}/"

echo "Setting up executables and links..."
# We create a wrapper script instead of a symlink just in case, or a symlink is fine
# With dpkg it's easier to create the symlink directly
ln -sf "/opt/${APP_NAME}/${APP_NAME}" "${DEB_DIR}/usr/bin/${APP_NAME}"

echo "Generating DEBIAN/control..."
cat <<EOF > "${DEB_DIR}/DEBIAN/control"
Package: ${APP_NAME}
Version: ${APP_VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Local User <user@localhost>
Description: Onshape to OrcaSlicer
 A GUI application to export Onshape models and open them directly in OrcaSlicer.
EOF

echo "Generating Desktop Entry..."
cat <<EOF > "${DEB_DIR}/usr/share/applications/${APP_NAME}.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Onshape to OrcaSlicer
Comment=Export Onshape models to 3MF and open in OrcaSlicer
Exec=/opt/${APP_NAME}/${APP_NAME}
Icon=utilities-terminal
Terminal=false
Categories=Utility;Graphics;3DGraphics;
EOF

echo "Building .deb package..."
dpkg-deb --build "${DEB_DIR}"

echo "Build successful! Package located at: dist/${APP_NAME}_${APP_VERSION}_amd64.deb"

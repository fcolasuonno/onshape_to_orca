# Onshape to OrcaSlicer

A Python based tool to browse your Onshape documents and export parts/assemblies directly to OrcaSlicer as 3MF files.

## Features
- **Document Browser**: Navigate your Onshape Documents and Elements (Part Studios & Assemblies).
- **One-Click Export**: Downloads geometry as `.3mf` using Onshape's Translation API.
- **OrcaSlicer Integration**: Automatically opens the exported model in OrcaSlicer.
- **Configurable**: Persists your API keys and OrcaSlicer executable path.

## Prerequisites
- **Python 3.12+**
- **OrcaSlicer** installed.
- **Onshape API Keys** (Access Key & Secret Key) from the [Onshape Developer Portal](https://dev-portal.onshape.com/).

## Installation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

   *Note: On Linux, you might need `sudo apt-get install libxcb-cursor0` if you encounter Qt plugin errors.*

## Usage

1. **Run the Application**:
   ```bash
   python3 onshape_to_orca.py
   ```

2. **Configuration** (First Run):
   - Enter your **Onshape Access Key** and **Secret Key**.
   - Enter the full path to your **OrcaSlicer executable** (e.g., `/home/user/AppImages/OrcaSlicer.AppImage` or found in `/usr/bin/orcaslicer`).
   - Click **Save & Connect**.

3. **Exporting**:
   - Select a Document from the left list.
   - Select a Part Studio or Assembly from the right list.
   - Click **Export 3MF & Open in OrcaSlicer**.

## Troubleshooting

- **ModuleNotFoundError: No module named 'PySide6'**: Ensure you are running the script with the same python instance where you installed requirements (e.g., `python3` vs `python`).
- **qt.qpa.plugin: Could not load the Qt platform plugin "xcb"**: Install the missing library:
  ```bash
  sudo apt-get install libxcb-cursor0
  ```

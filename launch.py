#!/usr/bin/env python3
import os
import platform
import subprocess
import sys
from pathlib import Path

def compile_c_code():
    source = Path("src/functions.c")
    if not source.exists():
        print("Source file not found:", source)
        return False

    # Create shared directory if it doesn't exist
    Path("shared").mkdir(exist_ok=True)

    if platform.system() == "Windows":
        output = Path("shared/functions.dll")
        compile_command = ["gcc", "-shared", str(source), "-o", str(output)]
    else:  # Unix-like systems
        output = Path("shared/functions.so")
        compile_command = ["cc", "-shared", "-fPIC", str(source), "-o", str(output)]

    try:
        result = subprocess.run(compile_command, capture_output=True, text=True)
        if result.returncode != 0:
            print("Compilation failed:", result.stderr)
            return False
        return True
    except Exception as e:
        print("Compilation error:", e)
        return False

def launch_main():
    if platform.system() == "Windows":
        # Hide console window on Windows
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.Popen([sys.executable, "src/main.py"], 
                        startupinfo=startupinfo, 
                        creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        # Unix-like systems
        subprocess.Popen([sys.executable, "src/main.py"])

if __name__ == "__main__":
    os.chdir(Path(__file__).parent)  # Set working directory to script location
    if compile_c_code():
        launch_main()
    else:
        print("Failed to launch application due to compilation errors")
        sys.exit(1)

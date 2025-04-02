#!/usr/bin/env python3
import os
import platform
import subprocess
import sys
import shutil
from pathlib import Path

def check_cuda_available():
    """Check if CUDA is available on the system"""
    try:
        # Check for NVIDIA tools
        if platform.system() == "Windows":
            nvcc_path = shutil.which("nvcc")
            if not nvcc_path:
                return False
        else:
            nvcc_path = shutil.which("nvcc")
            if not nvcc_path:
                return False
        
        # Try to run nvcc to verify CUDA installation
        result = subprocess.run([nvcc_path, "--version"], 
                               capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return False
        
        return True
    except Exception:
        return False

def compile_c_code():
    source_c = Path("src/functions.c")
    source_cuda = Path("src/functions.cu")
    
    if not source_c.exists():
        print("Source file not found:", source_c)
        return False

    # Create shared directory if it doesn't exist
    Path("shared").mkdir(exist_ok=True)
    
    # Check if CUDA is available
    use_cuda = check_cuda_available() and source_cuda.exists()
    
    if use_cuda:
        print("CUDA detected! Compiling GPU-accelerated version...")
        if platform.system() == "Windows":
            output = Path("shared/functions_cuda.dll")
            compile_command = [
                "nvcc", "--shared", 
                "-o", str(output), str(source_cuda)
            ]
        else:  # Unix-like systems
            output = Path("shared/functions_cuda.so")
            compile_command = [
                "nvcc", "--shared", "-Xcompiler", "-fPIC",
                "-o", str(output), str(source_cuda)
            ]
        
        try:
            result = subprocess.run(compile_command, capture_output=True, text=True)
            if result.returncode == 0:
                # Set environment variable to indicate CUDA is available
                os.environ["USE_CUDA"] = "1"
                print("CUDA compilation successful.")
            else:
                print("CUDA compilation failed:", result.stderr)
                use_cuda = False
        except Exception as e:
            print("CUDA compilation error:", e)
            use_cuda = False
    
    # Always compile the CPU version as fallback
    if platform.system() == "Windows":
        output = Path("shared/functions.dll")
        compile_command = ["gcc", "-shared", str(source_c), "-o", str(output)]
    else:  # Unix-like systems
        output = Path("shared/functions.so")
        compile_command = ["cc", "-shared", "-fPIC", str(source_c), "-o", str(output)]

    try:
        result = subprocess.run(compile_command, capture_output=True, text=True)
        if result.returncode != 0:
            print("CPU compilation failed:", result.stderr)
            if use_cuda:
                print("Proceeding with CUDA version only.")
                return True
            return False
        
        if not use_cuda:
            os.environ["USE_CUDA"] = "0"
            print("Using CPU implementation.")
        
        return True
    except Exception as e:
        print("CPU compilation error:", e)
        return use_cuda  # Return True if CUDA compiled successfully

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

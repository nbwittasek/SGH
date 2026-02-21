"""CONTAM solver orchestration.

Runs contamX3.exe as a subprocess and manages file I/O.
"""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_contam_executable() -> Optional[str]:
    """Auto-detect the CONTAM executable path.

    Searches:
    1. System PATH
    2. Common install locations on Windows (including versioned folders)
    """
    # Check PATH first
    found = shutil.which("contamX3") or shutil.which("contamX3.exe")
    if found:
        return str(Path(found).resolve())

    # Common Windows install locations (exact paths)
    common_paths = [
        Path("C:/Program Files/NIST/CONTAM/contamX3.exe"),
        Path("C:/Program Files (x86)/NIST/CONTAM/contamX3.exe"),
        Path("C:/CONTAM/contamX3.exe"),
        Path("C:/Program Files/NIST/CONTAM 3.4/contamX3.exe"),
        Path("C:/Program Files/NIST/CONTAM34/contamX3.exe"),
    ]
    for p in common_paths:
        if p.exists():
            return str(p.resolve())

    # Scan NIST directories for versioned CONTAM folders (e.g. CONTAM 3.4.0.8)
    nist_dirs = [
        Path("C:/Program Files/NIST"),
        Path("C:/Program Files (x86)/NIST"),
    ]
    for nist_dir in nist_dirs:
        if nist_dir.is_dir():
            for child in nist_dir.iterdir():
                if child.is_dir() and child.name.upper().startswith("CONTAM"):
                    exe = child / "contamX3.exe"
                    if exe.exists():
                        return str(exe.resolve())

    return None


def run_contam(
    contam_exe: str,
    prj_filepath: str,
    timeout_seconds: int = 600,
) -> dict:
    """Run the CONTAM solver on a PRJ file.

    Args:
        contam_exe: Path to contamX3.exe
        prj_filepath: Path to the .prj file to solve
        timeout_seconds: Maximum time to wait for the solver

    Returns:
        dict with keys:
            success: bool
            exit_code: int
            xlog_path: str (path to the generated .xlog file)
            stdout: str
            stderr: str
            error: str (empty on success)
    """
    prj_path = Path(prj_filepath)
    xlog_path = prj_path.with_suffix(".xlog")

    if not Path(contam_exe).exists():
        return {
            "success": False,
            "exit_code": -1,
            "xlog_path": str(xlog_path),
            "stdout": "",
            "stderr": "",
            "error": f"CONTAM executable not found: {contam_exe}",
        }

    if not prj_path.exists():
        return {
            "success": False,
            "exit_code": -1,
            "xlog_path": str(xlog_path),
            "stdout": "",
            "stderr": "",
            "error": f"PRJ file not found: {prj_filepath}",
        }

    try:
        logger.info("Running CONTAM: %s %s", contam_exe, prj_filepath)
        result = subprocess.run(
            [contam_exe, str(prj_path)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(prj_path.parent),
        )

        success = result.returncode == 0 and xlog_path.exists()

        if not xlog_path.exists():
            error = "CONTAM completed but no .xlog file was generated."
        elif result.returncode != 0:
            error = f"CONTAM exited with code {result.returncode}."
        else:
            error = ""

        return {
            "success": success,
            "exit_code": result.returncode,
            "xlog_path": str(xlog_path),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": error,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -1,
            "xlog_path": str(xlog_path),
            "stdout": "",
            "stderr": "",
            "error": f"CONTAM solver timed out after {timeout_seconds} seconds.",
        }
    except OSError as e:
        return {
            "success": False,
            "exit_code": -1,
            "xlog_path": str(xlog_path),
            "stdout": "",
            "stderr": "",
            "error": f"Failed to run CONTAM: {e}",
        }

import shutil
import subprocess
from pathlib import Path

from .constants import CERT_DIR, DATA_DIR, LOG_DIR


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def ensure_certs(domain: str) -> None:
    cert_path = CERT_DIR / "cert.pem"
    key_path = CERT_DIR / "key.pem"
    if cert_path.exists() and key_path.exists():
        return
    subject = f"/C=US/ST=State/L=City/O=Organization/CN={domain}"
    cmd = [
        "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
        "-days", "365", "-keyout", str(key_path), "-out", str(cert_path),
        "-subj", subject,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def regenerate_self_signed(domain: str) -> tuple[bool, str]:
    """Force-regenerate self-signed cert even if one already exists."""
    cert_path = CERT_DIR / "cert.pem"
    key_path = CERT_DIR / "key.pem"
    subject = f"/C=US/ST=State/L=City/O=Organization/CN={domain}"
    cmd = [
        "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
        "-days", "365", "-keyout", str(key_path), "-out", str(cert_path),
        "-subj", subject,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Self-signed certificate regenerated."
    except Exception as e:
        return False, f"Failed to generate certificate: {e}"


def save_manual_cert_paths(cert_src: str, key_src: str) -> tuple[bool, str]:
    """Copy user-supplied cert/key files into /data/certs."""
    cert_path = CERT_DIR / "cert.pem"
    key_path = CERT_DIR / "key.pem"
    try:
        src_cert = Path(cert_src.strip())
        src_key = Path(key_src.strip())
        if not src_cert.exists():
            return False, f"Certificate file not found: {src_cert}"
        if not src_key.exists():
            return False, f"Key file not found: {src_key}"
        shutil.copy2(src_cert, cert_path)
        shutil.copy2(src_key, key_path)
        return True, "Manual certificates saved successfully."
    except Exception as e:
        return False, f"Failed to save certificates: {e}"



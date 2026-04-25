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


def run_certbot(domain: str, email: str) -> tuple[bool, str]:
    """Run certbot standalone and copy resulting certs. Returns (ok, message)."""
    if not shutil.which("certbot"):
        return False, "certbot is not installed or not in PATH."
    cert_path = CERT_DIR / "cert.pem"
    key_path = CERT_DIR / "key.pem"
    cmd = [
        "certbot", "certonly", "--standalone", "--non-interactive",
        "--agree-tos", "--email", email, "-d", domain,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return False, result.stderr.strip() or "certbot failed."
        # copy live certs into /data/certs
        live_dir = Path(f"/etc/letsencrypt/live/{domain}")
        shutil.copy2(live_dir / "fullchain.pem", cert_path)
        shutil.copy2(live_dir / "privkey.pem", key_path)
        return True, f"Let's Encrypt certificate obtained for {domain}."
    except subprocess.TimeoutExpired:
        return False, "certbot timed out."
    except Exception as e:
        return False, f"certbot error: {e}"

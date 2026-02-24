import subprocess

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
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-days",
        "365",
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-subj",
        subject,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

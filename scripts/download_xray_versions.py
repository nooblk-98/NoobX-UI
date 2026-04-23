import json
import platform
import sys
import urllib.request
import zipfile
from pathlib import Path


def asset_candidates() -> list[str]:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return ["Xray-linux-64.zip", "Xray-linux-amd64.zip"]
    if machine in {"aarch64", "arm64"}:
        return ["Xray-linux-arm64-v8a.zip", "Xray-linux-arm64.zip"]
    if machine.startswith("armv7") or machine.startswith("armv6"):
        return ["Xray-linux-arm32-v7a.zip", "Xray-linux-armv7.zip"]
    return ["Xray-linux-64.zip"]


def tag_candidates(tag: str) -> list[str]:
    return [tag, tag[1:]] if tag.startswith("v") else [tag, f"v{tag}"]


def read_versions(versions_file: Path) -> list[str]:
    payload = json.loads(versions_file.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        versions = payload
    else:
        versions = payload.get("versions", [])
    return [str(v).strip() for v in versions if str(v).strip()]


def download_versions(versions: list[str], versions_dir: Path) -> None:
    base = "https://github.com/XTLS/Xray-core/releases/download"
    tmp = versions_dir / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    for tag in versions:
        target = versions_dir / tag
        target.mkdir(parents=True, exist_ok=True)
        zip_path = tmp / f"{tag}.zip"
        ok = False
        for t in tag_candidates(tag):
            for asset in asset_candidates():
                url = f"{base}/{t}/{asset}"
                try:
                    urllib.request.urlretrieve(url, zip_path)
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        names = set(zf.namelist())
                        if "xray" not in names:
                            continue
                        zf.extract("xray", path=target)
                        if "geosite.dat" in names:
                            zf.extract("geosite.dat", path=target)
                        if "geoip.dat" in names:
                            zf.extract("geoip.dat", path=target)
                    (target / "xray").chmod(0o755)
                    for asset_name in ("geosite.dat", "geoip.dat"):
                        p = target / asset_name
                        if p.exists():
                            p.chmod(0o644)
                    ok = True
                    break
                except Exception:
                    pass
            if ok:
                break
        if not ok:
            print(f"Warning: failed to download {tag}", file=sys.stderr)
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            pass


def main() -> None:
    only_default = "--only-default" in sys.argv

    versions_file = Path("/opt/xray/versions.json")
    versions_dir = Path("/opt/xray/versions")
    versions_dir.mkdir(parents=True, exist_ok=True)

    if not versions_file.exists():
        print("versions.json not found.", file=sys.stderr)
        sys.exit(1)

    versions = read_versions(versions_file)
    if not versions:
        print("No versions configured.", file=sys.stderr)
        sys.exit(1)

    if only_default:
        versions = versions[:1]

    download_versions(versions, versions_dir)


if __name__ == "__main__":
    main()

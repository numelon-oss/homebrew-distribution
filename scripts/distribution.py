#!/usr/bin/env python3
"""Generate package metadata from verified, published Numelon release assets."""

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.request


STABLE_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
KEY_NAME = "numelon-oss-gh-archive-keyring.asc"
MANIFEST_VERSION = "1.12.0"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def release_url(package, tag):
    return f"https://github.com/{package['repository']}/releases/download/{tag}"


def asset_names(name, version):
    return [
        *[f"{name}-{system}-{arch}.tar.gz" for system in ("darwin", "linux") for arch in ("amd64", "arm64")],
        *[f"{name}-windows-{arch}.zip" for arch in ("amd64", "arm64")],
        *[f"{name}_{version}_{arch}.deb" for arch in ("amd64", "arm64")],
    ]


def download(url, destination, local_source=None, expected=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if expected and destination.is_file() and digest(destination) == expected:
        return
    temporary = destination.with_name(destination.name + ".download")
    try:
        if local_source is not None:
            shutil.copyfile(local_source, temporary)
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "Numelon-OSS-Distribution"})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        if expected and digest(temporary) != expected:
            raise ValueError(f"Checksum mismatch: {destination.name}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def update(root, configuration, name, tag, local_release):
    if name not in configuration["packages"]:
        raise ValueError(f"Unknown package: {name}")
    if "-" in tag:
        print(f"Ignoring prerelease {tag}; distribution channels are stable only.")
        return
    if not STABLE_TAG.fullmatch(tag):
        raise ValueError("Expected a stable tag such as v0.4.0")
    package = configuration["packages"][name]
    version = tag[1:]
    expected_names = asset_names(name, version)
    if local_release is None:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{package['repository']}/releases/tags/{tag}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Numelon-OSS-Distribution"},
        )
        token = os.environ.get("GH_TOKEN")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=60) as response:
            release = json.load(response)
        if release["draft"] or release["prerelease"]:
            print(f"Ignoring unpublished or prerelease {tag}.")
            return
        if release["tag_name"] != tag:
            raise ValueError("Release tag does not match the request")
        missing = set(expected_names + ["SHA256SUMS"]) - {asset["name"] for asset in release["assets"]}
        if missing:
            raise ValueError(f"Release is missing assets: {', '.join(sorted(missing))}")

    base_url = release_url(package, tag)
    cache = root / ".cache" / name / tag
    manifest = cache / "SHA256SUMS"
    download(f"{base_url}/SHA256SUMS", manifest,
             local_release / "SHA256SUMS" if local_release else None)
    checksums = {}
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]([^/\\]+)", line)
        if not match or match[2] in checksums:
            raise ValueError("Invalid or duplicate entry in SHA256SUMS")
        checksums[match[2]] = match[1].lower()

    assets = {}
    for filename in expected_names:
        if filename not in checksums:
            raise ValueError(f"No checksum for {filename}")
        target = cache / filename
        download(f"{base_url}/{filename}", target,
                 local_release / filename if local_release else None, checksums[filename])
        assets[filename] = {"sha256": checksums[filename], "size": target.stat().st_size}
    record = {
        "repository": package["repository"], "tag": tag, "version": version,
        "checksum_manifest_sha256": digest(manifest), "assets": assets,
    }
    destination = root / "releases" / name / f"{tag}.json"
    if destination.exists() and json.loads(destination.read_text()) != record:
        raise ValueError(f"Published assets changed for {name} {tag}; use a new release version")
    write_json(destination, record)
    print(f"Verified {len(assets)} assets for {name} {tag}.")


def records(root, configuration):
    for name, package in configuration["packages"].items():
        versions = []
        for path in (root / "releases" / name).glob("*.json"):
            record = json.loads(path.read_text())
            match = STABLE_TAG.fullmatch(record["tag"])
            if not match or record["version"] != record["tag"][1:] or record["repository"] != package["repository"]:
                raise ValueError(f"Invalid release record: {path}")
            if set(record["assets"]) != set(asset_names(name, record["version"])):
                raise ValueError(f"Unexpected release asset list: {path}")
            for metadata in record["assets"].values():
                if not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"]):
                    raise ValueError(f"Invalid checksum: {path}")
            versions.append(record)
        versions.sort(key=lambda record: tuple(map(int, record["version"].split("."))))
        yield name, package, versions


def yaml_text(value, indentation=0):
    lines = []
    prefix = " " * indentation
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(yaml_text(item, indentation + 2))
            else:
                lines.append(f"{prefix}{key}: {json.dumps(item, ensure_ascii=False)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(prefix + "-")
                lines.extend(yaml_text(item, indentation + 2))
            else:
                lines.append(prefix + "- " + json.dumps(item, ensure_ascii=False))
    return lines


def write_yaml(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = f"https://aka.ms/winget-manifest.{value['ManifestType']}.{value['ManifestVersion']}.schema.json"
    path.write_text(f"# yaml-language-server: $schema={schema}\n\n" + "\n".join(yaml_text(value)) + "\n")


def render(root, configuration):
    for name, package, versions in records(root, configuration):
        if not versions:
            continue
        latest = versions[-1]
        base_url = release_url(package, latest["tag"])
        lines = [
            f"class {''.join(word.capitalize() for word in name.split('-'))} < Formula",
            f"  desc {json.dumps(package['description'])}",
            f"  homepage {json.dumps(package['homepage'])}",
            f"  version {json.dumps(latest['version'])}",
            f"  license {json.dumps(package['license'])}",
        ]
        for system in ("macos", "linux"):
            lines.extend(["", f"  on_{system} do"])
            for architecture, selector in (("arm64", "arm"), ("amd64", "intel")):
                filename = f"{name}-{'darwin' if system == 'macos' else system}-{architecture}.tar.gz"
                lines.extend([
                    f"    on_{selector} do", f"      url {json.dumps(base_url + '/' + filename)}",
                    f"      sha256 {json.dumps(latest['assets'][filename]['sha256'])}", "    end",
                ])
            lines.append("  end")
        lines.extend(["", "  def install", f"    bin.install {json.dumps(package['command'])}", "  end", "end", ""])
        formula = root / "Formula" / f"{name}.rb"
        formula.parent.mkdir(parents=True, exist_ok=True)
        formula.write_text("\n".join(lines))

        identifier = package["winget_id"]
        for release in versions:
            version = release["version"]
            directory = root / "winget" / "manifests" / identifier[0].lower() / Path(*identifier.split(".")) / version
            common = {"PackageIdentifier": identifier, "PackageVersion": version}
            write_yaml(directory / f"{identifier}.yaml", {
                **common, "DefaultLocale": "en-US", "ManifestType": "version", "ManifestVersion": MANIFEST_VERSION,
            })
            write_yaml(directory / f"{identifier}.locale.en-US.yaml", {
                **common, "PackageLocale": "en-US", "Publisher": package["publisher"],
                "PublisherUrl": package["publisher_url"], "PackageName": name.capitalize(),
                "PackageUrl": package["homepage"], "License": package["license"],
                "LicenseUrl": f"https://github.com/{package['repository']}/blob/{release['tag']}/LICENSE",
                "ShortDescription": package["description"],
                "ReleaseNotesUrl": f"https://github.com/{package['repository']}/releases/tag/{release['tag']}",
                "ManifestType": "defaultLocale", "ManifestVersion": MANIFEST_VERSION,
            })
            installers = []
            for architecture, platform in (("amd64", "x64"), ("arm64", "arm64")):
                filename = f"{name}-windows-{architecture}.zip"
                installers.append({
                    "Architecture": platform,
                    "InstallerUrl": f"{release_url(package, release['tag'])}/{filename}",
                    "InstallerSha256": release["assets"][filename]["sha256"].upper(),
                })
            write_yaml(directory / f"{identifier}.installer.yaml", {
                **common, "InstallerType": "zip", "NestedInstallerType": "portable",
                "NestedInstallerFiles": [{"RelativeFilePath": package["command"] + ".exe", "PortableCommandAlias": package["command"]}],
                "Commands": [package["command"]], "UpgradeBehavior": "install", "Installers": installers,
                "ManifestType": "installer", "ManifestVersion": MANIFEST_VERSION,
            })
        print(f"Rendered {name}: Homebrew {latest['version']}, {len(versions)} WinGet version(s).")


def stage_apt(root, configuration):
    site = root / ".site"
    site.mkdir(exist_ok=True)
    for path in (root / "public").iterdir():
        if path.is_file():
            shutil.copyfile(path, site / path.name)
    entries = []
    for name, package, versions in records(root, configuration):
        for release in versions:
            for filename, metadata in release["assets"].items():
                if not filename.endswith(".deb"):
                    continue
                cached = root / ".cache" / name / release["tag"] / filename
                download(f"{release_url(package, release['tag'])}/{filename}", cached, expected=metadata["sha256"])
                destination = site / "pool" / "main" / name[0] / name / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cached, destination)
        if versions:
            entries.append(f'<li><a href="{html.escape(package["homepage"], quote=True)}">{html.escape(name)}</a> {versions[-1]["version"]}</li>')
    (site / "pool").mkdir(exist_ok=True)
    url = configuration["apt"]["url"]
    instructions = f'''sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL {url}/{KEY_NAME} | sudo tee /etc/apt/keyrings/{KEY_NAME} > /dev/null
sudo chmod 0644 /etc/apt/keyrings/{KEY_NAME}
sudo tee /etc/apt/sources.list.d/numelon-oss-gh.sources > /dev/null <<'EOF'
Types: deb
URIs: {url}
Suites: stable
Components: main
Architectures: amd64 arm64
Signed-By: /etc/apt/keyrings/{KEY_NAME}
EOF
sudo apt update'''
    (site / "index.html").write_text(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Numelon OSS packages</title><style>body{{max-width:54rem;margin:3rem auto;padding:0 1rem;font:1rem/1.65 system-ui;background:#fff9f4;color:#261914}}a{{color:#673b0c}}pre{{overflow:auto;padding:1rem;border:1px solid #c9b8ad;background:#f4e8dc}}</style></head>
<body><h1>Numelon OSS packages</h1><p>Stable packages published by Numelon Open Source.</p>
<ul>{''.join(entries) if entries else '<li>No packages have been published yet.</li>'}</ul>
<h2>APT</h2><p>Add this signed repository on an AMD64 or ARM64 Debian-based system, then install a package listed above using <code>sudo apt install &lt;package&gt;</code>.</p>
<pre><code>{html.escape(instructions)}</code></pre>
<p><a href="{KEY_NAME}">Public signing key</a> · <a href="https://github.com/numelon-oss/homebrew-distribution">Repository and other installation methods</a></p>
</body></html>\n''')
    print(f"Staged APT files and landing page in {site}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("update", help="Verify a release and record its assets")
    ingest.add_argument("package")
    ingest.add_argument("tag")
    ingest.add_argument("--release-dir", type=Path, help="Use local release artefacts for an offline preview")
    commands.add_parser("render", help="Generate formulae and WinGet manifests from release records")
    commands.add_parser("stage-apt", help="Download retained Debian packages and stage Pages files")
    args = parser.parse_args()
    configuration = json.loads((args.root / "packages.json").read_text())
    if args.command == "update":
        update(args.root, configuration, args.package, args.tag, args.release_dir)
        render(args.root, configuration)
    elif args.command == "render":
        render(args.root, configuration)
    else:
        stage_apt(args.root, configuration)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))

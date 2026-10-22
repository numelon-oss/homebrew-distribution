# Numelon Open Source distribution

Homebrew formulae, WinGet manifests, and the signed APT repository at
[apt-oss-gh.numelon.com](https://apt-oss-gh.numelon.com).

Applications build their own releases, whilst this repository just distributes them.

## Publishing

Add an application to `packages.json`. Its release workflow sends a
`release-published` repository dispatch with `package` and `tag` fields.
The Distribution workflow verifies checksums, records the release, generates
package metadata, and publishes APT through GitHub Pages. Only stable releases
are included. WinGet manifests are submitted as a PR to `microsoft/winget-pkgs`;
Microsoft must accept the PR before the package appears in WinGet.

The workflow can also ingest a release manually. Leave the tag empty to rebuild
the existing catalogue; pushes to `main` rebuild it too.

## Config

| Type | Name |
| --- | --- |
| Repository secret | `APT_SIGNING_PRIVATE_KEY` |
| Repository secret | `APT_SIGNING_PASSPHRASE` |
| Repository secret | `WINGET_TOKEN` |
| Repository variable | `APT_SIGNING_FINGERPRINT` |

The matching public key and fingerprint live in `public/`.

Application repositories use a `DISTRIBUTION_TOKEN` secret: a fine-grained token
with **Contents: Read and write** permission on this repository.

`WINGET_TOKEN` is a **classic PAT** with only the **public_repo** scope, owned by
the [@numelon-bot](https://github.com/numelon-bot). WinGetCreate creates its fork as needed.
Rerun Distribution with a package and tag to retry a failed submission; existing
open submissions and accepted versions are skipped.

## Files

- `packages.json`: application metadata.
- `releases/`: verified release records.
- `Formula/` and `winget/`: generated package definitions, committed by Actions.
- `scripts/`: metadata generation and APT publication.
- `public/`: public signing key and Pages files.

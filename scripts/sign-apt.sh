#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

: "${APT_SIGNING_PRIVATE_KEY:?Set the APT_SIGNING_PRIVATE_KEY repository secret}"
: "${APT_SIGNING_PASSPHRASE:?Set the APT_SIGNING_PASSPHRASE repository secret}"
: "${APT_SIGNING_FINGERPRINT:?Set the APT_SIGNING_FINGERPRINT repository variable}"

expected_fingerprint=$(printf '%s' "$APT_SIGNING_FINGERPRINT" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')
if [[ ! $expected_fingerprint =~ ^([0-9A-F]{40}|[0-9A-F]{64})$ ]]; then
    echo "APT_SIGNING_FINGERPRINT must be the full key fingerprint." >&2
    exit 1
fi

signing_dir=$(mktemp -d /tmp/numelon-apt-sign.XXXXXX)
trap 'gpgconf --homedir "$signing_dir/keyring" --kill gpg-agent || true; rm -r -- "$signing_dir"' EXIT
mkdir -m 0700 "$signing_dir/keyring"
umask 077
printf '%s\n' "$APT_SIGNING_PRIVATE_KEY" > "$signing_dir/private.asc"
printf '%s\n' "$APT_SIGNING_PASSPHRASE" > "$signing_dir/passphrase"
gpg --homedir "$signing_dir/keyring" --batch --import "$signing_dir/private.asc"

public_key=public/numelon-oss-gh-archive-keyring.asc
public_fingerprint=$(
    gpg --homedir "$signing_dir/keyring" --batch --with-colons --show-keys "$public_key" |
        awk -F: '$1 == "fpr" && !found { print $10; found = 1 }'
)
if [[ $public_fingerprint != "$expected_fingerprint" ]]; then
    echo "The configured signing fingerprint does not match the committed public key." >&2
    exit 1
fi

release=.site/dists/stable/Release
gpg --homedir "$signing_dir/keyring" --batch --yes --pinentry-mode loopback \
    --passphrase-file "$signing_dir/passphrase" --local-user "$expected_fingerprint" \
    --digest-algo SHA256 --clearsign --output .site/dists/stable/InRelease "$release"
gpg --homedir "$signing_dir/keyring" --batch --yes --pinentry-mode loopback \
    --passphrase-file "$signing_dir/passphrase" --local-user "$expected_fingerprint" \
    --digest-algo SHA256 --detach-sign --output .site/dists/stable/Release.gpg "$release"

# verify with only the committed public key (not private signing keyring)
gpg --homedir "$signing_dir/keyring" --batch --dearmor --output "$signing_dir/public.gpg" "$public_key"
gpgv --keyring "$signing_dir/public.gpg" .site/dists/stable/InRelease
gpgv --keyring "$signing_dir/public.gpg" .site/dists/stable/Release.gpg "$release"
chmod 0644 .site/dists/stable/InRelease .site/dists/stable/Release.gpg

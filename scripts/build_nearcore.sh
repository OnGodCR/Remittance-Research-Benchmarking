#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build nearcore from source on the generator.
#
# WHY THIS IS NECESSARY
#
# The cluster was pinned to nearcore 2.3.1, which implements protocol 72. Every
# current near-sdk-rs release builds contracts for a much newer protocol: the
# contract DEPLOYS successfully and then every method call fails with
# CompilationError(PrepareError(Deserialization)), because the runtime cannot
# parse a module built for a protocol it does not know. Node and SDK versions
# have to move together, and the SDK is the harder one to pin backwards.
#
# There is no prebuilt 2.13.3 binary: the GitHub release carries no assets and
# the S3 paths that served older versions return 403. So it is built here.
#
# Runs on the GENERATOR with the validators stopped, so only one machine bills
# during the build (~$0.39/hr rather than ~$1.59/hr).
# ---------------------------------------------------------------------------
set -uo pipefail
VER="${1:-2.13.3}"
OUT=/opt/benchmark/neard

if [ -x "$OUT" ]; then
  echo "  already built: $("$OUT" --version 2>&1 | head -1)"
  exit 0
fi

export CARGO_HOME=/opt/rust/cargo RUSTUP_HOME=/opt/rust/rustup
export PATH="$CARGO_HOME/bin:$PATH"

echo "  installing build dependencies"
apt-get update -y >/dev/null 2>&1
apt-get install -y git clang llvm cmake pkg-config libssl-dev build-essential python3 >/dev/null 2>&1

if [ ! -x "$CARGO_HOME/bin/cargo" ]; then
  curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --no-modify-path >/dev/null 2>&1
fi

if [ ! -d /opt/nearcore ]; then
  echo "  cloning nearcore $VER"
  git clone --depth 1 --branch "$VER" https://github.com/near/nearcore /opt/nearcore >/dev/null 2>&1 \
    || { echo "  clone failed for tag $VER"; exit 1; }
fi

cd /opt/nearcore
# nearcore pins its own toolchain in rust-toolchain.toml; rustup honours it.
echo "  building (this takes 45-90 minutes)"
cargo build -p neard --release >/tmp/nearcore_build.log 2>&1
RC=$?
if [ "$RC" -ne 0 ] || [ ! -x /opt/nearcore/target/release/neard ]; then
  echo "  BUILD FAILED (rc=$RC)"
  grep -m5 -E "^error" /tmp/nearcore_build.log || tail -15 /tmp/nearcore_build.log
  exit 1
fi
cp /opt/nearcore/target/release/neard "$OUT"
chmod 755 "$OUT"
echo "  built: $("$OUT" --version 2>&1 | head -1)"

#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build the NEP-141 stablecoin contract the NEAR runs move.
#
# WHY THIS SCRIPT NOW EXISTS
#
# scripts/near_bootstrap.py has always told the operator to "run
# scripts/build_ft.sh first", and that script was never in the repository. It
# lived only on the generator's disk. When the cluster was rebuilt the disk
# went with it, and the whole NEAR deployment stopped at the token step.
#
# The version was not written down anywhere either -- not in the methodology
# log, not in the NEAR write-up. That is the more serious half of the problem,
# because gas per transfer is a published figure (2.214 x 10^12) and it depends
# on the contract that produced it. The pin below fixes it going forward.
#
# WHAT IS BUILT
#
# near-contract-standards' own fungible-token example: the reference NEP-141
# implementation, the one real stablecoins on NEAR are derived from. Not a
# hand-written contract, so nobody has to take our word for what it does.
#
# The SDK and the node have to move together. nearcore 2.13.3 speaks protocol
# 86 and refuses anything built for a protocol it does not know -- the contract
# DEPLOYS and then every call fails with CompilationError(PrepareError(
# Deserialization)), which is a confusing way to find out. That failure is why
# the node was built from source in the first place (scripts/build_nearcore.sh).
#
# The pinned SDK release is from within three weeks of the node commit
# (nearcore 2.13.3 is 4 Aug 2026), so they belong to the same era of the
# protocol rather than being matched by guesswork.
#
# Runs on the generator, where the Rust toolchain already is.
# ---------------------------------------------------------------------------
set -uo pipefail

SDK_TAG="${1:-near-sdk-v5.29.0}"
OUT=/opt/benchmark/fungible_token.wasm

if [ -f "$OUT" ]; then
  echo "  already built: $OUT ($(stat -c %s "$OUT") bytes)"
  exit 0
fi

export CARGO_HOME=/opt/rust/cargo RUSTUP_HOME=/opt/rust/rustup
export PATH="$CARGO_HOME/bin:$PATH"

if [ ! -x "$CARGO_HOME/bin/cargo" ]; then
  echo "  no Rust toolchain -- run scripts/build_nearcore.sh first"; exit 1
fi

rustup target add wasm32-unknown-unknown >/dev/null 2>&1

# target-cpu=mvp holds the output to WebAssembly's original feature set.
# Without it a current compiler emits newer WebAssembly features, the contract
# DEPLOYS fine and then every call fails with CompilationError(PrepareError(
# Deserialization)) -- the runtime cannot parse a module built for a version of
# WebAssembly it does not know. The node is only two and a half weeks older
# than this SDK release, so it should not be needed; it costs nothing and turns
# a confusing runtime failure into a non-event.
export RUSTFLAGS="-C target-cpu=mvp -C link-arg=-s"

if [ ! -d /opt/near-sdk-rs ]; then
  echo "  cloning near-sdk-rs $SDK_TAG"
  git clone --depth 1 --branch "$SDK_TAG" https://github.com/near/near-sdk-rs /opt/near-sdk-rs >/dev/null 2>&1 \
    || { echo "  clone failed for tag $SDK_TAG"; exit 1; }
fi

SRC=/opt/near-sdk-rs/examples/fungible-token
[ -d "$SRC" ] || { echo "  fungible-token example not found at $SRC"; ls /opt/near-sdk-rs/examples; exit 1; }

cd "$SRC"
echo "  building the contract to WebAssembly"
cargo build -p fungible-token --target wasm32-unknown-unknown --release \
  >/tmp/ft_build.log 2>&1
RC=$?

WASM=$(find /opt/near-sdk-rs -path "*wasm32-unknown-unknown/release/*.wasm" \
       -name "fungible_token*.wasm" 2>/dev/null | head -1)
if [ "$RC" -ne 0 ] || [ -z "$WASM" ]; then
  echo "  BUILD FAILED (rc=$RC)"
  grep -m5 -E "^error" /tmp/ft_build.log || tail -15 /tmp/ft_build.log
  exit 1
fi

cp "$WASM" "$OUT"
chmod 644 "$OUT"
echo "  built: $OUT ($(stat -c %s "$OUT") bytes) from near-sdk-rs $SDK_TAG"

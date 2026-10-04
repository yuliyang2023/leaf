#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -m)" = x86_64
TARGET=mipsel-unknown-linux-musl
TOOLCHAIN=mipsel-unknown-linux-muslsf
RUST_VERSION=nightly-2026-10-04
TOOLCHAIN_SHA256=93fcfc5e8d28096941df04c3c5bc56b653d8aa81f8634671f236e0f443a451b6
UPX_SHA256=402162aad30af47e60dbd767fb2e64ca394ace9727ba1f40283641f1d1b91657
BUILD_TEMP=$(mktemp -d)
trap 'rm -rf "$BUILD_TEMP"' EXIT
APT=()
if [ "$(id -u)" != 0 ]; then APT=(sudo); fi
"${APT[@]}" apt-get update -qq
"${APT[@]}" apt-get install -y -qq build-essential perl pkg-config libclang-dev qemu-user python3 curl ca-certificates xz-utils git file
if ! command -v rustup >/dev/null; then
    curl -fsSL --retry 3 -o "$BUILD_TEMP/rustup-init.sh" https://sh.rustup.rs
    sh "$BUILD_TEMP/rustup-init.sh" -y --profile minimal --default-toolchain none
fi
export PATH="$HOME/.cargo/bin:$PATH"
rustup toolchain install "$RUST_VERSION" --profile minimal --component rust-src
rustup override set "$RUST_VERSION"
curl -fL --retry 3 -o "$BUILD_TEMP/toolchain.tar.xz" "https://github.com/cross-tools/musl-cross/releases/download/20261001/$TOOLCHAIN.tar.xz"
echo "$TOOLCHAIN_SHA256  $BUILD_TEMP/toolchain.tar.xz" | sha256sum -c
tar -xJf "$BUILD_TEMP/toolchain.tar.xz" -C "$BUILD_TEMP"
compiler="$BUILD_TEMP/$TOOLCHAIN/bin/$TOOLCHAIN"
export CARGO_TARGET_MIPSEL_UNKNOWN_LINUX_MUSL_LINKER="$compiler-gcc"
export CC_mipsel_unknown_linux_musl="$compiler-gcc"
export AR_mipsel_unknown_linux_musl="$compiler-ar"
export CFLAGS_mipsel_unknown_linux_musl='-Os -march=24kec -mabi=32 -msoft-float'
unwind_archive=$("$compiler-gcc" -print-file-name=libgcc_eh.a)
test -f "$unwind_archive"
"$compiler-nm" "$unwind_archive" | grep '_Unwind_Resume' > "$BUILD_TEMP/unwind-symbols.txt"
mkdir "$BUILD_TEMP/unwind"
ln -s "$unwind_archive" "$BUILD_TEMP/unwind/libunwind.a"
export RUSTFLAGS="-C target-cpu=mips32r2 -C target-feature=+soft-float,+crt-static -C link-self-contained=no -C link-arg=-static -C link-arg=-Wl,--gc-sections -L native=$BUILD_TEMP/unwind"
export OPENSSL_STATIC=1
export CARGO_BUILD_JOBS=4
cargo build -Z build-std=std,panic_abort --profile oray --target "$TARGET" -p leaf-oray --features websocket
mkdir -p dist
binary=leaf-oray-vmess-ws
cp "target/$TARGET/oray/leaf-oray" "dist/$binary"
cargo tree -p leaf-oray --features websocket --edges features --target "$TARGET" > dist/FEATURES.txt
cp Cargo.lock dist/Cargo.lock
rustc -Vv > dist/BUILD-INFO.txt
git rev-parse HEAD >> dist/BUILD-INFO.txt
file "dist/$binary" > dist/ELF.txt
"$compiler-readelf" -h -A "dist/$binary" >> dist/ELF.txt
if "$compiler-readelf" -l "dist/$binary" | grep -q INTERP; then exit 1; fi
timeout 15 qemu-mipsel -cpu 24KEc "dist/$binary" -V
python3 scripts/oray-ws-smoke.py "dist/$binary"
curl -fL --retry 3 -o "$BUILD_TEMP/upx.tar.xz" https://github.com/upx/upx/releases/download/v5.2.1/upx-5.2.1-amd64_linux.tar.xz
echo "$UPX_SHA256  $BUILD_TEMP/upx.tar.xz" | sha256sum -c
tar -xJf "$BUILD_TEMP/upx.tar.xz" -C "$BUILD_TEMP"
upx="$BUILD_TEMP/upx-5.2.1-amd64_linux/upx"
"$upx" --best --lzma -o "dist/$binary-upx" "dist/$binary" > dist/UPX.txt 2>&1
"$upx" -t "dist/$binary-upx" >> dist/UPX.txt
timeout 15 qemu-mipsel -cpu 24KEc "dist/$binary-upx" -V
python3 scripts/oray-ws-smoke.py "dist/$binary-upx"
cp leaf-oray/leaf.vmess-ws.example.json ORAY-X1-WS.md LICENSE dist/
cd dist
gzip -9 -n -k "$binary"
sha256sum "$binary" "$binary.gz" "$binary-upx" > SHA256SUMS
printf '%s\n' '| File | Bytes | MiB |' '|---|---:|---:|' > SIZES.md
for item in "$binary" "$binary.gz" "$binary-upx"; do
    size=$(stat -c %s "$item")
    awk -v file="$item" -v bytes="$size" 'BEGIN {printf "| %s | %d | %.3f |\n", file, bytes, bytes/1048576}' >> SIZES.md
done
cat SIZES.md
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then cat SIZES.md >> "$GITHUB_STEP_SUMMARY"; fi

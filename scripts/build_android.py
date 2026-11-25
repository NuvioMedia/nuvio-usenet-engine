#!/usr/bin/env python3
"""Build all Android sidecars and record their source/binary correspondence."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from check_prebuilts import ABIS, ROOT, record, source_digest

TARGETS = (("arm64", "aarch64-linux-android"), ("arm", "armv7a-linux-androideabi"),
           ("amd64", "x86_64-linux-android"), ("386", "i686-linux-android"))

RUNTIME_TIME_FILE = Path("src") / "runtime" / "os_linux32.go"
RUNTIME_TIME_ANCHOR = "func configure64bitsTimeOn32BitsArchitectures() {\n"
RUNTIME_TIME_PATCH = """\t// Android 8.0-10 app seccomp filters kill the process on the time64
\t// syscalls even on kernels >= 5.1, and every Android filter allows the
\t// 32-bit variants, so Android always uses them (golang/go#83366).
\tif GOOS == "android" {
\t\tuse64bitsTimeOn32bits = false
\t\treturn
\t}
"""


def android_time32_goroot(go, workdir):
    """Return a GOROOT copy whose 32-bit Android runtime uses the time32 syscalls.

    Go chooses futex_time64 and timer_settime64 from the kernel version alone,
    so a 32-bit app on Android 8.0-10 with a kernel >= 5.1 (Fire OS 7 on a 5.4
    kernel, for example) is killed by SIGSYS before the sidecar starts. The
    patched file is only compiled for 32-bit targets, so 64-bit binaries are
    unchanged. Returns None when the toolchain already handles Android.
    """
    source = Path(subprocess.check_output([go, "env", "GOROOT"], text=True).strip())
    text = (source / RUNTIME_TIME_FILE).read_text()
    if text.count(RUNTIME_TIME_ANCHOR) != 1:
        raise RuntimeError(f"{source / RUNTIME_TIME_FILE} changed; review the Android time32 runtime patch")
    body = text.split(RUNTIME_TIME_ANCHOR, 1)[1].split("\n}\n", 1)[0]
    if 'GOOS == "android"' in body:
        return None
    goroot = workdir / "go"
    shutil.copytree(source, goroot, symlinks=True)
    (goroot / RUNTIME_TIME_FILE).write_text(text.replace(RUNTIME_TIME_ANCHOR, RUNTIME_TIME_ANCHOR + RUNTIME_TIME_PATCH))
    return goroot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path, required=True)
    parser.add_argument("--go", default="go")
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--release-repository", required=True, help="GitHub owner/repo that will host the versioned native assets")
    parser.add_argument("--host", default="linux-x86_64", choices=("linux-x86_64", "darwin-x86_64", "windows-x86_64"))
    args = parser.parse_args()
    args.ndk = args.ndk.resolve()
    before = source_digest()
    toolchain = args.ndk / "toolchains" / "llvm" / "prebuilt" / args.host / "bin"
    suffix = ".cmd" if args.host == "windows-x86_64" else ""
    outputs = []
    workdir = Path(tempfile.mkdtemp(prefix="nuvio-usenet-go-"))
    try:
        goroot = android_time32_goroot(args.go, workdir)
        go = str(goroot / "bin" / ("go.exe" if os.name == "nt" else "go")) if goroot else args.go
        for abi, (arch, target) in zip(ABIS, TARGETS):
            build = ROOT / "build" / "prebuilt" / abi
            subprocess.run([args.cmake, "-S", str(ROOT / "third_party" / "rapidyenc-native"), "-B", str(build),
                            f"-DCMAKE_TOOLCHAIN_FILE={args.ndk / 'build' / 'cmake' / 'android.toolchain.cmake'}",
                            f"-DANDROID_ABI={abi}", "-DANDROID_PLATFORM=android-24", "-DANDROID_STL=c++_static",
                            "-DCMAKE_BUILD_TYPE=Release", "-DDISABLE_SHARED=ON", "-DDISABLE_TOOL=ON", "-DDISABLE_CRC=ON"], check=True)
            subprocess.run([args.cmake, "--build", str(build), "--target", "rapidyenc_static", "-j", "4"], check=True)
            shutil.copyfile(build / "rapidyenc_static" / "librapidyenc.a",
                            ROOT / "third_party" / "rapidyenc" / f"librapidyenc_android_{arch}.a")
            env = dict(os.environ, GOOS="android", GOARCH=arch, CGO_ENABLED="1", GOTOOLCHAIN="local",
                       CC=str(toolchain / f"{target}24-clang{suffix}"), CXX=str(toolchain / f"{target}24-clang++{suffix}"))
            if goroot:
                env["GOROOT"] = str(goroot)
            if arch == "arm":
                env["GOARM"] = "7"
            output = build / "libnuvio_usenet.so"
            # CGO action IDs include toolchain paths; omit the Go build ID so
            # identical code has identical release checksums across build hosts.
            subprocess.run([go, "build", "-trimpath", "-buildvcs=false", "-buildmode=pie",
                            "-ldflags=-s -w -buildid= -extldflags=-Wl,-z,max-page-size=16384", "-o", str(output), "./cmd/nuvio-usenet"],
                           cwd=ROOT, env=env, check=True)
            outputs.append((abi, output))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if before != source_digest():
        raise RuntimeError("Usenet source changed during the build; prebuilts were not replaced")
    for abi, output in outputs:
        destination = ROOT / "prebuilt" / abi / "libnuvio_usenet.so"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output, destination)
    go_version = subprocess.check_output([args.go, "version"], text=True).strip()
    ndk_version = next(line.split("=", 1)[1].strip() for line in (args.ndk / "source.properties").read_text().splitlines()
                       if line.startswith("Pkg.Revision"))
    record(go_version, ndk_version, args.release_repository)


if __name__ == "__main__":
    main()

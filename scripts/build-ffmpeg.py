"""Build an audio-only, LGPL-2.1+ FFmpeg for PyAV wheels.

This is a reduced fork of PyAV-Org/pyav-ffmpeg (tag 8.0.1-3, the build used
for the av 16.1.0 PyPI wheels). Differences from upstream:

- No GPL components: x264/x265 are gone, and so is upstream's
  ``patches/ffmpeg.patch`` which relabelled them as ``version3`` libraries.
  The build uses neither ``--enable-gpl`` nor ``--enable-version3``, so the
  resulting libraries are plain "LGPL version 2.1 or later".
- Audio-only: ``--disable-everything --disable-autodetect`` plus exactly the
  components the aiortc/PyAV voice stack needs — the libopus encoder/decoder,
  the PCM A-law/mu-law and G.722 codecs, and the libavfilter pieces behind
  PyAV's AudioResampler. No video codecs, encoders, decoders, muxers,
  demuxers, protocols or hardware acceleration of any kind.
- All seven FFmpeg libraries (avcodec, avdevice, avfilter, avformat, avutil,
  swresample, swscale) are still built — PyAV links them all at import time.

The only third-party library built is libopus (BSD-3-Clause).
"""

import argparse
import concurrent.futures
import glob
import hashlib
import os
import platform
import shutil
import subprocess
import sys

from cibuildpkg import Builder, Package, fetch, run

plat = platform.system()
is_musllinux = plat == "Linux" and platform.libc_ver()[0] != "glibc"


def calculate_sha256(filename: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(filename, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


opus_package = Package(
    name="opus",
    source_url="https://ftp.osuosl.org/pub/xiph/releases/opus/opus-1.6.tar.gz",
    sha256="b7637334527201fdfd6dd6a02e67aceffb0e5e60155bbd89175647a80301c92c",
    build_arguments=["--disable-doc", "--disable-extra-programs"],
)

ffmpeg_package = Package(
    name="ffmpeg",
    source_url="https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz",
    sha256="05ee0b03119b45c0bdb4df654b96802e909e0a752f72e4fe3794f487229e5a41",
    build_arguments=[],
    build_parallel=plat != "Windows",
)


def download_and_verify_package(package: Package) -> None:
    tarball = os.path.join(
        os.path.abspath("source"),
        package.source_filename or package.source_url.split("/")[-1],
    )

    if not os.path.exists(tarball):
        try:
            fetch(package.source_url, tarball)
        except subprocess.CalledProcessError:
            pass

    if not os.path.exists(tarball):
        raise ValueError(f"tar bar doesn't exist: {tarball}")

    sha = calculate_sha256(tarball)
    if package.sha256 == sha:
        print(f"{package.name} tarball: hashes match")
    else:
        raise ValueError(
            f"sha256 hash of {package.name} tarball do not match!\nExpected: {package.sha256}\nGot: {sha}"
        )


def download_tars(packages: list[Package]) -> None:
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_package = {
            executor.submit(download_and_verify_package, package): package.name
            for package in packages
        }

        for future in concurrent.futures.as_completed(future_to_package):
            name = future_to_package[future]
            try:
                future.result()
            except Exception as exc:
                print(f"{name} generated an exception: {exc}")
                raise


def make_tarball_name() -> str:
    isArm64 = platform.machine() in {"arm64", "aarch64"}

    if sys.platform.startswith("win"):
        return "ffmpeg-windows-aarch64" if isArm64 else "ffmpeg-windows-x86_64"
    elif sys.platform.startswith("linux"):
        if is_musllinux:
            return "ffmpeg-musllinux-aarch64" if isArm64 else "ffmpeg-musllinux-x86_64"
        else:
            return "ffmpeg-manylinux-aarch64" if isArm64 else "ffmpeg-manylinux-x86_64"
    elif sys.platform.startswith("darwin"):
        return "ffmpeg-macos-arm64" if isArm64 else "ffmpeg-macos-x86_64"
    else:
        return "ffmpeg-unknown"


def main():
    parser = argparse.ArgumentParser("build-ffmpeg")
    parser.add_argument("destination")
    args = parser.parse_args()

    dest_dir = os.path.abspath(args.destination)

    output_dir = os.path.abspath("output")
    if plat == "Linux" and os.environ.get("CIBUILDWHEEL") == "1":
        output_dir = "/output"

    output_tarball = os.path.join(output_dir, make_tarball_name() + ".tar.gz")
    if os.path.exists(output_tarball):
        return

    builder = Builder(dest_dir=dest_dir)
    builder.create_directories()

    # install packages
    available_tools = set()
    if plat == "Windows":
        available_tools.update(["nasm"])

        # print tool locations
        print("PATH", os.environ["PATH"])
        for tool in ["gcc", "g++", "curl", "ld", "nasm", "pkg-config"]:
            run(["where", tool])

    # build tools
    build_tools = []
    if "nasm" not in available_tools and platform.machine() not in {"arm64", "aarch64"}:
        build_tools.append(
            Package(
                name="nasm",
                source_url="https://www.nasm.us/pub/nasm/releasebuilds/2.16.03/nasm-2.16.03.tar.xz",
                sha256="1412a1c760bbd05db026b6c0d1657affd6631cd0a63cddb6f73cc6d4aa616148",
            )
        )

    ffmpeg_package.build_arguments = [
        "--disable-programs",
        "--disable-doc",
        # Start from nothing: no components, no autodetected external libs
        # (also drops iconv/zlib/lzma/schannel/appleframeworks and every
        # hardware acceleration path).
        "--disable-everything",
        "--disable-autodetect",
        # Threading is autodetected, so re-enable it explicitly: FFmpeg's
        # native w32threads on Windows (the MINGW64 pthreads probe fails with
        # autodetect off), pthreads elsewhere.
        "--enable-w32threads" if plat == "Windows" else "--enable-pthreads",
        # The aiortc/PyAV voice stack: Opus via libopus (aiortc asks for the
        # "libopus" codec by name), plus aiortc's G.711/G.722 fallbacks.
        "--enable-libopus",
        "--enable-encoder=libopus,pcm_alaw,pcm_mulaw,adpcm_g722",
        "--enable-decoder=libopus,pcm_alaw,pcm_mulaw,adpcm_g722",
        # PyAV's AudioResampler drives a libavfilter graph: abuffer ->
        # aformat -> abuffersink, with aresample auto-inserted during format
        # negotiation.
        "--enable-filter=abuffer,abuffersink,aformat,aresample",
    ]

    if plat == "Darwin":
        ffmpeg_package.build_arguments.append("--extra-ldflags=-Wl,-ld_classic")

    packages = [opus_package, ffmpeg_package]

    download_tars(build_tools + packages)
    for tool in build_tools:
        builder.build(tool, for_builder=True)
    for package in packages:
        builder.build(package)

    if plat == "Windows":
        # fix .lib files being installed in the wrong directory
        for name in (
            "avcodec",
            "avdevice",
            "avfilter",
            "avformat",
            "avutil",
            "postproc",
            "swresample",
            "swscale",
        ):
            if os.path.exists(os.path.join(dest_dir, "bin", name + ".lib")):
                shutil.move(
                    os.path.join(dest_dir, "bin", name + ".lib"),
                    os.path.join(dest_dir, "lib"),
                )

        # copy the mingw runtime libraries the FFmpeg DLLs link against
        mingw_bindir = os.path.dirname(
            subprocess.run(["where", "gcc"], check=True, stdout=subprocess.PIPE)
            .stdout.decode()
            .splitlines()[0]
            .strip()
        )
        for name in (
            "libgcc_s_seh-1.dll",
            "libwinpthread-1.dll",
        ):
            shutil.copy(os.path.join(mingw_bindir, name), os.path.join(dest_dir, "bin"))

    # find libraries
    if plat == "Darwin":
        libraries = glob.glob(os.path.join(dest_dir, "lib", "*.dylib"))
    elif plat == "Linux":
        libraries = glob.glob(os.path.join(dest_dir, "lib", "*.so"))
    elif plat == "Windows":
        libraries = glob.glob(os.path.join(dest_dir, "bin", "*.dll"))

    # strip libraries
    if plat == "Darwin":
        run(["strip", "-S"] + libraries)
        run(["otool", "-L"] + libraries)
    else:
        run(["strip", "-s"] + libraries)

    # build output tarball; the audio-only build installs no programs, so
    # bin/ may not exist on non-Windows platforms
    os.makedirs(os.path.join(dest_dir, "bin"), exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    run(["tar", "czvf", output_tarball, "-C", dest_dir, "bin", "include", "lib"])


if __name__ == "__main__":
    main()

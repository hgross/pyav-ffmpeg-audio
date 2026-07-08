"""Smoke test and licence gate for the audio-only LGPL PyAV wheel.

Run against a freshly built wheel (cibuildwheel test step). Fails if the
bundled FFmpeg contains GPL configure flags or any video codec, or if the
audio path used by aiortc voice (libopus encode/decode, AudioResampler)
does not work.
"""

import sys

import av
import numpy as np
from av._core import library_meta

# The licence-relevant fingerprint of the audio-only build.
FORBIDDEN_CONFIGURE = ("--enable-gpl", "--enable-nonfree", "--enable-version3", "libx264", "libx265")
REQUIRED_CONFIGURE = ("--disable-everything", "--disable-autodetect", "--enable-libopus")
REQUIRED_CODECS = ("libopus", "pcm_alaw", "pcm_mulaw", "adpcm_g722")
FORBIDDEN_CODECS = (
    "libx264", "libx265", "libopenh264", "h264", "hevc",
    "libvpx", "libaom-av1", "libsvtav1", "mpeg4", "vp8", "vp9", "av1",
    "mjpeg", "aac", "mp3", "libmp3lame", "vorbis", "libvorbis",
)

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def main() -> int:
    print(f"av {av.__version__}, FFmpeg {av.ffmpeg_version_info}")

    # --- licence / build-flavour gate ------------------------------------
    for name, meta in library_meta.items():
        cfg = meta["configuration"]
        lic = meta["license"]
        for flag in FORBIDDEN_CONFIGURE:
            check(flag not in cfg, f"{name}: configuration free of {flag}")
        for flag in REQUIRED_CONFIGURE:
            check(flag in cfg, f"{name}: configuration contains {flag}")
        check(lic.startswith("LGPL version 2.1"), f"{name}: licence is LGPL 2.1+ (got {lic!r})")

    avail = av.codecs_available
    for codec in REQUIRED_CODECS:
        check(codec in avail, f"codec available: {codec}")
    for codec in FORBIDDEN_CODECS:
        check(codec not in avail, f"codec absent: {codec}")

    # --- the exact voice path used by ApexRelay Pilot + aiortc ------------
    # 20 ms of 440 Hz s16 mono at 48 kHz, as produced by the Pilot microphone track.
    sample_rate = 48000
    samples = (np.sin(2 * np.pi * 440 * np.arange(960) / sample_rate) * 10000).astype(np.int16)
    frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = sample_rate
    frame.pts = 0

    # AudioResampler drives a libavfilter graph (abuffer/aformat/aresample/abuffersink).
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    out = resampler.resample(frame)
    check(bool(out) and out[0].to_ndarray().size > 0, "AudioResampler resample round-trip")

    # Opus encode/decode exactly as aiortc.codecs.opus does it.
    encoder = av.CodecContext.create("libopus", "w")
    encoder.bit_rate = 96000
    encoder.format = "s16"
    encoder.layout = "stereo"
    encoder.options = {"application": "voip"}
    encoder.sample_rate = sample_rate
    enc_resampler = av.AudioResampler(format="s16", layout="stereo", rate=sample_rate, frame_size=960)

    packets = []
    for resampled in enc_resampler.resample(frame):
        packets += encoder.encode(resampled)
    packets += encoder.encode(None)  # flush
    check(bool(packets), f"libopus encode produced packets ({len(packets)})")

    decoder = av.CodecContext.create("libopus", "r")
    decoder.format = "s16"
    decoder.layout = "stereo"
    decoder.sample_rate = sample_rate
    decoded = []
    for packet in packets:
        decoded += decoder.decode(packet)
    check(bool(decoded) and decoded[0].to_ndarray().size > 0,
          f"libopus decode produced audio ({len(decoded)} frames)")

    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

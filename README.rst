pyav-ffmpeg-audio
=================

Audio-only, LGPL-2.1-or-later FFmpeg builds for `PyAV`_ wheels, plus the
matching ``av`` wheels themselves. This is a reduced fork of
`PyAV-Org/pyav-ffmpeg`_ (branched from tag ``8.0.1-3``, the build behind the
``av`` 16.1.0 PyPI wheels), created for the voice feature of ApexRelay Pilot,
which needs PyAV/aiortc audio without the GPL and patent baggage of the stock
PyPI wheels.

Why this fork exists
--------------------

The official ``av`` wheels on PyPI bundle an FFmpeg that dynamically links
GPL-2.0-or-later ``libx264`` and ``libx265`` binaries. Upstream additionally
patches FFmpeg's ``configure`` so those libraries are accepted without
``--enable-gpl`` and the binaries self-report "LGPL version 3 or later" —
but linking GPL x264/x265 makes the combined distribution effectively GPL
regardless of the label (see `PyAV issue #2270`_). That makes the stock
wheels unusable inside proprietary applications.

This fork instead builds FFmpeg 8.0.1:

- **without** ``--enable-gpl``, **without** ``--enable-version3``, and
  **without** upstream's configure-relabelling patch — the resulting
  libraries are plain **LGPL version 2.1 or later**;
- **audio-only**: ``--disable-everything --disable-autodetect`` plus exactly
  the components the aiortc/PyAV voice stack needs:

  - the ``libopus`` encoder and decoder (`libopus`_ is BSD-3-Clause, the only
    third-party library in the build),
  - the ``pcm_alaw``, ``pcm_mulaw`` and ``adpcm_g722`` codecs (aiortc's
    G.711/G.722 fallbacks),
  - the ``abuffer``, ``abuffersink``, ``aformat`` and ``aresample`` filters
    (the libavfilter graph behind PyAV's ``AudioResampler``).

  No video codecs, no muxers/demuxers, no protocols, no devices, no hardware
  acceleration — which also removes the H.264/H.265 patent-pool exposure of
  the stock wheels entirely.

All seven FFmpeg libraries (``avcodec``, ``avdevice``, ``avfilter``,
``avformat``, ``avutil``, ``swresample``, ``swscale``) are still built and
shipped, because PyAV links all of them at import time.

The ``av`` wheels built from these libraries carry a PEP 440 local version
label (e.g. ``16.1.0+lgpl.audio.1``) so the build flavour is visible in
``pip list`` and at runtime via ``av.__version__``. Every wheel passes
``scripts/wheel_smoke_test.py``, which fails on GPL configure flags, on any
available video codec, and on a broken Opus/resampler audio path.

Artifacts
---------

GitHub releases on this repository contain:

- ``ffmpeg-windows-x86_64.tar.gz`` / ``ffmpeg-macos-arm64.tar.gz`` — the
  FFmpeg dev trees (``bin``, ``include``, ``lib`` with import libraries and
  pkg-config files),
- ``av-16.1.0+*.whl`` — PyAV wheels (CPython 3.12/3.13) built against those
  libraries,
- the **exact source tarballs** (``ffmpeg-8.0.1.tar.xz``, ``opus-1.6.tar.gz``)
  used for the binaries, for LGPL source-availability purposes. The complete
  build configuration is this repository itself (see
  ``scripts/build-ffmpeg.py`` for the configure line).

Building
--------

Builds run via the ``build`` GitHub Actions workflow (``workflow_dispatch``
only — repository write access is required to trigger it) on
``windows-latest`` (MSYS2/MINGW64) and ``macos-14`` (arm64). The wheel jobs
check out ``PyAV-Org/PyAV`` at ``v16.1.0`` unmodified except for the version
stamp, compile it against the freshly built FFmpeg (MSVC + ``delvewheel`` on
Windows, ``delocate`` on macOS) and run the smoke test.

To reproduce locally, run ``python scripts/build-ffmpeg.py <dest>`` with the
platform toolchain described in the workflow file.

LGPL notice
-----------

FFmpeg is licensed under the GNU Lesser General Public License (LGPL)
version 2.1 or later; see the license texts shipped inside the FFmpeg source
tarball attached to each release. Applications bundling these libraries must
ship them as separate, replaceable files and provide access to this source.

.. _PyAV: https://github.com/PyAV-Org/PyAV
.. _PyAV-Org/pyav-ffmpeg: https://github.com/PyAV-Org/pyav-ffmpeg
.. _PyAV issue #2270: https://github.com/PyAV-Org/PyAV/issues/2270
.. _libopus: https://opus-codec.org/

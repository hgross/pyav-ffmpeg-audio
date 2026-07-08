# wheels branch

Prebuilt `av` (PyAV 16.1.0) wheels linked against the **audio-only,
LGPL-2.1-or-later FFmpeg 8.0.1** built by this repository (see the `audio-lgpl`
branch for the build recipe and the releases for the FFmpeg dev tarballs and
the matching FFmpeg/libopus source archives).

The wheels live on a git branch rather than as release assets because GitHub
release asset names mangle the `+` of PEP 440 local versions.

Consume them via SHA-pinned raw URLs so the artifact can never change under
you, e.g. in `uv`:

```toml
[tool.uv.sources]
av = [
  { url = "https://raw.githubusercontent.com/hgross/pyav-ffmpeg-audio/<commit-sha>/av-16.1.0+lgpl.audio.1-cp312-cp312-win_amd64.whl", marker = "sys_platform == 'win32' and python_full_version < '3.13'" },
]
```

Built by the `build` workflow (run 28967206168); every wheel passed
`scripts/wheel_smoke_test.py` (no GPL configure flags, no video codecs,
working libopus/resampler audio path). Integrity: see `SHA256SUMS`.

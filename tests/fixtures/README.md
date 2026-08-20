# Test fixtures

**This directory is intentionally empty of media.**

`tests/test_offline_pipeline.py` and `scripts/validate_final_product.py` expect
two deterministic clips here:

    finger_frame_short.mp4            320x180, 12 fps, 2 s, with a 48 kHz AAC tone
    finger_frame_short_stylized.mp4   the same clip under a hue/saturation shift

Both are generated from `examples/final.mp4` by `scripts/create_fixtures.py`.
They are not published, because the footage they were derived from belongs to the
upstream author and shows an identifiable person. See the root `NOTICE`.

To recreate them from a clip you own, follow `examples/README.md`, then run:

```bash
python scripts/create_fixtures.py
```

Without these fixtures, the 4 tests in `tests/test_offline_pipeline.py` will fail
on the missing-file assertion. The other 47 Python tests and all 46 JavaScript
tests are media-independent and pass without them.

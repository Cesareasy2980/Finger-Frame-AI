# Demo media

**This directory is intentionally empty of media.**

No demo video, GIF, or screenshot is published with this repository. The demo
clip that this project was originally developed against belongs to the upstream
author and shows an identifiable person, so it is not redistributed here. See
the root `NOTICE` file for the full attribution and licensing situation.

## Adding your own demo

To publish a demo, record a clip that **you own** and that everyone appearing in
it has consented to publish:

1. Record a landscape clip, roughly 5–10 seconds, showing a clear two-hand
   finger-frame gesture. Both hands must be fully visible for the whole shot.
2. Save it as `examples/final.mp4`.
3. Generate a reduced preview GIF:

   ```bash
   ffmpeg -i examples/final.mp4 -vf "fps=12,scale=560:-1:flags=lanczos" examples/final.gif
   ```

4. Whitelist the media by uncommenting these lines in the root `.gitignore`:

   ```gitignore
   !examples/final.mp4
   !examples/final.gif
   ```

5. Regenerate the deterministic test fixtures from your clip:

   ```bash
   python scripts/create_fixtures.py
   ```

6. Whitelist the fixtures in `.gitignore` as well:

   ```gitignore
   !tests/fixtures/*.mp4
   ```

7. Confirm the full offline pipeline still passes:

   ```bash
   python -m unittest discover -s tests -v
   python scripts/validate_final_product.py
   ```

## Why the fixtures matter

`tests/test_offline_pipeline.py` and `scripts/validate_final_product.py` run the
real MediaPipe detector against `tests/fixtures/`, and assert that a valid hand
quadrilateral is found on every frame. Synthetic or drawn hands do not satisfy
the detector, so those checks require genuine recorded footage.

The remaining 47 Python tests and all 46 JavaScript tests are media-independent
and run without any fixtures, which is what continuous integration executes.

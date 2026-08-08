# Turn 1 — Scene (paste into Claude.ai / ChatGPT with the photo)

**Don't hand-copy the schema from source anymore.** Run:

```bash
botdraw vision brief <job_id> --turn 1
```

This writes a folder with the exact prompt (`prompt.txt`), the images to
attach, and a `README.md` walking through attach → paste → save-the-reply
steps. The reply filename it expects (`turn01_scene.json`) already
matches what `BOTDRAW_VISION_TURNS_DIR` / `BOTDRAW_VISION_SCENE_JSON`
read.

Notes specific to this turn: prefer `classic` line_source for object
structure tests.

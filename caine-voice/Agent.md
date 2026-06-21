# See the canonical handoff doc at the project root

Open the **parent** folder (`Amazing-Digital-Circus-Birthday-Party-App/`) in Claude Code and read **`../Agent.md`**
there — it has the full context, the file map, the contract for adding a model, and the task list.

Quick reference (from this `caine-voice/` folder):
- Engine: `make_caine_voice.py`  ·  Party Server: `caine_studio_web.py` (`Start Caine Party.bat`, in the project root)
- Reference voice: `caine_ref_clean.wav`  ·  transcript: `caine_ref.txt`  ·  logs: `logs/`
- Test one model: `py make_caine_voice.py --model=qwen3 --test --force`
  then listen to `../caine-console/audio/qwen3/test_en.wav`
- **Never** copy one model's audio into another's folder (no fake fallbacks).

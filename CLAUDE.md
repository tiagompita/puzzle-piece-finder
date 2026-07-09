# Puzzle Piece Finder

A computer-vision tool that locates individual jigsaw pieces inside the full puzzle image via multi-scale template matching (OpenCV), with a CLI (`src/main.py`) and a Tkinter GUI (`src/gui.py`).

## Current Objective

This round of work aims to complete the project as fully as possible, across four fronts:

1. **Automatic segmentation** — give body to `src/segmentation.py` (currently empty): detect and crop pieces from a photo of the puzzle/board, instead of loading pre-cut pieces one by one.
2. **Visualization & export** — give body to `src/visualization.py` (currently empty): produce an annotated result image (including a "red dot" marker showing where a piece likely goes, per the original `notebooks/TODO`), and recover the JSON export that is currently disabled.
3. **Improve matching** — raise engine accuracy: colour-aware matching (not only grayscale), edge analysis for corner/border pieces, and better scoring/scale selection.
4. **Cleanup & fixes** — technical debt: broken default paths in `acquisition.py`, relative-import issues that stop the documented run commands from working, duplicate methods in the GUI, and orphaned/dead code.

**Explicitly out of scope** for this round: ML-based piece classification and a REST API (these are "Future" roadmap items).

## Architecture

| Module | Lines | Status | Notes |
|---|---|---|---|
| `src/matching.py` | ~476 | Functional (the engine) | Naive pixel diff, sliding-window search, and `multi_scale_template_match` (coarse downscale + full-res refinement, optional CUDA/GPU path). Refinement currently uses grayscale mean-absolute-difference and discards colour; `CCORR_NORMED` maps to `cv2.TM_CCOEFF_NORMED`. |
| `src/gui.py` | ~913 | Functional but messy | Whole Tkinter interface and orchestration: load puzzle/pieces, compute metrics, match single/all, overlays (rectangle + id + similarity %), progress, cancel, JSON export. Technical debt: `load_pieces` and `export_results` are each defined twice (the real JSON export is shadowed by a stub), plus orphaned/dead code inside `_handle_match_error`. |
| `src/acquisition.py` | — | Functional | Interactive image loading/selection. Broken default paths point at an old `puzzle_solver` folder. |
| `src/features.py` | ~48 | Functional | Pure helpers: image size, area, dominant colour (simple frequency, no k-means), colour distance, scale (px/cm). |
| `src/main.py` | ~19 | Functional | Minimal CLI orchestration. |
| `src/segmentation.py` | 0 | **Empty — to implement** | Automatic piece detection/cropping from a puzzle/board photo. |
| `src/visualization.py` | 0 | **Empty — to implement** | Annotated result image (incl. red-dot marker). (Recovering the JSON export is a separate fix in `src/gui.py`, where the export lives today — not part of this module.) |

Support files: `examples/basic_usage.py`; loose test scripts (`test_scales.py`, `gpu_test.py`, `temp_import_test.py`); docs (`README.md`, `CHANGELOG.md`, `QUICKSTART.md`, `CONTRIBUTING.md`); example data in `images/` (24 example pieces, 1 puzzle image, and `images/pieces/puzzle.json` ~512KB with pieces as base64).

Dependencies: Pillow, opencv-python, numpy (see `requirements.txt`). The GPU path needs an OpenCV build compiled with CUDA. Python 3.8+.

## Subagents & Model Routing

Three subagents are defined in `.claude/agents/`:

| Subagent | Model | Role | Limits |
|---|---|---|---|
| **planner** | Fable | Architecture and deep-planning specialist. Read-only tools (Read, Grep, Glob, WebSearch, WebFetch). | Never writes or edits code — plans and decisions only. Invoked ONLY for genuinely complex problems the implementer cannot chart alone (e.g. designing the segmentation pipeline from scratch, choosing between fundamentally different algorithmic strategies, cross-module architecture decisions). Expensive and weekly-limited — last resort, used as rarely as possible. |
| **implementer** | Opus | Primary workhorse. Full editing tools. | Handles complex logic needing real reasoning but with a clear path: image algorithms, template matching, segmentation, scoring/metrics, visualization logic, non-trivial bug fixes. Owns all changes to the critical modules (`src/matching.py`, `src/segmentation.py`, `src/features.py`) and reviews the helper's algorithmic edits. Default tier for substantive coding work. |
| **helper** | Sonnet | Cheapest, first-choice tier. Full editing tools. | Handles simple, low-risk work: GUI/UI tweaks, mechanical refactors, formatting, renames, documentation, requirements edits, simple tests, small fixes like broken paths. Hard limit: must NOT change algorithmic logic in the critical modules (`src/matching.py`, `src/segmentation.py`, scoring/feature logic in `src/features.py`) without the implementer designing or reviewing the change. Escalates instead of guessing. |

### Routing chain and rules

- Routing chain, cheapest first: **helper (Sonnet) → implementer (Opus) → planner (Fable)**.
- Always start at the cheapest tier that can plausibly do the task. Only escalate to the implementer when the helper is not enough. Only escalate to the planner when the implementer hits a genuine architecture/strategy wall it cannot resolve itself.
- Subagents cannot spawn other subagents. "Escalation" means the subagent stops and reports clearly what it needs and why, so the main orchestrator routes the work to the right tier.
- Hand-off pattern: planner produces a plan → implementer executes it → helper does the surrounding simple/mechanical work. The implementer reviews any helper edits that touch critical modules.
- Concrete mapping for this round's work (illustrative): cleanup/paths/docs/GUI-debt → helper; matching improvements, segmentation algorithm, visualization logic → implementer; only the hardest up-front design (e.g. the segmentation strategy) → planner, once, if needed.

## Cost-Saving Principle

The user has a tight **weekly limit on the Fable model**, so Fable must be used sparingly — only for planning/deep analysis of genuinely complex problems. The bulk of the work must fall on Opus (complex implementation) and Sonnet (simple tasks).

- Always use the cheapest model sufficient for the task.
- Reserve Fable (planner) strictly for complex problem planning; invoke it as little as possible.
- Let Opus (implementer) and Sonnet (helper) carry the bulk of the work.
- This is the user's primary cost-saving mechanism and must be respected in all work.

## Conventions

- `src/` uses tab indentation, `__all__` exports, and docstrings; pure helpers are kept separate from I/O.
- Critical modules requiring implementer design/review for any algorithmic change: `src/matching.py`, `src/segmentation.py`, and the scoring/feature logic in `src/features.py`.

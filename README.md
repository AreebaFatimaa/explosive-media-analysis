# Explosive Media: what a Telegram channel published before and after a war

Reporting and data analysis on **@akhbarenfejari** (Explosive Media / Akhbar Enfejari), the Iranian
channel behind the AI-generated Lego war videos that circulated widely during the 40-day U.S.–Iran
war of 2026.

This repository holds the full pipeline behind the published piece: the scraper, the classification
dashboard, the hand-coded golden dataset, the classifier prompts and outputs, the evaluation, and
the scrollytelling site that presents the findings.

**The story:** [`index.html`](index.html) — open locally with any static server (see below).
**Narrative draft:** [`explosion-story.md`](explosion-story.md)
**Full methodology:** [`explosion-methodology.md`](explosion-methodology.md), and the
[Methodology section](index.html#methodology) of the piece itself.

---

## What's in the dataset

Every post published by the channel between **Dec. 31, 2025 and April 9, 2026** — a window chosen
to bracket the war that began Feb. 28, 2026.

| | count |
|---|---|
| Posts | 2,840 |
| with video | 981 |
| with images | 1,665 |
| text-only | 194 |
| Hand-coded posts (golden set) | 339 |
| Days in window / days with posts | 100 / 64 |

## Pipeline

1. **Scrape** — `scripts/scrape.py`, Telegram API, posts plus media to a master CSV.
2. **Frames** — `scripts/take_screenshots.py`, one FFmpeg key frame per video at its midpoint.
3. **OCR** — Claude Haiku 4.5 Vision on frames, Persian text plus English translation per call.
4. **Transcription** — faster-whisper `medium`, CPU, INT8, `beam_size=3`, `language="fa"`.
5. **Translation** — `scripts/translate.py`, Claude Haiku, into `message_text_english`.
6. **Hand coding** — `dashboard/` (Flask), 339 randomly sampled posts into 17 categories.
   Sample size from [Naël Shiab's calculator](https://observablehq.com/@nshiab/how-many-entries-should-i-double-check-when-using-ai):
   ±5% at 95% confidence. Sample is reproducible: `random_state=42`, see `scripts/rebuild_golden_dataset.py`.
7. **Classification** — three separate passes, prompts and calls in `notebooks/notebook3.ipynb`:
   stance (pro-/anti-regime, Claude Haiku 4.5), Lego detection (Gemini 3.1 Flash Lite, one frame
   per post), and five thematic categories as a multi-label pass. Category definitions come from
   `schema.md`, the same definitions used for the hand coding.
8. **Evaluation** — `notebooks/precision-recall.ipynb`, classifier output against the golden set.
9. **Build** — `scripts/build.py` turns the prediction CSVs into the JSON in `data/` that the site reads.

## Accuracy

Measured against the 339 hand-coded posts. Support is how many hand-coded posts carry the label.

| Category | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| Anti-regime | 18 | 72% | 72% | 72% |
| Pro-regime | 30 | **21%** | 97% | 35% |
| Neither | 291 | 99% | 63% | 77% |
| Lego | 4 | 60% | 75% | 67% |
| International news | 140 | 74% | 80% | 77% |
| War coverage | 70 | 66% | 77% | 71% |
| Iranian economy | 21 | 50% | 57% | 53% |
| Foreign intervention | 10 | **11%** | 50% | 18% |
| Protests | 3 | **12%** | 33% | 18% |

Read this table before reading any number in the piece. Anti-regime holds. **Pro-regime, under the
broadened definition used throughout, has a precision of 21%** — roughly four in five posts it
labels pro-regime do not meet the hand-coded definition, so pro-regime shares indicate a direction
and not a measurement. Foreign intervention and protests are not usable at all. The Lego score sits
on four hand-coded examples and carries no statistical weight; what supports the Lego finding is
that all 24 flagged posts were checked by hand.

`schema.md` keeps a written revision history, including the mid-project decision to broaden
"pro-regime" from praise of the leadership to any framing that casts the state favourably — which
moved the corpus count from 304 to 1,138 without a single post changing. Part of what the
pro-regime figures measure is that definition.

The [Limitations](index.html#methodology) section of the piece lists the rest: the pre/post volume
asymmetry, the concentration of 74.5% of post-war posts on two days, thin per-class support, the
revision of golden labels after seeing model disagreements, single-frame video judgment, coding
through translation, and the absence of any control channel.

## Repository map

```
index.html                 the published piece
css/ js/                   site styles and D3 rendering
data/                      JSON the site reads, built by scripts/build.py
CSVs/
  explosive_media_messages.csv    master corpus, 2,840 rows
  golden_dataset.csv              339 hand-coded posts
  phase1_stance_predictions.csv   stance, final schema
  phase1_stance_predictions_v1.csv  stance, original narrow schema
  lego_predictions.csv            Lego detection
  phase3_tier1_predictions.csv    five thematic categories
scripts/                   scrape, screenshots, translate, rebuild golden set, build site data
notebooks/                 classification (notebook3), evaluation (precision-recall), revisions
dashboard/                 Flask app used to hand-code, transcribe and screenshot posts
transcription-scripts/     faster-whisper runners
schema.md                  category definitions and their revision history
lego_findings.md           detailed notes on the Lego classifier
media/ screenshots/ thumbs/  post media and extracted frames
```

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m http.server 8000        # then open http://localhost:8000
```

Rebuilding the site data from the prediction CSVs:

```bash
python scripts/build.py
```

The scraping, translation and classification steps need credentials in a `.env` file
(`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`). No credentials or
Telegram session files are committed. Note that the API calls do not pin a temperature, so
re-running the classifiers will not reproduce these labels exactly — the prediction CSVs in `CSVs/`
are the labels the published figures were actually computed from.

## Reflections

LLM classification is indeed a black box, and it feels uncomfortable to trust it with a big project
instead of having a team hand-code the data manually. While I could have used more iterations on the
prompts until I reached better precision and recall numbers, I'd still have not felt the confidence
you do when you classify by hand. While research suggests that LLMs are really good at this, I still
feel a bit uncertain. However, that said, the back and forth with Claude really helped nail down the
documentation, so if I ever want to improve the numbers here, I would always be able to.

## Credits

Reporting and data analysis by **Areeba Fatima**, April 2026.
Source channel: [@akhbarenfejari](https://t.me/akhbarenfejari).
Classification and translation with Claude Haiku 4.5 and Gemini 3.1 Flash Lite; transcription with
faster-whisper; charts with D3.

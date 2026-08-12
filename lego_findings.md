# LEGO content on @ExplosiveMedia — classifier findings and evaluation

A methods appendix covering the LEGO pass over the @ExplosiveMedia (Akhbar Enfejari) Telegram
corpus: 2,840 messages posted between 31 December 2025 and 9 April 2026, bracketing the 40-day
Iran–US war that began on 28 February 2026.

The LEGO classifier (Gemini 3.1 Flash Lite, served through OpenRouter) was shown every message
that carried a downloadable visual — images directly, videos via a single extracted key frame —
and asked a yes/no question plus a free-text description of what it saw. The schema definition it
was working from is deliberately minimal: *"Lego: any posts showing Lego content."*

All figures below were computed directly from `CSVs/lego_predictions.csv`,
`CSVs/golden_dataset.csv`, `CSVs/phase1_stance_predictions.csv` and
`CSVs/explosive_media_messages.csv`. Nothing is estimated.

---

## Numbers at a glance

| Measure | Value |
|---|---|
| Messages in corpus | 2,840 |
| Messages with a visual the classifier could see | 2,646 (93.2%) |
| Messages with no visual (not classifiable) | 194 (6.8%) |
| Decode/API errors | 2 |
| Flagged LEGO | 24 (0.85% of all messages; 0.91% of visuals) |
| — of which video key frames | 20 |
| — of which still images | 4 |
| Hand-coded LEGO positives in the 339-row golden set | 4 |
| Golden-set confusion matrix | TP 3, FP 2, FN 1, TN 333 |
| Precision / Recall / F1 / Accuracy (all 339 rows) | 0.600 / 0.750 / 0.667 / 0.991 |
| Precision / Recall / F1 / Accuracy (excl. the no-media positive) | 0.600 / 1.000 / 0.750 / 0.994 |
| LEGO posts before 28 Feb 2026 | 5 of 2,585 messages (0.19%) |
| LEGO posts on/after 28 Feb 2026 | 19 of 255 messages (7.45%) |
| Fold change in LEGO rate, pre → post | 38.5× (all messages) / 63.2× (visuals only) |
| Share of LEGO posts classed Pro-regime | 18 of 24 (75.0%) vs 39.8% base rate |
| LEGO posts classed Anti-regime | 0 |

---

## 1. Coverage

- The classifier was run over all **2,840** rows of the corpus, i.e. every message, with no
  sampling.
- **2,646 messages (93.2%)** had a media file on disk and were actually examined: **1,665 still
  images** (`.jpg`) and **981 videos** (`.mp4`). Videos were reduced to a single extracted key
  frame before being sent.
- **194 messages (6.8%)** had no media file and were returned as `no visual`. These were never
  seen by the model and cannot be scored as either hits or misses on visual grounds.
- The no-visual rows are not evenly spread: **89 of 2,585 (3.4%)** pre-war messages had no
  visual, against **105 of 255 (41.2%)** from 28 February onward. The post-war-onset stretch of
  the corpus is therefore much thinner in scrapeable media, which matters for every rate reported
  in §4.
- Of those 194, **20 are messages the corpus itself marks `has_media = Y`** but for which no file
  was retrieved — a scrape gap rather than a genuinely text-only post. Fourteen of the twenty fall
  in April 2026, the tail of the collection window.
- **2 messages errored** (`[error]`) rather than returning a verdict: `original_row` 893
  (2026-02-01, a still about car overpricing) and 948 (2026-02-02, a tunnel-closure notice).
  Neither has any textual signal of LEGO content, so the practical loss is negligible, but they
  are unscored.

---

## 2. What was flagged

- **24 messages were flagged LEGO** — 0.85% of the corpus, 0.91% of the messages with a visual.
- Split by media type: **20 came from video key frames** (2.0% of the 981 videos) and **4 from
  still images** (0.24% of the 1,665 images). LEGO content on this channel is overwhelmingly
  moving-image content; the stills that were flagged are mostly promotional posters and teasers
  advertising a video.
- The flagged set is heavily concentrated in time and in a single content franchise (see §4 and
  §6). It is not a scattering of incidental toy photographs.

---

## 3. Evaluation against the golden set

This is the formal accuracy check. It was computed over the **339 hand-coded rows** in
`CSVs/golden_dataset.csv`. A golden row counts as a LEGO positive if any of `theme`, `theme2`,
`theme3` or `theme4` equals `LEGO`. All 339 golden rows matched a prediction row on
`original_row`; there were no join failures.

### The confusion matrix

| | Predicted LEGO | Predicted not LEGO |
|---|---|---|
| **Hand-coded LEGO** | **TP = 3** | **FN = 1** |
| **Hand-coded not LEGO** | **FP = 2** | **TN = 333** |

- **Precision = 3 / 5 = 0.600**
- **Recall = 3 / 4 = 0.750**
- **F1 = 0.667**
- **Accuracy = 336 / 339 = 0.991**

### Excluding the row the classifier could not possibly have caught

- **Precision = 0.600, Recall = 3/3 = 1.000, F1 = 0.750, Accuracy = 335/338 = 0.994.**

### The caveat, which matters more than the rates

- **There are only four hand-coded LEGO positives in the entire golden set.** Every rate above
  rests on a denominator of four. One additional error moves recall by 25 percentage points. These
  numbers should be read as a sanity check that the classifier is not wildly miscalibrated, **not**
  as a precise performance estimate, and they should not be quoted as a stable accuracy figure in
  publication without this qualification attached.
- **One of the four positives — `original_row` 2826 — has no media file at all.** The message
  (3 April 2026: *"No one here likes you, Donald. 🇫🇷🇰🇼🇪🇸🇮🇶🇧🇭 GET LOST!"*) is marked
  `has_media = Y` in the corpus but no file was retrieved, so the classifier returned `no visual`.
  A vision classifier could never have found it. **Maximum achievable recall on this golden set is
  therefore 3/4 = 0.750**, and the classifier hit that ceiling exactly. Excluding that row, it
  missed nothing.
- **The two "false positives" are not obviously wrong.** Both — `original_row` 2749
  (2026-03-14_056.mp4, described as *"LEGO style office chair"*, a field-interview segment set in
  what the thumbnail shows as a blocky Oval-Office-style animated scene) and `original_row` 1656
  (2026-02-13_062.mp4, *"LEGO minifigure head"*, a "Good morning" post) — are frames from the
  channel's own brick-style animation output. They may reflect the golden coder applying `LEGO`
  only to posts *about* the LEGO franchise rather than every frame rendered in the style. Precision
  of 0.600 is thus a floor, not a settled figure; the disagreement is partly a coding-boundary
  question about where "LEGO-style animation" ends.
- **The stronger evidence is the hand-check of all 24 flagged items**, reproduced in §6. Every one
  of the 24 was read against its description and its message text, and all 24 are consistent with
  the channel's brick-animation output — either a brick-built scene, a minifigure, or a post
  advertising one. With only four golden positives, that item-by-item review carries more
  evidential weight than the F1 score.

---

## 4. Timing: LEGO content is a wartime phenomenon

The war began **28 February 2026**. Splitting the corpus at that date:

- **Before 28 Feb:** 5 LEGO posts out of **2,585** messages = **0.19%** (0.20% of the 2,496
  messages with a visual).
- **On/after 28 Feb:** 19 LEGO posts out of **255** messages = **7.45%** (12.67% of the 150
  messages with a visual).
- **Fold change: 38.5× on an all-messages basis, 63.2× on a visuals-only basis.** The visuals-only
  figure is the more conservative comparison, since it controls for the collapse in scrapeable
  media after the war began.
- **Caution:** the post-28-Feb window contains only 255 messages against 2,585 before it, and only
  150 of those have a visual. The direction of the shift is unambiguous and large, but the
  post-war percentage rests on a small base and should be reported with its denominator.

### By date

| Date | LEGO posts | Total messages that day |
|---|---|---|
| 2026-01-28 | 1 | 64 |
| 2026-02-13 | 1 | 64 |
| 2026-02-14 | 1 | 65 |
| 2026-02-17 | 2 | 70 |
| 2026-03-07 | 1 | 1 |
| **2026-03-14** | **8** | **82** |
| 2026-03-18 | 1 | 11 |
| 2026-03-19 | 1 | 11 |
| 2026-03-22 | 1 | 13 |
| 2026-03-23 | 1 | 4 |
| 2026-03-24 | 1 | 2 |
| 2026-03-26 | 1 | 1 |
| 2026-03-28 | 1 | 1 |
| 2026-03-29 | 2 | 3 |
| 2026-04-01 | 1 | 2 |

- **14 March 2026 is by far the biggest single day: 8 of the 24 flagged posts (one third).** That
  date is also an anomaly in the corpus generally — 82 messages, against single-digit daily counts
  either side of it. It reads as a catch-up or backfill dump of animation content produced during
  a gap in collection, so it should be treated as one publishing event rather than eight
  independent days of activity.
- From 18 March onward the channel's daily volume is tiny (1–13 messages), and LEGO posts make up a
  large share of it: on 26 March and 28 March, the single message posted that day was a LEGO
  animation. In the last stretch of the war the brick animations are close to the channel's whole
  visual output.
- The five pre-war flags are qualitatively different: two (28 January, 13 February, 14 February)
  are incidental — a robot playing with bricks in a tech-news item, a brick held up in a UN story,
  a "good morning" clip. The 17 February pair are the first genuine house-produced brick
  animations, advertised as *"Negotiation Animation — Production by the Explosive News Team"*.
  The format therefore predates the war by about ten days but only becomes a staple after it.

---

## 5. Overlap with regime stance

Crosstabbed against `p1_stance` from the Phase 1 classifier (all 2,840 rows joined, no misses):

| | Anti-regime | Neither | Pro-regime |
|---|---|---|---|
| **Not LEGO (2,816)** | 156 (5.5%) | 1,540 (54.7%) | 1,120 (39.8%) |
| **LEGO (24)** | **0 (0.0%)** | 6 (25.0%) | **18 (75.0%)** |

- **75.0% of LEGO posts are classed Pro-regime, against a base rate of 39.8% among non-LEGO
  posts** — roughly a doubling.
- **Not one LEGO post is classed Anti-regime.** Against a 5.5% anti-regime base rate, zero out of
  24 is what you would expect from a purely pro-state production line; with n=24 the expected count
  under the base rate is only about 1.3, so this is suggestive rather than statistically decisive
  on its own, but it is consistent with the content read in §6.
- The six LEGO posts classed `Neither` are mostly the incidental early ones (the robot/bricks tech
  item, the "good morning" clip, the UN story) plus two promotional posts with little evaluative
  text — a Spotify release announcement and a teaser. They are the posts where the stance signal is
  in the video rather than the caption, and five of the six carry `low` stance confidence.
- Of the 18 Pro-regime LEGO posts, **11 carry `high` or `medium` stance confidence**, so the
  pro-regime reading is not resting on marginal calls.

---

## 6. What the flagged posts actually show

Reading the classifier's `lego_what` descriptions alongside each post's translated text, the 24
flagged items fall into four groups.

**a) War-fighting propaganda rendered in bricks (the core of the set).**
- *"CGI missiles built from LEGO bricks"*, *"missiles flying through brick clouds"*, *"LEGO style
  burning air base"*, *"Lego minifigures in a war scene"*, *"LEGO minifigures holding Molotov
  cocktails"*.
- Titles: *"#Animation | Response to the Aggressor — No target is safe from Iranian missile
  fire"*; *"Victory Chronicles: Part 2"*; *"#Animation | Trump's Last Gamble — He turned to others
  for help but everyone turned their back on him… dying Pharaoh-like!"*; *"The Vengeance — For all
  the crimes you committed against humanity… ONE VENGEANCE FOR ALL."*
- The brick aesthetic is doing hard propaganda work: US airbases burning, Iranian missiles in
  flight, an American aircraft carrier destroyed.

**b) Mockery of Donald Trump and the US specifically.**
- *"LEGO minifigure of Donald Trump"* (2026-03-24) accompanies *"What a diss they gave Trump! A
  special and strange work from the Explosive News Team — English logo music Khamenei again."*
- 2026-03-26: *"We know they only feed you 2-minute clips every day of empty buildings being
  targeted, but you'd better watch this. Then ask your womanizing buddy: 'Is this true Peter? Why
  did we attack the island?' Loser!"* — written in English, addressed outward to a US audience.
- 2026-04-01: *"Lego Moses figure facing burning pyramid"*, captioned *"A teaser of what will be
  released tomorrow night… (I think this might be the longest Lego animation we've ever
  produced.)"*

**c) Religious/nationalist set pieces.**
- *"CGI golden bull built from bricks"* accompanying a music video, *"The Fire of the Nation"*;
  the Moses-and-the-pyramid framing above; *"Lego minifigure with ghost figures"*; and the
  *"Rise Up"* serial (*"All good entered battle with all evil"*). The channel repeatedly maps the
  war onto Quranic and Shia narrative templates — Moses against Pharaoh, the Elephant Keepers
  against Abraha — using minifigures as the cast.

**d) Vernacular and promotional filler.**
- *"LEGO boombox radio"* fronting episode 109 of `#explosive_news`; *"LEGO figure holding bowl of
  nuts"* on a Nowruz greeting; *"LEGO style office chair"* fronting a mock street interview;
  *"CGI render of LEGO bricks"* on a Spotify release announcement for a track called *"L.O.S.E.R"*.
- These show the brick style migrating out of standalone animations and into the channel's routine
  news-magazine furniture — the format became house identity, not just an occasional stunt.

**Language.** Several of the most recent flagged posts are written in English rather than Persian
(2026-03-26, 2026-03-28, 2026-03-29, and the 8 April Lego message noted in §8). The channel appears
to have pivoted the brick animations toward a foreign audience as the war progressed.

---

## 7. Evidence the content is channel-produced

Counting textual production markers across the 24 flagged posts:

- **11 of 24 (45.8%)** contain the word *"animation"*.
- **9 of 24 (37.5%)** name the *"Explosive News Team"*; a further 2 name *"Explosive Media"*.
  **12 of 24 (50.0%)** carry at least one of the channel's own production brands (*Explosive News
  Team*, *Explosive Media*, *Marjae Khabar*).
- **4 of 24** say *"produced by"* and **4 of 24** say *"production by"*.
- **6 of 24 (25.0%)** carry the `#Animation` hashtag; 2 carry `#Music_Video`.
- Two posts state it outright: 2026-03-29 — *"🎬 NEW Lego Animation Video from Explosive Media Team
  in Iran! 🇮🇷💥 … #Legostyleanimation"* — and 2026-04-01's *"the longest Lego animation we've ever
  produced"*.
- Read the other way: **40 messages in the corpus carry one of the house production brands, and 12
  of those 40 (30.0%) were flagged LEGO.** Brick animation is a substantial, though not exclusive,
  share of everything this channel makes in-house.
- Nothing in the flagged set is a repost of commercial LEGO material, an advertisement, or a
  franchise-news item. The LEGO aesthetic here is a production choice by the channel, not coverage
  of the LEGO brand.

---

## 8. Validation check: the "animation" keyword test

To test whether the classifier is over- or under-firing, all messages whose text mentions
*"animation"* were pulled independently of the classifier's verdict.

- **42 corpus messages mention "animation".** Of these, **11 were flagged LEGO**, **29 were seen
  and returned `No`**, and **2 had no visual at all**.
- Splitting by whether the post is house-produced (text names the Explosive News Team, Explosive
  Media, or Marjae Khabar):
  - **20 messages are house-produced animation announcements. 9 were flagged (45%); 11 were seen
    and returned `No`.**
  - **22 messages mention animation without a house brand; only 2 were flagged.**

**What the 22 non-house "animation" posts actually are:** almost all are ordinary
entertainment-news items about the commercial animation industry — the Fajr Film Festival opener
*Guardians of the Sun*, Oscar and BAFTA animated-feature nominees, *Zootopia 2*, *Toy Story 5*,
*Teenage Mutant Ninja Turtles*, box-office records for *Goat* and *Lynx*. The classifier correctly
returned `No` on every one of these. **There is no evidence of over-firing on the word
"animation" or on cartoon imagery generally.**

**What the 11 non-flagged house-produced animation posts are:** these are the channel's own
`#Animation` output — the *"Rise Up"* serial (episodes one, two and three), *"Logo of Iran's New
Leader"*, *"Lord of the Straits"*, *"Strait of Hormuz remains closed"*, *"The Elephant Keepers
Modern"*, the *"Khamenei Again"* music video, and others. Their sampled key frames were described
as *"a man in a car"*, *"missile launch"*, *"man speaking in front of news"*, *"candle with flame
and smoke"*, *"emergency light on control panel"* — plausible frames from a brick animation that
happen not to show a minifigure or a stud. Two earlier ones (*"Short animation Red Trail"*,
5 February) are described as illustrated rather than brick-built and may be a genuinely different
in-house style.

**Conclusion of the check: the classifier is under-firing, not over-firing.** Its 24 flags are a
conservative floor. If the roughly 9–11 house-produced animation posts whose key frames simply
missed the bricks belong to the same production line — which their titles, hashtags and branding
strongly suggest — the true count of brick-animation posts is closer to **33–35**, and the
post-28-February concentration would be more pronounced, not less. This is consistent with the
golden-set result, where the classifier's only miss was structurally impossible and neither
apparent false positive is clearly wrong.

**Two messages state LEGO explicitly and were unreachable.** `original_row` 2821 (29 March, *"A New
Lego animation will be released tonight."*) and 2836 (8 April, *"…the LEGO-style animations will
keep coming, stronger than ever"*, attached to a crypto-donation solicitation) are both marked
`has_media = Y` but have no retrieved file, so both returned `no visual`. Only **4 messages in the
entire corpus contain the string "lego" in their text**; two were flagged, and these two were
invisible to a vision-only method. Any published count should note that a text-plus-vision
combination would catch more than vision alone.

---

## 9. Limitations

- **Single-frame video sampling is the dominant limitation.** Each of the 981 videos was
  represented by one extracted key frame. Brick content appearing only later in a clip — after a
  live-action or title-card opening, which is the channel's habit — is invisible to the method.
  §8 shows this concretely: at least 9–11 house-produced animation posts were missed this way. Any
  count of LEGO posts derived from this pass is a **lower bound**.
- **194 messages (6.8%) had no visual and were never classified**, including two that say "Lego" in
  their own text and one of the four golden-set positives. Twenty of these are scrape failures on
  messages the corpus records as having media, concentrated in April 2026.
- **2 messages errored** and carry no verdict. Neither shows any textual sign of LEGO content, but
  they remain unscored.
- **The golden set contains only 4 LEGO positives.** Precision (0.600) and recall (0.750, or 1.000
  excluding the impossible row) are computed on single-digit counts and are extremely unstable —
  one error shifts recall 25 points. They demonstrate the classifier is not badly miscalibrated;
  they do not establish a reliable accuracy rate. The hand-review of all 24 flagged items in §6 is
  the stronger evidence.
- **The "false positive" boundary is unresolved.** Whether every frame rendered in brick style
  counts as "LEGO content", or only posts about LEGO as such, was never pinned down in the schema
  (*"any posts showing Lego content"*). Both apparent false positives sit on that line. Fixing the
  definition would change the precision figure.
- **Post-war data is thin.** Only 255 of 2,840 messages fall on or after 28 February, and only 150
  of those carry a visual — and 82 of the 255 are the single 14 March backfill. Percentages for the
  war period, including the headline 7.45% and 12.67% LEGO shares, rest on that small and unevenly
  distributed base.
- **Stance figures are classifier output, not hand-coding.** The pro-regime/anti-regime split in §5
  comes from the Phase 1 model and inherits its own error rate; it has not been separately
  validated on this 24-post subset.
- **The classifier saw pixels, not sound or motion.** Music, narration and on-screen Persian text
  in the videos were not available to it, so its descriptions characterise composition only.

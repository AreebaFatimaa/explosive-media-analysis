#!/usr/bin/env python3
"""Generate data JSON files for the scrollytelling site.

Run from anywhere — paths are resolved relative to this script's location.
After the project reorganization, the layout is:

    explosive-media-analysis/
        CSVs/explosive_media_messages.csv
        scripts/build.py        (this file)
        data/   <-- output JSON files written here
        media/
        screenshots/

The script writes JSON files into ``../data`` so that the static site at
``explosive-media-analysis/index.html`` can fetch them.
"""
import csv
import json
import os
import collections

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))      # explosive-media-analysis/
CSV_PATH = os.path.join(SITE_ROOT, 'CSVs', 'explosive_media_messages.csv')
DATA = os.path.join(SITE_ROOT, 'data')
SHOTS_DIR = os.path.join(SITE_ROOT, 'screenshots')
os.makedirs(DATA, exist_ok=True)


def load_rows():
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def is_repetitive(s):
    if not s:
        return True
    words = s.split()
    if len(words) < 6:
        return False
    return len(set(w.lower() for w in words)) / len(words) < 0.3


def write_json(name, data, indent=None):
    path = os.path.join(DATA, name)
    with open(path, 'w') as f:
        if indent:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        else:
            json.dump(data, f, ensure_ascii=False)
    print(f'  -> {name}')


def main():
    rows = load_rows()
    print(f'Loaded {len(rows)} rows from {CSV_PATH}')

    # ----- Timeline -----
    daily = collections.Counter()
    daily_by_type = collections.defaultdict(lambda: {'video': 0, 'image': 0, 'text': 0})
    for r in rows:
        d = r['date']
        if not d:
            continue
        daily[d] += 1
        fn = r.get('media_filename', '').strip()
        if fn.endswith('.mp4'):
            daily_by_type[d]['video'] += 1
        elif fn.endswith(('.jpg', '.png')):
            daily_by_type[d]['image'] += 1
        else:
            daily_by_type[d]['text'] += 1

    timeline = []
    for d in sorted(daily):
        t = daily_by_type[d]
        timeline.append({
            'date': d,
            'count': daily[d],
            'video': t['video'],
            'image': t['image'],
            'text': t['text'],
        })
    write_json('timeline.json', timeline)

    # ----- Mosaic -----
    mosaic = []
    for r in rows:
        fn = r.get('media_filename', '').strip()
        if fn.endswith('.mp4'):
            mtype = 'v'
        elif fn.endswith(('.jpg', '.png')):
            mtype = 'i'
        else:
            mtype = 't'
        mosaic.append({
            'd': r['date'],
            'm': mtype,
            't': r.get('theme', '').strip(),
            'x': (r.get('message_text_english', '') or '').strip()[:120],
        })
    write_json('mosaic.json', mosaic)

    # ----- Stats + chapter trackers -----
    themes = collections.Counter(
        r.get('theme', '').strip() for r in rows if r.get('theme', '').strip()
    )

    # Pro/anti-regime and LEGO counts come from the dedicated classifiers, not from
    # the 17-way `theme` column, which is a much weaker signal. Without this the
    # stats panel and the ch2 tracker print a different number from the narrative
    # for the same quantity.
    stance_pred = _read_indexed(STANCE_CSV)
    lego_pred = _read_indexed(LEGO_CSV)
    stance_counts = collections.Counter(
        (stance_pred.get(i, {}).get('p1_stance') or '').strip()
        for i in range(len(rows))
    )
    lego_count = sum(
        1 for i in range(len(rows))
        if (lego_pred.get(i, {}).get('lego') or '').strip().lower() in ('yes', 'true')
    )
    if stance_pred:
        themes['Pro-regime'] = stance_counts.get('Pro-regime', 0)
        themes['Anti-regime'] = stance_counts.get('Anti-regime', 0)
    if lego_pred:
        themes['LEGO'] = lego_count
    keywords = collections.Counter()
    for r in rows:
        kws = r.get('keywords', '').strip()
        if kws:
            for k in kws.split(','):
                k = k.strip()
                if k:
                    keywords[k] += 1
    persons = collections.Counter(
        r.get('include_person', '').strip() for r in rows if r.get('include_person', '').strip()
    )
    ai_yes = sum(1 for r in rows if r.get('AI_generated', '').strip().upper() == 'YES')
    ai_no = sum(1 for r in rows if r.get('AI_generated', '').strip().upper() == 'NO')

    def kw_match(r, terms):
        kws = (r.get('keywords', '') or '').lower()
        return any(t in kws for t in terms)

    def theme_match(r, themes_set):
        return r.get('theme', '').strip() in themes_set

    # Per-chapter trackers: counts + percentages (vs total = 2840)
    total = len(rows)
    def pct(n):
        return round(100 * n / total, 2)

    trackers = {
        'ch1_ai': {
            'label': 'Posts about AI',
            'count': sum(1 for r in rows if theme_match(r, {'Using AI'}) or kw_match(r, ['ai-generated', 'ai generated', 'using ai', 'commentary on ai', 'detecting ai', 'gemini'])),
            'subitems': [
                {'label': 'AI‑generated posts', 'count': ai_yes},
                {'label': 'Sanctions / VPN bypass', 'count': sum(1 for r in rows if kw_match(r, ['bypassing sanctions', 'sanctions', 'vpn']))},
            ],
        },
        'ch2_regime': {
            'label': 'Anti / pro‑regime posts',
            'count': stance_counts.get('Pro-regime', 0) + stance_counts.get('Anti-regime', 0),
            'subitems': [
                {'label': 'Anti‑regime', 'count': stance_counts.get('Anti-regime', 0)},
                {'label': 'Pro‑regime',  'count': stance_counts.get('Pro-regime', 0)},
            ],
        },
        'ch3_popculture': {
            'label': 'Pop culture posts',
            'count': sum(1 for r in rows if theme_match(r, {'Pop culture', 'Exams'}) or kw_match(r, ['pop culture', 'film', 'meme', 'exam'])),
            'subitems': [
                {'label': 'Exam‑night memes', 'count': sum(1 for r in rows if kw_match(r, ['exam']))},
                {'label': 'Iranian films',    'count': sum(1 for r in rows if kw_match(r, ['film']))},
            ],
        },
        'ch4_intervention': {
            'label': 'Foreign intervention posts',
            'count': sum(1 for r in rows if theme_match(r, {'Foreign intervention'}) or kw_match(r, ['mexico', 'cartel', 'guadalajara', 'foreign intervention'])),
            'subitems': [
                {'label': 'Mexico / cartel', 'count': sum(1 for r in rows if kw_match(r, ['mexico', 'cartel', 'guadalajara']))},
            ],
        },
        'ch5_economy': {
            'label': 'Economy posts',
            'count': sum(1 for r in rows if theme_match(r, {'Iranian economy'}) or kw_match(r, ['economy', 'sanctions', 'iranian economy'])),
            'subitems': [
                {'label': 'Sanctions', 'count': sum(1 for r in rows if kw_match(r, ['sanctions']))},
            ],
        },
        'ch6_international': {
            'label': 'International news posts',
            'count': sum(1 for r in rows if theme_match(r, {'International news', 'Gaza Genocide', 'Hamas'}) or kw_match(r, ['gaza', 'axios', 'international', 'palestine'])),
            'subitems': [
                {'label': 'Gaza / genocide', 'count': sum(1 for r in rows if kw_match(r, ['gaza', 'palestine']))},
                {'label': 'Axios / US media',  'count': sum(1 for r in rows if kw_match(r, ['axios']))},
                {'label': 'Sports',          'count': sum(1 for r in rows if theme_match(r, {'Sports'}) or kw_match(r, ['sport', 'football', 'olympic']))},
            ],
        },
        'ch7_weather': {
            'label': 'Weather / landscape posts',
            'count': sum(1 for r in rows if theme_match(r, {'Weather and landscape'}) or kw_match(r, ['weather', 'snow', 'landscape', 'rain'])),
            'subitems': [
                {'label': 'Snow', 'count': sum(1 for r in rows if kw_match(r, ['snow']))},
                {'label': 'Landscape', 'count': sum(1 for r in rows if kw_match(r, ['landscape']))},
            ],
        },
    }
    for k, v in trackers.items():
        v['percent'] = pct(v['count'])
        for sub in v['subitems']:
            sub['percent'] = pct(sub['count'])

    stats = {
        'total': total,
        'videos': sum(1 for r in rows if r.get('media_filename', '').endswith('.mp4')),
        'images': sum(1 for r in rows if r.get('media_filename', '').endswith(('.jpg', '.png'))),
        'text_only': sum(1 for r in rows if not r.get('media_filename', '').strip()),
        'themes': dict(themes.most_common()),
        'top_keywords': dict(keywords.most_common(40)),
        'top_persons': dict(persons.most_common(15)),
        'ai_yes': ai_yes,
        'ai_no': ai_no,
        'trackers': trackers,
    }
    write_json('stats.json', stats, indent=2)

    # ----- Feb 28 live feed -----
    feb28 = [r for r in rows if r['date'] == '2026-02-28']
    feb28.sort(key=lambda r: r['time_est'])
    start_idx = 0
    for i, r in enumerate(feb28):
        if 'Lebanon' in (r.get('message_text_english', '') or '')[:120]:
            start_idx = i
            break
    feed = []
    for r in feb28[start_idx:start_idx + 22]:
        feed.append({
            'time_est': r['time_est'],
            'text_en': (r['message_text_english'] or '').strip(),
            'media': r['media_filename'],
        })
    write_json('feb28.json', feed, indent=2)

    # ----- Curated chapter posts -----
    by_fn = {r['media_filename']: r for r in rows if r['media_filename']}

    def screenshot_url(fn):
        if not fn or not fn.endswith('.mp4'):
            return None
        date = fn[:10]
        base = fn[:-4]
        sp_fs = os.path.join(SHOTS_DIR, date, base + '.jpg')
        if os.path.exists(sp_fs):
            return f'screenshots/{date}/{base}.jpg'
        return None

    def post(fn):
        r = by_fn.get(fn)
        if not r:
            return None
        mtype = 'video' if fn.endswith('.mp4') else 'image'
        screenshot = screenshot_url(fn) if mtype == 'video' else None
        audio_en = (r.get('audio_transcription_english', '') or '').strip()
        if is_repetitive(audio_en):
            audio_en = ''
        return {
            'filename': fn,
            'type': mtype,
            'screenshot': screenshot,
            'date': r['date'],
            'time_est': r['time_est'],
            'text_en': (r.get('message_text_english', '') or '').strip(),
            'text_fa': (r.get('message_text_persian', '') or '').strip(),
            'theme': r.get('theme', '').strip(),
            'keywords': r.get('keywords', '').strip(),
            'person': r.get('include_person', '').strip(),
            'ai_generated': r.get('AI_generated', '').strip(),
            'audio_en': audio_en,
            'ocr_en': (r.get('ocr_text_english', '') or '').strip()[:500],
        }

    chapters = {
        'opening': post('2026-03-29_002.mp4'),
        'ch1_ai': {
            'id': 'ch1', 'num': 1, 'title': 'Using AI', 'color': 'ai',
            'posts': [
                post('2026-01-01_007.jpg'),
                post('2026-01-01_035.mp4'),
                post('2026-01-01_028.mp4'),
                post('2026-01-01_054.mp4'),
                post('2026-01-02_020.mp4'),
            ],
        },
        'ch2_regime': {
            'id': 'ch2', 'num': 2, 'title': 'From Anti-Regime to Pro-Regime', 'color': 'regime',
            'posts_before': [
                post('2026-01-01_005.mp4'),
                post('2026-01-01_011.jpg'),
                post('2026-01-02_013.mp4'),
            ],
            'posts_after': [
                post('2026-03-07_001.mp4'),
                post('2026-03-14_035.mp4'),
                post('2026-03-14_076.mp4'),
            ],
        },
        'ch3_popculture': {
            'id': 'ch3', 'num': 3, 'title': 'Pop Culture', 'color': 'popculture',
            'posts': [
                post('2026-01-01_022.mp4'),
                post('2026-01-01_047.mp4'),
                post('2026-01-02_058.mp4'),
            ],
        },
        'ch4_intervention': {
            'id': 'ch4', 'num': 4, 'title': 'Foreign Intervention', 'color': 'intervention',
            'posts': [
                post('2026-02-23_006.mp4'),
                post('2026-02-23_011.mp4'),
                post('2026-02-23_029.mp4'),
            ],
        },
        'ch5_economy': {
            'id': 'ch5', 'num': 5, 'title': 'Iranian Economy', 'color': 'economy',
            'posts': [
                post('2026-01-01_011.jpg'),
                post('2026-01-04_036.jpg'),
                post('2026-01-01_007.jpg'),
            ],
        },
        'ch6_international': {
            'id': 'ch6', 'num': 6, 'title': 'International News', 'color': 'international',
            'posts': [
                post('2026-01-01_019.jpg'),
                post('2026-01-28_063.jpg'),
                post('2026-01-31_022.mp4'),
                post('2026-02-02_026.mp4'),
                post('2026-02-07_006.mp4'),
            ],
        },
        'ch7_weather': {
            'id': 'ch7', 'num': 7, 'title': 'Weather and Landscape', 'color': 'weather',
            'posts': [
                post('2026-01-01_008.mp4'),
                post('2026-01-01_014.jpg'),
                post('2026-01-01_050.mp4'),
                post('2026-01-02_004.mp4'),
                post('2026-01-02_007.mp4'),
                post('2026-01-02_018.mp4'),
                post('2026-01-02_021.mp4'),
                post('2026-01-02_022.mp4'),
            ],
        },
    }
    write_json('posts.json', chapters, indent=2)

    # ----- Regime sentiment data for the scatter -----
    def is_anti(r):
        return (r.get('theme', '').strip() == 'Anti-regime'
                or 'anti-regime' in (r.get('keywords', '') or '').lower()
                or 'anti regime' in (r.get('keywords', '') or '').lower())

    def is_pro(r):
        return (r.get('theme', '').strip() == 'Pro-regime'
                or 'pro-regime' in (r.get('keywords', '') or '').lower()
                or 'irgc' in (r.get('keywords', '') or '').lower())

    def thumb_for(fn):
        if not fn:
            return None
        if fn.endswith('.mp4'):
            return screenshot_url(fn)
        if fn.endswith(('.jpg', '.png')):
            return f'media/{fn}'
        return None

    def regime_pt(r, side):
        fn = r.get('media_filename', '').strip()
        thumb = thumb_for(fn)
        text = (r.get('message_text_english', '') or '').strip()
        if len(text) > 220:
            text = text[:200].strip() + '…'
        return {
            'date': r['date'],
            'time_est': r['time_est'],
            'side': side,           # 'anti' or 'pro'
            'thumb': thumb,
            'filename': fn or None,
            'text': text,
            'theme': r.get('theme', '').strip(),
            'keywords': r.get('keywords', '').strip(),
        }

    anti_posts = [regime_pt(r, 'anti') for r in rows if is_anti(r)]
    pro_posts  = [regime_pt(r, 'pro')  for r in rows if is_pro(r)]

    # Sub-counts: anti × economy, pro × IRGC, etc. (for the narrative copy)
    def kw_or_theme(r, kw_list, theme_set):
        kws = (r.get('keywords', '') or '').lower()
        return r.get('theme', '').strip() in theme_set or any(k in kws for k in kw_list)

    breakdown = {
        'anti_total':   len(anti_posts),
        'pro_total':    len(pro_posts),
        'anti_by': {
            'iranian_economy':   sum(1 for r in rows if is_anti(r) and kw_or_theme(r, ['economy'], {'Iranian economy'})),
            'protests':          sum(1 for r in rows if is_anti(r) and kw_or_theme(r, ['protest'], {'Protests'})),
            'commentary_us':     sum(1 for r in rows if is_anti(r) and kw_or_theme(r, ['axios', 'commentary on american media'], set())),
        },
        'pro_by': {
            'lego_animations':   sum(1 for r in rows if is_pro(r) and kw_or_theme(r, ['lego'], {'LEGO'})),
            'irgc_general':      sum(1 for r in rows if is_pro(r) and kw_or_theme(r, ['irgc'], set())),
            'war_coverage':      sum(1 for r in rows if is_pro(r) and kw_or_theme(r, ['war'], {'War coverage'})),
        },
    }

    write_json('regime.json', {
        'anti': anti_posts,
        'pro':  pro_posts,
        'breakdown': breakdown,
    }, indent=2)

    # ----- Carousel videos (manually downloaded April 2026) -----
    carousel = [
        {'filename': '2026-04-03_193300.mp4', 'date': '2026-04-03', 'poster': 'screenshots/carousel/2026-04-03_193300.jpg', 'caption': 'Lego-style propaganda video. April 3, 2026.'},
        {'filename': '2026-04-02_190255.mp4', 'date': '2026-04-02', 'poster': 'screenshots/carousel/2026-04-02_190255.jpg', 'caption': 'Stop-motion animation. April 2, 2026.'},
        {'filename': '2026-04-05_175411.mp4', 'date': '2026-04-05', 'poster': 'screenshots/carousel/2026-04-05_175411.jpg', 'caption': 'IRGC-themed Lego sequence. April 5, 2026.'},
        {'filename': '2026-04-08_162609.mp4', 'date': '2026-04-08', 'poster': 'screenshots/carousel/2026-04-08_162609.jpg', 'caption': 'Late-war animation. April 8, 2026.'},
        {'filename': '2026-04-03_193232.mp4', 'date': '2026-04-03', 'poster': 'screenshots/carousel/2026-04-03_193232.jpg', 'caption': 'Companion piece, April 3 batch.'},
    ]
    write_json('carousel.json', carousel, indent=2)

    build_classifier_feeds(rows)

    print('\nDone.')


# ---------------------------------------------------------------------------
# Phase 1 (pro/anti-regime stance) and Phase 2 (LEGO) classifier outputs.
# These live in their own CSVs rather than the master file, so they are merged
# here by row index — the classifiers were run over the corpus in file order.
# ---------------------------------------------------------------------------

STANCE_CSV = os.path.join(SITE_ROOT, 'CSVs', 'phase1_stance_predictions.csv')
LEGO_CSV = os.path.join(SITE_ROOT, 'CSVs', 'lego_predictions.csv')
# The round-2 stance run, kept when v4 was promoted. The LEGO chart breaks its
# posts down by THESE labels, deliberately, while the pro/anti bars elsewhere
# use the v4 labels in STANCE_CSV.
STANCE_V2_CSV = os.path.join(SITE_ROOT, 'CSVs', 'phase1_stance_predictions_v2.csv')
WAR_START = '2026-02-28'
MIN_WEEK_N = 20          # below this a weekly percentage is not load-bearing


def _read_indexed(path):
    """Read a predictions CSV keyed by original_row."""
    if not os.path.exists(path):
        print(f'  !! missing {os.path.basename(path)} — skipping')
        return {}
    out = {}
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                out[int(r['original_row'])] = r
            except (KeyError, ValueError):
                continue
    return out


def _week_start(datestr):
    """Monday-anchored week start, matching the notebook's W-SUN periods."""
    import datetime as _dt
    d = _dt.date.fromisoformat(datestr)
    return (d - _dt.timedelta(days=(d.weekday() + 1) % 7)).isoformat()


def build_classifier_feeds(rows):
    stance = _read_indexed(STANCE_CSV)
    stance_v2 = _read_indexed(STANCE_V2_CSV)
    lego = _read_indexed(LEGO_CSV)
    if not stance:
        return

    weeks = collections.defaultdict(
        lambda: {'n': 0, 'pro': 0, 'anti': 0, 'neither': 0, 'lego': 0,
                 'lego_pro_v2': 0, 'lego_anti_v2': 0, 'lego_neither_v2': 0})
    for i, row in enumerate(rows):
        date = (row.get('date') or '').strip()
        if not date:
            continue
        w = weeks[_week_start(date)]
        w['n'] += 1
        s = (stance.get(i, {}).get('p1_stance') or '').strip()
        if s == 'Pro-regime':
            w['pro'] += 1
        elif s == 'Anti-regime':
            w['anti'] += 1
        elif s:
            w['neither'] += 1
        if (lego.get(i, {}).get('lego') or '').strip() == 'Yes':
            w['lego'] += 1
            # LEGO posts broken down by the ROUND-2 stance labels, for the
            # LEGO-only chart. Uses stance_v2, not the v4 `s` above.
            # lego_pro_v2 + lego_anti_v2 + lego_neither_v2 == lego.
            s2 = (stance_v2.get(i, {}).get('p1_stance') or '').strip()
            if s2 == 'Pro-regime':
                w['lego_pro_v2'] += 1
            elif s2 == 'Anti-regime':
                w['lego_anti_v2'] += 1
            else:
                w['lego_neither_v2'] += 1

    weekly = []
    for wk in sorted(weeks):
        v = weeks[wk]
        n = v['n'] or 1
        weekly.append({
            'week': wk,
            'n': v['n'],
            'pro': v['pro'], 'anti': v['anti'], 'lego': v['lego'],
            'lego_pro_v2': v['lego_pro_v2'],
            'lego_anti_v2': v['lego_anti_v2'],
            'lego_neither_v2': v['lego_neither_v2'],
            'pro_pct': round(v['pro'] / n * 100, 2),
            'anti_pct': round(v['anti'] / n * 100, 2),
            'lego_pct': round(v['lego'] / n * 100, 2),
            # Weeks under the threshold are drawn hollow/dashed on the site.
            'thin': v['n'] < MIN_WEEK_N,
        })
    write_json('stance_weekly.json', {
        'war_start': WAR_START,
        'min_week_n': MIN_WEEK_N,
        'weeks': weekly,
    }, indent=2)

    # One record per pro/anti post for the interactive key-frame timeline.
    # Thumbnails come from thumbs/ (see make_thumbs.py); posts without a visual
    # carry no thumb and are drawn as solid colour tiles.
    thumbs_dir = os.path.join(SITE_ROOT, 'thumbs')
    stance_posts = []
    for i, row in enumerate(rows):
        s = (stance.get(i, {}).get('p1_stance') or '').strip()
        if s not in ('Pro-regime', 'Anti-regime'):
            continue
        media = (row.get('media_filename') or '').strip()
        thumb = ''
        if media:
            cand = os.path.splitext(media)[0] + '.jpg'
            if os.path.exists(os.path.join(thumbs_dir, cand)):
                thumb = 'thumbs/' + cand
        stance_posts.append({
            'row': i,
            'date': row.get('date', ''),
            'side': 'pro' if s == 'Pro-regime' else 'anti',
            'thumb': thumb,
            'is_video': media.lower().endswith(('.mp4', '.mov')),
            'text': (row.get('message_text_english') or '').strip()[:260],
            'why': (stance.get(i, {}).get('p1_reason') or '').strip()[:200],
            'conf': (stance.get(i, {}).get('p1_confidence') or '').strip(),
        })

    have_dates = sorted({r.get('date', '') for r in rows if r.get('date')})
    write_json('stance_posts.json', {
        'war_start': WAR_START,
        'dates_with_data': have_dates,
        'pro': sum(1 for p in stance_posts if p['side'] == 'pro'),
        'anti': sum(1 for p in stance_posts if p['side'] == 'anti'),
        'posts': stance_posts,
    })

    # Every post the LEGO classifier flagged, for the gallery under the chart.
    lego_posts = []
    for i, row in enumerate(rows):
        if (lego.get(i, {}).get('lego') or '').strip() != 'Yes':
            continue
        media = (row.get('media_filename') or '').strip()
        shot = ''
        if media.lower().endswith(('.mp4', '.mov')):
            stem = os.path.splitext(media)[0]
            cand = os.path.join(SHOTS_DIR, row.get('date', ''), stem + '.jpg')
            if os.path.exists(cand):
                shot = f"screenshots/{row.get('date','')}/{stem}.jpg"
        elif media:
            shot = f'media/{media}'
        lego_posts.append({
            'original_row': i,
            'date': row.get('date', ''),
            'media': media,
            'poster': shot,
            'is_video': media.lower().endswith(('.mp4', '.mov')),
            'text': (row.get('message_text_english') or '')[:280],
            'what': lego.get(i, {}).get('lego_what', ''),
            'stance': (stance.get(i, {}).get('p1_stance') or '').strip(),
        })
    write_json('lego.json', {
        'count': len(lego_posts),
        'pre_war': sum(1 for p in lego_posts if p['date'] < WAR_START),
        'post_war': sum(1 for p in lego_posts if p['date'] >= WAR_START),
        'posts': lego_posts,
    }, indent=2)


if __name__ == '__main__':
    main()

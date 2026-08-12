/* Scrollytelling main controller */
(function () {
  'use strict';

  const qs = (sel, ctx = document) => ctx.querySelector(sel);
  const qsa = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  /* ============================================================
     DATA LOADING
     ============================================================ */
  async function loadJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error('Failed to load ' + url);
    return r.json();
  }

  /* ============================================================
     HELPERS
     ============================================================ */
  function formatTime(iso) {
    // "2026-02-28 01:22:26 EST" -> "01:22 EST"
    const m = /(\d{2}:\d{2}):\d{2} (\w+)/.exec(iso || '');
    if (!m) return iso || '';
    return m[1] + ' ' + m[2];
  }

  function niceDate(d) {
    const [y, m, day] = d.split('-').map(Number);
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[m-1]} ${day}, ${y}`;
  }

  function mediaURL(filename) {
    return 'media/' + filename;
  }
  function posterURL(filename) {
    if (!filename) return null;
    if (filename.endsWith('.mp4')) {
      const base = filename.slice(0, -4);
      const date = filename.slice(0, 10);
      return `screenshots/${date}/${base}.jpg`;
    }
    return 'media/' + filename;
  }

  function el(tag, attrs = {}, children = []) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'className') e.className = v;
      else if (k === 'style') Object.assign(e.style, v);
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (v != null) e.setAttribute(k, v);
    }
    if (!Array.isArray(children)) children = [children];
    for (const c of children) {
      if (c == null || c === false) continue;
      if (typeof c === 'string') e.appendChild(document.createTextNode(c));
      else e.appendChild(c);
    }
    return e;
  }

  /* ============================================================
     POST CARD RENDERING
     ============================================================ */
  function renderPostCard(post, opts = {}) {
    if (!post) {
      // Placeholder for missing media
      return el('div', { className: 'post-card' }, [
        el('div', { className: 'post-media', style: { aspectRatio: '9/16', background: '#222' } }),
        el('div', { className: 'post-body' }, [
          el('div', { className: 'post-text muted' }, '(Media unavailable)')
        ])
      ]);
    }
    const { landscape = false } = opts;
    const mediaBox = el('div', { className: 'post-media' + (landscape ? ' landscape' : '') });

    if (post.type === 'video') {
      // Video posts are shown as their extracted key frame — only the Lego
      // carousel at the top of the page plays video.
      const img = el('img', {
        'data-src': post.screenshot || posterURL(post.filename) || '',
        alt: post.text_en ? post.text_en.slice(0, 80) : 'Post key frame',
        loading: 'lazy',
      });
      mediaBox.appendChild(img);
      mediaBox.appendChild(el('div', { className: 'video-indicator' }, 'Video'));
    } else {
      const img = el('img', {
        'data-src': mediaURL(post.filename),
        alt: post.text_en ? post.text_en.slice(0, 80) : 'Post image',
        loading: 'lazy',
      });
      mediaBox.appendChild(img);
    }

    // Meta row
    const meta = el('div', { className: 'post-meta' }, [
      el('span', {}, niceDate(post.date)),
      el('span', { className: 'sep' }, '·'),
      el('span', {}, formatTime(post.time_est || '')),
    ]);
    if (post.theme) {
      meta.appendChild(el('span', { className: 'sep' }, '·'));
      meta.appendChild(el('span', { className: 'chip' }, post.theme));
    }
    if ((post.ai_generated || '').toUpperCase() === 'YES') {
      meta.appendChild(el('span', { className: 'chip ai-flag' }, 'AI‑generated'));
    }

    const bodyChildren = [meta];
    if (post.text_en) {
      // truncate really long captions
      let txt = post.text_en;
      if (txt.length > 440) txt = txt.slice(0, 420).trim() + '…';
      bodyChildren.push(el('div', { className: 'post-text' }, txt));
    }

    if (post.keywords) {
      const tags = el('div', { className: 'post-tags' });
      post.keywords.split(',').map(k => k.trim()).filter(Boolean).slice(0, 6).forEach(k => {
        tags.appendChild(el('span', { className: 'tag' }, '#' + k));
      });
      bodyChildren.push(tags);
    }

    if (post.audio_en && post.audio_en.length > 15) {
      const details = el('details', { className: 'transcript' });
      details.appendChild(el('summary', {}, 'Audio transcription'));
      let audio = post.audio_en;
      if (audio.length > 420) audio = audio.slice(0, 400).trim() + '…';
      details.appendChild(el('div', { className: 'transcript-body' }, audio));
      bodyChildren.push(details);
    }

    const card = el('div', { className: 'post-card' }, [
      mediaBox,
      el('div', { className: 'post-body' }, bodyChildren),
    ]);
    return card;
  }

  /* ============================================================
     VIDEO CONTROLLER: autoplay on scroll
     ============================================================ */
  function setupVideoController() {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        const v = entry.target;
        if (entry.isIntersecting) {
          if (v.getAttribute('data-src') && !v.src) v.src = v.getAttribute('data-src');
          v.play().catch(() => {});
        } else {
          v.pause();
        }
      });
    }, { threshold: 0.5 });

    // Lazy image observer too
    const imgIO = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const img = entry.target;
          const src = img.getAttribute('data-src');
          if (src) img.src = src;
          imgIO.unobserve(img);
        }
      });
    }, { rootMargin: '200px' });

    // Reobserve periodically as new elements append
    function observeAll() {
      qsa('video[data-src]').forEach(v => io.observe(v));
      qsa('img[data-src]:not([src])').forEach(i => imgIO.observe(i));
    }
    observeAll();
    // Export for later re-runs
    window.__observeMedia = observeAll;
  }

  /* ============================================================
     PROGRESS BAR + CHAPTER DOTS
     ============================================================ */
  function setupProgressBar() {
    const bar = qs('.progress-bar');
    const fill = qs('.progress-bar-fill');
    const dots = qsa('.chapter-dot');
    const chapters = qsa('[data-chapter]');

    function onScroll() {
      const scrolled = window.scrollY;
      const total = document.documentElement.scrollHeight - window.innerHeight;
      const pct = total > 0 ? (scrolled / total) * 100 : 0;
      fill.style.width = pct + '%';

      // Show after hero
      const hero = qs('.hero');
      if (hero && scrolled > hero.offsetHeight * 0.6) {
        bar.classList.add('visible');
      } else {
        bar.classList.remove('visible');
      }

      // Active chapter dot
      const midLine = scrolled + window.innerHeight * 0.35;
      let active = null;
      chapters.forEach(ch => {
        if (ch.offsetTop <= midLine) active = ch.getAttribute('data-chapter');
      });
      dots.forEach(d => d.classList.toggle('active', d.getAttribute('data-target') === active));
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    dots.forEach(d => {
      d.addEventListener('click', () => {
        const target = qs(`[data-chapter="${d.getAttribute('data-target')}"]`);
        if (target) window.scrollTo({ top: target.offsetTop - 20, behavior: 'smooth' });
      });
    });
  }

  /* ============================================================
     HERO VIDEO
     ============================================================ */
  function setupHero() {
    const v = qs('.hero-video');
    if (!v) return;
    v.muted = true;
    v.play().catch(() => {});
    const btn = qs('.hero .sound-toggle');
    if (btn) {
      btn.addEventListener('click', () => {
        v.muted = !v.muted;
        btn.textContent = v.muted ? '🔇' : '🔊';
        if (!v.muted && v.paused) v.play().catch(() => {});
      });
    }
  }

  /* ============================================================
     STAT CARDS — count up
     ============================================================ */
  function setupStatCounters() {
    const cards = qsa('.stat-card');
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        const el = e.target.querySelector('.num');
        const target = parseInt(el.getAttribute('data-value'), 10);
        if (isNaN(target)) return;
        const dur = 1600;
        const t0 = performance.now();
        function tick(t) {
          const p = Math.min(1, (t - t0) / dur);
          const eased = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.floor(target * eased).toLocaleString();
          if (p < 1) requestAnimationFrame(tick);
          else el.textContent = target.toLocaleString();
        }
        requestAnimationFrame(tick);
        io.unobserve(e.target);
      });
    }, { threshold: 0.4 });
    cards.forEach(c => io.observe(c));
  }

  /* ============================================================
     TIMELINE CHART (D3)
     ============================================================ */
  /* ------------------------------------------------------------------ *
   * Interactive key-frame timeline: one tile per pro/anti post, stacked by
   * the day it was posted. Pro-regime above the centre line, anti-regime
   * below — the same layout as the notebook chart, but every tile is
   * hoverable. Days with no collected posts are shaded so a gap in the
   * data never reads as silence from the channel.
   * ------------------------------------------------------------------ */
  function renderStanceTimeline(feed) {
    const chart = qs('#stance-timeline');
    if (!chart || !feed || !feed.posts) return;
    chart.innerHTML = '';

    const PRO = '#2a78d6', ANTI = '#e34946';
    const parse = d3.timeParse('%Y-%m-%d');
    const posts = feed.posts.map(p => ({ ...p, _d: parse(p.date) }));

    const width = chart.clientWidth || 960;
    const tile = width > 900 ? 13 : 9;
    const gap = 1;
    const margin = { top: 26, right: 14, bottom: 40, left: 40 };

    // Tallest stack on either side sets the height.
    // One day peaks at 62 posts on a side; drawing all of them makes the chart
    // taller than a screen. Cap the stack and mark the overflow instead.
    const MAX_STACK = 20;
    const perDaySide = d3.rollup(posts, v => v.length, p => p.date + '|' + p.side);
    const maxStack = Math.min(MAX_STACK, Math.max(4, d3.max(perDaySide.values()) || 4));
    const half = maxStack * (tile + gap) + 22;
    const height = half * 2 + margin.top + margin.bottom;
    const mid = margin.top + half;

    const start = parse('2025-12-31'), end = parse('2026-04-09');
    const x = d3.scaleTime()
      .domain([start, d3.timeDay.offset(end, 1)])
      .range([margin.left, width - margin.right]);

    const svg = d3.select(chart).append('svg')
      .attr('class', 'stance-timeline-svg')
      .attr('viewBox', `0 0 ${width} ${height}`);

    // Shade days with no collected messages.
    const have = new Set(feed.dates_with_data || []);
    const dayW = Math.max(1.5, (x(d3.timeDay.offset(start, 1)) - x(start)));
    d3.timeDay.range(start, d3.timeDay.offset(end, 1)).forEach(d => {
      const key = d3.timeFormat('%Y-%m-%d')(d);
      if (!have.has(key)) {
        svg.append('rect')
          .attr('x', x(d)).attr('y', margin.top)
          .attr('width', dayW).attr('height', height - margin.top - margin.bottom)
          .attr('fill', 'rgba(255,255,255,0.06)');
      }
    });

    // Stack each day's posts outward from the centre line.
    const stacked = [], overflow = [];
    d3.groups(posts, p => p.date + '|' + p.side).forEach(([, group]) => {
      group.forEach((p, i) => {
        if (i >= MAX_STACK) return;
        const off = 10 + i * (tile + gap);
        p._x = x(p._d) - tile / 2;
        p._y = p.side === 'pro' ? mid - off - tile : mid + off;
        stacked.push(p);
      });
      if (group.length > MAX_STACK) {
        const p0 = group[0], extra = group.length - MAX_STACK;
        const off = 10 + MAX_STACK * (tile + gap);
        overflow.push({
          x: x(p0._d), side: p0.side, n: extra,
          y: p0.side === 'pro' ? mid - off - 2 : mid + off + tile,
        });
      }
    });

    const tooltip = d3.select(chart).append('div').attr('class', 'timeline-tooltip');

    const g = svg.append('g');
    const tileNodes = [];
    stacked.forEach(p => {
      const col = p.side === 'pro' ? PRO : ANTI;
      const node = g.append('g').attr('class', 'tl-tile')
        .attr('transform', `translate(${p._x},${p._y})`);
      if (p.thumb) {
        node.append('image')
          .attr('href', p.thumb).attr('width', tile).attr('height', tile)
          .attr('preserveAspectRatio', 'xMidYMid slice');
        node.append('rect')
          .attr('width', tile).attr('height', tile)
          .attr('fill', 'none').attr('stroke', col).attr('stroke-width', 1);
      } else {
        // Text-only post: a solid tile, so the day's volume stays truthful.
        node.append('rect')
          .attr('width', tile).attr('height', tile)
          .attr('fill', col).attr('opacity', 0.55);
      }
      tileNodes.push({ node, p });
      node.on('mouseenter', function (event) {
        d3.select(this).select('rect').attr('stroke-width', 2.5);
        const side = p.side === 'pro' ? 'Pro-regime' : 'Anti-regime';
        tooltip.classed('visible', true).html(
          `<div class="tt-head" style="color:${col}">${side}` +
          `<span class="tt-date">${p.date}${p.is_video ? ' · video' : ''}</span></div>` +
          (p.thumb ? `<img src="${p.thumb}" alt="" />` : '') +
          `<div class="tt-text">${(p.text || '(no caption)').replace(/</g, '&lt;')}</div>` +
          (p.why ? `<div class="tt-why">Classifier: ${p.why.replace(/</g, '&lt;')} (${p.conf})</div>` : '')
        );
      }).on('mousemove', function (event) {
        const box = chart.getBoundingClientRect();
        const tx = event.clientX - box.left, ty = event.clientY - box.top;
        tooltip
          .style('left', Math.min(Math.max(tx + 14, 8), box.width - 280) + 'px')
          .style('top', Math.max(ty - 40, 8) + 'px');
      }).on('mouseleave', function () {
        d3.select(this).select('rect').attr('stroke-width', 1);
        tooltip.classed('visible', false);
      });
    });

    // Centre line, war marker, side labels, axis.
    svg.append('line').attr('x1', margin.left).attr('x2', width - margin.right)
      .attr('y1', mid).attr('y2', mid)
      .attr('stroke', 'rgba(255,255,255,0.75)').attr('stroke-width', 1);

    const warX = x(parse(feed.war_start));
    const warMarker = svg.append('line').attr('x1', warX).attr('x2', warX)
      .attr('y1', margin.top).attr('y2', height - margin.bottom)
      .attr('stroke', '#fff').attr('stroke-width', 1.6).attr('stroke-dasharray', '6 4');
    svg.append('text').attr('x', warX + 7).attr('y', margin.top + 12)
      .attr('fill', '#fff').attr('font-size', 13).attr('font-weight', 700)
      .text('the war begins');

    svg.append('text').attr('x', margin.left).attr('y', margin.top + 12)
      .attr('fill', PRO).attr('font-size', 13).attr('font-weight', 700)
      .text(`Pro-regime (${feed.pro.toLocaleString()})`);
    svg.append('text').attr('x', margin.left).attr('y', height - margin.bottom - 4)
      .attr('fill', ANTI).attr('font-size', 13).attr('font-weight', 700)
      .text(`Anti-regime (${feed.anti.toLocaleString()})`);

    svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).ticks(d3.timeWeek.every(2)).tickFormat(d3.timeFormat('%d %b')))
      .call(sel => sel.select('.domain').remove())
      .attr('color', 'rgba(255,255,255,0.5)').attr('font-size', 12);

    // Tell the page how much was truncated, so the caption can say so.
    const cappedDays = overflow.length;
    const deepest = d3.max(perDaySide.values()) || 0;
    const note = qs('.scrolly-caption');
    if (note && cappedDays) {
      note.innerHTML += ` Stacks are capped at ${MAX_STACK} posts per day per side —`
        + ` ${cappedDays} day-sides exceed that, the busiest being ${deepest} posts on a single day.`;
    }

    // ---- scrollytelling states -------------------------------------------
    // Each step dims everything except the posts it is talking about, so the
    // reader's eye lands on the subset the sentence describes.
    const war = feed.war_start;
    const MATCH = {
      'prewar-anti':  p => p.side === 'anti' && p.date <  war,
      'war':          p => p.date === war,
      'postwar-pro':  p => p.side === 'pro'  && p.date >= war,
      'postwar-anti': p => p.side === 'anti' && p.date >= war,
      'gaps':         () => false,
      'all':          () => true,
    };

    const gapBands = svg.selectAll('rect').filter(function () {
      return d3.select(this).attr('fill') === 'rgba(255,255,255,0.06)';
    });

    chart.__setState = function (state) {
      const test = MATCH[state] || MATCH.all;
      const noneMatch = state === 'gaps';
      tileNodes.forEach(({ node, p }) => {
        node.transition().duration(320)
          .style('opacity', noneMatch ? 0.12 : (test(p) ? 1 : 0.13));
      });
      gapBands.transition().duration(320)
        .attr('fill', noneMatch ? 'rgba(255,255,255,0.30)' : 'rgba(255,255,255,0.06)');
      warMarker.transition().duration(320)
        .attr('stroke-width', state === 'war' ? 3.4 : 1.6)
        .attr('stroke', state === 'war' ? '#ffd166' : '#fff');
    };
    chart.__setState('all');
  }

  /* Drive the pinned chart from whichever step is in view. */
  function setupScrolly() {
    const chart = qs('#stance-timeline');
    const steps = qsa('.scrolly-steps .step');
    if (!chart || !steps.length) return;

    const io = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        steps.forEach(s => s.classList.remove('is-active'));
        entry.target.classList.add('is-active');
        // Past the final step the overlay clears and the chart is the reader's.
        const scrolly = qs('.scrolly');
        if (scrolly) scrolly.classList.toggle('released',
          entry.target.classList.contains('step-release'));
        if (typeof chart.__setState === 'function') {
          chart.__setState(entry.target.getAttribute('data-state') || 'all');
        }
      });
    }, { rootMargin: '-45% 0px -45% 0px', threshold: 0 });

    steps.forEach(s => io.observe(s));
  }

  /* ------------------------------------------------------------------ *
   * Weekly regime-stance chart (mirrored: pro above the axis, anti below)
   * with an optional LEGO overlay. Weeks below the support threshold are
   * drawn hollow on a dashed line so a 2-message week can never read as a
   * trend. Hover any week for the underlying counts.
   * ------------------------------------------------------------------ */
  function renderStanceWeekly(feed, opts = {}) {
    const container = qs(opts.target);
    if (!container || !feed || !feed.weeks) return;
    container.innerHTML = '';

    const weeks = feed.weeks.map(w => ({ ...w, d: d3.timeParse('%Y-%m-%d')(w.week) }));
    const width = Math.min(940, container.clientWidth || 940);
    const height = 420;
    const margin = { top: 34, right: 26, bottom: 42, left: 52 };
    const PRO = '#2a78d6', ANTI = '#e34946', INK = '#f2f0eb';

    const svg = d3.select(container).append('svg')
      .attr('class', 'stance-svg')
      .attr('viewBox', `0 0 ${width} ${height}`);

    const x = d3.scaleTime()
      .domain(d3.extent(weeks, d => d.d))
      .range([margin.left, width - margin.right]);
    const maxUp = d3.max(weeks, d => Math.max(d.pro_pct, opts.lego ? d.lego_pct : 0)) || 100;
    const maxDn = d3.max(weeks, d => d.anti_pct) || 10;
    const y = d3.scaleLinear()
      .domain([-(maxDn + 6), maxUp + 10])
      .range([height - margin.bottom, margin.top]);

    // Thin weeks get a shaded column — the visual warning that the
    // percentage behind it rests on very few messages.
    const wk = (width - margin.left - margin.right) / weeks.length;
    svg.append('g').selectAll('rect').data(weeks.filter(d => d.thin)).join('rect')
      .attr('x', d => x(d.d) - wk / 2).attr('y', margin.top)
      .attr('width', wk).attr('height', height - margin.top - margin.bottom)
      .attr('fill', 'rgba(255,255,255,0.055)');

    // Gridlines + zero axis
    svg.append('g').selectAll('line').data(y.ticks(8)).join('line')
      .attr('x1', margin.left).attr('x2', width - margin.right)
      .attr('y1', d => y(d)).attr('y2', d => y(d))
      .attr('stroke', 'rgba(255,255,255,0.07)');
    svg.append('line')
      .attr('x1', margin.left).attr('x2', width - margin.right)
      .attr('y1', y(0)).attr('y2', y(0))
      .attr('stroke', INK).attr('stroke-width', 1.2);

    const solid = weeks.filter(d => !d.thin);
    const line = (acc, sign) => d3.line()
      .defined(d => d[acc] != null)
      .x(d => x(d.d)).y(d => y(sign * d[acc]));

    // Faint dashed spine through every week, solid only where supported.
    [['pro_pct', 1, PRO], ['anti_pct', -1, ANTI]].forEach(([acc, sign, col]) => {
      svg.append('path').datum(weeks).attr('fill', 'none').attr('stroke', col)
        .attr('stroke-width', 1.2).attr('stroke-dasharray', '4 3')
        .attr('opacity', 0.55).attr('d', line(acc, sign));
      svg.append('path').datum(solid).attr('fill', 'none').attr('stroke', col)
        .attr('stroke-width', 2.4).attr('d', line(acc, sign));
      svg.append('g').selectAll('circle').data(weeks).join('circle')
        .attr('cx', d => x(d.d)).attr('cy', d => y(sign * d[acc])).attr('r', 4.6)
        .attr('fill', d => d.thin ? 'transparent' : col)
        .attr('stroke', d => d.thin ? col : 'rgba(0,0,0,0.35)')
        .attr('stroke-width', d => d.thin ? 1.8 : 1);
    });

    if (opts.lego) {
      svg.append('path').datum(weeks).attr('fill', 'none').attr('stroke', INK)
        .attr('stroke-width', 1.4).attr('stroke-dasharray', '4 3')
        .attr('opacity', 0.7).attr('d', line('lego_pct', 1));
      svg.append('path').datum(solid).attr('fill', 'none').attr('stroke', INK)
        .attr('stroke-width', 3.6).attr('d', line('lego_pct', 1));
      svg.append('g').selectAll('circle').data(weeks).join('circle')
        .attr('cx', d => x(d.d)).attr('cy', d => y(d.lego_pct)).attr('r', 4.6)
        .attr('fill', d => d.thin ? 'transparent' : INK)
        .attr('stroke', INK).attr('stroke-width', d => d.thin ? 1.8 : 1);
    }

    // War marker
    const war = d3.timeParse('%Y-%m-%d')(feed.war_start);
    svg.append('line').attr('x1', x(war)).attr('x2', x(war))
      .attr('y1', margin.top - 8).attr('y2', height - margin.bottom)
      .attr('stroke', INK).attr('stroke-width', 1.6).attr('stroke-dasharray', '6 4');
    svg.append('text').attr('x', x(war) + 8).attr('y', margin.top - 12)
      .attr('fill', INK).attr('font-size', 13).attr('font-weight', 700)
      .text('the war begins');

    // Axes — y labels are absolute values because the axis is mirrored.
    svg.append('g').attr('transform', `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(8).tickFormat(v => Math.abs(v) + '%'))
      .call(g => g.select('.domain').remove())
      .attr('color', 'rgba(255,255,255,0.5)').attr('font-size', 12);
    svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).ticks(7).tickFormat(d3.timeFormat('%d %b')))
      .call(g => g.select('.domain').remove())
      .attr('color', 'rgba(255,255,255,0.5)').attr('font-size', 12);

    // Hover layer: one invisible band per week drives the tooltip.
    const tip = d3.select(container).append('div').attr('class', 'stance-tooltip');
    const focus = svg.append('line').attr('y1', margin.top).attr('y2', height - margin.bottom)
      .attr('stroke', 'rgba(255,255,255,0.35)').attr('stroke-width', 1).style('opacity', 0);

    svg.append('g').selectAll('rect').data(weeks).join('rect')
      .attr('x', d => x(d.d) - wk / 2).attr('y', margin.top)
      .attr('width', wk).attr('height', height - margin.top - margin.bottom)
      .attr('fill', 'transparent').style('cursor', 'crosshair')
      .on('mousemove', function (event, d) {
        focus.attr('x1', x(d.d)).attr('x2', x(d.d)).style('opacity', 1);
        const fmt = d3.timeFormat('%d %b %Y');
        tip.style('opacity', 1)
          .style('left', Math.min(x(d.d) / width * 100, 72) + '%')
          .style('top', '8px')
          .html(
            `<strong>week of ${fmt(d.d)}</strong>` +
            `<div class="tt-row"><span class="sw" style="background:${PRO}"></span>Pro-regime <b>${d.pro_pct}%</b> <em>(${d.pro})</em></div>` +
            `<div class="tt-row"><span class="sw" style="background:${ANTI}"></span>Anti-regime <b>${d.anti_pct}%</b> <em>(${d.anti})</em></div>` +
            (opts.lego ? `<div class="tt-row"><span class="sw" style="background:${INK}"></span>LEGO <b>${d.lego_pct}%</b> <em>(${d.lego})</em></div>` : '') +
            `<div class="tt-n">${d.n} messages that week${d.thin ? ' — too few to be reliable' : ''}</div>`
          );
      })
      .on('mouseleave', () => { tip.style('opacity', 0); focus.style('opacity', 0); });
  }

  /* ------------------------------------------------------------------ *
   * Weekly regime-stance chart, stacked bars of RAW COUNTS.
   *
   * Replaces the mirrored percentage lines. Counts rather than shares, so a
   * week with a handful of posts reads as a short bar instead of being
   * rescaled into a percentage that implies a trend. Every week is drawn —
   * there is no support threshold and nothing is hollowed out or hidden.
   *
   * Weeks where nothing was collected are not present in the feed at all, so
   * the grid is rebuilt at a 7-day step and the missing weeks are shaded grey.
   * ------------------------------------------------------------------ */
  function renderStanceWeeklyBars(feed, opts = {}) {
    const container = qs(opts.target);
    if (!container || !feed || !feed.weeks || !feed.weeks.length) return;
    container.innerHTML = '';

    const parse = d3.timeParse('%Y-%m-%d');
    const key = d3.timeFormat('%Y-%m-%d');
    const given = feed.weeks.map(w => ({ ...w, d: parse(w.week) }))
                            .sort((a, b) => a.d - b.d);

    // Rebuild a complete weekly grid. timeDay.offset (not +7*864e5) so a DST
    // change cannot shift a key and drop a week.
    const byKey = new Map(given.map(d => [d.week, d]));
    const last = given[given.length - 1].d;
    const weeks = [];
    for (let d = given[0].d; d <= last; d = d3.timeDay.offset(d, 7)) {
      const k = key(d);
      weeks.push(byKey.get(k) ||
        { week: k, d: new Date(+d), n: null, pro: 0, anti: 0, missing: true });
    }
    weeks.forEach(w => { w.stance = (w.pro || 0) + (w.anti || 0); });

    const width = Math.min(940, container.clientWidth || 940);
    const height = 420;
    const margin = { top: 34, right: 26, bottom: 42, left: 52 };
    // Same hues as before: validated on this dark surface (protan ΔE 21.9).
    const PRO = '#2a78d6', ANTI = '#e34946', INK = '#f2f0eb';
    const LEGO = '#3f4d60';                      // neutral slate under the hatch
    const GAP = '#0d1117';                       // section bg — the segment gap

    const svg = d3.select(container).append('svg')
      .attr('class', 'stance-svg')
      .attr('viewBox', `0 0 ${width} ${height}`);

    const x = d3.scaleTime()
      .domain([weeks[0].d, d3.timeDay.offset(last, 7)])
      .range([margin.left, width - margin.right]);
    const y = d3.scaleLinear()
      .domain([0, (d3.max(weeks, d => d.stance) || 1) * 1.18])
      .range([height - margin.bottom, margin.top]);

    const bw = d => Math.max(1, x(d3.timeDay.offset(d.d, 7)) - x(d.d) - 2);

    svg.append('g').selectAll('line').data(y.ticks(6)).join('line')
      .attr('x1', margin.left).attr('x2', width - margin.right)
      .attr('y1', d => y(d)).attr('y2', d => y(d))
      .attr('stroke', 'rgba(255,255,255,0.07)');

    // Stacked: pro at the base, anti above it. A GAP-coloured stroke gives the
    // 2px separation between the two segments.
    [['pro', 0, PRO], ['anti', 1, ANTI]].forEach(([acc, stackAbove, col]) => {
      svg.append('g').selectAll('rect')
        .data(weeks.filter(d => (d[acc] || 0) > 0)).join('rect')
        .attr('x', d => x(d.d))
        .attr('y', d => y((stackAbove ? d.pro || 0 : 0) + d[acc]))
        .attr('width', bw)
        .attr('height', d => Math.max(0, y(0) - y(d[acc])))
        .attr('fill', col)
        .attr('stroke', GAP).attr('stroke-width', 1.2);
    });

    // LEGO band: the Phase 2 vision classifier's count for the week, straight
    // from lego_predictions.csv. It is an INDEPENDENT classification — not a
    // subdivision of the stance model — so it gets its own neutral fill rather
    // than a tint of the pro-regime blue, and it is drawn as an overlay from
    // the baseline that adds no height to the stack. No post is counted twice,
    // and where LEGO exceeds the stance bars (a week whose LEGO posts took no
    // stance) the band simply rises past them.
    if (opts.lego) {
      const pid = 'lego-hatch-' + String(opts.target || '').replace(/\W/g, '');
      const pat = svg.append('defs').append('pattern')
        .attr('id', pid).attr('width', 7).attr('height', 7)
        .attr('patternUnits', 'userSpaceOnUse')
        .attr('patternTransform', 'rotate(45)');
      pat.append('rect').attr('width', 7).attr('height', 7).attr('fill', LEGO);
      pat.append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 7)
        .attr('stroke', 'rgba(255,255,255,0.92)').attr('stroke-width', 2.4);

      svg.append('g').selectAll('rect')
        .data(weeks.filter(d => (d.lego || 0) > 0)).join('rect')
        .attr('x', d => x(d.d))
        .attr('y', d => y(d.lego))
        .attr('width', bw)
        .attr('height', d => Math.max(0, y(0) - y(d.lego)))
        .attr('fill', `url(#${pid})`)
        .attr('stroke', GAP).attr('stroke-width', 1.2);
    }

    // A collected week that produced no stance-taking posts would be an empty
    // slot, indistinguishable from a no-collection week. Mark it on the base.
    svg.append('g').selectAll('line')
      .data(weeks.filter(d => !d.missing && d.n > 0 && d.stance === 0)).join('line')
      .attr('x1', d => x(d.d)).attr('x2', d => x(d.d) + bw(d))
      .attr('y1', y(0)).attr('y2', y(0))
      .attr('stroke', 'rgba(255,255,255,0.55)').attr('stroke-width', 2.6);

    svg.append('line')
      .attr('x1', margin.left).attr('x2', width - margin.right)
      .attr('y1', y(0)).attr('y2', y(0))
      .attr('stroke', INK).attr('stroke-width', 1.2);

    const war = parse(feed.war_start);
    svg.append('line').attr('x1', x(war)).attr('x2', x(war))
      .attr('y1', margin.top - 8).attr('y2', height - margin.bottom)
      .attr('stroke', INK).attr('stroke-width', 1.6).attr('stroke-dasharray', '6 4');
    svg.append('text').attr('x', x(war) + 8).attr('y', margin.top - 12)
      .attr('fill', INK).attr('font-size', 13).attr('font-weight', 700)
      .text('the war begins');

    svg.append('g').attr('transform', `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(6).tickFormat(d3.format('d')))
      .call(g => g.select('.domain').remove())
      .attr('color', 'rgba(255,255,255,0.5)').attr('font-size', 12);
    svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).ticks(7).tickFormat(d3.timeFormat('%d %b')))
      .call(g => g.select('.domain').remove())
      .attr('color', 'rgba(255,255,255,0.5)').attr('font-size', 12);

    const tip = d3.select(container).append('div').attr('class', 'stance-tooltip');
    svg.append('g').selectAll('rect').data(weeks).join('rect')
      .attr('x', d => x(d.d)).attr('y', margin.top)
      .attr('width', d => bw(d) + 2)
      .attr('height', height - margin.top - margin.bottom)
      .attr('fill', 'transparent').style('cursor', 'crosshair')
      .on('mousemove', function (event, d) {
        const fmt = d3.timeFormat('%d %b %Y');
        tip.style('opacity', 1)
          .style('left', Math.min(x(d.d) / width * 100, 72) + '%')
          .style('top', '8px')
          .html(
            `<strong>week of ${fmt(d.d)}</strong>` +
            (d.missing
              ? '<div class="tt-n">no messages collected</div>'
              : `<div class="tt-row"><span class="sw" style="background:${PRO}"></span>Pro-regime <b>${d.pro}</b> <em>(${d.pro_pct}%)</em></div>` +
                `<div class="tt-row"><span class="sw" style="background:${ANTI}"></span>Anti-regime <b>${d.anti}</b> <em>(${d.anti_pct}%)</em></div>` +
                (opts.lego ? `<div class="tt-row"><span class="sw" style="background:${LEGO};background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.92) 0 2px,transparent 2px 5px)"></span>LEGO <b>${d.lego || 0}</b> <em>(Phase 2)</em></div>` : '') +
                (opts.lego ? `<div class="tt-n">${d.n} messages that week · LEGO counted separately from stance</div>`
                           : `<div class="tt-n">${d.n} messages that week</div>`))
          );
      })
      .on('mouseleave', () => { tip.style('opacity', 0); });
  }

  /* ------------------------------------------------------------------ *
   * LEGO-only weekly chart: the 24 Phase 2 LEGO posts, stacked by their
   * ROUND-2 (v2) stance labels — 18 pro-regime, 6 neither. Counts, not shares.
   * The pro/anti bars in the other chart use v4; this one deliberately does
   * not, so it reads lego_*_v2 rather than the v4 fields.
   *
   * Note on the empty series: no LEGO post is classified anti-regime under
   * either stance version, so the light-yellow segment exists in the legend
   * and the code but has nothing to draw.
   * ------------------------------------------------------------------ */
  function renderLegoStanceBars(feed, opts = {}) {
    const container = qs(opts.target);
    if (!container || !feed || !feed.weeks || !feed.weeks.length) return;
    container.innerHTML = '';

    const parse = d3.timeParse('%Y-%m-%d');
    const weeks = feed.weeks.map(w => ({ ...w, d: parse(w.week) }))
                            .sort((a, b) => a.d - b.d);
    weeks.forEach(w => {
      w.legoTotal = (w.lego_pro_v2 || 0) + (w.lego_anti_v2 || 0) + (w.lego_neither_v2 || 0);
    });

    const width = Math.min(940, container.clientWidth || 940);
    const height = 420;
    const margin = { top: 34, right: 26, bottom: 42, left: 52 };
    const L_PRO = '#b85c1a';      // dark orange — pro-regime LEGO
    const L_ANTI = '#f2d275';     // light yellow — anti-regime LEGO (none exist)
    const L_NEITHER = '#4a5666';  // muted — LEGO taking no stance
    const INK = '#f2f0eb', GAP = '#0d1117';

    const svg = d3.select(container).append('svg')
      .attr('class', 'stance-svg')
      .attr('viewBox', `0 0 ${width} ${height}`);

    const last = weeks[weeks.length - 1].d;
    const x = d3.scaleTime()
      .domain([weeks[0].d, d3.timeDay.offset(last, 7)])
      .range([margin.left, width - margin.right]);
    const y = d3.scaleLinear()
      .domain([0, (d3.max(weeks, d => d.legoTotal) || 1) * 1.25])
      .range([height - margin.bottom, margin.top]);
    const bw = d => Math.max(1, x(d3.timeDay.offset(d.d, 7)) - x(d.d) - 2);

    svg.append('g').selectAll('line').data(y.ticks(5)).join('line')
      .attr('x1', margin.left).attr('x2', width - margin.right)
      .attr('y1', d => y(d)).attr('y2', d => y(d))
      .attr('stroke', 'rgba(255,255,255,0.07)');

    // Bottom to top: pro-regime, anti-regime, neither.
    const series = [['lego_pro_v2', L_PRO], ['lego_anti_v2', L_ANTI],
                    ['lego_neither_v2', L_NEITHER]];
    series.forEach(([acc, col], i) => {
      const below = series.slice(0, i).map(s => s[0]);
      svg.append('g').selectAll('rect')
        .data(weeks.filter(d => (d[acc] || 0) > 0)).join('rect')
        .attr('x', d => x(d.d))
        .attr('y', d => y(below.reduce((s, k) => s + (d[k] || 0), 0) + d[acc]))
        .attr('width', bw)
        .attr('height', d => Math.max(0, y(0) - y(d[acc])))
        .attr('fill', col)
        .attr('stroke', GAP).attr('stroke-width', 1.2);
    });

    svg.append('line')
      .attr('x1', margin.left).attr('x2', width - margin.right)
      .attr('y1', y(0)).attr('y2', y(0))
      .attr('stroke', INK).attr('stroke-width', 1.2);

    const war = parse(feed.war_start);
    svg.append('line').attr('x1', x(war)).attr('x2', x(war))
      .attr('y1', margin.top - 8).attr('y2', height - margin.bottom)
      .attr('stroke', INK).attr('stroke-width', 1.6).attr('stroke-dasharray', '6 4');
    svg.append('text').attr('x', x(war) + 8).attr('y', margin.top - 12)
      .attr('fill', INK).attr('font-size', 13).attr('font-weight', 700)
      .text('the war begins');

    svg.append('g').attr('transform', `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(5).tickFormat(d3.format('d')))
      .call(g => g.select('.domain').remove())
      .attr('color', 'rgba(255,255,255,0.5)').attr('font-size', 12);
    svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).ticks(7).tickFormat(d3.timeFormat('%d %b')))
      .call(g => g.select('.domain').remove())
      .attr('color', 'rgba(255,255,255,0.5)').attr('font-size', 12);

    const tip = d3.select(container).append('div').attr('class', 'stance-tooltip');
    svg.append('g').selectAll('rect').data(weeks).join('rect')
      .attr('x', d => x(d.d)).attr('y', margin.top)
      .attr('width', d => bw(d) + 2)
      .attr('height', height - margin.top - margin.bottom)
      .attr('fill', 'transparent').style('cursor', 'crosshair')
      .on('mousemove', function (event, d) {
        const fmt = d3.timeFormat('%d %b %Y');
        tip.style('opacity', 1)
          .style('left', Math.min(x(d.d) / width * 100, 72) + '%')
          .style('top', '8px')
          .html(
            `<strong>week of ${fmt(d.d)}</strong>` +
            (d.legoTotal === 0
              ? '<div class="tt-n">no LEGO posts</div>'
              : `<div class="tt-row"><span class="sw" style="background:${L_PRO}"></span>Pro-regime <b>${d.lego_pro_v2 || 0}</b></div>` +
                `<div class="tt-row"><span class="sw" style="background:${L_ANTI}"></span>Anti-regime <b>${d.lego_anti_v2 || 0}</b></div>` +
                `<div class="tt-row"><span class="sw" style="background:${L_NEITHER}"></span>Neither <b>${d.lego_neither_v2 || 0}</b></div>` +
                `<div class="tt-n">${d.legoTotal} LEGO posts that week</div>`)
          );
      })
      .on('mouseleave', () => { tip.style('opacity', 0); });
  }

  /* Gallery of every post the LEGO classifier flagged. */
  function renderLegoGallery(feed) {
    const container = qs('#lego-gallery');
    if (!container || !feed || !feed.posts) return;
    container.innerHTML = '';
    feed.posts
      .slice()
      .sort((a, b) => a.date.localeCompare(b.date))
      .forEach(p => {
        const card = el('figure', { class: 'lego-card' });
        if (p.poster) {
          card.appendChild(el('img', { src: p.poster, loading: 'lazy', alt: p.what || 'LEGO post' }));
        }
        card.appendChild(el('figcaption', {}, [
          el('span', { class: 'lego-date' }, [p.date]),
          el('span', { class: 'lego-what' }, [p.what || '']),
        ]));
        card.title = p.text || '';
        container.appendChild(card);
      });
  }

  function renderTimeline(data) {
    const container = qs('#timeline-chart');
    if (!container) return;
    const width = Math.min(900, container.clientWidth);
    const height = 260;
    const margin = { top: 40, right: 20, bottom: 46, left: 44 };

    const svg = d3.select(container)
      .append('svg')
      .attr('class', 'timeline-svg')
      .attr('viewBox', `0 0 ${width} ${height}`);

    // Build full date range, filling missing dates as 0
    const parse = d3.timeParse('%Y-%m-%d');
    const byDate = new Map(data.map(d => [d.date, d]));
    const start = parse('2025-12-31');
    const end = parse('2026-04-09');
    const allDates = d3.timeDay.range(start, d3.timeDay.offset(end, 1));
    const full = allDates.map(d => {
      const key = d3.timeFormat('%Y-%m-%d')(d);
      const rec = byDate.get(key);
      return { date: d, count: rec ? rec.count : 0, key };
    });

    const x = d3.scaleTime()
      .domain([start, d3.timeDay.offset(end, 1)])
      .range([margin.left, width - margin.right]);
    const y = d3.scaleLinear()
      .domain([0, d3.max(full, d => d.count) || 1]).nice()
      .range([height - margin.bottom, margin.top]);

    const barW = Math.max(2, (width - margin.left - margin.right) / full.length - 1);

    const warDate = parse('2026-02-28');

    // Gap shading Jan 9 - Jan 22 (collection gap)
    const gapStart = parse('2026-01-09');
    const gapEnd = parse('2026-01-23');
    svg.append('rect')
      .attr('class', 'gap-rect')
      .attr('x', x(gapStart))
      .attr('width', x(gapEnd) - x(gapStart))
      .attr('y', margin.top)
      .attr('height', height - margin.top - margin.bottom);
    svg.append('text')
      .attr('class', 'gap-text')
      .attr('x', (x(gapStart) + x(gapEnd)) / 2)
      .attr('y', margin.top + 14)
      .attr('text-anchor', 'middle')
      .text('Scraping gap');

    // Bars
    svg.append('g')
      .selectAll('rect.bar')
      .data(full)
      .enter()
      .append('rect')
      .attr('class', d => {
        const key = d3.timeFormat('%Y-%m-%d')(d.date);
        return 'bar' + (key === '2026-02-28' ? ' bar-war' : '');
      })
      .attr('x', d => x(d.date))
      .attr('width', barW)
      .attr('y', d => y(d.count))
      .attr('height', d => y(0) - y(d.count))
      .append('title')
      .text(d => `${d3.timeFormat('%b %d, %Y')(d.date)}: ${d.count} posts`);

    // War vertical line
    svg.append('line')
      .attr('class', 'annotation-line')
      .attr('x1', x(warDate) + barW / 2).attr('x2', x(warDate) + barW / 2)
      .attr('y1', margin.top - 12).attr('y2', height - margin.bottom);

    svg.append('text')
      .attr('class', 'annotation-text')
      .attr('x', x(warDate) + barW / 2)
      .attr('y', margin.top - 18)
      .attr('text-anchor', 'middle')
      .text('Feb 28: Tehran struck');

    // Axes
    const xAxis = d3.axisBottom(x)
      .tickFormat(d3.timeFormat('%b %d'))
      .ticks(d3.timeWeek.every(2));
    svg.append('g')
      .attr('class', 'axis x-axis')
      .attr('transform', `translate(0,${height - margin.bottom})`)
      .call(xAxis);

    const yAxis = d3.axisLeft(y).ticks(4);
    svg.append('g')
      .attr('class', 'axis y-axis')
      .attr('transform', `translate(${margin.left},0)`)
      .call(yAxis);

    svg.append('text')
      .attr('x', margin.left - 34)
      .attr('y', margin.top - 16)
      .attr('fill', '#888')
      .attr('font-size', 12)
      .attr('letter-spacing', '0.05em')
      .attr('text-transform', 'uppercase')
      .text('Posts/day');
  }

  /* ============================================================
     FEB 28 LIVE FEED
     ============================================================ */
  function renderLiveFeed(entries) {
    const container = qs('#livefeed-entries');
    if (!container) return;
    entries.forEach(e => {
      const time = formatTime(e.time_est);
      let text = (e.text_en || '').trim();
      if (!text) text = '(no caption)';
      if (text.length > 380) text = text.slice(0, 360).trim() + '…';
      const div = el('div', { className: 'livefeed-entry' }, [
        el('div', { className: 'time' }, time + ' · Feb 28'),
        el('div', { className: 'body' }, text),
      ]);
      container.appendChild(div);
    });
    // IO reveal
    const io = new IntersectionObserver((es) => {
      es.forEach(ent => {
        if (ent.isIntersecting) {
          ent.target.classList.add('visible');
          io.unobserve(ent.target);
        }
      });
    }, { threshold: 0.3 });
    qsa('.livefeed-entry', container).forEach(e => io.observe(e));
  }

  /* ============================================================
     CHAPTERS
     ============================================================ */
  function renderChapter(data, containerId, opts = {}) {
    const c = qs('#' + containerId);
    if (!c || !data) return;
    const grid = el('div', {
      className: 'posts-grid ' + (opts.cols || 'three'),
    });
    (data.posts || []).forEach(p => grid.appendChild(renderPostCard(p)));
    c.appendChild(grid);
  }

  function renderChapter2(data) {
    const beforeC = qs('#ch2-before');
    const afterC = qs('#ch2-after');
    if (!beforeC || !afterC || !data) return;
    const beforeGrid = el('div', { className: 'posts-grid three' });
    (data.posts_before || []).forEach(p => beforeGrid.appendChild(renderPostCard(p)));
    beforeC.appendChild(beforeGrid);
    const afterGrid = el('div', { className: 'posts-grid three' });
    (data.posts_after || []).forEach(p => afterGrid.appendChild(renderPostCard(p)));
    afterC.appendChild(afterGrid);
  }

  /* ============================================================
     MOSAIC (canvas)
     ============================================================ */
  function renderMosaic(tiles) {
    const canvas = qs('#mosaic-canvas');
    const tooltip = qs('#mosaic-tooltip');
    if (!canvas) return;
    const containerW = canvas.parentElement.clientWidth;
    const cols = Math.min(80, Math.max(40, Math.floor(containerW / 14)));
    const tileSize = Math.floor(containerW / cols);
    const rows = Math.ceil(tiles.length / cols);
    const w = cols * tileSize;
    const h = rows * tileSize;
    canvas.width = w * window.devicePixelRatio;
    canvas.height = h * window.devicePixelRatio;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const colorFor = (t) => {
      if (t.d === '2026-02-28') return '#e63946'; // war start
      if (t.m === 'v') return '#457b9d';
      if (t.m === 'i') return '#6b7f99';
      return '#2d3944';
    };

    // pre-sort by date (already is)
    tiles.forEach((t, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      ctx.fillStyle = colorFor(t);
      ctx.fillRect(col * tileSize, row * tileSize, tileSize - 1, tileSize - 1);
    });

    // Legend renderer
    const legend = qs('#mosaic-legend');
    if (legend) {
      legend.innerHTML = '';
      const items = [
        { c: '#457b9d', label: 'Video' },
        { c: '#6b7f99', label: 'Image' },
        { c: '#2d3944', label: 'Text only' },
        { c: '#e63946', label: 'Feb 28 — war begins' },
      ];
      items.forEach(i => {
        const s = el('span', {}, [
          el('span', { className: 'swatch', style: { background: i.c } }),
          document.createTextNode(i.label),
        ]);
        legend.appendChild(s);
      });
    }

    // Hover tooltip
    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const col = Math.floor(x / tileSize);
      const row = Math.floor(y / tileSize);
      const idx = row * cols + col;
      if (idx < 0 || idx >= tiles.length) { tooltip.style.display = 'none'; return; }
      const t = tiles[idx];
      tooltip.innerHTML = '';
      tooltip.appendChild(el('div', { className: 'date' }, niceDate(t.d)));
      tooltip.appendChild(el('div', {}, (t.x || '(no caption)').slice(0, 180)));
      if (t.t) tooltip.appendChild(el('div', { className: 'theme' }, t.t));
      tooltip.style.display = 'block';
      const tw = tooltip.offsetWidth;
      const th = tooltip.offsetHeight;
      let left = e.clientX - rect.left + 14;
      let top = e.clientY - rect.top + 14;
      if (left + tw > rect.width) left = e.clientX - rect.left - tw - 14;
      if (top + th > rect.height) top = e.clientY - rect.top - th - 14;
      tooltip.style.left = left + 'px';
      tooltip.style.top = top + 'px';
    });
    canvas.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
  }

  /* ============================================================
     LEGO HEADLINE: split chars into spans styled as bricks
     ============================================================ */
  function buildLegoHeadline() {
    const h = qs('.lego-headline');
    if (!h) return;
    const text = h.getAttribute('data-lego-text') || h.textContent;
    h.innerHTML = '';
    // Lego color palette — solid, kid-friendly
    const palette = ['#d62828','#264653','#f4a261','#2a9d8f','#e9c46a','#1d3557','#e63946','#457b9d','#fb8500','#2b9348'];
    const words = text.split(' ');
    words.forEach((word, wi) => {
      const wEl = document.createElement('span');
      wEl.className = 'lego-word';
      [...word].forEach((ch, ci) => {
        const b = document.createElement('span');
        b.className = 'lego-brick';
        // pick a color based on position, but make "Lego" stand out yellow
        const lower = word.toLowerCase();
        let color;
        if (lower === 'lego') color = palette[(ci + 4) % palette.length] === '#d62828' ? '#f4a261' : '#f4a261';
        else color = palette[(wi * 7 + ci * 3) % palette.length];
        b.style.setProperty('--lb', color);
        b.textContent = ch;
        wEl.appendChild(b);
      });
      h.appendChild(wEl);
    });
  }

  /* ============================================================
     CAROUSEL
     ============================================================ */
  function setupCarousel(items) {
    const track = qs('#carousel-track');
    const dotsBox = qs('#carousel-dots');
    const prev = qs('.carousel-nav.prev');
    const next = qs('.carousel-nav.next');
    if (!track) return;

    items.forEach((item, i) => {
      const slide = el('div', { className: 'carousel-slide' }, [
        el('div', { className: 'slide-media' }),
        el('div', { className: 'slide-caption' }, [
          el('div', { className: 'slide-date' }, niceDate(item.date)),
          document.createTextNode(item.caption || ''),
        ]),
      ]);
      const mediaBox = slide.querySelector('.slide-media');
      const video = el('video', {
        muted: 'muted', loop: 'loop', playsinline: 'playsinline',
        preload: 'metadata',
        poster: item.poster || '',
        'data-src': mediaURL(item.filename),
      });
      video.muted = true;
      mediaBox.appendChild(video);
      const sound = el('button', {
        className: 'slide-sound',
        'aria-label': 'Toggle sound',
        onclick: (e) => {
          e.stopPropagation();
          video.muted = !video.muted;
          sound.textContent = video.muted ? '🔇' : '🔊';
          if (!video.muted && video.paused) video.play().catch(()=>{});
        },
      }, '🔇');
      mediaBox.appendChild(sound);
      track.appendChild(slide);

      const d = el('button', {
        'aria-label': `Slide ${i + 1}`,
        onclick: () => goTo(i),
      });
      dotsBox.appendChild(d);
    });

    let position = 0;
    function visibleCount() {
      const w = window.innerWidth;
      if (w < 720) return 1;
      if (w < 1024) return 2;
      return 3;
    }
    function maxPos() {
      return Math.max(0, items.length - visibleCount());
    }
    function update() {
      position = Math.max(0, Math.min(position, maxPos()));
      const slideW = track.firstChild ? track.firstChild.getBoundingClientRect().width + 16 : 0;
      track.style.transform = `translateX(${-position * slideW}px)`;
      qsa('button', dotsBox).forEach((d, i) => {
        d.classList.toggle('active', i === position);
      });
      prev.disabled = position === 0;
      next.disabled = position >= maxPos();
    }
    function goTo(i) { position = i; update(); }
    prev.addEventListener('click', () => { position--; update(); });
    next.addEventListener('click', () => { position++; update(); });
    window.addEventListener('resize', update);
    update();

    // Touch swipe
    let startX = null;
    track.addEventListener('touchstart', e => { startX = e.touches[0].clientX; }, { passive: true });
    track.addEventListener('touchend', e => {
      if (startX == null) return;
      const dx = e.changedTouches[0].clientX - startX;
      if (Math.abs(dx) > 40) { position += dx < 0 ? 1 : -1; update(); }
      startX = null;
    });
  }

  /* ============================================================
     CHAPTER TRACKERS (donut + count)
     ============================================================ */
  function renderTrackers(stats) {
    if (!stats || !stats.trackers) return;
    qsa('.chapter-tracker').forEach(box => {
      const key = box.getAttribute('data-tracker');
      const t = stats.trackers[key];
      if (!t) return;
      const pct = t.percent || 0;
      // Donut
      const r = 22, c = 2 * Math.PI * r;
      const dash = (pct / 100) * c;
      box.innerHTML = '';
      const head = el('div', { className: 'tracker-head' });
      // SVG donut
      const ns = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('class', 'tracker-pie');
      svg.setAttribute('viewBox', '0 0 50 50');
      const bg = document.createElementNS(ns, 'circle');
      bg.setAttribute('cx', 25); bg.setAttribute('cy', 25); bg.setAttribute('r', r);
      bg.setAttribute('fill', 'none');
      bg.setAttribute('stroke', 'rgba(127,127,127,0.25)');
      bg.setAttribute('stroke-width', 6);
      svg.appendChild(bg);
      const fg = document.createElementNS(ns, 'circle');
      fg.setAttribute('cx', 25); fg.setAttribute('cy', 25); fg.setAttribute('r', r);
      fg.setAttribute('fill', 'none');
      fg.setAttribute('stroke', 'currentColor');
      fg.setAttribute('stroke-width', 6);
      fg.setAttribute('stroke-dasharray', `${dash} ${c}`);
      fg.setAttribute('stroke-linecap', 'round');
      fg.setAttribute('transform', 'rotate(-90 25 25)');
      fg.style.color = getComputedStyle(box).getPropertyValue('--chapter-color') || '#e63946';
      // Reach the chapter color from the parent
      const parent = box.closest('.chapter');
      if (parent) {
        const cc = getComputedStyle(parent).getPropertyValue('--chapter-color').trim();
        if (cc) fg.style.color = cc;
      }
      svg.appendChild(fg);
      head.appendChild(svg);
      head.appendChild(el('div', { className: 'tracker-num' }, [
        el('span', { className: 'pct' }, pct.toFixed(1) + '%'),
        el('span', { className: 'of' }, t.count.toLocaleString() + ' / ' + stats.total.toLocaleString()),
      ]));
      box.appendChild(head);
      box.appendChild(el('div', { className: 'tracker-label' }, t.label));
      if (t.subitems && t.subitems.length) {
        const sub = el('div', { className: 'tracker-sub' });
        t.subitems.forEach(s => {
          sub.appendChild(el('div', { className: 'row' }, [
            document.createTextNode(s.label),
            el('strong', {}, s.count.toLocaleString()),
          ]));
        });
        box.appendChild(sub);
      }
    });
  }

  /* ============================================================
     REGIME SCATTER (anti vs pro over time)
     ============================================================ */
  function renderRegimeScatter(regime) {
    if (!regime) return;
    const stats = qs('#scatter-stats');
    if (stats) {
      const b = regime.breakdown || {};
      stats.innerHTML = '';
      stats.appendChild(el('div', { className: 'regime-stat anti' }, [
        el('div', { className: 'head' }, 'Anti-regime'),
        el('div', { className: 'big' }, (b.anti_total || 0).toLocaleString() + ' posts'),
        el('div', { className: 'breakdown' }, [
          document.createTextNode('Including '),
          el('b', {}, (b.anti_by?.protests || 0).toString()),
          document.createTextNode(' on protests, '),
          el('b', {}, (b.anti_by?.iranian_economy || 0).toString()),
          document.createTextNode(' on the Iranian economy. Anti-regime voices held the top of the feed through January and most of February.'),
        ]),
      ]));
      stats.appendChild(el('div', { className: 'regime-stat pro' }, [
        el('div', { className: 'head' }, 'Pro-regime'),
        el('div', { className: 'big' }, (b.pro_total || 0).toLocaleString() + ' posts'),
        el('div', { className: 'breakdown' }, [
          document.createTextNode('Including '),
          el('b', {}, (b.pro_by?.war_coverage || 0).toString()),
          document.createTextNode(' tagged war coverage and '),
          el('b', {}, (b.pro_by?.irgc_general || 0).toString()),
          document.createTextNode(' explicitly tagged IRGC. Pro-regime posts intensified after Feb 28 and dominated the feed by mid-March.'),
        ]),
      ]));
    }

    const chart = qs('#scatter-chart');
    const tooltip = qs('#scatter-tooltip');
    if (!chart) return;
    chart.innerHTML = '';
    const containerW = chart.clientWidth || 800;
    const width = containerW;
    const height = 520;
    const margin = { top: 50, right: 24, bottom: 50, left: 24 };

    const all = [...(regime.anti || []), ...(regime.pro || [])];
    if (!all.length) return;

    const parse = d3.timeParse('%Y-%m-%d');
    all.forEach(p => { p._d = parse(p.date); });
    const start = parse('2025-12-31'), end = parse('2026-04-09');
    const x = d3.scaleTime()
      .domain([start, d3.timeDay.offset(end, 1)])
      .range([margin.left, width - margin.right]);

    // Y: anti above 0, pro below 0 — positions stacked with jitter to avoid overlap
    const tileSize = 18;
    function placePoints(arr, side) {
      // group by date
      const byDate = d3.groups(arr, p => p.date);
      const placed = [];
      byDate.forEach(([_d, group]) => {
        group.forEach((p, i) => {
          const stackOffset = (i + 0.5) * (tileSize + 2);
          p._x = x(p._d);
          p._y = side === 'anti'
            ? height / 2 - 10 - stackOffset
            : height / 2 + 10 + stackOffset;
          placed.push(p);
        });
      });
      return placed;
    }
    const antiPts = placePoints(regime.anti || [], 'anti');
    const proPts  = placePoints(regime.pro  || [], 'pro');

    const svg = d3.select(chart).append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`);

    // Centerline divider
    svg.append('line')
      .attr('class', 'divider')
      .attr('x1', margin.left).attr('x2', width - margin.right)
      .attr('y1', height / 2).attr('y2', height / 2);

    // Side labels
    svg.append('text').attr('class', 'side-label anti')
      .attr('x', margin.left).attr('y', margin.top - 24).text('↑ Anti-regime');
    svg.append('text').attr('class', 'side-label pro')
      .attr('x', margin.left).attr('y', height - margin.bottom + 36).text('↓ Pro-regime');

    // War line
    const warX = x(parse('2026-02-28'));
    svg.append('line').attr('class', 'war-line')
      .attr('x1', warX).attr('x2', warX)
      .attr('y1', margin.top - 18).attr('y2', height - margin.bottom + 12);
    svg.append('text').attr('class', 'war-label')
      .attr('x', warX + 6).attr('y', margin.top - 22).text('Feb 28');

    // X axis
    const xAxis = d3.axisBottom(x)
      .ticks(d3.timeMonth.every(1))
      .tickFormat(d3.timeFormat('%b %Y'));
    svg.append('g').attr('class', 'axis')
      .attr('transform', `translate(0,${height - margin.bottom + 4})`)
      .call(xAxis);

    // Tiles
    function drawSide(pts) {
      pts.forEach((p, i) => {
        if (p.thumb) {
          // Use a clipPath via SVG <image> rounded
          const grp = svg.append('g').attr('class', 'scatter-tile')
            .attr('transform', `translate(${p._x - tileSize/2},${p._y - tileSize/2})`);
          grp.append('rect')
            .attr('width', tileSize).attr('height', tileSize)
            .attr('rx', 3).attr('ry', 3)
            .attr('fill', p.side === 'anti' ? '#f4a261' : '#dc2626');
          grp.append('image')
            .attr('href', p.thumb)
            .attr('width', tileSize).attr('height', tileSize)
            .attr('preserveAspectRatio', 'xMidYMid slice');
          grp.append('rect')
            .attr('width', tileSize).attr('height', tileSize)
            .attr('rx', 3).attr('ry', 3)
            .attr('fill', 'none')
            .attr('stroke', p.side === 'anti' ? '#f4a261' : '#dc2626')
            .attr('stroke-width', 1.5);
          grp.on('mouseenter', () => showTip(grp.node(), p))
             .on('mouseleave', hideTip)
             .on('mousemove', e => moveTip(e));
          // Reveal
          setTimeout(() => grp.classed('visible', true), Math.min(2000, i * 18));
        } else {
          const r = svg.append('rect').attr('class', 'scatter-tile')
            .attr('x', p._x - tileSize/2).attr('y', p._y - tileSize/2)
            .attr('width', tileSize).attr('height', tileSize)
            .attr('rx', 3).attr('ry', 3)
            .attr('fill', p.side === 'anti' ? '#f4a261' : '#dc2626');
          r.on('mouseenter', () => showTip(r.node(), p))
           .on('mouseleave', hideTip)
           .on('mousemove', e => moveTip(e));
          setTimeout(() => r.classed('visible', true), Math.min(2000, i * 18));
        }
      });
    }
    drawSide(antiPts);
    drawSide(proPts);

    function showTip(node, p) {
      tooltip.innerHTML = '';
      tooltip.appendChild(el('span', { className: 'label ' + p.side }, p.side === 'anti' ? 'Anti-regime' : 'Pro-regime'));
      tooltip.appendChild(el('div', { className: 'date' }, niceDate(p.date)));
      if (p.text) tooltip.appendChild(el('div', {}, p.text));
      if (p.theme) tooltip.appendChild(el('div', { className: 'date', style: { marginTop: '4px' } }, 'theme: ' + p.theme));
      tooltip.style.display = 'block';
    }
    function hideTip() { tooltip.style.display = 'none'; }
    function moveTip(e) {
      const wrap = chart.parentElement.getBoundingClientRect();
      let lx = e.clientX - wrap.left + 14;
      let ly = e.clientY - wrap.top + 14;
      if (lx + 320 > wrap.width) lx = e.clientX - wrap.left - 320 - 14;
      tooltip.style.left = lx + 'px';
      tooltip.style.top  = ly + 'px';
    }
  }

  /* ============================================================
     BOOT
     ============================================================ */
  async function init() {
    setupHero();
    buildLegoHeadline();

    let posts, timeline, feb28, stats, mosaic, regime, carousel;
    try {
      [posts, timeline, feb28, stats, mosaic, regime, carousel] = await Promise.all([
        loadJSON('data/posts.json'),
        loadJSON('data/timeline.json'),
        loadJSON('data/feb28.json'),
        loadJSON('data/stats.json'),
        loadJSON('data/mosaic.json'),
        loadJSON('data/regime.json'),
        loadJSON('data/carousel.json'),
      ]);
    } catch (e) {
      console.error('Data load failed', e);
      return;
    }

    // Stat card values
    qsa('.stat-card .num').forEach(n => {
      const k = n.getAttribute('data-key');
      if (stats[k] != null) n.setAttribute('data-value', stats[k]);
    });

    if (qs('#timeline-chart')) renderTimeline(timeline);
    renderChapter(posts.ch1_ai, 'ch1-posts', { cols: 'three' });
    renderChapter2(posts.ch2_regime);
    renderLiveFeed(feb28);
    renderChapter(posts.ch3_popculture, 'ch3-posts', { cols: 'three' });
    renderChapter(posts.ch4_intervention, 'ch4-posts', { cols: 'three' });
    renderChapter(posts.ch5_economy, 'ch5-posts', { cols: 'three' });
    renderChapter(posts.ch6_international, 'ch6-posts', { cols: 'three' });

    // Chapter 7 weather grid (two/three col)
    const ch7 = qs('#ch7-grid');
    if (ch7 && posts.ch7_weather) {
      const grid = el('div', { className: 'weather-grid' });
      (posts.ch7_weather.posts || []).forEach(p => grid.appendChild(renderPostCard(p)));
      ch7.appendChild(grid);
    }

    if (qs('#mosaic-canvas')) renderMosaic(mosaic);

    // New: trackers, carousel, regime scatter
    if (qs('.chapter-tracker')) renderTrackers(stats);
    setupCarousel(carousel);
    renderRegimeScatter(regime);

    // Classifier charts (Phase 1 stance, Phase 2 LEGO)
    try {
      const [weekly, lego, timeline] = await Promise.all([
        loadJSON('data/stance_weekly.json'),
        loadJSON('data/lego.json'),
        loadJSON('data/stance_posts.json'),
      ]);
      renderStanceTimeline(timeline);
      setupScrolly();
      renderStanceWeeklyBars(weekly, { target: '#stance-chart' });
      renderLegoStanceBars(weekly, { target: '#lego-chart' });
      renderLegoGallery(lego);
    } catch (err) {
      console.error('classifier charts failed', err);
    }

    setupVideoController();
    if (qs('.stat-card')) setupStatCounters();
    setupProgressBar();

    window.addEventListener('resize', () => {
      if (window.__observeMedia) window.__observeMedia();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

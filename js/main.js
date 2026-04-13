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
      const poster = post.screenshot || null;
      const video = el('video', {
        src: mediaURL(post.filename),
        poster: poster || '',
        muted: 'muted',
        loop: 'loop',
        playsinline: 'playsinline',
        preload: 'none',
        'data-src': mediaURL(post.filename),
      });
      video.muted = true;
      mediaBox.appendChild(video);
      mediaBox.appendChild(el('div', { className: 'video-indicator' }, 'Video'));
      const soundBtn = el('button', {
        className: 'post-sound',
        'aria-label': 'Toggle sound',
        title: 'Toggle sound',
        onclick: (e) => {
          e.stopPropagation();
          video.muted = !video.muted;
          soundBtn.textContent = video.muted ? '🔇' : '🔊';
          if (!video.muted && video.paused) video.play().catch(()=>{});
        }
      }, '🔇');
      mediaBox.appendChild(soundBtn);
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
      .attr('font-size', 10)
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
     BOOT
     ============================================================ */
  async function init() {
    setupHero();

    let posts, timeline, feb28, stats, mosaic;
    try {
      [posts, timeline, feb28, stats, mosaic] = await Promise.all([
        loadJSON('data/posts.json'),
        loadJSON('data/timeline.json'),
        loadJSON('data/feb28.json'),
        loadJSON('data/stats.json'),
        loadJSON('data/mosaic.json'),
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

    renderTimeline(timeline);
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

    renderMosaic(mosaic);

    setupVideoController();
    setupStatCounters();
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

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

    // New: trackers, carousel, regime scatter
    renderTrackers(stats);
    setupCarousel(carousel);
    renderRegimeScatter(regime);

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

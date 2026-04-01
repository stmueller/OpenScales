/**
 * scale-runner.js  —  OpenScales HTML/JS Scale Runner
 * Version: 1.0.0
 *
 * Administers any OSD JSON scale in the browser.
 * Produces CSV output byte-compatible with ScaleRunner.pbl.
 * Dispatches peblTestComplete on completion for peblhub chain integration.
 *
 * Usage:
 *   ScaleRunner.mount(containerElement, {
 *     scale,        // scale code, e.g. "PHQ9"
 *     participant,  // participant ID string
 *     token,        // peblhub token (optional)
 *     language,     // BCP-47 language code (default: "en")
 *     collectURL,   // POST endpoint (optional)
 *     baseURL,      // base URL for fetching split scale JSON files (default: auto)
 *     osdURL,       // URL of a .osd bundle file — single-file alternative to baseURL
 *     params,       // runtime parameter overrides (object)
 *     onComplete,   // callback({status:"completed"}) (optional)
 *   });
 *
 * License: MIT
 */

'use strict';

const ScaleRunner = (() => {

  const VERSION = '1.0.0';

  // ============================================================
  // UTILITIES
  // ============================================================

  /** RFC-4180 CSV field quoting */
  function quoteCSV(val) {
    const s = (val === null || val === undefined) ? '' : String(val);
    if (s.includes('"') || s.includes(',') || s.includes('\n') || s.includes('\r')) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }

  function csvRow(fields) {
    return fields.map(quoteCSV).join(',');
  }

  /** Current Unix timestamp in ms */
  function nowMs() { return Date.now(); }

  /** Shuffle array in-place (Fisher-Yates) */
  function shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  /** Deep clone (JSON-safe) */
  function clone(obj) { return JSON.parse(JSON.stringify(obj)); }

  // ============================================================
  // LOADER
  // ============================================================

  /**
   * Fetch scale definition + translation, return {scaleDef, strings}.
   *
   * Two loading modes:
   *
   * 1. OSD bundle (single file):
   *    config.osdURL points directly to a {CODE}.osd file.
   *    One fetch; definition and all translations are embedded.
   *
   * 2. Split files (default):
   *    Fetches {dir}/{code}.json then {dir}/{code}.{lang}.json.
   *    Falls back from requested language → "en" → empty strings.
   *
   * In both modes, language fall-back order: requested → "en" → {}.
   */
  async function loadScale(code, language, baseURL, osdURL) {
    language = language || 'en';

    // ── Mode 1: .osd bundle ────────────────────────────────────
    if (osdURL) {
      const res = await fetch(osdURL);
      if (!res.ok) throw new Error(`Cannot load OSD bundle "${osdURL}": HTTP ${res.status}`);
      let bundle = await res.json();
      // Flat-format OSD (no "definition" wrapper) — normalise inline
      if (!bundle.definition && bundle.items) {
        bundle = { definition: bundle, translations: bundle.translations || {} };
      }
      if (!bundle.definition) throw new Error(`Invalid .osd file: missing "definition" key`);
      const scaleDef = bundle.definition;
      const allTrans = bundle.translations || {};
      const strings  = allTrans[language] || allTrans['en'] || {};
      return { scaleDef, strings };
    }

    // ── Mode 2: split files ────────────────────────────────────
    baseURL = (baseURL || '').replace(/\/$/, '');
    const dir = baseURL ? `${baseURL}/${code}` : `scales/${code}`;

    const defRes = await fetch(`${dir}/${code}.json`);
    if (!defRes.ok) throw new Error(`Cannot load scale "${code}": HTTP ${defRes.status}`);
    const scaleDef = await defRes.json();

    let strings = {};
    const langs = language === 'en' ? ['en'] : [language, 'en'];
    for (const lang of langs) {
      try {
        const res = await fetch(`${dir}/${code}.${lang}.json`);
        if (res.ok) { strings = await res.json(); break; }
      } catch (_) { /* try next */ }
    }

    return { scaleDef, strings };
  }

  /**
   * Resolve a text key to its display string.
   * Returns the key itself if missing — never throws.
   */
  // resolveText(key, strings, params, responseMap?, aliasMap?, extras?)
  //   S2: {param_name} or {param.name} → params lookup
  //   S3: {answer.id} or {answer.alias} → responseMap lookup (alias via aliasMap)
  //   S7: {score.dim}, {computed.name} → extras.scores / extras.computed lookup
  //   Unrecognised prefixes → literal passthrough
  function resolveText(key, strings, params, responseMap, aliasMap, extras) {
    if (!key) return '';
    let text = strings[key];
    if (text === undefined || text === null) text = key; // literal fallback
    if (typeof text !== 'string') return String(text);
    return text.replace(/\{([^}]+)\}/g, (match, name) => {
      // S3: answer piping
      if (name.startsWith('answer.')) {
        const ref = name.slice(7);
        if (responseMap) {
          if (responseMap[ref] !== undefined) return String(responseMap[ref]);
          // try alias → id lookup
          if (aliasMap && aliasMap[ref] !== undefined) {
            const qid = aliasMap[ref];
            if (responseMap[qid] !== undefined) return String(responseMap[qid]);
          }
        }
        return ''; // unanswered: empty string
      }
      // {param.name} — explicit prefix form
      if (name.startsWith('param.') && params) {
        const pname = name.slice(6);
        return params[pname] !== undefined ? String(params[pname]) : match;
      }
      // {score.*} — dimension score lookup
      if (name.startsWith('score.') && extras && extras.scores) {
        const sKey = name.slice(6);
        const val = extras.scores[sKey];
        return (val !== undefined && val !== null) ? String(Math.round(val * 100) / 100) : match;
      }
      // {computed.*} — computed variable lookup
      if (name.startsWith('computed.') && extras && extras.computed) {
        const cKey = name.slice(9);
        const val = extras.computed[cKey];
        return (val !== undefined && val !== null) ? String(typeof val === 'number' ? Math.round(val * 100) / 100 : val) : match;
      }
      // {loop.*} — not yet implemented
      if (name.startsWith('loop.')) {
        return match;
      }
      // bare name → param lookup (S2 / existing behaviour)
      if (params && params[name] !== undefined) return String(params[name]);
      return match;
    });
  }

  // ============================================================
  // QUESTION LIST BUILDER
  // ============================================================

  /**
   * Apply branching (A1) and section randomization (S4) to produce
   * the final flat ordered array of questions to administer.
   * Mirrors SelectBranchArms + FilterExcludedSections + ShuffleSectionOrder
   * from ScaleRunner.pbl.
   */
  function buildQuestionList(scaleDef, params) {
    params = params || {};
    const rawQuestions = scaleDef.items || scaleDef.questions || [];

    // ── 1. Resolve branch assignments ──────────────────────────
    const branchChoices = {};  // groupId → armId
    const excludedSections = new Set();

    if (scaleDef.branches) {
      // Support both array format [{id, method, arms}] and legacy object format
      const branchList = Array.isArray(scaleDef.branches)
        ? scaleDef.branches
        : Object.entries(scaleDef.branches).map(([id, def]) => ({ id, ...def }));

      for (const branchDef of branchList) {
        const groupId = branchDef.id;
        // Support both 'arms' (current spec) and legacy 'groups' key
        const arms = branchDef.arms || branchDef.groups || [];
        let chosenArm = null;

        if (branchDef.method === 'parameter') {
          // Arm whose id matches the named parameter value
          const pVal = params[branchDef.parameter];
          const matched = arms.find(a => String(a.id) === String(pVal));
          chosenArm = matched ? matched.id : (arms.length ? arms[0].id : null);
        } else {
          // Default: uniform random selection (method 'random', 'balanced', or unset)
          if (arms.length) {
            const totalWeight = arms.reduce((s, a) => s + (a.weight || 1), 0);
            let r = Math.random() * totalWeight;
            for (const a of arms) {
              r -= (a.weight || 1);
              if (r <= 0) { chosenArm = a.id; break; }
            }
            if (!chosenArm) chosenArm = arms[arms.length - 1].id;
          }
        }
        branchChoices[groupId] = chosenArm;

        // Mark sections NOT in the chosen arm as excluded
        const chosenGroup = arms.find(a => a.id === chosenArm);
        const includedSections = new Set(chosenGroup ? (chosenGroup.sections || []) : []);
        for (const a of arms) {
          if (a.id !== chosenArm) {
            for (const secId of (a.sections || [])) {
              if (!includedSections.has(secId)) excludedSections.add(secId);
            }
          }
        }
      }
    }

    // ── 2. Split into sections ──────────────────────────────────
    const sections = [];  // [{marker|null, questions:[]}]
    let currentSection = { marker: null, questions: [] };
    for (const q of rawQuestions) {
      if (q.type === 'section') {
        sections.push(currentSection);
        currentSection = { marker: q, questions: [] };
      } else {
        currentSection.questions.push(q);
      }
    }
    sections.push(currentSection);

    // ── 3. Section-order randomization (S4) ────────────────────
    let sectionOrder = sections.map((_, i) => i);
    if (scaleDef.randomize_sections) {
      const rsConfig = scaleDef.randomize_sections;
      const fixed = new Set(rsConfig.fixed || []);
      // Implicit first section (index 0) is always fixed
      const fixedIndices = new Set([0]);
      const freeIndices   = [];
      for (let i = 1; i < sections.length; i++) {
        const sid = sections[i].marker && sections[i].marker.id;
        if (sid && fixed.has(sid)) fixedIndices.add(i);
        else freeIndices.push(i);
      }
      const shuffledFree = shuffle([...freeIndices]);
      let si = 0;
      sectionOrder = sectionOrder.map((idx) => {
        if (fixedIndices.has(idx)) return idx;
        return shuffledFree[si++];
      });
    }

    // ── 4. Within-section randomization + flatten ───────────────
    const result = [];
    const shuffle_questions = !!params.shuffle_questions;

    for (const sIdx of sectionOrder) {
      const sec = sections[sIdx];
      const marker = sec.marker;
      const secId  = marker && marker.id;

      // Include section marker itself
      if (marker) {
        marker._excluded = secId && excludedSections.has(secId);
        result.push(marker);
      }

      let qs = [...sec.questions];

      // Within-section randomization — shuffle_questions is the master switch.
      // Nothing shuffles when shuffle_questions is false/0.
      if (shuffle_questions) {
        if (marker && marker.randomize) {
          // Section-level randomize: one pool, items pinned by random_group:0 or fixed list.
          const rCfg = marker.randomize;
          if (rCfg.method === 'shuffle') {
            const fixedIds = new Set(rCfg.fixed || []);
            const fixedItems = [], freeItems = [];
            const fixedPositions = [];
            qs.forEach((q, i) => {
              // Pin if random_group===0 OR id is in the explicit fixed list
              const pinned = (q.random_group === 0) || fixedIds.has(q.id);
              if (pinned) { fixedItems.push({ q, i }); fixedPositions.push(i); }
              else freeItems.push(q);
            });
            shuffle(freeItems);
            let fi = 0;
            qs = qs.map((_, i) => {
              const fp = fixedPositions.indexOf(i);
              if (fp >= 0) return fixedItems[fp].q;
              return freeItems[fi++];
            });
          }
        } else {
          // random_group-based shuffle within section
          qs = shuffleByGroup(qs);
        }
      }

      result.push(...qs);
    }

    // Build alias map: alias_name → question_id (for answer piping S3)
    const aliasMap = {};
    for (const q of rawQuestions) {
      if (q.answer_alias) aliasMap[q.answer_alias] = q.id;
    }

    return { questions: result, branchChoices, aliasMap };
  }

  /**
   * Shuffle questions within their random_group boundaries.
   * Group 0 = fixed. Groups 1+ = shuffle independently.
   */
  function shuffleByGroup(questions) {
    // Collect groups
    const groups = {};
    questions.forEach((q, i) => {
      const g = q.random_group !== undefined ? q.random_group : 0;
      if (!groups[g]) groups[g] = [];
      groups[g].push({ q, i });
    });

    // Shuffle each non-zero group
    for (const [g, items] of Object.entries(groups)) {
      if (Number(g) === 0) continue;
      const shuffled = shuffle(items.map(x => x.q));
      items.forEach((item, si) => { item.q = shuffled[si]; });
    }

    // Re-flatten preserving original index positions
    const result = [...questions];
    for (const [g, items] of Object.entries(groups)) {
      if (Number(g) === 0) continue;
      items.forEach(item => { result[item.i] = item.q; });
    }
    return result;
  }

  // ============================================================
  // CONDITION EVALUATOR
  // ============================================================

  /**
   * Exact port of ScaleRunner.pbl's recursive condition evaluator.
   * Operators: equals, not_equals, greater_than, less_than,
   *            in, not_in, is_answered, is_not_answered.
   */
  function evaluateCondition(condition, responseMap, params) {
    if (!condition) return true;

    // Compound: all (AND)
    if (condition.all) {
      return condition.all.every(c => evaluateCondition(c, responseMap, params));
    }
    // Compound: any (OR)
    if (condition.any) {
      return condition.any.some(c => evaluateCondition(c, responseMap, params));
    }

    // Resolve left-hand side — accept both "item" (new) and "question" (legacy)
    let lhsRaw;
    const itemRef = condition.item !== undefined ? condition.item : condition.question;
    if (itemRef !== undefined) {
      lhsRaw = responseMap[itemRef];
    } else if (condition.parameter !== undefined) {
      lhsRaw = (params || {})[condition.parameter];
    } else {
      return true; // unknown condition type — pass through
    }

    const op  = condition.operator;
    const rhsRaw = condition.value;

    // is_answered / is_not_answered — no value needed
    if (op === 'is_answered')     return lhsRaw !== undefined && lhsRaw !== null && lhsRaw !== '';
    if (op === 'is_not_answered') return lhsRaw === undefined || lhsRaw === null || lhsRaw === '';

    const lhsStr = String(lhsRaw !== undefined && lhsRaw !== null ? lhsRaw : '');
    const rhsStr = String(rhsRaw !== undefined && rhsRaw !== null ? rhsRaw : '');

    switch (op) {
      case 'equals':     return lhsStr === rhsStr;
      case 'not_equals': return lhsStr !== rhsStr;
      case 'greater_than': return parseFloat(lhsStr) > parseFloat(rhsStr);
      case 'less_than':    return parseFloat(lhsStr) < parseFloat(rhsStr);
      case 'in':    return Array.isArray(rhsRaw)
        ? rhsRaw.map(String).includes(lhsStr)
        : String(rhsRaw).split(',').map(s => s.trim()).includes(lhsStr);
      case 'not_in': return Array.isArray(rhsRaw)
        ? !rhsRaw.map(String).includes(lhsStr)
        : !String(rhsRaw).split(',').map(s => s.trim()).includes(lhsStr);
      default: return true;
    }
  }

  /**
   * Check if a question should be shown given current state.
   * Checks (in order): section exclusion → dimension visible_when → question visible_when.
   */
  function shouldShow(qdef, state, scaleDef) {
    // Section-excluded questions are always hidden
    if (state.sectionExcluded) return false;

    // Dimension-level visible_when
    if (qdef.dimension) {
      const dimDef = (scaleDef.dimensions || []).find(d => d.id === qdef.dimension);
      if (dimDef) {
        // enabled_param check
        if (dimDef.enabled_param !== undefined && dimDef.enabled_param !== null) {
          const enabled = state.params[dimDef.enabled_param];
          if (enabled !== undefined && !enabled && enabled !== 1 && enabled !== '1') return false;
        }
        // selectable + default_enabled
        if (dimDef.selectable && dimDef.default_enabled === false) {
          const paramKey = dimDef.enabled_param || `enable_${dimDef.id}`;
          if (!state.params[paramKey]) return false;
        }
        // dimension-level visible_when
        if (dimDef.visible_when) {
          if (!evaluateCondition(dimDef.visible_when, state.responseMap, state.params)) return false;
        }
      }
    }

    // Question-level visible_when
    if (qdef.visible_when) {
      return evaluateCondition(qdef.visible_when, state.responseMap, state.params);
    }

    return true;
  }

  /**
   * Get [min, max] numeric range for a question's response.
   * Cascade: question-level → likert_options → type defaults.
   */
  function getQuestionRange(qdef, scaleDef) {
    if (qdef.type === 'likert') {
      const qMin = qdef.likert_min;
      const qMax = qdef.likert_max;
      const sMin = scaleDef.likert_options && scaleDef.likert_options.min;
      const sMax = scaleDef.likert_options && scaleDef.likert_options.max;
      const pts  = qdef.likert_points ||
        (scaleDef.likert_options && scaleDef.likert_options.points) || 5;
      const min = qMin !== undefined ? qMin : (sMin !== undefined ? sMin : 1);
      const max = qMax !== undefined ? qMax : (sMax !== undefined ? sMax : pts);
      return [min, max];
    }
    if (qdef.type === 'vas') {
      return [qdef.min !== undefined ? qdef.min : 0,
              qdef.max !== undefined ? qdef.max : 100];
    }
    if (qdef.type === 'binary') return [0, 1];
    if (qdef.type === 'grid') {
      const rawCols = qdef.columns || [];
      if (rawCols.length === 0) return [null, null];
      // Check if columns have explicit values
      const hasValues = rawCols.some(c => typeof c === 'object' && c !== null && c.value !== undefined);
      if (hasValues) {
        const vals = rawCols.map(c => typeof c === 'object' ? (c.value || 0) : 0);
        return [Math.min(...vals), Math.max(...vals)];
      }
      return [1, rawCols.length];
    }
    return [null, null];
  }

  // ============================================================
  // VALIDATION
  // ============================================================

  /**
   * Validate a response against question constraints.
   * Returns {valid: bool, error: string|null}.
   */
  function validateResponse(qdef, response, strings, params) {
    strings = strings || {};
    params  = params  || {};
    const v = qdef.validation || {};

    // Required check
    const isRequired = isQuestionRequired(qdef);
    const isEmpty = response === null || response === undefined || response === '';
    if (isRequired && isEmpty && qdef.type !== 'multicheck') {
      return { valid: false, error: 'This question requires an answer.' };
    }

    // Type-specific validation
    if (qdef.type === 'short' || qdef.type === 'long') {
      const s = String(response || '');

      if (v.min_length !== undefined && s.length < v.min_length) {
        return { valid: false, error: v.min_length_error
          ? resolveText(v.min_length_error, strings, params)
          : `Please enter at least ${v.min_length} characters.` };
      }
      if (v.max_length !== undefined && s.length > v.max_length) {
        return { valid: false, error: v.max_length_error
          ? resolveText(v.max_length_error, strings, params)
          : `Please enter at most ${v.max_length} characters.` };
      }

      const words = s.trim() === '' ? 0 : s.trim().split(/\s+/).length;
      if (v.min_words !== undefined && words < v.min_words) {
        return { valid: false, error: v.min_words_error
          ? resolveText(v.min_words_error, strings, params)
          : `Please enter at least ${v.min_words} words.` };
      }
      if (v.max_words !== undefined && words > v.max_words) {
        return { valid: false, error: v.max_words_error
          ? resolveText(v.max_words_error, strings, params)
          : `Please enter at most ${v.max_words} words.` };
      }

      // Numeric validation: supports both validation.type="number" with min/max (OSD format)
      // and legacy validation.number_min/number_max
      const isNumericValidation = v.type === 'number' || v.number_min !== undefined || v.number_max !== undefined;
      if (!isEmpty && isNumericValidation) {
        const n = parseFloat(s);
        const numMin = v.min !== undefined ? v.min : v.number_min;
        const numMax = v.max !== undefined ? v.max : v.number_max;
        const minErr = v.min_error !== undefined ? v.min_error : v.number_min_error;
        const maxErr = v.max_error !== undefined ? v.max_error : v.number_max_error;
        if (isNaN(n)) {
          return { valid: false, error: 'Please enter a valid number.' };
        }
        if (numMin !== undefined && n < numMin) {
          return { valid: false, error: minErr
            ? resolveText(minErr, strings, params)
            : `Please enter a value of ${numMin} or more.` };
        }
        if (numMax !== undefined && n > numMax) {
          return { valid: false, error: maxErr
            ? resolveText(maxErr, strings, params)
            : `Please enter a value of ${numMax} or less.` };
        }
      }

      if (!isEmpty && v.pattern) {
        try {
          const re = new RegExp(v.pattern);
          if (!re.test(s)) {
            return { valid: false, error: v.pattern_error
              ? resolveText(v.pattern_error, strings, params)
              : 'Invalid format.' };
          }
        } catch (_) { /* invalid regex — skip */ }
      }
    }

    if (qdef.type === 'multicheck') {
      const selected = Array.isArray(response) ? response.length : 0;
      // min_selected / max_selected may be at question level or inside validation
      const minSel = qdef.min_selected !== undefined ? qdef.min_selected
                   : v.min_selected   !== undefined ? v.min_selected
                   : (isRequired ? 1 : 0);
      const maxSel = qdef.max_selected !== undefined ? qdef.max_selected : v.max_selected;
      if (selected < minSel) {
        return { valid: false, error: v.min_selected_error
          ? resolveText(v.min_selected_error, strings, params)
          : `Please select at least ${minSel} option(s).` };
      }
      if (maxSel !== undefined && selected > maxSel) {
        return { valid: false, error: v.max_selected_error
          ? resolveText(v.max_selected_error, strings, params)
          : `Please select at most ${maxSel} option(s).` };
      }
    }

    return { valid: true, error: null };
  }

  /** Type-based required defaults */
  function isQuestionRequired(qdef, scaleDef) {
    if (qdef.required !== undefined) return !!qdef.required;
    if (scaleDef && scaleDef.default_required !== undefined) return !!scaleDef.default_required;
    const requiredTypes = ['likert', 'vas', 'multi', 'grid', 'multicheck', 'imageresponse'];
    return requiredTypes.includes(qdef.type);
  }

  // ============================================================
  // MEDIA EMBEDDING  (C4a)
  // ============================================================

  /**
   * Parse the first <img> tag out of an HTML-lite text string.
   * Returns { before, src, width, align, alt, after } or null if no img found.
   * Supports self-closing <img .../> and open <img ...>.
   */
  function extractMedia(text) {
    if (!text || text.indexOf('<img') === -1) return null;
    const re = /<img\s([^>]*?)(?:\s*\/?>)/i;
    const m  = re.exec(text);
    if (!m) return null;

    const attrStr = m[1];
    const before  = text.slice(0, m.index);
    const after   = text.slice(m.index + m[0].length);

    function attr(name) {
      const a = new RegExp(name + '\\s*=\\s*["\']([^"\']*)["\']', 'i').exec(attrStr);
      return a ? a[1] : null;
    }

    return {
      before,
      after,
      src:    attr('src')    || '',
      width:  attr('width')  || '100%',
      align:  attr('align')  || 'center',
      alt:    attr('alt')    || '',
      remote: attr('remote') === 'true',
    };
  }

  /**
   * Build a DOM fragment for item text, splitting on <img> if present.
   * Returns a <div> containing: [text-above] [img?] [text-below].
   *
   * Remote media policy (C4a): remote URLs are blocked for images unless
   * the tag carries remote="true" or params.allow_remote_media is truthy.
   */
  function buildItemTextEl(rawText, baseURL, params) {
    const wrap = document.createElement('div');
    wrap.className = 'sr-item-text-wrap';

    const media = extractMedia(rawText);
    if (!media) {
      wrap.innerHTML = rawText;
      return wrap;
    }

    if (media.before.trim()) {
      const above = document.createElement('div');
      above.className = 'sr-item-text-above';
      above.innerHTML = media.before;
      wrap.appendChild(above);
    }

    if (media.src) {
      const isRemoteURL = /^https?:\/\//i.test(media.src);
      const remoteAllowed = media.remote || (params && params.allow_remote_media);

      if (isRemoteURL && !remoteAllowed) {
        // Block remote image — show placeholder and warn
        console.warn(
          '[ScaleRunner] Remote image blocked (add remote="true" to <img> or set ' +
          'allow_remote_media parameter): ' + media.src
        );
        const placeholder = document.createElement('div');
        placeholder.className = 'sr-media-placeholder';
        placeholder.textContent = '[image not loaded — remote media not permitted]';
        wrap.appendChild(placeholder);
      } else {
        const imgWrap = document.createElement('div');
        imgWrap.className = 'sr-media-wrap sr-media-align-' + media.align;
        const img = document.createElement('img');
        // Resolve src relative to baseURL if not an absolute URL
        img.src = isRemoteURL
          ? media.src
          : (baseURL ? baseURL + '/' : '') + media.src;
        img.alt = media.alt;
        img.style.width    = /^\d+$/.test(media.width) ? media.width + 'px' : media.width;
        img.style.maxWidth = '100%';
        img.style.height   = 'auto';
        img.className = 'sr-media-img';
        imgWrap.appendChild(img);
        wrap.appendChild(imgWrap);
      }
    }

    if (media.after.trim()) {
      const below = document.createElement('div');
      below.className = 'sr-item-text-below';
      below.innerHTML = media.after;
      wrap.appendChild(below);
    }

    return wrap;
  }

  // ============================================================
  // RENDERER
  // ============================================================

  /**
   * Render a question definition into a DOM element.
   * Returns the container element.
   */
  function renderQuestion(qdef, strings, scaleDef, state, onResponse, prevResponse) {
    const wrap = document.createElement('div');
    wrap.className = 'sr-question-body';

    switch (qdef.type) {
      case 'inst':
      case 'image':
        renderInst(qdef, strings, scaleDef, state, wrap, onResponse);
        break;
      case 'likert':
        renderLikert(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse);
        break;
      case 'multi':
        renderMulti(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse);
        break;
      case 'multicheck':
        renderMulticheck(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse);
        break;
      case 'short':
        renderShort(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse);
        break;
      case 'long':
        renderLong(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse);
        break;
      case 'vas':
        renderVAS(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse);
        break;
      case 'grid':
        renderGrid(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse);
        break;
      case 'imageresponse':
        renderImageresponse(qdef, strings, scaleDef, state, wrap, onResponse);
        break;
      default:
        // Unknown type — show as instruction
        renderInst(qdef, strings, scaleDef, state, wrap, onResponse);
    }

    return wrap;
  }

  function renderInst(qdef, strings, scaleDef, state, wrap, onResponse) {
    if (qdef.type === 'image' || qdef.image_file) {
      const img = document.createElement('img');
      img.src   = qdef.image_file || '';
      img.alt   = resolveText(qdef.text_key, strings, state.params, state.responseMap, state.aliasMap);
      img.className = 'sr-image';
      wrap.appendChild(img);
    }
    // inst: no response needed — signal immediately so Next appears
    setTimeout(() => onResponse(null, true), 0);
  }

  function renderLikert(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse) {
    const opts    = scaleDef.likert_options || {};
    const pts     = qdef.likert_points || opts.points || 5;
    const [min]   = getQuestionRange(qdef, scaleDef);
    const labels  = qdef.likert_labels || opts.labels || [];
    const reverse = qdef.likert_reverse || false;

    const row = document.createElement('div');
    row.className = 'sr-likert-row';
    if (pts >= 8) row.classList.add('sr-likert-row--compact');

    for (let i = 0; i < pts; i++) {
      // When reversed, display max value on the left down to min on the right
      const val   = reverse ? (min + pts - 1 - i) : (min + i);
      const btn   = document.createElement('button');
      btn.type    = 'button';
      btn.className = 'sr-likert-btn';
      btn.setAttribute('aria-pressed', 'false');

      const labelEl = document.createElement('span');
      labelEl.className = 'sr-likert-label';
      const lKey = labels[val - min];  // always index by value, regardless of display order
      if (lKey) {
        labelEl.innerHTML = resolveText(lKey, strings, state.params, state.responseMap, state.aliasMap);
        btn.classList.add('sr-likert-has-label');
      } else {
        labelEl.textContent = String(val);
      }

      const numEl = document.createElement('span');
      numEl.className = 'sr-likert-num';
      numEl.textContent = String(val);

      btn.appendChild(numEl);
      btn.appendChild(labelEl);

      // Pre-select if this was the previously recorded response
      if (prevResponse !== undefined && String(val) === String(prevResponse)) {
        btn.classList.add('sr-selected');
        btn.setAttribute('aria-pressed', 'true');
      }

      btn.addEventListener('click', () => {
        row.querySelectorAll('.sr-likert-btn').forEach(b => {
          b.classList.remove('sr-selected');
          b.setAttribute('aria-pressed', 'false');
        });
        btn.classList.add('sr-selected');
        btn.setAttribute('aria-pressed', 'true');
        onResponse(String(val), true);
      });

      row.appendChild(btn);
    }

    wrap.appendChild(row);

    // If pre-filled, restore response state without triggering auto-advance
    if (prevResponse !== undefined) {
      setTimeout(() => onResponse(String(prevResponse), true, true), 0);
    }
  }

  function renderMulti(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse) {
    const options = qdef.options || [];
    const list = document.createElement('ol');
    list.className = 'sr-option-list';

    options.forEach((opt, idx) => {
      // Options may be plain translation-key strings (OSD format) or objects with text_key/label+value
      const textKey = typeof opt === 'string' ? opt : (opt.text_key || opt.label);
      const value   = typeof opt === 'string' ? opt : (opt.value !== undefined ? String(opt.value) : String(idx + 1));

      const li   = document.createElement('li');
      const btn  = document.createElement('button');
      btn.type   = 'button';
      btn.className = 'sr-option-btn';
      btn.innerHTML = resolveText(textKey, strings, state.params, state.responseMap, state.aliasMap);
      btn.setAttribute('aria-pressed', 'false');

      // Pre-select if this was the previously recorded response
      if (prevResponse !== undefined && String(value) === String(prevResponse)) {
        btn.classList.add('sr-selected');
        btn.setAttribute('aria-pressed', 'true');
      }

      btn.addEventListener('click', () => {
        list.querySelectorAll('.sr-option-btn').forEach(b => {
          b.classList.remove('sr-selected');
          b.setAttribute('aria-pressed', 'false');
        });
        btn.classList.add('sr-selected');
        btn.setAttribute('aria-pressed', 'true');
        onResponse(value, true);
      });

      li.appendChild(btn);
      list.appendChild(li);
    });

    wrap.appendChild(list);

    // If pre-filled, restore response state without triggering auto-advance
    if (prevResponse !== undefined) {
      setTimeout(() => onResponse(String(prevResponse), true, true), 0);
    }
  }

  function renderMulticheck(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse) {
    const options  = qdef.options || [];
    const v        = qdef.validation || {};
    // min_selected / max_selected may appear at question level or inside validation
    const minSel   = qdef.min_selected !== undefined ? qdef.min_selected : (v.min_selected !== undefined ? v.min_selected : 1);
    const maxSel   = qdef.max_selected !== undefined ? qdef.max_selected : (v.max_selected !== undefined ? v.max_selected : Infinity);
    // Pre-fill: prevResponse is comma-separated values
    const prevSet  = prevResponse ? new Set(String(prevResponse).split(',').map(s => s.trim())) : new Set();
    const selected = new Set(prevSet);

    const list = document.createElement('ul');
    list.className = 'sr-option-list sr-multicheck-list';

    options.forEach((opt, idx) => {
      // Options may be plain translation-key strings (OSD format) or objects with text_key/label+value
      const textKey = typeof opt === 'string' ? opt : (opt.text_key || opt.label);
      const value   = typeof opt === 'string' ? opt : (opt.value !== undefined ? String(opt.value) : String(idx + 1));

      const li  = document.createElement('li');
      const lbl = document.createElement('label');
      lbl.className = 'sr-multicheck-label';

      const cb  = document.createElement('input');
      cb.type   = 'checkbox';
      cb.className = 'sr-checkbox';
      cb.value  = value;
      cb.checked = prevSet.has(value);

      const span = document.createElement('span');
      span.innerHTML = resolveText(textKey, strings, state.params, state.responseMap, state.aliasMap);

      cb.addEventListener('change', () => {
        if (cb.checked) {
          if (selected.size >= maxSel) { cb.checked = false; return; }
          selected.add(value);
        } else {
          selected.delete(value);
        }
        const arr = [...selected];
        onResponse(arr.length > 0 ? arr : [], selected.size >= minSel);
      });

      lbl.appendChild(cb);
      lbl.appendChild(span);
      li.appendChild(lbl);
      list.appendChild(li);
    });

    wrap.appendChild(list);

    // If pre-filled, signal the existing selection
    if (prevSet.size > 0) {
      setTimeout(() => onResponse([...prevSet], prevSet.size >= minSel), 0);
    }
  }

  function renderShort(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse) {
    const v  = qdef.validation || {};
    const input = document.createElement('input');
    input.type  = 'text';
    input.className = 'sr-text-input';
    if (qdef.maxlength || v.max_length) {
      input.maxLength = qdef.maxlength || v.max_length;
    }
    if (v.type === 'number' || v.number_min !== undefined || v.number_max !== undefined) {
      input.inputMode = 'numeric';
    }
    input.placeholder = '';
    input.setAttribute('autocomplete', 'off');
    if (prevResponse !== undefined) {
      input.value = String(prevResponse);
      setTimeout(() => onResponse(input.value, input.value.trim().length > 0), 0);
    }

    input.addEventListener('input', () => {
      onResponse(input.value, input.value.trim().length > 0);
    });

    wrap.appendChild(input);
  }

  function renderLong(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse) {
    const v  = qdef.validation || {};
    const ta = document.createElement('textarea');
    ta.className = 'sr-textarea';
    if (qdef.rows) ta.rows = qdef.rows;
    else           ta.rows = 6;
    if (qdef.cols) ta.cols = qdef.cols;
    if (qdef.maxlength || v.max_length) ta.maxLength = qdef.maxlength || v.max_length;
    if (prevResponse !== undefined) {
      ta.value = String(prevResponse);
      setTimeout(() => onResponse(ta.value, ta.value.trim().length > 0), 0);
    }

    ta.addEventListener('input', () => {
      onResponse(ta.value, ta.value.trim().length > 0);
    });

    wrap.appendChild(ta);
  }

  function renderVAS(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse) {
    const [min, max] = getQuestionRange(qdef, scaleDef);
    const midVal = Math.round((min + max) / 2);
    const vertical = qdef.orientation === 'vertical';
    const namedAnchors = qdef.anchors || null;

    const container = document.createElement('div');
    container.className = 'sr-vas-container';
    if (vertical) container.classList.add('sr-vas-vertical');

    const slider = document.createElement('input');
    slider.type  = 'range';
    slider.className = 'sr-vas-slider';
    slider.min   = String(min);
    slider.max   = String(max);
    slider.value = prevResponse !== undefined ? String(prevResponse) : String(midVal);
    slider.setAttribute('aria-label', resolveText(qdef.text_key, strings, state.params, state.responseMap, state.aliasMap));
    if (vertical) {
      slider.setAttribute('orient', 'vertical');   // Firefox
      slider.classList.add('sr-vas-slider-vertical');
    }

    // Hide thumb until first interaction (untouched state)
    let touched = prevResponse !== undefined;
    if (!touched) {
      slider.classList.add('sr-vas-untouched');
    } else {
      setTimeout(() => onResponse(slider.value, true), 0);
    }
    slider.addEventListener('input', () => {
      touched = true;
      slider.classList.remove('sr-vas-untouched');
      onResponse(slider.value, true);
    });
    slider.addEventListener('change', () => {
      if (touched) onResponse(slider.value, true);
    });

    if (namedAnchors && namedAnchors.length > 0) {
      // Named anchors — positioned labels along the slider
      const anchorBar = document.createElement('div');
      anchorBar.className = 'sr-vas-anchor-bar';

      // thumbRadius must match CSS thumb width / 2 (28px / 2 = 14px)
      const thumbR = 14;
      for (const anchor of namedAnchors) {
        const frac = (anchor.value - min) / (max - min);
        const el = document.createElement('span');
        el.className = 'sr-vas-anchor-point';
        el.style.left = `calc(${thumbR}px + ${frac} * (100% - ${thumbR * 2}px))`;
        el.style.cursor = 'pointer';
        el.innerHTML = resolveText(anchor.label, strings, state.params, state.responseMap, state.aliasMap);
        el.addEventListener('click', () => {
          slider.value = String(anchor.value);
          touched = true;
          slider.classList.remove('sr-vas-untouched');
          onResponse(slider.value, true);
        });
        anchorBar.appendChild(el);
      }

      // Add tick marks aligned with anchors
      const tickBar = document.createElement('div');
      tickBar.className = 'sr-vas-tick-bar';
      for (const anchor of namedAnchors) {
        const frac = (anchor.value - min) / (max - min);
        const tick = document.createElement('span');
        tick.className = 'sr-vas-tick';
        tick.style.left = `calc(${thumbR}px + ${frac} * (100% - ${thumbR * 2}px))`;
        tickBar.appendChild(tick);
      }

      container.appendChild(anchorBar);
      container.appendChild(slider);
      container.appendChild(tickBar);
    } else {
      // Legacy: simple low/high endpoint labels
      const anchorsDiv = document.createElement('div');
      anchorsDiv.className = 'sr-vas-anchors';

      const lowEl = document.createElement('span');
      lowEl.className = 'sr-vas-anchor-low';
      if (qdef.min_label) lowEl.innerHTML = resolveText(qdef.min_label, strings, state.params, state.responseMap, state.aliasMap);

      const highEl = document.createElement('span');
      highEl.className = 'sr-vas-anchor-high';
      if (qdef.max_label) highEl.innerHTML = resolveText(qdef.max_label, strings, state.params, state.responseMap, state.aliasMap);

      anchorsDiv.appendChild(lowEl);
      anchorsDiv.appendChild(highEl);
      container.appendChild(anchorsDiv);
      container.appendChild(slider);
    }

    wrap.appendChild(container);
  }

  function renderGrid(qdef, strings, scaleDef, state, wrap, onResponse, prevResponse) {
    const rows         = qdef.rows    || [];
    const rawCols      = qdef.columns || [];
    const optionalRows = new Set(qdef.optional_rows || []);

    // Normalize columns: support both plain strings and {text_key, value} objects
    const cols = rawCols.map((col, ci) => {
      if (typeof col === 'object' && col !== null) {
        return { textKey: col.text_key || col.label_key || '', value: col.value !== undefined ? col.value : ci + 1 };
      }
      return { textKey: col, value: ci + 1 };
    });

    // Pre-fill: prevResponse is space-separated per-row values
    const prevVals = prevResponse ? String(prevResponse).split(' ') : [];
    const responses = {};  // rowIndex → value string
    prevVals.forEach((v, ri) => { if (v) responses[ri] = v; });

    const tableWrap = document.createElement('div');
    tableWrap.className = 'sr-grid-wrap';

    const table = document.createElement('table');
    table.className = 'sr-grid';
    table.setAttribute('role', 'grid');

    // Header row
    const thead = document.createElement('thead');
    const hRow  = document.createElement('tr');
    // Empty top-left cell
    const th0   = document.createElement('th');
    th0.className = 'sr-grid-corner';
    hRow.appendChild(th0);
    cols.forEach(col => {
      const th = document.createElement('th');
      th.innerHTML = resolveText(col.textKey, strings, state.params, state.responseMap, state.aliasMap);
      th.className = 'sr-grid-col-head';
      hRow.appendChild(th);
    });
    thead.appendChild(hRow);
    table.appendChild(thead);

    // Body rows
    const tbody = document.createElement('tbody');
    rows.forEach((rowKey, ri) => {
      const isOptional = optionalRows.has(rowKey);
      const tr = document.createElement('tr');
      tr.className = ri % 2 === 0 ? 'sr-grid-row-even' : 'sr-grid-row-odd';
      if (isOptional) tr.classList.add('sr-grid-row-optional');

      const tdLabel = document.createElement('td');
      tdLabel.className = 'sr-grid-row-label';
      tdLabel.innerHTML = resolveText(rowKey, strings, state.params, state.responseMap, state.aliasMap);
      if (isOptional) {
        const optTag = document.createElement('span');
        optTag.className = 'sr-optional-tag';
        optTag.textContent = strings['optional_label'] || '(optional)';
        tdLabel.appendChild(optTag);
      }
      tr.appendChild(tdLabel);

      cols.forEach((col, ci) => {
        const td  = document.createElement('td');
        td.className = 'sr-grid-cell';
        const rb  = document.createElement('input');
        rb.type   = 'radio';
        rb.name   = `${qdef.id}_row${ri}`;
        rb.value  = String(col.value);
        rb.className = 'sr-grid-radio';
        rb.setAttribute('aria-label',
          `${resolveText(rowKey, strings, state.params, state.responseMap, state.aliasMap)}: ${resolveText(col.textKey, strings, state.params, state.responseMap, state.aliasMap)}`);

        // Pre-select if this col's value matches the previously recorded response for this row
        if (prevVals[ri] && prevVals[ri] === String(col.value)) {
          rb.checked = true;
        }

        rb.addEventListener('change', () => {
          if (rb.checked) {
            responses[ri] = String(col.value);
            const allAnswered = rows.every((rk, i) => optionalRows.has(rk) || responses[i] !== undefined);
            const responseStr = rows.map((_, i) => responses[i] || '').join(' ');
            onResponse(responseStr, allAnswered);
          }
        });

        td.appendChild(rb);
        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);

    // If pre-filled, signal current state
    if (Object.keys(responses).length > 0) {
      setTimeout(() => {
        const allAnswered = rows.every((_, i) => responses[i] !== undefined);
        const responseStr = rows.map((_, i) => responses[i] || '').join(' ');
        onResponse(responseStr, allAnswered);
      }, 0);
    }
  }

  function renderImageresponse(qdef, strings, scaleDef, state, wrap, onResponse) {
    if (qdef.image_file) {
      const img = document.createElement('img');
      img.src   = qdef.image_file;
      img.alt   = resolveText(qdef.text_key, strings, state.params, state.responseMap, state.aliasMap);
      img.className = 'sr-image';
      wrap.appendChild(img);
    }
    // Text response area
    const input = document.createElement('input');
    input.type  = 'text';
    input.className = 'sr-text-input';
    input.setAttribute('autocomplete', 'off');
    input.addEventListener('input', () => { onResponse(input.value, false); });
    wrap.appendChild(input);
  }

  // ============================================================
  // EXPRESSION EVALUATOR (S7 / Expression Language)
  // ============================================================

  /**
   * Tokenize an expression string into an array of tokens.
   * Tokens: number, string, identifier (answer.x, score.x, computed.x, parameter.x),
   *         operator (+, -, *, /, >=, <=, >, <, ==, !=), paren, comma, keyword (and, or, not, in, not_in).
   */
  function tokenizeExpr(expr) {
    const tokens = [];
    let i = 0;
    while (i < expr.length) {
      const ch = expr[i];
      // Whitespace
      if (/\s/.test(ch)) { i++; continue; }
      // Number (including decimals)
      if (/[0-9]/.test(ch) || (ch === '.' && i + 1 < expr.length && /[0-9]/.test(expr[i + 1]))) {
        let num = '';
        while (i < expr.length && /[0-9.]/.test(expr[i])) { num += expr[i]; i++; }
        tokens.push({ type: 'num', value: parseFloat(num) });
        continue;
      }
      // Two-char operators
      if (i + 1 < expr.length) {
        const two = expr[i] + expr[i + 1];
        if (['>=', '<=', '==', '!='].includes(two)) {
          tokens.push({ type: 'op', value: two });
          i += 2;
          continue;
        }
      }
      // Single-char operators and parens
      if ('+-*/><'.includes(ch)) {
        tokens.push({ type: 'op', value: ch });
        i++;
        continue;
      }
      if (ch === '(' || ch === ')') {
        tokens.push({ type: ch });
        i++;
        continue;
      }
      if (ch === ',') {
        tokens.push({ type: ',' });
        i++;
        continue;
      }
      // Identifiers and keywords (a-z, A-Z, _, 0-9, .)
      if (/[a-zA-Z_]/.test(ch)) {
        let id = '';
        while (i < expr.length && /[a-zA-Z0-9_.]/.test(expr[i])) { id += expr[i]; i++; }
        // Keywords
        if (id === 'and' || id === 'or' || id === 'not' || id === 'true' || id === 'false'
            || id === 'in' || id === 'not_in') {
          if (id === 'true')  { tokens.push({ type: 'num', value: 1 }); continue; }
          if (id === 'false') { tokens.push({ type: 'num', value: 0 }); continue; }
          tokens.push({ type: 'kw', value: id });
          continue;
        }
        // Built-in functions
        if (['count', 'sum', 'abs', 'min', 'max'].includes(id)) {
          tokens.push({ type: 'fn', value: id });
          continue;
        }
        // Dotted identifier (answer.x, score.x, computed.x, parameter.x)
        tokens.push({ type: 'id', value: id });
        continue;
      }
      // Skip unknown characters
      i++;
    }
    return tokens;
  }

  /**
   * Parse and evaluate a tokenized expression.
   * Recursive descent parser with standard precedence:
   *   or < and < not < comparison < add/sub < mul/div < unary < atom
   *
   * context: { answer: {}, score: {}, computed: {}, parameter: {} }
   */
  function evalExpr(tokens, pos, context) {
    return parseOr(tokens, pos, context);
  }

  function parseOr(tokens, pos, ctx) {
    let [left, p] = parseAnd(tokens, pos, ctx);
    while (p < tokens.length && tokens[p].type === 'kw' && tokens[p].value === 'or') {
      p++;
      const [right, p2] = parseAnd(tokens, p, ctx);
      left = (left || right) ? 1 : 0;
      p = p2;
    }
    return [left, p];
  }

  function parseAnd(tokens, pos, ctx) {
    let [left, p] = parseNot(tokens, pos, ctx);
    while (p < tokens.length && tokens[p].type === 'kw' && tokens[p].value === 'and') {
      p++;
      const [right, p2] = parseNot(tokens, p, ctx);
      left = (left && right) ? 1 : 0;
      p = p2;
    }
    return [left, p];
  }

  function parseNot(tokens, pos, ctx) {
    if (pos < tokens.length && tokens[pos].type === 'kw' && tokens[pos].value === 'not') {
      const [val, p] = parseNot(tokens, pos + 1, ctx);
      return [val ? 0 : 1, p];
    }
    return parseComparison(tokens, pos, ctx);
  }

  function parseComparison(tokens, pos, ctx) {
    let [left, p] = parseAddSub(tokens, pos, ctx);
    if (p < tokens.length && tokens[p].type === 'op'
        && ['>', '<', '>=', '<=', '==', '!='].includes(tokens[p].value)) {
      const op = tokens[p].value;
      const [right, p2] = parseAddSub(tokens, p + 1, ctx);
      switch (op) {
        case '>':  left = left >  right ? 1 : 0; break;
        case '<':  left = left <  right ? 1 : 0; break;
        case '>=': left = left >= right ? 1 : 0; break;
        case '<=': left = left <= right ? 1 : 0; break;
        case '==': left = left == right ? 1 : 0; break;
        case '!=': left = left != right ? 1 : 0; break;
      }
      p = p2;
    }
    return [left, p];
  }

  function parseAddSub(tokens, pos, ctx) {
    let [left, p] = parseMulDiv(tokens, pos, ctx);
    while (p < tokens.length && tokens[p].type === 'op'
           && (tokens[p].value === '+' || tokens[p].value === '-')) {
      const op = tokens[p].value;
      const [right, p2] = parseMulDiv(tokens, p + 1, ctx);
      left = op === '+' ? left + right : left - right;
      p = p2;
    }
    return [left, p];
  }

  function parseMulDiv(tokens, pos, ctx) {
    let [left, p] = parseUnary(tokens, pos, ctx);
    while (p < tokens.length && tokens[p].type === 'op'
           && (tokens[p].value === '*' || tokens[p].value === '/')) {
      const op = tokens[p].value;
      const [right, p2] = parseUnary(tokens, p + 1, ctx);
      left = op === '*' ? left * right : (right !== 0 ? left / right : NaN);
      p = p2;
    }
    return [left, p];
  }

  function parseUnary(tokens, pos, ctx) {
    if (pos < tokens.length && tokens[pos].type === 'op' && tokens[pos].value === '-') {
      const [val, p] = parseAtom(tokens, pos + 1, ctx);
      return [-val, p];
    }
    return parseAtom(tokens, pos, ctx);
  }

  function parseAtom(tokens, pos, ctx) {
    if (pos >= tokens.length) return [0, pos];
    const tok = tokens[pos];

    // Number literal
    if (tok.type === 'num') return [tok.value, pos + 1];

    // Parenthesized expression
    if (tok.type === '(') {
      const [val, p] = parseOr(tokens, pos + 1, ctx);
      const p2 = (p < tokens.length && tokens[p].type === ')') ? p + 1 : p;
      return [val, p2];
    }

    // Function call: fn(args...)
    if (tok.type === 'fn') {
      const fnName = tok.value;
      let p = pos + 1;
      const args = [];
      if (p < tokens.length && tokens[p].type === '(') {
        p++; // skip (
        while (p < tokens.length && tokens[p].type !== ')') {
          const [val, p2] = parseOr(tokens, p, ctx);
          args.push(val);
          p = p2;
          if (p < tokens.length && tokens[p].type === ',') p++;
        }
        if (p < tokens.length && tokens[p].type === ')') p++;
      }
      let result = 0;
      switch (fnName) {
        case 'abs':   result = args.length ? Math.abs(args[0]) : 0; break;
        case 'min':   result = args.length ? Math.min(...args) : 0; break;
        case 'max':   result = args.length ? Math.max(...args) : 0; break;
        case 'sum':   result = args.reduce((a, b) => a + b, 0); break;
        case 'count': result = args.length; break;
      }
      return [result, p];
    }

    // Identifier: answer.x, score.x, computed.x, parameter.x
    if (tok.type === 'id') {
      const parts = tok.value.split('.');
      const ns = parts[0];
      const key = parts.slice(1).join('.');
      let val = 0;
      if (ns === 'answer' && ctx.answer) {
        const raw = ctx.answer[key];
        val = (raw !== undefined && raw !== null && raw !== '' && raw !== 'NA')
          ? parseFloat(raw) : 0;
        if (isNaN(val)) val = 0;
      } else if (ns === 'score' && ctx.score) {
        val = ctx.score[key] !== undefined && ctx.score[key] !== null ? ctx.score[key] : 0;
      } else if (ns === 'computed' && ctx.computed) {
        val = ctx.computed[key] !== undefined && ctx.computed[key] !== null ? ctx.computed[key] : 0;
      } else if (ns === 'parameter' && ctx.parameter) {
        const raw = ctx.parameter[key];
        val = (raw !== undefined && raw !== null) ? parseFloat(raw) : 0;
        if (isNaN(val)) val = 0;
      }
      return [val, pos + 1];
    }

    // Unknown token — skip
    return [0, pos + 1];
  }

  /**
   * Evaluate a computed-variable expression string.
   * Returns a number (or boolean coerced to 0/1).
   */
  function evaluateExpression(exprStr, context) {
    const tokens = tokenizeExpr(exprStr);
    const [result] = evalExpr(tokens, 0, context);
    return result;
  }

  /**
   * Evaluate all computed variables defined in scaleDef.computed.
   * Respects dependency order: variables that reference other computed.* are evaluated after.
   * Returns { name: value, ... }
   */
  function computeComputedVars(scaleDef, responseMap, scores, transformedScores, params) {
    const computedBlock = scaleDef.computed || {};
    const names = Object.keys(computedBlock);
    if (names.length === 0) return {};

    const computed = {};
    const context = {
      answer: responseMap,
      score: Object.assign({}, scores, transformedScores),
      computed,
      parameter: params || {}
    };

    // Build dependency graph: which computed vars reference other computed vars
    const deps = {};
    for (const name of names) {
      const expr = computedBlock[name].expression || '';
      deps[name] = names.filter(other => other !== name && expr.includes('computed.' + other));
    }

    // Topological sort (Kahn's algorithm)
    const inDegree = {};
    for (const n of names) inDegree[n] = 0;
    for (const n of names) {
      for (const d of deps[n]) inDegree[n]++;
    }
    // Reverse: who depends on me
    const dependents = {};
    for (const n of names) dependents[n] = [];
    for (const n of names) {
      for (const d of deps[n]) dependents[d].push(n);
    }

    const queue = names.filter(n => inDegree[n] === 0);
    const order = [];
    while (queue.length) {
      const n = queue.shift();
      order.push(n);
      for (const dep of dependents[n]) {
        inDegree[dep]--;
        if (inDegree[dep] === 0) queue.push(dep);
      }
    }
    // Any remaining (circular) — just append
    for (const n of names) {
      if (!order.includes(n)) order.push(n);
    }

    // Evaluate in order
    for (const name of order) {
      const def = computedBlock[name];
      const val = evaluateExpression(def.expression || '0', context);
      computed[name] = (def.type === 'boolean') ? (val ? true : false) : val;
    }

    return computed;
  }

  // ============================================================
  // SCORER
  // ============================================================

  /**
   * Compute dimension scores from responseMap.
   * Returns {scores: {dimId: numericScore | null}, transformedScores: {dimId: number}}.
   */
  function computeScores(scaleDef, responseMap) {
    // Expand grid responses: responseMap['gridId'] = "3 4 2" → 'gridId_1'=3, 'gridId_2'=4, ...
    const expandedMap = Object.assign({}, responseMap);
    (scaleDef.items || scaleDef.questions || []).forEach(qdef => {
      if (qdef.type !== 'grid') return;
      const gridVal = responseMap[qdef.id];
      if (gridVal === undefined || gridVal === null || gridVal === 'NA') return;
      const parts = String(gridVal).split(' ');
      (qdef.rows || []).forEach((_, ri) => {
        expandedMap[`${qdef.id}_${ri + 1}`] = parts[ri] !== undefined ? parts[ri] : 'NA';
      });
    });
    responseMap = expandedMap;

    const scores = {};
    const scoring = scaleDef.scoring || {};
    const codedValuesByDim = {};

    // Helper: score one item-based dimension into scores/codedValuesByDim
    function scoreDimension(dimId, scoreDef) {
      const method  = scoreDef.method;
      const items   = scoreDef.items || [];
      const coding  = scoreDef.item_coding || {};
      const weights = scoreDef.weights || {};
      const correct = scoreDef.correct_answers || {};

      let total = 0, weightSum = 0, count = 0;
      const codedValues = [];

      for (const itemId of items) {
        const rawVal = responseMap[itemId];
        if (rawVal === undefined || rawVal === null || rawVal === '' || rawVal === 'NA') continue;

        if (method === 'sum_correct') {
          const acceptable = correct[itemId];
          if (acceptable) {
            const resp = String(rawVal).toLowerCase().trim();
            const match = acceptable.some(ans => {
              const a = String(ans).toLowerCase().trim();
              if (a === '*') return true;
              if (a.includes('?') || a.includes('*')) return wildcardMatch(resp, a);
              return resp === a;
            });
            if (match) total++;
            count++;
          }
          continue;
        }

        const numVal = parseFloat(rawVal);
        if (isNaN(numVal)) continue;

        const c = coding[itemId] !== undefined ? coding[itemId] : 1;
        if (c === 0) continue;

        let coded = numVal;
        if (c < 0) {
          const allItems = scaleDef.items || scaleDef.questions || [];
          let qdef = allItems.find(q => q.id === itemId);
          if (!qdef) {
            const m = itemId.match(/^(.+)_(\d+)$/);
            if (m) qdef = allItems.find(q => q.id === m[1] && q.type === 'grid');
          }
          const [rMin, rMax] = getQuestionRange(qdef || {}, scaleDef);
          coded = (rMin !== null && rMax !== null) ? (rMin + rMax) - numVal : numVal;
        }

        codedValues.push(coded);
        const w = weights[itemId] !== undefined ? weights[itemId] : 1;
        if (method === 'weighted_sum' || method === 'weighted_mean') {
          total += coded * w;
          weightSum += w;
        } else {
          total += coded;
        }
        count++;
      }

      // Score inputs (composite — uses already-computed transformed scores)
      if (scoreDef.scores) {
        const tScores = codedValuesByDim._transformedScores || {};
        for (const scoreId of scoreDef.scores) {
          const c = coding[scoreId] !== undefined ? coding[scoreId] : 1;
          if (c === 0) continue;
          // prefer transformed output, fall back to raw
          const val = tScores[scoreId] !== undefined ? tScores[scoreId] : scores[scoreId];
          if (val === undefined || val === null) continue;
          const coded = val * c;
          codedValues.push(coded);
          const w = weights[scoreId] !== undefined ? weights[scoreId] : 1;
          if (method === 'weighted_sum' || method === 'weighted_mean') {
            total += coded * w;
            weightSum += w;
          } else {
            total += coded;
          }
          count++;
        }
      }

      if (count === 0) {
        scores[dimId] = null;
      } else if (method === 'mean_coded') {
        scores[dimId] = total / count;
      } else if (method === 'weighted_mean') {
        scores[dimId] = weightSum !== 0 ? total / weightSum : null;
      } else {
        scores[dimId] = total;
      }
      codedValuesByDim[dimId] = codedValues;
    }

    // Pass 1: item-based dimensions (no scores field)
    for (const [dimId, scoreDef] of Object.entries(scoring)) {
      if (!scoreDef.scores) scoreDimension(dimId, scoreDef);
    }

    // Apply transforms after pass 1 so pass 2 can use transformed outputs
    const transformedScores = {};
    for (const [dimId, scoreDef] of Object.entries(scoring)) {
      if (!scoreDef.scores && scoreDef.transform && scores[dimId] !== null && scores[dimId] !== undefined) {
        transformedScores[dimId] = applyTransform(
          scores[dimId], scoreDef.transform, codedValuesByDim[dimId] || []
        );
      }
    }

    // Stash transformed scores so scoreDimension can reach them for pass 2
    codedValuesByDim._transformedScores = transformedScores;

    // Pass 2: composite dimensions that reference other dimension scores
    for (const [dimId, scoreDef] of Object.entries(scoring)) {
      if (scoreDef.scores) scoreDimension(dimId, scoreDef);
    }

    // Apply transforms for pass-2 dimensions
    for (const [dimId, scoreDef] of Object.entries(scoring)) {
      if (scoreDef.scores && scoreDef.transform && scores[dimId] !== null && scores[dimId] !== undefined) {
        transformedScores[dimId] = applyTransform(
          scores[dimId], scoreDef.transform, codedValuesByDim[dimId] || []
        );
      }
    }

    delete codedValuesByDim._transformedScores;

    return { scores, transformedScores };
  }

  function getNormLabel(score, scoreDef) {
    const thresholds = (scoreDef && scoreDef.norms && scoreDef.norms.thresholds) || [];
    const t = thresholds.find(t => score >= t.min && score <= t.max);
    return t ? t.label : null;
  }

  function applyTransform(rawScore, transformSteps, codedValues) {
    const n = codedValues.length;
    const stats = { n };
    if (n > 0) {
      stats.sum   = codedValues.reduce((a, b) => a + b, 0);
      stats.mean  = stats.sum / n;
      stats.min   = Math.min(...codedValues);
      stats.max   = Math.max(...codedValues);
      stats.range = stats.max - stats.min;
      const m = stats.mean;
      stats.sd = Math.sqrt(codedValues.reduce((acc, v) => acc + (v - m) ** 2, 0) / n);
    }
    let result = rawScore;
    for (const step of transformSteps) {
      let val = step.value;
      if (typeof val === 'string') val = stats[val] ?? 0;
      switch (step.op) {
        case 'add':      result += val; break;
        case 'subtract': result -= val; break;
        case 'multiply': result *= val; break;
        case 'divide':   if (val !== 0) result /= val; break;
      }
    }
    return result;
  }

  /** Simple wildcard match: * = any sequence, ? = single char */
  function wildcardMatch(str, pattern) {
    const re = '^' + pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&')
      .replace(/\*/g, '.*').replace(/\?/g, '.') + '$';
    try { return new RegExp(re).test(str); } catch (_) { return false; }
  }

  // ============================================================
  // DATA FORMATTERS
  // ============================================================

  /**
   * Build individual CSV lines (one per question).
   * Header: subnum,order,timestamp,question_id,text_key,question_text,response,rt,{dim1},...
   * Grid questions expand to one row per sub-item.
   */
  function buildIndividualCSV(state, scaleDef, scores, transformedScores, strings) {
    const dims = Object.keys(scores);
    const tDims = dims.filter(d => (transformedScores || {})[d] !== undefined);
    const header = ['subnum', 'order', 'timestamp', 'question_id', 'text_key',
                    'question_text', 'response', 'rt', ...dims, ...tDims.map(d => d + '_t')];

    const lines = [csvRow(header)];

    const { questions, responses, rts, timestamps, order, params, responseMap, aliasMap } = state;
    const participant = state.participant;

    questions.forEach((qdef, qi) => {
      if (qdef.type === 'section') return;

      const resp       = responses[qi];
      const rt         = rts[qi] !== undefined ? rts[qi] : 0;
      const ts         = timestamps[qi] !== undefined ? timestamps[qi] : '';
      const ord        = order[qi] !== undefined ? order[qi] : qi + 1;
      const qText      = resolveText(qdef.text_key, strings, params, responseMap, aliasMap);
      const responseVal = resp !== undefined && resp !== null ? resp : 'NA';

      // Dimension score columns — show coded item value per row
      const dimCols = dims.map(dimId => {
        const sd = (scaleDef.scoring || {})[dimId];
        if (!sd) return '';
        if (!sd.items || !sd.items.includes(qdef.id)) return '';
        if (responseVal === 'NA') return 'NA';
        // Coded value
        const numVal = parseFloat(responseVal);
        if (isNaN(numVal)) return responseVal;
        const coding = sd.item_coding && sd.item_coding[qdef.id];
        if (coding === -1) {
          const [rMin, rMax] = getQuestionRange(qdef, scaleDef);
          if (rMin !== null && rMax !== null) return String((rMin + rMax) - numVal);
        }
        return String(numVal);
      });

      // Transformed score columns — show dim-level transformed score for items in that dim
      const tDimCols = tDims.map(dimId => {
        const sd = (scaleDef.scoring || {})[dimId];
        if (!sd || !sd.items || !sd.items.includes(qdef.id)) return '';
        if (responseVal === 'NA') return 'NA';
        const tScore = (transformedScores || {})[dimId];
        return tScore !== undefined ? String(Math.round(tScore * 100) / 100) : 'NA';
      });

      if (qdef.type === 'grid') {
        // Expand one row per grid sub-item, computing per-sub-item dim columns
        const rows = qdef.rows || [];
        const respParts = (typeof responseVal === 'string' ? responseVal : '').split(' ');
        const [gMin, gMax] = getQuestionRange(qdef, scaleDef);
        rows.forEach((rowKey, ri) => {
          const subId = `${qdef.id}_${ri + 1}`;
          const subResp = respParts[ri] || 'NA';
          const subText = resolveText(rowKey, strings, params, responseMap, aliasMap);

          const subDimCols = dims.map(dimId => {
            const sd = (scaleDef.scoring || {})[dimId];
            if (!sd || !sd.items || !sd.items.includes(subId)) return '';
            if (subResp === 'NA') return 'NA';
            const numVal = parseFloat(subResp);
            if (isNaN(numVal)) return subResp;
            const c = sd.item_coding && sd.item_coding[subId];
            if (c === -1 && gMin !== null && gMax !== null) {
              return String((gMin + gMax) - numVal);
            }
            return String(numVal);
          });

          const subTDimCols = tDims.map(dimId => {
            const sd = (scaleDef.scoring || {})[dimId];
            if (!sd || !sd.items || !sd.items.includes(subId)) return '';
            if (subResp === 'NA') return 'NA';
            const tScore = (transformedScores || {})[dimId];
            return tScore !== undefined ? String(Math.round(tScore * 100) / 100) : 'NA';
          });

          lines.push(csvRow([
            participant, String(ord), String(ts), subId,
            qdef.text_key, subText, subResp, String(rt), ...subDimCols, ...subTDimCols
          ]));
        });
      } else {
        lines.push(csvRow([
          participant, String(ord), String(ts), qdef.id,
          qdef.text_key, qText, String(responseVal), String(rt), ...dimCols, ...tDimCols
        ]));
      }
    });

    return lines;
  }

  /**
   * Build pooled header string.
   * subnum,timestamp,time,{question_ids...},{dim_ids...},{branchGroup_arm,...}
   */
  function buildPooledHeader(state, scaleDef, computedVars) {
    const qIds = [];
    (state.questions || []).forEach(qdef => {
      if (qdef.type === 'section' || qdef.type === 'inst' || qdef.type === 'image') return;
      if (qdef.type === 'grid') {
        (qdef.rows || []).forEach((_, ri) => qIds.push(`${qdef.id}_${ri + 1}`));
      } else {
        qIds.push(qdef.id);
      }
    });

    const dims = Object.keys(scaleDef.scoring || {});
    const tDims = dims.filter(d => (scaleDef.scoring || {})[d] && (scaleDef.scoring || {})[d].transform);
    const compNames = Object.keys(computedVars || {});
    const branchCols = Object.keys(state.branchChoices || {}).map(g => `${g}_arm`);

    return csvRow(['subnum', 'timestamp', 'time', ...qIds, ...dims, ...tDims.map(d => d + '_t'), ...compNames, ...branchCols]);
  }

  /**
   * Build single pooled data line.
   */
  function buildPooledLine(state, scaleDef, scores, transformedScores, computedVars) {
    const { questions, responses, participant, startTime, branchChoices } = state;
    const timestamp = Math.round(startTime / 1000);
    const elapsed   = Math.round((nowMs() - startTime) / 1000);

    const qVals = [];
    questions.forEach((qdef, qi) => {
      if (qdef.type === 'section' || qdef.type === 'inst' || qdef.type === 'image') return;
      const resp = responses[qi];
      const val  = resp !== undefined && resp !== null ? resp : 'NA';
      if (qdef.type === 'grid') {
        const parts = (typeof val === 'string' ? val : '').split(' ');
        (qdef.rows || []).forEach((_, ri) => qVals.push(parts[ri] || 'NA'));
      } else {
        qVals.push(val);
      }
    });

    const dims    = Object.keys(scaleDef.scoring || {});
    const dimVals = dims.map(d => scores[d] !== null && scores[d] !== undefined ? String(scores[d]) : 'NA');
    const tDims   = dims.filter(d => (scaleDef.scoring || {})[d] && (scaleDef.scoring || {})[d].transform);
    const tDimVals = tDims.map(d => {
      const v = (transformedScores || {})[d];
      return v !== undefined ? String(v) : 'NA';
    });
    const compVals = Object.values(computedVars || {}).map(v =>
      v !== undefined && v !== null ? String(v) : 'NA'
    );
    const branchVals = Object.values(branchChoices || {}).map(v => v || 'NA');

    return csvRow([participant, String(timestamp), String(elapsed),
                   ...qVals, ...dimVals, ...tDimVals, ...compVals, ...branchVals]);
  }

  // ============================================================
  // UPLOADER
  // ============================================================

  /**
   * POST data to collectURL.
   * Shape matches both peblhub api/upload.php and server/collect.php.
   */
  async function submitData(config, csvLines, pooledLine, pooledHeader, scaleDef) {
    if (!config.collectURL) return { ok: true, local: true };

    const fd = new FormData();
    fd.append('participant', config.participant || '');
    fd.append('subnum',      config.participant || '');  // upload.php requires subnum
    fd.append('scale',       config.scale || '');
    fd.append('token',       config.token  || '');
    fd.append('version',     VERSION);

    // Individual CSV as a file upload
    const csvBlob = new Blob([csvLines.join('\r\n') + '\r\n'], { type: 'text/csv' });
    const filename = `${config.scale}-${config.participant}.csv`;
    fd.append('data',     csvBlob, filename);
    fd.append('fileToUpload', csvBlob, filename);  // peblhub compat alias

    // Pooled line
    fd.append('pooled',        pooledLine);
    fd.append('pooled_header', pooledHeader);
    fd.append('individual_header', csvLines[0] || '');

    // taskname for peblhub compat
    fd.append('taskname', config.scale || '');
    if (config.token) {
      fd.append('auth_token',     config.token);
      fd.append('upload_password', config.token);
    }

    try {
      const res = await fetch(config.collectURL, { method: 'POST', body: fd });
      return { ok: res.ok, status: res.status };
    } catch (err) {
      console.warn('ScaleRunner: upload failed', err);
      return { ok: false, error: err.message };
    }
  }

  // ============================================================
  // DOM SHELL HELPERS
  // ============================================================

  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function showError(container, msg) {
    let err = container.querySelector('.sr-error');
    if (!err) {
      err = el('div', 'sr-error');
      container.appendChild(err);
    }
    err.textContent = msg || '';
    err.style.display = msg ? '' : 'none';
  }

  function clearError(container) { showError(container, ''); }

  // ============================================================
  // MAIN MOUNT FUNCTION
  // ============================================================

  /**
   * Mount the scale runner into containerElement.
   */
  async function mount(containerElement, config) {
    config = config || {};
    const container = containerElement;
    container.innerHTML = '';
    container.className = 'sr-container';

    // ── Loading state ──────────────────────────────────────────
    const loadingEl = el('div', 'sr-loading', '<span class="sr-spinner"></span><p>Loading…</p>');
    container.appendChild(loadingEl);

    // ── Load scale ────────────────────────────────────────────
    let scaleDef, strings;
    try {
      ({ scaleDef, strings } = await loadScale(
        config.scale,
        config.language || 'en',
        config.baseURL  || '',
        config.osdURL   || null
      ));
    } catch (err) {
      container.innerHTML = '';
      const errEl = el('div', 'sr-error-fatal',
        `<strong>Error loading scale:</strong> ${err.message}`);
      container.appendChild(errEl);
      console.error('ScaleRunner load error:', err);
      return;
    }

    // ── Derive scale code if not set (osd= mode) ─────────────
    if (!config.scale) {
      const info = scaleDef.scale_info || {};
      config = Object.assign({}, config, {
        scale: info.code || scaleDef.code ||
               (config.osdURL ? config.osdURL.split('/').pop().replace(/\.osd$/i, '') : '') ||
               'scale'
      });
    }

    // ── Merge runtime params ──────────────────────────────────
    const params = {};
    const paramDefs = scaleDef.parameters || {};
    for (const [k, pd] of Object.entries(paramDefs)) {
      params[k] = pd.default !== undefined ? pd.default : null;
    }
    if (config.params) Object.assign(params, config.params);

    // ── Apply OSD show_header param to title visibility ───────
    // show_header default (from OSD) overrides the runner's URL-param-based showTitle,
    // but only when the caller hasn't explicitly set showTitle to false already.
    if (params.show_header !== undefined && !Number(params.show_header)) {
      config = Object.assign({}, config, { showTitle: false });
    }

    // ── Build question list ───────────────────────────────────
    const { questions, branchChoices, aliasMap } = buildQuestionList(scaleDef, params);

    // Count scorable questions for progress
    const scorableQ = questions.filter(q => q.type !== 'section').length;

    // ── Initialize state ──────────────────────────────────────
    const state = {
      questions,
      currentIndex: 0,
      responseMap:  {},
      responses:    new Array(questions.length).fill(undefined),
      rts:          new Array(questions.length).fill(0),
      timestamps:   new Array(questions.length).fill(null),
      order:        new Array(questions.length).fill(0),
      sectionExcluded:          false,
      sectionRevisable:         true,   // default: implicit section 0 is revisable
      sectionFirstVisibleIndex: -1,     // index of first visible question in current section (-1 = none yet)
      branchChoices,
      aliasMap,
      startTime:    nowMs(),
      participant:  config.participant || 'unknown',
      scale:        config.scale || '',
      params,
    };

    // ── Remove loading screen ─────────────────────────────────
    container.innerHTML = '';

    // ── Build static shell ────────────────────────────────────
    const scaleTitle = (scaleDef.scale_info && scaleDef.scale_info.name) || config.scale || '';

    const header = el('header', 'sr-header');
    const titleEl = el('h1', 'sr-title', scaleTitle);
    if (config.showTitle === false) titleEl.hidden = true;
    header.appendChild(titleEl);
    const sectionTitleEl = el('h2', 'sr-section-title', '');
    sectionTitleEl.hidden = true;
    header.appendChild(sectionTitleEl);
    container.appendChild(header);

    const main = el('main', 'sr-main');
    container.appendChild(main);

    // ── Demo mode banner ──────────────────────────────────────
    if (config.demo) {
      const demoBanner = el('div', 'sr-demo-banner',
        '🔍 <strong>Demo mode</strong> — responses are not saved or uploaded.');
      container.insertBefore(demoBanner, main);
    }

    const progressBar  = el('div', 'sr-progress-bar');
    const progressFill = el('div', 'sr-progress-fill');
    progressBar.appendChild(progressFill);
    container.appendChild(progressBar);

    const progressText = el('div', 'sr-progress-text', '');
    container.appendChild(progressText);

    // ── Question rendering loop ───────────────────────────────
    let orderCounter = 0;
    let navGeneration = 0;  // bumped on every navigation; cancels stale auto-advance timeouts

    function advance() {
      state.currentIndex++;
      showNext();
    }

    // Navigate backward to the previous answered question within the current section.
    // Cannot cross section boundaries.
    function goBack() {
      let idx = state.currentIndex - 1;
      while (idx >= 0) {
        const q = state.questions[idx];
        if (q.type === 'section') {
          // Hit a section boundary — cannot go further back
          break;
        }
        // Only land on questions that were answered (not hidden/NA)
        if (state.responses[idx] !== undefined && state.responses[idx] !== null) {
          state.currentIndex = idx;
          renderCurrentQuestion(state.currentIndex);
          return;
        }
        idx--;
      }
      // No eligible previous question found — stay put (shouldn't happen if Back was properly gated)
      renderCurrentQuestion(state.currentIndex);
    }

    function showNext() {
      // Find next question to show (skip section markers + hidden questions)
      while (state.currentIndex < state.questions.length) {
        const q = state.questions[state.currentIndex];

        if (q.type === 'section') {
          // Update section exclusion and revisable flags; reset first-visible tracker
          const secExcluded = q._excluded ||
            (q.visible_when && !evaluateCondition(q.visible_when, state.responseMap, state.params));
          state.sectionExcluded    = !!secExcluded;
          state.sectionRevisable   = q.revisable !== false;  // default true
          state.sectionFirstVisibleIndex = -1;               // reset for new section

          // Update header section title
          const secTitle = q.text_key ? resolveText(q.text_key, strings, state.params, state.responseMap, state.aliasMap) : '';
          if (secTitle) {
            sectionTitleEl.textContent = secTitle;
            sectionTitleEl.hidden = false;
          } else {
            sectionTitleEl.textContent = '';
            sectionTitleEl.hidden = true;
          }

          state.currentIndex++;
          continue;
        }

        if (!shouldShow(q, state, scaleDef)) {
          // Record as NA
          state.responses[state.currentIndex]  = undefined;
          state.rts[state.currentIndex]        = 0;
          state.timestamps[state.currentIndex] = null;
          state.currentIndex++;
          continue;
        }

        // Track the first visible question in the current section (for Back boundary)
        if (state.sectionFirstVisibleIndex < 0) {
          state.sectionFirstVisibleIndex = state.currentIndex;
        }

        // Render this question
        renderCurrentQuestion(state.currentIndex);
        return;
      }

      // All done!
      finish();
    }

    function renderCurrentQuestion(qi) {
      const myGeneration = ++navGeneration;  // capture; stale timeouts won't match
      const qdef = state.questions[qi];
      main.innerHTML = '';
      clearError(main);

      // Only assign a new presentation order on the first visit (not on re-visit after Back)
      if (!state.order[qi]) {
        orderCounter++;
        state.order[qi] = orderCounter;
      }
      state.timestamps[qi] = nowMs();

      // Question-head instruction line (render before item text)
      const opts = scaleDef.likert_options || {};
      const headKey = qdef.question_head || (qdef.type === 'likert' && opts.question_head);
      if (headKey) {
        const headText = resolveText(headKey, strings, state.params, state.responseMap, state.aliasMap);
        if (headText && headText !== headKey) {
          const headEl = document.createElement('p');
          headEl.className = 'sr-question-head';
          headEl.innerHTML = headText;
          main.appendChild(headEl);
        }
      }

      // Item text — split on <img> if present (C4a Media Embedding)
      const qTextRaw = resolveText(qdef.text_key, strings, state.params, state.responseMap, state.aliasMap);
      const qTextEl  = buildItemTextEl(qTextRaw, config.baseURL || '', state.params);
      qTextEl.classList.add('sr-question-text');
      main.appendChild(qTextEl);

      // Pre-fill previous response if re-visiting after Back
      const prevResponse = state.responseMap[qdef.id] !== undefined &&
                           state.responseMap[qdef.id] !== 'NA'
                             ? state.responseMap[qdef.id]
                             : undefined;

      // Response state — start from previous response if available
      let currentResponse = prevResponse !== undefined ? prevResponse : undefined;
      const required = isQuestionRequired(qdef, scaleDef);

      // Declare nextBtn early so onResponse closure can reference it
      let nextBtn;

      function onResponse(value, readyToAdvance, noAutoAdvance) {
        currentResponse = value;
        if (nextBtn) nextBtn.disabled = !readyToAdvance && required;
        if (readyToAdvance && !noAutoAdvance && ['likert', 'multi'].includes(qdef.type)) {
          // Auto-advance after short delay; guard against stale fire after Back navigation
          setTimeout(() => {
            if (myGeneration === navGeneration && currentResponse !== undefined) handleNext();
          }, 400);
        }
      }

      // Render response widget (pass prevResponse so widgets can pre-select)
      const widget = renderQuestion(qdef, strings, scaleDef, state, onResponse, prevResponse);
      main.appendChild(widget);

      // Error display
      const errorEl = el('div', 'sr-inline-error', '');
      main.appendChild(errorEl);

      // Next / Skip buttons
      const btnRow = el('div', 'sr-btn-row');

      // Back button — only when current section is revisable and a prior answered question exists
      const canGoBack = state.sectionRevisable &&
                        state.sectionFirstVisibleIndex >= 0 &&
                        qi > state.sectionFirstVisibleIndex;
      if (canGoBack) {
        const backBtn = el('button', 'sr-back-btn');
        backBtn.type = 'button';
        backBtn.textContent = strings['back_label'] || 'BACK';
        backBtn.addEventListener('click', () => goBack());
        btnRow.appendChild(backBtn);
      }

      // Skip button for optional questions
      if (!required && qdef.type !== 'inst' && qdef.type !== 'image') {
        const skipBtn = el('button', 'sr-skip-btn');
        skipBtn.type = 'button';
        skipBtn.textContent = strings['skip_label'] || 'SKIP';
        skipBtn.addEventListener('click', () => {
          const skipRT = nowMs() - state.timestamps[qi];
          state.responses[qi]  = 'NA';
          state.rts[qi]        = skipRT;
          state.responseMap[qdef.id] = 'NA';
          advance();
        });
        btnRow.appendChild(skipBtn);
      }

      nextBtn = el('button', 'sr-next-btn');
      nextBtn.type = 'button';
      nextBtn.textContent = strings['next_label'] || 'NEXT';
      // Next is enabled if: a prevResponse exists (re-visit), or question is non-required, or type is inst/image
      nextBtn.disabled = required && qdef.type !== 'inst' && qdef.type !== 'image' && prevResponse === undefined;

      function handleNext() {
        const val = currentResponse;
        const result = validateResponse(qdef, val, strings, state.params);
        if (!result.valid) {
          errorEl.textContent = result.error || 'Please answer this question.';
          nextBtn.disabled = false;
          return;
        }
        errorEl.textContent = '';

        const rt = nowMs() - state.timestamps[qi];
        state.responses[qi]  = val;
        state.rts[qi]        = rt;
        const mapVal = Array.isArray(val) ? val.join(',') : val;
        state.responseMap[qdef.id] = mapVal !== undefined && mapVal !== null ? mapVal : '';

        // Gate check — must happen after response is recorded so data is saved
        if (qdef.gate && gateTriggered(qdef.gate, mapVal)) {
          terminate(qdef.gate);
          return;
        }

        advance();
      }

      nextBtn.addEventListener('click', handleNext);
      btnRow.appendChild(nextBtn);
      main.appendChild(btnRow);

      // Progress
      const answered = state.responses.filter((r, i) => {
        const q = state.questions[i];
        return q && q.type !== 'section' && r !== undefined;
      }).length;
      const total = scorableQ;
      const pct   = total > 0 ? Math.round((answered / total) * 100) : 0;
      progressFill.style.width = `${pct}%`;
      progressFill.setAttribute('aria-valuenow', String(pct));
      progressText.textContent = `${answered} of ${total}`;

      // Keyboard navigation: Enter = Next
      const keyHandler = (e) => {
        if (e.key === 'Enter' && !nextBtn.disabled) {
          document.removeEventListener('keydown', keyHandler);
          handleNext();
        }
      };
      document.addEventListener('keydown', keyHandler);
    }

    /**
     * Returns true if the gate condition FAILS (i.e. the participant
     * should be blocked). Response is already stored in state.responseMap.
     */
    function gateTriggered(gate, response) {
      if (gate.required_value !== undefined) {
        return String(response) !== String(gate.required_value);
      }
      if (gate.operator) {
        // Reuse evaluateCondition with a synthetic question reference
        // We pass a fake question id __gate__ and put the response there
        const cond = { question: '__gate__', operator: gate.operator, value: gate.value };
        return !evaluateCondition(cond, { __gate__: response }, state.params);
      }
      return false;
    }

    /**
     * Terminate the scale after a gate blocks the participant.
     * Still saves all collected data so the record exists.
     */
    async function terminate(gate) {
      main.innerHTML = '';
      progressFill.style.width = '0%';
      progressText.textContent = '';

      // Compute partial scores from whatever was answered
      const { scores, transformedScores } = computeScores(scaleDef, state.responseMap);
      const computedVars = computeComputedVars(scaleDef, state.responseMap, scores, transformedScores, state.params);
      const csvLines   = buildIndividualCSV(state, scaleDef, scores, transformedScores, strings);
      const pooledHdr  = buildPooledHeader(state, scaleDef, computedVars);
      const pooledLine = buildPooledLine(state, scaleDef, scores, transformedScores, computedVars);

      // Upload data — status will be visible from incomplete question columns
      try {
        await submitData(config, csvLines, pooledLine, pooledHdr, scaleDef);
      } catch (err) {
        console.warn('ScaleRunner: upload error on termination', err);
      }

      // Show termination message
      const msgKey  = gate.terminate_message_key;
      const msgText = (msgKey && strings[msgKey]) || strings['gate_terminated'] ||
        'Thank you. Based on your responses you are not eligible to continue.';

      const wrap = el('div', 'sr-terminate');
      wrap.appendChild(el('h2', 'sr-terminate-heading',
        strings['terminate_heading'] || 'Session Ended'));
      const msgEl = el('p', 'sr-terminate-text');
      msgEl.innerHTML = msgText;
      wrap.appendChild(msgEl);
      main.appendChild(wrap);

      // Expose data before callbacks so chain runners can access responseMap
      container._scaleData = { csvLines, pooledLine, pooledHdr, scores, state };

      // Dispatch peblTestComplete with status 'terminated' — chain runners see this
      const detail = { status: 'terminated', scale: config.scale,
                       participant: config.participant, scores, computed: computedVars,
                       responses: state.responseMap };
      document.dispatchEvent(new CustomEvent('peblTestComplete', {
        bubbles: true, detail
      }));
      if (config.onComplete) config.onComplete(detail);
    }

    async function finish() {
      main.innerHTML = '';
      progressFill.style.width = '100%';
      progressText.textContent = '';

      // Compute scores and computed variables (S7)
      const { scores, transformedScores } = computeScores(scaleDef, state.responseMap);
      const computedVars = computeComputedVars(scaleDef, state.responseMap, scores, transformedScores, state.params);

      // Build CSV
      const csvLines    = buildIndividualCSV(state, scaleDef, scores, transformedScores, strings);
      const pooledHdr   = buildPooledHeader(state, scaleDef, computedVars);
      const pooledLine  = buildPooledLine(state, scaleDef, scores, transformedScores, computedVars);

      // Upload
      let uploadOK = false;
      try {
        const res = await submitData(config, csvLines, pooledLine, pooledHdr, scaleDef);
        uploadOK = res.ok;
      } catch (err) {
        console.warn('ScaleRunner: upload error', err);
      }

      // Build HTML report
      const csvContent = csvLines.join('\r\n') + '\r\n';
      const reportHTML = buildReport(state, scaleDef, scores, transformedScores, strings, config.demo, csvContent, computedVars);

      // Upload report too (best-effort, same endpoint)
      if (config.collectURL) {
        try {
          const fd2 = new FormData();
          const rptFilename = `${config.scale}-${state.participant}-report.html`;
          fd2.append('fileToUpload', new Blob([reportHTML], {type:'text/html'}), rptFilename);
          fd2.append('data',        new Blob([reportHTML], {type:'text/html'}), rptFilename);
          fd2.append('participant', state.participant);
          fd2.append('scale',       config.scale || '');
          fd2.append('token',       config.token  || '');
          fd2.append('taskname',    config.scale  || '');
          if (config.token) { fd2.append('auth_token', config.token);
                              fd2.append('upload_password', config.token); }
          await fetch(config.collectURL, { method: 'POST', body: fd2 });
        } catch (_) { /* report upload failure is non-fatal */ }
      }

      // Debrief / end page
      const debriefKey  = (scaleDef.scale_info && scaleDef.scale_info.debrief_key) || 'debrief';
      const debriefText = strings[debriefKey] || strings['debrief'] || '';
      const debrief = el('div', 'sr-debrief');
      // Completion heading
      debrief.appendChild(el('h2', 'sr-debrief-heading',
        strings['complete_heading'] || 'Thank you!'));
      if (debriefText) {
        const txt = el('p', 'sr-debrief-text');
        txt.innerHTML = debriefText;
        debrief.appendChild(txt);
      }
      main.appendChild(debrief);

      // Report download link
      const rptBlob = new Blob([reportHTML], { type: 'text/html' });
      const rptURL  = URL.createObjectURL(rptBlob);
      const rptLink = document.createElement('a');
      rptLink.href      = rptURL;
      rptLink.download  = `${config.scale}-${state.participant}-report.html`;
      rptLink.className = 'sr-report-link';
      rptLink.textContent = 'Download report';
      main.appendChild(rptLink);

      // Trial-by-trial CSV download link
      const csvBlob = new Blob([csvLines.join('\r\n') + '\r\n'], { type: 'text/csv' });
      const csvURL  = URL.createObjectURL(csvBlob);
      const csvLink = document.createElement('a');
      csvLink.href      = csvURL;
      csvLink.download  = `${config.scale}-${state.participant}.csv`;
      csvLink.className = 'sr-report-link';
      csvLink.textContent = 'Download trial-by-trial data';
      main.appendChild(csvLink);

      if (!uploadOK && config.collectURL) {
        const note = el('p', 'sr-upload-note',
          'Note: Your responses could not be uploaded automatically. ' +
          'Please contact the researcher.');
        main.appendChild(note);
      }

      // Expose data before callbacks so chain runners can access responseMap
      container._scaleData = { csvLines, pooledLine, pooledHdr, scores, reportHTML, state };

      // Dispatch peblTestComplete event — identical to PEBL's signal
      const detail = { status: 'completed', scale: config.scale,
                       participant: config.participant, scores, computed: computedVars,
                       responses: state.responseMap };
      document.dispatchEvent(new CustomEvent('peblTestComplete', {
        bubbles: true, detail
      }));
      if (config.onComplete) config.onComplete(detail);
    }

    // ── Start ─────────────────────────────────────────────────
    showNext();
  }

  // ============================================================
  // REPORT BUILDER
  // ============================================================

  /**
   * Build an HTML report string, mirroring ScaleRunner.pbl's report.
   * Returns an HTML string (full document).
   */
  function buildReport(state, scaleDef, scores, transformedScores, strings, demo, csvContent, computedVars) {
    const info       = scaleDef.scale_info || {};
    const name       = info.name  || state.scale || '';
    const citation   = info.citation || '';
    const description = info.description || '';
    const footerRefs = (scaleDef.report && scaleDef.report.footer_refs) || [];

    // Completion time in minutes, rounded to 2 decimal places — matches native
    const elapsedMs  = nowMs() - state.startTime;
    const elapsedMin = Math.round((elapsedMs / 1000 / 60) * 100) / 100;
    const ts         = new Date(state.startTime).toLocaleString();

    // ── CSS matching native ScaleRunner.pbl exactly ──────────
    const css = `
      body { font-family: Arial, sans-serif; margin: 40px; }
      table { border-collapse: collapse; margin: 20px 0; }
      th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
      th { background-color: #4CAF50; color: white; }
      tr:nth-child(even) { background-color: #f2f2f2; }
      .summary { background-color: #e7f3e7; padding: 20px; border-radius: 5px; margin: 20px 0; }
      h1 { color: #333; }
      h2 { color: #666; }
      .citation { font-style: italic; color: #666; margin: 10px 0; }
      .norm-label { font-style: italic; color: #555; }`;

    // ── Dimension scores table ────────────────────────────────
    let dimScoresSection = '';
    if (scaleDef.dimensions && scaleDef.dimensions.length) {
      let hasNorms = false;
      let hasTrans = false;
      const dimIds = new Set(scaleDef.dimensions.map(d => d.id));
      const rowData = scaleDef.dimensions.map(dim => {
        const score = scores[dim.id];
        if (score === undefined) return null;
        const val = score !== null ? (Math.round(score * 100) / 100) : 'N/A';
        const scoreDef = (scaleDef.scoring || {})[dim.id];
        const normLabel = (score !== null) ? getNormLabel(score, scoreDef) : null;
        if (normLabel) hasNorms = true;
        const tScore = (transformedScores || {})[dim.id];
        const tVal = tScore !== undefined ? Math.round(tScore * 100) / 100 : null;
        if (tVal !== null) hasTrans = true;
        return { name: dim.name, val, normLabel, tVal };
      }).filter(r => r !== null);

      // Include composite scores (scoring keys not matching any dimension)
      if (scaleDef.scoring) {
        Object.keys(scaleDef.scoring).forEach(key => {
          if (dimIds.has(key)) return;
          const score = scores[key];
          if (score === undefined) return;
          const val = score !== null ? (Math.round(score * 100) / 100) : 'N/A';
          const scoreDef = scaleDef.scoring[key];
          const normLabel = (score !== null) ? getNormLabel(score, scoreDef) : null;
          if (normLabel) hasNorms = true;
          const tScore = (transformedScores || {})[key];
          const tVal = tScore !== undefined ? Math.round(tScore * 100) / 100 : null;
          if (tVal !== null) hasTrans = true;
          // Use name field, or fall back to formatted key
          const name = scoreDef.name
            || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
          rowData.push({ name, val, normLabel, tVal });
        });
      }

      if (rowData.length) {
        const tHeader  = hasTrans ? '<th>Transformed</th>' : '';
        const normHeader = hasNorms ? '<th>Interpretation</th>' : '';
        const thead = `<tr><th>Dimension</th><th>Score</th>${tHeader}${normHeader}</tr>`;
        const dimRows = rowData.map(r => {
          const tCell   = hasTrans  ? `<td>${r.tVal !== null ? r.tVal : ''}</td>` : '';
          const normCell = hasNorms ? `<td class="norm-label">${r.normLabel || ''}</td>` : '';
          return `<tr><td>${r.name}</td><td>${r.val}</td>${tCell}${normCell}</tr>`;
        }).join('');
        dimScoresSection = `<h2>Dimension Scores</h2>
          <table><thead>${thead}</thead>
          <tbody>${dimRows}</tbody></table>`;
      }
    }

    // ── Computed variables table (S7) ────────────────────────
    let computedSection = '';
    if (computedVars && Object.keys(computedVars).length > 0) {
      const compBlock = scaleDef.computed || {};
      let hasCompNorms = false;
      const compRowData = Object.entries(computedVars).map(([name, val]) => {
        const def = compBlock[name] || {};
        const displayVal = (val !== null && val !== undefined)
          ? (typeof val === 'number' ? Math.round(val * 100) / 100 : String(val))
          : 'N/A';
        const displayName = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const normLabel = (val !== null && val !== undefined && typeof val === 'number')
          ? getNormLabel(val, def) : null;
        if (normLabel) hasCompNorms = true;
        return { displayName, displayVal, normLabel };
      });
      const compNormHeader = hasCompNorms ? '<th>Interpretation</th>' : '';
      const compRows = compRowData.map(r => {
        const normCell = hasCompNorms
          ? `<td class="norm-label">${r.normLabel || ''}</td>` : '';
        return `<tr><td>${r.displayName}</td><td>${r.displayVal}</td>${normCell}</tr>`;
      }).join('');
      computedSection = `<h2>Computed Variables</h2>
        <table><thead><tr><th>Variable</th><th>Value</th>${compNormHeader}</tr></thead>
        <tbody>${compRows}</tbody></table>`;
    }

    // ── Responses table ───────────────────────────────────────
    // Columns: Question | Response | [one per dimension]
    const dims = scaleDef.dimensions || [];
    const dimHeaders = dims.map(d => `<th>${d.name}</th>`).join('');
    const respRows = [];

    (scaleDef.items || scaleDef.questions || []).forEach(qdef => {
      // Skip sections, inst, and image-only items
      if (['section', 'inst', 'image'].includes(qdef.type)) return;

      const resp = state.responseMap[qdef.id];

      // Skip hidden questions (visible_when + no response)
      if ((resp === undefined || resp === 'NA') && qdef.visible_when) return;

      // Question text — resolve param substitutions, truncate at 120 chars
      let qText = resolveText(qdef.text_key, strings, state.params, state.responseMap, state.aliasMap);
      if (qText.length > 120) qText = qText.slice(0, 117) + '...';

      const respVal = resp !== undefined && resp !== null ? resp : 'NA';

      if (qdef.type === 'grid') {
        // Expand grid into one row per sub-item
        const rows = qdef.rows || [];
        const respParts = (typeof respVal === 'string' ? respVal : '').split(' ');
        const [gMin, gMax] = getQuestionRange(qdef, scaleDef);
        rows.forEach((rowKey, ri) => {
          const subId   = `${qdef.id}_${ri + 1}`;
          const subResp = respParts[ri] || 'NA';
          const subText = resolveText(rowKey, strings, state.params, state.responseMap, state.aliasMap);

          const subDimCells = dims.map(dim => {
            const sd = (scaleDef.scoring || {})[dim.id];
            if (!sd || !sd.items || !sd.items.includes(subId)) return '<td></td>';
            if (subResp === 'NA' || subResp === '') return '<td></td>';
            const numVal = parseFloat(subResp);
            if (isNaN(numVal)) return `<td>${subResp}</td>`;
            const c = sd.item_coding && sd.item_coding[subId];
            let coded = numVal;
            if (c === -1 && gMin !== null && gMax !== null) {
              coded = (gMin + gMax) - numVal;
            }
            return `<td>${coded}</td>`;
          }).join('');

          respRows.push(`<tr><td>${subText}</td><td>${subResp}</td>${subDimCells}</tr>`);
        });
      } else {
      // Per-dimension coded values
      const dimCells = dims.map(dim => {
        const sd = (scaleDef.scoring || {})[dim.id];
        if (!sd || !sd.items || !sd.items.includes(qdef.id)) return '<td></td>';
        if (respVal === 'NA' || respVal === '') return '<td></td>';

        // sum_correct: show 1 (correct) or 0 (incorrect), not the raw response
        if (sd.method === 'sum_correct') {
          const acceptable = (sd.correct_answers || {})[qdef.id];
          if (!acceptable) return '<td></td>';
          const r = String(respVal).toLowerCase().trim();
          const isCorrect = acceptable.some(ans => {
            const a = String(ans).toLowerCase().trim();
            if (a === '*') return true;
            if (a.includes('?') || a.includes('*')) return wildcardMatch(r, a);
            return r === a;
          });
          return `<td>${isCorrect ? 1 : 0}</td>`;
        }

        // Likert / coded methods: apply item_coding
        const numVal = parseFloat(respVal);
        if (isNaN(numVal)) return `<td>${respVal}</td>`;
        const c = sd.item_coding && sd.item_coding[qdef.id];
        let coded = numVal;
        if (c === -1) {
          const [rMin, rMax] = getQuestionRange(qdef, scaleDef);
          if (rMin !== null && rMax !== null) coded = (rMin + rMax) - numVal;
        }
        return `<td>${coded}</td>`;
      }).join('');

      respRows.push(`<tr><td>${qText}</td><td>${respVal}</td>${dimCells}</tr>`);
      }
    });

    const responsesSection = `<h2>Responses</h2>
      <table><thead><tr><th>Question</th><th>Response</th>${dimHeaders}</tr></thead>
      <tbody>${respRows.join('')}</tbody></table>`;

    // ── Data files section ────────────────────────────────────
    let dataFilesSection;
    const csvFilename    = `${state.scale}-${state.participant}.csv`;
    const pooledFilename = `${state.scale}-pooled.csv`;
    const reportFilename = `${state.scale}-${state.participant}-report.html`;
    const csvDataURI = csvContent
      ? 'data:text/csv;base64,' + btoa(unescape(encodeURIComponent(csvContent)))
      : '';
    dataFilesSection = `<hr>
      <h2>Data Files</h2>
      ${demo ? '<p><em>Demo mode — data was not uploaded to a server.</em></p>' : ''}
      <p>The following data files were generated for this session:</p>
      <ul>
        <li>${csvDataURI
          ? `<a href="${csvDataURI}" download="${csvFilename}">${csvFilename}</a>`
          : csvFilename} — Trial-by-trial data</li>
        <li>${pooledFilename} — Summary data</li>
        <li>${reportFilename} — This report</li>
      </ul>`;

    // ── Parameters section ────────────────────────────────────
    const paramRows = Object.entries(state.params || {}).map(
      ([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
    const paramsSection = paramRows ? `<hr>
      <h2>Parameters</h2>
      <table><thead><tr><th>Parameter</th><th>Value</th></tr></thead>
      <tbody>${paramRows}</tbody></table>` : '';

    // ── Footer references ─────────────────────────────────────
    const footerSection = footerRefs.length
      ? '<hr>' + footerRefs.map(r => `<p>${r}</p>`).join('') : '';

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${name} Report - ${state.participant}</title>
  <style>${css}</style>
</head>
<body>
  <h1>${name}</h1>
  ${citation ? `<p><span class="citation">${citation}</span></p>` : ''}
  <p>Participant: <strong>${state.participant}</strong></p>
  <p>Test Date: <strong>${ts}</strong></p>
  <hr>
  <div class="summary">
    <h2>Summary</h2>
    <p><strong>Completion Time:</strong> ${elapsedMin} minutes</p>
    ${description ? `<p>${description}</p>` : ''}
  </div>
  ${dimScoresSection}
  ${computedSection}
  ${responsesSection}
  ${dataFilesSection}
  ${paramsSection}
  ${footerSection}
  <hr>
  <p style="font-size:0.85em;color:#888;text-align:center;">
    Scale administered via <a href="https://openscales.net" target="_blank">OpenScales</a>.
    Run on desktop using <a href="http://pebl.sf.net" target="_blank">PEBL</a>
    | Run online via <a href="http://peblhub.online" target="_blank">PEBLHub</a>.
  </p>
</body>
</html>`;
  }

  // ============================================================
  // PUBLIC API
  // ============================================================

  return { mount, VERSION };

})();

// Make available as module export and as global
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ScaleRunner;
}

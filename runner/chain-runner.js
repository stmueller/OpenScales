/**
 * OpenScales Chain Runner v0.1
 *
 * Loads an .osc (Open Scale Chain) file and executes the study session:
 * consent gates, scale administration, branching, messages, redirects.
 *
 * Depends on: scale-runner.js (ScaleRunner.mount)
 *
 * Usage:
 *   ChainRunner.start(containerElement, {
 *     oscURL: 'study.osc',         // URL to .osc file (required)
 *     urlParams: URLSearchParams,   // from the page URL
 *   });
 */

const ChainRunner = (() => {
  'use strict';

  const VERSION = '0.1.0';

  // ============================================================
  // PARAMETER RESOLUTION
  // ============================================================

  /**
   * Resolve all parameters from the .osc definition + URL.
   */
  function resolveParameters(paramDefs, urlParams) {
    const resolved = {};

    for (const [name, def] of Object.entries(paramDefs || {})) {
      switch (def.source) {
        case 'url':
          resolved[name] = urlParams.get(name) || def.default || '';
          if (def.required && !resolved[name]) {
            throw new Error(`Required parameter "${name}" is missing from URL.`);
          }
          break;
        case 'random':
          if (Array.isArray(def.values) && def.values.length > 0) {
            resolved[name] = def.values[Math.floor(Math.random() * def.values.length)];
          }
          break;
        case 'auto':
          if (def.type === 'iso8601') {
            resolved[name] = new Date().toISOString();
          } else if (def.type === 'uuid') {
            resolved[name] = crypto.randomUUID ? crypto.randomUUID()
              : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
                  const r = Math.random() * 16 | 0;
                  return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
                });
          }
          break;
        case 'fixed':
          resolved[name] = def.value || '';
          break;
        default:
          resolved[name] = def.default || '';
      }
    }

    // Also capture any URL params starting with param_ as pass-through
    for (const [k, v] of urlParams.entries()) {
      if (k.startsWith('param_') && !(k.slice(6) in resolved)) {
        resolved[k.slice(6)] = v;
      }
    }

    return resolved;
  }

  /**
   * Substitute ${name} placeholders in a string with parameter values.
   * Values are URI-encoded when substituted into URLs.
   */
  function substituteParams(template, params, isURL) {
    if (!template) return template;
    return template.replace(/\$\{(\w+)\}/g, (match, name) => {
      const val = params[name] !== undefined ? String(params[name]) : match;
      return isURL ? encodeURIComponent(val) : val;
    });
  }

  // ============================================================
  // CHAIN FLATTENING (resolve branches into a linear step list)
  // ============================================================

  /**
   * Flatten the chain by resolving branch steps into their selected arms.
   * Also applies random_group shuffling.
   */
  function flattenChain(chain, params) {
    const flat = [];

    for (const step of chain) {
      if (step.type === 'branch') {
        const branchVal = substituteParams(step.on, params, false);
        const arm = step.arms[branchVal] || step.default || [];
        // Recursively flatten the selected arm (arms can contain branches)
        flat.push(...flattenChain(arm, params));
      } else {
        flat.push(step);
      }
    }

    // Apply random_group shuffling
    return shuffleGroups(flat);
  }

  /**
   * Shuffle steps within the same random_group, preserving fixed-position steps.
   */
  function shuffleGroups(steps) {
    // Collect groups
    const groups = {};
    for (let i = 0; i < steps.length; i++) {
      const g = steps[i].random_group;
      if (g && g > 0) {
        if (!groups[g]) groups[g] = [];
        groups[g].push(i);
      }
    }

    // Fisher-Yates shuffle within each group
    const result = [...steps];
    for (const indices of Object.values(groups)) {
      const values = indices.map(i => result[i]);
      for (let i = values.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [values[i], values[j]] = [values[j], values[i]];
      }
      indices.forEach((idx, k) => { result[idx] = values[k]; });
    }

    return result;
  }

  // ============================================================
  // DATA UPLOAD
  // ============================================================

  /**
   * Upload a single file (CSV or JSON) to the data endpoint.
   */
  async function uploadFile(endpoint, filename, content, contentType, headers) {
    if (!endpoint) return { ok: true, local: true };

    const fd = new FormData();
    const blob = new Blob([content], { type: contentType });
    fd.append('data', blob, filename);

    // Add extra headers as form fields (some endpoints read from POST body)
    const fetchHeaders = {};
    for (const [k, v] of Object.entries(headers || {})) {
      fetchHeaders[k] = v;
    }

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: fetchHeaders,
        body: fd,
      });
      return { ok: res.ok, status: res.status };
    } catch (err) {
      console.error('Upload failed:', err);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Upload scale data via the existing collect.php interface.
   */
  async function uploadScaleData(dataConfig, params, scaleCode, scaleData) {
    if (!dataConfig || !dataConfig.endpoint) return;

    const endpoint = substituteParams(dataConfig.endpoint, params, true);

    const fd = new FormData();
    fd.append('participant', params.pid || params.participant || 'unknown');
    fd.append('scale', scaleCode);
    fd.append('version', VERSION);

    // Individual CSV
    if (scaleData.csvLines && scaleData.csvLines.length > 0) {
      const csvContent = scaleData.csvLines.join('\n');
      const filename = substituteParams(
        dataConfig.filename_pattern || '${scale_code}_${pid}.csv',
        { ...params, scale_code: scaleCode },
        false
      );
      const blob = new Blob([csvContent], { type: 'text/csv' });
      fd.append('data', blob, filename);
    }

    // Pooled line
    if (scaleData.pooledLine) {
      fd.append('pooled', scaleData.pooledLine);
    }
    if (scaleData.pooledHdr) {
      fd.append('pooled_header', scaleData.pooledHdr);
    }

    // Extra headers
    const fetchHeaders = {};
    for (const [k, v] of Object.entries(dataConfig.headers || {})) {
      fetchHeaders[k] = substituteParams(v, params, false);
    }

    try {
      const res = await fetch(endpoint, {
        method: dataConfig.method || 'POST',
        headers: fetchHeaders,
        body: fd,
      });

      // Upload report HTML (separate POST, same as scale-runner.js)
      if (scaleData.reportHTML) {
        try {
          const fd2 = new FormData();
          const pid = params.pid || params.participant || 'unknown';
          const rptFilename = `${scaleCode}-${pid}-report.html`;
          fd2.append('data', new Blob([scaleData.reportHTML], { type: 'text/html' }), rptFilename);
          fd2.append('participant', pid);
          fd2.append('scale', scaleCode);
          await fetch(endpoint, { method: 'POST', headers: fetchHeaders, body: fd2 });
        } catch (_) { /* report upload failure is non-fatal */ }
      }

      return { ok: res.ok, status: res.status };
    } catch (err) {
      console.error(`Upload failed for ${scaleCode}:`, err);
      return { ok: false, error: err.message };
    }
  }

  // ============================================================
  // SESSION LOG
  // ============================================================

  function createSessionLog(osc, params) {
    return {
      osc_version: osc.osc_version,
      study_code: osc.study_info?.code || '',
      study_name: osc.study_info?.name || '',
      pid: params.pid || params.participant || '',
      condition: params.condition || '',
      parameters: { ...params },
      session_start: new Date().toISOString(),
      session_end: null,
      steps: [],
    };
  }

  function logStep(sessionLog, stepInfo) {
    sessionLog.steps.push(stepInfo);
  }

  // ============================================================
  // STEP EXECUTORS
  // ============================================================

  /**
   * Show a message step.
   */
  function executeMessage(container, step) {
    return new Promise(resolve => {
      container.innerHTML = '';

      const wrapper = document.createElement('div');
      wrapper.className = 'chain-message';
      wrapper.style.cssText = 'max-width:700px;margin:4rem auto;padding:2rem;';

      if (step.title) {
        const h2 = document.createElement('h2');
        h2.textContent = step.title;
        wrapper.appendChild(h2);
      }

      const p = document.createElement('div');
      p.innerHTML = step.text || '';
      wrapper.appendChild(p);

      const btn = document.createElement('button');
      btn.textContent = step.button || 'Continue';
      btn.className = 'chain-btn';
      btn.style.cssText = 'margin-top:1.5rem;padding:0.7rem 2rem;font-size:1rem;' +
        'background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;';
      btn.onclick = () => resolve('completed');
      wrapper.appendChild(btn);

      container.appendChild(wrapper);
    });
  }

  /**
   * Add a "Continue" button to the current debrief/completion page.
   * Returns a promise that resolves when the user clicks it.
   */
  function waitForContinue(container) {
    return new Promise(resolve => {
      const btn = document.createElement('button');
      btn.textContent = 'Continue';
      btn.className = 'chain-continue-btn';
      btn.style.cssText = 'display:block;margin:1.5rem auto;padding:0.7rem 2.5rem;font-size:1rem;' +
        'background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;';
      btn.onclick = () => resolve();

      // Append to the last major div in the container (the debrief area)
      const target = container.querySelector('.sr-debrief') ||
                     container.querySelector('.sr-main') ||
                     container;
      target.appendChild(btn);

      // Scroll button into view
      btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  /**
   * Execute a consent step — runs the OSD scale, checks the consent item.
   */
  function executeConsent(container, step, params, oscBaseURL) {
    return new Promise((resolve, reject) => {
      container.innerHTML = '';

      const osdURL = resolveOsdURL(step.osd, oscBaseURL);

      ScaleRunner.mount(container, {
        osdURL: osdURL,
        participant: params.pid || params.participant || 'anon',
        language: params.lang || 'en',
        collectURL: null,   // chain runner handles upload
        demo: false,
        showTitle: false,
        params: step.parameters || {},

        onComplete: async function (detail) {
          // Check consent item
          const responses = detail.responses || {};
          const state = container._scaleData?.state;
          const responseMap = state?.responseMap || {};
          const actualResponse = responses[step.consent_item] || responseMap[step.consent_item];

          const consented = String(actualResponse) === String(step.consent_value);

          // For consent, don't show continue button — advance immediately
          resolve({
            outcome: consented ? 'consented' : 'declined',
            scaleData: container._scaleData || null,
          });
        }
      });
    });
  }

  /**
   * Execute a scale step — runs the OSD scale, returns data on completion.
   */
  function executeScale(container, step, params, oscBaseURL) {
    return new Promise((resolve, reject) => {
      container.innerHTML = '';

      const osdURL = resolveOsdURL(step.osd, oscBaseURL);
      const scaleParams = { ...(step.parameters || {}) };

      ScaleRunner.mount(container, {
        osdURL: osdURL,
        participant: params.pid || params.participant || 'anon',
        language: params.lang || scaleParams.lang || 'en',
        collectURL: null,   // chain runner handles upload
        demo: false,
        showTitle: true,
        params: scaleParams,

        onComplete: async function (detail) {
          const result = {
            outcome: detail.status || 'completed',
            scores: detail.scores || {},
            computed: detail.computed || {},
            scaleData: container._scaleData || null,
            scaleCode: detail.scale || step.osd.replace(/\.osd$/i, '').split('/').pop(),
          };

          // Wait for user to click Continue before advancing
          await waitForContinue(container);
          resolve(result);
        }
      });
    });
  }

  /**
   * Resolve an OSD path relative to the .osc file's URL.
   */
  function resolveOsdURL(osdRef, oscBaseURL) {
    if (!osdRef) return '';
    // Absolute URL
    if (/^https?:\/\//i.test(osdRef)) return osdRef;
    // Relative to .osc location
    return oscBaseURL + '/' + osdRef;
  }

  // ============================================================
  // MAIN CHAIN EXECUTOR
  // ============================================================

  async function start(container, config) {
    const { oscURL, urlParams } = config;

    if (!oscURL) {
      container.innerHTML = '<div style="padding:2rem;color:#dc2626;">' +
        '<h2>Configuration Error</h2>' +
        '<p>An <code>osc</code> parameter pointing to an .osc chain file is required.</p></div>';
      return;
    }

    // Show loading
    container.innerHTML = '<div style="padding:3rem;text-align:center;color:#6b7280;">' +
      'Loading study...</div>';

    // Fetch .osc file
    let osc;
    try {
      const res = await fetch(oscURL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      osc = await res.json();
    } catch (err) {
      container.innerHTML = `<div style="padding:2rem;color:#dc2626;">` +
        `<h2>Error Loading Study</h2>` +
        `<p>Could not load <code>${oscURL}</code>: ${err.message}</p></div>`;
      return;
    }

    // Base URL for resolving relative .osd paths
    const oscBaseURL = oscURL.substring(0, oscURL.lastIndexOf('/'));

    // Resolve parameters
    let params;
    try {
      params = resolveParameters(osc.parameters, urlParams || new URLSearchParams());
    } catch (err) {
      container.innerHTML = `<div style="padding:2rem;color:#dc2626;">` +
        `<h2>Missing Required Parameter</h2>` +
        `<p>${err.message}</p>` +
        `<p>Add the parameter to the URL, e.g.: <code>?pid=P001</code></p></div>`;
      return;
    }

    // Add study-level params
    params.study_code = osc.study_info?.code || '';
    params.timestamp = params.timestamp || new Date().toISOString();

    // Flatten chain (resolve branches, shuffle random_groups)
    const steps = flattenChain(osc.chain || [], params);

    // Session log
    const sessionLog = createSessionLog(osc, params);

    // Data config
    const dataConfig = osc.data || {};

    // Execute steps sequentially
    let stepNum = 0;
    for (const step of steps) {
      stepNum++;
      const stepStart = new Date().toISOString();

      switch (step.type) {

        case 'consent': {
          const result = await executeConsent(container, step, params, oscBaseURL);

          logStep(sessionLog, {
            step: stepNum,
            type: 'consent',
            scale_code: step.osd?.replace(/\.osd$/i, '').split('/').pop() || 'consent',
            started: stepStart,
            completed: new Date().toISOString(),
            outcome: result.outcome,
          });

          // Upload consent data
          if (result.scaleData && dataConfig.endpoint) {
            const code = step.osd?.replace(/\.osd$/i, '').split('/').pop() || 'Consent';
            await uploadScaleData(dataConfig, params, code, result.scaleData);
          }

          if (result.outcome === 'declined') {
            // Handle decline
            if (step.on_decline === 'end' || !step.on_decline) {
              container.innerHTML = '<div style="max-width:600px;margin:4rem auto;padding:2rem;text-align:center;">' +
                '<h2>Thank you</h2>' +
                '<p>You have chosen not to participate. You may close this window.</p></div>';
              sessionLog.session_end = new Date().toISOString();
              if (dataConfig.session_log !== false) {
                await uploadSessionLog(dataConfig, params, sessionLog);
              }
              return;
            }
            // If on_decline is 'skip', continue to next step
          }
          break;
        }

        case 'scale': {
          const result = await executeScale(container, step, params, oscBaseURL);

          logStep(sessionLog, {
            step: stepNum,
            type: 'scale',
            scale_code: result.scaleCode,
            started: stepStart,
            completed: new Date().toISOString(),
            outcome: result.outcome,
          });

          // Upload scale data
          if (result.scaleData && dataConfig.endpoint) {
            await uploadScaleData(dataConfig, params, result.scaleCode, result.scaleData);
          }
          break;
        }

        case 'message': {
          const paramStep = {
            ...step,
            title: substituteParams(step.title, params, false),
            text: substituteParams(step.text, params, false),
          };
          const outcome = await executeMessage(container, paramStep);

          logStep(sessionLog, {
            step: stepNum,
            type: 'message',
            started: stepStart,
            completed: new Date().toISOString(),
            outcome,
          });
          break;
        }

        case 'redirect': {
          logStep(sessionLog, {
            step: stepNum,
            type: 'redirect',
            url: substituteParams(step.url, params, true),
            started: stepStart,
            completed: new Date().toISOString(),
            outcome: 'redirected',
          });

          // Finalize session log before redirect
          sessionLog.session_end = new Date().toISOString();
          if (dataConfig.session_log !== false) {
            await uploadSessionLog(dataConfig, params, sessionLog);
          }

          const redirectURL = substituteParams(step.url, params, true);
          const delay = (step.delay || 0) * 1000;

          if (step.message || delay > 0) {
            container.innerHTML = '<div style="max-width:600px;margin:4rem auto;padding:2rem;text-align:center;">' +
              `<p>${substituteParams(step.message || 'Redirecting...', params, false)}</p></div>`;
          }

          setTimeout(() => {
            window.location.href = redirectURL;
          }, delay);
          return; // End chain execution
        }

        default:
          console.warn(`Unknown step type: ${step.type}`);
      }
    }

    // Chain complete (no redirect step)
    sessionLog.session_end = new Date().toISOString();
    if (dataConfig.session_log !== false) {
      await uploadSessionLog(dataConfig, params, sessionLog);
    }

    // Show completion
    container.innerHTML = '<div style="max-width:600px;margin:4rem auto;padding:2rem;text-align:center;">' +
      '<h2>Study Complete</h2>' +
      '<p>Thank you for your participation. You may close this window.</p></div>';
  }

  /**
   * Upload the session log JSON.
   */
  async function uploadSessionLog(dataConfig, params, sessionLog) {
    if (!dataConfig.endpoint) return;

    const endpoint = substituteParams(dataConfig.endpoint, params, true);
    const filename = substituteParams(
      dataConfig.session_log_filename || 'session_${pid}_${timestamp}.json',
      { ...params, timestamp: new Date().toISOString().replace(/[:.]/g, '-') },
      false
    );

    const content = JSON.stringify(sessionLog, null, 2);

    const fd = new FormData();
    fd.append('participant', params.pid || params.participant || 'unknown');
    fd.append('scale', '_session');
    fd.append('data', new Blob([content], { type: 'application/json' }), filename);

    const fetchHeaders = {};
    for (const [k, v] of Object.entries(dataConfig.headers || {})) {
      fetchHeaders[k] = substituteParams(v, params, false);
    }

    try {
      await fetch(endpoint, {
        method: dataConfig.method || 'POST',
        headers: fetchHeaders,
        body: fd,
      });
    } catch (err) {
      console.error('Session log upload failed:', err);
    }
  }

  // ============================================================
  // PUBLIC API
  // ============================================================

  return { start, VERSION };

})();

if (typeof module !== 'undefined' && module.exports) {
  module.exports = ChainRunner;
}

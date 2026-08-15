/* Abaqus Agent — i18n engine, shared by / and /workbench.
 *
 * Chinese is the default and stays the better-tended language: the users this
 * is built for are Chinese-speaking simulation engineers, and English is the
 * alternative, not the source. So `zh` is the fallback chain's last stop and a
 * missing English string shows the Chinese one rather than a raw key — a UI
 * that reads `nav.workbench` is worse than one that reads 工作台.
 *
 * Both pages are single-file and framework-free, so the catalogue lives inline
 * in each page (register() merges) and only the engine is shared. Same split
 * as design-system.css: tokens shared, markup local.
 *
 * Missing lookups are recorded rather than swallowed; scripts/run_i18n_ui_check.py
 * drives the real UI and asserts the record is empty, which is what keeps "we
 * support English" from meaning "70% of it is English". The static check can
 * only count strings — it cannot see a panel that never re-renders, or a
 * render function that throws, and both of those happened.
 *
 * Each page also carries a small stand-in for this engine, used only if this
 * file fails to load. Losing the language switch is a fair degradation;
 * losing every event handler on the page because a <script> 404'd is not.
 */
(function (global) {
  'use strict';

  var STORE_KEY = 'abaqus-agent-lang';
  var SUPPORTED = ['zh', 'en'];
  var FALLBACK = 'zh';

  var dicts = { zh: {}, en: {} };
  var missing = Object.create(null);
  var listeners = [];
  var current = null;

  function detect() {
    var stored = null;
    try { stored = global.localStorage.getItem(STORE_KEY); } catch (e) { /* private mode */ }
    if (SUPPORTED.indexOf(stored) >= 0) return stored;
    var nav = (global.navigator && (global.navigator.language || global.navigator.userLanguage)) || '';
    return nav.toLowerCase().indexOf('zh') === 0 ? 'zh' : 'en';
  }

  function interpolate(text, params) {
    if (!params) return text;
    return text.replace(/\{(\w+)\}/g, function (whole, name) {
      return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : whole;
    });
  }

  function lookup(key) {
    var hit = dicts[current] && dicts[current][key];
    if (typeof hit === 'string') return hit;
    // Record against the language that was actually asked for, so the check
    // can say "English is 12 strings short" instead of just "something missing".
    missing[current + '::' + key] = true;
    var fall = dicts[FALLBACK] && dicts[FALLBACK][key];
    return typeof fall === 'string' ? fall : key;
  }

  function t(key, params) {
    return interpolate(lookup(key), params);
  }

  function register(catalogue) {
    SUPPORTED.forEach(function (lang) {
      var block = catalogue && catalogue[lang];
      if (!block) return;
      Object.keys(block).forEach(function (key) { dicts[lang][key] = block[key]; });
    });
    if (current) apply();
  }

  /* Never overwrite text this engine did not write.
   *
   * data-i18n marks *placeholder* copy — an empty-state line, a button's idle
   * label. Runtime code then writes over some of those nodes with things that
   * are not translatable copy at all: an Evidence report, a Solver Doctor
   * report, "⟳ Running…" on a button that is still mid-request, a settings
   * badge that says the API key IS configured. A naive apply() re-stamps the
   * placeholder onto all of them on every language switch, so switching
   * language silently destroyed a solve report and told a user with a
   * configured key that it was unset — in green, because the class had not
   * changed.
   *
   * So: remember what we wrote. If the node no longer says it, someone else
   * owns that node now and we leave it alone. Code that wants the node back
   * under management calls I18N.reclaim(el).
   */
  function applyText(el) {
    var key = el.getAttribute('data-i18n');
    var previous = el.__i18nWrote;
    if (previous !== undefined && el.textContent !== previous) return;
    var next = t(key);
    el.textContent = next;
    el.__i18nWrote = next;
  }

  function reclaim(el) {
    if (el) delete el.__i18nWrote;
  }

  function apply(root) {
    var scope = root || global.document;
    if (!scope || !scope.querySelectorAll) return;

    scope.querySelectorAll('[data-i18n]').forEach(applyText);

    // "placeholder:spec.prompt, title:nav.workbench.hint"
    scope.querySelectorAll('[data-i18n-attr]').forEach(function (el) {
      el.getAttribute('data-i18n-attr').split(',').forEach(function (pair) {
        var bits = pair.split(':');
        if (bits.length !== 2) return;
        el.setAttribute(bits[0].trim(), t(bits[1].trim()));
      });
    });

    if (scope === global.document && scope.documentElement) {
      scope.documentElement.setAttribute('lang', current === 'zh' ? 'zh-CN' : 'en');
      scope.querySelectorAll('[data-i18n-title]').forEach(function (el) {
        global.document.title = t(el.getAttribute('data-i18n-title'));
      });
    }
  }

  function setLang(lang) {
    if (SUPPORTED.indexOf(lang) < 0 || lang === current) return;
    current = lang;
    try { global.localStorage.setItem(STORE_KEY, lang); } catch (e) { /* private mode */ }
    apply();
    listeners.forEach(function (fn) { try { fn(lang); } catch (e) { console.error(e); } });
    global.document.dispatchEvent(new CustomEvent('i18n:change', { detail: { lang: lang } }));
  }

  function toggle() { setLang(current === 'zh' ? 'en' : 'zh'); }

  var I18N = {
    t: t,
    register: register,
    apply: apply,
    reclaim: reclaim,
    setLang: setLang,
    toggle: toggle,
    supported: SUPPORTED.slice(),
    onChange: function (fn) { listeners.push(fn); },
    // Read by scripts/run_i18n_ui_check.py. Keys look like "en::nav.workbench".
    missingKeys: function () { return Object.keys(missing); },
    resetMissing: function () { missing = Object.create(null); }
  };
  Object.defineProperty(I18N, 'lang', { get: function () { return current; } });

  current = detect();
  global.I18N = I18N;

  if (global.document) {
    if (global.document.readyState === 'loading') {
      global.document.addEventListener('DOMContentLoaded', function () { apply(); });
    } else {
      apply();
    }
  }
})(window);

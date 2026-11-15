/* Display preferences: text size (A− / A+) and high contrast.
   Sets data-fs and data-contrast on <html>; style.css turns them into --fs and the high-contrast tokens.
   With no saved choice, high contrast follows the system setting (prefers-contrast: more). */
(() => {
  'use strict';
  const SIZES = [1, 1.15, 1.3, 1.5];
  const KEY_FS = 'hac-fs', KEY_CONTRAST = 'hac-contrast';
  const root = document.documentElement;
  const read = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const save = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked: choice lasts this visit */ } };
  const systemHigh = matchMedia('(prefers-contrast: more)');

  let fs = Math.min(SIZES.length - 1, Math.max(0, parseInt(read(KEY_FS), 10) || 0));
  let contrast = read(KEY_CONTRAST);          // 'high', 'normal' or null (follow the system)

  const $ = id => document.getElementById(id);
  const isHigh = () => (contrast ? contrast === 'high' : systemHigh.matches);

  function render() {
    root.dataset.fs = String(fs);
    root.style.setProperty('--fs', String(SIZES[fs]));
    if (contrast) root.dataset.contrast = contrast; else delete root.dataset.contrast;
    $('fs-down').disabled = fs === 0;
    $('fs-up').disabled = fs === SIZES.length - 1;
    $('contrast').setAttribute('aria-pressed', String(isHigh()));
    const size = I18N.t('a11y.size', { p: Math.round(SIZES[fs] * 100) });
    $('fs-down').title = `${I18N.t('a11y.smaller')} (${size})`;
    $('fs-up').title = `${I18N.t('a11y.larger')} (${size})`;
    $('contrast').title = I18N.t('a11y.contrast');
    // the map measures its box, so let it refit after the text size changes the layout
    window.dispatchEvent(new Event('resize'));
  }

  function setSize(next) { fs = Math.min(SIZES.length - 1, Math.max(0, next)); save(KEY_FS, String(fs)); render(); }

  $('fs-down').addEventListener('click', () => setSize(fs - 1));
  $('fs-up').addEventListener('click', () => setSize(fs + 1));
  $('contrast').addEventListener('click', () => { contrast = isHigh() ? 'normal' : 'high'; save(KEY_CONTRAST, contrast); render(); });
  systemHigh.addEventListener('change', () => { if (!contrast) render(); });
  I18N.onChange(render);
  render();
})();

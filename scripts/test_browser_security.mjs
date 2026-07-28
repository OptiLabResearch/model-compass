import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const context = {
  URL,
  Set,
  document: { readyState: 'loading', addEventListener() {} },
  location: { origin: 'https://models.optiqo.dev', pathname: '/' },
  window: {},
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('public/assets/nav.js', 'utf8'), context);

const { escapeHtml, safeUrl } = context.ModelCompassNav;
assert.equal(escapeHtml('<img src=x onerror=alert(1)>'), '&lt;img src=x onerror=alert(1)&gt;');
assert.equal(safeUrl('javascript:alert(1)', '#'), '#');
assert.equal(safeUrl('data:text/html,boom', '#'), '#');
assert.equal(safeUrl('//evil.example/x', '#'), '#');
assert.equal(safeUrl('///evil.example/x', '#'), '#');
assert.equal(safeUrl('/\\evil.example/x', '#'), '#');
assert.equal(safeUrl('https://evil.example/x', '#'), '#');
assert.equal(safeUrl('https://artificialanalysis.ai/models/test', '#'), 'https://artificialanalysis.ai/models/test');
assert.equal(safeUrl('./index.html', '#'), '/index.html');
console.log('Browser security helpers passed');

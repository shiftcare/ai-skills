import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const script = execFileSync(fileURLToPath(new URL('../.venv/bin/python', import.meta.url)),
  ['-c', 'from report import SCRIPT; print(SCRIPT)'],
  { cwd: new URL('..', import.meta.url), encoding: 'utf8' });

function reportPage(hash) {
  const nodes = new Map();
  function node(id, parent = null, dataset = {}, tagName = 'DIV') {
    const element = Object.assign(new EventTarget(), {
      id, parent, dataset, tagName, hidden: true, open: false,
      classList: { toggle() {} },
      closest(selector) {
        for (let current = this; current; current = current.parent) {
          if (selector === '[data-case-panel]' && current.dataset.casePanel) return current;
        }
        return null;
      },
      querySelector(selector) {
        return [...nodes.values()].find((child) => {
          if (selector !== '[data-case]' || !child.dataset.case) return false;
          for (let current = child.parent; current; current = current.parent) {
            if (current === this) return true;
          }
          return false;
        }) ?? null;
      },
      scrollIntoView() { this.scrolled = true; },
    });
    nodes.set(id, element);
    return element;
  }
  for (const view of ['overview', 'results', 'case']) {
    node(view + '-view').hidden = view !== 'overview';
    node(view + '-tab');
  }
  const suite = node('suite-s1', null, {}, 'DETAILS');
  for (let index = 1; index <= 2; index++) {
    const navigation = node('case-c' + index, suite, {}, 'DETAILS');
    node('case-button-' + index, navigation, { case: 'C' + index });
    const panel = node('case-panel-c' + index, null, { casePanel: 'C' + index });
    node('result-r' + index, panel, {}, 'DETAILS');
  }
  const document = {
    getElementById: (id) => nodes.get(id) ?? null,
    querySelectorAll: (selector) => [...nodes.values()].filter((element) =>
      selector === '[data-case-panel]' ? element.dataset.casePanel :
      selector === '[data-case]' ? element.dataset.case : false),
    querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; },
  };
  const window = new EventTarget();
  const location = { hash };
  runInNewContext(script, { document, window, location });
  return { nodes, navigate(nextHash) {
    location.hash = nextHash;
    window.dispatchEvent(new Event('hashchange'));
  } };
}

test('loading a result fragment selects its case and opens the result', () => {
  const { nodes } = reportPage('#result-r2');
  assert.equal(nodes.get('case-view').hidden, false);
  assert.equal(nodes.get('overview-view').hidden, true);
  assert.equal(nodes.get('case-panel-c1').hidden, true);
  assert.equal(nodes.get('case-panel-c2').hidden, false);
  assert.equal(nodes.get('result-r2').open, true);
});

test('hash navigation restores result, case, and suite targets', () => {
  const { nodes, navigate } = reportPage('');
  assert.equal(nodes.get('overview-view').hidden, false);
  navigate('#result-r2');
  assert.equal(nodes.get('case-panel-c2').hidden, false);
  assert.equal(nodes.get('result-r2').open, true);
  navigate('#result-r1');
  assert.equal(nodes.get('case-panel-c2').hidden, true);
  assert.equal(nodes.get('case-panel-c1').hidden, false);
  assert.equal(nodes.get('result-r1').open, true);
  navigate('#case-c2');
  assert.equal(nodes.get('case-panel-c2').hidden, false);
  navigate('#suite-s1');
  assert.equal(nodes.get('case-panel-c1').hidden, false);
  assert.doesNotThrow(() => navigate('#invented-unknown-fragment'));
});

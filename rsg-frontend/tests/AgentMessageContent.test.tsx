import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// The normalization is independent of React/CSS so tests can run in Node.
import { normalizeAgentMarkdown } from '../src/components/agentMarkdown';

function render(text: string) {
  return renderToStaticMarkup(<ReactMarkdown remarkPlugins={[remarkGfm]}>{normalizeAgentMarkdown(text)}</ReactMarkdown>);
}

test('renders the reported revenue answer with bold and a real table', () => {
  const html = render('Products contributing at least **15%**:\n\n| Product | Revenue | Share |\n|---|---:|---:|\n| Monitor | 473,000 | 32.87% |\n| Desk | 222,500 | 15.46% |');
  assert.match(html, /<strong>15%<\/strong>/);
  assert.match(html, /<table>/);
  assert.match(html, /<td>Monitor<\/td>/);
  assert.match(html, /text-align:right/);
  assert.doesNotMatch(html, /\*\*15%\*\*/);
});

test('renders headings, nested lists, inline code and fenced SQL', () => {
  const html=render('### Revenue\n\n- **Monitor**\n  - Completed only\n\nUse `SUM`.\n\n```sql\nSELECT * FROM sales;\n```');
  assert.match(html, /<h3>Revenue<\/h3>/);
  assert.equal((html.match(/<ul>/g)??[]).length, 2);
  assert.match(html, /<code>SUM<\/code>/);
  assert.match(html, /<pre><code class="language-sql">SELECT \* FROM sales;/);
});

test('repairs missing and mismatched table separator rows', () => {
  assert.match(render('| Product | Revenue |\n| Monitor | 473000 |'), /<table>/);
  assert.match(render('| Product | Revenue |\n|---|\n| Monitor | 473000 |'), /<table>/);
});

test('keeps prose following a table outside the table', () => {
  const html=render('Results:\n| Product | Revenue |\n|---|---|\n| Desk | 222500 |\nOnly qualifying products.');
  assert.match(html, /<\/table>\n<p>Only qualifying products\.<\/p>/);
});

test('never rewrites table-like content inside code fences', () => {
  const source='````text\n| a | b |\n| 1 | 2 |\n```\nkeep this inside the longer fence\n````';
  assert.equal(normalizeAgentMarkdown(source),source);
  assert.doesNotMatch(render(source),/<table>/);
});

test('unwraps an entire markdown wrapper but preserves SQL wrappers', () => {
  assert.match(render('```markdown\n**Revenue**\n```'), /<strong>Revenue<\/strong>/);
  assert.match(render('```sql\nSELECT 1\n```'), /language-sql/);
});

test('HTML and unsafe links cannot execute', () => {
  const html=render('<script>alert(1)</script>\n\n[click](javascript:alert%281%29)');
  assert.doesNotMatch(html, /<script>|href="javascript:/);
  assert.match(html, /&lt;script&gt;/);
});

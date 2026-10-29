/** Repair agent tables outside code fences without interpreting raw HTML. */
export function normalizeAgentMarkdown(text: string): string {
  let source = text.replace(/\r\n?|\u2028|\u2029/g, '\n');
  const wrapped = source.trim().match(/^(`{3,}|~{3,})(?:markdown|md)\s*\n([\s\S]*?)\n\1\s*$/i);
  if (wrapped) source = wrapped[2];

  const lines = source.split('\n');
  const output: string[] = [];
  let fence: { marker: string; length: number } | null = null;
  const isRow = (line: string) => /^\s*\|/.test(line);
  const separator = (line: string) => /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(line);
  const cells = (line: string) => line.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '').split(/(?<!\\)\|/).length;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (marker) {
      if (!fence) fence = { marker: marker[1][0], length: marker[1].length };
      else if (marker[1][0] === fence.marker && marker[1].length >= fence.length && !marker[2].trim()) fence = null;
      output.push(line);
      continue;
    }
    if (fence || !isRow(line)) {
      output.push(line);
      continue;
    }
    const rows = [line];
    while (i + 1 < lines.length && isRow(lines[i + 1])) rows.push(lines[++i]);
    if (rows.length > 1) {
      const rule = '|' + ' --- |'.repeat(cells(rows[0]));
      if (!separator(rows[1])) rows.splice(1, 0, rule);
      else if (cells(rows[1]) !== cells(rows[0])) rows[1] = rule;
      if (output.length && output[output.length - 1].trim()) output.push('');
    }
    output.push(...rows);
    if (rows.length > 1 && i + 1 < lines.length && lines[i + 1].trim()) output.push('');
  }
  return output.join('\n');
}


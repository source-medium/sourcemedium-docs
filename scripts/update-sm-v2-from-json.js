const fs = require('fs');
const path = require('path');

const JSON_PATH = path.join(__dirname, '..', 'yaml-files', 'latest-v2-schemas-10-20-25.json');
const TABLES_DIR = path.join(__dirname, '..', 'data-activation', 'data-tables', 'sm_transformed_v2');

function loadLatest() {
  const raw = fs.readFileSync(JSON_PATH, 'utf8');
  const rows = JSON.parse(raw);
  const byTable = new Map();
  for (const r of rows) {
    if (!r || r.dataset_name !== 'sm_transformed_v2') continue;
    const t = r.table_name;
    if (!byTable.has(t)) byTable.set(t, { table: t, table_type: r.table_type || '', description: r.table_description || '', columns: new Map() });
    const entry = byTable.get(t);
    // Update table description with the most recent non-empty value
    if (r.table_description && r.table_description.trim()) {
      entry.description = r.table_description.trim();
    }
    const col = r.column_name;
    if (!col) continue;
    const cdesc = (r.column_description || '').trim();
    if (!entry.columns.has(col)) {
      entry.columns.set(col, cdesc);
    } else if (cdesc) {
      entry.columns.set(col, cdesc);
    }
  }
  return byTable;
}

function yamlEscapeFolded(text) {
  // Keep text as-is; folded style handles most characters fine.
  return text.replace(/\r\n/g, '\n');
}

function generateYaml(table, description, columns) {
  const lines = [];
  lines.push('```yaml');
  lines.push('version: 2');
  lines.push('');
  lines.push('models:');
  lines.push(`  - name: ${table}`);
  lines.push('    description: >');
  const descLines = yamlEscapeFolded(description || '').split('\n');
  if (descLines.length === 0 || (descLines.length === 1 && descLines[0] === '')) {
    lines.push('      ');
  } else {
    for (const dl of descLines) {
      lines.push(`      ${dl}`);
    }
  }
  lines.push('    columns:');
  const sorted = Array.from(columns.keys()).sort((a, b) => a.localeCompare(b));
  for (const col of sorted) {
    lines.push(`      - name: ${col}`);
    lines.push('        description: >');
    const cdesc = yamlEscapeFolded(columns.get(col) || '');
    const cdescLines = cdesc.split('\n');
    if (cdescLines.length === 0 || (cdescLines.length === 1 && cdescLines[0] === '')) {
      lines.push('          ');
    } else {
      for (const cl of cdescLines) {
        lines.push(`          ${cl}`);
      }
    }
    lines.push('');
  }
  lines.push('```');
  return lines.join('\n');
}

function updateMdx(filePath, yamlBlock) {
  const original = fs.readFileSync(filePath, 'utf8');
  const start = original.indexOf('```yaml');
  if (start === -1) return false;
  const end = original.indexOf('```', start + 7);
  if (end === -1) return false;
  const before = original.slice(0, start);
  const after = original.slice(end + 3);
  const updated = before + yamlBlock + after;
  fs.writeFileSync(filePath, updated, 'utf8');
  return true;
}

function ensureMdx(filePath, table, description, columns) {
  if (fs.existsSync(filePath)) return false;
  const frontmatter = `---\n` +
    `title: '${table}'\n` +
    `description: ''\n` +
    `---\n\n`;
  const yamlBlock = generateYaml(table, description, columns);
  fs.writeFileSync(filePath, frontmatter + yamlBlock + '\n', 'utf8');
  return true;
}

function shortBlurb(text) {
  if (!text) return '';
  const s = String(text).trim();
  const periodIdx = s.indexOf('.');
  let first = periodIdx > -1 ? s.slice(0, periodIdx + 1) : s;
  if (first.length > 140) first = first.slice(0, 137).trimEnd() + '...';
  return first;
}

function generateIndex(byTable) {
  const groups = {
    'Dimension': [],
    'Fact': [],
    'One Big Table': [],
    'Report': []
  };
  for (const [, v] of byTable) {
    const type = v.table_type || '';
    if (groups[type]) groups[type].push(v);
  }
  for (const k of Object.keys(groups)) groups[k].sort((a, b) => a.table.localeCompare(b.table));

  const lines = [];
  lines.push('---');
  lines.push('title: "SM Transformed v2 Tables"');
  lines.push('description: "Browse all tables in the sm_transformed_v2 schema, grouped by type."');
  lines.push('---');
  lines.push('');
  lines.push('Welcome to the sm_transformed_v2 schema. Use this page to quickly jump to table-level documentation. Tables are grouped by their role in the model for clarity.');
  lines.push('');

  if (groups['Dimension'].length) {
    lines.push('### Dimensions');
    lines.push('<CardGroup cols={2}>');
    for (const v of groups['Dimension']) {
      const t = v.table;
      lines.push(`  <Card title="${t}" href="/data-activation/data-tables/sm_transformed_v2/${t}">`);
      lines.push('    ' + shortBlurb(v.description));
      lines.push('  </Card>');
    }
    lines.push('</CardGroup>');
    lines.push('');
  }

  if (groups['Fact'].length) {
    lines.push('### Facts');
    lines.push('<CardGroup cols={2}>');
    for (const v of groups['Fact']) {
      const t = v.table;
      lines.push(`  <Card title="${t}" href="/data-activation/data-tables/sm_transformed_v2/${t}">`);
      lines.push('    ' + shortBlurb(v.description));
      lines.push('  </Card>');
    }
    lines.push('</CardGroup>');
    lines.push('');
  }

  if (groups['One Big Table'].length) {
    lines.push('### OBT (One Big Table)');
    lines.push('<CardGroup cols={2}>');
    for (const v of groups['One Big Table']) {
      const t = v.table;
      lines.push(`  <Card title="${t}" href="/data-activation/data-tables/sm_transformed_v2/${t}">`);
      lines.push('    ' + shortBlurb(v.description));
      lines.push('  </Card>');
    }
    lines.push('</CardGroup>');
    lines.push('');
  }

  if (groups['Report'].length) {
    lines.push('### Reports');
    lines.push('<CardGroup cols={2}>');
    for (const v of groups['Report']) {
      const t = v.table;
      lines.push(`  <Card title="${t}" href="/data-activation/data-tables/sm_transformed_v2/${t}">`);
      lines.push('    ' + shortBlurb(v.description));
      lines.push('  </Card>');
    }
    lines.push('</CardGroup>');
    lines.push('');
  }

  lines.push('<br/>');
  lines.push('');
  lines.push('Need something else in this index? Ping us and we’ll add it.');
  lines.push('');
  return lines.join('\n');
}

function main() {
  const byTable = loadLatest();
  const mdxFiles = fs.readdirSync(TABLES_DIR).filter(f => f.endsWith('.mdx'));
  const results = [];
  // Update existing MDX files that match JSON tables (skip index.mdx)
  for (const f of mdxFiles) {
    if (f === 'index.mdx') continue;
    const filePath = path.join(TABLES_DIR, f);
    const table = path.basename(f, '.mdx');
    const entry = byTable.get(table);
    if (!entry) {
      results.push({ file: f, status: 'skipped', reason: 'table not found in JSON' });
      continue;
    }
    const yamlBlock = generateYaml(entry.table, entry.description, entry.columns);
    const ok = updateMdx(filePath, yamlBlock);
    results.push({ file: f, status: ok ? 'updated' : 'failed', reason: ok ? '' : 'yaml block not found' });
  }
  // Create missing MDX files for tables present in JSON but not on disk
  for (const [table, entry] of byTable) {
    const fileName = `${table}.mdx`;
    const filePath = path.join(TABLES_DIR, fileName);
    if (!fs.existsSync(filePath)) {
      const created = ensureMdx(filePath, table, entry.description, entry.columns);
      results.push({ file: fileName, status: created ? 'created' : 'error', reason: created ? '' : 'create failed' });
    }
  }
  // Regenerate index from JSON
  const indexMdx = generateIndex(byTable);
  fs.writeFileSync(path.join(TABLES_DIR, 'index.mdx'), indexMdx, 'utf8');

  console.log(JSON.stringify(results, null, 2));
}

if (require.main === module) {
  main();
}

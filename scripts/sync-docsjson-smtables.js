const fs = require('fs');
const path = require('path');

const DOCS_JSON = path.join(__dirname, '..', 'docs.json');
const SCHEMA_JSON = path.join(__dirname, '..', 'yaml-files', 'latest-v2-schemas-10-20-25.json');

function loadJSON(p) { return JSON.parse(fs.readFileSync(p, 'utf8')); }

function collectTables(schema) {
  const out = new Map(); // name -> type
  for (const r of schema) {
    if (!r || r.dataset_name !== 'sm_transformed_v2') continue;
    if (!out.has(r.table_name)) out.set(r.table_name, r.table_type || '');
  }
  // Desired order: Dimension, Fact, One Big Table, Report, then name ASC
  const order = { 'Dimension': 1, 'Fact': 2, 'One Big Table': 3, 'Report': 4 };
  return Array.from(out.entries())
    .sort((a, b) => {
      const [na, ta] = a; const [nb, tb] = b;
      const oa = order[ta] || 99; const ob = order[tb] || 99;
      if (oa !== ob) return oa - ob;
      return na.localeCompare(nb);
    })
    .map(([name]) => `data-activation/data-tables/sm_transformed_v2/${name}`);
}

function updateSourceMediumTablesNav(docs, pages) {
  // docs.navigation.tabs[].groups[...] possibly nested groups
  const tabs = docs?.navigation?.tabs;
  if (!Array.isArray(tabs)) return false;

  let updated = false;
  function walkGroups(node) {
    if (!node) return;
    if (node.group === 'SourceMedium Tables' && Array.isArray(node.pages)) {
      node.pages = pages;
      updated = true;
      return; // still continue, in case of duplicates
    }
    if (Array.isArray(node.pages)) {
      for (const p of node.pages) {
        if (p && typeof p === 'object') walkGroups(p);
      }
    }
    if (Array.isArray(node.groups)) {
      for (const g of node.groups) walkGroups(g);
    }
  }

  for (const tab of tabs) {
    walkGroups(tab);
  }
  return updated;
}

function main() {
  const docs = loadJSON(DOCS_JSON);
  const schema = loadJSON(SCHEMA_JSON);
  const pages = collectTables(schema);
  const ok = updateSourceMediumTablesNav(docs, pages);
  if (!ok) {
    console.error('SourceMedium Tables group not found or navigation shape unexpected. No changes made.');
    process.exit(0);
  }
  fs.writeFileSync(DOCS_JSON, JSON.stringify(docs, null, 2) + '\n', 'utf8');
  console.log('Updated docs.json SourceMedium Tables with', pages.length, 'entries.');
}

if (require.main === module) main();


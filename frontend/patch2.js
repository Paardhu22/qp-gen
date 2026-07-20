const fs = require('fs');
const file = 'frontend/components/generator-form.tsx';
let content = fs.readFileSync(file, 'utf8');

content = content.replace(
  'contentScopePolicy: z.enum(["strict", "source_only"]).default("strict"),',
  'contentScopePolicy: z.enum(["strict", "source_only"]),'
);

fs.writeFileSync(file, content);

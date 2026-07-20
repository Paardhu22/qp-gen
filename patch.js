const fs = require('fs');
const file = 'frontend/components/generator-form.tsx';
let content = fs.readFileSync(file, 'utf8');

content = content.replace(
  'includeViAlternatives: z.boolean(),',
  'includeViAlternatives: z.boolean(),\n  contentScopePolicy: z.enum(["strict", "source_only"]).default("strict"),'
);

content = content.replace(
  'includeViAlternatives: true,',
  'includeViAlternatives: true,\n      contentScopePolicy: "strict",'
);

content = content.replace(
  'include_vi_alternatives: values.includeViAlternatives,',
  'include_vi_alternatives: values.includeViAlternatives,\n          contentScopePolicy: values.contentScopePolicy,'
);

const uiCode = `
          <FormField
            control={form.control}
            name="contentScopePolicy"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-foreground">
                  Generation Strictness
                </FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full bg-background border-border text-foreground">
                      <SelectValue placeholder="Select strictness" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground min-w-[var(--radix-select-trigger-width)]">
                    <SelectItem value="strict">Standard Default (Allows Curriculum Fallback)</SelectItem>
                    <SelectItem value="source_only">Strict to Source Material (Source Only)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-zinc-400 dark:text-muted-foreground mt-1 leading-snug">
                  {field.value === "strict" 
                    ? "If uploaded chapters lack coverage for certain blueprint topics, the AI will generate those questions from general CBSE curriculum knowledge."
                    : "Questions are generated STRICTLY from your source material. Blueprint slots missing from your PDF will be skipped, which may result in a shorter paper."}
                </p>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Cluster C: VI alternative toggle.`;

content = content.replace(
  '{/* Cluster C: VI alternative toggle.',
  uiCode
);

// Also remove the old hardcoded strict text
content = content.replace(
  '<p className="text-xs text-muted-foreground">\n          Questions are generated STRICTLY from your source material.\n        </p>',
  ''
);

fs.writeFileSync(file, content);

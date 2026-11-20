Status: done
For: cursor

# Brief 002: the demo button must upload each sample with its drawer type

Do not edit: everything listed in brief 001, and `apps/api/**`.

## The problem in brief 001's button
`openDemoCase()` in `apps/web/components/dashboard.tsx` uploads the three files together, then classifies whatever is in
`uploaded.workspace.gap.unrecognized`. On a real server the files are read in the background **after** the upload
response, so at that moment they sit in `gap.in_progress`, not in `unrecognized`. The loop finds nothing, and with no AI
key (or AI off for the office) the three files end up waiting for a person to sort them. The form is not filled.
(The test client hides this, because it runs background work before it returns.)

## The fix
Upload each sample on its own with its drawer type, and drop the classify loop:

```ts
for (const [index, item] of DEMO_DOCUMENTS.entries()) {
  const uploaded = await api.upload(created.id, [files[index]], { documentType: item.type });
  if (uploaded.rejected.length) throw new Error("פתיחת תיק הדוגמה נכשלה. נסו שוב.");
}
router.push(`/cases/${created.id}`);
```

A type chosen with the upload is kept by the reader, and once the text is read the case fills the details from it
(`CaseService.run_ingestion`). Claude pinned this exact sequence in
`apps/api/tests/test_demo_documents.py::test_the_dashboard_demo_case_fills_the_form_with_no_ai`: all three drawers filled,
nothing waiting for review, 9 of the 10 Form 101 details read from the samples.

Keep the rest of brief 001's button as it is (case name, client name, progress label, Hebrew error).

## Checks
- `npx tsc --noEmit -p apps/web`
- Rebuild and restart port 3000.

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md`.

## Answers
(Claude answers questions from `status.md` here.)

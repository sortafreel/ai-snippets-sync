## Context
@/Users/woutut/Documents/Code/wizard/src/lib/programs/self-driving/ARCHITECTURE.md
@/Users/woutut/Documents/Code/posthog/products/signals/ARCHITECTURE.md

- I did a round of AI review for the PR for this branch @/Users/woutut/Documents/Code/pr_reviewer/reviews/192/review_report.md for this repo (`context-mill`)
- I need to you to start reviewer agents in parallel (as ultracode) and validate each specific issue
- By validate - I mean keeping things that are actual problems and could be encountered in production, not theoretic 1 in a million things
- Don't skip too many though, lean into "makes sense and could happen", not "will happen every day"
- In the end create an md file of the root of this repo in the PR-review-like style:
  - Where the issue happens (files+lines)
  - What's the issue and potential fix (what the reviewer of the PR would wrote)
  - What's the assessment (what's the author of the PR would reply)

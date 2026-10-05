---
name: text-similarity
description: >
  Optional. Cosine similarity of texts you already have, via text_similarity.
  Not a classifier and not Holix memory search.
tags:
  - embeddings
  - similarity
  - optional
opt_in: true
user-invocable: true
---

## When to use

Call `text_similarity` to compare strings that are already in the conversation: a near-duplicate, or which of a few passages is closest to another.

Pass the texts in the language they are written in. Do not translate them first.

This does not search profile memory, documents, or skills, and it does not pick a label. For a closed set of answers use `systemone_decide` when that tool is on.

## Call

- Two texts: `text_a` and `text_b`. Read `cosine` (1 is the same direction, 0 is unrelated).
- Up to eight texts: `texts`. Read the cosine matrix.

If the tool returns `Embeddings error`, say so. Do not invent a score.

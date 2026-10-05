---
name: typed-decision
description: >
  Optional. Closed-set choice, an ordinal score, or a yes/no probability
  via systemone_decide. The decision model does not write the user-facing answer.
tags:
  - decision
  - optional
opt_in: true
user-invocable: true
---

## When to use

Call `systemone_decide` only for a judgment with answers you already listed:

- one label from a fixed set (`choice`)
- a position on a scale you wrote, worst to best (`score`)
- whether one statement is true (`noul`)

The default decision model is multilingual. Write `state` and criteria in the same language as the user. Do not translate them to English first.

Do not use it to draft a reply, write code, extract a free string (a name, a sum, a paragraph), or search memory.

## Call

`state` is the text or object to judge. `questions` is a map. The question id is only a label. The meaning belongs in `instructions` and `criteria`.

- `choice`: `criteria` is an object of allowed answer to when it applies.
- `score`: `criteria` is an array of at least two levels, lowest to highest. The score is a position on that list, not a free 0–100 number.
- `noul`: `instructions` is a statement. The result `noul` is the probability it is true, from 0 to 1.

Read `probabilities` and `confidence` before acting. A split near 0.5 is not a decision. If the tool returns `System One error`, say so. Do not invent probabilities.

## After the result

You still write the user-facing answer. The decision result picks or gates. It does not replace the reply.

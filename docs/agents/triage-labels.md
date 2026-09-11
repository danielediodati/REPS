# Triage labels

| role | label here | meaning |
|---|---|---|
| `needs-triage` | `needs-triage` | the maintainer needs to evaluate it |
| `needs-info` | `needs-info` | waiting on the reporter |
| `ready-for-agent` | `ready-for-agent` | fully specified, ready for an AFK agent |
| `ready-for-human` | `ready-for-human` | needs a human to implement |
| `wontfix` | `wontfix` | will not be actioned |

The tracker is local markdown, so a label is a `Status:` line near the top of the issue file. Each issue has exactly one role at a time:

```markdown
# Import free-exercise-db into `exercises`

Status: ready-for-agent
```

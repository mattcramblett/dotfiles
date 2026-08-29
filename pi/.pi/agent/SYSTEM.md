Your output should be tight and always start with a summary before giving some detail. Give the user condensed, easily consumable information rather than a verbose or exhaustive explanation. The user will probe for more detail if they are interested.

When showing git diffs, use:
```bash
git diff --no-color | delta --paging=never --line-numbers
```

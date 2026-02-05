---
name: tech-debt
description: Analyze and prioritize technical debt with ROI-based remediation plans. Supports Python, C#, Node.js, TypeScript, React, and other languages. Use when user says "analyze technical debt", "check code quality", "what's slowing down development", "review my changes for tech debt", "check for duplications before I commit", "analyze this feature branch", or "find code smells in my PR".
---

# Technical Debt Analyzer

Identify, quantify, and prioritize technical debt with git-aware analysis for feature branches and uncommitted changes.

## Analysis Modes

### 1. Uncommitted Changes (Pre-commit)
Analyze staged/unstaged changes before committing:
```bash
git diff              # Unstaged changes
git diff --cached     # Staged changes
```

### 2. Feature Branch (vs main)
Analyze all commits on current branch:
```bash
git log main..HEAD --oneline              # List commits
git diff main...HEAD                       # All changes
git diff main...HEAD --name-only          # Changed files
```

### 3. Full Codebase
Analyze entire project or specific directories.

## Detection Patterns by Language

### Universal Patterns
- **Duplication**: Repeated code blocks (>10 lines similar)
- **Long files**: >500 lines suggests need for splitting
- **Deep nesting**: >4 levels of indentation
- **Large functions**: >50 lines per function/method
- **TODO/FIXME/HACK comments**: Unresolved debt markers
- **Commented-out code**: Dead code left behind

### Python
- Bare `except:` blocks
- `import *` usage
- Missing type hints in public APIs
- Mutable default arguments

### C# / .NET
- Empty catch blocks
- `dynamic` overuse
- Missing `IDisposable` patterns
- Large classes (>1000 lines)
- Region abuse hiding complexity

### TypeScript / JavaScript / React
- `any` type usage
- `eslint-disable` comments
- Prop drilling (>3 levels)
- Missing error boundaries
- Large components (>300 lines)
- Inline styles instead of CSS modules
- Missing `key` props in lists

### Node.js
- Callback hell (nested callbacks >3 levels)
- Missing error handling in async code
- Synchronous file operations
- Hardcoded configuration

## Debt Categories

### Code Debt
- **Duplication**: Copy-paste, repeated logic
- **Complexity**: High cyclomatic complexity, deep nesting
- **Structure**: Circular dependencies, tight coupling

### Architecture Debt
- **Design**: Missing abstractions, SOLID violations
- **Technology**: Outdated dependencies, deprecated APIs

### Testing Debt
- **Coverage**: Untested paths, missing edge cases
- **Quality**: Brittle, slow, or flaky tests

### Documentation Debt
- Missing API docs, undocumented complex logic

## Git Analysis Commands

```bash
# Files changed on feature branch
git diff main...HEAD --name-only --diff-filter=AM

# Frequency of changes (churn = likely debt)
git log --since="6 months ago" --pretty=format: --name-only | sort | uniq -c | sort -rn | head -20

# Find large commits (potential rushed code)
git log --oneline --shortstat | head -50

# Authors of changed files (for context)
git log main..HEAD --pretty=format:"%an" | sort | uniq -c
```

## Output Format

### Summary Dashboard
```yaml
scope: feature-branch  # or uncommitted/full-codebase
files_analyzed: 12
languages: [typescript, python]

debt_found:
  critical: 2
  high: 5
  medium: 8
  low: 15

top_issues:
  - type: duplication
    files: [src/api/users.ts, src/api/orders.ts]
    lines: 45
    recommendation: Extract shared validation logic

  - type: complexity
    file: src/services/payment.cs
    method: ProcessTransaction
    cyclomatic: 23
    recommendation: Split into smaller methods
```

### Prioritized Actions

**Before Commit** (fix now):
- Duplicated code introduced in this change
- New `any` types or `eslint-disable`
- Missing error handling

**This Sprint** (quick wins):
- High-churn files with issues
- Test coverage gaps in changed code

**Backlog** (track for later):
- Larger refactors
- Dependency updates

## ROI Calculation

For each debt item:
```
effort_hours: 4
monthly_cost_hours: 2  # Time lost due to this debt
roi: 50%               # monthly_cost / effort
payback_months: 2
```

## Prevention Recommendations

Based on findings, suggest:
- Pre-commit hooks (husky, pre-commit)
- CI checks (complexity limits, coverage gates)
- Linter rules to prevent recurrence

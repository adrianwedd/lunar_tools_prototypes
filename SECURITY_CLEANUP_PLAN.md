# Git History Security Cleanup Plan

## 🔍 Identified Security Issues

### Critical: API Keys in Git History
- **File**: `GITHUB_ISSUES.md` (commit 2e4595d)
- **Exposed Keys**:
  - LangSmith API key: `lsv2_pt_[REDACTED_32_CHARS]_[REDACTED_10_CHARS]`
  - LangSmith API key: `lsv2_pt_[REDACTED_32_CHARS]_[REDACTED_10_CHARS]`

### Current Working Directory Issues
- `.env` file contains active API keys (should not be committed)
- `.temp/` directory contains temporary files with hardcoded keys
- Various cache files triggering false positives

## 🛠️ Recommended Cleanup Strategy

### Phase 1: Immediate Actions (Safe)
1. ✅ **Revoke exposed API keys** - Contact API providers to invalidate exposed keys
2. ✅ **Update .gitignore** - Ensure sensitive files are properly ignored
3. ✅ **Remove sensitive files** - Clean working directory of secret-containing files
4. ✅ **Update documentation** - Redact keys in current documentation

### Phase 2: Git History Cleanup (Destructive)
⚠️ **WARNING**: This will rewrite git history and require force-push

#### Option A: BFG Repo-Cleaner (Recommended)
```bash
# Install BFG Repo-Cleaner
brew install bfg  # macOS
# or download from: https://rtyley.github.io/bfg-repo-cleaner/

# Create text file with secrets to remove
echo "lsv2_pt_[REDACTED_KEY_1]" > secrets.txt
echo "lsv2_pt_[REDACTED_KEY_2]" >> secrets.txt

# Clone fresh copy for cleaning
git clone --mirror https://github.com/adrianwedd/lunar_tools_prototypes.git lunar_tools_clean.git

# Run BFG to remove secrets
bfg --replace-text secrets.txt lunar_tools_clean.git

# Clean up and push
cd lunar_tools_clean.git
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force
```

#### Option B: Git Filter-Branch (Alternative)
```bash
# Remove specific content from all history
git filter-branch --tree-filter 'find . -name "GITHUB_ISSUES.md" -exec sed -i "" "s/lsv2_pt_[a-f0-9]*_[a-f0-9]*/[REDACTED]/g" {} \;' --all

# Force push cleaned history
git push --force --all
```

### Phase 3: Post-Cleanup Verification
1. **Scan cleaned repository**: Run detect-secrets on cleaned repo
2. **Update all clones**: Team members need to re-clone
3. **Verify API key revocation**: Confirm old keys are inactive
4. **Update secrets baseline**: Refresh .secrets.baseline file

## 🚨 Coordination Required

**Before executing Phase 2**:
- [ ] Coordinate with repository owner/team
- [ ] Install BFG Repo Cleaner: `brew install bfg` or download from https://rtyley.github.io/bfg-repo-cleaner/
- [ ] Backup current repository state
- [ ] Revoke/rotate exposed API keys with LangSmith
- [ ] Notify team members they'll need to re-clone
- [ ] Schedule maintenance window if this affects CI/CD

**Specific Keys to Remove**:
- `lsv2_pt_[REDACTED_KEY_1]` (ends with _ac16fa90c6)
- `lsv2_pt_[REDACTED_KEY_2]` (ends with _123b70d230)

**Ready-to-execute commands**:
```bash
# Create replacement file
echo "lsv2_pt_[REDACTED_KEY_1]==>[REDACTED_LANGSMITH_KEY]" > secrets.txt
echo "lsv2_pt_[REDACTED_KEY_2]==>[REDACTED_LANGSMITH_KEY]" >> secrets.txt

# Run BFG on repository
bfg --replace-text secrets.txt .git
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force
```

## 🔐 Prevention Measures (Already Implemented)
- ✅ Pre-commit hooks with detect-secrets
- ✅ Enhanced PII filtering in logging
- ✅ .env.example template for secure setup
- ✅ Comprehensive .gitignore for sensitive files

## 📋 Post-Cleanup Checklist
- [ ] Verify no secrets in `git log --all -p | grep -E "(sk-|r8_|lsv2_pt_|ghp_)"`
- [ ] Update GitHub issue #4 with completion status
- [ ] Document new API keys in secure location
- [ ] Test all prototypes with new API keys
- [ ] Update CI/CD environment variables if needed

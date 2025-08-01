# GitHub Issues to Create

This document contains GitHub issues that should be created once the repository is initialized.

---

## Issue 1: 🔒 CRITICAL: Remove hardcoded API keys from temporary files

**Priority:** Critical  
**Labels:** security, critical, bug

### Summary
**CRITICAL SECURITY ISSUE**: Hardcoded API keys and secrets have been found in temporary files in the `.temp/` directory.

### Security Concerns Found
- `interactive_storytelling0.10.py`: Contains hardcoded LangSmith API key `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`
- `interactive_storytelling0.9.py`: Contains hardcoded API key `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`
- `interactive_storytelling0.8.py`: Contains hardcoded API key
- Multiple temp files contain hardcoded authorization headers

### Immediate Actions Required
1. **Revoke exposed API keys immediately** from LangSmith console
2. Remove all files in `.temp/` directory
3. Add `.temp/` to `.gitignore` (already present but ensure it's respected)
4. Audit all repository history for exposed keys

### Long-term Solutions
- Implement pre-commit hooks to prevent API key commits
- Add secrets scanning to CI/CD pipeline
- Use environment variables exclusively for API keys
- Implement secret scanning tools like `detect-secrets`

---

## Issue 2: 🛠️ Add comprehensive development tooling and linting configuration

**Priority:** High  
**Labels:** enhancement, tooling, development

### Summary
The project lacks comprehensive development tooling configuration for consistent code quality and developer experience.

### Missing Tools & Configuration
1. **Ruff configuration** - No `ruff.toml` or `pyproject.toml` [tool.ruff] section
2. **Pre-commit hooks** - No `.pre-commit-config.yaml`
3. **Type checking configuration** - mypy.ini or pyproject.toml [tool.mypy]
4. **Code formatting** - Black configuration
5. **Import sorting** - isort configuration

### Proposed Solutions
- Add `ruff.toml` with project-specific rules
- Configure pre-commit hooks for automatic code quality checks
- Set up mypy with appropriate type checking rules
- Configure Black and isort for consistent formatting
- Add development dependencies to pyproject.toml

### Files to Create/Update
- `.pre-commit-config.yaml`
- `pyproject.toml` (add tool configurations)
- Update CI pipeline to use these tools

---

## Issue 3: 🧪 Improve test coverage and add integration tests

**Priority:** Medium  
**Labels:** testing, quality

### Summary
Current test suite only includes basic smoke tests. Need comprehensive test coverage for core functionality.

### Current Test Issues
- Only smoke tests that mock keyboard input
- No unit tests for individual methods
- No integration tests for AI components
- Missing tests for configuration management
- No performance tests for audio/visual processing

### Proposed Improvements
1. **Unit Tests**
   - Test Manager initialization with different configs
   - Test configuration loading and environment overrides
   - Test error handling in tool initialization

2. **Integration Tests**
   - Test end-to-end prototype workflows (mocked)
   - Test AI tool integrations with mock responses
   - Test audio/visual pipeline components

3. **Test Infrastructure**
   - Add pytest fixtures for common test setups
   - Add test data and mock responses
   - Configure test coverage reporting

### Files Affected
- `tests/` directory expansion
- `conftest.py` enhancements
- New test files for each major component

---

## Issue 4: 📚 Create comprehensive documentation and missing standard files

**Priority:** Medium  
**Labels:** documentation, enhancement

### Summary
Several standard project files are missing or incomplete, affecting project professionalism and contributor onboarding.

### Missing Files
1. **`.env.example`** - Template for environment variables
2. **`CONTRIBUTING.md`** - Contributor guidelines (exists but may need updates)
3. **`CHANGELOG.md`** - Version change tracking
4. **`setup.py`** - Alternative setup script
5. **API documentation** - Sphinx or similar documentation

### Documentation Improvements Needed
1. **README.md Updates**
   - Add badges (build status, coverage, etc.)
   - Add more detailed setup instructions
   - Include troubleshooting section
   - Add API key setup guide

2. **Code Documentation**
   - Add docstrings to all public methods
   - Add type hints throughout codebase
   - Document configuration options

3. **Developer Documentation**
   - Architecture decision records (ADRs)
   - Development workflow documentation
   - Testing guidelines

---

## Issue 5: 🐞 Fix syntax errors and code quality issues

**Priority:** High  
**Labels:** bug, code-quality

### Summary
Multiple code quality issues found during analysis that need attention.

### Syntax Errors
- `.temp/interactive_storytelling0.7.py:7` - Invalid syntax in import statement

### Code Quality Issues
1. **Excessive use of bare `except` clauses**
   - Multiple files use `except Exception as e:` without specific exception handling
   - Should use more specific exception types where possible

2. **Print statements for logging**
   - `lunar_tools_demo.py` uses print() instead of logging
   - Should use consistent logging throughout

3. **Stub implementations**
   - `src/lunar_tools_art/tools.py` contains only stub classes with `pass`
   - Need to implement or import actual tool classes

4. **Missing error handling**
   - Some prototype files lack proper error handling
   - Need graceful degradation when tools fail to initialize

### Proposed Fixes
- Replace print statements with proper logging
- Implement specific exception handling
- Add proper tool implementations or imports
- Add input validation where needed

---

## Issue 6: 🔧 Fix CI/CD pipeline and improve project configuration

**Priority:** Medium  
**Labels:** ci/cd, infrastructure

### Summary
The existing CI pipeline has some issues and could be improved for better reliability and coverage.

### Current CI Issues
1. **Invalid file reference** - `mypy lunar_tools_art.py` doesn't exist (should be `src/lunar_tools_art/`)
2. **Missing dependency caching** - Could improve build times
3. **No coverage reporting** - Should track test coverage
4. **Limited Python version testing** - Only tests Python 3.10

### Proposed Improvements
1. **Fix existing pipeline**
   - Correct mypy target paths
   - Fix dependency installation issues
   - Add proper error handling

2. **Enhanced pipeline features**
   - Test multiple Python versions (3.9, 3.10, 3.11, 3.12)
   - Add coverage reporting with codecov
   - Add security scanning with Safety
   - Add license compliance checking

3. **Additional workflows**
   - Dependency update automation (Dependabot)
   - Release automation
   - Documentation building and deployment

---

## Issue 7: 🎨 Standardize prototype structure and add error handling

**Priority:** Medium  
**Labels:** enhancement, architecture

### Summary
Prototypes have inconsistent structure and error handling patterns that should be standardized.

### Current Issues
1. **Inconsistent error handling** across prototypes
2. **No standard base class** for prototypes
3. **Inconsistent logging** patterns
4. **No graceful shutdown** handling
5. **Hardcoded configuration** in some prototypes

### Proposed Solutions
1. **Create base prototype class**
   - Common initialization patterns
   - Standard error handling
   - Consistent logging setup
   - Graceful shutdown handling

2. **Standardize prototype structure**
   - Common constructor signature
   - Standard run() method pattern
   - Consistent configuration handling
   - Standard testing patterns

3. **Improve error resilience**
   - Graceful degradation when AI services are unavailable
   - Better handling of hardware device failures
   - Recovery mechanisms for temporary failures

### Files Affected
- All files in `prototypes/` directory
- New base class in `src/lunar_tools_art/`
- Updated tests to match new patterns

---

## Issue 8: 🔐 Implement security best practices and secret management

**Priority:** High  
**Labels:** security, enhancement

### Summary
Implement comprehensive security measures to prevent future security issues and improve overall security posture.

### Security Enhancements Needed
1. **Secret Management**
   - Implement proper secret loading with validation
   - Add secret rotation mechanisms
   - Implement secret masking in logs (already partially done)

2. **Input Validation**
   - Validate all user inputs in prototypes
   - Sanitize file paths and names
   - Validate configuration parameters

3. **Security Scanning**
   - Add Bandit security linting to pre-commit hooks
   - Implement dependency vulnerability scanning
   - Add SAST (Static Application Security Testing) tools

4. **Access Control**
   - Implement proper file permissions
   - Add rate limiting for AI API calls
   - Implement proper session management

### Implementation Steps
1. Create security configuration templates
2. Add security scanning to CI/CD
3. Implement input validation utilities
4. Add security testing to test suite
5. Create security documentation

---

## Creating These Issues

Once you initialize this repository with git and push to GitHub, create these issues using:

```bash
# Initialize repository if not done
git init
git remote add origin <your-repo-url>

# Create issues using GitHub CLI
gh issue create --title "🔒 CRITICAL: Remove hardcoded API keys" --body-file issue1.md --label "security,critical"
# ... repeat for each issue
```

Or create them manually through the GitHub web interface using the content above.
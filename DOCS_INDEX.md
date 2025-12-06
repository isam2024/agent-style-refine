# Documentation Index

Complete guide to all project documentation.

---

## Quick Links

| Document | Purpose | Audience |
|----------|---------|----------|
| [README.md](./README.md) | Quick start, overview, usage | All users |
| [DOCUMENTATION.md](./DOCUMENTATION.md) | Complete reference, API docs | Developers, power users |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Technical deep dive, algorithms | Developers, contributors |
| [CHANGELOG.md](./CHANGELOG.md) | Version history, changes | All users |

---

## Document Breakdown

### README.md
**Purpose:** Get started quickly

**What's Inside:**
- Feature overview
- Quick start guide (5 minutes)
- Basic usage examples
- Configuration basics
- Troubleshooting common issues
- Branch overview (main vs feature)

**Read This If:**
- ✅ You're new to the project
- ✅ You want to get running quickly
- ✅ You need basic configuration help
- ✅ You're deciding which branch to use

**Length:** ~10 min read

---

### DOCUMENTATION.md
**Purpose:** Complete project reference

**What's Inside:**
1. **Project Overview** - Purpose, features, tech stack
2. **Architecture** - System diagram, component interaction
3. **Core Concepts** - Identity vs style, invariants, evaluation
4. **API Reference** - All endpoints with examples
5. **Data Models** - Complete schema documentation
6. **Services** - Service layer explanation
7. **Prompts System** - Prompt architecture and templates
8. **Evaluation System** - Multi-dimensional scoring, weights
9. **Branches** - Main vs feature comparison
10. **Configuration** - Environment variables, settings
11. **Deployment** - Development and production setup
12. **Troubleshooting** - Comprehensive error guide

**Read This If:**
- ✅ You need API documentation
- ✅ You're integrating with the system
- ✅ You need to understand data models
- ✅ You're deploying to production
- ✅ You need configuration reference

**Length:** ~45 min read

**Key Sections:**

**API Reference (Section 4):**
- REST endpoints with request/response examples
- WebSocket event documentation
- Error codes and handling

**Data Models (Section 5):**
- StyleProfile schema
- CritiqueResult schema
- Database models
- Pydantic validation rules

**Evaluation System (Section 8):**
- Six dimensions explained
- Weighted scoring algorithm
- Three-tier approval logic
- Catastrophic failure detection

---

### ARCHITECTURE.md
**Purpose:** Deep technical understanding

**What's Inside:**
1. **System Architecture** - Layered architecture, component interactions
2. **Data Flow Pipelines** - Complete flow diagrams with code
3. **Algorithms** - Weighted regression, approval logic, confidence tracking
4. **Evaluation System** - Dimension weights, scoring rubrics
5. **Prompt Engineering** - Template system, substitution patterns
6. **VLM Integration** - Ollama client, response parsing
7. **State Management** - Database schema, versioning, file organization
8. **Error Handling** - Strategy, retry logic, logging
9. **Performance Optimization** - Caching, parallelization
10. **Design Decisions** - Why SQLite? Why Base64? Why WebSocket?

**Read This If:**
- ✅ You're contributing code
- ✅ You need to understand algorithms
- ✅ You're debugging complex issues
- ✅ You want to understand design choices
- ✅ You're implementing new features

**Length:** ~60 min read

**Key Sections:**

**Algorithms (Section 3):**
- Weighted regression detection (full code + examples)
- Three-tier approval logic (decision tree)
- Recovery guidance generation
- Feature confidence tracking (logarithmic growth)

**Data Flow Pipelines (Section 2):**
- Style extraction pipeline (step-by-step)
- Iteration pipeline (complete flow)
- Auto-evaluation pipeline (training loop)

**Design Decisions (Section 10):**
- Why SQLite over PostgreSQL?
- Why Base64 image transport?
- Why WebSocket for progress?
- Why Pydantic over dataclasses?
- Why mechanical baseline construction?

---

### CHANGELOG.md
**Purpose:** Track all changes and versions

**What's Inside:**
1. **[2.0-experimental]** - Feature branch changes
   - Vectorized feedback system
   - Feature classification
   - Confidence tracking
   - Known issues with llava:7b
2. **[1.5]** - Main branch improvements
   - Weighted multi-dimensional evaluation
   - Three-tier approval system
   - Catastrophic recovery
   - Identity locking
   - Mechanical baseline construction
3. **[1.0]** - Initial release
   - Core system
   - Training modes
   - Style library
4. **Migration Guides** - How to upgrade/downgrade
5. **Development History** - Session-by-session progress

**Read This If:**
- ✅ You want to know what changed
- ✅ You're upgrading versions
- ✅ You need migration instructions
- ✅ You're tracking feature development

**Length:** ~20 min read

**Key Sections:**

**Version Comparison:**
- Main branch: Production stable
- Feature branch: Experimental, needs llama3.2-vision:11b

**Migration Paths:**
- Main → Feature: Requires VLM upgrade
- Feature → Main: Simple checkout, no data loss

---

## Reading Paths

### For New Users (Getting Started)

**Path:** README → DOCUMENTATION (sections 1-3) → Try it!

1. Read [README.md](./README.md) - Quick start (10 min)
2. Read [DOCUMENTATION.md](./DOCUMENTATION.md) sections:
   - Section 1: Project Overview
   - Section 2: Architecture (high-level)
   - Section 3: Core Concepts
3. Start training your first style!

**Time:** 30 minutes

---

### For Developers (Integration)

**Path:** README → DOCUMENTATION (API) → ARCHITECTURE (pipelines)

1. Read [README.md](./README.md) - Quick start (10 min)
2. Read [DOCUMENTATION.md](./DOCUMENTATION.md) sections:
   - Section 4: API Reference
   - Section 5: Data Models
   - Section 6: Services
3. Read [ARCHITECTURE.md](./ARCHITECTURE.md) sections:
   - Section 2: Data Flow Pipelines
   - Section 6: VLM Integration
4. Start building!

**Time:** 60 minutes

---

### For Contributors (Deep Dive)

**Path:** All docs in order

1. Read [README.md](./README.md) - Overview (10 min)
2. Read [DOCUMENTATION.md](./DOCUMENTATION.md) - Complete (45 min)
3. Read [ARCHITECTURE.md](./ARCHITECTURE.md) - Complete (60 min)
4. Read [CHANGELOG.md](./CHANGELOG.md) - History (20 min)
5. Review code with docs as reference

**Time:** 2-3 hours

---

### For Troubleshooting

**Path:** README (troubleshooting) → DOCUMENTATION (troubleshooting)

1. Check [README.md](./README.md) - Troubleshooting section
2. If not resolved, check [DOCUMENTATION.md](./DOCUMENTATION.md) section 12
3. If still stuck, check [ARCHITECTURE.md](./ARCHITECTURE.md) section 8 (Error Handling)
4. Open GitHub issue with debug logs

---

### For Understanding Algorithms

**Path:** ARCHITECTURE (algorithms) → DOCUMENTATION (evaluation)

1. Read [ARCHITECTURE.md](./ARCHITECTURE.md) section 3: Algorithms
   - Weighted regression detection
   - Three-tier approval logic
   - Recovery guidance
   - Confidence tracking
2. Read [DOCUMENTATION.md](./DOCUMENTATION.md) section 8: Evaluation System
   - Dimension weights
   - Catastrophic thresholds
3. Review code in `backend/services/auto_improver.py`

---

## Finding Specific Information

### How do I...?

**...set up the project?**
→ [README.md](./README.md) - Quick Start section

**...call the API?**
→ [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 4: API Reference

**...understand the data models?**
→ [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 5: Data Models

**...configure the system?**
→ [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 10: Configuration

**...deploy to production?**
→ [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 11: Deployment

**...understand weighted evaluation?**
→ [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 3: Algorithms (Weighted Regression)

**...debug VLM responses?**
→ [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 6: VLM Integration (Response Parsing)

**...understand profile versioning?**
→ [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 7: State Management (Profile Versioning)

**...see what changed in v1.5?**
→ [CHANGELOG.md](./CHANGELOG.md) - [1.5] section

**...migrate from main to feature branch?**
→ [CHANGELOG.md](./CHANGELOG.md) - Migration Guide section

**...troubleshoot oscillation?**
→ [README.md](./README.md) - Troubleshooting OR [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 12

---

## Code Examples Location

### API Usage Examples

**Location:** [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 4

**Examples:**
- Creating a session
- Running an iteration
- Submitting feedback
- Auto training loop
- WebSocket connection

### Algorithm Examples

**Location:** [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 3

**Examples:**
- Weighted delta calculation (with numbers)
- Three-tier approval decision tree
- Recovery guidance generation
- Feature confidence update

### Service Usage Examples

**Location:** [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 2

**Examples:**
- Style extraction pipeline (full code)
- Iteration pipeline (full code)
- Auto-evaluation pipeline (full code)

---

## Documentation Statistics

| Document | Lines | Words | Read Time | Sections |
|----------|-------|-------|-----------|----------|
| README.md | 530 | 2,800 | 10 min | 15 |
| DOCUMENTATION.md | 1,650 | 11,500 | 45 min | 12 |
| ARCHITECTURE.md | 2,850 | 18,000 | 60 min | 10 |
| CHANGELOG.md | 680 | 4,200 | 20 min | 4 versions |
| **Total** | **5,710** | **36,500** | **135 min** | **41** |

---

## Visual Guides

### System Architecture Diagram

**Location:** [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 2

Shows:
- Frontend → Backend → Services → External systems
- Component interactions
- Data flow

### Data Flow Diagrams

**Location:** [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 2

Shows:
- Style extraction flow
- Iteration loop flow
- Auto-evaluation flow

### Decision Trees

**Location:** [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 3

Shows:
- Three-tier approval logic
- Catastrophic failure detection

---

## Updates and Maintenance

### Last Updated

- README.md: 2025-12-05
- DOCUMENTATION.md: 2025-12-05
- ARCHITECTURE.md: 2025-12-05
- CHANGELOG.md: 2025-12-05
- DOCS_INDEX.md: 2025-12-05

### Update Schedule

Documentation is updated with each:
- Major version release
- Significant feature addition
- Breaking changes
- Architecture changes

### Contributing to Docs

1. Keep docs in sync with code
2. Add examples for new features
3. Update CHANGELOG.md with every commit
4. Regenerate this index when adding docs

---

## Glossary (Cross-Reference)

**Core Invariants**
- Definition: [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 3.2
- Technical Details: [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 5 (Prompt Engineering)

**Weighted Regression Detection**
- Concept: [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 8.1
- Algorithm: [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 3.1
- Code: `backend/services/auto_improver.py:calculate_weighted_delta()`

**StyleProfile**
- Schema: [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 5.1
- Versioning: [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 7.2

**Catastrophic Failure**
- Definition: [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 3.5
- Recovery Process: [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 3.3
- Thresholds: [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 8 (table)

**Feature Classification** (Feature Branch)
- Overview: [CHANGELOG.md](./CHANGELOG.md) - [2.0-experimental]
- Schema: [DOCUMENTATION.md](./DOCUMENTATION.md) - Section 5 (FeatureType)
- Algorithm: [ARCHITECTURE.md](./ARCHITECTURE.md) - Section 3.4

---

## Additional Resources

### External Documentation

- **Ollama API:** https://github.com/ollama/ollama/blob/main/docs/api.md
- **ComfyUI API:** https://github.com/comfyanonymous/ComfyUI/wiki/API
- **FastAPI:** https://fastapi.tiangolo.com/
- **Pydantic:** https://docs.pydantic.dev/
- **React:** https://react.dev/

### Related Papers

- DreamBooth: Fine Tuning Text-to-Image Diffusion Models (Ruiz et al., 2022)
- Prompt-to-Prompt Image Editing (Hertz et al., 2022)

---

## Version Compatibility

| Version | Branch | VLM | Status | Docs |
|---------|--------|-----|--------|------|
| 1.5 | main | llava:7b | ✅ Stable | Complete |
| 2.0-experimental | feature/vectorized-feedback | llama3.2-vision:11b | 🔬 Experimental | Complete |

---

## Contact

**Questions about documentation?**
- Open issue: https://github.com/isam2024/agent-style-refine/issues
- Tag: `documentation`

**Found an error?**
- Submit PR with correction
- Reference doc file + line number

**Want to contribute?**
- Read [ARCHITECTURE.md](./ARCHITECTURE.md) first
- Follow code style in existing docs
- Add examples for new features

---

*Documentation index last updated: 2025-12-05*

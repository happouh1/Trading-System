# Phase 4A implementation review

Status: **IMPLEMENTED; LOCAL QUALITY SUITE PASSED; CLEAN-INSTALL CI PENDING**

Phase 4A adds a research-only portfolio boundary for classifying equity candidates, measuring
liquidity and portfolio exposures, enforcing configured caps, simulating accepted candidates in
canonical order, and persisting immutable assessments. It does not change signal generation,
broker behavior, or the locked Webull exit manifest.

Long-term candidates are identifiable but automatically ineligible because point-in-time
fundamentals are not implemented. Options, portfolio margin, short borrow, correlations, and live
capital remain outside scope.

Local validation passed Ruff, strict mypy across 177 files, and 270 pytest tests. The existing
virtual environment lacks `setuptools.build_meta`; its clean editable reinstall could not complete
because the build-dependency index was unavailable. GitHub CI remains the clean-install authority.

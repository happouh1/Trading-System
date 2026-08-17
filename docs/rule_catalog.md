# Rule catalog

No executable trade-decision rules exist through the current Phase 1B increment. Data-validation,
causal-feature, pivot-confirmation, and structure-classification formulas are research infrastructure,
not trade entries. Pivot rules implement specification Section 5.1; structure states and swing labels
implement Section 5.2. Pattern triggers remain unimplemented until their isolated state machines are
added later in Phase 1B.

Phase 1D adds no trade-decision rules. `OUTCOME-GENERIC-1` labels success when favorable excursion
reaches 2R strictly before adverse excursion reaches 1R within the declared future horizon. This is
post-decision research data and remains inaccessible to decision modules.

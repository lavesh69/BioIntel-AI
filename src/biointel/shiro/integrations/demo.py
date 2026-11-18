from __future__ import annotations

DEMO_PROJECT_ID = "SHIRO-SYNTHETIC-DEMO"
DEMO_PROJECT_NAME = "Shiro synthetic biomedical demo"

DEMO_REPORT = b"""# Synthetic RNA-seq biomarker report

Synthetic/demo evidence only. This is not patient data and not a real scientific result.

## Differential expression
TP53 expression increased 2.8-fold with adjusted p-value 0.01 in the treated synthetic cohort. BRCA1 showed no material change. The analysis used a negative-binomial model.

## Quality control
All six synthetic samples passed library-size and mapping-rate checks. This evidence cannot support clinical diagnosis or treatment.
"""

DEMO_TABLE = b"""gene\tlog2_fold_change\tadjusted_p_value\tstatus
TP53\t1.485\t0.01\tsynthetic_up
BRCA1\t0.04\t0.72\tsynthetic_unchanged
EGFR\t-0.31\t0.18\tsynthetic_not_significant
"""

DEMO_QUESTIONS = (
    "What happened to TP53 in the synthetic report?",
    "Synthetic report mein TP53 ka result summarize karo.",
    "सिंथेटिक रिपोर्ट में TP53 का परिणाम बताइए।",
    "What evidence exists for KRAS mutation?",
)
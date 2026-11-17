# Quality scoring methodology

The score is an explainable heuristic, not an objective statement about whether data is useful.
It combines completeness (30%), uniqueness (20%), custom-rule validity (25%), type consistency
(15%), and schema stability (10%). Every deduction appears in both report formats with its
category, severity, points, and reason.

Missing-cell percentage reduces completeness, exact duplicate-row percentage reduces uniqueness,
and mixed apparent types reduce consistency. Failed custom rules reduce validity using severity
weights. Schema stability remains neutral until an explicit version comparison is requested;
comparison reports classify drift independently as informational, warning, or critical.

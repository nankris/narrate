# dotted-json-keys

Status: **fixed**

Evidence: BLOG_NOTES 2026-10-27 23:30 and 07_2026-10-27_agent_v1_real_nvidia-dev_kitchen trace/report (external staging).

VL returned .verdict/.evidence. Recursive key normalization strips leading dots/whitespace and lowercases; verdict values are case-insensitive.

# utf8-truncation

Status: **fixed**

Evidence: BLOG_NOTES 2026-10-27 23:30 and 07_2026-10-27_agent_v1_real_nvidia-dev_kitchen trace/report (external staging).

Byte truncation damaged Devanagari. Raw response and compact result limits now slice characters, with Hindi regression tests.

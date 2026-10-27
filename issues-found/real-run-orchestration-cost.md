# orchestration-cost

Status: **fixed**

Evidence: BLOG_NOTES 2026-10-27 23:30 and 07_2026-10-27_agent_v1_real_nvidia-dev_kitchen trace/report (external staging).

40 turns and 13 inspections consumed ~$0.130 orchestration. Append-only messages, batches, propose_cue, compact state and overlap caching reduce redundant work. Real cost reduction remains unmeasured.

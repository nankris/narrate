# wrong-event-drafts

Status: **fixed**

Symptom (Tears of Steel real run): gap 30.5-31.6 s was drafted as "rocket ignition" (happens at 0-9 s); another draft mentioned opening credits. Inspecting gap 1 (30.52-31.65) returned events at 24.52-26.04.

Root cause: not a timestamp offset. The prompt told the orchestrator to inspect `[gap.start-6, gap.end]`, so the first events of the 6 s pre-roll (24.52 = segment start) were correct absolute times but belonged before the gap, and the orchestrator forwarded arbitrary `context_events` to draft_description, which sent them all to the drafting model. A genuine risk also existed that the VL model answers clip-relative (0..duration) times, which were never converted.

Fix: drafts use only inspected events overlapping the gap window (start-1.0 s..end+0.5 s) plus at most 2 recent earlier events tagged "earlier, context only"; pre-roll shrunk to 2 s; inspect_video_segment now normalises times with a range heuristic (`absolute_times`: fits segment => absolute, fits 0..duration => relative, start added; mixed => events outside the segment dropped; ambiguous cases stay absolute).

Tests: `test_draft_context_limited_to_gap_window`, `test_absolute_times_heuristic`, `test_inspect_converts_relative_vl_times`.

# Mock perception and evaluation

Symptom: generated descriptions say a shape moves across a coloured scene regardless of actual input content.

Evidence: MockClient builds events from frame sampling timestamps and uses a fixed bilingual phrase table. No media is sent to a provider in mock mode. The synthetic clip uses captions and a moving glyph, not real people cooking.

Root cause: offline deterministic mock is for validating orchestration, scheduling and artifacts.

Fix/status: CLI warning, report mock marker, README results card and cached-artifact notice distinguish mock data from visual analysis. Real quality, Hindi translation and accessibility evaluation remain open.

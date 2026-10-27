# Provider compatibility and budget estimates

Symptom: video_url, JSON response format, and regional model support cannot be established offline.

Evidence: development ran MockClient exclusively. No real smoke results exist. The configured video_url part follows the task's proposed schema, not a verified provider response.

Root cause: real API calls were prohibited; no runtime key is available. Model prices/IDs came from the supplied task catalog, not a live lookup.

Fix/status: auto video-to-contact-sheet fallback implemented; explicit strategies and per-model base_url/json_mode overrides provided. Authorized smoke script tests both media paths later. One logical Ultra call can have two transport retries. Budget reserves every attempted request, including uncertain failed requests; byte-based media estimates are conservative and may block a request before provider billing would require it. Real media token accounting and costs remain to verify.

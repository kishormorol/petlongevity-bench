# M3 Temporal Prioritization Prompt

You are operating under a historical cutoff. Use ONLY evidence and database records explicitly supplied in the frozen snapshot.

Rank candidate interventions for future dog/cat healthy-aging research. For each candidate output:
- candidate_id
- score in [0,1]
- confidence in [0,1]
- concise evidence rationale
- direct_pet_evidence flag
- uncertainty note

Do not use later knowledge, memorized trial outcomes, or external browsing. Treat absence of future validation as unknown, not proof of ineffectiveness.

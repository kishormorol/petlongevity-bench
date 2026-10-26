# M2 Evidence Judgment Prompt

Given a CLAIM and an EVIDENCE PACKET, output JSON with:
- item_id
- label: supported | contradicted | insufficient
- direct_species_evidence: boolean
- surrogate_vs_hard_endpoint: string
- efficacy_vs_protocol: string

Judge only from the supplied evidence. Penalize species transfer, surrogate-to-lifespan overclaiming, association-to-causation overclaiming, and protocol-to-efficacy overclaiming.

# Phase 9E Proposal — Signed Stage Review

Phase 9E binds Ed25519 reviewer attestations to one Phase 9D review-ready assessment, plan, stage,
validity window, and immutable request hash. Required roles and credential issuance remain external,
operator-defined inputs. Reviewers must be distinct principals.

`SIGNATURES_VERIFIED` describes cryptographic evidence only. It is deliberately not named
`AUTHORIZED`: the implementation cannot activate a stage, deploy software, access a network,
write to a broker, or enable live trading. Expired requests, invalid signatures, credential mismatch,
or reviewer-separation failure are blocked. Missing required signatures remain incomplete.

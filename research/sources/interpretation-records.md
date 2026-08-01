# CRA Source Interpretation Records

**Generated:** 2026-07-31
**Issue:** #3 (REG-001)
**Source Policy:** `.blitzhub/policies/source-policy.yaml` (section 4: required_separation)

This file records the distinction between **facts**, **interpretations**,
**inferences**, **recommendations**, and **open questions** as required by
`.blitzhub/policies/source-policy.yaml` section 4 (required_separation).

---

## Record 1: CRA Application Timeline

**Source:** `cra-regulation-2024-2847` (Regulation (EU) 2024/2847), Article 70
**EC Summary:** `ec-cra-summary`, `ec-cra-factpage-implementation`

### Facts (F)
- F1: The CRA entered into force on 10 December 2024 (Article 70(1)).
- F2: Chapter IV applies from 11 June 2026 (Article 70(2)).
- F3: Reporting obligations (Article 14) apply from 11 September 2026 (Article 70(3)).
- F4: The Regulation applies in its entirety from 11 December 2027 (Article 70(6)).
- F5: Products placed on the market before 11 December 2027 are subject to CRA only
  if, from that date, they are subject to a substantial modification (Article 71).
- F6: EU type-examination certificates and approval decisions issued regarding
  cybersecurity requirements remain valid until 11 June 2028 (Article 71).

### Interpretations (I)
- I1: [Interpretation] The 24-hour early warning notification deadline (Article 14(1))
  applies from 11 September 2026. This is stated explicitly in the regulation but the
  implication that manufacturers cannot submit a single combined notification rather
  than three separate notifications is an interpretation.

### Inferences (IN)
- IN1: [Inference] Since Chapter IV applies from 11 June 2026, Member States must
  designate notifying authorities by that date (Article 43).

### Recommendations (R)
- R1: [Recommendation from guidance] Manufacturers should begin preparing for CRA
  compliance before 11 September 2026 (EC guidance C(2026) 5252). This is a
  recommendation from the Commission guidance, not a binding obligation.

### Open Questions (OQ)
- OQ1: [Open question] What constitutes a "substantial modification" is partially left
  to interpretation. Article 2(39) defines it as a modification that makes the product
  "materially different" from the original. The threshold for "materially different"
  is not precisely defined in quantitative terms.

---

## Record 2: Scope of the CRA

**Source:** `cra-regulation-2024-2847`, Articles 1-5; `ec-cra-summary`;
`ec-faqs-cra-2025` (FAQ 1.4)

### Facts
- F1: The CRA applies to hardware and software products ("products with digital
  elements") made available on the Union market (Article 1(1)).
- F2: "Product with digital elements" includes both final products and components
  placed separately on the market (Article 1(1)).
- F3: Products fall in scope when their intended purpose or reasonably foreseeable
  use includes a direct or indirect logical or physical data connection to a device
  or network (Article 1(2)).
- F4: Products not made available on the market (not supplied in a commercial
  activity) are not subject to the CRA (Article 5(1), Recital 18).

### Interpretations
- I1: [Interpretation] The term "making available on the market" in the CRA is
  interpreted as "making a product available for distribution or use on the Union
  market in the course of a commercial activity" (Article 3(27)). Whether a specific
  distribution model constitutes "commercial activity" is an interpretation point.

### Inferences
- IN1: [Inference] Free and open-source software (FOSS) that is published but not
  "made available on the market" within the meaning of the CRA is excluded from
  scope (Article 5(1), Recital 18, confirmed in EC FAQ 1.8).

### Open Questions
- OQ1: [Open question] Whether a product with digital elements that is distributed
  via a marketplace platform (e.g., app store) constitutes "making available on
  the market" by the platform operator or only by the manufacturer — this is
  addressed in EC FAQ 1.4 but the exact boundary is not precisely defined.

---

## Record 3: Excluded and Exception Products

**Source:** `cra-regulation-2024-2847`, Article 5;
`delegated-regulation-2025-1535`; `enisa-technical-implementation-guidance-nis2-2024-2690`

### Facts
- F1: Products covered by other Union legislation are excluded from the CRA to the
  extent that that other legislation is fully applicable (Article 5(2)).
- F2: The Delegated Regulation (EU) 2025/1535 excludes from the CRA certain products
  with digital elements falling within the scope of Regulation (EU) No 168/2013
  (vehicles).
- F3: The CRA applies to the categories of radio equipment in scope of the
  Radio Equipment Directive (RED) and covers the essential requirements of the RED
  on cybersecurity (RED Delegated Regulation (EU) 2022/30).

### Interpretations
- I1: [Interpretation] The phrase "to the extent that that other legislation is fully
  applicable" (Article 5(2)) requires a case-by-case determination. Whether another
  act provides "equivalent" cybersecurity coverage is an interpretation.

### Open Questions
- OQ1: [Open question] The scope of the vehicle exclusion under Delegated Regulation
  (EU) 2025/1535 — specifically, whether it covers aftermarket connected-car
  accessories or only OEM-installed systems — is not fully clarified.

---

## Record 4: Reporting Obligations

**Source:** `cra-regulation-2024-2847`, Articles 14-15;
`enisa-srp-page`, `enisa-srp-notification`, `enisa-srp-user-registration`

### Facts
- F1: Manufacturers must notify actively exploited vulnerabilities and severe
  incidents to their national CSIRT and to ENISA (Article 14(1)).
- F2: The notification deadlines are:
  - 24 hours for early warning (Article 14(2)(a))
  - 72 hours for the main notification (Article 14(2)(b))
  - 14 days for the final report after a corrective/mitigating measure (Article 14(2)(c))
  - 1 month from the 72h submission for severe incidents (Article 14(2)(d))
- F3: Notifications are submitted via the Single Reporting Platform (SRP) established
  and maintained by ENISA (Article 15(1)).

### Interpretations
- I1: [Interpretation] Whether a vulnerability is "actively exploited" determines
  whether Article 14 obligations are triggered. The definition of "active
  exploitation" is not precisely quantified; the EC FAQ provides examples but the
  threshold is an interpretation point.

### Open Questions
- OQ1: [Open question] The exact criteria for distinguishing an "early warning"
  notification from a "main" notification are not precisely defined in quantitative
  terms.
- OQ2: [Open question] The SRP FAQ (Q11) states that the SRP uses "may also" for
  voluntary reporting. The ENISA SRP page summarises this as "could be used" —
  whether this reflects a mandatory or purely optional pathway for voluntary reporting
  is an open question (interpretation note in catalog: `enisa-srp-page`).

---

## Record 5: Conformity Assessment

**Source:** `cra-regulation-2024-2847`, Article 32; Annex VIII;
`enisa-technical-competence-cra-notified-bodies-2026`

### Facts
- F1: Manufacturers of non-important/non-critical products may use the self-assessment
  procedure (internal control based on module A) (Article 32(1)).
- F2: For important products of class I, self-assessment is only permitted if the
  manufacturer has applied harmonised standards or common specifications (Article 32(2)).
- F3: Important products of class II and critical products require third-party
  assessment or use of an EU cybersecurity certification scheme (Article 32(3)).
- F4: Notified bodies must meet technical competence requirements as specified by ENISA.

### Inferences
- IN1: [Inference] Products listed in Annex III (important) and Annex IV (critical)
  are determined by the Implementing Regulation (EU) 2025/2392, which provides
  the technical descriptions of those categories.

### Open Questions
- OQ1: [Open question] The exact boundary between "important" and "critical" product
  categories for certain product types is not always clear-cut and may require
  case-by-case determination.

---

## Record 6: Open-Source Software

**Source:** `cra-regulation-2024-2847`, Articles 21-25; `ec-cra-summary`;
`ec-faqs-cra-2025`; `commission-guidance-cra-2026-5252`

### Facts
- F1: Open-source software stewards are defined as legal persons that systematically
  provide support on a sustained basis for the development of specific FOSS intended
  for commercial activities (Article 3(22)).
- F2: Open-source software stewards are required to have a cybersecurity policy,
  cooperate with market surveillance authorities, and report actively exploited
  vulnerabilities (Article 24(2)).
- F3: Open-source software stewards are not subject to penalties for CRA infringements
  (Article 22(4)).
- F4: Manufacturers of important products of class I and II that are FOSS may use
  self-assessment, provided they make the technical documentation publicly available
  (Article 32(5)).

### Interpretations
- I1: [Interpretation] The EC guidance clarifies when FOSS is "placed on the market"
  based on monetisation, donations, or support services (FAQ 1.4, guidance 2.2).
  Whether a specific FOSS distribution model constitutes "placing on the market"
  is an interpretation.

### Open Questions
- OQ1: [Open question] The boundary between "FOSS steward" and "FOSS contributor"
  is not precisely defined. A contributor who occasionally fixes a bug is unlikely
  to be a steward, but a maintainer of a widely-used project may be — the exact
  threshold is an interpretation point (EC guidance, Section 3.3).
- OQ2: [Open question] The exact monetary thresholds for "monetisation of other
  services" that would make FOSS "placed on the market" are not quantitatively
  defined in the regulation; the guidance provides qualitative examples.

---

## Record 7: CELEX Identifier Correction (NIS2 Directive)

**Source:** `nis2-directive-2022-2555`

### Fact
- F1: The NIS2 Directive is Directive (EU) 2022/2555, not Regulation (EU) 2022/2555.
  Its CELEX number is **32022L2555** (prefix L for directives), not 32022R2555
  (prefix R for regulations).

### Interpretation
- I1: [Interpretation from research process] The incorrect CELEX prefix 32022R2555
  was initially encountered in secondary sources. This was corrected after direct
  verification of the EUR-Lex page, which confirms CELEX:32022L2555.

### Inference
- IN1: [Inference] The NIS2 Directive is related to the CRA through Article 69(1) of
  the CRA, which requires the Commission to consult the ENISA Management Board and
  the CSIRTs network on matters related to the CRA's implementation.

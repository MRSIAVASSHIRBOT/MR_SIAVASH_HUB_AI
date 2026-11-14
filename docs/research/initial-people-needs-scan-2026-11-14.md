# Initial People-Needs Research Scan — 2026-11-14

## Scope and confidence

This is a first-pass scan of small-business and solo-operator needs, not a representative survey of all people or all countries. Evidence combines three institutional/business surveys and one public community discussion. Survey populations and commercial interests differ; percentages must not be combined or treated as global prevalence. The Reddit post is one self-reported case and is useful for discovering workflow details, not estimating how common they are.

## Evidence register

### 1. Digital work is fragmented; owners want fewer tools

- U.S. Bank's 2025 Small Business Perspective survey sampled 1,000 U.S. owners of businesses with annual revenue up to $25 million and 2–99 employees. It reports that 63% feel overwhelmed by the number of tools needed to run their business and 82% say consolidation is a priority.
- A 2026 inTandem/vCita report, based on 500 service-based small-business owners in its 2025 end-of-year survey, reports that 43% would pay more for a solution that reduces the number of tools used. It also reports that 59% feel more comfortable with AI when they can approve each action.
- Interpretation: a coherent command centre and reliable integrations may solve more than another isolated AI feature. The product must show what it will do, what it did, and what needs approval.

Sources:
- https://www.usbank.com/about-us-bank/company-blog/article-library/us-bank-survey-looks-at-small-business-stressors-ai-and-succession-plans.html
- https://intandem.vcita.com/content-hub/the-2026-small-business-digital-adoption-report

### 2. Time, cost, skills, and content are recurring adoption barriers

- CFIB's September 2025 survey of 2,478 Canadian independent-business owners includes 2,355 responses to its digital-tool challenge question. The reported challenges include limited time to manage tools consistently (66%), setup and maintenance cost (45%), keeping up with changes (43%), lack of technical skills or training (42%), difficulty creating quality content (31%), and difficulty integrating systems (21%).
- OECD's 2025 D4SME survey covers 1,009 responses across ten OECD countries. It reports maintenance costs (40%), time for training (39%), and hardware costs (32%) as leading digitalisation barriers. The paper also reports AI-app use among surveyed SMEs rising from 26% in 2024 to 39% in 2025.
- Interpretation: reduce setup and maintenance effort, avoid tool sprawl, provide guided onboarding, and make routine content operations less time-consuming.

Sources:
- https://www.cfib-fcei.ca/hubfs/Your%20Voice%20Survey%20September%202025_111225.pdf
- https://www.oecd.org/en/publications/sme-digitalisation-for-competitiveness_197e3077-en.html

### 3. Solo operators lose time to fragmented administration

- A February 2026 public r/smallbusiness discussion describes one solo consultant's workload: email and follow-ups, meeting preparation and notes, invoicing reminders, documents scattered across storage services, and repetitive client questions. The author reports spending multiple hours each day on some of these activities.
- This is one anecdote, not a prevalence estimate. It gives concrete workflow examples that can be checked against further independent discussions and interviews.
- Interpretation: a permissioned operations assistant could classify requests, find relevant owner-approved documents, prepare follow-ups, draft answers, and create reminders—while leaving external messages and financial actions for human approval.

Source:
- https://www.reddit.com/r/smallbusiness/comments/1r307db/how_did_you_reduce_admin_time_as_a_solo_business/

## Opportunity candidates

These are hypotheses for validation, not confirmed product-market fit.

| Candidate | Problem hypothesis | Proposed first product slice | Evidence strength | Existing Hub fit |
|---|---|---|---|---|
| Unified small-business command centre | Users switch between tools and struggle to keep information and tasks coordinated | One dashboard that links tasks, knowledge, content, documents, and approved integrations | Medium-high: two surveys, different samples | High: shared API, workflows, memory, knowledge, tool registry |
| Human-approved admin automation | Repetitive email, follow-up, meeting, and document work consumes time | Draft-first workflows for triage, summaries, reminders, and handoff | Medium: survey barriers plus one detailed anecdote | High: agent, jobs, policy, approvals; email/calendar connectors still needed |
| Low-maintenance website service | Some small firms struggle with setup, technical upkeep, cost, and choosing tools | Guided site brief, editable starter site, content updates, health checks, reviewed deployment | Medium: CFIB digital adoption findings; needs more direct owner evidence | Low-medium: developer/code foundations exist; website product pipeline is not built |
| Content-to-distribution workflow | Owners lack time and skills to create and maintain consistent quality content | One brief to reusable content assets, channel drafts, scheduling, and performance review | Medium-high: CFIB survey and U.S. Bank use-case data | High: content/media/scheduling foundations already exist |
| Customer-support knowledge assistant | Repeated questions and follow-ups interrupt service work | Search approved FAQs/documents, draft a context-aware reply, route uncertain cases to a human | Medium: one community case plus broad admin-work evidence | Medium: knowledge, memory, agents exist; ticket/inbox adapters are missing |
| Document and client-work organizer | Important documents and notes are scattered and hard to retrieve | Owner-scoped document intake, metadata, search, meeting-note summaries, and reminders | Medium: OECD skills/maintenance context plus community case | Medium: knowledge and memory foundations exist; richer file parsing is missing |
| Digital setup navigator | Users do not know which tools to choose or how to connect them | Guided needs assessment and a minimal, cost-aware, interoperable setup plan | Medium-high: CFIB and OECD barriers | Medium: discovery catalog and capability registry exist; recommendation workflow is missing |

## Initial priority order

1. **Unified small-business command centre** — highest cross-domain leverage; avoid rebuilding every service as a separate application.
2. **Human-approved admin automation** — strong fit with the existing Agent, Workflow, and Policy architecture.
3. **Content-to-distribution workflow** — reuse the strongest existing product vertical, then add better measurement and workflow reuse.
4. **Customer-support knowledge assistant** — combines knowledge retrieval, memory, drafting, and human handoff.
5. **Document and client-work organizer** — a natural extension of knowledge ingestion, but richer file parsing and retention controls are prerequisites.
6. **Digital setup navigator** — useful as an onboarding and recommendation layer.
7. **Low-maintenance website service** — valuable but requires a distinct site-building, preview, hosting, and deployment vertical.

## Validation rules before implementation

- Do not call a need validated from one post, one vendor survey, or an AI-generated summary.
- Seek at least two independent source URLs from at least two source types for each opportunity before moving it to validated.
- Record geography, population, sample size, date, source limitations, and direct evidence URL.
- Separate observed user statements from our interpretation and proposed solution.
- Prefer reversible prototypes and user interviews before expensive integrations.
- Measure time saved, task completion, error rate, user trust, adoption, and total tool cost—not feature count.

## Immediate next research

Expand beyond small businesses into students, families, independent creators, accessibility needs, community organisations, and everyday digital administration. Use public sources and consent-based interviews; do not collect private personal data or scrape closed communities. Keep the initial small-business vertical as a testable starting segment, not the permanent product boundary.


## Cross-domain scan: creators, educators, and digital accessibility

The first scan was deliberately expanded beyond business owners to avoid turning a broad public-benefit platform into a small-business-only product.

### 4. Independent creators face persistent production pressure

- Epidemic Sound's 2025 report describes a survey of 3,000 professional creators in the United States and United Kingdom. It reports time pressure (36%), burnout (35%), and algorithm complexity/discoverability (34%) among recurring challenges. It also reports broad AI use in content development and generation.
- The publisher is a commercial creator-audio provider, so the findings are useful directional evidence rather than neutral global prevalence.
- Interpretation: creators may need a dependable end-to-end production system—planning, reusable formats, editing, rights-aware asset management, multi-platform adaptation, scheduling, and performance feedback—not simply another text/image generator.

Source:
- https://corporate.epidemicsound.com/press-and-media/press-releases/2025/content-creators-are-the-new-entrepreneurs-epidemic-sound-unveils-the-future-of-the-creator-economy-report-2025/

### 5. Educators report a substantial administrative workload

- OECD TALIS 2024 reports that around 52% of teachers across participating education systems identify general administrative work as a source of stress.
- Pew Research Center's survey of 2,531 U.S. public K–12 teachers reports that 84% do not have enough time during regular work hours to complete tasks such as grading, lesson planning, paperwork, and answering work email.
- Interpretation: a teacher-facing administrative assistant could organize forms, calendars, communications, lesson resources, and routine records. It should not make consequential student decisions or replace educator judgment.

Sources:
- https://www.oecd.org/en/publications/2025/10/results-from-talis-2024_28fbde1d/full-report/the-demands-of-teaching_0e941e2f.html
- https://www.pewresearch.org/social-trends/wp-content/uploads/sites/3/2024/04/ST_24.04.04_teacher-survey_report.pdf

### 6. Accessibility barriers cause people to abandon digital tasks

- Accessiway's 2025 European Digital Accessibility Survey reports 6,599 respondents across Italy, Germany, Austria, France, and the United Kingdom; 73.1% said they regularly encounter digital barriers and 68.4% had abandoned at least one digital process because of a barrier. The survey is published by a commercial accessibility provider, so its findings should be treated as directional and checked against independent accessibility research.
- Intopia's 2025 assistive-technology survey involved 218 people in Australia and New Zealand, 91% of whom reported a disability, impairment, or chronic condition. Across 757 reported online barriers, recurring themes included inaccessible or poorly coded pages, pop-ups/overlays, cognitive load, time cost, and missing form labels.
- Interpretation: accessibility should be a shared engineering quality gate across every generated website and interface, not a separate decorative feature. Include semantic HTML, keyboard navigation, screen-reader labels, clear instructions, readable layouts, reduced cognitive load, and accessible forms from the start.

Sources:
- https://www.accessiway.com/digital-accessibility-survey
- https://surveys.intopia.digital/assistive-technology-survey-2025-results/

## Additional opportunity candidates

| Candidate | Problem hypothesis | Proposed first product slice | Evidence strength | Existing Hub fit |
|---|---|---|---|---|
| Creator production operations | Independent creators face time pressure, workload, and platform complexity | Plan once, generate approved variants, manage assets and rights metadata, schedule, and review results | Medium: 3,000-creator commercial survey | High: existing content/media/scheduling foundations |
| Educator administration assistant | Teachers lose time to paperwork, planning administration, and work email | Organize forms, calendars, class communications, and reusable resources with teacher review | Medium-high: OECD cross-system evidence and Pew U.S. survey | Medium: workflows and knowledge exist; education-specific privacy and interfaces are missing |
| Accessibility-first web quality service | People encounter barriers in forms, navigation, readability, and assistive-technology use | Automated static checks plus human-readable remediation guidance and manual review checklist | Medium: two specialist surveys with different populations | Medium: web/code foundations exist; accessibility audit and remediation pipeline is not built |

## Updated product principle

Accessibility, privacy, and human control are cross-cutting requirements—not optional modules. A useful AI system should reduce work without creating new barriers, preserve the user's ability to review consequential actions, and make its outputs usable by people with different devices, languages, and access needs.

## Research coverage and next gaps

Current evidence is strongest for small-business digital operations, creators, educators, and accessibility. It is still weak for families, older adults, public-service users outside the surveyed countries, community organisations, and people with limited connectivity or digital literacy. These groups require separate research before assigning priorities. Avoid treating the current opportunity order as a universal ranking.

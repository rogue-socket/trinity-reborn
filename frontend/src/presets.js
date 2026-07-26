export const presets = [
  {
    id: "neet-leak",
    kicker: "Education / public trust",
    title: "NEET leak protests",
    summary: "Students, officials, and organisers respond to allegations around a high-stakes entrance exam.",
    accent: "pink",
    eventTitle: "Exam leak allegations surface",
    eventType: "public_demonstration",
    location: "New Delhi",
    actors: ["Student demonstrators", "National examinations board", "Independent education reporters"],
    claim: "A national entrance examination may have been compromised before testing began.",
  },
  {
    id: "fifa-governance",
    kicker: "Sport / power",
    title: "FIFA World Cup corruption",
    summary: "A bid process is under scrutiny as football officials, investigators, and supporters trade competing accounts.",
    accent: "yellow",
    eventTitle: "World Cup bid inquiry opens",
    eventType: "investigation",
    location: "Geneva",
    actors: ["Football ethics panel", "Tournament bid committee", "Supporters coalition"],
    claim: "An international football tournament bid may have involved improper influence.",
  },
  {
    id: "europe-fires",
    kicker: "Climate / survival",
    title: "Europe forest fires",
    summary: "A severe fire season displaces communities while emergency crews and climate researchers track a fast-moving threat.",
    accent: "blue",
    eventTitle: "Wildfire emergency expands",
    eventType: "emergency_response",
    location: "Southern Europe",
    actors: ["Volunteer fire crews", "Regional emergency authority", "Forest communities"],
    claim: "An expanding wildfire emergency is threatening several forest communities.",
  },
];

const graphExtras = {
  "neet-leak": {
    entities: [
      { entity_id: "ent-legal", type: "community_group", name: "Student legal network" },
      { entity_id: "ent-monitor", type: "government_agency", name: "Exam monitoring cell" },
      { entity_id: "ent-campus", type: "city_or_locality", name: "University district" },
    ],
    events: [
      { event_id: "evt-hearing", type: "public_hearing", title: "Emergency review hearing begins", participant_entity_ids: ["ent-legal", "ent-monitor", "ent-group"], location_entity_ids: ["ent-campus"] },
      { event_id: "evt-briefing", type: "press_conference", title: "Examinations board issues briefing", participant_entity_ids: ["ent-institution", "ent-observer"], location_entity_ids: ["ent-place"] },
    ],
    claims: [
      { claim_id: "clm-review", text: "The exam monitoring cell opened a preliminary review after student complaints.", event_id: "evt-hearing", subject_ref: "ent-monitor", object_ref_or_value: "ent-group", asserted_by_entity_id: "ent-legal", epistemic_status: "corroborated" },
      { claim_id: "clm-board", text: "The examinations board said verification procedures were still under way.", event_id: "evt-briefing", subject_ref: "ent-institution", object_ref_or_value: "ent-group", asserted_by_entity_id: "ent-observer", epistemic_status: "reported" },
    ],
  },
  "fifa-governance": {
    entities: [
      { entity_id: "ent-investigator", type: "government_agency", name: "Independent ethics investigators" },
      { entity_id: "ent-host", type: "government_body", name: "Host city council" },
      { entity_id: "ent-whistleblower", type: "person", name: "Former bid adviser" },
      { entity_id: "ent-archive", type: "media_outlet", name: "Sports archive desk" },
    ],
    events: [
      { event_id: "evt-testimony", type: "public_hearing", title: "Former adviser gives testimony", participant_entity_ids: ["ent-whistleblower", "ent-investigator", "ent-archive"], location_entity_ids: ["ent-place"] },
    ],
    claims: [
      { claim_id: "clm-records", text: "Investigators requested records connected to the tournament bid process.", event_id: "evt-demo", subject_ref: "ent-investigator", object_ref_or_value: "ent-institution", asserted_by_entity_id: "ent-archive", epistemic_status: "corroborated" },
      { claim_id: "clm-adviser", text: "A former adviser alleged that informal influence shaped early bid discussions.", event_id: "evt-testimony", subject_ref: "ent-whistleblower", object_ref_or_value: "ent-institution", asserted_by_entity_id: "ent-archive", epistemic_status: "disputed" },
      { claim_id: "clm-council", text: "The host city council said it had not seen evidence of improper conduct.", event_id: "evt-demo", subject_ref: "ent-host", object_ref_or_value: "ent-investigator", asserted_by_entity_id: "ent-archive", epistemic_status: "reported" },
    ],
  },
  "europe-fires": {
    entities: [
      { entity_id: "ent-research", type: "organization", name: "Wildfire research observatory" },
      { entity_id: "ent-evacuation", type: "community_group", name: "Evacuation support network" },
    ],
    events: [
      { event_id: "evt-evacuation", type: "emergency_response", title: "Evacuation corridors open", participant_entity_ids: ["ent-evacuation", "ent-group", "ent-institution"], location_entity_ids: ["ent-place"] },
      { event_id: "evt-forecast", type: "public_briefing", title: "Fire outlook briefing is released", participant_entity_ids: ["ent-research", "ent-observer"], location_entity_ids: ["ent-place"] },
    ],
    claims: [
      { claim_id: "clm-forecast", text: "The observatory forecast elevated fire risk as dry conditions continued.", event_id: "evt-forecast", subject_ref: "ent-research", object_ref_or_value: "ent-place", asserted_by_entity_id: "ent-observer", epistemic_status: "corroborated" },
    ],
  },
};

export function buildPresetSeed(preset) {
  const topicKey = `demo-${preset.id}`;
  const [group, institution, observer] = preset.actors;
  const extra = graphExtras[preset.id];
  const article = `${preset.claim} ${group} called for a public response while ${institution} said it was reviewing the situation. ${observer} gathered testimony from people affected in ${preset.location}.`;

  return {
    topic: {
      topic_key: topicKey,
      display_name: preset.title,
      scope: {
        description: preset.summary,
        geography: [preset.location],
        start: "2026-07-01",
        end: null,
      },
    },
    package: {
      schema_version: "1.0",
      package_id: crypto.randomUUID(),
      topic_key: topicKey,
      metadata: { title: `${preset.title} — demo briefing`, generated_at: new Date().toISOString() },
      sources: [{ source_id: "src-demo" }],
      articles: [{ article_id: "art-demo", source_id: "src-demo", content: article }],
      evidence: [{
        evidence_id: "ev-demo",
        article_id: "art-demo",
        excerpt: preset.claim,
        start_offset: 0,
        end_offset: preset.claim.length,
      }],
      entities: [
        { entity_id: "ent-group", type: "community_group", name: group },
        { entity_id: "ent-institution", type: "organization", name: institution },
        { entity_id: "ent-observer", type: "media_outlet", name: observer },
        { entity_id: "ent-place", type: "city_or_locality", name: preset.location },
        ...extra.entities,
      ],
      events: [{
        event_id: "evt-demo",
        type: preset.eventType,
        title: preset.eventTitle,
        temporal: { start: "2026-07-01T10:00:00Z", precision: "day", basis: "reported" },
        participant_entity_ids: ["ent-group", "ent-institution", "ent-observer"],
        location_entity_ids: ["ent-place"],
        evidence_ids: ["ev-demo"],
      }, ...extra.events.map((event) => ({
        ...event,
        temporal: { start: "2026-07-02T10:00:00Z", precision: "day", basis: "reported" },
        evidence_ids: ["ev-demo"],
      }))],
      claims: [{
        claim_id: "clm-demo",
        text: preset.claim,
        event_id: "evt-demo",
        subject_ref: "ent-institution",
        predicate_candidate: "responded_to",
        object_ref_or_value: "ent-group",
        temporal_scope: { start: "2026-07-01", precision: "day", basis: "reported" },
        asserted_by_entity_id: "ent-observer",
        epistemic_status: "reported",
        evidence_ids: ["ev-demo"],
      }, ...extra.claims.map((claim) => ({
        ...claim,
        predicate_candidate: "responded_to",
        temporal_scope: { start: "2026-07-02", precision: "day", basis: "reported" },
        evidence_ids: ["ev-demo"],
      }))],
      relationships: [{
        relationship_id: "rel-demo",
        subject_ref: "ent-group",
        object_ref: "evt-demo",
        source_relation_label: "participated in",
        evidence_ids: ["ev-demo"],
      }],
    },
  };
}

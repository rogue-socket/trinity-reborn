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

export function buildPresetSeed(preset) {
  const token = crypto.randomUUID().replaceAll("-", "");
  const topicKey = `${preset.id}-${token}`;
  const [group, institution, observer] = preset.actors;
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
      ],
      events: [{
        event_id: "evt-demo",
        type: preset.eventType,
        title: preset.eventTitle,
        temporal: { start: "2026-07-01T10:00:00Z", precision: "day", basis: "reported" },
        participant_entity_ids: ["ent-group", "ent-institution", "ent-observer"],
        location_entity_ids: ["ent-place"],
        evidence_ids: ["ev-demo"],
      }],
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
      }],
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

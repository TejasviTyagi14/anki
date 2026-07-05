// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Per reaction-type mastery, computed inside the Rust engine.
//!
//! "Mastered" for a card = FSRS retrievability >= `min_retrievability` AND the
//! number of passing mechanism grades (stored by the grader in the card's
//! `custom_data` under `mg_pass`) >= `min_pass_grades`. Reaction types come from
//! note tags under a namespace prefix (default `mechgrader::reaction::`), e.g.
//! the tag `mechgrader::reaction::SN1` attributes a card to reaction type
//! `SN1`.
//!
//! This is a read-only aggregation: it performs no writes and creates no undo
//! entries.

use std::collections::HashMap;

use anki_proto::mechgrader::topic_mastery_response::Topic;
use anki_proto::mechgrader::TopicMasteryRequest;
use anki_proto::mechgrader::TopicMasteryResponse;
use fsrs::FSRS;
use fsrs::FSRS5_DEFAULT_DECAY;
use serde_json::Value;

use crate::prelude::*;

const DEFAULT_TAG_PREFIX: &str = "mechgrader::reaction::";
const DEFAULT_MIN_RETRIEVABILITY: f32 = 0.9;
const DEFAULT_MIN_PASS_GRADES: u32 = 2;

#[derive(Default)]
struct TopicAcc {
    total_cards: u32,
    cards_with_memory: u32,
    mastered_cards: u32,
    recall_sum: f32,
}

impl Collection {
    pub(crate) fn compute_topic_mastery(
        &mut self,
        req: TopicMasteryRequest,
    ) -> Result<TopicMasteryResponse> {
        let prefix = if req.tag_prefix.trim().is_empty() {
            DEFAULT_TAG_PREFIX.to_string()
        } else {
            req.tag_prefix.clone()
        };
        let min_retrievability = if req.min_retrievability <= 0.0 {
            DEFAULT_MIN_RETRIEVABILITY
        } else {
            req.min_retrievability
        };
        let min_pass_grades = if req.min_pass_grades == 0 {
            DEFAULT_MIN_PASS_GRADES
        } else {
            req.min_pass_grades
        };

        // Scope to reaction-tagged cards; AND with the caller's search if given.
        // Scoping by tag keeps this fast on large collections: only MechCards
        // are visited, not every card.
        let tag_filter = format!("tag:{prefix}*");
        let search = if req.search.trim().is_empty() {
            tag_filter
        } else {
            format!("({}) AND ({})", req.search, tag_filter)
        };

        let timing = self.timing_today()?;
        let fsrs = FSRS::new(None).unwrap();

        let mut acc: HashMap<String, TopicAcc> = HashMap::new();
        // note id -> its tags, so multi-card notes don't re-query.
        let mut tag_cache: HashMap<NoteId, Vec<String>> = HashMap::new();

        self.for_each_card_in_search(search.as_str(), |col, card| {
            if !tag_cache.contains_key(&card.note_id) {
                let tags = col
                    .storage
                    .get_note(card.note_id)?
                    .map(|n| n.tags)
                    .unwrap_or_default();
                tag_cache.insert(card.note_id, tags);
            }
            let reaction_types: Vec<String> = tag_cache
                .get(&card.note_id)
                .unwrap()
                .iter()
                .filter_map(|t| t.strip_prefix(prefix.as_str()))
                .filter(|s| !s.is_empty())
                .map(str::to_string)
                .collect();
            if reaction_types.is_empty() {
                return Ok(());
            }

            let recall = card.memory_state.map(|state| {
                let elapsed = card.seconds_since_last_review(&timing).unwrap_or_default();
                fsrs.current_retrievability_seconds(
                    state.into(),
                    elapsed,
                    card.decay.unwrap_or(FSRS5_DEFAULT_DECAY),
                )
            });
            let pass_count = mechgrader_pass_count(&card.custom_data);

            for rt in reaction_types {
                let e = acc.entry(rt).or_default();
                e.total_cards += 1;
                if let Some(r) = recall {
                    e.cards_with_memory += 1;
                    e.recall_sum += r;
                    if r >= min_retrievability && pass_count >= min_pass_grades {
                        e.mastered_cards += 1;
                    }
                }
            }
            Ok(())
        })?;

        let mut topics: Vec<Topic> = acc
            .into_iter()
            .map(|(reaction_type, a)| Topic {
                reaction_type,
                total_cards: a.total_cards,
                cards_with_memory: a.cards_with_memory,
                mastered_cards: a.mastered_cards,
                average_recall: if a.cards_with_memory > 0 {
                    a.recall_sum / a.cards_with_memory as f32
                } else {
                    0.0
                },
            })
            .collect();
        topics.sort_by(|a, b| a.reaction_type.cmp(&b.reaction_type));

        Ok(TopicMasteryResponse { topics })
    }
}

/// Count of passing mechanism grades the grader stores in a card's custom_data
/// under "mg_pass". Absent/invalid -> 0.
fn mechgrader_pass_count(custom_data: &str) -> u32 {
    if custom_data.trim().is_empty() {
        return 0;
    }
    serde_json::from_str::<Value>(custom_data)
        .ok()
        .and_then(|v| v.get("mg_pass").and_then(Value::as_u64))
        .unwrap_or(0) as u32
}

#[cfg(test)]
mod test {
    use anki_proto::mechgrader::TopicMasteryRequest;

    use crate::card::CardId;
    use crate::card::FsrsMemoryState;
    use crate::prelude::*;
    use crate::services::MechgraderService;

    fn req() -> TopicMasteryRequest {
        TopicMasteryRequest {
            search: String::new(),
            tag_prefix: String::new(),
            min_retrievability: 0.0,
            min_pass_grades: 0,
        }
    }

    fn add_tagged_card(col: &mut Collection, tags: &[&str]) -> CardId {
        let nt = col.basic_notetype();
        let mut note = nt.new_note();
        note.tags = tags.iter().map(|t| t.to_string()).collect();
        col.add_note(&mut note, DeckId(1)).unwrap();
        col.storage.all_cards_of_note(note.id).unwrap()[0].id
    }

    /// Give a card an FSRS memory state and a mechanism pass count.
    /// `elapsed_days` controls retrievability: 0 -> R ~= 1, large -> R low.
    fn set_state(
        col: &mut Collection,
        cid: CardId,
        stability: f32,
        elapsed_days: i64,
        passes: u32,
        has_memory: bool,
    ) {
        let mut card = col.storage.get_card(cid).unwrap().unwrap();
        if has_memory {
            card.memory_state = Some(FsrsMemoryState {
                stability,
                difficulty: 5.0,
            });
            card.decay = Some(fsrs::FSRS5_DEFAULT_DECAY);
            card.last_review_time =
                Some(TimestampSecs(TimestampSecs::now().0 - elapsed_days * 86_400));
        }
        card.custom_data = format!("{{\"mg_pass\":{passes}}}");
        col.storage.update_card(&card).unwrap();
    }

    #[test]
    fn groups_by_reaction_tag_and_ignores_untagged() {
        let mut col = Collection::new();
        add_tagged_card(&mut col, &["mechgrader::reaction::SN1"]);
        add_tagged_card(&mut col, &["mechgrader::reaction::SN1"]);
        add_tagged_card(&mut col, &["mechgrader::reaction::SN2"]);
        add_tagged_card(&mut col, &["some::other::tag"]); // not a reaction tag
        add_tagged_card(&mut col, &[]); // untagged

        let resp = col.topic_mastery(req()).unwrap();
        let types: Vec<_> = resp.topics.iter().map(|t| t.reaction_type.as_str()).collect();
        assert_eq!(types, vec!["SN1", "SN2"]); // sorted, no others
        assert_eq!(resp.topics[0].total_cards, 2);
        assert_eq!(resp.topics[1].total_cards, 1);
    }

    #[test]
    fn mastered_requires_both_retrievability_and_passes() {
        let mut col = Collection::new();
        let a = add_tagged_card(&mut col, &["mechgrader::reaction::SN1"]);
        let b = add_tagged_card(&mut col, &["mechgrader::reaction::SN1"]);
        let c = add_tagged_card(&mut col, &["mechgrader::reaction::SN1"]);
        let d = add_tagged_card(&mut col, &["mechgrader::reaction::SN1"]);
        set_state(&mut col, a, 100.0, 0, 2, true); // high R + enough passes -> mastered
        set_state(&mut col, b, 100.0, 0, 0, true); // high R, 0 passes -> not mastered
        set_state(&mut col, c, 1.0, 100, 5, true); // low R -> not mastered
        set_state(&mut col, d, 100.0, 0, 5, false); // no memory -> not counted with memory

        let resp = col.topic_mastery(req()).unwrap();
        let sn1 = &resp.topics[0];
        assert_eq!(sn1.reaction_type, "SN1");
        assert_eq!(sn1.total_cards, 4);
        assert_eq!(sn1.cards_with_memory, 3); // a, b, c
        assert_eq!(sn1.mastered_cards, 1); // only a
    }

    #[test]
    fn average_recall_is_over_cards_with_memory_only() {
        let mut col = Collection::new();
        let a = add_tagged_card(&mut col, &["mechgrader::reaction::E2"]);
        let b = add_tagged_card(&mut col, &["mechgrader::reaction::E2"]);
        let c = add_tagged_card(&mut col, &["mechgrader::reaction::E2"]);
        set_state(&mut col, a, 100.0, 0, 0, true); // R ~= 1
        set_state(&mut col, b, 100.0, 0, 0, true); // R ~= 1
        set_state(&mut col, c, 100.0, 0, 0, false); // no memory

        let resp = col.topic_mastery(req()).unwrap();
        let e2 = &resp.topics[0];
        assert_eq!(e2.total_cards, 3);
        assert_eq!(e2.cards_with_memory, 2);
        // mean of two ~1.0 values, NOT diluted by the memoryless card.
        assert!(e2.average_recall > 0.9, "avg was {}", e2.average_recall);
    }

    #[test]
    fn min_pass_grades_override_is_respected() {
        let mut col = Collection::new();
        let a = add_tagged_card(&mut col, &["mechgrader::reaction::E1"]);
        set_state(&mut col, a, 100.0, 0, 1, true); // 1 pass

        // default min_pass_grades = 2 -> not mastered
        assert_eq!(col.topic_mastery(req()).unwrap().topics[0].mastered_cards, 0);

        // override to 1 -> mastered
        let mut r = req();
        r.min_pass_grades = 1;
        assert_eq!(col.topic_mastery(r).unwrap().topics[0].mastered_cards, 1);
    }

    #[test]
    fn read_only_query_does_not_break_undo() {
        let mut col = Collection::new();
        // an undoable op
        add_tagged_card(&mut col, &["mechgrader::reaction::SN1"]);
        assert!(col.can_undo().is_some());
        let notes_before = col.storage.get_all_notes().len();

        // running the query must not consume the undo entry or mutate anything
        let _ = col.topic_mastery(req()).unwrap();

        assert!(col.can_undo().is_some(), "query should not clear undo");
        col.undo().unwrap();
        assert_eq!(col.storage.get_all_notes().len(), notes_before - 1);
    }
}

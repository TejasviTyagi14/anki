// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! MechGrader fork: mastery-aware review pipeline backend.
//!
//! Stage 0 ships only a liveness probe (`mechgrader_engine_info`) to prove the
//! proto -> Rust -> Python bridge is wired against the forked engine. Stage 1
//! adds the substantive `topic_mastery` query and the `points_at_stake` review
//! ordering to this same service.

use anki_proto::mechgrader::EngineInfoResponse;

use crate::prelude::*;

impl crate::services::MechgraderService for Collection {
    fn mechgrader_engine_info(&mut self) -> Result<EngineInfoResponse> {
        let anki_version = crate::version::version().to_string();
        let build_hash = crate::version::buildhash().to_string();
        Ok(EngineInfoResponse {
            info: format!("MechGrader engine live on Anki {anki_version} ({build_hash})"),
            anki_version,
            build_hash,
        })
    }
}

#[cfg(test)]
mod test {
    use crate::collection::CollectionBuilder;
    use crate::services::MechgraderService;

    #[test]
    fn engine_info_is_reachable_and_mentions_mechgrader() {
        let mut col = CollectionBuilder::default().build().unwrap();
        let info = col.mechgrader_engine_info().unwrap();
        assert!(
            info.info.contains("MechGrader engine live"),
            "unexpected engine info: {}",
            info.info
        );
        assert!(!info.anki_version.is_empty());
    }
}

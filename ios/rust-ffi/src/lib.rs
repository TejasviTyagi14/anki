// C FFI over the forked Anki engine (`anki` / rslib) for the iOS app.
//
// The whole point: the iOS app calls the SAME Rust engine RPC the desktop uses
// (`MechgraderService::mechgrader_engine_info` on a real `Collection`), compiled
// natively for the phone — not a reimplementation and not the WebView. This is
// the Swift analogue of `mechgrader/tools/stage0_engine_probe.py` (which proves
// the same thing over the Python/rsbridge FFI).

use std::ffi::CStr;
use std::ffi::CString;
use std::os::raw::c_char;

use anki::backend::Backend;
use anki::collection::CollectionBuilder;
use anki::decks::DeckId;
use anki::services::BackendCollectionService;
use anki::services::BackendSyncService;
use anki::services::MechgraderService;
use anki_i18n::I18n;
use anki_proto::collection::OpenCollectionRequest;
use anki_proto::sync::FullUploadOrDownloadRequest;
use anki_proto::sync::SyncCollectionRequest;
use anki_proto::sync::SyncLoginRequest;

/// Run the forked engine's `mechgrader_engine_info` RPC on an in-memory
/// collection and return its message (e.g. "MechGrader engine live on Anki
/// 26.05 (<buildhash>)"). Ownership transfers to the caller — free with
/// [`mechgrader_string_free`].
///
/// # Safety
/// The returned pointer must be freed exactly once via `mechgrader_string_free`.
#[no_mangle]
pub extern "C" fn mechgrader_engine_info() -> *mut c_char {
    let message = engine_info_message();
    CString::new(message)
        .unwrap_or_else(|_| CString::new("MechGrader engine: <string error>").unwrap())
        .into_raw()
}

fn engine_info_message() -> String {
    match CollectionBuilder::default().build() {
        Ok(mut col) => match col.mechgrader_engine_info() {
            Ok(info) => info.info,
            Err(err) => format!("mechgrader_engine_info error: {err}"),
        },
        Err(err) => format!("collection build error: {err}"),
    }
}

/// Free a string returned by this library.
///
/// # Safety
/// `ptr` must have come from [`mechgrader_engine_info`] and not been freed yet.
#[no_mangle]
pub extern "C" fn mechgrader_string_free(ptr: *mut c_char) {
    if !ptr.is_null() {
        unsafe {
            drop(CString::from_raw(ptr));
        }
    }
}

// --------------------------------------------------------------------------- //
// Phone -> desktop sync: add a card in a local collection on the phone and push
// it to a self-hosted Anki sync server (the SAME sync the desktop uses), so a
// desktop syncing from that server receives the card. This is the native engine
// doing real Anki sync from the phone.
// --------------------------------------------------------------------------- //

/// Create/open a collection under `base_dir`, add a Basic card (`front`/`back`)
/// to the Default deck, then sync-upload it to the Anki sync server at
/// `endpoint` with `username`/`password`. Returns a JSON string
/// `{"ok":bool,"message":str}`. Free it with [`mechgrader_string_free`].
///
/// # Safety
/// All arguments must be valid NUL-terminated C strings (or null).
#[no_mangle]
pub extern "C" fn mechgrader_sync_push(
    base_dir: *const c_char,
    endpoint: *const c_char,
    username: *const c_char,
    password: *const c_char,
    front: *const c_char,
    back: *const c_char,
) -> *mut c_char {
    let json = match sync_push(
        &cstr(base_dir),
        &cstr(endpoint),
        &cstr(username),
        &cstr(password),
        &cstr(front),
        &cstr(back),
    ) {
        Ok(msg) => format!("{{\"ok\":true,\"message\":{}}}", json_string(&msg)),
        Err(err) => format!("{{\"ok\":false,\"message\":{}}}", json_string(&err)),
    };
    CString::new(json)
        .unwrap_or_else(|_| CString::new("{\"ok\":false,\"message\":\"<enc error>\"}").unwrap())
        .into_raw()
}

fn cstr(ptr: *const c_char) -> String {
    if ptr.is_null() {
        return String::new();
    }
    unsafe { CStr::from_ptr(ptr) }.to_string_lossy().into_owned()
}

fn json_string(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// Add a card to a local collection and push it to the sync server. Reuses the
/// exact Backend sync methods the desktop uses (login → collection sync → full
/// upload). Returns a human-readable status on success.
pub fn sync_push(
    base_dir: &str,
    endpoint: &str,
    username: &str,
    password: &str,
    front: &str,
    back: &str,
) -> Result<String, String> {
    let base = std::path::Path::new(base_dir);
    let col_path = base.join("collection.anki2");
    let media_folder = base.join("collection.media");
    let media_db = base.join("collection.media.db");
    std::fs::create_dir_all(&media_folder).ok();

    // 1) Open (creating if needed) the collection and add a MechGrader card.
    let note_count = {
        let mut builder = CollectionBuilder::new(&col_path);
        builder.set_tr(I18n::template_only());
        let mut col = builder.build().map_err(|e| format!("open collection: {e}"))?;
        let notetype = col
            .get_notetype_by_name("Basic")
            .map_err(|e| format!("notetype lookup: {e}"))?
            .ok_or_else(|| "no 'Basic' notetype in a fresh collection".to_string())?;
        let mut note = notetype.new_note();
        note.set_field(0, front).map_err(|e| format!("set front: {e}"))?;
        if note.fields().len() > 1 {
            note.set_field(1, back).map_err(|e| format!("set back: {e}"))?;
        }
        col.add_note(&mut note, DeckId(1))
            .map_err(|e| format!("add note: {e}"))?;
        let count = col
            .search_notes_unordered("")
            .map(|v| v.len())
            .unwrap_or(0);
        col.close(None).map_err(|e| format!("close: {e}"))?;
        count
    };

    // 2) Open in a Backend and sync-upload to the server.
    let backend = Backend::new(I18n::template_only(), false);
    backend
        .open_collection(OpenCollectionRequest {
            collection_path: col_path.to_string_lossy().into_owned(),
            media_folder_path: media_folder.to_string_lossy().into_owned(),
            media_db_path: media_db.to_string_lossy().into_owned(),
        })
        .map_err(|e| format!("backend open: {e}"))?;

    let auth = backend
        .sync_login(SyncLoginRequest {
            username: username.to_string(),
            password: password.to_string(),
            endpoint: Some(endpoint.to_string()),
        })
        .map_err(|e| format!("sync_login (server reachable?): {e}"))?;

    let out = backend
        .sync_collection(SyncCollectionRequest {
            auth: Some(auth.clone()),
            sync_media: false,
        })
        .map_err(|e| format!("sync_collection: {e}"))?;

    // ChangesRequired: NO_CHANGES=0, NORMAL_SYNC=1, FULL_SYNC=2, FULL_DOWNLOAD=3, FULL_UPLOAD=4
    let action = if out.required == 2 || out.required == 4 {
        backend
            .full_upload_or_download(FullUploadOrDownloadRequest {
                auth: Some(auth),
                upload: true,
                server_usn: None,
            })
            .map_err(|e| format!("full upload: {e}"))?;
        "full-upload"
    } else if out.required == 0 {
        "no-changes (already in sync)"
    } else {
        "normal-sync"
    };

    Ok(format!(
        "pushed {note_count} card(s) to {endpoint} [{action}]"
    ))
}

#[cfg(test)]
mod tests {
    use super::engine_info_message;

    #[test]
    fn engine_info_mentions_mechgrader() {
        assert!(engine_info_message().contains("MechGrader engine live"));
    }
}

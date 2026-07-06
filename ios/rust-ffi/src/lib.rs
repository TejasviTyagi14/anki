// C FFI over the forked Anki engine (`anki` / rslib) for the iOS app.
//
// The whole point: the iOS app calls the SAME Rust engine RPC the desktop uses
// (`MechgraderService::mechgrader_engine_info` on a real `Collection`), compiled
// natively for the phone — not a reimplementation and not the WebView. This is
// the Swift analogue of `mechgrader/tools/stage0_engine_probe.py` (which proves
// the same thing over the Python/rsbridge FFI).

use std::ffi::CString;
use std::os::raw::c_char;

use anki::collection::CollectionBuilder;
use anki::services::MechgraderService;

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

#[cfg(test)]
mod tests {
    use super::engine_info_message;

    #[test]
    fn engine_info_mentions_mechgrader() {
        assert!(engine_info_message().contains("MechGrader engine live"));
    }
}

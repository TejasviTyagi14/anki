// C declarations for the Rust FFI over the forked Anki engine (ios/rust-ffi).
// Imported into Swift via `-import-objc-header` (see ios/build_sim.sh).
#ifndef MECHGRADER_FFI_H
#define MECHGRADER_FFI_H

// Runs the forked engine's mechgrader_engine_info RPC natively and returns a
// heap string owned by the caller (free with mechgrader_string_free).
char *mechgrader_engine_info(void);

// Adds a Basic card (front/back) to a local collection under base_dir and
// sync-uploads it to the Anki sync server at endpoint (username/password).
// Returns a JSON string {"ok":bool,"message":str} owned by the caller.
char *mechgrader_sync_push(const char *base_dir, const char *endpoint,
                           const char *username, const char *password,
                           const char *front, const char *back);

// Frees a string returned by this library.
void mechgrader_string_free(char *ptr);

#endif /* MECHGRADER_FFI_H */

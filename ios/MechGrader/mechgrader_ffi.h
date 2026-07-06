// C declarations for the Rust FFI over the forked Anki engine (ios/rust-ffi).
// Imported into Swift via `-import-objc-header` (see ios/build_sim.sh).
#ifndef MECHGRADER_FFI_H
#define MECHGRADER_FFI_H

// Runs the forked engine's mechgrader_engine_info RPC natively and returns a
// heap string owned by the caller (free with mechgrader_string_free).
char *mechgrader_engine_info(void);

// Frees a string returned by mechgrader_engine_info.
void mechgrader_string_free(char *ptr);

#endif /* MECHGRADER_FFI_H */

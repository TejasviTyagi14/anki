// Host runner for the iOS "Sync card to desktop" button's action: it calls the
// SAME `mechgrader_ffi::sync_push` the Swift button calls, so the automated
// verification (mechgrader/tools/sync_ios_verify.py) exercises the real code path.
//
// Usage:
//   cargo run -p mechgrader_ffi --example sync_push_demo -- \
//       <base_dir> <endpoint> <user> <pass> <front> <back>

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 7 {
        eprintln!("usage: sync_push_demo <base_dir> <endpoint> <user> <pass> <front> <back>");
        std::process::exit(2);
    }
    match mechgrader_ffi::sync_push(&a[1], &a[2], &a[3], &a[4], &a[5], &a[6]) {
        Ok(msg) => println!("OK {msg}"),
        Err(err) => {
            eprintln!("ERR {err}");
            std::process::exit(1);
        }
    }
}

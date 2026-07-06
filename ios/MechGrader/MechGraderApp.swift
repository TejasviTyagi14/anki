// MechGrader iOS shell — a minimal SwiftUI app that hosts the SHARED web/mechgrader
// bundle in a WKWebView (the same editor bundle desktop/Android use). This is the
// WebView companion; the native shared-engine path (rslib via a Swift FFI) is the
// documented next step (docs/mobile.md). Built for the iOS Simulator with swiftc.
//
// The bundle is served through a custom URL scheme (mgapp://) rather than file://
// so ES-module scripts load with a correct JS MIME type (file:// serves the wrong
// MIME and modules silently fail to execute).
import SwiftUI
import WebKit

@main
struct MechGraderApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

/// Calls the SAME forked Rust engine RPC the desktop uses, compiled natively for
/// the phone (ios/rust-ffi over rslib). Proves the engine is shared, not a
/// reimplementation. Returns e.g. "MechGrader engine live on Anki 26.05 (<hash>)".
func nativeEngineInfo() -> String {
    guard let ptr = mechgrader_engine_info() else { return "native engine: <null>" }
    defer { mechgrader_string_free(ptr) }
    return String(cString: ptr)
}

/// Adds a card to a local collection in the app's Documents dir and sync-uploads
/// it to `endpoint` — the native engine doing real Anki sync from the phone.
func nativeSyncPush(endpoint: String) -> String {
    let docs = FileManager.default
        .urls(for: .documentDirectory, in: .userDomainMask).first?.path
        ?? NSTemporaryDirectory()
    let front = "SN2 mechanism — synced from iPhone"
    let back = "hydroxide + bromomethane (backside attack)"
    guard let ptr = mechgrader_sync_push(docs, endpoint, "tester", "pw-abc-12345", front, back)
    else { return "sync: <null>" }
    defer { mechgrader_string_free(ptr) }
    return String(cString: ptr)
}

private let PRIMARY = Color(red: 0.76, green: 0.25, blue: 0.05)

struct ContentView: View {
    @State private var engine: String = "querying native engine…"
    @State private var endpoint: String = "http://localhost:27701"
    @State private var syncMsg: String = ""
    @State private var syncing = false

    var body: some View {
        VStack(spacing: 0) {
            // Native engine banner (proves the phone runs rslib natively).
            VStack(alignment: .leading, spacing: 3) {
                Text("NATIVE RUST ENGINE (rslib) ON THIS PHONE")
                    .font(.system(size: 10, weight: .bold)).foregroundColor(PRIMARY)
                Text(engine)
                    .font(.system(.footnote, design: .monospaced))
                    .foregroundColor(Color(red: 0.11, green: 0.10, blue: 0.09))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 14).padding(.vertical, 8)
            .background(Color(red: 0.992, green: 0.914, blue: 0.867))

            // Phone -> desktop sync (native engine does real Anki sync).
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    TextField("sync server", text: $endpoint)
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                        .font(.system(size: 12, design: .monospaced))
                    Button(action: doSync) {
                        Text(syncing ? "Syncing…" : "Sync card → desktop")
                            .font(.system(size: 13, weight: .bold)).foregroundColor(.white)
                            .padding(.horizontal, 12).padding(.vertical, 9)
                            .background(PRIMARY).cornerRadius(8)
                    }
                    .disabled(syncing)
                }
                if !syncMsg.isEmpty {
                    Text(syncMsg)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 14).padding(.vertical, 8)
            .background(Color(red: 1.0, green: 0.973, blue: 0.949))

            MechWebView().ignoresSafeArea(.container, edges: .bottom)
        }
        .onAppear { engine = nativeEngineInfo() }
    }

    private func doSync() {
        syncing = true
        syncMsg = "syncing to \(endpoint)…"
        let ep = endpoint
        DispatchQueue.global().async {
            let result = nativeSyncPush(endpoint: ep)
            DispatchQueue.main.async {
                syncMsg = result
                syncing = false
            }
        }
    }
}

final class BundleSchemeHandler: NSObject, WKURLSchemeHandler {
    static func mime(for path: String) -> String {
        if path.hasSuffix(".html") { return "text/html; charset=utf-8" }
        if path.hasSuffix(".js") || path.hasSuffix(".mjs") { return "text/javascript; charset=utf-8" }
        if path.hasSuffix(".css") { return "text/css; charset=utf-8" }
        if path.hasSuffix(".json") { return "application/json; charset=utf-8" }
        if path.hasSuffix(".wasm") { return "application/wasm" }
        if path.hasSuffix(".svg") { return "image/svg+xml" }
        return "application/octet-stream"
    }

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else {
            task.didFailWithError(NSError(domain: "mgapp", code: 400)); return
        }
        var rel = url.path
        if rel.isEmpty || rel == "/" { rel = "/index.html" }
        rel = String(rel.drop(while: { $0 == "/" }))  // e.g. "editor.js" or "vendor/rdkit/RDKit_minimal.wasm"
        // Resolve against the bundled web/ dir so nested paths (vendor/rdkit/…) work.
        guard let webRoot = Bundle.main.resourceURL?.appendingPathComponent("web") else {
            task.didFailWithError(NSError(domain: "mgapp", code: 500)); return
        }
        let fileURL = webRoot.appendingPathComponent(rel)
        guard let data = try? Data(contentsOf: fileURL) else {
            task.didFailWithError(NSError(domain: "mgapp", code: 404,
                userInfo: [NSLocalizedDescriptionKey: "not found: \(rel)"]))
            return
        }
        let resp = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": BundleSchemeHandler.mime(for: rel),
                           "Access-Control-Allow-Origin": "*"])!
        task.didReceive(resp)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}

struct MechWebView: UIViewRepresentable {
    // Keep a strong ref so the scheme handler outlives makeUIView.
    final class Coordinator { let handler = BundleSchemeHandler() }
    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(context.coordinator.handler, forURLScheme: "mgapp")
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isInspectable = true
        webView.load(URLRequest(url: URL(string: "mgapp://app/index.html")!))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

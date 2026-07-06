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
            ContentView().ignoresSafeArea()
        }
    }
}

struct ContentView: View {
    var body: some View {
        MechWebView().ignoresSafeArea()
    }
}

final class BundleSchemeHandler: NSObject, WKURLSchemeHandler {
    static func mime(for path: String) -> String {
        if path.hasSuffix(".html") { return "text/html; charset=utf-8" }
        if path.hasSuffix(".js") || path.hasSuffix(".mjs") { return "text/javascript; charset=utf-8" }
        if path.hasSuffix(".css") { return "text/css; charset=utf-8" }
        if path.hasSuffix(".json") { return "application/json; charset=utf-8" }
        if path.hasSuffix(".svg") { return "image/svg+xml" }
        return "application/octet-stream"
    }

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else {
            task.didFailWithError(NSError(domain: "mgapp", code: 400)); return
        }
        var rel = url.path
        if rel.isEmpty || rel == "/" { rel = "/index.html" }
        rel = String(rel.drop(while: { $0 == "/" }))           // "editor.js"
        let name = (rel as NSString).deletingPathExtension       // "editor"
        let ext = (rel as NSString).pathExtension                // "js"
        guard let fileURL = Bundle.main.url(forResource: name, withExtension: ext, subdirectory: "web"),
              let data = try? Data(contentsOf: fileURL) else {
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

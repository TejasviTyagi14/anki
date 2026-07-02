import SwiftUI
import PencilKit
import Vision

/// Stylus-first ink surface for answering a card by hand.
///
/// Deliberately minimal: a single fixed pen and an eraser — no thin/medium/thick
/// width picker and no `PKToolPicker`. `drawingPolicy = .anyInput` lets it also
/// accept finger/trackpad input so it works in the Simulator (which has no Pencil).
struct HandwritingCanvas: UIViewRepresentable {
    @Binding var drawing: PKDrawing
    var isEraser: Bool

    private static let inkColor = UIColor(red: 0.10, green: 0.12, blue: 0.14, alpha: 1)

    func makeUIView(context: Context) -> PKCanvasView {
        let canvas = PKCanvasView()
        canvas.drawingPolicy = .anyInput
        canvas.backgroundColor = .clear
        canvas.isOpaque = false
        canvas.tool = tool
        canvas.delegate = context.coordinator
        return canvas
    }

    func updateUIView(_ canvas: PKCanvasView, context: Context) {
        canvas.tool = tool
        // Reflect external resets (e.g. Clear / next card) without clobbering
        // in-progress strokes. PKStroke isn't Equatable, so compare counts.
        if canvas.drawing.strokes.count != drawing.strokes.count {
            canvas.drawing = drawing
        }
    }

    private var tool: PKTool {
        isEraser ? PKEraserTool(.vector) : PKInkingTool(.pen, color: Self.inkColor, width: 6)
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, PKCanvasViewDelegate {
        let parent: HandwritingCanvas
        init(_ parent: HandwritingCanvas) { self.parent = parent }
        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            parent.drawing = canvasView.drawing
        }
    }
}

enum Handwriting {
    /// Turn an ink drawing into typed text.
    ///
    /// This is the "how Notes does it" step. Notes/Freeform use Apple's on-device
    /// handwriting model; on iPadOS 27 that engine is public as `PKStrokeRecognizer`
    /// (`await recognizer.updateDrawing(drawing); recognizer.recognizedText`).
    /// On this SDK we get equivalent on-device results by rasterizing the strokes
    /// and running Vision OCR — no network, fully offline.
    static func recognize(_ drawing: PKDrawing) async -> String {
        let bounds = drawing.bounds
        guard bounds.width > 1, bounds.height > 1 else { return "" }

        let padded = bounds.insetBy(dx: -24, dy: -24)
        let inked = drawing.image(from: padded, scale: 3)

        // Composite onto white so dark ink reads well for OCR.
        let renderer = UIGraphicsImageRenderer(size: inked.size)
        let composited = renderer.image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(origin: .zero, size: inked.size))
            inked.draw(at: .zero)
        }
        guard let cg = composited.cgImage else { return "" }

        return await withCheckedContinuation { cont in
            let request = VNRecognizeTextRequest { req, _ in
                let text = (req.results as? [VNRecognizedTextObservation] ?? [])
                    .compactMap { $0.topCandidates(1).first?.string }
                    .joined(separator: " ")
                cont.resume(returning: text)
            }
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true
            let handler = VNImageRequestHandler(cgImage: cg, options: [:])
            do { try handler.perform([request]) } catch { cont.resume(returning: "") }
        }
    }
}

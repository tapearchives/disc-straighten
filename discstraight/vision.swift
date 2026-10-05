import Foundation
import Vision

do {
    guard CommandLine.arguments.count == 3 else {
        throw NSError(domain: "disc-straighten", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "Usage: vision image language,language"])
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    let supported = try request.supportedRecognitionLanguages()
    let desired = CommandLine.arguments[2].split(separator: ",").map(String.init)
    let unsupported = desired.filter { !supported.contains($0) }
    guard unsupported.isEmpty else {
        throw NSError(domain: "disc-straighten", code: 2,
                      userInfo: [NSLocalizedDescriptionKey: "Unsupported OCR languages: \(unsupported); available: \(supported)"])
    }
    request.recognitionLanguages = desired
    request.usesLanguageCorrection = false
    request.minimumTextHeight = 0.004
    try VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1])).perform([request])
    let rows: [[String: Any]] = (request.results ?? []).compactMap { observation in
        guard let text = observation.topCandidates(1).first else { return nil }
        return ["text": text.string, "confidence": text.confidence,
                "bottom_left": [observation.bottomLeft.x, observation.bottomLeft.y],
                "bottom_right": [observation.bottomRight.x, observation.bottomRight.y],
                "top_left": [observation.topLeft.x, observation.topLeft.y],
                "top_right": [observation.topRight.x, observation.topRight.y]]
    }
    let result: [String: Any] = ["languages": request.recognitionLanguages,
                               "revision": request.revision, "rows": rows]
    print(String(data: try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), encoding: .utf8)!)
} catch {
    FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
    exit(1)
}

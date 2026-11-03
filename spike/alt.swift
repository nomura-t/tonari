// 試し: SpeechTranscriber と DictationTranscriber で、文脈の語と別候補の効き方を比べる
import AVFoundation
import Foundation
import Speech

@main
struct Alt {
  static func main() async throws {
    let a = CommandLine.arguments
    let path = a[1], engine = a[2]
    let words = a.count > 3 ? (try String(contentsOfFile: a[3], encoding: .utf8)).split(separator: "\n").map(String.init) : []
    let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
    let loc = Locale(identifier: "ja_JP")
    var outs: [String] = []
    if engine == "speech" {
      let t = SpeechTranscriber(locale: loc, transcriptionOptions: [], reportingOptions: [.alternativeTranscriptions], attributeOptions: [])
      let an = SpeechAnalyzer(modules: [t])
      if !words.isEmpty { let c = AnalysisContext(); c.contextualStrings[.general] = words; try await an.setContext(c) }
      let col = Task { var o: [String] = []; for try await r in t.results where r.isFinal { o.append(String(r.text.characters) + "  ||alts: " + r.alternatives.prefix(4).map { String($0.characters) }.joined(separator: " | ")) }; return o }
      if let last = try await an.analyzeSequence(from: file) { try await an.finalizeAndFinish(through: last) }
      outs = try await col.value
    } else {
      if !(await DictationTranscriber.installedLocales).contains(where: { $0.identifier(.bcp47) == loc.identifier(.bcp47) }) {
        let t0 = DictationTranscriber(locale: loc, preset: .longDictation)
        if let req = try await AssetInventory.assetInstallationRequest(supporting: [t0]) { try await req.downloadAndInstall() }
      }
      let t = DictationTranscriber(locale: loc, contentHints: [], transcriptionOptions: [.punctuation], reportingOptions: [.alternativeTranscriptions], attributeOptions: [])
      let an = SpeechAnalyzer(modules: [t])
      if !words.isEmpty { let c = AnalysisContext(); c.contextualStrings[.general] = words; try await an.setContext(c) }
      let col = Task { var o: [String] = []; for try await r in t.results where r.isFinal { o.append(String(r.text.characters) + "  ||alts: " + r.alternatives.prefix(4).map { String($0.characters) }.joined(separator: " | ")) }; return o }
      if let last = try await an.analyzeSequence(from: file) { try await an.finalizeAndFinish(through: last) }
      outs = try await col.value
    }
    print(outs.joined(separator: "\n"))
  }
}

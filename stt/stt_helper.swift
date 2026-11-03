// stt_helper.swift — Apple の SpeechAnalyzer / SpeechTranscriber で音声ファイルを文字起こしし、
// 標準出力に JSON を1つだけ出す。となりの Python サーバーから子プロセスとして呼ばれる。
// 作者の別のアプリの道具に、文脈の語（--context）と確信度（low）と別候補（alts）の出力を足したもの。
//
// 使い方: stt-helper <音声ファイル> [ロケール（既定 ja_JP）] [--context <語の一覧ファイル（1行1語）>]
// 出力:   {"text": 全文, "segments": [{"text", "start", "end", "conf"}], "low": [{"text", "conf"}], "alts": [{"text", "alts"}],
//          "context": 渡した語の数, "elapsed": 処理秒数, "locale": "ja_JP"}
// エラー: 標準エラーに「コード: 説明」の1行を書き、終了コード1。
//         コード = usage / file_not_found / audio_unreadable / unavailable /
//                  locale_unsupported / model_not_installed / transcription_failed
//
// segments の時刻は、確定結果の文字ごとの属性 audioTimeRange の最小の開始と最大の終了。
// 結果の range（CMTimeRange）は無音を含めて音声全体を隙間なく敷き詰める区間なので使わず、
// 時刻つきの文字が1つも無い結果のときだけ range に落とす（2026-10-20 実測で決めた）。

import AVFoundation
import CoreMedia
import Foundation
import Speech

struct Segment: Encodable {
  let text: String
  let start: Double
  let end: Double
  let conf: Double?  // 文字の確信度の最小値（属性が無ければ nil）
}

struct LowSpan: Encodable {
  let text: String
  let conf: Double
}

struct AltSpan: Encodable {
  let text: String
  let alts: [String]
}

struct Output: Encodable {
  let text: String
  let segments: [Segment]
  let low: [LowSpan]
  let alts: [AltSpan]
  let context: Int
  let elapsed: Double
  let locale: String
}

/// 確信度がこれより低い連なりを low に出す（整形役に「聞き取りが怪しい箇所」として渡す）。
let lowConfidence = 0.5
var lowSpans: [LowSpan] = []
/// 確定結果ごとの別候補（1位と違うものだけ・3つまで）。SpeechTranscriber は文脈の語（contextualStrings）を
/// 渡しても結果が変わらなかった（2026-10-29 実測）ので、整形役には別候補と確信度を手がかりとして渡す。
var altSpans: [AltSpan] = []

func fail(_ code: String, _ message: String) -> Never {
  let line = "\(code): \(message)"
    .replacingOccurrences(of: "\r", with: " ")
    .replacingOccurrences(of: "\n", with: " ")
  FileHandle.standardError.write((line + "\n").data(using: .utf8)!)
  exit(1)
}

func round3(_ x: Double) -> Double { (x * 1000).rounded() / 1000 }
func floor3(_ x: Double) -> Double { (x * 1000).rounded(.down) / 1000 }

func seconds(_ d: Duration) -> Double {
  let c = d.components
  return Double(c.seconds) + Double(c.attoseconds) / 1e18
}

func sameLocale(_ a: Locale, _ b: Locale) -> Bool {
  a.identifier(.bcp47) == b.identifier(.bcp47)
}

/// 確定結果1つを segment にする。時刻は文字の属性 audioTimeRange の和、無ければ結果の range。
/// 秒はミリ秒に丸め、end が音声の長さ（duration）を丸めで超えないように切り詰める。
func makeSegment(_ r: SpeechTranscriber.Result, duration: Double) -> Segment? {
  let text = String(r.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
  if text.isEmpty { return nil }
  let others = r.alternatives.dropFirst().map { String($0.characters).trimmingCharacters(in: .whitespacesAndNewlines) }
    .filter { !$0.isEmpty && $0 != text }
  if !others.isEmpty { altSpans.append(AltSpan(text: text, alts: Array(others.prefix(3)))) }
  var lo = Double.infinity
  var hi = -Double.infinity
  var minConf: Double? = nil
  for run in r.text.runs {
    if let c = run.transcriptionConfidence {
      minConf = min(minConf ?? 1, c)
      if c < lowConfidence {
        let t = String(r.text[run.range].characters).trimmingCharacters(in: .whitespaces)
        if !t.isEmpty { lowSpans.append(LowSpan(text: t, conf: round3(c))) }
      }
    }
    guard let tr = run.audioTimeRange, tr.start.isNumeric, tr.end.isNumeric else { continue }
    lo = min(lo, tr.start.seconds)
    hi = max(hi, tr.end.seconds)
  }
  if !lo.isFinite || !hi.isFinite {
    guard r.range.start.isNumeric, r.range.end.isNumeric else { return Segment(text: text, start: 0, end: 0, conf: minConf) }
    lo = r.range.start.seconds
    hi = r.range.end.seconds
  }
  let start = round3(lo)
  var end = round3(hi)
  if end > duration { end = floor3(duration) }
  return Segment(text: text, start: min(start, end), end: end, conf: minConf.map(round3))
}

func makeTranscriber(_ locale: Locale) -> SpeechTranscriber {
  // preset は .transcription（確定結果だけ・途中結果なし）。時刻を取るために .audioTimeRange を足す。
  var preset = SpeechTranscriber.Preset.transcription
  preset.attributeOptions.insert(.audioTimeRange)
  preset.attributeOptions.insert(.transcriptionConfidence)
  preset.reportingOptions.insert(.alternativeTranscriptions)
  return SpeechTranscriber(
    locale: locale,
    transcriptionOptions: preset.transcriptionOptions,
    reportingOptions: preset.reportingOptions,
    attributeOptions: preset.attributeOptions)
}

@main
struct STTHelper {
  static func main() async {
    var args = Array(CommandLine.arguments.dropFirst())
    var contextWords: [String] = []
    if let i = args.firstIndex(of: "--context") {
      guard i + 1 < args.count else { fail("usage", "--context の後に語の一覧ファイルが要ります") }
      let listPath = args[i + 1]
      guard let body = try? String(contentsOfFile: listPath, encoding: .utf8) else {
        fail("file_not_found", "語の一覧ファイルが読めません: \(listPath)")
      }
      contextWords = body.split(whereSeparator: \.isNewline)
        .map { $0.trimmingCharacters(in: .whitespaces) }
        .filter { !$0.isEmpty }
      args.removeSubrange(i...(i + 1))
    }
    guard args.count == 1 || args.count == 2 else {
      fail("usage", "使い方: stt-helper <音声ファイル> [ロケール（既定 ja_JP）] [--context <語の一覧ファイル>]")
    }
    let path = args[0]
    let localeArg = args.count == 2 ? args[1] : "ja_JP"
    let clock = ContinuousClock()
    let t0 = clock.now

    // 1. ファイル
    var isDir: ObjCBool = false
    guard FileManager.default.fileExists(atPath: path, isDirectory: &isDir), !isDir.boolValue else {
      fail("file_not_found", "音声ファイルがありません: \(path)")
    }
    let file: AVAudioFile
    do {
      file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
    } catch {
      fail("audio_unreadable", "音声ファイルとして読めません: \(path) (\(error.localizedDescription))")
    }

    // 2. ロケール（supportedLocales に無ければ非対応）
    guard SpeechTranscriber.isAvailable else {
      fail("unavailable", "この Mac では SpeechTranscriber が使えません")
    }
    guard let locale = await SpeechTranscriber.supportedLocale(equivalentTo: Locale(identifier: localeArg)) else {
      fail("locale_unsupported", "ロケールに対応していません: \(localeArg)")
    }

    // 3. モデル（installedLocales に無ければ AssetInventory で導入を要求する）
    // AssetInventory.status(forModules:) は導入済みでも .supported を返したので判定に使わない（2026-10-20 実測）。
    let transcriber = makeTranscriber(locale)
    if !(await SpeechTranscriber.installedLocales).contains(where: { sameLocale($0, locale) }) {
      let request: AssetInstallationRequest?
      do {
        request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber])
      } catch {
        fail("model_not_installed", "モデルが未導入で、導入の要求もできません: \(locale.identifier) (\(error.localizedDescription))")
      }
      if let request {
        do {
          try await request.downloadAndInstall()
        } catch {
          fail("model_not_installed", "モデルが未導入で、導入に失敗しました: \(locale.identifier) (\(error.localizedDescription))")
        }
      }
      if !(await SpeechTranscriber.installedLocales).contains(where: { sameLocale($0, locale) }) {
        fail("model_not_installed", "モデルが未導入です（導入を要求できませんでした）: \(locale.identifier)")
      }
    }

    // 4. 文字起こし
    let duration = Double(file.length) / file.processingFormat.sampleRate
    let analyzer = SpeechAnalyzer(modules: [transcriber])
    if !contextWords.isEmpty {
      let ctx = AnalysisContext()
      ctx.contextualStrings[.general] = contextWords
      do {
        try await analyzer.setContext(ctx)
      } catch {
        fail("transcription_failed", "文脈の語を渡せませんでした: \(error.localizedDescription)")
      }
    }
    let collector = Task { () throws -> [Segment] in
      var segs: [Segment] = []
      for try await r in transcriber.results where r.isFinal {
        if let s = makeSegment(r, duration: duration) { segs.append(s) }
      }
      return segs
    }
    do {
      if let last = try await analyzer.analyzeSequence(from: file) {
        try await analyzer.finalizeAndFinish(through: last)
      } else {
        await analyzer.cancelAndFinishNow()
      }
    } catch {
      collector.cancel()
      fail("transcription_failed", "文字起こしに失敗しました: \(error.localizedDescription)")
    }
    let segments: [Segment]
    do {
      segments = try await collector.value.sorted { $0.start < $1.start }
    } catch {
      fail("transcription_failed", "結果の受け取りに失敗しました: \(error.localizedDescription)")
    }

    // 5. 出力（標準出力は JSON 1つだけ）
    // 日本語・中国語は確定結果をそのままつなぎ、ほかの言語は空白1つでつなぐ。
    let lang = locale.language.languageCode?.identifier ?? ""
    let joiner = ["ja", "zh", "yue"].contains(lang) ? "" : " "
    let out = Output(
      text: segments.map(\.text).joined(separator: joiner),
      segments: segments,
      low: lowSpans,
      alts: altSpans,
      context: contextWords.count,
      elapsed: round3(seconds(clock.now - t0)),
      locale: locale.identifier)
    do {
      let enc = JSONEncoder()
      enc.outputFormatting = [.sortedKeys]  // キーの並びを毎回同じにする
      let data = try enc.encode(out)
      FileHandle.standardOutput.write(data)
      FileHandle.standardOutput.write("\n".data(using: .utf8)!)
    } catch {
      fail("transcription_failed", "JSON の書き出しに失敗しました: \(error.localizedDescription)")
    }
  }
}

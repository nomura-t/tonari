// となり.app — 手元のサーバー（Python）を起動し、その画面を WKWebView の窓で開く。
// swiftc 単体・ad-hoc 署名。
// サーバーがすでに動いていれば（run.sh で起動したときなど）それを使い、閉じるときも止めない。
//   ./となり.app/Contents/MacOS/Tonari --selftest [--port N] [--snapshot 出力.png] [--js 式]
//   窓を出さずに起動→画面の読み込み→（--js の式を評価して表示）→（撮影）→停止まで確かめる
import AppKit
import WebKit

let info = Bundle.main.infoDictionary ?? [:]
let args = CommandLine.arguments
let SELFTEST = args.contains("--selftest")
let PORT: Int = {
    if let i = args.firstIndex(of: "--port"), i + 1 < args.count, let p = Int(args[i + 1]) { return p }
    return Int(info["TonariPort"] as? String ?? "") ?? 4880
}()
let BASE = "http://127.0.0.1:\(PORT)/"
let APP_DIR = info["TonariAppDir"] as? String ?? ""
let UV = info["TonariUV"] as? String ?? "/opt/homebrew/bin/uv"
let TOOL_PATH = info["TonariPath"] as? String ?? "/usr/bin:/bin"
let LOG_DIR = (("~/Library/Logs/tonari") as NSString).expandingTildeInPath

func say(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

final class AppDelegate: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate {
    var window: NSWindow?
    var web: WKWebView!
    var server: Process?
    var loadedApp = false

    func applicationDidFinishLaunching(_ note: Notification) {
        if !SELFTEST { buildMenu() }
        let cfg = WKWebViewConfiguration()
        cfg.mediaTypesRequiringUserActionForPlayback = []
        web = WKWebView(frame: NSRect(x: 0, y: 0, width: 1440, height: 900), configuration: cfg)
        web.uiDelegate = self
        web.navigationDelegate = self
        if #available(macOS 13.3, *) { web.isInspectable = true }
        if !SELFTEST {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                             styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            w.title = "となり"
            w.contentView = web
            w.setFrameAutosaveName("TonariMain")
            if !w.setFrameUsingName("TonariMain") { w.center() }
            w.makeKeyAndOrderFront(nil)
            window = w
            NSApp.activate(ignoringOtherApps: true)
        }
        web.loadHTMLString(page("起動しています", "棚の本文を写して、聞き取りの準備をしています。初回は数秒かかります。"), baseURL: nil)
        Task { await boot() }
    }

    func page(_ title: String, _ body: String) -> String {
        """
        <!doctype html><meta charset="utf-8"><style>
        :root{color-scheme:light dark}body{margin:0;height:100vh;display:grid;place-items:center;font:17px -apple-system,"Hiragino Sans",sans-serif;background:Canvas;color:CanvasText}
        div{max-width:34em;padding:24px;line-height:1.8}h1{font-size:22px;margin:0 0 8px}p{margin:0;opacity:.75}code{font-size:14px}
        </style><div><h1>\(title)</h1><p>\(body)</p></div>
        """
    }

    func alive() async -> Bool {
        var req = URLRequest(url: URL(string: BASE + "api/state")!)
        req.setValue("1", forHTTPHeaderField: "X-Tonari")
        req.timeoutInterval = 1.5
        do {
            let (_, r) = try await URLSession.shared.data(for: req)
            return (r as? HTTPURLResponse)?.statusCode == 200
        } catch { return false }
    }

    @MainActor
    func boot() async {
        if !(await alive()) {
            do { try startServer() } catch {
                fail("サーバーを起動できませんでした", "\(error.localizedDescription)<br>ログ: <code>\(LOG_DIR)/server.log</code>")
                return
            }
        }
        for _ in 0..<160 {   // 最大40秒（初回は uv が依存を入れる）
            if await alive() { break }
            if let p = server, !p.isRunning { break }
            try? await Task.sleep(nanoseconds: 250_000_000)
        }
        guard await alive() else {
            fail("サーバーが立ち上がりませんでした", "ログ: <code>\(LOG_DIR)/server.log</code>")
            return
        }
        web.load(URLRequest(url: URL(string: BASE)!))
    }

    func startServer() throws {
        try FileManager.default.createDirectory(atPath: LOG_DIR, withIntermediateDirectories: true)
        let logPath = LOG_DIR + "/server.log"
        if !FileManager.default.fileExists(atPath: logPath) { FileManager.default.createFile(atPath: logPath, contents: nil) }
        let log = try FileHandle(forWritingTo: URL(fileURLWithPath: logPath))
        log.seekToEndOfFile()
        log.write("\n=== \(Date()) となり.app がサーバーを起動 (port \(PORT)) ===\n".data(using: .utf8)!)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: UV)
        p.arguments = ["run", "--quiet", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", String(PORT)]
        p.currentDirectoryURL = URL(fileURLWithPath: APP_DIR)
        var env = ProcessInfo.processInfo.environment.filter { !$0.key.hasPrefix("ANTHROPIC_") }
        env["PATH"] = TOOL_PATH
        env["TONARI_PORT"] = String(PORT)
        p.environment = env
        p.standardOutput = log
        p.standardError = log
        try p.run()
        server = p
    }

    func stopServer() {
        guard let p = server, p.isRunning else { return }
        // 先生役のプロセスを閉じてから止める（/api/shutdown）。返事が無ければ SIGTERM
        var req = URLRequest(url: URL(string: BASE + "api/shutdown")!)
        req.httpMethod = "POST"
        req.setValue("1", forHTTPHeaderField: "X-Tonari")
        req.timeoutInterval = 2
        let sem = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: req) { _, _, _ in sem.signal() }.resume()
        _ = sem.wait(timeout: .now() + 2.5)
        let deadline = Date().addingTimeInterval(4)
        while p.isRunning && Date() < deadline { usleep(100_000) }
        if p.isRunning { p.terminate() }
    }

    @MainActor
    func fail(_ title: String, _ body: String) {
        web.loadHTMLString(page(title, body), baseURL: nil)
        if SELFTEST { say("SELFTEST FAIL: \(title)"); stopServer(); exit(1) }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ note: Notification) { stopServer() }

    // ---- 画面の読み込み ----
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard webView.url?.absoluteString.hasPrefix(BASE) == true else { return }
        loadedApp = true
        guard SELFTEST else { return }
        Task { @MainActor in
            for _ in 0..<60 {
                let r = try? await webView.evaluateJavaScript("""
                  JSON.stringify({rail: !!document.querySelector('#sessions'), secure: window.isSecureContext,
                    mic: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia), recorder: typeof MediaRecorder,
                    webm: typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported('audio/webm;codecs=opus'),
                    sessions: document.querySelectorAll('#sessions .sess').length, ready: !!window.tonari})
                """)
                if let s = r as? String, s.contains("\"ready\":true") {
                    print("SELFTEST OK \(s)")
                    if let i = args.firstIndex(of: "--js"), i + 1 < args.count {
                        // 画面を操作して確かめる式（Promise を返してよい）。結果を JSON の文字にして表示する
                        do {
                            let v = try await webView.callAsyncJavaScript("const v = await (\(args[i + 1])); return JSON.stringify(v);",
                                                                          arguments: [:], in: nil, contentWorld: .page)
                            print("SELFTEST JS \(v ?? "null")")
                        } catch { print("SELFTEST JS ERROR \(error)") }
                    }
                    if let i = args.firstIndex(of: "--snapshot"), i + 1 < args.count {
                        try? await Task.sleep(nanoseconds: 2_500_000_000)   // 書体と図の描画を待つ
                        let conf = WKSnapshotConfiguration()
                        if let img = try? await webView.takeSnapshot(configuration: conf),
                           let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                           let png = rep.representation(using: .png, properties: [:]) {
                            try? png.write(to: URL(fileURLWithPath: args[i + 1]))
                            print("SNAPSHOT \(args[i + 1]) \(Int(img.size.width))x\(Int(img.size.height))")
                        } else { say("SNAPSHOT FAIL") }
                    }
                    stopServer()
                    exit(0)
                }
                try? await Task.sleep(nanoseconds: 250_000_000)
            }
            say("SELFTEST FAIL: 画面が出ませんでした")
            stopServer()
            exit(1)
        }
    }

    // 外のサイトへのリンクは既定のブラウザで開く
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let u = action.request.url, ["http", "https"].contains(u.scheme ?? ""), u.host != "127.0.0.1",
           action.navigationType == .linkActivated {
            NSWorkspace.shared.open(u)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let u = action.request.url { NSWorkspace.shared.open(u) }
        return nil
    }

    // マイクは手元のサーバーの画面にだけ許す（毎回の確認を出さない。OS の許可は初回に1回）
    @available(macOS 12.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo,
                 type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(origin.host == "127.0.0.1" && type == .microphone ? .grant : .deny)
    }

    // ---- メニュー ----
    @objc func reload(_ s: Any?) { if loadedApp { web.reload() } else { Task { await boot() } } }
    @objc func openInBrowser(_ s: Any?) { NSWorkspace.shared.open(URL(string: BASE)!) }
    @objc func openLog(_ s: Any?) { NSWorkspace.shared.open(URL(fileURLWithPath: LOG_DIR + "/server.log")) }
    @objc func openData(_ s: Any?) {
        NSWorkspace.shared.open(URL(fileURLWithPath: ("~/Library/Application Support/tonari" as NSString).expandingTildeInPath))
    }
    @objc func go(_ s: NSMenuItem) { web.evaluateJavaScript("location.hash = '\(s.representedObject as? String ?? "#/")'") }

    func buildMenu() {
        let main = NSMenu()
        func sub(_ title: String, _ items: [NSMenuItem]) {
            let it = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            let m = NSMenu(title: title)
            items.forEach { m.addItem($0) }
            it.submenu = m
            main.addItem(it)
        }
        func item(_ t: String, _ a: Selector?, _ k: String, _ mods: NSEvent.ModifierFlags = .command, target: AnyObject? = nil) -> NSMenuItem {
            let i = NSMenuItem(title: t, action: a, keyEquivalent: k)
            i.keyEquivalentModifierMask = mods
            i.target = target
            return i
        }
        sub("となり", [item("となりを終了", #selector(NSApplication.terminate(_:)), "q")])
        sub("ファイル", [
            item("Chrome などのブラウザで開く", #selector(openInBrowser(_:)), "b", [.command, .shift], target: self),
            item("記録のフォルダを開く", #selector(openData(_:)), "o", [.command, .shift], target: self),
            item("サーバーのログを開く", #selector(openLog(_:)), "l", [.command, .shift], target: self),
            .separator(),
            item("窓を閉じる", #selector(NSWindow.performClose(_:)), "w"),
        ])
        sub("編集", [
            item("取り消す", Selector(("undo:")), "z"), item("やり直す", Selector(("redo:")), "z", [.command, .shift]), .separator(),
            item("切り取り", #selector(NSText.cut(_:)), "x"), item("コピー", #selector(NSText.copy(_:)), "c"),
            item("貼り付け", #selector(NSText.paste(_:)), "v"), item("すべてを選択", #selector(NSText.selectAll(_:)), "a"),
        ])
        sub("表示", [item("読み直す", #selector(reload(_:)), "r", target: self)])
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
app.setActivationPolicy(SELFTEST ? .prohibited : .regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()

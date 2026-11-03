// アプリのアイコン（1024px PNG）を描く。build_app.sh から呼ぶ。
// 図柄: 中心の概念の札と、上下左右のとなりの札（上=上位・下=下位・左右=対）を線でつないだもの。
import AppKit

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "icon_1024.png"
let S: CGFloat = 1024
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(S), pixelsHigh: Int(S), bitsPerSample: 8,
                           samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                           bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let ctx = NSGraphicsContext.current!.cgContext

func rgb(_ hex: UInt32, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255, alpha: a)
}

// 地（macOS のアイコン格子: 824px の角丸正方形・余白100px）
let tile = NSRect(x: 100, y: 100, width: 824, height: 824)
let tilePath = NSBezierPath(roundedRect: tile, xRadius: 185, yRadius: 185)
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -10), blur: 28, color: rgb(0x000000, 0.30).cgColor)
rgb(0xF7F8FA).setFill(); tilePath.fill()
ctx.restoreGState()
tilePath.addClip()
NSGradient(starting: rgb(0xFFFFFF), ending: rgb(0xE9ECF1))!.draw(in: tilePath, angle: -90)

let C = NSPoint(x: 512, y: 512)
let around: [(NSPoint, UInt32)] = [
    (NSPoint(x: 512, y: 760), 0x5B6B86),   // 上位
    (NSPoint(x: 512, y: 264), 0x5B6B86),   // 下位
    (NSPoint(x: 264, y: 512), 0x3E7BFA),   // 対
    (NSPoint(x: 760, y: 512), 0x3E7BFA),   // 対
]
// 線
ctx.setLineCap(.round)
for (p, _) in around {
    let l = NSBezierPath(); l.move(to: C); l.line(to: p)
    l.lineWidth = 26; rgb(0xC3CAD6).setStroke(); l.stroke()
}
// となりの札
for (p, c) in around {
    let r = NSRect(x: p.x - 78, y: p.y - 78, width: 156, height: 156)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -6), blur: 14, color: rgb(0x000000, 0.18).cgColor)
    rgb(0xFFFFFF).setFill(); NSBezierPath(roundedRect: r, xRadius: 44, yRadius: 44).fill()
    ctx.restoreGState()
    let b = NSBezierPath(roundedRect: r.insetBy(dx: 9, dy: 9), xRadius: 36, yRadius: 36)
    b.lineWidth = 18; rgb(c).setStroke(); b.stroke()
}
// 中心の札
let cr = NSRect(x: C.x - 128, y: C.y - 128, width: 256, height: 256)
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -10), blur: 24, color: rgb(0x000000, 0.28).cgColor)
rgb(0x1F2533).setFill(); NSBezierPath(roundedRect: cr, xRadius: 66, yRadius: 66).fill()
ctx.restoreGState()
rgb(0xFFFFFF).setFill()
NSBezierPath(roundedRect: NSRect(x: C.x - 70, y: C.y + 6, width: 140, height: 34), xRadius: 17, yRadius: 17).fill()
rgb(0xFFFFFF, 0.55).setFill()
NSBezierPath(roundedRect: NSRect(x: C.x - 70, y: C.y - 50, width: 96, height: 34), xRadius: 17, yRadius: 17).fill()

NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))

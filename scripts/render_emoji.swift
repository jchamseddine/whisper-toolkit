// Render an emoji into a square PNG with a transparent background.
//
// Why Swift here, when the rest of the toolkit is Python: only AppKit knows how
// to compose Apple Color Emoji's colour glyphs. Pillow does not read that
// font's `sbix` bitmap sheets.
//
// Two limits of the font worth keeping in mind:
//   - its largest sheet is 160 px, so beyond that it is upscaling — crisp at
//     real icon size, soft when very large;
//   - the glyph overflows its em box, hence `fontScale` < 1, otherwise the
//     drawing is clipped by the canvas edges.
//
// usage: swift render_emoji.swift <emoji> <pixels> <output.png> [fontScale]

import AppKit

let emoji = CommandLine.arguments[1]
let px = Int(CommandLine.arguments[2])!
let out = CommandLine.arguments[3]
let fontScale = CommandLine.arguments.count > 4 ? Double(CommandLine.arguments[4])! : 1.0

let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: px, pixelsHigh: px,
    bitsPerSample: 8, samplesPerPixel: 4,
    hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0, bitsPerPixel: 0
)!

NSGraphicsContext.saveGraphicsState()
let ctx = NSGraphicsContext(bitmapImageRep: rep)!
NSGraphicsContext.current = ctx
ctx.cgContext.interpolationQuality = .high
ctx.imageInterpolation = .high
ctx.cgContext.setShouldAntialias(true)
ctx.cgContext.clear(CGRect(x: 0, y: 0, width: px, height: px))

let side = CGFloat(px)
let font = NSFont(name: "Apple Color Emoji", size: side * fontScale)!
let text = NSAttributedString(string: emoji, attributes: [.font: font])
let size = text.size()
text.draw(at: NSPoint(x: (side - size.width) / 2, y: (side - size.height) / 2))

NSGraphicsContext.restoreGraphicsState()

guard let png = rep.representation(using: .png, properties: [:]) else {
    FileHandle.standardError.write("PNG encoding failed\n".data(using: .utf8)!)
    exit(1)
}
try png.write(to: URL(fileURLWithPath: out))
print("wrote \(out) (\(px)x\(px))")

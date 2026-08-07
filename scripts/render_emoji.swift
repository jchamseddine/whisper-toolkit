// Rendu d'un emoji en PNG carré à fond transparent.
//
// Pourquoi du Swift ici, alors que le reste du toolkit est en Python : seul
// AppKit sait composer les glyphes couleur d'Apple Color Emoji. Pillow ne lit
// pas les planches bitmap `sbix` de cette police.
//
// Deux limites de la police à garder en tête :
//   - sa plus grande planche fait 160 px, donc au-delà c'est de
//     l'agrandissement — net à taille d'icône réelle, doux en très grand ;
//   - le glyphe déborde de sa boîte em, d'où `fontScale` < 1, sinon le dessin
//     est rogné par les bords de la toile.
//
// usage : swift render_emoji.swift <emoji> <pixels> <sortie.png> [fontScale]

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
let texte = NSAttributedString(string: emoji, attributes: [.font: font])
let taille = texte.size()
texte.draw(at: NSPoint(x: (side - taille.width) / 2, y: (side - taille.height) / 2))

NSGraphicsContext.restoreGraphicsState()

guard let png = rep.representation(using: .png, properties: [:]) else {
    FileHandle.standardError.write("échec de l'encodage PNG\n".data(using: .utf8)!)
    exit(1)
}
try png.write(to: URL(fileURLWithPath: out))
print("écrit \(out) (\(px)x\(px))")

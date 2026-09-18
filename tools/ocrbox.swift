import Foundation
import Vision
import AppKit

// 用法: ocrbox <图片路径> ...
// 输出: 每张图一行 JSON: {"file":"...","w":504,"h":672,"blocks":[{"t":"文字","x":0.1,"y":0.2,"w":0.3,"h":0.05},...]}
// 坐标: x/y 为左上角, 归一化 0~1, y 从图片顶部往下

func ocr(_ path: String) -> String {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return "{\"file\":\"\(path)\",\"error\":\"load\"}"
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch {
        return "{\"file\":\"\(path)\",\"error\":\"perform\"}"
    }
    guard let obs = req.results else { return "{\"file\":\"\(path)\",\"w\":\(cg.width),\"h\":\(cg.height),\"blocks\":[]}" }
    var blocks: [String] = []
    for o in obs {
        guard let c = o.topCandidates(1).first else { continue }
        let bb = o.boundingBox          // Vision 坐标: 原点左下, 归一化
        let x = bb.minX, w = bb.width
        let yTop = 1.0 - bb.maxY        // 转成从顶部算
        let h = bb.height
        let t = c.string.replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .replacingOccurrences(of: "\t", with: " ")
        let conf = String(format: "%.2f", c.confidence)
        blocks.append("{\"t\":\"\(t)\",\"x\":\(x),\"y\":\(yTop),\"w\":\(w),\"h\":\(h),\"c\":\(conf)}")
    }
    return "{\"file\":\"\(path)\",\"w\":\(cg.width),\"h\":\(cg.height),\"blocks\":[\(blocks.joined(separator: ","))]}"
}

let args = Array(CommandLine.arguments.dropFirst())
for a in args { print(ocr(a)) }

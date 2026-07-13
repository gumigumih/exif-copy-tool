import AppKit
import Foundation

final class ExifCopyServiceProvider: NSObject {
    private let appExecutable = "/Applications/ExifCopyTool.app/Contents/MacOS/ExifCopyTool"

    @objc func copyExif(
        _ pasteboard: NSPasteboard,
        userData: String?,
        error: AutoreleasingUnsafeMutablePointer<NSString?>
    ) {
        do {
            let paths = try selectedFilePaths(from: pasteboard)
            guard let formatName = userData, !formatName.isEmpty else {
                throw ServiceError("フォーマットが指定されていません")
            }

            let outputURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("exif-copy-\(UUID().uuidString).txt")
            defer { try? FileManager.default.removeItem(at: outputURL) }

            let process = Process()
            process.executableURL = URL(fileURLWithPath: appExecutable)
            process.arguments = ["--render-to", outputURL.path, formatName] + paths
            let stderr = Pipe()
            process.standardError = stderr
            try process.run()
            process.waitUntilExit()

            guard process.terminationStatus == 0 else {
                let data = stderr.fileHandleForReading.readDataToEndOfFile()
                let message = String(data: data, encoding: .utf8) ?? "EXIF処理に失敗しました"
                throw ServiceError(message.trimmingCharacters(in: .whitespacesAndNewlines))
            }

            let text = try String(contentsOf: outputURL, encoding: .utf8)
            let generalPasteboard = NSPasteboard.general
            generalPasteboard.clearContents()
            guard generalPasteboard.setString(text, forType: .string) else {
                throw ServiceError("クリップボードへの書き込みに失敗しました")
            }

            let notification = NSUserNotification()
            notification.title = "EXIFコピー"
            notification.informativeText = "EXIF情報をコピーしました"
            NSUserNotificationCenter.default.deliver(notification)
        } catch let serviceError {
            error.pointee = serviceError.localizedDescription as NSString
        }
    }

    private func selectedFilePaths(from pasteboard: NSPasteboard) throws -> [String] {
        let options: [NSPasteboard.ReadingOptionKey: Any] = [.urlReadingFileURLsOnly: true]
        if let urls = pasteboard.readObjects(forClasses: [NSURL.self], options: options) as? [URL], !urls.isEmpty {
            return urls.map(\.path)
        }

        let legacyType = NSPasteboard.PasteboardType("NSFilenamesPboardType")
        if let paths = pasteboard.propertyList(forType: legacyType) as? [String], !paths.isEmpty {
            return paths
        }
        throw ServiceError("画像ファイルを取得できませんでした")
    }

}

struct ServiceError: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

let application = NSApplication.shared
let provider = ExifCopyServiceProvider()
application.servicesProvider = provider
application.setActivationPolicy(.prohibited)
application.run()

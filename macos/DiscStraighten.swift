// Native drop target; the existing CLI owns all image processing and logs.
import Cocoa
import UniformTypeIdentifiers
import WebKit

// One palette shared with the Windows interface and the alignment illustration.
enum Theme {
    static let palette: [String: String] = {
        let url = Bundle.main.resourceURL!.appendingPathComponent("engine/discstraight/ui_theme.json")
        guard let data = try? Data(contentsOf: url),
              let colors = try? JSONDecoder().decode([String: String].self, from: data) else { return [:] }
        return colors
    }()
    static func color(_ name: String) -> NSColor {
        guard let hex = palette[name], let value = UInt32(hex.dropFirst(), radix: 16) else { return .labelColor }
        return NSColor(srgbRed: CGFloat((value >> 16) & 255)/255,
                       green: CGFloat((value >> 8) & 255)/255, blue: CGFloat(value & 255)/255, alpha: 1)
    }
}

final class ComparisonDocument: NSView {
    override var isFlipped: Bool { true }
}

final class ComparisonScroll: NSScrollView {
    override func tile() {
        super.tile()
        if let document = documentView, abs(document.frame.width - contentSize.width) > 0.5 {
            document.setFrameSize(NSSize(width: contentSize.width, height: document.frame.height))
        }
    }
}

struct CommandResult {
    let code: Int32
    let text: String
}

final class Engine {
    let root = Bundle.main.resourceURL!.appendingPathComponent("engine")
    var environment: [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin")
        env["PYTHONUNBUFFERED"] = "1"
        // Imported source is inside the signed bundle; never write __pycache__ there.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if env["DISC_STRAIGHTEN_ENV"] == nil {
            let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            env["DISC_STRAIGHTEN_ENV"] = support.appendingPathComponent("Disc Straighten/runtime").path
        }
        return env
    }

    // Always call off the main thread. Drain the single pipe before waiting so
    // verbose installation or image progress cannot fill it and deadlock.
    func run(_ arguments: [String], onLine: ((String) -> Void)? = nil) -> CommandResult {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = root.appendingPathComponent("de-askew")
        process.arguments = arguments
        process.environment = environment
        process.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = pipe
        process.standardError = pipe
        var collected = Data()
        var pending = Data()
        do {
            try process.run()
            while true {
                let data = pipe.fileHandleForReading.availableData
                if data.isEmpty { break }
                collected.append(data)
                if collected.count > 262_144 { collected.removeFirst(collected.count - 262_144) }
                pending.append(data)
                while let newline = pending.firstIndex(of: 10) {
                    onLine?(String(decoding: pending[..<newline], as: UTF8.self))
                    pending.removeSubrange(...newline)
                }
            }
            if !pending.isEmpty { onLine?(String(decoding: pending, as: UTF8.self)) }
            process.waitUntilExit()
            return CommandResult(code: process.terminationStatus, text: String(decoding: collected, as: UTF8.self))
        } catch {
            return CommandResult(code: 1, text: error.localizedDescription)
        }
    }
}

final class DropView: NSView {
    var receive: (([URL]) -> Void)?
    private var highlighted = false
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        registerForDraggedTypes([.fileURL])
        wantsLayer = true
        layer?.cornerRadius = 12
        setAccessibilityLabel("Drop images or folders here")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        (highlighted ? NSColor.controlAccentColor.withAlphaComponent(0.12) : NSColor.controlBackgroundColor).setFill()
        NSBezierPath(roundedRect: bounds.insetBy(dx: 1, dy: 1), xRadius: 12, yRadius: 12).fill()
        (highlighted ? NSColor.controlAccentColor : NSColor.separatorColor).setStroke()
        let border = NSBezierPath(roundedRect: bounds.insetBy(dx: 1, dy: 1), xRadius: 12, yRadius: 12)
        border.lineWidth = 2
        border.stroke()
    }
    private func urls(_ sender: NSDraggingInfo) -> [URL] {
        (sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL]) ?? []
    }
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        highlighted = !urls(sender).isEmpty
        needsDisplay = true
        return highlighted ? .copy : []
    }
    override func draggingExited(_ sender: NSDraggingInfo?) { highlighted = false; needsDisplay = true }
    override func prepareForDragOperation(_ sender: NSDraggingInfo) -> Bool { !urls(sender).isEmpty }
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let files = urls(sender)
        highlighted = false; needsDisplay = true
        guard !files.isEmpty else { return false }
        receive?(files)
        return true
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let engine = Engine()
    let worker = DispatchQueue(label: "org.tapearchives.disc-straighten.processing", qos: .userInitiated)
    var window: NSWindow!
    let destinationLabel = NSTextField(wrappingLabelWithString: "Output: output inside each input folder · separate image, preview and JSON folders")
    let statusLabel = NSTextField(wrappingLabelWithString: "Ready. Originals stay unchanged.")
    let activity = NSTextView()
    let progress = NSProgressIndicator()
    let media = NSPopUpButton()
    var preferencesButton: NSButton!
    var revealButton: NSButton!
    var clearQueueButton: NSButton!
    var queue: [[URL]] = []
    var busy = false
    var initialized = false
    var latestOutput: URL?
    var saved: [String: Any] = [:]
    var preferencesSheet: NSWindow?
    var helpWindow: NSWindow?
    var activityScroll: NSScrollView!
    var emptyReview: NSTextField?
    let resultCount = NSTextField(labelWithString: "No images processed yet")
    var savedCount = 0
    var reviewCount = 0
    var failedCount = 0
    var comparisonsScroll: NSScrollView?
    let comparisons = ComparisonDocument()
    var comparisonCount = 0
    let autoContrast = NSButton(checkboxWithTitle: "Contrast", target: nil, action: nil)
    let autoBrightness = NSButton(checkboxWithTitle: "Brightness", target: nil, action: nil)
    let autoColor = NSButton(checkboxWithTitle: "Color", target: nil, action: nil)
    let autoAll = NSButton(checkboxWithTitle: "All adjustments", target: nil, action: nil)
    let keepMetadata = NSButton(checkboxWithTitle: "Keep metadata", target: nil, action: nil)
    var relativeField: NSTextField!
    var fixedField: NSTextField!
    var mode: NSPopUpButton!
    var preferenceMessage: NSTextField!
    var saveButton: NSButton!

    func applicationDidFinishLaunching(_ notification: Notification) {
        makeMenu()
        makeWindow()
        initialized = true
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        busy = true
        setBusyUI(true)
        statusLabel.stringValue = "Preparing the processor… First use may install Python dependencies."
        worker.async {
            let result = self.engine.run(["--show-preferences"]) { line in
                DispatchQueue.main.async { if !line.hasPrefix("{") { self.append(line) } }
            }
            DispatchQueue.main.async {
                self.busy = false
                self.setBusyUI(false)
                if result.code == 0 { self.readPreferences(result.text); self.statusLabel.stringValue = "Ready. Drop photos to begin." }
                else { self.append(result.text); self.statusLabel.stringValue = "Setup needs attention. Open Activity for details." }
                self.nextBatch()
            }
        }
    }

    func makeMenu() {
        let bar = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Preferences…", action: #selector(showPreferences), keyEquivalent: ",").target = self
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit de-askew", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu; bar.addItem(appItem)
        let fileItem = NSMenuItem(title: "File", action: nil, keyEquivalent: "")
        let fileMenu = NSMenu(title: "File")
        fileMenu.addItem(withTitle: "Add Images or Folders…", action: #selector(chooseFiles), keyEquivalent: "o").target = self
        fileMenu.addItem(withTitle: "Processing Comparisons", action: #selector(showComparisons), keyEquivalent: "r").target = self
        fileItem.submenu = fileMenu; bar.addItem(fileItem)
        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit")
        for (name, selector, key) in [("Cut", #selector(NSText.cut(_:)), "x"), ("Copy", #selector(NSText.copy(_:)), "c"), ("Paste", #selector(NSText.paste(_:)), "v"), ("Select All", #selector(NSText.selectAll(_:)), "a")] {
            editMenu.addItem(withTitle: name, action: selector, keyEquivalent: key)
        }
        editItem.submenu = editMenu; bar.addItem(editItem)
        let viewItem = NSMenuItem(title: "View", action: nil, keyEquivalent: "")
        let viewMenu = NSMenu(title: "View")
        viewMenu.addItem(withTitle: "Standard Window", action: #selector(standardWindow), keyEquivalent: "0").target = self
        let compact = viewMenu.addItem(withTitle: "Compact Window", action: #selector(compactWindow), keyEquivalent: "0")
        compact.keyEquivalentModifierMask = [.command, .shift]; compact.target = self
        viewMenu.addItem(withTitle: "Show or Hide Activity", action: #selector(toggleActivity), keyEquivalent: "l").target = self
        viewItem.submenu = viewMenu; bar.addItem(viewItem)
        let helpItem = NSMenuItem(title: "Help", action: nil, keyEquivalent: "")
        let helpMenu = NSMenu(title: "Help")
        helpMenu.addItem(withTitle: "de-askew User Guide", action: #selector(showHelp), keyEquivalent: "?").target = self
        helpItem.submenu = helpMenu; bar.addItem(helpItem)
        NSApp.helpMenu = helpMenu
        NSApp.mainMenu = bar
    }

    @objc func showHelp() {
        if helpWindow == nil {
            let guide = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1000, height: 760),
                                 styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            guide.title = "de-askew User Guide"
            guide.isReleasedWhenClosed = false
            guide.minSize = NSSize(width: 560, height: 440)
            let configuration = WKWebViewConfiguration()
            configuration.defaultWebpagePreferences.allowsContentJavaScript = false
            let web = WKWebView(frame: guide.contentView!.bounds, configuration: configuration)
            web.autoresizingMask = [.width, .height]
            guide.contentView!.addSubview(web)
            let root = Bundle.main.resourceURL!.appendingPathComponent("manual")
            web.loadFileURL(root.appendingPathComponent("index.html"), allowingReadAccessTo: root)
            helpWindow = guide
            guide.center()
        }
        helpWindow!.makeKeyAndOrderFront(nil)
    }

    func button(_ title: String, _ action: Selector) -> NSButton {
        NSButton(title: title, target: self, action: action)
    }
    func label(_ text: String, size: CGFloat = 12, muted: Bool = false) -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: text)
        field.font = .systemFont(ofSize: size)
        field.textColor = Theme.color(muted ? "muted" : "ink")
        return field
    }
    func section(_ text: String) -> NSTextField {
        let field = label(text, size: 13)
        field.font = .systemFont(ofSize: 13, weight: .semibold)
        return field
    }
    func makeWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1160, height: 800),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "de-askew"
        window.minSize = NSSize(width: 900, height: 720)
        window.appearance = NSAppearance(named: .aqua)
        window.backgroundColor = Theme.color("canvas")
        window.isReleasedWhenClosed = false
        window.center()
        let stack = NSStackView()
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        let content = window.contentView!
        content.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 16),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -16)])
        let heading = NSStackView(); heading.orientation = .vertical; heading.alignment = .leading; heading.spacing = 5
        let title = label("de-askew", size: 30); title.font = .systemFont(ofSize: 30, weight: .semibold)
        heading.addArrangedSubview(title)
        heading.addArrangedSubview(label("Bring your media into alignment.", size: 14, muted: true))
        heading.addArrangedSubview(label("DISC + CASSETTE  /  TAPEARCHIVES", size: 10, muted: true))
        let art = NSImageView()
        art.image = NSImage(contentsOf: Bundle.main.resourceURL!.appendingPathComponent("manual/images/alignment.png"))
        art.imageScaling = .scaleProportionallyUpOrDown
        art.setAccessibilityLabel("A tilted disc and cassette aligned to their geometric templates")
        art.widthAnchor.constraint(equalToConstant: 290).isActive = true
        art.heightAnchor.constraint(equalToConstant: 98).isActive = true
        let header = NSStackView(views: [heading, NSView(), art]); header.spacing = 20
        stack.addArrangedSubview(header)
        let rule = NSBox(); rule.boxType = .separator; stack.addArrangedSubview(rule)
        let body = NSStackView(); body.orientation = .horizontal; body.alignment = .top; body.spacing = 24
        let sidebar = NSStackView(); sidebar.orientation = .vertical; sidebar.alignment = .leading; sidebar.spacing = 10
        sidebar.widthAnchor.constraint(equalToConstant: 248).isActive = true
        let drop = DropView(frame: .zero)
        drop.receive = { [weak self] urls in self?.enqueue(urls) }
        let dropContents = NSStackView(); dropContents.orientation = .vertical; dropContents.spacing = 7
        let symbol = NSImageView(image: NSImage(systemSymbolName: "square.and.arrow.down", accessibilityDescription: nil)!)
        symbol.contentTintColor = Theme.color("accent")
        symbol.heightAnchor.constraint(equalToConstant: 26).isActive = true
        dropContents.addArrangedSubview(symbol)
        dropContents.addArrangedSubview(section("Drop photos or folders"))
        dropContents.addArrangedSubview(label("Selections and subfolders welcome", size: 11, muted: true))
        dropContents.translatesAutoresizingMaskIntoConstraints = false; drop.addSubview(dropContents)
        NSLayoutConstraint.activate([drop.heightAnchor.constraint(equalToConstant: 122),
            dropContents.centerXAnchor.constraint(equalTo: drop.centerXAnchor),dropContents.centerYAnchor.constraint(equalTo: drop.centerYAnchor)])
        sidebar.addArrangedSubview(drop)
        let choose = button("Choose Images or Folders…", #selector(chooseFiles))
        choose.bezelStyle = .rounded; choose.controlSize = .large; choose.contentTintColor = Theme.color("accent")
        sidebar.addArrangedSubview(choose)
        sidebar.addArrangedSubview(label("JPEG · PNG · TIFF · WebP · BMP · HEIC", size: 10, muted: true))
        sidebar.setCustomSpacing(18, after: sidebar.arrangedSubviews.last!)
        sidebar.addArrangedSubview(section("Media type"))
        media.addItems(withTitles: ["Automatic", "Optical disc", "Compact cassette"])
        media.setAccessibilityLabel("Media type"); sidebar.addArrangedSubview(media)
        sidebar.setCustomSpacing(16, after: media)
        sidebar.addArrangedSubview(section("Finishing"))
        let options = NSStackView(); options.orientation = .vertical; options.alignment = .leading; options.spacing = 5
        let firstOptions = NSStackView(views: [autoContrast, autoBrightness]); firstOptions.spacing = 12
        let secondOptions = NSStackView(views: [autoColor, autoAll]); secondOptions.spacing = 12
        options.addArrangedSubview(firstOptions); options.addArrangedSubview(secondOptions); options.addArrangedSubview(keepMetadata)
        options.heightAnchor.constraint(equalToConstant: 70).isActive = true
        keepMetadata.toolTip = "Copies supported EXIF/XMP/IPTC, including location tags. Requires ExifTool. Defaults off."
        autoAll.toolTip = "Apply contrast, brightness and color to the final cropped pixels. Defaults off."
        sidebar.addArrangedSubview(options)
        sidebar.addArrangedSubview(label("Optional adjustments. All off by default.", size: 11, muted: true))
        sidebar.setCustomSpacing(16, after: sidebar.arrangedSubviews.last!)
        sidebar.addArrangedSubview(section("Destination"))
        destinationLabel.font = .systemFont(ofSize: 11); destinationLabel.textColor = Theme.color("muted")
        sidebar.addArrangedSubview(destinationLabel)
        preferencesButton = button("Output Preferences…", #selector(showPreferences)); sidebar.addArrangedSubview(preferencesButton)
        sidebar.addArrangedSubview(label("Originals stay unchanged. Every batch gets a fresh output folder.", size: 11, muted: true))
        let support = NSStackView(views: [button("User Guide", #selector(showHelp)), button("Activity", #selector(toggleActivity))]); support.spacing = 10
        sidebar.addArrangedSubview(support)
        for view in [drop, choose, media, destinationLabel] as [NSView] { view.widthAnchor.constraint(equalTo: sidebar.widthAnchor).isActive = true }
        for view in sidebar.arrangedSubviews { view.widthAnchor.constraint(lessThanOrEqualTo: sidebar.widthAnchor).isActive = true }
        let review = NSStackView(); review.orientation = .vertical; review.alignment = .leading; review.spacing = 8
        review.addArrangedSubview(section("Before & after"))
        review.addArrangedSubview(label("Checkerboard shows transparency. Open a result to inspect full resolution.", size: 11, muted: true))
        let scroll = ComparisonScroll(); scroll.hasVerticalScroller = true; scroll.hasHorizontalScroller = true
        scroll.autohidesScrollers = false; scroll.borderType = .noBorder; scroll.backgroundColor = Theme.color("canvas")
        comparisons.frame = NSRect(x: 0, y: 0, width: 0, height: 310)
        scroll.documentView = comparisons; comparisonsScroll = scroll
        emptyReview = label("Your images will appear here.\n\n1   Drop photos or folders\n2   Let geometry straighten each image\n3   Review the transparent PNG and its log", size: 15, muted: true)
        emptyReview!.frame = NSRect(x: 28, y: 80, width: 430, height: 170)
        comparisons.addSubview(emptyReview!)
        review.addArrangedSubview(scroll); scroll.widthAnchor.constraint(equalTo: review.widthAnchor).isActive = true
        let sidebarScroll = NSScrollView(); sidebarScroll.hasVerticalScroller = true
        sidebarScroll.autohidesScrollers = true; sidebarScroll.drawsBackground = false
        sidebarScroll.widthAnchor.constraint(equalToConstant: 268).isActive = true
        let sidebarDocument = ComparisonDocument(frame: NSRect(x: 0, y: 0, width: 248, height: 570))
        sidebar.translatesAutoresizingMaskIntoConstraints = false; sidebarDocument.addSubview(sidebar)
        NSLayoutConstraint.activate([sidebar.topAnchor.constraint(equalTo: sidebarDocument.topAnchor),
            sidebar.leadingAnchor.constraint(equalTo: sidebarDocument.leadingAnchor),
            sidebar.heightAnchor.constraint(equalToConstant: 560)])
        sidebarScroll.documentView = sidebarDocument
        body.addArrangedSubview(sidebarScroll); body.addArrangedSubview(review)
        sidebarScroll.heightAnchor.constraint(equalTo: body.heightAnchor).isActive = true
        review.widthAnchor.constraint(equalTo: body.widthAnchor, constant: -292).isActive = true
        review.heightAnchor.constraint(equalTo: body.heightAnchor).isActive = true
        stack.addArrangedSubview(body)
        activityScroll = NSScrollView(); activityScroll.hasVerticalScroller = true; activityScroll.borderType = .bezelBorder
        activity.isEditable = false; activity.isSelectable = true
        activity.font = .monospacedSystemFont(ofSize: 11, weight: .regular); activity.textColor = .labelColor
        activity.textContainerInset = NSSize(width: 10, height: 10); activity.isVerticallyResizable = true
        activity.isHorizontallyResizable = false; activity.autoresizingMask = [.width]; activity.textContainer?.widthTracksTextView = true
        activity.setAccessibilityLabel("Processing activity"); activityScroll.documentView = activity
        activityScroll.heightAnchor.constraint(equalToConstant: 110).isActive = true
        stack.addArrangedSubview(activityScroll); activityScroll.isHidden = true
        progress.style = .spinning; progress.controlSize = .small; progress.isIndeterminate = true; progress.isDisplayedWhenStopped = false
        progress.widthAnchor.constraint(equalToConstant: 18).isActive = true
        statusLabel.font = .systemFont(ofSize: 12); statusLabel.maximumNumberOfLines = 2
        statusLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let statusRow = NSStackView(views: [progress, statusLabel]); statusRow.spacing = 10
        let footer = NSStackView(); footer.orientation = .vertical; footer.alignment = .leading; footer.spacing = 6
        footer.addArrangedSubview(statusRow)
        resultCount.font = .systemFont(ofSize: 11); resultCount.textColor = Theme.color("muted")
        revealButton = button("Show Latest Output", #selector(revealOutput)); revealButton.isEnabled = false
        clearQueueButton = button("Clear Pending Batches", #selector(clearQueue)); clearQueueButton.isEnabled = false
        let actions = NSStackView(views: [resultCount, NSView(), revealButton, clearQueueButton]); actions.spacing = 10
        footer.addArrangedSubview(actions); actions.widthAnchor.constraint(equalTo: footer.widthAnchor).isActive = true
        stack.addArrangedSubview(footer)
        for view in [header, rule, body, activityScroll!, footer] as [NSView] { view.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true }
        body.setContentHuggingPriority(.defaultLow, for: .vertical)
        scroll.setContentHuggingPriority(.defaultLow, for: .vertical)
        append("Originals are preserved. Folders include subfolders; generated outputs are excluded.\nPNG masters retain alpha. Checks appear only in previews. Geometry warnings remain available in JSON logs.")
    }
    @objc func toggleActivity() { activityScroll.isHidden.toggle() }
    @objc func compactWindow() { window.setContentSize(NSSize(width: 900, height: 720)) }
    @objc func standardWindow() { window.setContentSize(NSSize(width: 1160, height: 800)) }
    @objc func showComparisons() { window.makeKeyAndOrderFront(nil); window.makeFirstResponder(comparisonsScroll) }
    @objc func openResult(_ sender: NSButton) {
        if let path = sender.identifier?.rawValue { NSWorkspace.shared.open(URL(fileURLWithPath: path)) }
    }
    func addComparison(_ json: [String: Any]) {
        guard let scroll = comparisonsScroll else { return }
        let follow = comparisons.bounds.height <= scroll.contentSize.height || scroll.documentVisibleRect.maxY >= comparisons.bounds.height - 24
        emptyReview?.removeFromSuperview(); emptyReview = nil
        let failed = json["error"] as? String
        let review = json["status"] as? String == "review_required"
        let card = NSStackView(); card.orientation = .vertical; card.alignment = .leading; card.spacing = 5
        card.wantsLayer = true; card.layer?.backgroundColor = Theme.color("surface").cgColor; card.layer?.cornerRadius = 10
        card.edgeInsets = NSEdgeInsets(top: 10, left: 12, bottom: 10, right: 12)
        let filename = URL(fileURLWithPath: json["input"] as? String ?? "Processing error").lastPathComponent
        let time = DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .medium)
        let header = NSTextField(labelWithString: "\(filename)  ·  \(time)")
        header.font = .systemFont(ofSize: 12, weight: .semibold); header.lineBreakMode = .byTruncatingMiddle
        header.toolTip = "\(filename)  ·  \(time)"; card.addArrangedSubview(header)
        let pair = NSStackView(); pair.distribution = .fillEqually; pair.spacing = 12
        if let error = failed {
            let explanation = error.contains("insufficient image data") || error.contains("improper image header")
                ? "The file is damaged or is not a supported image." : String(error.prefix(450))
            let message = label("Could not process this image.\n\(explanation)\n\nCheck the source and add it again to retry. Details are in Activity.", muted: true)
            pair.addArrangedSubview(message); failedCount += 1
        } else {
            for (caption, key) in [("BEFORE", "before_preview"), ("AFTER · TRANSPARENT PNG", "preview")] {
                let column = NSStackView(); column.orientation = .vertical; column.spacing = 3
                column.addArrangedSubview(label(caption, size: 10, muted: true))
                let image = NSImageView(); image.imageScaling = .scaleProportionallyUpOrDown
                if let path = json[key] as? String { image.image = NSImage(contentsOfFile: path) }
                image.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
                image.setContentHuggingPriority(.defaultLow, for: .horizontal)
                image.heightAnchor.constraint(equalToConstant: 142).isActive = true
                image.setAccessibilityLabel("\(caption): \(filename)")
                column.addArrangedSubview(image); image.widthAnchor.constraint(equalTo: column.widthAnchor).isActive = true
                pair.addArrangedSubview(column)
            }
            savedCount += 1; if review { reviewCount += 1 }
        }
        card.addArrangedSubview(pair)
        let notice = label(failed != nil ? "Failed · original preserved" : review ? "Saved · review geometry or orientation" : "Saved", size: 11)
        notice.textColor = Theme.color(failed != nil ? "danger" : review ? "warning" : "accent")
        notice.toolTip = (json["warnings"] as? [String])?.joined(separator: "\n")
        let bottom = NSStackView(views: [notice, NSView()]); bottom.spacing = 6
        if let path = json["image"] as? String {
            let open = button("Open PNG", #selector(openResult(_:))); open.identifier = NSUserInterfaceItemIdentifier(path)
            open.controlSize = .small; bottom.addArrangedSubview(open)
        }
        card.addArrangedSubview(bottom); card.translatesAutoresizingMaskIntoConstraints = false; comparisons.addSubview(card)
        NSLayoutConstraint.activate([card.topAnchor.constraint(equalTo: comparisons.topAnchor, constant: 8 + CGFloat(comparisonCount) * 242),
            card.leadingAnchor.constraint(equalTo: comparisons.leadingAnchor, constant: 4),
            card.heightAnchor.constraint(equalToConstant: 232),card.widthAnchor.constraint(equalTo: comparisons.widthAnchor, constant: -8),
            header.widthAnchor.constraint(equalTo: card.widthAnchor, constant: -24),
            pair.widthAnchor.constraint(equalTo: card.widthAnchor, constant: -24),
            bottom.widthAnchor.constraint(equalTo: card.widthAnchor, constant: -24)])
        comparisonCount += 1
        resultCount.stringValue = "\(savedCount) saved  ·  \(reviewCount) to review  ·  \(failedCount) failed"
        comparisons.setFrameSize(NSSize(width: scroll.contentSize.width, height: 16 + CGFloat(comparisonCount) * 242))
        comparisons.layoutSubtreeIfNeeded()
        if follow { card.scrollToVisible(card.bounds) }
    }

    @objc func chooseFiles() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = true; panel.allowsMultipleSelection = true
        panel.prompt = "Add to Queue"
        panel.beginSheetModal(for: window) { response in if response == .OK { self.enqueue(panel.urls) } }
    }
    func application(_ application: NSApplication, open urls: [URL]) { enqueue(urls) }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); return true
    }
    func enqueue(_ urls: [URL]) {
        let files = Array(Set(urls.filter { $0.isFileURL }.map { $0.standardizedFileURL })).sorted { $0.path < $1.path }
        guard !files.isEmpty else { return }
        queue.append(files)
        if initialized {
            window.makeKeyAndOrderFront(nil)
            append("Added \(files.count) file(s) or folder(s) to the queue.")
            clearQueueButton.isEnabled = busy && !queue.isEmpty
            nextBatch()
        }
    }
    func nextBatch() {
        guard initialized, !busy, !queue.isEmpty, preferencesSheet == nil else { return }
        let files = queue.removeFirst()
        let kind = ["auto", "disc", "cassette"][media.indexOfSelectedItem]
        busy = true; setBusyUI(true)
        statusLabel.stringValue = "Processing \(files.first!.lastPathComponent)…"
        // '--' keeps a filename from being interpreted as an option.
        var arguments = ["--media", kind, "--preview"]
        for (control, flag) in [(autoContrast, "--auto-contrast"), (autoBrightness, "--auto-brightness"),
                                (autoColor, "--auto-color"), (autoAll, "--auto-adjust"), (keepMetadata, "--keep-metadata")] {
            if control.state == .on { arguments.append(flag) }
        }
        arguments += ["--"] + files.map(\.path)
        showComparisons()
        let failuresBeforeBatch = failedCount
        worker.async {
            let result = self.engine.run(arguments) { line in
                DispatchQueue.main.async { self.received(line) }
            }
            DispatchQueue.main.async {
                self.busy = false; self.setBusyUI(false)
                switch result.code {
                case 0: self.statusLabel.stringValue = "Batch complete. Images and logs saved."
                case 2: self.statusLabel.stringValue = "Batch complete — review needed. Images and logs saved."
                default: self.statusLabel.stringValue = "Batch finished with errors. See result cards or Activity."
                    if self.failedCount == failuresBeforeBatch {
                        self.append(result.text.suffix(1800).description)
                        self.addComparison(["input": files[0].path, "error": String(result.text.suffix(450))])
                    }
                }
                self.nextBatch()
            }
        }
    }
    func received(_ line: String) {
        if let data = line.data(using: .utf8), let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let image = json["image"] as? String {
                latestOutput = URL(fileURLWithPath: image); revealButton.isEnabled = true
                let review = json["status"] as? String == "review_required"
                append("\(review ? "Review needed" : "Saved"): \(image)")
                addComparison(json)
                if let warnings = json["warnings"] as? [String], !warnings.isEmpty { append("  " + warnings.joined(separator: ", ")) }
            } else if let error = json["error"] as? String { append("Could not process \(json["input"] ?? "image"): \(error)"); addComparison(json) }
            else if json["status"] as? String == "processing", let input = json["input"] as? String {
                statusLabel.stringValue = "Processing \(URL(fileURLWithPath: input).lastPathComponent)…"
            }
        } else { append(line) }
    }
    func append(_ text: String) {
        activity.string += text + "\n"
        if activity.string.count > 30_000 { activity.string = String(activity.string.suffix(24_000)) }
        activity.scrollToEndOfDocument(nil)
    }
    func setBusyUI(_ value: Bool) {
        preferencesButton.isEnabled = !value; media.isEnabled = !value
        for control in [autoContrast, autoBrightness, autoColor, autoAll, keepMetadata] { control.isEnabled = !value }
        clearQueueButton.isEnabled = value && !queue.isEmpty
        value ? progress.startAnimation(nil) : progress.stopAnimation(nil)
    }
    @objc func clearQueue() { queue.removeAll(); clearQueueButton.isEnabled = false; append("Pending batches removed. The current batch will finish.") }
    @objc func revealOutput() { if let url = latestOutput { NSWorkspace.shared.activateFileViewerSelecting([url]) } }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard busy || !queue.isEmpty else { return .terminateNow }
        let alert = NSAlert()
        alert.messageText = "Processing is still running"
        alert.informativeText = "Let the current batch finish before quitting. You can remove pending batches with Clear Pending Batches."
        alert.addButton(withTitle: "Keep Processing")
        alert.runModal()
        return .terminateCancel
    }
    func readPreferences(_ text: String) {
        // Bootstrap messages may precede the CLI's final JSON line.
        for line in text.components(separatedBy: .newlines).reversed() {
            if let data = line.data(using: .utf8), let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], json["schema"] as? Int == 1 {
                saved = json
                let location = json["output_mode"] as? String == "fixed" ? (json["fixed_folder"] as? String ?? "") : "\(json["relative_folder"] as? String ?? "output") relative to each input folder"
                destinationLabel.stringValue = "Output: \(location) · separate image, preview and JSON folders"
                break
            }
        }
    }

    @objc func showPreferences() {
        guard !busy, preferencesSheet == nil else { NSSound.beep(); return }
        let sheet = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 610, height: 310), styleMask: [.titled], backing: .buffered, defer: false)
        sheet.title = "Output Preferences"
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        sheet.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: sheet.contentView!.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: sheet.contentView!.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: sheet.contentView!.topAnchor, constant: 24)])
        let heading = NSTextField(labelWithString: "Where should results go?"); heading.font = .boldSystemFont(ofSize: 17)
        stack.addArrangedSubview(heading)
        mode = NSPopUpButton(); mode.addItems(withTitles: ["Relative to each input folder", "One fixed location"])
        mode.selectItem(at: saved["output_mode"] as? String == "fixed" ? 1 : 0)
        mode.target = self; mode.action = #selector(preferenceModeChanged)
        stack.addArrangedSubview(mode)
        relativeField = NSTextField(string: saved["relative_folder"] as? String ?? "output")
        relativeField.placeholderString = "output"; relativeField.setAccessibilityLabel("Relative output folder")
        let relativeRow = NSStackView(views: [NSTextField(labelWithString: "Relative folder:"), relativeField]); relativeRow.spacing = 12
        relativeField.widthAnchor.constraint(equalToConstant: 410).isActive = true
        stack.addArrangedSubview(relativeRow)
        fixedField = NSTextField(string: saved["fixed_folder"] as? String ?? "")
        fixedField.placeholderString = "/Volumes/Archive/Prepared"; fixedField.setAccessibilityLabel("Fixed output folder")
        let fixedRow = NSStackView(views: [NSTextField(labelWithString: "Fixed folder:"), fixedField, button("Choose…", #selector(chooseOutput))]); fixedRow.spacing = 12
        fixedField.widthAnchor.constraint(equalToConstant: 325).isActive = true
        stack.addArrangedSubview(fixedRow)
        preferenceMessage = NSTextField(wrappingLabelWithString: "Default: output inside the source folder. These preferences also apply to the command line; -o overrides them for one run.")
        preferenceMessage.textColor = .secondaryLabelColor
        preferenceMessage.widthAnchor.constraint(equalToConstant: 560).isActive = true
        stack.addArrangedSubview(preferenceMessage)
        saveButton = button("Save", #selector(savePreferences)); saveButton.keyEquivalent = "\r"
        let cancel = button("Cancel", #selector(closePreferences)); cancel.keyEquivalent = "\u{1b}"
        let buttons = NSStackView(views: [button("Use Default", #selector(defaultPreferences)), cancel, saveButton]); buttons.spacing = 12
        stack.addArrangedSubview(buttons)
        preferencesSheet = sheet; preferenceModeChanged()
        window.beginSheet(sheet)
    }
    @objc func preferenceModeChanged() { relativeField.isEnabled = mode.indexOfSelectedItem == 0; fixedField.isEnabled = mode.indexOfSelectedItem == 1 }
    @objc func defaultPreferences() { mode.selectItem(at: 0); relativeField.stringValue = "output"; preferenceModeChanged() }
    @objc func chooseOutput() {
        guard let sheet = preferencesSheet else { return }
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.canCreateDirectories = true
        panel.prompt = "Use This Folder"
        panel.beginSheetModal(for: sheet) { response in
            if response == .OK, let url = panel.url { self.fixedField.stringValue = url.path; self.mode.selectItem(at: 1); self.preferenceModeChanged() }
        }
    }
    @objc func closePreferences() {
        guard saveButton.isEnabled, let sheet = preferencesSheet else { return }
        window.endSheet(sheet); preferencesSheet = nil; nextBatch()
    }
    @objc func savePreferences() {
        let fixed = mode.indexOfSelectedItem == 1
        let value = fixed ? fixedField.stringValue : relativeField.stringValue
        guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            preferenceMessage.stringValue = "Enter an output folder before saving."; return
        }
        if fixed && !(value as NSString).expandingTildeInPath.hasPrefix("/") {
            preferenceMessage.stringValue = "Choose an absolute fixed location, starting with / or ~/."; return
        }
        saveButton.isEnabled = false
        worker.async {
            let result = self.engine.run([fixed ? "--set-output-fixed" : "--set-output-relative", value])
            DispatchQueue.main.async {
                self.saveButton.isEnabled = true
                if result.code == 0 { self.readPreferences(result.text); self.closePreferences() }
                else { self.preferenceMessage.stringValue = String(result.text.suffix(350)) }
            }
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()

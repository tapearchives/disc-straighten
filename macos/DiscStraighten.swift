// Native drop target; the existing CLI owns all image processing and logs.
import Cocoa
import UniformTypeIdentifiers

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
        process.executableURL = root.appendingPathComponent("disc-straighten")
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
    let destinationLabel = NSTextField(wrappingLabelWithString: "Output: output inside each input folder · images and JSON logs together")
    let statusLabel = NSTextField(labelWithString: "Ready. Originals stay unchanged.")
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
                else { self.append(result.text); self.statusLabel.stringValue = "Setup needs attention. See activity below." }
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
        appMenu.addItem(withTitle: "Quit Disc Straighten", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu; bar.addItem(appItem)
        let fileItem = NSMenuItem(title: "File", action: nil, keyEquivalent: "")
        let fileMenu = NSMenu(title: "File")
        fileMenu.addItem(withTitle: "Add Images or Folders…", action: #selector(chooseFiles), keyEquivalent: "o").target = self
        fileItem.submenu = fileMenu; bar.addItem(fileItem)
        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit")
        for (name, selector, key) in [("Cut", #selector(NSText.cut(_:)), "x"), ("Copy", #selector(NSText.copy(_:)), "c"), ("Paste", #selector(NSText.paste(_:)), "v"), ("Select All", #selector(NSText.selectAll(_:)), "a")] {
            editMenu.addItem(withTitle: name, action: selector, keyEquivalent: key)
        }
        editItem.submenu = editMenu; bar.addItem(editItem)
        NSApp.mainMenu = bar
    }

    func button(_ title: String, _ action: Selector) -> NSButton {
        NSButton(title: title, target: self, action: action)
    }
    func makeWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 780, height: 600),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Disc Straighten · TapeArchives"
        window.minSize = NSSize(width: 660, height: 520)
        window.isReleasedWhenClosed = false
        window.center()
        let stack = NSStackView()
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        let content = window.contentView!
        content.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 22),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -22)])
        let title = NSTextField(labelWithString: "Straighten your archive photos")
        title.font = .systemFont(ofSize: 23, weight: .semibold)
        stack.addArrangedSubview(title)
        let subtitle = NSTextField(wrappingLabelWithString: "Flatten discs and compact cassettes, orient the artwork, and save transparent images with transformation logs.")
        subtitle.textColor = .secondaryLabelColor
        stack.addArrangedSubview(subtitle)
        let drop = DropView(frame: .zero)
        drop.receive = { [weak self] urls in self?.enqueue(urls) }
        let dropText = NSTextField(labelWithString: "Drop images or folders here")
        dropText.font = .systemFont(ofSize: 19, weight: .medium)
        dropText.translatesAutoresizingMaskIntoConstraints = false
        drop.addSubview(dropText)
        NSLayoutConstraint.activate([drop.heightAnchor.constraint(equalToConstant: 100),
            dropText.centerXAnchor.constraint(equalTo: drop.centerXAnchor), dropText.centerYAnchor.constraint(equalTo: drop.centerYAnchor)])
        stack.addArrangedSubview(drop)
        let controls = NSStackView()
        controls.spacing = 12
        controls.addArrangedSubview(button("Choose Images or Folders…", #selector(chooseFiles)))
        controls.addArrangedSubview(NSTextField(labelWithString: "Media:"))
        media.addItems(withTitles: ["Automatic", "Optical disc", "Compact cassette"])
        media.setAccessibilityLabel("Media type")
        controls.addArrangedSubview(media)
        preferencesButton = button("Preferences…", #selector(showPreferences))
        controls.addArrangedSubview(preferencesButton)
        stack.addArrangedSubview(controls)
        destinationLabel.font = .systemFont(ofSize: 12)
        destinationLabel.textColor = .secondaryLabelColor
        stack.addArrangedSubview(destinationLabel)
        progress.style = .bar; progress.isIndeterminate = true; progress.isDisplayedWhenStopped = false
        stack.addArrangedSubview(progress)
        stack.addArrangedSubview(statusLabel)
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true; scroll.borderType = .bezelBorder
        activity.isEditable = false; activity.isSelectable = true
        activity.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        activity.textColor = .labelColor
        activity.textContainerInset = NSSize(width: 10, height: 10)
        activity.isVerticallyResizable = true; activity.isHorizontallyResizable = false
        activity.autoresizingMask = [.width]
        activity.textContainer?.widthTracksTextView = true
        activity.setAccessibilityLabel("Processing activity")
        scroll.documentView = activity
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 100).isActive = true
        stack.addArrangedSubview(scroll)
        let bottom = NSStackView(); bottom.spacing = 12
        revealButton = button("Show Latest Output in Finder", #selector(revealOutput)); revealButton.isEnabled = false
        clearQueueButton = button("Finish Current Batch Only", #selector(clearQueue)); clearQueueButton.isEnabled = false
        bottom.addArrangedSubview(revealButton); bottom.addArrangedSubview(clearQueueButton)
        stack.addArrangedSubview(bottom)
        for view in [subtitle, drop, destinationLabel, progress, scroll] as [NSView] {
            view.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        }
        append("JPEG, PNG, TIFF, WebP and BMP. Folder scans do not include subfolders.\nExisting outputs are protected. Results marked ‘Review needed’ still include saved images and logs.")
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
        let arguments = ["--media", kind, "--preview", "--"] + files.map(\.path)
        worker.async {
            let result = self.engine.run(arguments) { line in
                DispatchQueue.main.async { self.received(line) }
            }
            DispatchQueue.main.async {
                self.busy = false; self.setBusyUI(false)
                switch result.code {
                case 0: self.statusLabel.stringValue = "Batch complete. Images and logs saved."
                case 2: self.statusLabel.stringValue = "Batch complete — review needed. Images and logs saved."
                default: self.statusLabel.stringValue = "Batch finished with errors. See activity below."
                    self.append(result.text.suffix(1800).description)
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
                if let warnings = json["warnings"] as? [String], !warnings.isEmpty { append("  " + warnings.joined(separator: ", ")) }
            } else if let error = json["error"] as? String { append("Could not process \(json["input"] ?? "image"): \(error)") }
        } else { append(line) }
    }
    func append(_ text: String) {
        activity.string += text + "\n"
        if activity.string.count > 30_000 { activity.string = String(activity.string.suffix(24_000)) }
        activity.scrollToEndOfDocument(nil)
    }
    func setBusyUI(_ value: Bool) {
        preferencesButton.isEnabled = !value; media.isEnabled = !value
        clearQueueButton.isEnabled = value && !queue.isEmpty
        value ? progress.startAnimation(nil) : progress.stopAnimation(nil)
    }
    @objc func clearQueue() { queue.removeAll(); clearQueueButton.isEnabled = false; append("Pending batches removed. The current batch will finish.") }
    @objc func revealOutput() { if let url = latestOutput { NSWorkspace.shared.activateFileViewerSelecting([url]) } }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard busy || !queue.isEmpty else { return .terminateNow }
        let alert = NSAlert()
        alert.messageText = "Processing is still running"
        alert.informativeText = "Let the current batch finish before quitting. You can remove pending batches with Finish Current Batch Only."
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
                destinationLabel.stringValue = "Output: \(location) · images and JSON logs together"
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

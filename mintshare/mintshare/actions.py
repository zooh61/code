"""Registry of every user-visible action (used by the main window, tray, CLI and workflows)."""

# id: (label, category, icon)
ACTIONS = {
    # capture
    "fullscreen":      ("Capture entire screen", "Capture", "video-display-symbolic"),
    "monitor":         ("Capture current monitor", "Capture", "video-joined-displays-symbolic"),
    "active_window":   ("Capture active window", "Capture", "window-new-symbolic"),
    "window":          ("Capture window (pick)", "Capture", "view-restore-symbolic"),
    "region":          ("Capture region", "Capture", "edit-select-all-symbolic"),
    "last_region":     ("Capture last region", "Capture", "view-refresh-symbolic"),
    "scrolling":       ("Scrolling capture", "Capture", "go-down-symbolic"),
    "auto_capture":    ("Auto capture (timed)", "Capture", "alarm-symbolic"),
    "webpage":         ("Webpage capture…", "Capture", "web-browser-symbolic"),
    "ocr":             ("Capture text (OCR)", "Capture", "insert-text-symbolic"),
    "record_screen":   ("Start/stop screen recording", "Capture", "media-record-symbolic"),
    "record_gif":      ("Start/stop GIF recording", "Capture", "camera-video-symbolic"),
    # upload
    "upload_files":    ("Upload files…", "Upload", "document-send-symbolic"),
    "upload_clipboard": ("Upload from clipboard", "Upload", "edit-paste-symbolic"),
    "upload_text":     ("Upload text…", "Upload", "text-x-generic-symbolic"),
    "upload_url":      ("Upload from URL…", "Upload", "network-transmit-symbolic"),
    "shorten_url":     ("Shorten URL…", "Upload", "insert-link-symbolic"),
    "drop_window":     ("Drop window", "Upload", "emblem-downloads-symbolic"),
    # tools
    "color_picker":    ("Screen color picker", "Tools", "color-select-symbolic"),
    "color_window":    ("Color picker window", "Tools", "applications-graphics-symbolic"),
    "ruler":           ("Ruler", "Tools", "measure-symbolic"),
    "pin_region":      ("Pin region to screen", "Tools", "view-pin-symbolic"),
    "pin_clipboard":   ("Pin clipboard image", "Tools", "view-pin-symbolic"),
    "editor":          ("Image editor…", "Tools", "applications-graphics-symbolic"),
    "effects":         ("Image effects…", "Tools", "image-x-generic-symbolic"),
    "combiner":        ("Image combiner…", "Tools", "view-dual-symbolic"),
    "splitter":        ("Image splitter…", "Tools", "view-grid-symbolic"),
    "thumbnailer":     ("Image thumbnailer…", "Tools", "zoom-out-symbolic"),
    "metadata":        ("Image metadata…", "Tools", "dialog-information-symbolic"),
    "video_converter": ("Video converter…", "Tools", "video-x-generic-symbolic"),
    "video_thumbs":    ("Video thumbnailer…", "Tools", "view-grid-symbolic"),
    "qr_generate":     ("QR code…", "Tools", "view-barcode-symbolic"),
    "qr_scan":         ("Scan QR code (region)", "Tools", "view-barcode-symbolic"),
    "hash_check":      ("Hash check…", "Tools", "emblem-system-symbolic"),
    "indexer":         ("Directory indexer…", "Tools", "folder-symbolic"),
    "net_tools":       ("Ping & DNS lookup…", "Tools", "network-wired-symbolic"),
    "monitor_test":    ("Monitor test", "Tools", "video-display-symbolic"),
    # app
    "open_main":       ("Open MintShare", "App", "applications-graphics-symbolic"),
    "open_history":    ("History", "App", "document-open-recent-symbolic"),
    "open_folder":     ("Open screenshots folder", "App", "folder-pictures-symbolic"),
    "open_settings":   ("Settings", "App", "preferences-system-symbolic"),
    "quit":            ("Quit", "App", "application-exit-symbolic"),
}

JOBS = [k for k, v in ACTIONS.items() if v[1] in ("Capture", "Upload", "Tools") and k not in ("drop_window",)]

AFTER_CAPTURE = [
    ("effects", "Add image effects / watermark"), ("editor", "Open in image editor"),
    ("copy_image", "Copy image to clipboard"), ("print", "Print image"), ("save", "Save image to file"),
    ("save_as", "Save image to file as…"), ("upload", "Upload image to host"), ("pin", "Pin to screen"),
    ("ocr", "Recognize text (OCR) → clipboard"), ("delete_after_upload", "Delete local file after upload"),
    ("open_file", "Open file"), ("open_folder", "Show file in folder"),
]
AFTER_UPLOAD = [
    ("shorten", "Shorten URL"), ("copy_url", "Copy URL to clipboard"), ("open_url", "Open URL in browser"),
    ("show_qr", "Show QR code of URL"),
]

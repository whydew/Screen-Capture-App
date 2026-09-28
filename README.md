# Screen Capture to PDF

A small Windows app that screenshots a monitor or app window, presses a key to move to the next page, and repeats until you press Esc. When you stop, it can combine the screenshots into a single PDF with searchable OCR text.

It's built for capturing documents that you can only page through on screen, such as reports, statements, e-books, or slide viewers that don't offer an export.

## Features

- Capture any monitor, or a single app window (the capture follows the window if you move it)
- Adjustable time between screenshots, so slower PCs have time to load each page
- Configurable key to press after each shot (`alt+right` by default, or `page down`, `right`, `ctrl+tab`, or none)
- Countdown before starting, so you can click into the right window
- Name the output folder and pick where it's saved
- Press Esc from any app to stop
- After stopping, create a searchable PDF (OCR), a plain PDF, or keep the screenshots only
- Minimizes itself while capturing so it doesn't appear in the screenshots

## Download

Go to the [Releases](../../releases) page, download the latest zip, and extract it. Keep `ScreenCaptureToPDF.exe` and the `Tesseract-OCR` folder together in the same folder, since the app uses that folder for OCR.

## How to use

1. Open the page or document you want to capture and go to the first page.
2. Run `ScreenCaptureToPDF.exe`.
3. Under **Capture**, pick a monitor or an app window. Press **Refresh** if the window you want isn't listed.
4. Set **Seconds between screenshots**. Start with 1.0 and raise it if pages are being captured before they finish loading.
5. Set the **Key to press after each shot** to whatever moves your document forward one page.
6. Enter a **Folder name**, pick a location with **Browse**, and choose what to create when stopped.
7. Press **Start**. If you picked a monitor, click into the target window during the countdown.
8. Press **Esc** when you reach the last page.

The app saves screenshots as `0001.png`, `0002.png`, and so on. If you chose a PDF option, the PDF appears in the same folder with the folder's name. OCR takes a few seconds per page, and the progress shows in the app window and taskbar title.

If a folder with the same name already exists, the app creates a new one with `(2)`, `(3)`, etc. added instead of overwriting it.

## Running from source

Requires Windows and Python 3.9 or newer.

```
pip install -r requirements.txt
python screen_capture_app.py
```

For OCR, install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki). The app looks for it in these places, in order:

1. A `Tesseract-OCR` folder next to the app
2. `C:\Program Files\Tesseract-OCR`
3. `C:\Program Files (x86)\Tesseract-OCR`
4. `%LOCALAPPDATA%\Programs\Tesseract-OCR`
5. Your `PATH`

## Building the exe

On a Windows PC with Python and Tesseract installed, double-click `build_exe.bat`. It installs the dependencies, builds `ScreenCaptureToPDF.exe` with PyInstaller, and copies your Tesseract install into the `dist` folder. Zip the `dist` folder to share it or attach it to a release.

## Troubleshooting

**Pages are blank, half-loaded, or repeated.** Raise the seconds between screenshots.

**The key press does nothing.** The target window needs to be in focus. Click into it during the countdown, and avoid clicking other windows while it runs. Some apps also need a different key than `alt+right`.

**App window captures are offset or cropped.** This can happen on displays with scaling above 100%. Capturing the whole monitor instead usually works.

**"OCR needs Tesseract" error.** Make sure the `Tesseract-OCR` folder is next to the exe, or install Tesseract. You can also choose "Plain PDF (no OCR)".

**Antivirus or work PC blocks the exe.** Unsigned PyInstaller apps that listen for keypresses are sometimes flagged as a false positive. On a managed PC, you may need IT to allow it. You can also run it from source.

## Files

| File | Purpose |
|---|---|
| `screen_capture_app.py` | The app |
| `build_exe.bat` | Builds the exe and bundles Tesseract |
| `requirements.txt` | Python dependencies |

## License

Add a license of your choice. Tesseract is distributed under the Apache 2.0 license, so include its license file when you share the bundled `Tesseract-OCR` folder.
